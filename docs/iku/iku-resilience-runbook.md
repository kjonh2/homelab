# Iku resilience and recovery runbook

Last verified: 2026-11-15. This runbook separates live redundancy from backup-based recovery.

## Current layout

- K3s v1.37.2 has one VPS control-plane node and one tainted Linux homelab worker. Both are Ready.
- `iku-public-site` has two ready pods, one on `vps-4e5174e4` and one on `homelab`. Required pod anti-affinity prevents both replicas from landing on the same hostname. During a rolling update, Kubernetes may briefly run one replica while it replaces the other (`maxUnavailable: 1`, `maxSurge: 0`).
- Each public-site pod runs Nginx and a token-authenticated Cloudflare Tunnel connector. Both connectors registered four HTTP/2 edge connections in the latest check. The cluster's outbound QUIC check failed, so the connectors are configured to use HTTP/2.
- `iknowu.org/` and `app.iknowu.org/login` returned HTTP 200 from the public Cloudflare address. This confirms normal public routing, not successful service during a full VPS outage.
- Auth, portal, PostgreSQL, Nextcloud, n8n, and LFM3 remain on the VPS. Their PVC data uses local-path storage. The homelab stores encrypted Restic backups and is not an automatic replacement control plane.
- On 2026-11-14, both K3s nodes were `Ready`; the two `iku-public-site` pods were `2/2 Running` on separate nodes. The latest SQLite and PostgreSQL restore-check jobs completed successfully. `cloud.iknowu.org/index.php/login` returned HTTP 200. These checks confirm the present services and recent backup restore, not recovery after losing the VPS host.
- Revalidated later on 2026-11-15 over Tailscale SSH: both nodes are `Ready`; all nine pods in `iku` were `Running` and `Ready`; all 11 PVCs were `Bound` (10 in `iku`, one 100 GiB Restic repository in `iku-backup`). Several containers had non-zero restart counters, but their recorded last termination reason was `Completed` at 2026-11-15 05:56 UTC; no pod was unready during the check. `kubectl top nodes` showed VPS at 143m CPU/5992 MiB (3%/77%) and homelab at 228m/4371 MiB (5%/55%). This is an instantaneous sample; the VPS still has no measured safe margin for another model-serving process. The Restic server pod was Running on the homelab. The daily backup CronJob was active at 03:17 Europe/Paris; SQLite and PostgreSQL restore-check jobs were Complete. The weekly retention CronJob was active for Sunday 09:17 Europe/Paris with 7 daily, 4 weekly, and 6 monthly snapshots; its `lastScheduleTime` was still empty before its next run, so no retention run was verified yet.
- A later live check on 2026-11-15 over Tailscale SSH again showed both nodes `Ready`, the nine application pods `Running`/`Ready`, and both public-site replicas on separate nodes. The VPS sample had risen to 2711m CPU (67%) and 6579 MiB memory (84%); the homelab showed 1378m CPU (34%) and 4440 MiB (56%). `drisa-audio-vps` used 2066m CPU and 3031 MiB, while `lfm3-server` used 897 MiB; the homelab `drisa-audio` fallback used 2837 MiB. These are point-in-time readings, not capacity guarantees. The VPS has little memory headroom during this sample, so do not add another resident model service such as Unsloth Studio there without new capacity measurements. Both audio deployments remain Ready, with the VPS deployment as primary and the homelab deployment available as fallback.
- A follow-up backup check on 2026-11-15 found the daily backup job Complete and all four SQLite snapshots (`iku-auth`, `n8n`, `nextcloud`, `k3s-state`) passing their integrity checks. The weekly prune job also completed and removed two snapshots; the 7 daily / 4 weekly / 6 monthly policy remains configured. The backup, prune, and monthly restore-check CronJobs are enabled. The restore-check CronJob has not had its first scheduled run (`lastScheduleTime` is empty), although the earlier manual SQLite/PostgreSQL restore drills are Complete. All 11 PVCs are Bound, and 11 NetworkPolicies are installed across `iku` and `iku-backup`. The backup server remains Running on the homelab. A completed backup/prune job confirms that run only; it does not verify that a restore can be performed from the latest snapshot.

## Routine checks

From the laptop while connected to Tailscale:

```powershell
ssh ubuntu@100.67.97.92 "sudo kubectl get nodes -o wide"
ssh ubuntu@100.67.97.92 "sudo kubectl -n iku get pods -l app.kubernetes.io/name=iku-public-site -o wide"
ssh ubuntu@100.67.97.92 "sudo kubectl -n iku logs deploy/iku-public-site -c cloudflared --since=15m"
```

