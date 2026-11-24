# IAV — Gemini Media Enhancement POC (HOELT)

A Streamlit proof-of-concept for SME content-authoring workflows, built
on Vertex AI (Gemini, Veo, Gemini Omni), with Azure as a configurable
fallback for some capabilities.

**Start here:** [`CLAUDE.md`](CLAUDE.md) — architecture, the full
capability inventory, how to run it, and the environment setup. For
everything video-specific in depth — what's live-verified, what's only
documented, every bug found and fixed, and the design for what's next —
see [`docs/VIDEO_CAPABILITIES.md`](docs/VIDEO_CAPABILITIES.md).

```bash
pip install -r requirements.txt
streamlit run app.py             # main shell: image + audio capabilities
streamlit run video_studio.py    # standalone shell: every video capability
```

Needs `.env` + `.credentials/service-account.json` — see `CLAUDE.md` §6.
