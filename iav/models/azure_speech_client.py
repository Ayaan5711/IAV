"""Azure Speech wrapper — transcription for Audio-to-Audio.

Optional dependency: if the SDK isn't installed or AZURE_SPEECH_KEY /
AZURE_SPEECH_REGION aren't set, every function here raises
AzureSpeechUnavailable rather than crashing the app. Callers should catch
that and fall back to another ASR path.

Azure's acoustic models are markedly more robust to background noise than
prompting a general-purpose model to "transcribe verbatim" -- that's the
"noise cleaning" this module provides. It is not a separate denoise pass;
the installed SDK version (1.50.0) does not expose a dedicated noise
-suppression toggle in its Python bindings, so this doesn't claim one.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import wave
import xml.sax.saxutils as saxutils
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

try:
    import azure.cognitiveservices.speech as speechsdk
    _SDK_AVAILABLE = True
except ImportError:
    speechsdk = None  # type: ignore[assignment]
    _SDK_AVAILABLE = False

try:
    import audioop
    _AUDIOOP_AVAILABLE = True
except ImportError:
    audioop = None  # type: ignore[assignment]
    _AUDIOOP_AVAILABLE = False

try:
    # Makes `ssl` (and therefore requests/urllib3) verify against the OS's
    # native certificate store instead of the bundled certifi list. Needed
    # behind a corporate TLS-inspecting proxy, where Windows already trusts
    # the proxy's injected root CA but certifi doesn't -- without this, the
    # REST fallback below fails with CERTIFICATE_VERIFY_FAILED even though
    # the same host is reachable fine from Postman or a browser.
    import truststore
    truststore.inject_into_ssl()
    _TRUSTSTORE_ACTIVE = True
except ImportError:
    _TRUSTSTORE_ACTIVE = False

RECOGNITION_TIMEOUT_SECONDS = 600
REST_TIMEOUT_SECONDS = 30
REST_MAX_BYTES = 10 * 1024 * 1024  # Azure's short-audio REST endpoint's own cap


class AzureSpeechUnavailable(RuntimeError):
    """Raised when Azure Speech can't be used -- caller should fall back."""


@dataclass
class AzureTranscriptionResult:
    text: str
    language: str
    # Azure Speech bills per hour of audio processed, not per token -- best
    # effort from the actual WAV sent to Azure; None when it couldn't be
    # measured (cost tracking degrades gracefully in that case).
    duration_seconds: float | None = None