Expect two Ready nodes and two Ready public-site pods on distinct nodes. Check the homelab connector log separately if needed:

```bash
sudo kubectl -n iku logs <homelab-site-pod> -c cloudflared --since=15m
```

Public smoke checks from Windows (the laptop's hosts file currently maps `iknowu.org` to `127.0.0.1`; a normal request resets locally, while forcing Cloudflare succeeds. Do not use the unforced request to diagnose public ingress):

```powershell
curl.exe -sS -o NUL -w '%{http_code}' --resolve iknowu.org:443:188.114.96.2 https://iknowu.org/
curl.exe -sS -o NUL -w '%{http_code}' --resolve app.iknowu.org:443:188.114.96.2 https://app.iknowu.org/login
```

Expected status is `200` for both paths. The app login being public does not make authenticated portal APIs public; those still require an Iku session.

### Nextcloud HTTP 500 triage

On 2026-11-14, a reported Nextcloud Internal Server Error could not be reproduced: the public `/index.php/login` and `/status.php` endpoints both returned HTTP 200, the Nextcloud pod was `1/1 Running` with no restarts, and the recent container log search contained no `error`, `exception`, `critical`, or `500` entries. This only confirms the service at the time of the check; capture the failing URL and reproduce the request before attributing the cause.

From the VPS, check the pod and recent application log around the failure time:

```bash
sudo k3s kubectl -n iku get pods -l app=nextcloud -o wide
sudo k3s kubectl -n iku logs deploy/nextcloud --all-containers --since=30m --tail=300
```

From a client, check the two basic endpoints without following redirects:

```powershell
curl.exe -sS -o NUL -w 'login HTTP %{http_code}\n' https://cloud.iknowu.org/index.php/login
curl.exe -sS -o NUL -w 'status HTTP %{http_code}\n' https://cloud.iknowu.org/status.php
```

## Failure boundaries

| Failure | Current response | Recovery boundary |
| --- | --- | --- |
| One public-site pod or connector fails | Deployment recreates the pod; the other replica remains on the other node. | Verify both pod readiness and both connector logs after recovery. A full node-isolation test has not been run. |
| VPS application pod restarts | K3s restarts the pod and its local PVC remains attached to the VPS. | Check the deployment, pod logs, and readiness probes. |
| VPS host/control plane is offline | Homelab remains an enrolled worker and backup receiver, but cannot become a control plane automatically. Public-site presence on the homelab alone is not proof of end-to-end tunnel/origin failover: DNS, ClusterIP endpoints, and the externally managed tunnel route still need the VPS cluster to be reachable. | Restore the VPS control plane first. Whole-node restore onto homelab is not automated. |
| VPS-local application data is lost | Restore the latest verified Restic snapshots from the homelab repository. | The SQLite integrity and full PostgreSQL logical-dump restore drills passed; the restore job queries the recovered tables in a disposable non-root PostgreSQL server. Whole-node restore remains untested and is not automated. Never treat the backup receiver as live replicated storage. |
| Laptop enters Gaming mode | The listener and gateway stay active while local model serving and the 3D world stop. The updated profile routes MOSS/Parakeet and Kokoro through the homelab's private audio Service, while LFM stays on its selected text host. | Audio API and gateway fallback are verified. MOSS did not finish a short sample within five minutes; the configured 30-second inference timeout then let Parakeet run. The first cold fallback took 81 seconds. On 2026-11-14, the Android-originated WAV was replayed through the live STT, LLM, and Kokoro functions: a transcript returned in 69 seconds, the LLM returned in 31 seconds, and Kokoro generated a 1.73 MB WAV in 45 seconds. This was a server-side replay, not verification of real-time Redmi capture/playback. A later ADB recheck installed the updated APK, confirmed the gateway token was stored encrypted, and authenticated the phone to the Drisa gateway; an actual microphone utterance and phone playback still need user verification. |

## Restore cautions

- Preserve the Restic password separately from the homelab disk. Without it, the encrypted repository cannot be restored.
- If the Drisa PostgreSQL password is exposed or needs rotation, follow [the dedicated credential rotation procedure](drisa-postgres-credential-rotation.md). It preserves the existing PVC and Fernet key.
- The backup receiver and repository reside on the homelab's local storage. Loss of that machine can also lose the off-host backup copy.
- A completed SQLite restore drill verifies those snapshots only. It does not verify PostgreSQL, Kubernetes secret recovery, PVC recreation, public ingress, or full VPS rebuild.
- Do not open K3s, model, PostgreSQL, Nextcloud, or n8n ports to the public Internet to work around a failed tailnet route.
