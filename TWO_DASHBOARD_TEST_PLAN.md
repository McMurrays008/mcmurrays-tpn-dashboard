# Next Day + Scan Status — staggered-refresh staging

This branch is for **two dashboards on one web service**:
- **Next Day:** `/`, automated weekdays **07:00–17:00 on the hour**, Europe/London.
- **Scan Status:** `/scan-status`, automated weekdays **07:30–17:30 on the half hour**, Europe/London.
- **Dedicated Day:** excluded from the mounted application. Keep using its **separate manual-upload dashboard**.

The existing process-wide `browser_refresh_lock` is used by both collectors. It prevents concurrent Chromium launches inside the same Python process, including manually requested refreshes. Keep **one Uvicorn worker and one Render instance**; with multiple workers or instances, use a distributed lock instead.

## Before deploying

1. Build/test the Docker image and route handling. Smoke-test `/` and the authenticated `/scan-status` dashboard, its `data.js`, images, ready endpoint, and manual refresh.
2. Verify both scanners authenticate to TPN and produce fresh, correctly filtered data. Test 07:00 + 07:30 scheduling, UK daylight saving/timezone, and at least one full weekday schedule.
3. Check shared refresh lock under an overlapping manual request (including failure/retry), and ensure Chromium closes and lock is released.
4. Measure **peak** total memory, not only idle samples. Watch Render logs and OOM/restart events. Do not assume staggered schedules guarantee low RAM if a run overlaps the next slot; locking queues instead.
5. Confirm acknowledgement behaviour and data persistence/recovery after restarts. Scan Status's generated `data.js` and Next Day's snapshot are in the service's ephemeral filesystem.
6. Check existing secrets/environment variables (TPN credentials, REFRESH_TOKEN, acknowledgement credentials) through Render's secure environment settings. Never commit secrets.
7. Do **not** change the live Render service/branch, upgrade or incur charges without explicit approval.

This is a **code-prepared staging branch, not a deployed or verified combined service**. The parent application's startup registers Scan Status's scheduler explicitly because a mounted FastAPI subapp does not automatically run its own startup hooks. Scan Status does not have a second independently started scheduler.

Original three-dashboard preparation: `staging/three-dashboard-preparation`.
