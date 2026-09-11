TPN Dashboard v13

Replace TWO files in the GitHub repository root:
- server.py
- dashboard.html

Changes:
1. Fixed automatic refresh times:
   Monday-Friday at 08:00, 09:00, 10:00 ... through 18:00 Europe/London.
   Optional Render variable REFRESH_HOURS can override the default APScheduler hour expression.
2. Dashboard filters:
   - Status
   - Customer / Sender
   - Service
   - Delivery Depot
   - Consignee
   - Acknowledgement state
   - Free-text search
3. Existing acknowledge/unacknowledge and reload-latest-data features remain.

Keep:
ENABLE_SCHEDULER=true
TIMEZONE=Europe/London

REFRESH_MINUTES is no longer used by v13.
After deploy, /health should show:
"version":"v13-fixed-hourly-filters"
