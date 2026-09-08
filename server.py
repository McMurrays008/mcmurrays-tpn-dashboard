from __future__ import annotations
import asyncio, json, os, threading
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
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
    "running": False
}

def do_refresh():
    if not lock.acquire(blocking=False):
        return {"ok": False, "message": "Refresh already running"}
    status["running"] = True
    status["last_attempt"] = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        result = run_collection()
        status["last_success"] = datetime.now().astimezone().isoformat(timespec="seconds")
        status["last_error"] = None
        return result
    except Exception as e:
        status["last_error"] = f"{type(e).__name__}: {e}"
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
    return FileResponse(HERE/"data.js", media_type="application/javascript",
                        headers={"Cache-Control":"no-store, max-age=0"})

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
    # Weekdays only, every N minutes. If you want tighter working hours, change hour="6-19".
    sched.add_job(do_refresh, "cron", day_of_week="mon-fri", hour="6-19",
                  minute=f"*/{minutes}", id="tpn_refresh", max_instances=1, coalesce=True)
    sched.start()

if __name__ == "__main__":
    start_scheduler()
    port = int(os.getenv("PORT","8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
