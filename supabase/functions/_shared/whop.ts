import { env } from "./util.ts";

// Sandbox: https://sandbox-api.whop.com/api/v1 (test card 4242…). Live: leave unset.
const WHOP_API = Deno.env.get("WHOP_API_BASE") ?? "https://api.whop.com/api/v1";

async function whop(path: string, init: RequestInit = {}) {
  const res = await fetch(`${WHOP_API}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env("WHOP_API_KEY")}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Whop ${init.method ?? "GET"} ${path} → ${res.status}: ${text}`);
  return JSON.parse(text);
}

// A per-study checkout on the tier's fixed-price plan. The metadata is copied
// onto the resulting payment, which is how the webhook knows which study paid.
export async function createCheckout(planId: string, studyId: string, redirectUrl?: string) {
  const body: Record<string, unknown> = { plan_id: planId, metadata: { study_id: studyId } };
  if (redirectUrl) body.redirect_url = redirectUrl;
  const cfg = await whop("/checkout_configurations", { method: "POST", body: JSON.stringify(body) });
  const url = cfg.purchase_url ?? cfg.url ?? cfg.checkout_url;
  if (!url) throw new Error(`Whop checkout response had no purchase_url: ${JSON.stringify(cfg)}`);
  return { id: cfg.id as string, url: url as string };
}

// Never trust a webhook body or a redirect alone: re-fetch the payment from Whop.
export async function getPayment(paymentId: string) {
  const p = await whop(`/payments/${encodeURIComponent(paymentId)}`);
  const paid = p.status === "paid" || p.substatus === "succeeded";
  const amount = Number(p.usd_total ?? p.total ?? p.final_amount ?? p.subtotal ?? NaN);
  return {
    id: p.id as string,
    paid,
    status: p.status as string,
    amountUsd: Number.isFinite(amount) ? amount : null,
    studyId: (p.metadata?.study_id ?? null) as string | null,
    email: (p.user?.email ?? p.member?.email ?? null) as string | null,
    raw: p,
  };
}

// Standard Webhooks scheme: HMAC-SHA256 over `${id}.${timestamp}.${rawBody}`,
// header `webhook-signature: v1,<base64>` (possibly several, space-separated).
// Whop's secret is a `ws_…` string; we try the key encodings the SDKs use
// rather than guess wrong at 6 PM.
export async function verifyWebhook(req: Request, rawBody: string): Promise<boolean> {
  const id = req.headers.get("webhook-id");
  const ts = req.headers.get("webhook-timestamp");
  const sigHeader = req.headers.get("webhook-signature");
  if (!id || !ts || !sigHeader) return false;
  if (Math.abs(Date.now() / 1000 - Number(ts)) > 5 * 60) return false;

  const secret = env("WHOP_WEBHOOK_SECRET");
  const stripped = secret.replace(/^(ws_|whsec_)/, "");
  const enc = new TextEncoder();
  const keys: Uint8Array<ArrayBuffer>[] = [enc.encode(secret), enc.encode(stripped)];
  try {
    keys.push(Uint8Array.from(atob(stripped), (c) => c.charCodeAt(0)));
  } catch { /* not base64 */ }

  const signed = enc.encode(`${id}.${ts}.${rawBody}`);
  const provided = sigHeader.split(" ").map((s) => s.split(",")[1]).filter(Boolean);

  for (const raw of keys) {
    const key = await crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, signed));
    const expected = btoa(String.fromCharCode(...mac));
    if (provided.some((p) => timingSafeEqual(p, expected))) return true;
  }
  return false;
}

function timingSafeEqual(a: string, b: string) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
