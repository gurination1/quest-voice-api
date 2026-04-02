interface ReplyRequest {
  transcript?: string;
  history?: string[];
  mode?: string;
}

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  try {
    const body = (await request.json()) as ReplyRequest;
    const transcript = body.transcript?.trim();

    if (!transcript) {
      return json({ error: "transcript is required" }, 400);
    }

    const model = Deno.env.get("OPENAI_MODEL") ?? "gpt-4o-mini";
    const apiKey = Deno.env.get("OPENAI_API_KEY");
    if (!apiKey) {
      return json({ reply: offlineReply(transcript), mode: "offline" });
    }

    const history = (body.history ?? []).slice(-6).join("\n");
    const response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model,
        input: [
          {
            role: "system",
            content: [
              {
                type: "input_text",
                text:
                  "You produce short spoken replies for an AR/VR live subtitle demo. Reply in one or two short sentences. Be direct and easy to read aloud.",
              },
            ],
          },
          {
            role: "user",
            content: [
              {
                type: "input_text",
                text: `Recent conversation:\n${history}\n\nLatest transcript:\n${transcript}`,
              },
            ],
          },
        ],
        max_output_tokens: 90,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return json({ reply: offlineReply(transcript), upstream_error: errorText }, 200);
    }

    const jsonResponse = await response.json();
    const reply = extractOutputText(jsonResponse) || offlineReply(transcript);
    return json({ reply, mode: "openai" });
  } catch (error) {
    return json(
      { reply: "I caught part of that, but the reply service hit an error.", details: String(error) },
      200,
    );
  }
});

function extractOutputText(payload: any): string {
  const outputs = payload?.output ?? [];
  for (const item of outputs) {
    const contents = item?.content ?? [];
    for (const content of contents) {
      if (typeof content?.text === "string" && content.text.trim()) {
        return content.text.trim();
      }
    }
  }
  return "";
}

function offlineReply(transcript: string): string {
  return `Heard "${transcript}". The hosted model is not configured yet, but subtitles are working.`;
}

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json",
    },
  });
}
