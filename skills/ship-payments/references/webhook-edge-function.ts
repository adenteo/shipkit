// RevenueCat webhook receiver (Supabase edge function example).
//
// RevenueCat POSTs subscription lifecycle events here so the backend can
// mirror the user's premium entitlement into its own `users` table. The
// CLIENT still treats RevenueCat as the source of truth for gating; this
// mirror exists so server-side code has a single column to read instead of
// round-tripping to RC's REST API.
//
// ── How to adapt ─────────────────────────────────────────────────────────
// - Non-Supabase backend: the LOGIC is platform-agnostic, verify the shared
//   secret, classify the event type, skip anonymous users, upsert the row.
//   Only the Supabase client calls need swapping.
// - Add these columns to your users table first:
//     is_premium boolean, premium_expires_at timestamptz,
//     premium_product_id text, premium_updated_at timestamptz
//
// ── Setup ────────────────────────────────────────────────────────────────
// 1. Deploy the function. On Supabase, deploy with --no-verify-jwt:
//        npx supabase functions deploy revenuecat-webhook --no-verify-jwt
//    RevenueCat does not send a Supabase JWT, so the gateway's JWT check
//    would reject every event. The function authenticates via its own
//    shared secret instead.
// 2. RC Dashboard → Integrations → Webhooks → add the function URL, and set
//    an Authorization header value (any strong random string).
// 3. Store that same value as the REVENUECAT_WEBHOOK_SECRET env var.
//
// ── Identity ─────────────────────────────────────────────────────────────
// Events identify the user via `app_user_id`, which the iOS client sets by
// calling Purchases.logIn(<your user id>). If the client never calls logIn,
// events arrive with an anonymous `$RCAnonymousID:` user and are skipped:
// there is nothing to update server-side.

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

// We trust RevenueCat's event classification.
const ENABLE_EVENTS = new Set([
  "INITIAL_PURCHASE",
  "RENEWAL",
  "UNCANCELLATION",
  "PRODUCT_CHANGE",
  "TRANSFER",
  "NON_RENEWING_PURCHASE",
  "TEMPORARY_ENTITLEMENT_GRANT",
]);

const DISABLE_EVENTS = new Set([
  "CANCELLATION",
  "EXPIRATION",
  "SUBSCRIPTION_PAUSED",
  "BILLING_ISSUE",
]);
// Anything else (TEST, INVOICE_ISSUANCE, SUBSCRIBER_ALIAS, …) is acknowledged
// with a 200 but causes no DB write.

interface RCEvent {
  type: string;
  app_user_id?: string;
  original_app_user_id?: string;
  product_id?: string;
  expiration_at_ms?: number;
}

interface RCWebhookPayload {
  event?: RCEvent;
}

serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  // Verify the shared secret. The endpoint is public, this is the only
  // thing standing between the internet and your users table.
  const expectedSecret = Deno.env.get("REVENUECAT_WEBHOOK_SECRET");
  if (!expectedSecret) {
    console.error("[rc-webhook] REVENUECAT_WEBHOOK_SECRET not set");
    return new Response("Server misconfigured", { status: 500, headers: corsHeaders });
  }
  if (req.headers.get("authorization") !== expectedSecret) {
    console.warn("[rc-webhook] Rejected request with bad/missing auth");
    return new Response("Unauthorized", { status: 401, headers: corsHeaders });
  }

  let payload: RCWebhookPayload;
  try {
    payload = await req.json();
  } catch (_) {
    return new Response("Bad JSON", { status: 400, headers: corsHeaders });
  }

  const event = payload.event;
  if (!event) {
    return new Response("Missing event", { status: 400, headers: corsHeaders });
  }

  const eventType = event.type ?? "";
  console.log(`[rc-webhook] Received event=${eventType}`);

  // Identify the user. Skip anonymous events, the user wasn't logged in.
  const appUserId = event.app_user_id ?? event.original_app_user_id ?? "";
  if (!appUserId || appUserId.startsWith("$RCAnonymousID:")) {
    console.log(`[rc-webhook] Skipping anonymous event (app_user_id=${appUserId})`);
    return new Response("ok (anonymous)", { status: 200, headers: corsHeaders });
  }

  // Decide whether this event enables or disables premium.
  let isPremium: boolean;
  if (ENABLE_EVENTS.has(eventType)) {
    isPremium = true;
  } else if (DISABLE_EVENTS.has(eventType)) {
    isPremium = false;
  } else {
    console.log(`[rc-webhook] Event '${eventType}' is non-mutating, no DB write`);
    return new Response("ok (no-op)", { status: 200, headers: corsHeaders });
  }

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } },
  );

  const expiresAt = event.expiration_at_ms
    ? new Date(event.expiration_at_ms).toISOString()
    : null;

  const { error } = await supabase
    .from("users")
    .update({
      is_premium: isPremium,
      premium_expires_at: expiresAt,
      premium_product_id: event.product_id ?? null,
      premium_updated_at: new Date().toISOString(),
    })
    .eq("id", appUserId);

  if (error) {
    console.error(`[rc-webhook] DB update failed for user=${appUserId}:`, error);
    return new Response("DB update failed", { status: 500, headers: corsHeaders });
  }

  console.log(`[rc-webhook] Updated user=${appUserId} → is_premium=${isPremium}`);
  return new Response("ok", { status: 200, headers: corsHeaders });
});
