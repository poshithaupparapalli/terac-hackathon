// deno test --allow-env supabase/functions/_shared/whop.test.ts
import { assertEquals } from "jsr:@std/assert@1";
import { verifyWebhook } from "./whop.ts";

const SECRET_B64 = btoa("super-secret-key-bytes");
Deno.env.set("WHOP_WEBHOOK_SECRET", `ws_${SECRET_B64}`);

async function sign(id: string, ts: string, body: string) {
  const raw = Uint8Array.from(atob(SECRET_B64), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey("raw", raw, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(`${id}.${ts}.${body}`)));
  return `v1,${btoa(String.fromCharCode(...mac))}`;
}

function req(headers: Record<string, string>) {
  return new Request("http://x", { method: "POST", headers });
}

Deno.test("accepts a valid Standard Webhooks signature", async () => {
  const ts = String(Math.floor(Date.now() / 1000));
  const body = '{"type":"payment.succeeded"}';
  const sig = await sign("msg_1", ts, body);
  assertEquals(await verifyWebhook(req({ "webhook-id": "msg_1", "webhook-timestamp": ts, "webhook-signature": sig }), body), true);
});

Deno.test("rejects tampered body and stale timestamp", async () => {
  const ts = String(Math.floor(Date.now() / 1000));
  const sig = await sign("msg_1", ts, "original");
  assertEquals(await verifyWebhook(req({ "webhook-id": "msg_1", "webhook-timestamp": ts, "webhook-signature": sig }), "tampered"), false);
  const old = String(Math.floor(Date.now() / 1000) - 600);
  const oldSig = await sign("msg_1", old, "original");
  assertEquals(await verifyWebhook(req({ "webhook-id": "msg_1", "webhook-timestamp": old, "webhook-signature": oldSig }), "original"), false);
});
