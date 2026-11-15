#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  exec sudo -n -- bash "$0" "$@"
fi

K3S_BIN="${K3S_BIN:-/usr/local/bin/k3s}"
"$K3S_BIN" kubectl -n kube-system patch deployment metrics-server --type=strategic \
  --patch '{"spec":{"template":{"spec":{"containers":[{"name":"metrics-server","readinessProbe":{"timeoutSeconds":5},"livenessProbe":{"timeoutSeconds":5}}]}}}}'

"$K3S_BIN" kubectl -n kube-system rollout status deployment/metrics-server --timeout=180s
"$K3S_BIN" kubectl top nodes
