# Status: ON HOLD (2026-06)

MVP scaffold is committed and pushed. **Active development paused** — focus is on [care-visit-ai](https://github.com/fluent93/care-visit-ai) (Strategy A).

## What's done (resume from here)

- [x] `schema.py` — action items / decisions / open questions JSON
- [x] `providers.py` + `stt.py` — Gemini extract + STT
- [x] `webapp/server.py` — English UI, PIN, Markdown export, feedback
- [x] `render.yaml` — Render blueprint (not deployed)
- [x] GitHub: https://github.com/fluent93/meeting-actions (`a4f3177`)

## When resuming

1. Render Blueprint deploy + `GEMINI_API_KEY`
2. Apply PIN UX improvements from care-visit-ai `50f0f45` if needed
3. 3 English beta users → r/SideProject

## Local run

```powershell
cd D:\meeting-actions
pip install -r requirements.txt
$env:GEMINI_API_KEY="..."
uvicorn webapp.server:app --port 8001
```
