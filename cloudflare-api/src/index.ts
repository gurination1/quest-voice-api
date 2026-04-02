interface Env {
  AI: Ai;
  API_KEYS: KVNamespace;
  UPSTREAM_MODE: string;
  UPSTREAM_OPENAI_BASE_URL: string;
  UPSTREAM_OPENAI_API_KEY: string;
  UPSTREAM_OPENAI_MODEL: string;
  DEFAULT_REPLY_MODEL: string;
  DEFAULT_STT_MODEL: string;
  DEFAULT_TTS_MODEL: string;
  ALLOW_SHARED_KEYS: string;
  ALLOW_PERSONAL_KEYS: string;
  FALLBACK_CONFIG_JSON: string;
}

type ServiceMode = "device" | "cloud" | "off";

interface ApiKeyRecord {
  id: string;
  label: string;
  mode: "shared" | "personal";
  enabled: boolean;
  features?: {
    cloud_stt?: boolean;
    cloud_reply?: boolean;
    cloud_tts?: boolean;
  };
  limits?: {
    max_requests_per_day?: number;
  };
}

interface ReplyRequest {
  transcript?: string;
  history?: string[];
  mode?: "fast" | "full";
}

interface SessionRequest {
  transcript?: string;
  text?: string;
  history?: string[];
  stt_mode?: ServiceMode;
  reply_mode?: ServiceMode;
  tts_mode?: ServiceMode;
  voice?: string;
  audio_base64?: string;
}

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, content-type, x-api-key",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method === "OPTIONS") {
      return new Response("ok", { headers: corsHeaders });
    }

    try {
      const url = new URL(request.url);
      const pathname = url.pathname;

      if (pathname === "/health") {
        return json({
          ok: true,
          status: "ok",
          timestamp: new Date().toISOString(),
          defaults: {
            reply_model: env.DEFAULT_REPLY_MODEL,
            stt_model: env.DEFAULT_STT_MODEL,
            tts_model: env.DEFAULT_TTS_MODEL,
          },
        });
      }

      const keyRecord = await verifyApiKey(request, env);

      if (pathname === "/config" && request.method === "GET") {
        return handleConfig(env, keyRecord);
      }
      if (pathname === "/reply" && request.method === "POST") {
        return handleReply(request, env, keyRecord);
      }
      if (pathname === "/stt" && request.method === "POST") {
        return handleStt(request, env, keyRecord);
      }
      if (pathname === "/tts" && request.method === "POST") {
        return handleTts(request, env, keyRecord);
      }
      if (pathname === "/session/respond" && request.method === "POST") {
        return handleSession(request, env, keyRecord);
      }
      if (pathname === "/v1/chat/completions" && request.method === "POST") {
        return handleChatCompletions(request, env, keyRecord);
      }

      return json({ ok: false, error: "Not found" }, 404);
    } catch (error) {
      const status = error instanceof HttpError ? error.status : 500;
      return json(
        {
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        },
        status,
      );
    }
  },
};

async function verifyApiKey(request: Request, env: Env): Promise<ApiKeyRecord> {
  const authHeader = request.headers.get("authorization");
  const xApiKey = request.headers.get("x-api-key");
  const token = authHeader?.startsWith("Bearer ")
    ? authHeader.slice("Bearer ".length).trim()
    : xApiKey?.trim();

  if (!token) {
    throw new HttpError(401, "Missing API key");
  }

  const kvValue = await env.API_KEYS.get(`key:${token}`);
  if (!kvValue) {
    throw new HttpError(403, "Invalid API key");
  }

  const keyRecord = JSON.parse(kvValue) as ApiKeyRecord;
  if (!keyRecord.enabled) {
    throw new HttpError(403, "API key disabled");
  }

  if (keyRecord.mode === "shared" && env.ALLOW_SHARED_KEYS !== "true") {
    throw new HttpError(403, "Shared keys are disabled");
  }
  if (keyRecord.mode === "personal" && env.ALLOW_PERSONAL_KEYS !== "true") {
    throw new HttpError(403, "Personal keys are disabled");
  }

  return keyRecord;
}

function handleConfig(env: Env, keyRecord: ApiKeyRecord): Response {
  const fallbackConfig = safeJsonParse(env.FALLBACK_CONFIG_JSON, {});
  return json({
    ok: true,
    key: {
      id: keyRecord.id,
      label: keyRecord.label,
      mode: keyRecord.mode,
    },
    features: {
      cloud_stt: keyRecord.features?.cloud_stt ?? true,
      cloud_reply: keyRecord.features?.cloud_reply ?? true,
      cloud_tts: keyRecord.features?.cloud_tts ?? true,
    },
    defaults: fallbackConfig,
  });
}

