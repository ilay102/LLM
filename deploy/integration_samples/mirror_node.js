/**
 * mirror_node.js — drop-in async traffic mirror for Node.js apps.
 *
 * What this does:
 *     Your prod code keeps calling OpenAI/Anthropic exactly as before.
 *     Every request is ALSO sent (fire-and-forget) to the VIREN gateway
 *     for side-by-side comparison.
 *
 * Properties:
 *     - Mirror request is fire-and-forget; never blocks the caller.
 *     - Errors swallowed silently. Prod call is never affected.
 *     - If the gateway is unreachable, the mirror is dropped.
 *
 * Usage — minimal:
 *
 *     const OpenAI = require('openai');
 *     const { attachMirror } = require('./mirror_node');
 *
 *     const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
 *     attachMirror(client, {
 *         gatewayUrl: 'https://gw.example.com/v1',
 *         gatewayKey: 'pilot-...',     // we give you this
 *         pilotId: 'acme-pilot-1',
 *     });
 *
 *     // Use client as normal — mirror happens in background.
 *     const resp = await client.chat.completions.create({ ... });
 */

const DEFAULTS = {
  modelOverride: 'auto',
  sampleRate: 1.0,
  timeoutMs: 10000,
};

async function mirrorCall(gatewayUrl, gatewayKey, pilotId, payload, timeoutMs) {
  // Use global fetch (Node 18+). Falls back gracefully if missing.
  const fetchFn = (typeof fetch === 'function')
    ? fetch
    : (await import('node-fetch')).default;

  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), timeoutMs);

  try {
    await fetchFn(`${gatewayUrl.replace(/\/$/, '')}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${gatewayKey}`,
        'x-pilot-id': pilotId,
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (_e) {
    // Swallow. Mirror is best-effort.
  } finally {
    clearTimeout(t);
  }
}

function buildPayload(kwargs, modelOverride) {
  const out = {
    model: modelOverride || kwargs.model || 'auto',
    messages: kwargs.messages || [],
  };
  for (const k of ['temperature', 'max_tokens', 'top_p', 'stop', 'tools',
                   'tool_choice', 'response_format']) {
    if (kwargs[k] !== undefined) out[k] = kwargs[k];
  }
  return out;
}

/**
 * Wrap an OpenAI client's chat.completions.create in place. Subsequent calls
 * will also fire a mirror request in the background.
 */
function attachMirror(client, opts) {
  const {
    gatewayUrl,
    gatewayKey,
    pilotId,
    modelOverride = DEFAULTS.modelOverride,
    sampleRate = DEFAULTS.sampleRate,
    shouldMirror = null,
    timeoutMs = DEFAULTS.timeoutMs,
  } = opts;

  if (!gatewayUrl || !gatewayKey || !pilotId) {
    throw new Error('attachMirror: gatewayUrl, gatewayKey, and pilotId are required');
  }

  const original = client.chat.completions.create.bind(client.chat.completions);

  client.chat.completions.create = async function (kwargs, requestOptions) {
    // Decide whether to mirror this call.
    const mirrorThis =
      (sampleRate >= 1.0 || Math.random() < sampleRate) &&
      (!shouldMirror || shouldMirror(kwargs));

    if (mirrorThis) {
      const payload = buildPayload(kwargs, modelOverride);
      // Fire-and-forget. We do NOT await.
      void mirrorCall(gatewayUrl, gatewayKey, pilotId, payload, timeoutMs);
    }

    // Always proceed with the real call as before.
    return original(kwargs, requestOptions);
  };
}

/** Anthropic SDK variant (anthropic.messages.create) */
function attachMirrorAnthropic(client, opts) {
  const {
    gatewayUrl, gatewayKey, pilotId,
    modelOverride = DEFAULTS.modelOverride,
    sampleRate = DEFAULTS.sampleRate,
    timeoutMs = DEFAULTS.timeoutMs,
  } = opts;
  const original = client.messages.create.bind(client.messages);

  client.messages.create = async function (kwargs, requestOptions) {
    if (sampleRate >= 1.0 || Math.random() < sampleRate) {
      const payload = {
        model: modelOverride || kwargs.model || 'auto',
        messages: kwargs.messages || [],
        max_tokens: kwargs.max_tokens || 1024,
        ...(kwargs.temperature !== undefined && { temperature: kwargs.temperature }),
        ...(kwargs.tools !== undefined && { tools: kwargs.tools }),
      };
      void mirrorCall(gatewayUrl, gatewayKey, pilotId, payload, timeoutMs);
    }
    return original(kwargs, requestOptions);
  };
}

module.exports = { attachMirror, attachMirrorAnthropic };

// --- Demo when run directly ------------------------------------------------
if (require.main === module) {
  (async () => {
    const OpenAI = require('openai');
    const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY || 'sk-dummy' });
    attachMirror(client, {
      gatewayUrl: process.env.GATEWAY_URL || 'http://localhost:8000/v1',
      gatewayKey: process.env.GATEWAY_KEY || 'dev-key',
      pilotId: 'demo',
    });
    console.log('Mirror attached. Making a normal call...');
    const resp = await client.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: [{ role: 'user', content: 'Say hi in 5 words.' }],
      max_tokens: 20,
    });
    console.log('Prod response:', resp.choices[0].message.content);
    console.log('(Mirror is firing in the background — check gateway logs.)');
    // Let the background mirror finish before exit
    await new Promise(r => setTimeout(r, 2000));
  })();
}
