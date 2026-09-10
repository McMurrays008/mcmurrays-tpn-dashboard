# TPN shared acknowledgements on Netlify Blobs

This adds a small shared acknowledgement API to the existing GitHub repository without moving the TPN collector away from Render.

## Files to add to the repository root

- `package.json`
- `netlify.toml`
- `netlify/functions/acknowledgements.mjs`
- `netlify-public/index.html`
- replace `dashboard.html` with the supplied shared-acknowledgement version

Render can ignore the Netlify files; the existing Python collector/server remain unchanged.

## Netlify environment variable

Optional but recommended:

`ACK_ALLOWED_ORIGINS=https://mcmurrays-tpn-dashboard.onrender.com`

If the Render dashboard later gets a custom domain, replace the value with that origin. Multiple origins can be comma-separated.

## API

- `GET /api/acknowledgements` - returns current acknowledgement state
- `GET /api/acknowledgements?docket=12345` - returns one docket
- `POST /api/acknowledgements` - body: `{ "docket":"12345", "action":"acknowledge", "user":"Sarah", "note":"" }`
- `POST /api/acknowledgements` - body: `{ "docket":"12345", "action":"unacknowledge", "user":"Sarah", "note":"" }`

A current state record is stored per docket and every change is also retained as an audit blob.

## Netlify endpoint used by dashboard

The supplied dashboard currently points to:

`https://meek-lollipop-ea9426.netlify.app/api/acknowledgements`

If the Netlify site's public URL is different, change the `ACK_API` constant near the start of the dashboard JavaScript.
