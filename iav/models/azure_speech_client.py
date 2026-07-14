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

import logging
import os
import shutil
import subprocess
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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

RECOGNITION_TIMEOUT_SECONDS = 600


class AzureSpeechUnavailable(RuntimeError):
    """Raised when Azure Speech can't be used -- caller should fall back."""


@dataclass
class AzureTranscriptionResult:
    text: str
    language: str


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
        audio_config = speechsdk.audio.AudioConfig(filename=str(wav_path))
        recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

        segments: list[str] = []
        errors: list[str] = []
        done = threading.Event()

        def _on_recognized(evt: object) -> None:
            result = evt.result  # type: ignore[attr-defined]
            if result.reason == speechsdk.ResultReason.RecognizedSpeech and result.text:
                segments.append(result.text)

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
        return AzureTranscriptionResult(text=text, language=language)
    finally:
        if cleanup:
            cleanup()


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

    logger.info(
        "azure_speech: resampled %s to 16kHz mono via pure-Python audioop (no ffmpeg needed)",
        audio_path.name,
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
