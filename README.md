# Meeting Actions — MVP

Drop a meeting recording → **action items, decisions, open questions** as structured JSON + Markdown.

English-first, global indie SaaS track (**Strategy B**), built in parallel with [care-visit-ai](https://github.com/fluent93/care-visit-ai) (**Strategy A**).

## Quick start

```powershell
cd D:\meeting-actions
pip install -r requirements.txt
$env:GEMINI_API_KEY="your-key"
uvicorn webapp.server:app --host 0.0.0.0 --port 8001
# → http://localhost:8001
```

## Architecture

```
[audio] → stt.GeminiSTTProvider → [transcript]
[transcript] → providers.GeminiProvider.extract() → schema OUTPUT_SCHEMA
```

Same patterns as care-visit-ai: swappable STT/LLM, fixed JSON contract, PIN-protected share links.

## Deploy (Render)

1. Push to GitHub → New Blueprint → `render.yaml`
2. Set `GEMINI_API_KEY`
3. Share URL with beta users

## Dual-track plan (with care-visit-ai)

| Week | A: 진료 동행 | B: Meeting Actions |
|------|-------------|-------------------|
| 1 | PIN + 피드백 + 5가구 파일럿 | MVP deploy + 3 beta users |
| 2–4 | Supabase prep, 프롬프트 조이기 | Product Hunt / r/SideProject |
| 6+ | 유료 20가구 | Stripe $9/mo if 10+ active users |

## Next (v0.2)

- [ ] Stripe / Lemon Squeezy
- [ ] Whisper API option (longer meetings)
- [ ] Slack / email share

## License

Private pilot — not for production health data patterns; meeting content is user responsibility.
