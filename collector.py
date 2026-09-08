from __future__ import annotations
import json, os, subprocess, sys
from datetime import date, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
DOWNLOAD_DIR = HERE / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

def last_working_day(today: date) -> date:
    holidays = {date.fromisoformat(x.strip()) for x in os.getenv("BANK_HOLIDAYS","").split(",") if x.strip()}
    d = today - timedelta(days=1)
    while d.weekday() >= 5 or d in holidays:
        d -= timedelta(days=1)
    return d

def first_visible(page, selectors):
    for selector in selectors:
        try:
            loc = page.locator(selector)
            if loc.count() and loc.first.is_visible():
                return loc.first
        except Exception:
            pass
    return None

def click_named(page, text, exact=True):
    candidates = [
        page.get_by_role("button", name=text, exact=exact),
        page.get_by_role("link", name=text, exact=exact),
        page.get_by_text(text, exact=exact),
    ]
    for loc in candidates:
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.click()
                return
        except Exception:
            pass
    raise RuntimeError(f"Could not find control: {text}")

def fill_date(page, label, selectors, value):
    try:
        loc = page.get_by_label(label, exact=False)
        if loc.count() and loc.first.is_visible():
            loc.first.fill(value)
            return
    except Exception:
        pass
    loc = first_visible(page, selectors)
    if not loc:
        raise RuntimeError(f"Could not locate {label}")
    loc.fill(value)

def set_grid_filter(page, column_name: str, operator_text: str, value: str):
    # Locate column header
    header = None
    for loc in [page.get_by_role("columnheader", name=column_name, exact=True),
                page.get_by_text(column_name, exact=True)]:
        try:
            if loc.count() and loc.first.is_visible():
                header = loc.first
                break
        except Exception:
            pass
    if not header:
        raise RuntimeError(f"Could not locate grid column: {column_name}")

    # Open its filter/menu
    opened = False
    for sel in [
        "button[title*='Filter' i]", "a[title*='Filter' i]",
        ".k-grid-filter", ".k-header-column-menu",
        "[aria-label*='filter' i]", "[aria-label*='menu' i]"
    ]:
        try:
            btn = header.locator(sel)
            if btn.count() and btn.first.is_visible():
                btn.first.click()
                opened = True
                break
        except Exception:
            pass
    if not opened:
        try:
            header.click()
            opened = True
        except Exception:
            pass
    page.wait_for_timeout(500)

    # Pick operator
    operator_selected = False
    try:
        loc = page.get_by_text(operator_text, exact=True)
        if loc.count() and loc.first.is_visible():
            loc.first.click()
            operator_selected = True
    except Exception:
        pass
    if not operator_selected:
        try:
            selects = page.locator("select:visible")
            if selects.count():
                selects.last.select_option(label=operator_text)
                operator_selected = True
        except Exception:
            pass

    # Fill value
    filled = False
    for sel in [".k-filter-menu input:visible", ".k-columnmenu-item-content input:visible",
                "[role='dialog'] input:visible", "input[type='text']:visible"]:
        try:
            inputs = page.locator(sel)
            if inputs.count():
                inputs.last.fill(value)
                filled = True
                break
        except Exception:
            pass
    if not filled:
        raise RuntimeError(f"Could not enter filter value for {column_name}")

    # Apply
    for label in ("Filter", "Apply"):
        try:
            btn = page.get_by_role("button", name=label, exact=False)
            if btn.count() and btn.last.is_visible():
                btn.last.click()
                page.wait_for_timeout(800)
                return
        except Exception:
            pass
    raise RuntimeError(f"Could not apply filter for {column_name}")