def _wav_file_duration_seconds(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            return frames / rate if rate else None
    except (wave.Error, EOFError, OSError) as exc:
        logger.warning("azure_speech: could not read duration from %s: %s", path.name, exc)
        return None


def is_configured() -> bool:
    if not _SDK_AVAILABLE:
        logger.info("azure_speech: not configured -- azure-cognitiveservices-speech is not installed")
        return False
    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        logger.info(
            "azure_speech: not configured -- AZURE_SPEECH_KEY=%s, AZURE_SPEECH_REGION=%s",
            "set" if key else "MISSING", "set" if region else "MISSING",
        )
        return False
    return True


def _apply_proxy(speech_config: "speechsdk.SpeechConfig") -> None:
    """Points the SDK's native transport at the corporate proxy, if one is
    configured.

    Unlike `requests` (used by the REST paths below), the Speech SDK's own
    WebSocket connection does NOT pick up a proxy automatically -- it only
    uses one if told to explicitly via set_proxy(). Behind a network that
    requires all outbound traffic through the proxy, skipping this makes
    the SDK try a direct connection and fail with
    WS_OPEN_ERROR_UNDERLYING_IO_OPEN_FAILED, even when the same proxy
    already works fine for this app's REST calls.

    Checks AZURE_SPEECH_PROXY_HOST / AZURE_SPEECH_PROXY_PORT (+ optional
    _USERNAME / _PASSWORD) first -- explicit, app-specific settings that go
    in .env alongside AZURE_SPEECH_KEY/AZURE_SPEECH_REGION, not guessed
    from ambient system state. Falls back to parsing the standard
    HTTPS_PROXY/HTTP_PROXY env vars if those aren't set, for setups where
    the OS/shell already exports one.
    """
    host = os.environ.get("AZURE_SPEECH_PROXY_HOST")
    port_raw = os.environ.get("AZURE_SPEECH_PROXY_PORT")
    if host and port_raw:
        try:
            port = int(port_raw)
        except ValueError:
            logger.warning(
                "azure_speech: AZURE_SPEECH_PROXY_PORT=%r is not a valid integer -- SDK proxy not configured",
                port_raw,
            )
            return
        username = os.environ.get("AZURE_SPEECH_PROXY_USERNAME") or None
        password = os.environ.get("AZURE_SPEECH_PROXY_PASSWORD") or None
        speech_config.set_proxy(host, port, username, password)
        logger.info("azure_speech: configured SDK to use proxy %s:%d (from AZURE_SPEECH_PROXY_HOST/PORT)", host, port)
        return

    proxy_url = (
        os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    )
    if not proxy_url:
        return
    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port:
        logger.warning(
            "azure_speech: HTTPS_PROXY/HTTP_PROXY is set (%s) but couldn't be parsed as "
            "host:port -- SDK proxy not configured",
            proxy_url,
        )
        return
    speech_config.set_proxy(parsed.hostname, parsed.port, parsed.username, parsed.password)
    logger.info("azure_speech: configured SDK to use proxy %s:%d (from HTTPS_PROXY/HTTP_PROXY)", parsed.hostname, parsed.port)


def transcribe_file(audio_path: Path, *, language: str = "en-US") -> AzureTranscriptionResult:
    """Continuous recognition over an audio file, returns the full transcript.

    Azure's AudioConfig(filename=...) wants WAV natively; non-WAV input is
    converted first via ffmpeg (see _ensure_wav).
    """
    if not _SDK_AVAILABLE:
        raise AzureSpeechUnavailable("azure-cognitiveservices-speech is not installed.")

    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        raise AzureSpeechUnavailable("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION are not set.")

    wav_path, cleanup = _ensure_wav(audio_path)
    try:
        speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        speech_config.speech_recognition_language = language
        _apply_proxy(speech_config)
        audio_config = speechsdk.audio.AudioConfig(filename=str(wav_path))
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        segments: list[str] = []
        errors: list[str] = []
        done = threading.Event()

        def _on_recognized(evt: object) -> None:
            result = evt.result  # type: ignore[attr-defined]
            if result.reason == speechsdk.ResultReason.RecognizedSpeech and result.text:
                segments.append(result.text)
            elif result.reason == speechsdk.ResultReason.NoMatch:
                no_match = speechsdk.NoMatchDetails.from_result(result)
                logger.warning(
                    "azure_speech: NoMatch on a segment -- reason=%s (audio reached Azure fine, "
                    "it just didn't detect recognizable speech in it)",
                    no_match.reason,
                )
            else:
                logger.warning("azure_speech: unexpected result.reason=%s on a segment", result.reason)

        def _on_canceled(evt: object) -> None:
            if evt.reason == speechsdk.CancellationReason.Error:  # type: ignore[attr-defined]
                errors.append(evt.error_details or "unknown Azure Speech error")  # type: ignore[attr-defined]
            done.set()

        def _on_stopped(evt: object) -> None:
            done.set()

        recognizer.recognized.connect(_on_recognized)
        recognizer.canceled.connect(_on_canceled)
        recognizer.session_stopped.connect(_on_stopped)

        logger.info(
            "azure_speech: starting continuous recognition (language=%s, file=%s)",
            language, wav_path.name,
        )
        recognizer.start_continuous_recognition()
        finished = done.wait(timeout=RECOGNITION_TIMEOUT_SECONDS)
        recognizer.stop_continuous_recognition()

        if not finished:
            raise AzureSpeechUnavailable(
                f"Azure Speech recognition timed out after {RECOGNITION_TIMEOUT_SECONDS}s."
            )
        if errors:
            raise AzureSpeechUnavailable(f"Azure Speech recognition failed: {errors[0]}")

        text = " ".join(segments).strip()
        logger.info("azure_speech: recognized %d segment(s), %d chars", len(segments), len(text))
        duration_seconds = _wav_file_duration_seconds(wav_path)

        if text:
            return AzureTranscriptionResult(text=text, language=language, duration_seconds=duration_seconds)

        # Retry via REST while wav_path (the normalized 16kHz mono PCM WAV,
        # same file the SDK just used) still exists on disk -- cleanup()
        # below deletes it, and the original audio_path isn't necessarily a
        # WAV at all (e.g. an mp3/m4a/webm upload), which would make
        # _wav_format_content_type() silently mislabel raw non-WAV bytes as
        # WAV/PCM instead of declaring their real format.
        logger.info(
            "azure_speech: SDK path recognized no text -- retrying via Azure's REST endpoint "
            "directly, declaring the real audio format explicitly (this is what a direct Postman "
            "call against Azure does, bypassing the SDK's local AudioConfig(filename=...) WAV parsing)"
        )
        rest_text = _transcribe_via_rest(wav_path, language=language, key=key, region=region)
        if rest_text:
            logger.info("azure_speech: REST retry succeeded where the SDK path did not")
            rest_duration = _wav_file_duration_seconds(wav_path) or duration_seconds
            return AzureTranscriptionResult(text=rest_text, language=language, duration_seconds=rest_duration)

        return AzureTranscriptionResult(text="", language=language)
    finally:
        if cleanup:
            cleanup()


def _wav_format_content_type(audio_path: Path) -> str | None:
    """Reads the real WAV header (sample rate / bit depth / channels) so the
    REST call can declare the file's actual format explicitly -- the same
    thing a direct Postman request does. Returns None for anything the REST
    endpoint's simple PCM content-type can't describe (e.g. non-WAV, or
    8/24/32-bit samples), in which case the caller assumes 16kHz mono PCM.
    """
    try:
        with wave.open(str(audio_path), "rb") as src:
            channels = src.getnchannels()
            sample_width = src.getsampwidth()
            frame_rate = src.getframerate()
    except (wave.Error, EOFError):
        return None
    if sample_width != 2 or channels not in (1, 2):
        return None
    return f"audio/wav; codecs=audio/pcm; samplerate={frame_rate}"


def _transcribe_via_rest(audio_path: Path, *, language: str, key: str, region: str) -> str | None:
    """Azure's short-audio REST endpoint, called the same way Postman would --
    with the audio's real format declared explicitly in Content-Type, instead
    of relying on the SDK's local WAV parsing.

    Only handles a single utterance up to ~60s / 10MB (Azure's own limit on
    this endpoint); returns None for anything larger, any network/HTTP
    failure, or a non-success recognition status, so the caller can treat it
    as "no better answer than the SDK path already gave."
    """
    try:
        size = audio_path.stat().st_size
    except OSError as exc:
        logger.warning("azure_speech: could not stat %s for REST call: %s", audio_path.name, exc)
        return None
    if size > REST_MAX_BYTES:
        logger.info(
            "azure_speech: %s (%d bytes) exceeds the short-audio REST endpoint's limit, skipping REST retry",
            audio_path.name, size,
        )
        return None

    try:
        raw = audio_path.read_bytes()
    except OSError as exc:
        logger.warning("azure_speech: could not read %s for REST call: %s", audio_path.name, exc)
        return None

    content_type = _wav_format_content_type(audio_path) or "audio/wav; codecs=audio/pcm; samplerate=16000"
    url = f"https://{region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": content_type,
        "Accept": "application/json",
    }
    try:
        resp = requests.post(
            url,
            params={"language": language, "format": "simple"},
            headers=headers,
            data=raw,
            timeout=REST_TIMEOUT_SECONDS,
        )
    except requests.exceptions.SSLError as exc:
        if _TRUSTSTORE_ACTIVE:
            logger.warning("azure_speech: REST call failed with a certificate error even with truststore active: %s", exc)
        else:
            logger.warning(
                "azure_speech: REST call failed with a certificate verification error (%s). This is "
                "typical behind a corporate TLS-inspecting proxy -- install 'truststore' "
                "(pip install truststore) so this call trusts the same certificates Windows/Postman "
                "already do, then restart the app.",
                exc,
            )
        return None
    except requests.RequestException as exc:
        logger.warning("azure_speech: REST call failed (%s)", exc)
        return None

    if resp.status_code != 200:
        logger.warning(
            "azure_speech: REST call returned HTTP %d: %s",
            resp.status_code, resp.text[:300],
        )
        return None

    try:
        payload = resp.json()
    except ValueError:
        logger.warning("azure_speech: REST call returned a non-JSON body")
        return None

    status = payload.get("RecognitionStatus")
    if status != "Success":
        logger.info("azure_speech: REST recognition status=%s (no usable text)", status)
        return None

    text = (payload.get("DisplayText") or "").strip()
    logger.info("azure_speech: REST call succeeded (content-type=%s), %d chars", content_type, len(text))
    return text or None


