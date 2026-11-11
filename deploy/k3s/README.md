# Iku on K3s

The VPS is the first K3s server. It uses the embedded SQLite datastore, encrypted Kubernetes Secrets, the built-in local-path StorageClass, and a host-only model cache. The API server listens on the host but UFW does not allow public TCP/6443. Only SSH is publicly allowed. The pod and service CIDRs are allowed through UFW for in-cluster networking.

## First node

K3s is installed on `vps-4e5174e4` as a single-node cluster. It currently has no public ingress. Additional nodes must reach the API over the private Tailscale network; do not open 6443, VXLAN 8472, or kubelet 10250 to the public Internet.

See [the current VPS capacity snapshot](../../docs/iku/iku-vps-capacity.md) for the observed resource budget and deployment limits.

## LFM3

This manifest serves one model at a time through a ClusterIP service. Omni is the initial model; the text-only model is available by switching the deployment. The GGUFs are copied to `/opt/iku/models` with read-only Pod access, and the API key is supplied as a Kubernetes Secret generated on the VPS. The Deployment uses the official llama.cpp server image pinned to the published multi-architecture digest for build `b12242`, CPU inference, four threads, one parallel request, and a 4 GiB memory ceiling.

On the VPS, create the API key without printing it, then apply the secret:

```bash
sudo install -d -m 700 /etc/rancher/k3s/secrets
sudo sh -c 'umask 077; test -s /etc/rancher/k3s/secrets/lfm3.env || printf "LLAMA_API_KEY=%s\n" "$(openssl rand -hex 32)" > /etc/rancher/k3s/secrets/lfm3.env'
sudo install -d -o root -g root -m 755 /opt/iku/models
sudo cp -L /home/ubuntu/.cache/huggingface/hub/models--LiquidAI--LFM3-1.7B-GGUF/snapshots/cd0c74c575b5c416f3011b5b4c298077f26ca8c2/LFM3-1.7B-Q4_K_M.gguf /opt/iku/models/lfm3-text.gguf
sudo cp -L /home/ubuntu/.cache/huggingface/hub/models--LiquidAI--LFM3-Omni-2B-GGUF/snapshots/d508b88f08a5b4286f2d2805a6a8d69a0ff44c72/LFM3-Omni-2B-Q4_K_M.gguf /opt/iku/models/lfm3-omni.gguf
sudo chmod 644 /opt/iku/models/*.gguf
sudo k3s kubectl apply -f /opt/homelab/deploy/k3s/namespace.yaml
sudo k3s kubectl -n iku create secret generic lfm3-api --from-env-file=/etc/rancher/k3s/secrets/lfm3.env --dry-run=client -o yaml | sudo k3s kubectl apply -f -
sudo k3s kubectl apply -f /opt/homelab/deploy/k3s/lfm3.yaml
```

The API is reachable inside the cluster at `http://lfm3-api.iku.svc.cluster.local:8080/v1`. It has no NodePort or public Ingress. Keep it behind Tailscale and retain the API key when adding clients.

Switch the single model pod:

```bash
sudo /opt/homelab/deploy/k3s/switch-lfm3-model.sh text
sudo /opt/homelab/deploy/k3s/switch-lfm3-model.sh omni
```

The Deployment uses a `Recreate` strategy, so the old model is stopped before the new one starts. The two models are never loaded at the same time.

## Nextcloud and n8n

`data-services.yaml` deploys Nextcloud 35.0.2 and n8n 2.46.6 as single replicas with persistent local-path volumes. Both use SQLite for this single-user VPS setup. Nextcloud keeps `config`, `data`, `custom_apps`, and `themes` in separate PVCs; its core code is copied from the image into the container's writable layer at startup. `nextcloud-startup` installs SQLite on the first start and runs `occ upgrade` when the image version changes. This avoids syncing the full code tree into persistent webroot storage. Its container drops all capabilities except the ones needed for ownership setup, Apache's low port, and dropping to the web user. n8n uses a persistent encryption key from the root-only secret file. Web Services are ClusterIP only; Tailscale Serve will provide private HTTPS after the VPS node is approved. The host firewall blocks public web traffic.

Loopback-only systemd forwards reserve these tailnet endpoints:

| Service | Tailnet URL |
| --- | --- |
| Iku Portal | `https://vps-4e5174e4.tail2931da.ts.net/` |
| n8n | `https://vps-4e5174e4.tail2931da.ts.net:8443/` |
| Nextcloud | `https://vps-4e5174e4.tail2931da.ts.net:8444/` |
| LFM3 API | `https://vps-4e5174e4.tail2931da.ts.net:8445/v1` |

The Nextcloud administrator name is `ikuadmin`. Its generated password and the n8n encryption key are stored in `/etc/rancher/k3s/secrets/iku-data.env` on the VPS with mode 0600. Retrieve the initial Nextcloud password over SSH only when needed:

```bash
sudo awk -F= '$1 == "NEXTCLOUD_ADMIN_PASSWORD" {print $2}' /etc/rancher/k3s/secrets/iku-data.env
```

Nextcloud and n8n are configured for the VPS's Tailscale MagicDNS name and their planned private HTTPS ports. The actual Serve routes still require tailnet approval and have not been enabled. Do not expose these ClusterIP Services directly to the public Internet. Local-path volumes survive pod restarts but are not backups or replicated storage.

## Drisa mobile voice link

The Android Services screen includes a push-to-talk entry for the Windows laptop's Drisa gateway. The app uses `wss://iknowu.tail2931da.ts.net/`, device ID `redmi-note-11`, and stores the gateway token encrypted with Android Keystore. The laptop's Tailscale Serve HTTPS approval is still pending; after approval, serve `http://127.0.0.1:8765` on the laptop. The token is stored at `C:\Users\kjonh\workspace\drisa\gateway_token.txt` on the laptop and must be entered once in the app.

Install the APK built from `android/` with `gradlew.bat :app:assembleModernDebug`; it is a debug build, not signed for Play Store release. Sign in with the existing Iku account before opening Services; `MainActivity` redirects unauthenticated sessions to Firebase `LoginActivity`. In Services, open **Falar com a Drisa**, keep the endpoint and device ID defaults, enter the gateway token from the laptop once, and connect. The Android app encrypts and stores that token with Android Keystore. The Redmi Note 11 accepted the current APK over ADB on 2026-11-11; the voice flow still awaits an authenticated app session and the laptop Serve route.

## Laptop Gaming mode

The Drisa mode switch lives at `C:\Users\kjonh\workspace\drisa\drisa_mode.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\kjonh\workspace\drisa\drisa_mode.ps1 gaming
powershell -ExecutionPolicy Bypass -File C:\Users\kjonh\workspace\drisa\drisa_mode.ps1 normal
```

Gaming mode stops the local Unsloth model server and 3D world while retaining the microphone listener and voice gateway. It selects local Whisper.cpp transcription, Windows PT-PT speech, and the VPS LFM3 Omni endpoint. The mode is prepared but not activated; the VPS and laptop Serve approvals and an end-to-end voice run are still required first. Other Linux tailnet devices are not yet K3s workers; the cluster currently has only the VPS node.

## Persistent application data

The default `local-path` StorageClass stores each PVC on the node that first binds it. This survives pod/container restarts but is not replicated and is not a backup. Back up PVCs and the K3s datastore off-host before storing personal files.
