import { getStore } from '@netlify/blobs';

const STORE_NAME = 'tpn-team-acknowledgements';

function corsHeaders(request) {
  // This endpoint contains no credentials/cookies and is intentionally callable
  // by the Render-hosted dashboard. Using * avoids brittle origin matching and,
  // together with text/plain POSTs from the dashboard, avoids browser preflight issues.
  const requestedHeaders = request.headers.get('access-control-request-headers');
  return {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET, POST, OPTIONS',
    'access-control-allow-headers': requestedHeaders || 'content-type, accept',
    'access-control-max-age': '86400',
    'cache-control': 'no-store',
  };
}

function json(request, body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      ...corsHeaders(request),
    },
  });
}

function cleanText(value, max) {
  return String(value ?? '').trim().slice(0, max);
}

function safeDocket(value) {
  const docket = cleanText(value, 80);
  if (!docket || !/^[A-Za-z0-9._\/-]+$/.test(docket)) return null;
  return docket;
}

function store() {
  return getStore({ name: STORE_NAME, consistency: 'strong' });
}

async function listCurrentAcks() {
  const s = store();
  const result = {};
  for await (const page of s.list({ prefix: 'current/', paginate: true })) {
    for (const blob of page.blobs) {
      const record = await s.get(blob.key, { type: 'json', consistency: 'strong' });
      if (record?.docket) result[String(record.docket)] = record;
    }
  }
  return result;
}

async function parseBody(request) {
  const raw = await request.text();
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    throw new Error('Invalid JSON body.');
  }
}

export default async (request) => {
  if (request.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: corsHeaders(request) });
  }

  if (request.method === 'GET') {
    try {
      const url = new URL(request.url);
      const docket = safeDocket(url.searchParams.get('docket'));
      const s = store();

      if (docket) {
        const record = await s.get(`current/${docket}`, { type: 'json', consistency: 'strong' });
        return json(request, { ok: true, acknowledgement: record || null });
      }

      const acknowledgements = await listCurrentAcks();
      return json(request, {
        ok: true,
        acknowledgements,
        generated_at: new Date().toISOString(),
      });
    } catch (error) {
      console.error('GET acknowledgements failed', error);
      return json(request, { ok: false, error: 'Could not load acknowledgements.' }, 500);
    }
  }

  if (request.method === 'POST') {
    try {
      const body = await parseBody(request);
      const docket = safeDocket(body?.docket);
      const action = cleanText(body?.action, 20).toLowerCase();
      const user = cleanText(body?.user, 80);
      const note = cleanText(body?.note, 500);

      if (!docket) return json(request, { ok: false, error: 'A valid docket is required.' }, 400);
      if (!['acknowledge', 'unacknowledge'].includes(action)) {
        return json(request, { ok: false, error: 'Action must be acknowledge or unacknowledge.' }, 400);
      }
      if (!user) return json(request, { ok: false, error: 'User name is required.' }, 400);

      const now = new Date().toISOString();
      const record = {
        docket,
        acknowledged: action === 'acknowledge',
        user,
        time: now,
        note,
      };

      const s = store();
      await s.setJSON(`current/${docket}`, record);
      await s.setJSON(
        `audit/${docket}/${now.replace(/[:.]/g, '-')}-${crypto.randomUUID()}`,
        {
          ...record,
          action,
          user_agent: cleanText(request.headers.get('user-agent'), 250),
        }
      );

      return json(request, { ok: true, acknowledgement: record });
    } catch (error) {
      console.error('POST acknowledgement failed', error);
      const message = error?.message === 'Invalid JSON body.' ? error.message : 'Could not save acknowledgement.';
      return json(request, { ok: false, error: message }, error?.message === 'Invalid JSON body.' ? 400 : 500);
    }
  }

  return json(request, { ok: false, error: 'Method not allowed.' }, 405);
};

export const config = {
  path: '/api/acknowledgements',
};
