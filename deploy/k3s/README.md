# Iku on K3s

The VPS is the first K3s server. It uses the embedded SQLite datastore, encrypted Kubernetes Secrets, the built-in local-path StorageClass, and a host-only model cache. The API server listens on the host but UFW does not allow public TCP/6443. Only SSH is publicly allowed. The pod and service CIDRs are allowed through UFW for in-cluster networking.

## First node

K3s is installed on `vps-4e5174e4` as a single-node cluster. It currently has no public ingress. Additional nodes must reach the API over the private Tailscale network; do not open 6443, VXLAN 8472, or kubelet 10250 to the public Internet.

Host security was checked on 2026-11-11: UFW is enabled with incoming traffic denied by default; SSH is key-only (`PasswordAuthentication no`, `PermitRootLogin no`, `MaxAuthTries 3`) and rate-limited. TCP/6443 and TCP/10250 did not accept connections over the VPS public address. `unattended-upgrades` is enabled. The host Docker daemon had no running containers and is disabled; K3s continues on its own containerd. If rebuilding an image on the VPS, temporarily start Docker with `sudo systemctl start docker.service`, then stop it again with `sudo systemctl disable --now docker.service docker.socket` after importing the image into K3s.

See [the current VPS capacity snapshot](../../docs/iku/iku-vps-capacity.md) for the observed resource budget and deployment limits.

## Iku portal

The private portal at the VPS tailnet root checks Nextcloud, n8n, and LFM3 from inside the cluster and shows their current health on the home and Services pages. The app checks only unauthenticated health endpoints and does not read user files, workflows, or model prompts. Links require a device connected to the tailnet. The laptop Drisa gateway is marked as local because the VPS cannot verify its state.

The health probe URLs can be overridden with `NEXTCLOUD_HEALTH_URL`, `N8N_HEALTH_URL`, and `LFM3_HEALTH_URL` on the portal Deployment. Probes time out after 2.5 seconds. The 0.1.5 portal and 0.1.4 auth manifests add per-account session listing and revocation. The API limits session results to the authenticated user, checks same-origin on browser revocation, revokes an Android refresh-token family with its session, and records an audit event. These candidate versions passed the auth API suite (13 tests) and Next.js production build; deployment is pending. The current live versions are `iku-auth:0.1.3` and `iku-portal:0.1.4`. The live portal fails closed with `IKU_AUTH_ENFORCE=true`. The first administrator and TOTP bootstrap are complete; the Kubernetes bootstrap key and VPS bootstrap file have been removed. The current portal displays health checks for Nextcloud, n8n, and LFM3; profile, current session, and 2FA state from the authenticated session; and enforces the admin role on the admin route. MFA-factor changes, API-token management, and broader administrative actions are not yet implemented. Service pages only check unauthenticated health endpoints.

### Local Iku Auth

The service is a single-replica FastAPI/SQLite service with Argon2id password hashing, encrypted TOTP seeds, one-time bootstrap, revocable web sessions, rotating Android refresh tokens, login throttling, and audit events. Its ClusterIP is `iku-auth.iku.svc.cluster.local:8080`; the API has no public route or interactive documentation. SQLite lives on a VPS-local PVC and is not HA. Readiness and the unauthenticated session response were checked after deployment.

Install development dependencies, run the API suite, and build the auth image from the repository root:

```powershell
python -m pip install -r services/iku-auth/requirements-dev.txt
python -m unittest discover -s services/iku-auth/tests -v
docker build -t iku-auth:0.1.4 -f services/iku-auth/Dockerfile services/iku-auth
```

Create a random 32-byte bootstrap token locally and keep it in a user-only file; transfer it to the VPS without printing it. On the VPS, create the encryption key and Kubernetes Secret:

```bash
sudo install -d -m 700 /etc/rancher/k3s/secrets/iku-auth
sudo sh -c 'umask 077; test -s /etc/rancher/k3s/secrets/iku-auth/totp-key || python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())" > /etc/rancher/k3s/secrets/iku-auth/totp-key'
sudo k3s kubectl -n iku create secret generic iku-auth-secrets \
  --from-file=bootstrap-token=/etc/rancher/k3s/secrets/iku-auth/bootstrap-token \
  --from-file=totp-key=/etc/rancher/k3s/secrets/iku-auth/totp-key \
  --dry-run=client -o yaml | sudo k3s kubectl apply -f -
sudo k3s kubectl apply -f /opt/homelab/deploy/k3s/auth.yaml
sudo k3s kubectl -n iku rollout status deployment/iku-auth --timeout=120s
```

