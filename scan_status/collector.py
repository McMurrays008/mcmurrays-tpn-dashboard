import os, subprocess, sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
DOWNLOADS=HERE/"downloads"; DOWNLOADS.mkdir(exist_ok=True)

def visible(page, selectors):
  for selector in selectors:
    loc=page.locator(selector)
    if loc.count() and loc.first.is_visible(): return loc.first
  return None

def click_named(page, text):
  candidates=[
    page.get_by_role("menuitem",name=text,exact=False),
    page.get_by_role("button",name=text,exact=True),
    page.get_by_role("link",name=text,exact=True),
    page.get_by_text(text,exact=True),
  ]
  for group in candidates:
    try:
      for i in range(group.count()):
        item=group.nth(i)
        if item.is_visible(): item.click(); return
    except Exception:
      pass
  raise RuntimeError(f"Could not find visible control: {text}")

def run_collection(stage_callback=None):
  def stage(s):
    print(f"[refresh] Stage: {s}",flush=True)
    if stage_callback: stage_callback(s)
  username,password=os.getenv("TPN_USERNAME"),os.getenv("TPN_PASSWORD")
  if not username or not password: raise RuntimeError("TPN_USERNAME/TPN_PASSWORD are not configured")
  today=datetime.now(ZoneInfo('Europe/London')).date(); date_text=today.strftime(os.getenv("DATE_FORMAT","%d/%m/%Y"))
  with sync_playwright() as p:
    stage("Starting browser")
    browser=p.chromium.launch(headless=os.getenv("HEADLESS","true").lower()=="true",args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--renderer-process-limit=1"])
    context=browser.new_context(accept_downloads=True,locale="en-GB",viewport={"width":1280,"height":800})
    page=context.new_page(); page.set_default_timeout(20000)
    page.route("**/*",lambda route: route.abort() if route.request.resource_type in {"image","media","font"} else route.continue_())
    try:
      stage("Opening TPN login"); page.goto(os.getenv("TPN_LOGIN_URL","https://pilot.tpnconnect.com/"),wait_until="domcontentloaded")
      u=visible(page,["input[placeholder*='Username' i]","input[name='Username']","input[name='username']"])
      pw=visible(page,["input[placeholder*='Password' i]","input[name='Password']","input[name='password']","input[type='password']"])
      if not u or not pw: raise RuntimeError("Could not identify TPN login fields")
      stage("Entering TPN credentials"); u.fill(username); pw.fill(password)
      login=page.get_by_role("button",name="Login",exact=True)
      login.first.click() if login.count() else pw.press("Enter")
      try: page.wait_for_load_state("networkidle",timeout=30000)
      except Exception: page.wait_for_load_state("domcontentloaded",timeout=30000)
      page.wait_for_timeout(1000)
      if page.get_by_text("Login",exact=True).count() and page.locator("input[placeholder*='Username' i]:visible").count():
        raise RuntimeError("TPN login page remained visible after submitting credentials")
      stage("Opening Browse")
      click_named(page,"Browse")
      page.wait_for_timeout(800)
      stage("Selecting today's date")
      for name in ("DateFrom","DateTo"):
        field=page.locator(f'input[name="{name}"]').first
        field.wait_for(state="visible")
        field.fill(date_text)
        # TPN can replace the date input after fill; use the page keyboard so
        # the blur does not depend on the original locator remaining attached.
        page.keyboard.press("Tab")
      stage("Selecting All consignments")
      for label in ("Consignments","Consignment Type","Browse Type"):
        try:
          box=page.get_by_label(label,exact=False)
          if box.count() and box.first.is_visible(): box.first.select_option(label="All consignments"); break
        except Exception: pass
      stage("Loading Browse results")
      # The TPN grid refreshes itself after this click. Do not wait for a full
      # page navigation, which can remain open indefinitely and starve Render.
      page.get_by_role("button",name="Browse",exact=True).last.click(no_wait_after=True,timeout=20000)
      # Locator.count() has no useful wait boundary when the TPN grid is busy.
      # Waiting for the first row gives the refresh a firm recovery timeout.
      page.locator(".k-grid-content tbody tr, table tbody tr").first.wait_for(state="attached",timeout=90000)
      # Export all results, then enforce Req=008 and Col=008 against the spreadsheet.
      stage("Exporting All consignments")
      download=None; export_error=None
      for attempt in range(2):
        try:
          export=page.get_by_text("Export To Excel",exact=False).first
          export.wait_for(state="visible",timeout=30000)
          with page.expect_download(timeout=90000) as info:
            export.click(force=True,no_wait_after=True)
          download=info.value
          break
        except Exception as exc:
          export_error=exc
          if attempt==0:
            stage("Export delayed — retrying")
            page.wait_for_timeout(4000)
      if download is None:
        raise RuntimeError(f"Export download failed after two attempts: {export_error}")
      target=DOWNLOADS/download.suggested_filename; download.save_as(target)
      # Release Chromium before pandas opens the export. Keeping both alive can
      # exceed the memory available on smaller Render instances and restart the service.
      context.close(); context=None
      browser.close(); browser=None
      stage("Filtering Req 008 and Col 008")
      result=subprocess.run(
        [sys.executable,str(HERE/"build_data.py"),str(target),str(HERE/"data.js")],
        timeout=60,text=True,capture_output=True
      )
      if result.stdout: print(result.stdout.strip(),flush=True)
      if result.returncode:
        detail=(result.stderr or result.stdout or "TPN export conversion failed").strip().splitlines()[-1]
        raise RuntimeError(f"TPN parser: {detail}")
      stage("Completed")
      return {"ok":True,"target_day":today.isoformat(),"date_text":date_text,"download":target.name}
    except Exception:
      stage("Failed")
      try: page.screenshot(path=str(HERE/"tpn_failure.png"))
      except Exception: pass
      raise
    finally:
      if context: context.close()
      if browser: browser.close()