def run_collection() -> dict:
    username = os.getenv("TPN_USERNAME")
    password = os.getenv("TPN_PASSWORD")
    if not username or not password:
        raise RuntimeError("TPN_USERNAME/TPN_PASSWORD are not configured.")

    login_url = os.getenv("TPN_LOGIN_URL", "https://staging.tpnconnect.com/")
    date_format = os.getenv("DATE_FORMAT", "%d/%m/%Y")
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    target_day = last_working_day(date.today())
    date_text = target_day.strftime(date_format)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(accept_downloads=True)
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

            # TPN Connect staging login: the current page exposes Username and Password
            # by placeholder. Use those first, with generic fallbacks.
            u = first_visible(page, [
                "input[placeholder='Username']",
                "input[placeholder*='Username' i]",
                "input[name='Username']",
                "input[name='username']",
                "#Username", "#username",
                "input[type='text']"
            ])
            pw = first_visible(page, [
                "input[placeholder='Password']",
                "input[placeholder*='Password' i]",
                "input[name='Password']",
                "input[name='password']",
                "#Password", "#password",
                "input[type='password']"
            ])
            if not (u and pw):
                raise RuntimeError("Could not identify TPN username/password fields.")

            u.fill(username)
            pw.fill(password)

            # The yellow Login control is reliably identified by its visible text.
            login = None
            for candidate in [
                page.get_by_role("button", name="Login", exact=True),
                page.get_by_role("link", name="Login", exact=True),
                page.get_by_text("Login", exact=True),
            ]:
                try:
                    if candidate.count() and candidate.first.is_visible():
                        login = candidate.first
                        break
                except Exception:
                    pass

            if login:
                login.click()
            else:
                # Fallback for legacy ASP.NET/image/button implementations:
                # submit from the password field/form.
                try:
                    pw.press("Enter")
                except Exception:
                    raise RuntimeError("Found TPN credentials fields but could not activate Login.")
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)

            # If login failed, stop before attempting Browse and preserve diagnostics.
            if page.get_by_text("Login", exact=True).count() and page.locator("input[placeholder*='Username' i]:visible").count():
                raise RuntimeError("TPN login page remained visible after submitting credentials.")

            # Confirmed workflow
            click_named(page, "Browse", exact=True)
            page.wait_for_timeout(800)

            fill_date(page, "Date From",
                      ["input[name*='DateFrom' i]","input[id*='DateFrom' i]","input[placeholder*='Date From' i]"],
                      date_text)
            fill_date(page, "Date To",
                      ["input[name*='DateTo' i]","input[id*='DateTo' i]","input[placeholder*='Date To' i]"],
                      date_text)

            # Browse button inside tab
            b = page.get_by_role("button", name="Browse", exact=True)
            if b.count():
                b.last.click()
            else:
                click_named(page, "Browse", exact=True)
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(800)

            set_grid_filter(page, "Req", "Is equal to", "8")
            set_grid_filter(page, "Del", "Is not equal to", "8")

            rows = page.locator(".k-grid-content tbody tr, table tbody tr")
            if rows.count() == 0:
                raise RuntimeError("Filtered grid has no results; export stopped.")

            export = None
            for loc in [
                page.get_by_role("button", name="Export To Excel", exact=False),
                page.get_by_role("link", name="Export To Excel", exact=False),
                page.get_by_text("Export To Excel", exact=False)
            ]:
                try:
                    if loc.count() and loc.first.is_visible():
                        export = loc.first
                        break
                except Exception:
                    pass
            if not export:
                raise RuntimeError("Could not find Export To Excel.")

            with page.expect_download(timeout=60000) as dli:
                export.click()
            download = dli.value
            filename = download.suggested_filename
            if not filename.lower().endswith((".xlsx",".xls")):
                filename = f"TPN_Consignment_Export_{target_day.isoformat()}.xlsx"
            target = DOWNLOAD_DIR / filename
            download.save_as(target)

            subprocess.check_call([sys.executable, str(HERE/"build_data_from_xlsx.py"), str(target), str(HERE/"data.js")])

            return {
                "ok": True,
                "target_day": target_day.isoformat(),
                "date_text": date_text,
                "download": target.name
            }
        except Exception:
            page.screenshot(path=str(HERE/"tpn_failure.png"), full_page=True)
            (HERE/"tpn_failure_url.txt").write_text(page.url, encoding="utf-8")
            try:
                (HERE/"tpn_failure_html.html").write_text(page.content(), encoding="utf-8")
            except Exception:
                pass
            raise
        finally:
            browser.close()