The first administrator bootstrap is complete on the live VPS. For a fresh installation only, open [the private Iku portal](https://vps-4e5174e4.tail2931da.ts.net/) while connected to Tailscale, choose **Configurar o primeiro administrador**, set the administrator credentials locally, enroll TOTP, save recovery codes, and confirm a fresh TOTP. Never send the bootstrap token, password, TOTP seed, or recovery codes in chat. After setup, remove the `bootstrap-token` key from the Kubernetes Secret and its VPS file; the live Kubernetes key and VPS file have been removed, and the database permanently disables bootstrap. A leftover client-side token file remains on this Windows PC and should be deleted manually; the completed bootstrap and removed Secret key make it unusable.

The portal session guard checks the API on every portal request and fails closed if auth cannot be reached. On Android, connect Tailscale, open **Perfil → Ligar sessão Iku**, then confirm the admin TOTP. The Profile screen exchanges a verified Firebase identity for an Iku session and stores access/refresh tokens encrypted with Android Keystore; it rotates refresh tokens on reconnect and revokes the session on logout. Firebase remains the app sign-in provider during this bridge. The current APK is installed on the Redmi and its SHA-256 matches the local build. The Firebase-to-Iku exchange is verified live: the Redmi Profile shows **Sessão Iku já ligada** and the auth database reports an active Android session. API-token administration and SSO proxying remain follow-up work. Nextcloud, n8n, and model APIs continue using their own authentication until moved behind the auth gateway and tested.

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

The default `local-path` StorageClass stores each PVC on the node that first binds it. This survives pod/container restarts but is not replicated and is not a backup. The off-host backup job below must complete successfully before relying on recovery.

### Encrypted VPS backups to the homelab

`backup.yaml` runs a daily Restic backup from the VPS to a private, append-only Rest Server on the homelab. The repository is encrypted by Restic; the local recovery folder is `C:\Users\kjonh\workspace\drisa\iku-backup-credentials`. Keep a separately protected copy of `restic-password`; without it, the repository cannot be restored. The server password and bcrypt `htpasswd` are also stored there. The backup client sends data over the K3s overlay network and the receiver has no public or tailnet Service.

Apply the manifest first to create the isolated namespace, then install/update the credentials and SQLite snapshot ConfigMap without writing secrets into Git:

```powershell
Get-Content deploy/k3s/backup.yaml -Raw | ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl apply -f -'
kubectl create secret generic iku-backup-credentials --namespace iku-backup `
  --from-file=htpasswd="$env:USERPROFILE\workspace\drisa\iku-backup-credentials\htpasswd" `
  --from-file=rest-server-password="$env:USERPROFILE\workspace\drisa\iku-backup-credentials\rest-server-password" `
  --from-file=restic-password="$env:USERPROFILE\workspace\drisa\iku-backup-credentials\restic-password" `
  --dry-run=client -o yaml | ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl apply -f -'
kubectl create configmap iku-backup-sqlite --namespace iku-backup `
  --from-file=snapshot_sqlite.py=deploy/k3s/backup-sqlite.py `
  --dry-run=client -o yaml | ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl apply -f -'
```

The retention CronJob is separate from the append-only backup client. Its dry-run was checked against the live repository, and the user approved the 7 daily, 4 weekly, and 6 monthly retention window. The live schedule runs Sunday at 09:17 Europe/Paris. Apply updates with `Get-Content deploy/k3s/backup-prune.yaml -Raw | tailscale ssh ubuntu@vps-4e5174e4 'sudo k3s kubectl apply -f -'`. Pause it with `sudo k3s kubectl patch cronjob iku-backup-prune -n iku-backup --type=merge -p '{"spec":{"suspend":true}}'` if needed.

The initial snapshot can be started with `ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl -n iku-backup create job --from=cronjob/iku-backup iku-backup-manual'`. The job uses SQLite's online backup API for the Iku auth, n8n, Nextcloud and K3s state databases, validates each snapshot, then backs up those snapshots alongside the VPS K3s persistent volumes and configuration. Other application files are read live, so files changing during the run are not a point-in-time filesystem snapshot. Repository writes are limited to the `iku-backup-client` pod by NetworkPolicy; the client can reach only cluster DNS and the receiver, while the receiver has no egress and accepts only the client on port 8000. The backup namespace allows hostPath only because this job must read node-local K3s files. Its storage, K3s and config source mounts are read-only. The SQLite init container alone mounts the Nextcloud data PVC directory read-write so SQLite WAL mode can create its shared-memory lock; it opens the database in read-only mode, and the restic client excludes the live database and WAL files. The path points to the current Nextcloud PVC directory and must be updated if that PVC is recreated. The two root backup containers add only `DAC_READ_SEARCH` to read files owned by service UIDs or root. They disallow privilege escalation, use read-only root filesystems, and do not mount service-account tokens. The receiver runs non-root and drops all capabilities. Its `local-path` repository is tied to the homelab disk and does not survive loss of that machine. Append-only mode prevents the backup client from pruning. `backup-prune.yaml` defines a separate maintenance CronJob on the homelab node; it mounts only the Restic password and repository and has no network access. It keeps 7 daily, 4 weekly, and 6 monthly snapshots. Pruning deletes snapshots outside that window. Verify restores periodically rather than assuming a successful upload is enough.

## Homelab fallback worker

The VPS control plane is configured to use its private Tailscale address (`100.67.97.92`) for the API certificate and Flannel interface. Its firewall permits K3s traffic only on `tailscale0` from the homelab (`100.72.114.73`); no public K3s ports are opened. The homelab is an Arch Linux x86_64 machine with 4 CPU cores and 7.6 GiB RAM. It is registered and verified `Ready` on K3s v1.37.2+k3s1 with the `homelab.role=fallback:NoSchedule` taint.

`join-homelab-worker.sh` documents how to rejoin it if it is rebuilt: stage a fresh K3s node token in `/home/kiko/.k3s-agent-token` with owner `kiko` and mode `0600`, copy the script to `/home/kiko/`, then run `sudo bash /home/kiko/join-homelab-worker.sh`. The script installs the same K3s version as the VPS, applies only tailnet firewall rules for Flannel VXLAN and metrics, and deletes the temporary token file. It adds the node with a `NoSchedule` taint so services stay on the VPS until fallback workloads and storage are deliberately configured.

Adding this worker does not make the cluster highly available: the VPS still owns the only control plane and the application volumes are local to the VPS. If the VPS is offline, Kubernetes cannot reschedule workloads on the homelab.
