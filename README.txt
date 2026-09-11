TPN DEDICATED DAY — AUTOMATION V4
=================================

This package supports TWO different refresh jobs.

1) MORNING FULL REFRESH — 08:00
--------------------------------
Runs:
  tpn_dedicated_day_automation.py

It:
- opens TPN
- Integration: exports All for the last 7 working days
- Browse: exports Excel for the last 7 working days
- filters locally:
    Service starts with DD
    Browse also Req = 8 and Del != 8
- prepares the dashboard source data
- refreshes dedicated-day-data.json when update_dashboard.py is in this folder

2) BROWSE STATUS REFRESH — EVERY 2 HOURS
-----------------------------------------
Runs:
  refresh_browse_statuses.py

Scheduled at:
  10:00
  12:00
  14:00
  16:00
  18:00

It does NOT rebuild the day's delivery population.

Instead it:
- opens only top-level Browse
- exports the last 7 working days with no website grid filters
- filters locally:
    Service starts with DD
    Req = 8
    Del != 8
- reads Docket + STATUS from the filtered Browse file
- matches those Dockets to the existing dedicated-day-data.json
- changes only the Status values
- rewrites the JSON
- leaves the dashboard HTML unchanged

This means the dashboard population established by the morning run stays
stable, while statuses can move during the day.

FIRST-TIME SETUP
----------------
1. Put these files in the SAME folder as the permanent dashboard package.
   That folder should contain:
     dashboard.html
     dedicated-day-data.json
     update_dashboard.py

2. Run:
     install_automation.bat

3. Check:
     tpn_automation_config.json

4. Test manually:
     run_morning_full_refresh.bat
     run_status_refresh_now.bat

5. When both tests work, run:
     install_2_hour_schedule.bat

SCHEDULE
--------
08:00  full refresh
10:00  Browse status refresh
12:00  Browse status refresh
14:00  Browse status refresh
16:00  Browse status refresh
18:00  Browse status refresh

WHY FIXED TIMES INSTEAD OF AN INFINITE 2-HOUR LOOP?
----------------------------------------------------
Windows Task Scheduler is more reliable for this. Each run is independent.
If one run fails because TPN asks for login, the next scheduled run still
gets its own attempt.

LOGIN / SESSION
---------------
The script uses a visible Chromium browser with a persistent local profile.

If TPN still considers the session valid, a scheduled refresh may proceed
without intervention.

If TPN requires authentication again, the browser will stop at login and
wait for you. No TPN username/password is stored by these scripts.

IMPORTANT
---------
Run the scheduled tasks while you are logged into Windows. The provided
installer creates interactive tasks because the TPN browser may need your
attention.

To remove the scheduled tasks:
  remove_schedule.bat
