# -*- coding: utf-8 -*-
"""
Meeting Actions — pilot web app (FastAPI).

Drop a meeting recording → transcript → action items JSON.
Reuses the same job/PIN/feedback pattern as care-visit-ai.

Run locally:
  pip install -r requirements.txt
  $env:GEMINI_API_KEY="..."
  uvicorn webapp.server:app --host 0.0.0.0 --port 8001
"""

import hashlib
import json
import os
import secrets
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import providers  # noqa: E402
import stt  # noqa: E402

app = FastAPI(title="Meeting Actions")

DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)
EVENTS_LOG = DATA / "events.jsonl"
FEEDBACK_LOG = DATA / "feedback.jsonl"
RESULT_TTL_DAYS = int(os.environ.get("RESULT_TTL_DAYS", "7"))
STT_ENGINE = os.environ.get("STT_ENGINE", "gemini")

JOBS: dict[str, dict] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _log_event(event: str, job_id: str | None = None, **extra: object) -> None:
    row = {"ts": _utcnow().isoformat(), "event": event, **extra}
    if job_id:
        row["job_id"] = job_id
    with EVENTS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _pin_hash(job_id: str, pin: str) -> str:
    return hashlib.sha256(f"{job_id}:{pin}".encode()).hexdigest()


def _new_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(4))


def _meta_path(job_id: str) -> Path:
    return DATA / f"{job_id}.meta.json"


def _save_meta(job_id: str, pin: str) -> None:
    now = _utcnow()
    meta = {
        "pin_hash": _pin_hash(job_id, pin),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=RESULT_TTL_DAYS)).isoformat(),
    }
    _meta_path(job_id).write_text(json.dumps(meta), encoding="utf-8")


def _load_meta(job_id: str) -> dict | None:
    p = _meta_path(job_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _verify_access(job_id: str, pin: str | None) -> dict:
    meta = _load_meta(job_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Job not found")
    expires = datetime.fromisoformat(meta["expires_at"])
    if _utcnow() > expires:
        raise HTTPException(status_code=410, detail="This summary expired (7 days)")
    if not pin or _pin_hash(job_id, pin.strip()) != meta["pin_hash"]:
        raise HTTPException(status_code=403, detail="PIN required or incorrect")
    return meta


def _gemini():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    return providers.get_provider("gemini", key, model)


def _process(job_id: str, audio_path: str) -> None:
    try:
        JOBS[job_id] = {"status": "transcribing"}
        key = os.environ.get("GEMINI_API_KEY")
        transcript = stt.get_stt(STT_ENGINE, key).transcribe(audio_path)
        JOBS[job_id] = {"status": "extracting"}
        result = _gemini().extract(transcript)
        payload = {"result": result, "transcript_preview": transcript[:2000]}
        (DATA / f"{job_id}.json").write_text(json.dumps(payload), encoding="utf-8")
        JOBS[job_id] = {"status": "done"}
        _log_event(
            "job_done",
            job_id,
            action_count=len(result.get("action_items") or []),
            uncertain_count=sum(1 for a in result.get("action_items") or [] if a.get("uncertain")),
        )
    except Exception as e:  # noqa: BLE001
        JOBS[job_id] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
        _log_event("job_error", job_id, error=f"{type(e).__name__}: {e}")
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


@app.post("/api/process")
async def api_process(audio: UploadFile = File(...)):
    job_id = secrets.token_urlsafe(12)
    suffix = os.path.splitext(audio.filename or "")[1].lower() or ".m4a"
    ap = DATA / f"_aud_{job_id}{suffix}"
    ap.write_bytes(await audio.read())
    pin = _new_pin()
    _save_meta(job_id, pin)
    JOBS[job_id] = {"status": "queued"}
    _log_event("job_queued", job_id)
    threading.Thread(target=_process, args=(job_id, str(ap)), daemon=True).start()
    return {"job_id": job_id, "pin": pin}


@app.get("/api/status/{job_id}")
def api_status(job_id: str):
    if (DATA / f"{job_id}.json").exists():
        return {"status": "done"}
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return j


@app.get("/api/result/{job_id}")
def api_result(job_id: str, pin: str = Query(..., min_length=4, max_length=6)):
    _verify_access(job_id, pin)
    p = DATA / f"{job_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not ready yet")
    return JSONResponse(json.loads(p.read_text(encoding="utf-8")))


@app.get("/api/result/{job_id}/markdown")
def api_result_markdown(job_id: str, pin: str = Query(..., min_length=4, max_length=6)):
    _verify_access(job_id, pin)
    p = DATA / f"{job_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Not ready yet")
    data = json.loads(p.read_text(encoding="utf-8"))
    r = data["result"]
    lines = [f"# {r.get('one_line_summary', 'Meeting summary')}", ""]
    if r.get("decisions"):
        lines += ["## Decisions", ""] + [f"- {d}" for d in r["decisions"]] + [""]
    if r.get("action_items"):
        lines += ["## Action items", ""]
        for a in r["action_items"]:
            flag = " ⚠️ verify" if a.get("uncertain") else ""
            lines.append(
                f"- **{a.get('owner', '?')}** — {a.get('task')} (due: {a.get('due')}){flag}"
            )
        lines.append("")
    if r.get("open_questions"):
        lines += ["## Open questions", ""] + [f"- {q}" for q in r["open_questions"]] + [""]
    lines.append(f"_{r.get('disclaimer', '')}_")
    return PlainTextResponse("\n".join(lines))


