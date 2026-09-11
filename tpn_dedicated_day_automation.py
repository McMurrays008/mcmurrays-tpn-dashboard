from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "tpn_automation_config.json"


def load_config():
    if not CONFIG_PATH.exists():
        raise SystemExit(f"Missing config file: {CONFIG_PATH}")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["download_folder"] = Path(
        os.path.expandvars(os.path.expanduser(cfg.get("download_folder", str(ROOT))))
    ).resolve()
    cfg["browser_profile_folder"] = Path(
        os.path.expandvars(os.path.expanduser(cfg.get("browser_profile_folder", str(ROOT / "browser_profile"))))
    ).resolve()
    return cfg


def parse_iso_dates(values):
    out = set()
    for v in values or []:
        try:
            out.add(datetime.strptime(v, "%Y-%m-%d").date())
        except ValueError:
            print(f"Warning: ignored invalid bank holiday date {v!r}; expected YYYY-MM-DD")
    return out


def last_working_day(today: date, bank_holidays: set[date]) -> date:
    d = today - timedelta(days=1)
    while d.weekday() >= 5 or d in bank_holidays:
        d -= timedelta(days=1)
    return d


def working_date(cfg) -> date:
    mode = str(cfg.get("date_mode", "last_working_day")).lower()
    holidays = parse_iso_dates(cfg.get("bank_holidays", []))
    today = date.today()
    if mode == "today":
        return today
    if mode == "last_working_day":
        return last_working_day(today, holidays)
    if mode.startswith("fixed:"):
        return datetime.strptime(mode.split(":", 1)[1], "%Y-%m-%d").date()
    raise SystemExit("date_mode must be 'today', 'last_working_day', or 'fixed:YYYY-MM-DD'")

def working_day_range(end_date: date, count: int, bank_holidays: set[date]):
    days=[]
    d=end_date
    while len(days) < count:
        if d.weekday() < 5 and d not in bank_holidays:
            days.append(d)
        d -= timedelta(days=1)
    return min(days), max(days)