def _resample_wav_pure_python(audio_path: Path) -> tuple[Path, Callable[[], None]] | None:
    """Resamples a real WAV file to 16kHz mono 16-bit PCM using only the
    standard library (wave + audioop) -- no ffmpeg required.

    This is what Azure's AudioConfig(filename=...) reliably supports;
    Gemini's own TTS output is 24kHz, which is outside that and is exactly
    what silently produced zero recognized segments. Returns None (caller
    should fall back to ffmpeg) if audioop isn't available, the file isn't
    readable as WAV, or the sample width isn't the common 16-bit case.
    """
    if not _AUDIOOP_AVAILABLE:
        return None
    try:
        with wave.open(str(audio_path), "rb") as src:
            channels = src.getnchannels()
            sample_width = src.getsampwidth()
            frame_rate = src.getframerate()
            frames = src.readframes(src.getnframes())
    except (wave.Error, EOFError) as exc:
        logger.warning("azure_speech: could not read %s as WAV for resampling: %s", audio_path.name, exc)
        return None

    if frame_rate == 16000 and channels == 1 and sample_width == 2:
        return None  # already the format Azure wants -- nothing to do
    if sample_width != 2:
        logger.warning(
            "azure_speech: unsupported sample width %d for pure-Python resampling, skipping",
            sample_width,
        )
        return None

    if channels == 2:
        frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
        channels = 1
    if frame_rate != 16000:
        frames, _ = audioop.ratecv(frames, sample_width, channels, frame_rate, 16000, None)
        frame_rate = 16000

    tmp_dir = tempfile.mkdtemp(prefix="iav-azure-speech-")
    out_path = Path(tmp_dir) / "resampled.wav"
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(sample_width)
        out.setframerate(frame_rate)
        out.writeframes(frames)

    def _cleanup() -> None:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    duration_s = (len(frames) / (sample_width * channels)) / frame_rate if frame_rate else 0
    peak = audioop.max(frames, sample_width) if frames else 0
    logger.info(
        "azure_speech: resampled %s to 16kHz mono via pure-Python audioop (no ffmpeg needed) -- "
        "duration=%.2fs, peak_amplitude=%d/32768 (near 0 means the audio is effectively silent)",
        audio_path.name, duration_s, peak,
    )
    return out_path, _cleanup