@app.post("/api/feedback/{job_id}")
def api_feedback(
    job_id: str,
    pin: str = Query(..., min_length=4, max_length=6),
    body: dict = Body(...),
):
    _verify_access(job_id, pin)
    rating = (body.get("rating") or "").strip().lower()
    if rating not in ("up", "down", "wrong"):
        raise HTTPException(status_code=400, detail="rating must be up, down, or wrong")
    row = {
        "ts": _utcnow().isoformat(),
        "job_id": job_id,
        "rating": rating,
        "comment": (body.get("comment") or "").strip()[:500],
    }
    with FEEDBACK_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    _log_event("feedback", job_id, rating=rating)
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def upload_page():
    return UPLOAD_HTML


@app.get("/r/{job_id}", response_class=HTMLResponse)
def result_page(job_id: str):
    return RESULT_HTML.replace("__JOB_ID__", job_id)


_STYLE = """
<style>
  :root { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  * { box-sizing: border-box; }
  body { margin:0; background:#f4f6fb; color:#1a1d26; font-size:16px; line-height:1.55; }
  .wrap { max-width:560px; margin:0 auto; padding:24px 20px 48px; }
  .hero { text-align:center; padding:8px 0 16px; }
  .hero h1 { font-size:26px; margin:8px 0; letter-spacing:-.4px; }
  .hero p { color:#5c6478; margin:0; }
  .card { background:#fff; border-radius:16px; padding:20px; margin:14px 0;
          box-shadow:0 2px 12px rgba(20,30,60,.08); }
  .big-btn { display:block; width:100%; padding:16px; font-size:17px; font-weight:700;
             border:0; border-radius:12px; background:#3b5bdb; color:#fff; cursor:pointer; }
  .big-btn:disabled { opacity:.5; cursor:not-allowed; }
  .muted { color:#6b7280; font-size:13px; }
  .label { font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.06em;
           color:#6b7280; margin-bottom:8px; }
  .tldr { font-size:18px; font-weight:700; line-height:1.45; }
  ul { margin:8px 0; padding-left:20px; }
  .action { border-top:1px solid #eef0f5; padding:10px 0; }
  .action:first-child { border-top:0; }
  .pill { display:inline-block; background:#fff3cd; color:#856404; border-radius:999px;
          padding:2px 8px; font-size:11px; font-weight:700; }
  input[type=file], input[type=password], textarea { width:100%; padding:12px; font-size:15px;
    border:1px solid #dde1ea; border-radius:10px; margin:6px 0; }
  .fb-row { display:flex; gap:8px; margin-top:8px; }
  .fb-btn { flex:1; padding:10px; border:0; border-radius:10px; font-weight:600; cursor:pointer; }
  .pin-num { font-size:28px; font-weight:800; letter-spacing:6px; color:#3b5bdb; }
  .pin-box { background:#eef2ff; border-radius:12px; padding:16px; text-align:center; margin:12px 0; }
</style>
"""

UPLOAD_HTML = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meeting Actions</title>{_STYLE}</head>
<body><div class="wrap">
  <div class="hero">
    <h1>Meeting Actions</h1>
    <p>Drop your recording. Get action items in minutes.</p>
  </div>
  <div class="card">
    <div class="label">Meeting recording</div>
    <p class="muted">Zoom / Meet / Teams export — mp3, m4a, wav, mp4</p>
    <input id="audioFile" type="file">
  </div>
  <button id="go" class="big-btn">Extract actions</button>
  <p id="msg" class="muted" style="text-align:center;margin-top:12px;"></p>
  <p class="muted" style="text-align:center;">Audio is deleted after processing. Results expire in 7 days.</p>
