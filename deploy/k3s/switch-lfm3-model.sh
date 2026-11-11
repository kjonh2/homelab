#!/usr/bin/env bash
set -euo pipefail

variant="${1:-}"
case "$variant" in
  text)
    model_path='/models/lfm3-text.gguf'
    ;;
  omni)
    model_path='/models/lfm3-omni.gguf'
    ;;
  *)
    echo 'Usage: sudo ./switch-lfm3-model.sh text|omni' >&2
    exit 2
    ;;
esac

kubectl_bin=(sudo k3s kubectl)
"${kubectl_bin[@]}" -n iku create configmap lfm3-model --from-literal="MODEL_PATH=$model_path" --dry-run=client -o yaml | "${kubectl_bin[@]}" apply -f -
"${kubectl_bin[@]}" -n iku rollout restart deployment/lfm3-server
"${kubectl_bin[@]}" -n iku rollout status deployment/lfm3-server --timeout=15m
