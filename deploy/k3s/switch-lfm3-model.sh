#!/usr/bin/env bash
set -euo pipefail

variant="${1:-}"
case "$variant" in
  text) model_id='lfm3-text' ;;
  omni) model_id='lfm3-omni' ;;
  *) echo 'Usage: sudo ./switch-lfm3-model.sh text|omni' >&2; exit 2 ;;
esac

kubectl_bin=(sudo k3s kubectl)
secret="$("${kubectl_bin[@]}" -n iku get secret lfm3-api -o jsonpath='{.data.LLAMA_API_KEY}' | base64 -d)"
log_file="$(mktemp)"
"${kubectl_bin[@]}" -n iku port-forward --address=127.0.0.1 svc/lfm3-api 18085:8080 >"$log_file" 2>&1 &
forward_pid=$!
cleanup() { kill "$forward_pid" 2>/dev/null || true; rm -f "$log_file"; }
trap cleanup EXIT

for _ in $(seq 1 40); do
  if curl --silent --fail -H "Authorization: Bearer $secret" http://127.0.0.1:18085/models >/dev/null; then break; fi
  sleep 0.25
done
curl --fail --silent --show-error \
  -H "Authorization: Bearer $secret" \
  -H 'Content-Type: application/json' \
  --data "{\"model\":\"$model_id\"}" \
  http://127.0.0.1:18085/models/load
printf '\nRequested %s model load.\n' "$variant"
