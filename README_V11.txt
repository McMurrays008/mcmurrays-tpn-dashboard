TPN Cloud Dashboard v11

Changes from v10:
- Keeps the successful low-memory browser/export workflow.
- Adds support for TPN's ConsignmentExport.xls download.
- Parser handles binary BIFF .xls, HTML-as-.xls, SpreadsheetML 2003, and .xlsx.
- Adds xlrd for binary .xls support.

For upgrade from v10, replace:
1. build_data_from_xlsx.py
2. requirements.txt
3. server.py (only needed for the v11 version marker)

Keep ENABLE_SCHEDULER=false for the first manual test.
After deployment, /health should show version: v11-xls-support-low-memory.
