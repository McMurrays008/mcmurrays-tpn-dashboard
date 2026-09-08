from __future__ import annotations
import json, os, threading
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, RedirectResponse
import uvicorn

from collector import run_collection

HERE = Path(__file__).resolve().parent
load_dotenv(HERE/".env")

app = FastAPI(title="TPN Dashboard Automation")
lock = threading.Lock()
status = {
    "last_attempt": None,
    "last_success": None,
    "last_error": None,
    "running": False,
    "current_stage": "Idle"
}

def do_refresh():
    if not lock.acquire(blocking=False):
        return {"ok": False, "message": "Refresh already running"}
    status["running"] = True
    status["current_stage"] = "Starting"
    status["last_attempt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        def update_stage(name):
            status["current_stage"] = name
        result = run_collection(stage_callback=update_stage)
        status["last_success"] = datetime.now().astimezone().isoformat(timespec="seconds")
        status["last_error"] = None
        status["current_stage"] = "Completed"
        return result
    except Exception as e:
        status["last_error"] = f"{type(e).__name__}: {e}"
        if status.get("current_stage") != "Failed":
            status["current_stage"] = "Failed"
        raise
    finally:
        status["running"] = False
        lock.release()

@app.get("/")
def home():
    return FileResponse(HERE/"dashboard.html", media_type="text/html")

@app.get("/dashboard.html")
def dashboard():
    return FileResponse(HERE/"dashboard.html", media_type="text/html")

@app.get("/data.js")
def data_js():
    return FileResponse(
        HERE/"data.js",
        media_type="application/javascript",
        headers={"Cache-Control":"no-store, max-age=0"}
    )

@app.get("/health")
def health():
    return JSONResponse({"service":"tpn-dashboard","status":status})

@app.post("/refresh")
def refresh(x_refresh_token: str | None = Header(default=None)):
    expected = os.getenv("REFRESH_TOKEN")
    if not expected or x_refresh_token != expected:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        return do_refresh()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def admin_page(message: str = "", ok: bool | None = None, show_screenshot: bool = False) -> str:
    if ok is True:
        banner = f'<div class="banner success">{message}</div>'
    elif ok is False:
        banner = f'<div class="banner error">{message}</div>'
    else:
        banner = ""

    screenshot_block = ""
    if show_screenshot:
        p = HERE/"tpn_failure.png"
        if p.exists():
            # The image is served through a short-lived page-local route that is only
            # revealed after the token has been validated by POST.
            import base64
            encoded = base64.b64encode(p.read_bytes()).decode("ascii")
            screenshot_block = f"""
            <h3>Last TPN Failure Screenshot</h3>
            <p class="small">This is exactly what the Playwright browser captured when the TPN run failed.</p>
            <img src="data:image/png;base64,{encoded}" alt="TPN failure screenshot"
                 style="max-width:100%;height:auto;border:1px solid #cbd5e1;border-radius:8px">
            """
        else:
            screenshot_block = """
            <h3>Last TPN Failure Screenshot</h3>
            <div class="banner error">No TPN failure screenshot is currently available.</div>
            """

    st = json.dumps(status, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TPN Manual Refresh</title>
<style>
body{{font-family:Arial,sans-serif;background:#f4f7fb;margin:0;padding:32px;color:#1f2937}}
.card{{max-width:900px;margin:0 auto;background:white;padding:28px;border-radius:14px;
box-shadow:0 4px 18px rgba(0,0,0,.08)}}
h1{{margin-top:0}}
label{{display:block;font-weight:700;margin-bottom:8px}}
input{{width:100%;box-sizing:border-box;padding:12px;border:1px solid #cbd5e1;border-radius:8px}}
button{{margin-top:14px;padding:12px 18px;border:0;border-radius:8px;background:#1f4e78;color:white;
font-weight:700;cursor:pointer}}
.banner{{padding:12px 14px;border-radius:8px;margin-bottom:16px}}
.success{{background:#e8f5e9}}
.error{{background:#fdecec}}
pre{{white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:8px;font-size:13px}}
.small{{font-size:13px;color:#64748b}}
hr{{border:0;border-top:1px solid #e2e8f0;margin:28px 0}}
</style>
</head>
<body>
<div class="card">
<h1>TPN Manual Refresh</h1>
<p>Enter the Render <strong>REFRESH_TOKEN</strong> and click the button below.</p>
{banner}

<form method="post" action="/admin-refresh">
<label for="token">Refresh token</label>
<input id="token" name="token" type="password" autocomplete="off" required>
<button type="submit">Run TPN Refresh Now</button>
</form>

<hr>

<form method="post" action="/admin-show-failure">
<label for="token2">Refresh token</label>
<input id="token2" name="token" type="password" autocomplete="off" required>
<button type="submit">Show Last TPN Failure Screenshot</button>
</form>

<p class="small">The token is submitted only to this service for validation and is not stored by this page.</p>

<h3>Current service status</h3>
<pre>{st}</pre>

{screenshot_block}

<p><a href="/health">Open health check</a> · <a href="/">Open dashboard</a></p>
</div>
</body>
</html>"""

@app.get("/admin-refresh", response_class=HTMLResponse)
def admin_refresh_page():
    return HTMLResponse(admin_page())

@app.post("/admin-refresh", response_class=HTMLResponse)
def admin_refresh_run(token: str = Form(...)):
    expected = os.getenv("REFRESH_TOKEN")
    if not expected or token != expected:
        return HTMLResponse(admin_page("Invalid refresh token.", False), status_code=401)
    try:
        result = do_refresh()
        if result.get("ok") is False:
            msg = result.get("message", "Refresh did not start.")
            return HTMLResponse(admin_page(msg, False), status_code=409)
        msg = "Refresh completed successfully. " + json.dumps(result, ensure_ascii=False)
        return HTMLResponse(admin_page(msg, True))
    except Exception as e:
        return HTMLResponse(admin_page(f"Refresh failed: {type(e).__name__}: {e}", False), status_code=500)

@app.post("/admin-show-failure", response_class=HTMLResponse)
def admin_show_failure(token: str = Form(...)):
    expected = os.getenv("REFRESH_TOKEN")
    if not expected or token != expected:
        return HTMLResponse(admin_page("Invalid refresh token.", False), status_code=401)
    p = HERE/"tpn_failure.png"
    if not p.exists():
        return HTMLResponse(admin_page("No TPN failure screenshot is currently available.", False), status_code=404)
    return HTMLResponse(admin_page("Showing the last captured TPN failure screenshot below.", True, True))

@app.get("/failure-screenshot")
def failure_screenshot(x_refresh_token: str | None = Header(default=None)):
    expected = os.getenv("REFRESH_TOKEN")
    if not expected or x_refresh_token != expected:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    p = HERE/"tpn_failure.png"
    if not p.exists():
        raise HTTPException(status_code=404, detail="No failure screenshot available")
    return FileResponse(p, media_type="image/png")

def start_scheduler():
    if os.getenv("ENABLE_SCHEDULER","true").lower() != "true":
        return
    minutes = max(5, int(os.getenv("REFRESH_MINUTES","15")))
    tz = os.getenv("TIMEZONE","Europe/London")
    sched = BackgroundScheduler(timezone=tz)
    sched.add_job(
        do_refresh,
        "cron",
        day_of_week="mon-fri",
        hour="6-19",
        minute=f"*/{minutes}",
        id="tpn_refresh",
        max_instances=1,
        coalesce=True
    )
    sched.start()

if __name__ == "__main__":
    start_scheduler()
    port = int(os.getenv("PORT","8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