</div>
<script>
const go=document.getElementById('go'), audioFile=document.getElementById('audioFile'), msg=document.getElementById('msg');
go.onclick=()=>{{
  if(!audioFile.files[0]){{ msg.textContent='Choose a file first.'; return; }}
  const fd=new FormData(); fd.append('audio', audioFile.files[0], audioFile.files[0].name);
  go.disabled=true; msg.textContent='Uploading...';
  fetch('/api/process',{{method:'POST',body:fd}}).then(r=>r.json()).then(({{job_id,pin}})=>{{
    sessionStorage.setItem('pin_'+job_id, pin);
    const labels={{queued:'Queued...',transcribing:'Transcribing...',extracting:'Extracting actions...'}};
    const poll=()=>fetch('/api/status/'+job_id).then(r=>r.json()).then(s=>{{
      if(s.status==='done'){{
        msg.innerHTML='<div class="pin-box">Share this PIN with your team<div class="pin-num">'+pin+'</div></div>';
        setTimeout(()=>location.href='/r/'+job_id, 3000); return;
      }}
      if(s.status==='error'){{ msg.textContent='Error: '+s.error; go.disabled=false; return; }}
      msg.textContent=labels[s.status]||s.status; setTimeout(poll, 2500);
    }});
    poll();
  }}).catch(e=>{{ msg.textContent='Upload failed: '+e; go.disabled=false; }});
}};
</script></body></html>"""

RESULT_HTML = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meeting summary</title>{_STYLE}</head>
<body><div class="wrap">
  <div class="hero"><h1 style="font-size:22px;">Meeting summary</h1></div>
  <button id="copyMd" class="big-btn" style="background:#212529;margin-bottom:8px;">Copy as Markdown</button>
  <div id="pinGate" class="card" style="display:none;">
    <div class="label">PIN</div>
    <input id="pinIn" type="password" inputmode="numeric" maxlength="6">
    <button id="pinGo" class="big-btn" style="margin-top:8px;">Open</button>
  </div>
  <div id="root"><p class="muted">Loading...</p></div>
  <div id="feedback" class="card" style="display:none;">
    <div class="label">Was this useful?</div>
    <div class="fb-row">
      <button class="fb-btn fb-up" data-r="up" style="background:#e8f5ec;">👍</button>
      <button class="fb-btn fb-down" data-r="down" style="background:#f0f0f0;">😐</button>
      <button class="fb-btn fb-wrong" data-r="wrong" style="background:#fde8e8;">👎</button>
    </div>
    <textarea id="fbComment" rows="2" placeholder="Optional comment"></textarea>
    <p id="fbMsg" class="muted"></p>
  </div>
  <p class="muted">AI-generated summary — verify with attendees before acting on it.</p>
  <p style="text-align:center;"><a href="/">+ New meeting</a></p>
</div>
<script>
const JOB="__JOB_ID__";
const esc=s=>(s||'').replace(/[&<>]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}}[c]));
function getPin(){{ return sessionStorage.getItem('pin_'+JOB) || new URLSearchParams(location.search).get('pin') || ''; }}

document.getElementById('copyMd').onclick=async()=>{{
  const pin=getPin(); if(!pin){{ alert('Enter PIN first'); return; }}
  const t=await fetch('/api/result/'+JOB+'/markdown?pin='+encodeURIComponent(pin)).then(r=>r.text());
  await navigator.clipboard.writeText(t); alert('Markdown copied!');
}};

function render(r){{
  let h='';
  if(r.one_line_summary) h+=`<div class="card"><div class="label">TL;DR</div><div class="tldr">${{esc(r.one_line_summary)}}</div></div>`;
  if((r.decisions||[]).length) h+=`<div class="card"><div class="label">Decisions</div><ul>${{r.decisions.map(d=>'<li>'+esc(d)+'</li>').join('')}}</ul></div>`;
  if((r.action_items||[]).length){{
    let inner=''; r.action_items.forEach(a=>{{
      inner+=`<div class="action"><b>${{esc(a.owner)}}</b> — ${{esc(a.task)}}<br><span class="muted">Due: ${{esc(a.due)}}</span>${{a.uncertain?' <span class="pill">verify</span>':''}}</div>`;
    }});
    h+=`<div class="card"><div class="label">Action items</div>${{inner}}</div>`;
  }}
  if((r.open_questions||[]).length) h+=`<div class="card"><div class="label">Open questions</div><ul>${{r.open_questions.map(q=>'<li>'+esc(q)+'</li>').join('')}}</ul></div>`;
  return h||'<p class="muted">No content</p>';
}}

async function showResult(pin){{
  document.getElementById('pinGate').style.display='none';
  const data=await fetch('/api/result/'+JOB+'?pin='+encodeURIComponent(pin)).then(r=>{{
    if(!r.ok) throw new Error(r.status); return r.json();
  }});
  document.getElementById('root').innerHTML=render(data.result);
  document.getElementById('feedback').style.display='block';
  document.querySelectorAll('.fb-btn').forEach(btn=>{{
    btn.onclick=async()=>{{
      await fetch('/api/feedback/'+JOB+'?pin='+encodeURIComponent(pin),{{
        method:'POST', headers:{{'Content-Type':'application/json'}},
        body:JSON.stringify({{rating:btn.dataset.r, comment:document.getElementById('fbComment').value}})
      }});
      document.getElementById('fbMsg').textContent='Thanks for the feedback!';
    }};
  }});
}}

(function init(){{
  const pin=getPin();
  if(pin){{ showResult(pin).catch(()=>{{ document.getElementById('root').innerHTML='<p>Could not load. Check PIN.</p>'; document.getElementById('pinGate').style.display='block'; }}); return; }}
  document.getElementById('root').innerHTML='';
  document.getElementById('pinGate').style.display='block';
  document.getElementById('pinGo').onclick=()=>{{
    const p=document.getElementById('pinIn').value.trim(); if(!p) return;
    sessionStorage.setItem('pin_'+JOB,p); showResult(p).catch(e=>alert(e));
  }};
}})();
</script></body></html>"""