def _ensure_wav(audio_path: Path) -> tuple[Path, Callable[[], None] | None]:
    """Normalizes to 16kHz mono 16-bit PCM WAV -- what Azure's
    AudioConfig(filename=...) reliably supports.

    Azure is picky about WAV internals (sample rate, bit depth, channel
    count), not just the container/extension -- it doesn't raise an error
    on a mismatch, it just silently recognizes zero segments. Real .wav
    uploads and Gemini's own 24kHz TTS output both commonly fall outside
    what it wants. Tries a pure-Python resample first (no ffmpeg needed);
    falls back to ffmpeg for non-WAV input or anything the pure-Python
    path can't handle.

    Returns (path, cleanup) -- cleanup removes any temp file created here;
    None when the original file was used directly.
    """
    if audio_path.suffix.lower() == ".wav":
        resampled = _resample_wav_pure_python(audio_path)
        if resampled is not None:
            return resampled

    if not shutil.which("ffmpeg"):
        if audio_path.suffix.lower() == ".wav":
            logger.warning(
                "azure_speech: ffmpeg not on PATH and pure-Python resampling wasn't applicable -- "
                "using the uploaded WAV as-is, which may not recognize correctly if its internals "
                "aren't 16kHz mono PCM"
            )
            return audio_path, None
        raise AzureSpeechUnavailable(
            f"Input is {audio_path.suffix} but ffmpeg is not on PATH to convert it for Azure Speech."
        )

    tmp_dir = tempfile.mkdtemp(prefix="iav-azure-speech-")
    out_path = Path(tmp_dir) / "converted.wav"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio_path), "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(out_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0 or not out_path.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
        stderr_tail = (proc.stderr or b"").decode("utf-8", errors="replace")[-500:]
        if audio_path.suffix.lower() == ".wav":
            logger.warning("azure_speech: ffmpeg normalization failed, using uploaded WAV as-is: %s", stderr_tail)
            return audio_path, None
        raise AzureSpeechUnavailable(f"ffmpeg conversion to WAV failed: {stderr_tail}")

    def _cleanup() -> None:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return out_path, _cleanup


