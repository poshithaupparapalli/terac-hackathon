#!/usr/bin/env bash
# Usage: bash scripts/set-secret-key.sh
# Prompts (hidden) for the new sb_secret_ key, checks it actually works against the
# database, and only then saves it as the VERA_SECRET_KEY function secret.
set -euo pipefail
REF=lcsjutaaxzntwxfgvhjj
URL="https://$REF.supabase.co"

read -rsp "Paste the sb_secret_ key (input hidden), then Enter: " KEY; echo
KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"

case "$KEY" in
  sb_secret_*) ;;
  sb_publishable_*) echo "✗ That's the publishable key. Copy the SECRET key instead."; exit 1 ;;
  *) echo "✗ Doesn't start with sb_secret_ — copy it again from Project Settings → API Keys."; exit 1 ;;
esac
if [[ "$KEY" == *"·"* || "$KEY" == *"*"* || ${#KEY} -lt 40 ]]; then
  echo "✗ Looks masked/truncated (length ${#KEY}). Use the copy button next to the key."; exit 1
fi

CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/rest/v1/whop_events?select=webhook_id&limit=1" \
  -H "apikey: $KEY" -H "Authorization: Bearer $KEY")
if [[ "$CODE" != "200" ]]; then
  echo "✗ Supabase rejected this key (HTTP $CODE). Nothing was changed."; exit 1
fi

supabase secrets set "VERA_SECRET_KEY=$KEY" --project-ref "$REF" >/dev/null
echo "✓ Key works and is saved as VERA_SECRET_KEY. Tell Claude to re-test."
