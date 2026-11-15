# Iku homelab architecture

The three machines have different jobs. They are not identical copies of the Iku stack.

| Machine | Current role | Services and limits |
| --- | --- | --- |
| OVH VPS `vps-4e5174e4` | Primary K3s server and application host | Iku Auth, portal, PostgreSQL Drisa memory, Nextcloud, n8n, private LFM3 router, and MOSS/Kokoro audio service. Tailscale-only forwarding protects internal APIs; Cloudflare Tunnel publishes the website and portal login. It is the only control plane. |
| Linux `homelab` | Tainted K3s fallback worker and off-host backup receiver | Restic repository and pruning/restore jobs, plus one public-site and Cloudflare Tunnel replica. The `homelab.role=fallback:NoSchedule` taint keeps ordinary workloads off this low-power machine. |
| Windows laptop | Interactive Drisa client and third compute fallback | Acer Aspire AG15-42P, Ryzen 7 5825U (8 cores/16 threads), 31.4 GiB RAM, AMD Radeon integrated graphics as reported by Windows. Always-on microphone listener and voice gateway. Normal mode uses local MOSS/Parakeet, Kokoro, and Unsloth as fallbacks. Gaming mode stops the local Unsloth server and 3D world while keeping the listener and gateway; it routes STT to homelab MOSS with Parakeet fallback, TTS to homelab Kokoro, and LLM requests to VPS LFM3. |

## Request and data paths

- The Redmi Iku app authenticates with Firebase and the Iku Auth bridge. Its private service status and model-management calls require an Iku session.
- The Drisa voice gateway on the laptop is reached by Android through its tailnet-only Tailscale Serve hostname. Android speech is transcribed, answered by the selected LFM3 host with shared PostgreSQL history, and returned through VPS Kokoro. Desktop-world speech uses the same PostgreSQL conversation, then publishes its exact transcript and reply through the authenticated local gateway so connected Android clients receive the same turn and Kokoro audio.
- LFM3 runs on the VPS at a private ClusterIP and tailnet HTTPS forward. Unsloth/LFM3 GGUF variants are selectable, with one model resident at a time; the current text selection is uncensored.
- VPS MOSS STT, LFM3, and Kokoro TTS are the default routes. In Normal mode, laptop models are fallbacks if the VPS route is unavailable or busy. Gaming mode stops laptop model serving; audio can fall back to the homelab through a loopback-only SSH tunnel, while text remains VPS-only.
- The public React landing page is served by unprivileged Nginx. `app.iknowu.org` is proxied by that Nginx instance to the Iku portal service, and `cloud.iknowu.org` is proxied to Nextcloud. Cloudflare Tunnel is the public ingress; application ports are not opened on the VPS firewall.
- PostgreSQL stores encrypted Drisa messages and summaries on a VPS-local PVC. Restic sends encrypted backups to the homelab receiver; the restore drill verified the database backup path. This is recovery, not live database replication.

## Hardware and fallback budget

- VPS: 4 vCPU and 8 GiB RAM. It is the default host for LFM3, MOSS, Kokoro, and the application stack. On 2026-11-15, node metrics showed 77% memory use while services were Ready; do not add another resident inference server such as Unsloth Studio without a fresh capacity test. LFM3 already runs through the private `llama.cpp` service.
- Homelab: Intel Pentium J3710 (4 cores) and 7.6 GiB RAM. It runs the Restic receiver, public-site replica, and K3s fallback audio service, but remains a worker and is not a control-plane or general LLM replacement.
- Laptop: Windows reported an 8-core/16-thread Ryzen 7 5825U, 31.4 GiB RAM, and integrated Radeon graphics. Normal mode keeps local LFM3, Parakeet, and Kokoro available as fallbacks while the VPS remains primary. Gaming mode stops laptop inference and the 3D world; the gateway and microphone listener remain active, with VPS text/audio primary and homelab audio as fallback. Text has no laptop fallback while gaming.

The laptop hardware values were read from Windows on 2026-11-15; the integrated graphics entry is the only adapter reported in that snapshot. They are a capacity reference, not a promise of model throughput. The VPS measurements are instantaneous and should be refreshed before any service is added.

## Network isolation

The public website and portal are published through Cloudflare Tunnel. Tailscale Serve listeners on the VPS are tailnet-only; every Kubernetes Service is `ClusterIP`, and there are no Kubernetes Ingress resources. The public Nginx proxy sends `app.iknowu.org` to the portal and `cloud.iknowu.org` to Nextcloud.

On 2026-11-14, ingress allow-lists were applied to the portal, Iku Auth, Nextcloud, n8n, and LFM3 using `deploy/k3s/service-ingress-network-policies.yaml`; separate policies still protect Drisa audio, Drisa PostgreSQL, and the backup namespace. Egress remains unrestricted by these new policies. Traffic from a pod's node remains allowed by Kubernetes, preserving node-local Tailscale Serve forwards and kubelet probes. After applying, the public site, portal login/auth endpoint, and Nextcloud login/status returned their expected HTTP responses; n8n and LFM3 returned HTTP 200 over their tailnet-only Serve ports, and all selected pods remained Ready. Add any new in-cluster callers to the relevant policy before deploying them.

## Availability boundaries

K3s currently has two Ready nodes, but only the VPS runs the control plane. The public site and its Cloudflare connector each have two replicas, with required pod anti-affinity placing one on each node. This gives the static site an independent connector and origin on the homelab. The portal, Auth, PostgreSQL, Nextcloud, n8n, and LFM3 are still VPS workloads; their local-path storage is not replicated. They do not automatically fail over if the VPS is unavailable. The homelab can receive scheduled backups, but restoring services there remains a manual recovery operation.

See [the resilience runbook](iku-resilience-runbook.md) for checks and recovery boundaries, [K3s deployment notes](../../deploy/k3s/README.md), and the [VPS capacity snapshot](iku-vps-capacity.md).
