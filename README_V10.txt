TPN Dashboard Cloud Automation v10

Purpose of this test version
- Avoids the Req/Del Telerik grid filter menus entirely. Those were the stage at which the free Render instance repeatedly restarted.
- Exports the Browse results for the last working day, then filters the workbook locally using Req = 8 AND Del != 8 before creating data.js.
- Removes the after-login screenshot and uses a smaller browser viewport / additional low-memory Chromium options.
- /health now includes version and live process/container memory figures when Render exposes them.
- Scheduler defaults to hourly. Keep ENABLE_SCHEDULER=false until one manual run completes successfully.

Deploy test
1. Replace collector.py, server.py and build_data_from_xlsx.py in the GitHub repo root.
2. Keep ENABLE_SCHEDULER=false.
3. Let Render deploy.
4. Open /health and confirm version is v10-no-grid-filter-low-memory.
5. Run one manual refresh from /admin-refresh.
6. Watch /health every 15-30 seconds.
7. A successful run should move through Opening Browse -> dates -> Loading Browse results -> Preparing unfiltered export -> Exporting Excel -> Building dashboard data -> Completed.

After manual success
- Set ENABLE_SCHEDULER=true
- Set REFRESH_MINUTES=60
This runs at the top of each hour Monday-Friday during the configured 06-19 window.