async function handleReply(request: Request, env: Env, keyRecord: ApiKeyRecord): Promise<Response> {
  ensureFeature(keyRecord, "cloud_reply");
  const body = (await request.json()) as ReplyRequest;
  const transcript = body.transcript?.trim();
  if (!transcript) {
    throw new HttpError(400, "transcript is required");
  }

  const reply = await generateReply(env, transcript, body.history ?? [], body.mode ?? "fast");
  return json({
    ok: true,
    transcript,
    reply,
    modes: {
      stt: "device",
      reply: "cloud",
      tts: "device",
    },
    fallbacks: [],
  });
}

async function handleStt(request: Request, env: Env, keyRecord: ApiKeyRecord): Promise<Response> {
  ensureFeature(keyRecord, "cloud_stt");
  const formData = await request.formData();
  const audioFile = formData.get("audio");
  if (!(audioFile instanceof File)) {
    throw new HttpError(400, "audio file is required");
  }

  const bytes = await audioFile.arrayBuffer();
  const result = await env.AI.run(env.DEFAULT_STT_MODEL, {
    audio: [...new Uint8Array(bytes)],
  });

  return json({
    ok: true,
    transcript: result.text ?? "",
    provider: env.DEFAULT_STT_MODEL,
  });
}

async function handleTts(request: Request, env: Env, keyRecord: ApiKeyRecord): Promise<Response> {
  ensureFeature(keyRecord, "cloud_tts");
  const body = (await request.json()) as { text?: string; voice?: string };
  const text = body.text?.trim();
  if (!text) {
    throw new HttpError(400, "text is required");
  }

  const result = await env.AI.run(env.DEFAULT_TTS_MODEL, {
    prompt: text,
    voice: body.voice || "en-US-Wavenet-A",
  });

  return json({
    ok: true,
    provider: env.DEFAULT_TTS_MODEL,
    audio: result.audio ?? null,
    format: result.format ?? "wav",
  });
}

async function handleSession(request: Request, env: Env, keyRecord: ApiKeyRecord): Promise<Response> {
  const body = (await request.json()) as SessionRequest;
  const sttMode = body.stt_mode ?? "device";
  const replyMode = body.reply_mode ?? "cloud";
  const ttsMode = body.tts_mode ?? "device";
  const history = body.history ?? [];

  let transcript = body.transcript?.trim() || body.text?.trim() || "";
  const fallbacks: string[] = [];

  if (!transcript && sttMode === "cloud") {
    ensureFeature(keyRecord, "cloud_stt");
    if (!body.audio_base64) {
      throw new HttpError(400, "audio_base64 is required when cloud STT is selected");
    }
    const bytes = base64ToUint8Array(body.audio_base64);
    const sttResult = await env.AI.run(env.DEFAULT_STT_MODEL, { audio: [...bytes] });
    transcript = sttResult.text ?? "";
  }

  let reply = "";
  if (replyMode === "cloud") {
    ensureFeature(keyRecord, "cloud_reply");
    if (transcript) {
      reply = await generateReply(env, transcript, history, "fast");
    } else {
      fallbacks.push("reply_skipped_no_transcript");
    }
  }

  let ttsAudio: unknown = null;
  if (ttsMode === "cloud" && reply) {
    ensureFeature(keyRecord, "cloud_tts");
    const ttsResult = await env.AI.run(env.DEFAULT_TTS_MODEL, {
      prompt: reply,
      voice: body.voice || "en-US-Wavenet-A",
    });
    ttsAudio = ttsResult.audio ?? null;
  }

  return json({
    ok: true,
    transcript,
    reply,
    tts_audio: ttsAudio,
    modes: {
      stt: sttMode,
      reply: replyMode,
      tts: ttsMode,
    },
    fallbacks,
  });
}

async function handleChatCompletions(request: Request, env: Env, keyRecord: ApiKeyRecord): Promise<Response> {
  ensureFeature(keyRecord, "cloud_reply");
  const body = (await request.json()) as {
    messages?: Array<{ role: string; content: string }>;
    model?: string;
    max_tokens?: number;
    temperature?: number;
    stream?: boolean;
  };

  const messages = body.messages ?? [];
  const lastUserMessage = [...messages].reverse().find((message) => message.role === "user")?.content?.trim();
  if (!lastUserMessage) {
    throw new HttpError(400, "at least one user message is required");
  }

  const content = await generateReplyFromMessages(
    env,
    messages,
    body.model,
    body.max_tokens ?? 180,
    body.temperature ?? 0.6,
  );
  return json({
    id: crypto.randomUUID(),
    object: "chat.completion",
    created: Math.floor(Date.now() / 1000),
    model:
      body.model ||
      (env.UPSTREAM_MODE === "openai_proxy" ? env.UPSTREAM_OPENAI_MODEL || "nyx" : env.DEFAULT_REPLY_MODEL),
    choices: [
      {
        index: 0,
        message: {
          role: "assistant",
          content,
        },
        finish_reason: "stop",
      },
    ],
  });
}