def synthesize_speech(text: str, *, voice: str) -> bytes:
    """Text-to-speech via Azure Neural TTS. Returns a complete 24kHz mono
    16-bit PCM WAV file (RIFF header included) -- unlike Gemini's TTS, which
    returns raw PCM the caller has to wrap itself, this is already a
    ready-to-write WAV container.

    Single-voice only -- Azure Neural TTS here doesn't do the multi-speaker
    dialogue Gemini's TTS supports; callers should route multi-speaker
    requests to Gemini regardless of the selected engine.

    Tries the SDK first, then falls back to the REST endpoint. The SDK's
    WebSocket transport does its own TLS/network handling independent of
    Python's `ssl` module and doesn't read HTTPS_PROXY/HTTP_PROXY on its
    own (see _apply_proxy()) -- behind a network that requires all
    outbound traffic through a proxy, an unconfigured SDK path fails with
    a connection error even once that proxy is set as an env var and the
    REST path (which `requests` picks it up for automatically) succeeds.
    The REST fallback here stays as a backstop for whatever _apply_proxy()
    doesn't cover. Same shape as _transcribe_via_rest()'s relationship to
    the SDK ASR path.
    """
    if not _SDK_AVAILABLE:
        raise AzureSpeechUnavailable("azure-cognitiveservices-speech is not installed.")

    key = os.environ.get("AZURE_SPEECH_KEY")
    region = os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        raise AzureSpeechUnavailable("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION are not set.")

    try:
        return _synthesize_via_sdk(text, voice=voice, key=key, region=region)
    except AzureSpeechUnavailable as sdk_exc:
        logger.warning(
            "azure_speech: SDK-based synthesis failed, retrying via REST endpoint: %s", sdk_exc
        )
        try:
            return _synthesize_via_rest(text, voice=voice, key=key, region=region)
        except AzureSpeechUnavailable as rest_exc:
            raise AzureSpeechUnavailable(
                f"Both the SDK and REST synthesis paths failed. SDK: {sdk_exc} | REST: {rest_exc}"
            ) from rest_exc