def fmt_ui(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def safe_click(locator, timeout=5000):
    try:
        locator.first.click(timeout=timeout)
        return True
    except Exception:
        return False


def click_exact_nav(page, name: str):
    candidates = [
        page.get_by_role("link", name=name, exact=True),
        page.get_by_role("button", name=name, exact=True),
        page.locator(f'a:has-text("{name}")').filter(has_text=re.compile(rf"^\s*{re.escape(name)}\s*$", re.I)),
        page.locator(f'button:has-text("{name}")').filter(has_text=re.compile(rf"^\s*{re.escape(name)}\s*$", re.I)),
    ]
    for loc in candidates:
        if safe_click(loc):
            return
    raise RuntimeError(f"Could not find top-level navigation item {name!r}")


def fill_by_label_or_placeholder(page, names, value):
    for name in names:
        for loc in (
            page.get_by_label(re.compile(name, re.I)),
            page.get_by_placeholder(re.compile(name, re.I)),
        ):
            try:
                if loc.count():
                    loc.first.fill(value, timeout=3000)
                    return True
            except Exception:
                pass

    # Fallback: text input near visible label text.
    for name in names:
        loc = page.locator(
            f'xpath=//*[self::label or self::span or self::div][contains(translate(normalize-space(.), '
            f'"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"), "{name.lower()}")]'
            f'/following::input[1]'
        )
        try:
            if loc.count():
                loc.first.fill(value, timeout=3000)
                return True
        except Exception:
            pass
    return False


def set_date_range(page, start_date: date, end_date: date):
    from_value = fmt_ui(start_date)
    to_value = fmt_ui(end_date)
    ok_from = fill_by_label_or_placeholder(
        page, [r"date\s*from", r"\bfrom\b", r"start\s*date"], from_value
    )
    ok_to = fill_by_label_or_placeholder(
        page, [r"date\s*to", r"\bto\b", r"end\s*date"], to_value
    )

    if ok_from and ok_to:
        return

    # Generic fallback: first two visible date/text inputs.
    inputs = page.locator(
        'input:visible[type="date"], input:visible.k-input, input:visible[type="text"]'
    )
    if inputs.count() >= 2:
        inputs.nth(0).fill(from_value)
        inputs.nth(1).fill(to_value)
        return
    raise RuntimeError("Could not identify the Date From / Date To controls")


def choose_all_export_type(page):
    # Native select first.
    selects = page.locator("select:visible")
    for i in range(selects.count()):
        sel = selects.nth(i)
        try:
            options = sel.locator("option").all_text_contents()
            if any(x.strip().lower() == "all" for x in options):
                sel.select_option(label="All")
                return
        except Exception:
            pass

    # Combobox / Kendo dropdown fallback.
    combos = page.get_by_role("combobox")
    for i in range(combos.count()):
        combo = combos.nth(i)
        try:
            combo.click(timeout=2000)
            option = page.get_by_role("option", name="All", exact=True)
            if option.count():
                option.first.click(timeout=2000)
                return
            all_text = page.get_by_text("All", exact=True)
            if all_text.count():
                all_text.last.click(timeout=2000)
                return
        except Exception:
            pass
    raise RuntimeError("Could not set Integration export type to All")


def download_via_button(page, button_name_regex, dest: Path, timeout=120000):
    with page.expect_download(timeout=timeout) as info:
        button = page.get_by_role("button", name=re.compile(button_name_regex, re.I))
        if button.count():
            button.first.click()
        else:
            link = page.get_by_role("link", name=re.compile(button_name_regex, re.I))
            if link.count():
                link.first.click()
            else:
                text = page.get_by_text(re.compile(button_name_regex, re.I))
                if text.count():
                    text.first.click()
                else:
                    raise RuntimeError(f"Could not find download button matching {button_name_regex!r}")
    dl = info.value
    dest.parent.mkdir(parents=True, exist_ok=True)
    dl.save_as(dest)
    return dest


def integration_export(page, cfg, start_date: date, end_date: date) -> Path:
    print("\n[1/2] Integration → Consignment Export")
    click_exact_nav(page, "Integration")
    page.wait_for_timeout(1000)

    set_date_range(page, start_date, end_date)
    choose_all_export_type(page)

    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    dest = cfg["download_folder"] / f"RAW_ConsignmentExport - {stamp}.csv"

    # Prefer exact Export button.
    with page.expect_download(timeout=120000) as info:
        export_btn = page.get_by_role("button", name="Export", exact=True)
        if export_btn.count():
            export_btn.first.click()
        else:
            export_link = page.get_by_role("link", name="Export", exact=True)
            if export_link.count():
                export_link.first.click()
            else:
                page.get_by_text("Export", exact=True).first.click()
    info.value.save_as(dest)
    print(f"Saved: {dest.name}")
    return dest


def find_grid_header(page, column_name):
    # Exact header cell where possible.
    exact = page.locator("th").filter(has_text=re.compile(rf"^\s*{re.escape(column_name)}\s*$", re.I))
    if exact.count():
        return exact.first
    fuzzy = page.locator("th").filter(has_text=re.compile(rf"\b{re.escape(column_name)}\b", re.I))
    if fuzzy.count():
        return fuzzy.first
    raise RuntimeError(f"Could not find grid column {column_name!r}")


def click_filter_icon(header):
    candidates = [
        header.locator(".k-grid-filter"),
        header.locator("a.k-grid-filter"),
        header.locator("button.k-grid-filter"),
        header.locator('[aria-label*="Filter" i]'),
        header.locator("a").filter(has=header.locator(".k-icon")),
    ]
    for loc in candidates:
        try:
            if loc.count():
                loc.first.click(timeout=3000)
                return
        except Exception:
            pass
    raise RuntimeError("Could not find filter icon in grid header")


def visible_filter_popup(page):
    selectors = [
        ".k-filter-menu:visible",
        ".k-popup:visible",
        ".k-animation-container:visible",
        '[role="dialog"]:visible',
    ]
    for selector in selectors:
        loc = page.locator(selector)
        if loc.count():
            return loc.last
    return page.locator("body")


def set_operator_in_popup(page, popup, operator_text):
    # Native select.
    sels = popup.locator("select:visible")
    if sels.count():
        sel = sels.first
        try:
            labels = sel.locator("option").all_text_contents()
            for label in labels:
                if operator_text.lower() in label.lower():
                    sel.select_option(label=label)
                    return
        except Exception:
            pass

    # Kendo/operator dropdown.
    combo_candidates = [
        popup.get_by_role("combobox"),
        popup.locator(".k-dropdownlist:visible"),
        popup.locator(".k-dropdown:visible"),
    ]
    for combos in combo_candidates:
        for i in range(combos.count()):
            combo = combos.nth(i)
            try:
                combo.click(timeout=2000)
                page.wait_for_timeout(250)
                option = page.get_by_text(re.compile(rf"^{re.escape(operator_text)}$", re.I))
                if option.count():
                    option.last.click(timeout=2000)
                    return
            except Exception:
                pass

    # Sometimes operator text itself is a button.
    op = popup.get_by_text(re.compile(operator_text, re.I))
    if op.count():
        op.first.click()
        return

    raise RuntimeError(f"Could not set filter operator to {operator_text!r}")


def set_filter_value(popup, value):
    # Prefer non-hidden text/number input.
    inputs = popup.locator('input:visible:not([type="checkbox"]):not([type="radio"])')
    for i in range(inputs.count()):
        loc = inputs.nth(i)
        try:
            if loc.is_editable():
                loc.fill(str(value), timeout=2000)
                return
        except Exception:
            pass
    raise RuntimeError("Could not find filter value input")


def click_filter_apply(popup):
    for label in ("Filter", "Apply"):
        btn = popup.get_by_role("button", name=re.compile(rf"^{label}$", re.I))
        if btn.count() and safe_click(btn):
            return
        txt = popup.get_by_text(label, exact=True)
        if txt.count() and safe_click(txt):
            return
    raise RuntimeError("Could not apply grid filter")


def apply_kendo_filter(page, column_name, operator_text, value):
    header = find_grid_header(page, column_name)
    click_filter_icon(header)
    page.wait_for_timeout(400)
    popup = visible_filter_popup(page)
    set_operator_in_popup(page, popup, operator_text)
    set_filter_value(popup, value)
    click_filter_apply(popup)
    page.wait_for_timeout(700)


def browse_export(page, cfg, start_date: date, end_date: date) -> Path:
    print("\n[2/2] Browse → Dedicated Day Check")
    click_exact_nav(page, "Browse")  # exact match avoids Quick Browse / Browse Deleted
    page.wait_for_timeout(1000)

    set_date_range(page, start_date, end_date)

    browse_btn = page.get_by_role("button", name="Browse", exact=True)
    if browse_btn.count():
        browse_btn.first.click()
    else:
        page.get_by_text("Browse", exact=True).last.click()
    page.wait_for_timeout(1500)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = cfg["download_folder"] / f"RAW_TPN Dedicated Day Check({stamp}).xlsx"

    with page.expect_download(timeout=120000) as info:
        export_btn = page.get_by_role("button", name=re.compile(r"Export\s*To\s*Excel", re.I))
        if export_btn.count():
            export_btn.first.click()
        else:
            export_text = page.get_by_text(re.compile(r"Export\s*To\s*Excel", re.I))
            if not export_text.count():
                raise RuntimeError("Could not find 'Export To Excel'")
            export_text.first.click()

    info.value.save_as(dest)
    print(f"Saved: {dest.name}")
    return dest


def wait_for_manual_login(page, cfg):
    print("\nA browser window has opened.")
    print("Log in to TPN normally. The script will continue when the TPN application menu is visible.")
    print("If you are already signed in, it should continue automatically.\n")

    timeout_ms = int(cfg.get("manual_login_timeout_minutes", 10)) * 60 * 1000
    try:
        page.get_by_text("Browse", exact=True).first.wait_for(state="visible", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        raise RuntimeError("Timed out waiting for manual TPN login")



def norm_header(v):
    return re.sub(r"\s+", " ", str(v or "").strip()).lower()

def find_header(headers, candidates):
    hmap = {norm_header(h): h for h in headers if h is not None}
    for c in candidates:
        if norm_header(c) in hmap:
            return hmap[norm_header(c)]
    # fuzzy fallback
    for h in headers:
        nh = norm_header(h)
        for c in candidates:
            if norm_header(c) in nh:
                return h
    return None

def locally_filter_integration(csv_path: Path, cfg) -> Path:
    print("\nLocal filtering: Integration export")
    raw = csv_path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            pass
    if text is None:
        raise RuntimeError("Could not decode Integration CSV")

    import csv
    reader = csv.DictReader(text.splitlines())
    rows = list(reader)
    headers = reader.fieldnames or []
    service_col = find_header(headers, ["Service"])
    if not service_col:
        raise RuntimeError("Could not find Service column in Integration export")

    prefix = str(cfg.get("service_prefix", "DD")).upper()
    kept = [r for r in rows if str(r.get(service_col, "") or "").strip().upper().startswith(prefix)]

    filtered = csv_path.with_name(csv_path.stem + "_DD_ONLY.csv")
    with filtered.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(kept)

    print(f"Integration rows: {len(rows)} -> {len(kept)} after Service starts with {prefix}")
    return filtered

def to_number(v):
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(str(v).strip())
    except Exception:
        return None

def locally_filter_browse(xlsx_path: Path, cfg) -> Path:
    print("\nLocal filtering: Browse export")
    from openpyxl import load_workbook, Workbook

    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    headers = list(next(it))
    rows = list(it)

    service_idx = None
    req_idx = None
    del_idx = None

    for i, h in enumerate(headers):
        nh = norm_header(h)
        if service_idx is None and nh == "service":
            service_idx = i
        if req_idx is None and nh == "req":
            req_idx = i
        if del_idx is None and nh == "del":
            del_idx = i

    if service_idx is None:
        # fuzzy fallback
        for i, h in enumerate(headers):
            if "service" in norm_header(h):
                service_idx = i
                break
    if req_idx is None:
        for i, h in enumerate(headers):
            if norm_header(h).startswith("req"):
                req_idx = i
                break
    if del_idx is None:
        for i, h in enumerate(headers):
            if norm_header(h) == "del" or norm_header(h).startswith("del "):
                del_idx = i
                break

    missing = []
    if service_idx is None: missing.append("Service")
    if req_idx is None: missing.append("Req")
    if del_idx is None: missing.append("Del")
    if missing:
        raise RuntimeError("Could not find Browse columns: " + ", ".join(missing))

    prefix = str(cfg.get("service_prefix", "DD")).upper()
    kept = []
    for r in rows:
        service = str(r[service_idx] or "").strip().upper()
        req = to_number(r[req_idx])
        dele = to_number(r[del_idx])

        # Local rules:
        # Service begins with DD
        # Req == 8
        # Del != 8
        if not service.startswith(prefix):
            continue
        if req != 8:
            continue
        if dele == 8:
            continue
        kept.append(r)

    filtered = xlsx_path.with_name(xlsx_path.stem + "_FILTERED.xlsx")
    out = Workbook(write_only=True)
    ows = out.create_sheet("Filtered")
    ows.append(headers)
    for r in kept:
        ows.append(list(r))
    out.save(filtered)

    print(f"Browse rows: {len(rows)} -> {len(kept)} after Service starts with {prefix}, Req=8, Del!=8")
    return filtered


def run_dashboard_update(cfg):
    if not cfg.get("run_dashboard_updater_after_download", True):
        return
    updater = ROOT / "update_dashboard.py"
    if not updater.exists():
        print("\nDashboard updater not found in this folder; downloads are complete.")
        print("Copy this automation into the permanent dashboard folder if you want JSON refresh to run automatically.")
        return

    print("\nRefreshing dedicated-day-data.json ...")
    result = subprocess.run([sys.executable, str(updater)], cwd=str(ROOT), text=True)
    if result.returncode != 0:
        raise RuntimeError("Downloads succeeded, but update_dashboard.py returned an error")


def main():
    parser = argparse.ArgumentParser(description="Download TPN Dedicated Day source exports and refresh the dashboard.")
    parser.add_argument("--date", help="Override date in YYYY-MM-DD format")
    args = parser.parse_args()

    cfg = load_config()
    cfg["download_folder"].mkdir(parents=True, exist_ok=True)
    cfg["browser_profile_folder"].mkdir(parents=True, exist_ok=True)

    end_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else working_date(cfg)
    holidays = parse_iso_dates(cfg.get("bank_holidays", []))
    start_date, end_date = working_day_range(end_date, 7, holidays)
    print(f"TPN Dedicated Day automation")
    print(f"Export date range: {fmt_ui(start_date)} to {fmt_ui(end_date)} (last 7 working days)")
    print("Local filters after export: Service starts DD; Browse also Req=8 and Del!=8")
    print(f"Download folder: {cfg['download_folder']}")

    base_url = cfg.get("base_url", "https://connect.tpnsecure.com/")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(cfg["browser_profile_folder"]),
            headless=False,
            accept_downloads=True,
            viewport={"width": 1500, "height": 950},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(base_url, wait_until="domcontentloaded", timeout=120000)

        wait_for_manual_login(page, cfg)
        integration_raw = integration_export(page, cfg, start_date, end_date)
        browse_raw = browse_export(page, cfg, start_date, end_date)

        print("\nBoth raw TPN exports completed successfully.")
        context.close()

    integration_filtered = locally_filter_integration(integration_raw, cfg)
    browse_filtered = locally_filter_browse(browse_raw, cfg)

    # Create dashboard-friendly copies so update_dashboard.py always finds the locally filtered versions.
    final_csv = cfg["download_folder"] / f"ConsignmentExport - {datetime.now():%Y-%m-%dT%H%M%S}.csv"
    final_xlsx = cfg["download_folder"] / f"TPN Dedicated Day Check({datetime.now():%Y%m%d-%H%M%S}).xlsx"
    shutil.copy2(integration_filtered, final_csv)
    shutil.copy2(browse_filtered, final_xlsx)

    print("\nPrepared dashboard source files:")
    print(f" - {final_csv.name}")
    print(f" - {final_xlsx.name}")

    run_dashboard_update(cfg)
    print("\nFinished.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nERROR: {exc}")
        print("\nThe browser has not been automated further so you can safely inspect the issue.")
        raise SystemExit(1)
