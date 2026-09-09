TPN Dashboard v12 - dashboard data display fix

Replace these files in the GitHub repository root:
1. dashboard.html
2. server.py

What changed:
- Fixes the JavaScript 'status' element-name collision that could stop rendering after the snapshot header loaded.
- Fetches /data.js with cache disabled and a timestamp on every page load/reload.
- Adds visible data-loading/zero-row warnings.
- Adds /health data diagnostics: data.exists, source, generated_at, rows and size_bytes.
- Keeps acknowledgements in browser localStorage, including when fresh data is loaded.
- Acknowledged jobs can be unacknowledged.
- Adds Service, Status, Delivery Depot and Acknowledgement filters.
- Adds a Reload latest data button.

After deployment:
- Open /health and confirm version is v12-dashboard-data-fix.
- Check data.rows is greater than 0.
- Then open / or click Reload latest data.
