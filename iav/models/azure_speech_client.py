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


def _ensure_wav(audio_path: Path) -> tuple[Path, Callable[[], None] | None]:
    """Returns a WAV path Azure can read, converting via ffmpeg if needed.

    Returns (path, cleanup) -- cleanup removes any temp file created here;
    None when the original file was already used directly.
    """
    if audio_path.suffix.lower() == ".wav":
        return audio_path, None

    if not shutil.which("ffmpeg"):
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
        raise AzureSpeechUnavailable(f"ffmpeg conversion to WAV failed: {stderr_tail}")

    def _cleanup() -> None:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return out_path, _cleanup
