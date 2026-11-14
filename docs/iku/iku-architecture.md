# Iku homelab architecture

The three machines have different jobs. They are not identical copies of the Iku stack.

| Machine | Current role | Services and limits |
| --- | --- | --- |
| OVH VPS `vps-4e5174e4` | Primary K3s server and application host | Iku Auth, portal, PostgreSQL Drisa memory, Nextcloud, n8n, and the LFM3 router. Tailscale-only forwarding protects internal APIs; Cloudflare Tunnel publishes the website and portal login. It is the only control plane. |
| Linux `homelab` | Tainted K3s fallback worker and off-host backup receiver | Restic repository and pruning/restore jobs, plus one public-site and Cloudflare Tunnel replica. The `homelab.role=fallback:NoSchedule` taint keeps ordinary workloads off this low-power machine. |
| Windows laptop | Interactive Drisa client and third compute fallback | Always-on microphone listener and voice gateway. Normal mode uses laptop MOSS STT with Parakeet fallback, Kokoro TTS, and can run Unsloth locally. Gaming mode stops the local Unsloth server and 3D world while keeping the listener and gateway; it routes STT to homelab MOSS with Parakeet fallback, TTS to homelab Kokoro, and LLM requests to VPS LFM3. |

## Request and data paths

- The Redmi Iku app authenticates with Firebase and the Iku Auth bridge. Its private service status and model-management calls require an Iku session.
- The Drisa voice gateway on the laptop is reached through its tailnet-only Tailscale Serve hostname. The gateway sends transcripts to the selected LFM3 host and sends only the final text to TTS.
- LFM3 runs on the VPS at a private ClusterIP and tailnet HTTPS forward. One model is resident at a time; the uncensored LFM3 text model is the current selection.
- MOSS, Parakeet, and Kokoro are selected from the laptop's local model service in Normal mode. In Gaming mode, the laptop watchdog maintains a loopback-only SSH forward to the homelab audio service and directs STT/TTS there. The homelab worker is therefore a dependency for voice I/O in this mode.
- The public React landing page is served by unprivileged Nginx. `app.iknowu.org` is proxied by that Nginx instance to the Iku portal service, and `cloud.iknowu.org` is proxied to Nextcloud. Cloudflare Tunnel is the public ingress; application ports are not opened on the VPS firewall.
- PostgreSQL stores encrypted Drisa messages and summaries on a VPS-local PVC. Restic sends encrypted backups to the homelab receiver; the restore drill verified the database backup path. This is recovery, not live database replication.

## Network isolation

The public website and portal are published through Cloudflare Tunnel. Tailscale Serve listeners on the VPS are tailnet-only; every Kubernetes Service is `ClusterIP`, and there are no Kubernetes Ingress resources. The public Nginx proxy sends `app.iknowu.org` to the portal and `cloud.iknowu.org` to Nextcloud.

On 2026-11-14, ingress allow-lists were applied to the portal, Iku Auth, Nextcloud, n8n, and LFM3 using `deploy/k3s/service-ingress-network-policies.yaml`; separate policies still protect Drisa audio, Drisa PostgreSQL, and the backup namespace. Egress remains unrestricted by these new policies. Traffic from a pod's node remains allowed by Kubernetes, preserving node-local Tailscale Serve forwards and kubelet probes. After applying, the public site, portal login/auth endpoint, and Nextcloud login/status returned their expected HTTP responses; n8n and LFM3 returned HTTP 200 over their tailnet-only Serve ports, and all selected pods remained Ready. Add any new in-cluster callers to the relevant policy before deploying them.

## Availability boundaries

K3s currently has two Ready nodes, but only the VPS runs the control plane. The public site and its Cloudflare connector each have two replicas, with required pod anti-affinity placing one on each node. This gives the static site an independent connector and origin on the homelab. The portal, Auth, PostgreSQL, Nextcloud, n8n, and LFM3 are still VPS workloads; their local-path storage is not replicated. They do not automatically fail over if the VPS is unavailable. The homelab can receive scheduled backups, but restoring services there remains a manual recovery operation.

See [the resilience runbook](iku-resilience-runbook.md) for checks and recovery boundaries, [K3s deployment notes](../../deploy/k3s/README.md), and the [VPS capacity snapshot](iku-vps-capacity.md).
