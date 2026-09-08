# TPN Dashboard — Cloud Automation

This package is designed to run away from the McMurrays PCs.

## What it does

On a schedule, the hosted container:

1. Opens TPN staging in Chromium.
2. Logs in using TPN credentials held as hosting-platform secrets.
3. Opens top-level **Browse**.
4. Sets Date From and Date To to the last working day.
5. Loads the Browse grid.
6. Applies `Req = 8`.
7. Applies `Del != 8`.
8. Clicks **Export To Excel**.
9. Parses the downloaded workbook.
10. Replaces `data.js`.
11. Serves the latest dashboard at the public/private host URL.

The current acknowledgement behaviour is still HTML/browser-local: users type their
name at the top and the name/time is stored on that browser.

## No local installation

Staff PCs only need a normal web browser. Python, Playwright and Chromium run inside
the cloud container.

## Recommended deployment route

Render or Railway are both suitable container hosts. This package includes:
- `Dockerfile`
- `render.yaml`
- `railway.json`

You will need an account with the chosen host and a GitHub repository or another
supported deployment upload method.

## Required secrets

Add these in the hosting provider's Environment/Secrets section:

- `TPN_USERNAME`
- `TPN_PASSWORD`
- `REFRESH_TOKEN`

Do not commit these values to GitHub and do not put them in the source files.

Optional:
- `BANK_HOLIDAYS=2026-12-25,2026-12-28`
- `REFRESH_MINUTES=15`

## Dashboard URL

The root `/` serves `dashboard.html`.
`/health` shows last attempt/success/error status.
`/data.js` is served with no-cache headers.

## Scheduler

Default:
- Monday-Friday
- 06:00 through 19:59 Europe/London
- every 15 minutes

Change the cron window in `server.py` if operating hours differ.

## Manual refresh

POST `/refresh` with HTTP header:

`X-Refresh-Token: <REFRESH_TOKEN>`

This is optional; the background scheduler handles normal updates.

## First cloud run

The remaining uncertainty is the exact DOM used by TPN's Req/Del filter menus.
The confirmed human workflow is implemented, with accessible/Kendo-style selectors.

If the first hosted refresh fails, the container saves:
- `tpn_failure.png`
- `tpn_failure_url.txt`
- `tpn_failure_html.html`

The `/failure-screenshot` endpoint can return the PNG when called with the same
`X-Refresh-Token` header.

That first diagnostic is normally enough to make the final selector adjustment.

## Security note

A publicly reachable dashboard URL would expose consignment information unless the
hosting layer is access-controlled. Before production use, put the site behind the
host's access control, Cloudflare Access, or another organisation-approved login/
private-network layer.

This package intentionally does not store TPN credentials in the browser or HTML.
