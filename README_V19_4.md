TPN Dashboard v19.4 — Export first, filter locally

Replace these THREE repository-root files:
1. server.py
2. collector.py
3. build_data_from_xlsx.py

Do not replace dashboard.html or any Netlify acknowledgement files.

Changes:
- Removes unreliable browser-side TPN grid filtering for Req = 8 and Del != 8.
- Exports the complete Browse result for the target day.
- Applies Req/Request = depot 8 and Del/Deliver != depot 8 locally in build_data_from_xlsx.py.
- Depot comparison normalizes 008, 8 and 8.0 as depot 8.
- Keeps the v19.3 safe-diagnostic handling so screenshot failures cannot mask the real error.
- Uses the robust Export To Excel click/download logic with a 120-second download allowance.
- Server version becomes v19.4-export-then-filter.
- Existing dashboard, contextual filters, delivered block and shared acknowledgements remain unchanged.

After Render deploys:
- /health should show "version":"v19.4-export-then-filter"
- click Reload latest data once
- allow roughly 1–2 minutes
- /health should show current_stage "Completed", last_error null, and today's generated_at with fresh:true.
