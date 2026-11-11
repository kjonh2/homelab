# Iku on K3s

The VPS is the first K3s server. It uses the embedded SQLite datastore, encrypted Kubernetes Secrets, the built-in local-path StorageClass, and a host-only model cache. The API server listens on the host but UFW does not allow public TCP/6443. Only SSH is publicly allowed. The pod and service CIDRs are allowed through UFW for in-cluster networking.

## First node

K3s is installed on `vps-4e5174e4` as a single-node cluster. It currently has no public ingress. Additional nodes must reach the API over the private Tailscale network; do not open 6443, VXLAN 8472, or kubelet 10250 to the public Internet.

See [the current VPS capacity snapshot](../../docs/iku/iku-vps-capacity.md) for the observed resource budget and deployment limits.

## Iku portal

The private portal at the VPS tailnet root checks Nextcloud, n8n, and LFM3 from inside the cluster and shows their current health on the home and Services pages. The app checks only unauthenticated health endpoints and does not read user files, workflows, or model prompts. Links require a device connected to the tailnet. The laptop Drisa gateway is marked as local because the VPS cannot verify its state.

The health probe URLs can be overridden with `NEXTCLOUD_HEALTH_URL`, `N8N_HEALTH_URL`, and `LFM3_HEALTH_URL` on the portal Deployment. Probes time out after 2.5 seconds. The profile, device, session, and administration pages remain placeholders until an identity service is implemented; the login form is disabled.

## LFM3

The ClusterIP service runs llama.cpp in router mode and discovers GGUFs in `/opt/iku/models`. It lists each model's loaded state and accepts authenticated load requests. `--models-max 1` keeps only one model resident at a time; `--reasoning off` keeps internal reasoning out of generated answers. The model directory is read-only in the Pod. The API key is supplied as a Kubernetes Secret generated on the VPS. The Deployment uses the official llama.cpp server image pinned to the published multi-architecture digest for build `b12242`, CPU inference, four threads, one parallel request, and a 4 GiB memory ceiling.

On the VPS, create the API key without printing it, then apply the secret:

```bash
sudo install -d -m 700 /etc/rancher/k3s/secrets
sudo sh -c 'umask 077; test -s /etc/rancher/k3s/secrets/lfm3.env || printf "LLAMA_API_KEY=%s\n" "$(openssl rand -hex 32)" > /etc/rancher/k3s/secrets/lfm3.env'
sudo install -d -o root -g root -m 755 /opt/iku/models
sudo cp -L /home/ubuntu/.cache/huggingface/hub/models--LiquidAI--LFM3-1.7B-GGUF/snapshots/cd0c74c575b5c416f3011b5b4c298077f26ca8c2/LFM3-1.7B-Q4_K_M.gguf /opt/iku/models/lfm3-text.gguf
sudo cp -L /home/ubuntu/.cache/huggingface/hub/models--LiquidAI--LFM3-Omni-2B-GGUF/snapshots/d508b88f08a5b4286f2d2805a6a8d69a0ff44c72/LFM3-Omni-2B-Q4_K_M.gguf /opt/iku/models/lfm3-omni.gguf
sudo curl --fail --location --retry 3 'https://huggingface.co/AtomicChat/LFM3-1.7B-Uncensored-GGUF/resolve/main/LFM3-1.7B-Uncensored-AD-Q4_K_M.gguf?download=true' --output /opt/iku/models/lfm3-uncensored.gguf
sudo chown root:root /opt/iku/models/lfm3-uncensored.gguf
sudo chmod 644 /opt/iku/models/lfm3-uncensored.gguf
sudo chmod 644 /opt/iku/models/*.gguf
sudo k3s kubectl apply -f /opt/homelab/deploy/k3s/namespace.yaml
sudo k3s kubectl -n iku create secret generic lfm3-api --from-env-file=/etc/rancher/k3s/secrets/lfm3.env --dry-run=client -o yaml | sudo k3s kubectl apply -f -
sudo k3s kubectl apply -f /opt/homelab/deploy/k3s/lfm3.yaml
```

The API is reachable inside the cluster at `http://lfm3-api.iku.svc.cluster.local:8080/v1`. It has no NodePort or public Ingress. Keep it behind Tailscale and retain the API key when adding clients.

Load one of the installed models without restarting the Pod:

```bash
sudo /opt/homelab/deploy/k3s/switch-lfm3-model.sh text
sudo /opt/homelab/deploy/k3s/switch-lfm3-model.sh uncensored
sudo /opt/homelab/deploy/k3s/switch-lfm3-model.sh omni
```

