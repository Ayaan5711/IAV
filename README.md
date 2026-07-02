# IAV — Gemini Media Enhancement POC

A proof-of-concept for AI-assisted media enhancement capabilities intended to plug into an SME-facing content authoring engine. Built around Google's Gemini family of models (via Vertex AI).

## Use cases in scope

1. **Image enhancement** — SME hand-drawn diagrams rendered as professional images
2. **Audio**
   - Text → Audio (script-driven TTS)
   - Audio → Audio (raw recording → transcribe → TTS)
3. **Video → Questions** — generate question/answer sets from a source video
4. **Video → Professional video** — clean up SME tutorial recordings

## Shape of the POC

- Backend: Python module per capability, behind a unified interface
- Frontend: Minimal Streamlit UI, one tab per capability
- Auth: Google Cloud service account (Vertex AI)
- I/O: Industry-standard formats (PNG/JPG, MP3/WAV, MP4, JSON)

## Planning

See [`docs/POC_PLAN.md`](docs/POC_PLAN.md) for the refined scope, architecture, build order, and open items.

The underlying capability feasibility analysis (model availability, pricing, limitations) lives in the original feasibility document referenced in that plan.

## System dependencies

The **Video → Professional** capability runs an ffmpeg filter chain. Install
ffmpeg before using that tab:

- Linux: `sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: download from <https://www.gyan.dev/ffmpeg/builds/> and add to PATH

All other capabilities work without ffmpeg.

## Running

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Drop your service account JSON at .credentials/service-account.json
.venv/bin/streamlit run app.py
```

## Status

Phase 4 (Video → Professional) implemented. POC functionally complete pending
end-to-end verification across all four capabilities.
