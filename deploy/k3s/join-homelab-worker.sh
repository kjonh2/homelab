#!/usr/bin/env bash
set -euo pipefail

readonly node_name='homelab'
readonly node_ip='100.72.114.73'
readonly server_ip='100.67.97.92'
readonly version='v1.37.2+k3s1'
readonly token_file='/home/kiko/.k3s-agent-token'

if [[ "${EUID}" -ne 0 ]]; then
  echo 'Run with sudo: sudo bash join-homelab-worker.sh' >&2
  exit 1
fi
if [[ "$(hostname -s)" != "$node_name" ]]; then
  echo "This script is for $node_name only." >&2
  exit 1
fi
if [[ -L "$token_file" || ! -f "$token_file" || "$(stat -c '%U:%a' "$token_file")" != 'kiko:600' ]]; then
  echo 'The temporary K3s token file is missing or has unsafe permissions.' >&2
  exit 1
fi
if ! ip -4 addr show dev tailscale0 | grep -Fq "$node_ip/32"; then
  echo "Tailscale interface does not have the expected address $node_ip." >&2
  exit 1
fi
if ! command -v ufw >/dev/null || ! ufw status | grep -q '^Status: active'; then
  echo 'UFW must be active before joining this node.' >&2
  exit 1
fi

trap 'rm -f "$token_file"' EXIT
ufw allow in on tailscale0 from "$server_ip" to any port 8472 proto udp comment k3s-vps-flannel
ufw allow in on tailscale0 from "$server_ip" to any port 10250 proto tcp comment k3s-vps-metrics

export K3S_URL="https://${server_ip}:6443"
export K3S_TOKEN="$(tr -d '\r\n' < "$token_file")"
export K3S_NODE_NAME="$node_name"
export K3S_NODE_IP="$node_ip"
export INSTALL_K3S_VERSION="$version"
export INSTALL_K3S_EXEC='agent --flannel-iface=tailscale0 --node-label=homelab.role=fallback --node-taint=homelab.role=fallback:NoSchedule'

if [[ -z "$K3S_TOKEN" ]]; then
  echo 'The temporary K3s token file is empty.' >&2
  exit 1
fi
curl -sfL https://get.k3s.io | sh -
systemctl is-active --quiet k3s-agent
echo 'homelab joined as a tainted K3s worker; no application pods will schedule there until explicitly allowed.'