The VPS exposes the official LFM3 text and Omni models plus [AtomicChat's LFM3-1.7B-Uncensored Q4 model](https://huggingface.co/AtomicChat/LFM3-1.7B-Uncensored-GGUF). The uncensored model is the active VPS text selection. All are served through the authenticated llama.cpp router, with one model resident at a time. The Iku Android app's **Drisa → Modelos da Drisa** panel can list and load models on the VPS or the laptop; transcription and Kokoro TTS remain on the laptop.

## Nextcloud and n8n

`data-services.yaml` deploys Nextcloud 35.0.2 and n8n 2.46.6 as single replicas with persistent local-path volumes. Both use SQLite for this single-user VPS setup. Nextcloud keeps `config`, `data`, `custom_apps`, and `themes` in separate PVCs; its core code is copied from the image into the container's writable layer at startup. `nextcloud-startup` installs SQLite on the first start and runs `occ upgrade` when the image version changes. This avoids syncing the full code tree into persistent webroot storage. Its container drops all capabilities except the ones needed for ownership setup, Apache's low port, and dropping to the web user. n8n uses a persistent encryption key from the root-only secret file. Web Services are ClusterIP only; loopback-only systemd forwards publish private HTTPS via Tailscale Serve. The host firewall blocks public web traffic.

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

Nextcloud and n8n are configured for the VPS's Tailscale MagicDNS name and private HTTPS ports. Tailscale Serve routes are active for the portal, n8n, Nextcloud, and LFM3 API and are tailnet-only. Do not expose these ClusterIP Services directly to the public Internet. Local-path volumes survive pod restarts but are not backups or replicated storage.

## Drisa mobile voice link

The Android Services screen includes a push-to-talk entry for the Windows laptop's Drisa gateway. The app uses `wss://iknowu.tail2931da.ts.net/`, device ID `redmi-note-11`, and stores the gateway token encrypted with Android Keystore. The gateway also proxies authenticated model status/load requests to the laptop's Unsloth Studio and the private VPS LFM3 API. The token is stored at `C:\Users\kjonh\workspace\drisa\gateway_token.txt` on the laptop and must be entered once in the app.

Install the APK built from `android/` with `gradlew.bat :app:assembleModernDebug`; it is a debug build, not signed for Play Store release. Sign in with the existing Iku account before opening Services; `MainActivity` redirects unauthenticated sessions to Firebase `LoginActivity`. In Services, open **Falar com a Drisa**, keep the endpoint and device ID defaults, enter the gateway token from the laptop once, and connect. The **Modelos da Drisa** panel shows loaded models by host and category and lets the user load an available model on the laptop or VPS.

## Laptop Gaming mode

The Drisa mode switch lives at `C:\Users\kjonh\workspace\drisa\drisa_mode.ps1`. The gaming environment configuration is versioned at [`deploy/windows/drisa_remote_config.ps1`](../../deploy/windows/drisa_remote_config.ps1) and copied to `workspace/drisa` so the launcher can dot-source it. The shared speech sanitizer is [`deploy/windows/drisa_speech_text.py`](../../deploy/windows/drisa_speech_text.py); its tests run with `python -m unittest discover -s deploy/windows -p 'test_*.py'` from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\kjonh\workspace\drisa\drisa_mode.ps1 gaming
powershell -ExecutionPolicy Bypass -File C:\Users\kjonh\workspace\drisa\drisa_mode.ps1 normal
```

Gaming mode stops the local Unsloth model server and 3D world while retaining the microphone listener and voice gateway. It selects local Whisper.cpp transcription, Windows PT-PT speech, and the VPS LFM3 router using model ID `lfm3-omni`. The mode is prepared but not activated. The VPS and laptop routes are private to the tailnet; the phone app still needs a final on-device check. The homelab is registered as a tainted K3s fallback worker; current workloads remain on the VPS.

After restarting the K3s server on the VPS, verify the `iku-portal-forward`, `iku-n8n-forward`, `iku-nextcloud-forward`, and `iku-lfm3-forward` systemd units. Restart them if inactive:

```bash
sudo systemctl restart iku-portal-forward iku-n8n-forward iku-nextcloud-forward iku-lfm3-forward
```

## Persistent application data

The default `local-path` StorageClass stores each PVC on the node that first binds it. This survives pod/container restarts but is not replicated and is not a backup. Back up PVCs and the K3s datastore off-host before storing personal files.

## Homelab fallback worker

The VPS control plane is configured to use its private Tailscale address (`100.67.97.92`) for the API certificate and Flannel interface. Its firewall permits K3s traffic only on `tailscale0` from the homelab (`100.72.114.73`); no public K3s ports are opened. The homelab is an Arch Linux x86_64 machine with 4 CPU cores and 7.6 GiB RAM. It is registered and verified `Ready` on K3s v1.37.2+k3s1 with the `homelab.role=fallback:NoSchedule` taint.

`join-homelab-worker.sh` documents how to rejoin it if it is rebuilt: stage a fresh K3s node token in `/home/kiko/.k3s-agent-token` with owner `kiko` and mode `0600`, copy the script to `/home/kiko/`, then run `sudo bash /home/kiko/join-homelab-worker.sh`. The script installs the same K3s version as the VPS, applies only tailnet firewall rules for Flannel VXLAN and metrics, and deletes the temporary token file. It adds the node with a `NoSchedule` taint so services stay on the VPS until fallback workloads and storage are deliberately configured.

Adding this worker does not make the cluster highly available: the VPS still owns the only control plane and the application volumes are local to the VPS. If the VPS is offline, Kubernetes cannot reschedule workloads on the homelab.
