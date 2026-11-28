# Three-dashboard integration staging (NOT deployed)

This branch builds on `staging/dedicated-day-manual-consolidation` and does not change `main` or pull request #1.

## Routes and refresh behaviours
- `/`: Next Day, existing weekday hourly scheduled refresh at minute 00.
- `/dedicated-days`: Dedicated Day, OneDrive/manual refresh only. No periodic Dedicated Day polling.
- `/scan-status`: Scan Status, weekday hourly refresh at **07:15–17:15 Europe/London**. Accessible with existing HTTP Basic login (username `dashboard`, password configured via `REFRESH_TOKEN`). The scanner subapp's own startup handler is *not* invoked by mounting, so the parent app explicitly calls `start_scan_status_scheduler()`.
- All three collection jobs acquire `refresh_coordinator.browser_refresh_lock` before launching Chromium/downloading data. This lock is process-local: **run one Uvicorn worker and one Render instance only**. Multiple instances or workers would require a Redis/distributed lock.
- Scan Status data and collector live under `scan_status/`. Its HTML asset/data URLs and manual-refresh requests have been adapted for the mounted route.

## Before a paid test
1. Inspect the actual Docker build and import dependencies, especially `pandas`, `playwright`, `xlrd`, and Chromium.
2. Use a **separate, explicitly authorised** Render test service/environment with one worker; do not enable automatically deployed feature branches on the existing live service.
3. Populate `TPN_USERNAME`, `TPN_PASSWORD`, `REFRESH_TOKEN`, `ONEDRIVE_MORNING_URL`, `ONEDRIVE_STATUS_URL`, existing Upstash credentials, and other required application environment variables as secure secrets. Never commit them.
4. Keep `ENABLE_SCHEDULER=false` and `ENABLE_SCAN_STATUS_SCHEDULER=false` until manual smoke tests pass. Enable schedules only after confirming timezone and no unintended startup collection.
5. Test all routes, Next Day live refresh, Dedicated Day manual OneDrive import and status matching, Scan Status manual refresh, customer filters, existing acknowledgements, and graceful error responses.
6. Trigger overlapping requests and check they do not launch overlapping browsers; verify no data corruption and locks release on errors. Inspect actual refresh logs.
7. Run through at least one weekday full hourly refresh cycle including 07:00 Next Day and 07:15 Scan Status, while tracking peak memory at 30–60-second resolution and checking server OOM/restart events. Target should be **comfortably below 2 GiB** if Standard is chosen, and verify operational headroom.
8. Confirm Dedicated Day data and Scan Status data survive restarts, or configure a persistent store / explicit re-import before production. The current working files are ephemeral on Render.

## Current status
- Code prepared in GitHub; only static source inspection has been performed.
- **NOT** verified: a successful Docker build, end-to-end TPN/OneDrive refreshes, distributed coordination, data persistence, 2 GB or 512 MB memory limits, or Render deployment.
- Do not merge or deploy until these conditions are explicitly reviewed and approved.