def _wav_has_audio_frames(data: bytes) -> bool:
    """True if `data` parses as a WAV container with at least one actual
    audio frame.

    Observed in practice: Azure can report a "successful" synthesis that's
    really just a bare RIFF header with zero samples (44 bytes -- the
    minimal WAV header size, with no audio data after it) -- typically
    when the requested voice can't produce intelligible speech for the
    given text (e.g. an English voice given non-Latin-script text it can't
    phonemize). Treating that as success would silently ship broken/near-
    empty output. Returns True for anything that doesn't parse as WAV at
    all, so this only rejects the specific "valid WAV, zero frames" case
    rather than second-guessing formats it doesn't understand.
    """
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            return wav.getnframes() > 0
    except (wave.Error, EOFError):
        return True


def _synthesize_via_sdk(text: str, *, voice: str, key: str, region: str) -> bytes:
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_synthesis_voice_name = voice
    _apply_proxy(speech_config)
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm
    )
    # audio_config=None -- return the audio in-memory instead of playing it
    # to a speaker or writing it to a file, since this runs headless.
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)

    logger.info("azure_speech: synthesizing speech via SDK (voice=%s, chars=%d)", voice, len(text))
    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        audio_bytes = result.audio_data
        if not audio_bytes or not _wav_has_audio_frames(audio_bytes):
            # Observed in practice: the SDK reports success with 0 bytes (or
            # a header-only WAV with 0 frames) and no cancellation/error
            # detail at all. Treating that as success would save a broken
            # (silent) output file -- raise so the REST fallback above gets
            # a real chance, and Auto mode can fall back to Gemini instead.
            raise AzureSpeechUnavailable(
                f"Azure Speech SDK reported synthesis completed but returned no actual audio "
                f"({len(audio_bytes)} bytes) -- often means the voice couldn't produce speech "
                "for this text (e.g. a voice/language mismatch)."
            )
        logger.info("azure_speech: SDK synthesis completed (%d bytes)", len(audio_bytes))
        return audio_bytes

    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        raise AzureSpeechUnavailable(
            f"Azure Speech synthesis canceled: {details.reason} -- {details.error_details}"
        )
    raise AzureSpeechUnavailable(f"Azure Speech synthesis failed: reason={result.reason}")


def _voice_locale(voice: str) -> str:
    """Derives the xml:lang locale (e.g. "en-IN") from an Azure voice name
    (e.g. "en-IN-NeerjaNeural") -- config.yaml offers en-GB/en-IN voices
    alongside en-US ones, so this can't be hardcoded to "en-US".
    """
    parts = voice.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return "en-US"


def _synthesize_via_rest(text: str, *, voice: str, key: str, region: str) -> bytes:
    """Azure Neural TTS via the REST endpoint -- plain HTTPS POST, no
    WebSocket, so it benefits from the truststore fix the same way the
    speech-to-text REST fallback does.
    """
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    locale = _voice_locale(voice)
    ssml = (
        f"<speak version='1.0' xml:lang='{locale}'>"
        f"<voice xml:lang='{locale}' name='{saxutils.escape(voice)}'>"
        f"{saxutils.escape(text)}"
        "</voice></speak>"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm",
        "User-Agent": "iav-azure-speech-rest",
    }
    logger.info("azure_speech: synthesizing speech via REST (voice=%s, chars=%d)", voice, len(text))
    try:
        resp = requests.post(url, headers=headers, data=ssml.encode("utf-8"), timeout=REST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise AzureSpeechUnavailable(f"REST TTS call failed: {exc}") from exc

    if resp.status_code != 200:
        raise AzureSpeechUnavailable(f"REST TTS returned HTTP {resp.status_code}: {resp.text[:300]}")
    if not resp.content:
        raise AzureSpeechUnavailable("REST TTS returned an empty response body.")
    if not _wav_has_audio_frames(resp.content):
        raise AzureSpeechUnavailable(
            f"REST TTS returned a WAV response with no actual audio frames ({len(resp.content)} "
            "bytes -- likely just a header) -- often means the voice couldn't produce speech "
            "for this text (e.g. a voice/language mismatch)."
        )

    logger.info("azure_speech: REST synthesis completed (%d bytes)", len(resp.content))
    return resp.content
