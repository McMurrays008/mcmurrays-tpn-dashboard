"""Process-wide browser refresh coordination for all mounted dashboards.

All collectors must acquire this lock before launching Chromium or downloading
Microsoft 365 files. A waiting job does not launch another browser.
"""
import threading

browser_refresh_lock = threading.Lock()