async function generateReply(
  env: Env,
  transcript: string,
  history: string[],
  mode: "fast" | "full",
): Promise<string> {
  const maxTokens = mode === "full" ? 320 : 120;
  const systemPrompt =
    mode === "full"
      ? "You are the online reply engine for a Meta Quest 2 avatar app. Answer naturally, clearly, and use complete sentences while staying concise."
      : "You are the fast reply engine for a Meta Quest 2 avatar app. Reply in one or two short sentences.";
  const content = await generateReplyFromMessages(
    env,
    [
      { role: "system", content: systemPrompt },
      {
        role: "user",
        content: `Conversation history:\n${formatHistory(history)}\n\nLatest transcript:\n${transcript}`,
      },
    ],
    undefined,
    maxTokens,
    0.5,
  );
  return content || `Heard: ${transcript}`;
}

async function generateReplyFromMessages(
  env: Env,
  messages: Array<{ role: string; content: string }>,
  requestedModel?: string,
  maxTokens = 180,
  temperature = 0.6,
): Promise<string> {
  if (env.UPSTREAM_MODE === "openai_proxy") {
    return generateReplyViaUpstream(env, messages, requestedModel, maxTokens, temperature);
  }

  const result = await env.AI.run(requestedModel || env.DEFAULT_REPLY_MODEL, {
    messages,
    max_tokens: maxTokens,
    temperature,
  });

  return extractTextResult(result);
}

async function generateReplyViaUpstream(
  env: Env,
  messages: Array<{ role: string; content: string }>,
  requestedModel?: string,
  maxTokens = 180,
  temperature = 0.6,
): Promise<string> {
  const baseUrl = env.UPSTREAM_OPENAI_BASE_URL?.trim();
  if (!baseUrl) {
    throw new HttpError(500, "UPSTREAM_OPENAI_BASE_URL is not configured");
  }

  const response = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/chat/completions`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(env.UPSTREAM_OPENAI_API_KEY
        ? { authorization: `Bearer ${env.UPSTREAM_OPENAI_API_KEY}` }
        : {}),
    },
    body: JSON.stringify({
      model: requestedModel || env.UPSTREAM_OPENAI_MODEL || "nyx",
      messages,
      max_tokens: maxTokens,
      temperature,
      stream: false,
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new HttpError(response.status, `Upstream chat error: ${text}`);
  }

  const payload = (await response.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  return payload.choices?.[0]?.message?.content?.trim() || "";
}

function extractTextResult(result: unknown): string {
  const value = result as
    | { response?: string }
    | { result?: { response?: string } }
    | { choices?: Array<{ message?: { content?: string } }> }
    | { output_text?: string };
  if ("output_text" in value && typeof value.output_text === "string") {
    return value.output_text.trim();
  }
  if ("response" in value && typeof value.response === "string") {
    return value.response.trim();
  }
  if ("result" in value && typeof value.result?.response === "string") {
    return value.result.response.trim();
  }
  if ("choices" in value) {
    return value.choices?.[0]?.message?.content?.trim() || "";
  }
  return "";
}

function ensureFeature(keyRecord: ApiKeyRecord, feature: keyof NonNullable<ApiKeyRecord["features"]>): void {
  if (keyRecord.features?.[feature] === false) {
    throw new HttpError(403, `Feature disabled for this key: ${feature}`);
  }
}

function formatHistory(history: string[]): string {
  return history.length ? history.slice(-8).join("\n") : "No previous turns.";
}

function safeJsonParse<T>(value: string, fallback: T): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function base64ToUint8Array(base64: string): Uint8Array {
  const normalized = base64.includes(",") ? base64.split(",").pop() || "" : base64;
  const decoded = atob(normalized);
  const bytes = new Uint8Array(decoded.length);
  for (let i = 0; i < decoded.length; i += 1) {
    bytes[i] = decoded.charCodeAt(i);
  }
  return bytes;
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      ...corsHeaders,
      "content-type": "application/json; charset=utf-8",
    },
  });
}

class HttpError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}
