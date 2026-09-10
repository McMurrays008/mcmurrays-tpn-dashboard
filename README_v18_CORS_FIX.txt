TPN Dashboard v18 - Netlify shared acknowledgement CORS fix

Replace these TWO files in GitHub:

1) dashboard.html
   -> repository root /dashboard.html

2) acknowledgements.mjs
   -> /netlify/functions/acknowledgements.mjs

Do not replace server.py, collector.py, build_data_from_xlsx.py or data.js.

What changed:
- Netlify acknowledgement function now returns permissive CORS headers on every response.
- OPTIONS preflight is explicitly supported.
- Dashboard POST uses text/plain JSON, which is a CORS 'simple request' and avoids browser preflight.
- No cookies/credentials are sent to the acknowledgement API.
- Existing Netlify Blobs shared acknowledgement storage and audit history remain unchanged.

After GitHub commits both files, wait for BOTH Netlify and Render to redeploy.
Then hard-refresh the Render dashboard (Ctrl+F5), acknowledge one docket, and check:
https://meek-lollipop-ea9426.netlify.app/api/acknowledgements
The docket should now appear in the acknowledgements object.
