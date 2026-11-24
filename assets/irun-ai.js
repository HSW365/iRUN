/* Shared iRun AI client. All browser AI requests pass through the iRun gateway. */
(() => {
  const ENDPOINT = "https://lsxdlmrjrcivxwgfkpop.supabase.co/functions/v1/irun-ai";
  window.IRUN_AI = async ({ system, messages, max = 3500, onText, signal }) => {
    let owner = "";
    try { owner = localStorage.getItem("irun_owner") || ""; } catch {}
    if (!owner) throw new Error("Sign in to iRun first. Your owner session is missing.");
    const response = await fetch(ENDPOINT, {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner, system, messages, max_tokens: max })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const status = data.provider_status || response.status;
      if (status === 429) throw new Error("iRun AI is temporarily rate-limited or the provider account has reached its usage limit. Check the server-side AI provider quota, then retry.");
      throw new Error(data.error || `iRun AI request failed (${response.status}).`);
    }
    const text = String(data.text || "");
    if (!text.trim()) throw new Error("iRun AI returned an empty response. Try again.");
    if (typeof onText === "function") onText(text);
    return text;
  };
})();
