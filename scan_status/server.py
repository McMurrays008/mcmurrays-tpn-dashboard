import json, os, threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, status as http_status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from .collector import run_collection
from refresh_coordinator import browser_refresh_lock

HERE=Path(__file__).resolve().parent; TZ=ZoneInfo("Europe/London")
app=FastAPI(title="McMurrays TPN Scan Status")
lock=threading.Lock(); state={"running":False,"stage":"Idle","last_attempt":None,"last_success":None,"last_error":None}
basic=HTTPBasic()

def authorised(credentials:HTTPBasicCredentials=Depends(basic)):
  expected=os.getenv("REFRESH_TOKEN","")
  valid_user=secrets.compare_digest(credentials.username,"dashboard")
  valid_password=bool(expected) and secrets.compare_digest(credentials.password,expected)
  if not (valid_user and valid_password):
    raise HTTPException(http_status.HTTP_401_UNAUTHORIZED,"Authentication required",headers={"WWW-Authenticate":"Basic"})
  return True

def refresh_job():
  if not lock.acquire(blocking=False): return
  state.update(running=True,stage="Starting",last_attempt=datetime.now(TZ).isoformat(),last_error=None)
  try:
    with browser_refresh_lock:
      run_collection(lambda s: state.update(stage=s))
    state.update(last_success=datetime.now(TZ).isoformat(),stage="Completed")
  except Exception as e:
    state.update(last_error=str(e),stage="Failed")
    print(f"[refresh] ERROR: {e}",flush=True)
  finally:
    state["running"]=False; lock.release()

@app.get("/")
def home(_=Depends(authorised)): return FileResponse(HERE/"dashboard.html",media_type="text/html")
@app.get("/dashboard.html")
def dashboard(_=Depends(authorised)): return FileResponse(HERE/"dashboard.html",media_type="text/html")
@app.get("/data.js")
def data(_=Depends(authorised)): return FileResponse(HERE/"data.js",media_type="application/javascript",headers={"Cache-Control":"no-store"})
@app.get("/assets/mcmurrays-logo.png")
def mcmurrays_logo(_=Depends(authorised)): return FileResponse(HERE/"assets"/"mcmurrays-logo.png",media_type="image/png",headers={"Cache-Control":"public, max-age=86400"})
@app.get("/assets/tpn-logo.png")
def tpn_logo(_=Depends(authorised)): return FileResponse(HERE/"assets"/"tpn-logo.png",media_type="image/png",headers={"Cache-Control":"public, max-age=86400"})
@app.get("/health")
def health(_=Depends(authorised)): return JSONResponse({"service":"tpn-scan-status","status":state})
@app.get("/ready")
def ready():
  # Non-sensitive deployment probe; detailed errors remain behind dashboard auth.
  error_code=None
  if state["last_error"]:
    message=state["last_error"].lower()
    if "no consignments matching" in message: error_code="NO_MATCHING_008"
    elif "could not find the tpn consignment table" in message: error_code="UNRECOGNISED_EXPORT"
    elif "no results" in message: error_code="NO_RESULTS"
    elif "date" in message: error_code="DATE_FIELD"
    elif "export" in message or "download" in message: error_code="EXPORT"
    elif "login" in message: error_code="LOGIN"
    elif "browse" in message or "control" in message: error_code="BROWSE"
    else: error_code="COLLECTOR"
  return JSONResponse({
    "service":"tpn-scan-status",
    "ready":bool(state["last_success"]),
    "running":state["running"],
    "stage":state["stage"],
    "last_success":state["last_success"],
    "error_code":error_code,
  })
@app.post("/refresh",status_code=202)
def refresh(x_refresh_token:str|None=Header(default=None)):
  if not os.getenv("REFRESH_TOKEN") or x_refresh_token!=os.getenv("REFRESH_TOKEN"): raise HTTPException(401,"Invalid refresh token")
  if state["running"] or lock.locked(): return {"accepted":False,"message":"Refresh already running","status":state}
  threading.Thread(target=refresh_job,daemon=True).start(); return {"accepted":True,"status":state}

@app.post("/dashboard-refresh",status_code=202)
def dashboard_refresh(_=Depends(authorised)):
  if state["running"]: return {"accepted":False,"message":"Refresh already running","status":state}
  threading.Thread(target=refresh_job,daemon=True).start()
  return {"accepted":True,"message":"Refresh started","status":state}

@app.on_event("startup")
def start_scheduler():
  global scheduler
  if scheduler is not None: return
  if os.getenv("ENABLE_SCAN_STATUS_SCHEDULER","true").lower() != "true": return
  scheduler=BackgroundScheduler(timezone=TZ)
  scheduler.add_job(refresh_job,"cron",day_of_week="mon-fri",minute=15,hour="7-17",id="scan_status_refresh",max_instances=1,coalesce=True)
  scheduler.start()

scheduler = None

