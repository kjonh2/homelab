# Iku on K3s

The VPS is the first K3s server. It uses the embedded SQLite datastore, encrypted Kubernetes Secrets, the built-in local-path StorageClass, and a host-only model cache. The API server listens on the host but UFW does not allow public TCP/6443. Only SSH is publicly allowed. The pod and service CIDRs are allowed through UFW for in-cluster networking.

## First node

K3s is installed on `vps-4e5174e4` as the only control-plane server. The Linux `homelab` machine is a Ready worker with the `homelab.role=fallback:NoSchedule` taint. The public React site has two replicas, with required pod anti-affinity placing one on each node. The rest of the application and all K3s control-plane state remain on the VPS; this is not a highly available cluster and workloads do not automatically fail over when the VPS is unavailable. Additional nodes must reach the API over the private Tailscale network; do not open 6443, VXLAN 8472, or kubelet 10250 to the public Internet.

Host security was rechecked on 2026-11-14: UFW is enabled with incoming traffic denied by default; SSH is key-only (`PasswordAuthentication no`, `PermitRootLogin no`, `MaxAuthTries 3`) and rate-limited. Public probes to TCP/5432, 6443, 8443–8445, and 10250 failed over both IPv4 and IPv6. K3s API/6443, Flannel/8472 UDP, and kubelet/10250 are allowed only on `tailscale0` from the homelab node; PostgreSQL/5432 is bound to the VPS Tailscale address and allowed only from the laptop. Pod/service CIDR rules remain for cluster networking. `unattended-upgrades` is active. Applied updates to `containerd.io` 2.4.2-4, Docker Buildx 0.39.0, Docker Compose 5.7.1, and Tailscale 1.104.7; three additional updates remain phased by Ubuntu. Both K3s nodes and all application deployments remained Ready afterward. The host Docker daemon had no running containers and is disabled; K3s continues on its own containerd. If rebuilding an image on the VPS, temporarily start Docker with `sudo systemctl start docker.service`, then stop it again with `sudo systemctl disable --now docker.service docker.socket` after importing the image into K3s.

### Ubuntu 26.04 AppArmor and containerd

The VPS uses Ubuntu 26.04.1, kernel 7.0.0-43, AppArmor 5.0.2, and K3s containerd 2.3.7. With `kernel.apparmor_restrict_unprivileged_unconfined=1`, the default `cri-containerd.apparmor.d` profile can deny signals between processes in the same stacked container profile. On 2026-11-14 this caused PostgreSQL `SIGURG` denials and checkpoint requests waiting at `CheckpointStart`. The profile in `deploy/k3s/apparmor/cri-containerd.apparmor.d` preserves the containerd v2.3.7 restrictions while adding same-container signal and ptrace permissions only for the exact `cri-containerd.apparmor.d//&unconfined` peer. Install it before K3s on rebuilt or replaced Ubuntu 26.04 nodes:

```sh
sudo install -o root -g root -m 0644 deploy/k3s/apparmor/cri-containerd.apparmor.d /etc/apparmor.d/cri-containerd.apparmor.d
sudo apparmor_parser -r -K /etc/apparmor.d/cri-containerd.apparmor.d
```

AppArmor remains enforcing and the host restriction stays enabled. A same-container `SIGURG`/`SIGTERM` check passed after loading the profile. Existing processes may need recreation to use the replacement profile. The PostgreSQL pod was recreated on its existing bound 4 GiB PVC; it returned `2/2 Running`, `CHECKPOINT` and removal of the disposable restore database completed, and the production row counts remained 166 messages and 1 conversation. This is an interim host profile override for [containerd issue #14485](https://github.com/containerd/containerd/issues/14485) while its [upstream template fix](https://github.com/containerd/containerd/pull/14487) remains under review.

See [the current VPS capacity snapshot](../../docs/iku/iku-vps-capacity.md) for the observed resource budget and deployment limits.

## Iku portal

The private portal at the VPS tailnet root checks Nextcloud, n8n, and LFM3 from inside the cluster and shows their current health on the home and Services pages. Its server-side probes read only unauthenticated health endpoints, not user files, workflows, or model prompts. The Android status API validates the Iku session before returning those health states. Links require a device connected to the tailnet. The laptop Drisa gateway is marked as local because the VPS cannot verify its state.

`service-ingress-network-policies.yaml` restricts ingress to the portal, Iku Auth, Nextcloud, n8n, and LFM3 to the proxy and application callers they require. It leaves egress unchanged and relies on the Kubernetes node-traffic exemption for tailnet forwards and kubelet probes. Apply it after reviewing any new in-cluster caller with `Get-Content deploy/k3s/service-ingress-network-policies.yaml -Raw | ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl apply -f -'`. Public traffic still enters through Cloudflare Tunnel; Tailscale Serve listeners remain tailnet-only.

The health probe URLs can be overridden with `NEXTCLOUD_HEALTH_URL`, `N8N_HEALTH_URL`, and `LFM3_HEALTH_URL` on the portal Deployment. Probes time out after 2.5 seconds. The 0.1.5 portal and auth manifests added per-account session listing and revocation. The API limits session results to the authenticated user, checks same-origin on browser revocation, revokes an Android refresh-token family with its session, and records an audit event. The auth suite passed 13 tests and the Next.js production build passed. Auth `0.1.4` failed at startup because a shell script had CRLF line endings. `.gitattributes` now enforces LF; auth `0.1.5` and portal `0.1.6` were deployed and Ready. The live portal fails closed with `IKU_AUTH_ENFORCE=true`. The first administrator and TOTP bootstrap are complete; the Kubernetes bootstrap key and VPS bootstrap file have been removed. Auth `0.1.6` and portal `0.1.7` are deployed and Ready. The portal displays health checks for Nextcloud, n8n, and LFM3; profile, current session, and 2FA state from the authenticated session; and enforces the admin role on the admin route. Auth `0.1.6` adds scoped, expiring API tokens with one-time secret display, hash-only storage, per-token revocation, audit events, and API authorization checks. Token administration is restricted to browser sessions; administrators must have TOTP enabled. The SQLite change is an additive startup migration, and the migrated `token_prefix` column is present. The 16-test auth suite and Next.js production build pass. Live checks show the login page returns 200, unauthenticated token API returns 401, and private pages redirect to login. Portal forwarding remains loopback-only through tailnet-only Tailscale Serve. Service pages only check unauthenticated health endpoints.

Portal `0.1.9` adds `GET /api/homelab/status` for the Android Início screen. It requires an Iku bearer session, validates it with `iku-auth`, then returns only the three service names, descriptions, private links, and health states; internal probe URLs and user data are not returned. The phone must be on Tailscale and have a linked Iku session. On 2026-11-12, auth `0.1.7` and portal `0.1.9` were built from commit `8d6a3aa`, imported into K3s containerd, and rolled out Ready. Live checks returned HTTP 200 for `/login`, 401 for `/api/homelab/status` without a bearer token, and 200 for Nextcloud, n8n, and LFM3 health. The Redmi app then refreshed its Iku session and showed all three services available.

## Public landing site

`public-site/` builds a static React landing page for `iknowu.org`; the Kubernetes Deployment serves it through two unprivileged Nginx pods, each paired with a Cloudflare Tunnel connector. Required hostname anti-affinity keeps one pod on the VPS and one on the homelab. Updates may briefly have one replica unavailable so a replacement can move onto its node while the other serves traffic. The same Nginx config routes `app.iknowu.org` to the Iku portal service. The tunnel remains the only public entry point; do not open VPS web ports in UFW. The externally managed Tunnel public-hostname route and end-to-end behavior during a full VPS outage have not been verified; two running connectors do not establish full cluster failover.

On Windows, build and deploy with `powershell -ExecutionPolicy Bypass -File deploy/k3s/deploy-public-site.ps1`. The script uses the existing `%USERPROFILE%\workspace\drisa\cloudflare_tunnel_token_vps.txt` by default; pass `-TunnelTokenFile` only if the token is stored elsewhere. It validates the token file before applying anything, sends the Kubernetes Secret manifest through SSH stdin without writing the token to disk or command arguments, and waits for the rollout and an in-cluster HTTP check. Use `-BuildOnly` to build without connecting to the VPS. Re-run only after Tailscale SSH has been approved for the current session.

### Local Iku Auth

#### Account administration (Auth 0.1.7 / Portal 0.1.9 live)

The admin page and API require a browser session belonging to an MFA-enabled admin; API tokens and normal users receive 403. Admins can create a single-use invitation for a normal `user` account. It expires after 72 hours, is stored as a SHA-256 token hash, and is shown only once in the portal. The invited person enters the code and chooses a password at `/invite`; no public registration or invite token in URLs is enabled. Reissuing an invite for the same email revokes the previous invite. Admins can list pending invites and accounts, cancel invites, and disable or re-enable accounts. Disabling revokes all live sessions, Android refresh families and API tokens, and the API prevents the current admin from disabling themself or the final active admin. These changes create the additive `user_invites` table at service startup and do not alter existing account credentials. Normal users cannot assign roles or promote accounts to admin.

The service is a single-replica FastAPI/SQLite service with Argon2id password hashing, encrypted TOTP seeds, one-time bootstrap, revocable web sessions, rotating Android refresh tokens, login throttling, and audit events. Its ClusterIP is `iku-auth.iku.svc.cluster.local:8080`; the API has no public route or interactive documentation. SQLite lives on a VPS-local PVC and is not HA. Readiness and the unauthenticated session response were checked after deployment.

Install development dependencies, run the API suite, and build the auth image from the repository root:

```powershell
python -m pip install -r services/iku-auth/requirements-dev.txt
python -m unittest discover -s services/iku-auth/tests -v
docker build -t iku-auth:0.2.0 -f services/iku-auth/Dockerfile services/iku-auth
docker build -t iku-portal:0.1.11 -f iku-portal/Dockerfile iku-portal
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

The portal session guard checks the API on every portal request and fails closed if auth cannot be reached. On Android, connect Tailscale, open **Perfil → Ligar sessão Iku**, then confirm the admin TOTP. The Profile screen exchanges a verified Firebase identity for an Iku session and stores access/refresh tokens encrypted with Android Keystore; it rotates refresh tokens on reconnect and revokes the session on logout. Firebase remains the app sign-in provider during this bridge. The Início screen calls `/api/homelab/status` with the short-lived Iku bearer token; after an HTTP 401 it rotates the saved refresh token and retries once, then asks for a new login if the refresh token is invalid. The portal validates the bearer token with Iku Auth before returning only the three service health states. API tokens are managed in the portal's **Segurança** page. Auth `0.2.0` and portal `0.1.11` add OIDC provider routes and an MFA-protected account-to-Nextcloud-UID mapping in **Admin → Contas Iku**.

### Nextcloud OIDC

The auth Deployment uses the issuer `https://app.iknowu.org/api/auth/oidc` and the fixed Nextcloud callback `https://cloud.iknowu.org/apps/user_oidc/code`. Generate and store the client secret on the VPS without printing it, then create the separate Kubernetes Secret before applying `auth.yaml`:

```bash
sudo install -d -m 700 /etc/rancher/k3s/secrets/iku-auth-oidc
sudo sh -c 'umask 077; test -s /etc/rancher/k3s/secrets/iku-auth-oidc/client-secret || openssl rand -hex 32 > /etc/rancher/k3s/secrets/iku-auth-oidc/client-secret'
sudo k3s kubectl -n iku create secret generic iku-auth-oidc \
  --from-file=client-secret=/etc/rancher/k3s/secrets/iku-auth-oidc/client-secret \
  --dry-run=client -o yaml | sudo k3s kubectl apply -f -
```

Build/import auth `0.2.0` and portal `0.1.11`, apply their manifests, and verify both rollouts. Confirm discovery at `https://app.iknowu.org/api/auth/oidc/.well-known/openid-configuration`. Install Nextcloud's `user_oidc` app and configure client ID `nextcloud`, the discovery URL above, and the secret from the protected VPS file. Keep the existing password login enabled. In the Iku portal, **Admin → Contas Iku**, set the current administrator's Nextcloud UID to `ikuadmin`; this maps the OIDC `sub` to the existing account so its current files remain attached. Test the SSO button and a normal login before considering any change to local login or auto-provisioning. Never put the client secret in this repository, a command transcript, or chat.

Live state on 2026-11-14: auth `0.2.0` and portal `0.1.11` are Ready in K3s on the VPS. `iku-auth-oidc` exists as a separate Kubernetes Secret; the provider signing key is generated and persisted by Iku Auth. Nextcloud `user_oidc` `8.13.0` is installed and enabled, with provider identifier `iku`, client ID `nextcloud`, discovery URL above, and mappings `sub` → UID, `email` → email, and `name` → display name. Unique UID is disabled so an administrator can link the provider subject to the existing `ikuadmin` UID. The temporary secret file used for configuration was removed from the Nextcloud pod. The public discovery endpoint and Nextcloud login page both return HTTP 200. Password login remains available. **Still required:** sign in to the Iku portal with the administrator account and TOTP, open **Admin → Contas Iku**, link that Iku account to Nextcloud UID `ikuadmin`, then complete a browser SSO login and confirm the existing files are present. Do not change Nextcloud's default login behavior before that end-to-end check. The Redmi was connected over USB ADB on 2026-11-14: the modern APK was installed, the Iku session renewed, the Drisa WSS gateway authenticated, and the app showed 3/3 services available. The real microphone-to-response flow remains unverified.

## LFM3

The ClusterIP service runs llama.cpp in router mode and discovers GGUFs in `/opt/iku/models`. It lists each model's loaded state and accepts authenticated load requests. `--models-max 1` keeps only one model resident at a time; `--reasoning off` keeps internal reasoning out of generated answers. The model directory is read-only in the Pod. The API key is supplied as a Kubernetes Secret, mounted read-only and passed to llama.cpp by file path so the secret does not appear in the server process arguments. The model-switch helper sends its authorization header to curl through standard input rather than a process argument. The Deployment uses the official llama.cpp server image pinned to the published multi-architecture digest for build `b12242`, CPU inference, four threads, one parallel request, and a 4 GiB memory ceiling.

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

`data-services.yaml` deploys Nextcloud 35.0.2 and n8n 2.46.6 as single replicas with persistent local-path volumes. Both use SQLite for this single-user VPS setup. Nextcloud keeps `config`, `data`, `custom_apps`, and `themes` in separate PVCs; its core code is copied from the image into the container's writable layer at startup. `nextcloud-startup` installs SQLite on the first start and runs `occ upgrade` when the image version changes. This avoids syncing the full code tree into persistent webroot storage. Its container drops all capabilities except the ones needed for ownership setup, Apache's low port, and dropping to the web user. n8n uses a persistent encryption key from the root-only secret file. Web Services remain ClusterIP only: the public `cloud.iknowu.org` host reaches Nextcloud through the existing Cloudflare Tunnel and Nginx proxy, while loopback-only systemd forwards publish private HTTPS via Tailscale Serve. The host firewall blocks public web traffic.

Loopback-only systemd forwards reserve these tailnet endpoints:

| Service | Tailnet URL |
| --- | --- |
| Iku Portal | `https://vps-4e5174e4.tail2931da.ts.net/` |
| n8n | `https://vps-4e5174e4.tail2931da.ts.net:8443/` |
| Nextcloud | `https://vps-4e5174e4.tail2931da.ts.net:8444/` |
| LFM3 API | `https://vps-4e5174e4.tail2931da.ts.net:8445/v1` |

The initial Nextcloud administrator is `ikuadmin`. There is no public self-registration; the Iku portal's invitations create Iku accounts, not Nextcloud accounts. Its initial password is stored in `/etc/rancher/k3s/secrets/iku-data.env` on the VPS with mode 0600. Retrieve it only in the private VPS terminal and never paste it into chat or logs:

```bash
sudo awk -F= '$1 == "NEXTCLOUD_ADMIN_PASSWORD" {print $2}' /etc/rancher/k3s/secrets/iku-data.env
```

The secret contains only the password used at initial installation; it will not reflect a later password change inside Nextcloud. To set a new password when the current one is unknown, connect to the VPS through Tailscale SSH and run the interactive `occ` reset:

```bash
sudo k3s kubectl -n iku exec -it deploy/nextcloud -- su -s /bin/sh www-data -c 'php /var/www/html/occ user:resetpassword ikuadmin'
```

If the public page shows an internal server error, check the live login route, pod status, and recent logs before changing permissions or restoring data:

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' https://cloud.iknowu.org/index.php/login
sudo k3s kubectl -n iku get pods -l app.kubernetes.io/name=nextcloud
sudo k3s kubectl -n iku logs deploy/nextcloud --since=30m
sudo k3s kubectl -n iku exec deploy/nextcloud -- su -s /bin/sh www-data -c 'php /var/www/html/occ status'
```

On 2026-11-14, a logged request failed with SQLite `attempt to write a readonly database`; the Nextcloud Pod was subsequently recreated. The current PVC mounts read-write, the SQLite file and data directory are writable by `www-data`, and the login route returned HTTP 200. If this error recurs, inspect the pod mount and node filesystem state before applying a permission change.

Nextcloud and n8n are configured for the VPS's Tailscale MagicDNS name and private HTTPS ports. Tailscale Serve routes are active for the portal, n8n, Nextcloud, and LFM3 API and are tailnet-only. Do not expose these ClusterIP Services directly to the public Internet. Local-path volumes survive pod restarts but are not backups or replicated storage.

## Drisa mobile voice link

The Android Services screen includes a push-to-talk entry for the Windows laptop's Drisa gateway. The app uses `wss://iknowu.tail2931da.ts.net/`, device ID `redmi-note-11`, and stores the gateway token encrypted with Android Keystore. The gateway also proxies authenticated model status/load requests to the laptop's Unsloth Studio and the private VPS LFM3 API. The token is stored at `C:\Users\kjonh\workspace\drisa\gateway_token.txt` on the laptop and must be entered once in the app.

Install the APK built from `android/` with `gradlew.bat :app:assembleModernDebug`; it is a debug build, not signed for Play Store release. Sign in with the existing Iku account before opening Services; `MainActivity` redirects unauthenticated sessions to Firebase `LoginActivity`. In Services, open **Falar com a Drisa**, keep the endpoint and device ID defaults, enter the gateway token from the laptop once, and connect. The **Modelos da Drisa** panel shows loaded models by host and category and lets the user load an available model on the laptop or VPS.

### Install and validate over wireless ADB

For Android 11 or later, wireless debugging avoids USB-driver issues. Put the laptop and phone on the same Wi-Fi network, then on the phone open **Developer options → Wireless debugging → Pair device with pairing code**. In a PowerShell opened at the repository root, pair with the IP address and pairing port shown on the phone:

```powershell
adb pair <phone-ip>:<pairing-port>
# Enter the short-lived code directly at the adb prompt; never paste it into chat.
```

Return to the main **Wireless debugging** screen and use its connection port (it may differ from the pairing port):

```powershell
adb connect <phone-ip>:<debug-port>
adb devices -l
.\android\gradlew.bat -p android :app:assembleModernDebug
adb install -r android/app/build/outputs/apk/modern/debug/app-modern-debug.apk
```

Accept the MIUI install prompt on the phone if it appears. In the Iku app, sign in, connect to Drisa, load a model, and verify a microphone utterance and Kokoro playback. Android's [wireless debugging guide](https://developer.android.com/tools/adb) documents this pairing flow. The pairing code is not needed after the device is paired; do not store it.

## Laptop Gaming mode

The Drisa mode switch is versioned at [`deploy/windows/drisa_mode.ps1`](../../deploy/windows/drisa_mode.ps1), with gaming environment settings in [`deploy/windows/drisa_remote_config.ps1`](../../deploy/windows/drisa_remote_config.ps1). Copy the mode switch, remote settings, watchdog, and watchdog registration scripts into `%USERPROFILE%\workspace\drisa`; the watchdog checks the gateway and active voice listener every minute while the user is signed in. The launcher dot-sources the runtime copy of the remote configuration. The shared speech sanitizer is [`deploy/windows/drisa_speech_text.py`](../../deploy/windows/drisa_speech_text.py); its tests run with `python -m unittest discover -s deploy/windows -p 'test_*.py'` from the repository root. The Gaming route can be tested without starting services with `powershell -NoProfile -ExecutionPolicy Bypass -File deploy/windows/test_drisa_remote_config.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\kjonh\workspace\drisa\drisa_mode.ps1 gaming
powershell -ExecutionPolicy Bypass -File C:\Users\kjonh\workspace\drisa\drisa_mode.ps1 normal
```

Gaming mode stops the local Unsloth model server and 3D world while retaining the microphone listener and voice gateway. Its watchdog routes transcription to MOSS with Parakeet fallback and speech output to Kokoro on the homelab audio service through a loopback SSH tunnel; text generation goes to the VPS LFM3 API. The text-model choice is preserved from `gateway_config.json`. The mode is implemented but not active; the laptop is currently in normal mode. A synthetic Portuguese voice request passed through MOSS transcription, the VPS LFM3 answer, and Kokoro WAV generation over the tailnet WebSocket. Android UI playback still needs direct verification. The Redmi app displays the loaded laptop model and the private WebSocket route is reachable. The homelab is registered as a tainted K3s fallback worker; current workloads remain on the VPS except for the Restic receiver and the public-site replica.

After restarting the K3s server on the VPS, verify the `iku-portal-forward`, `iku-n8n-forward`, `iku-nextcloud-forward`, and `iku-lfm3-forward` systemd units. Restart them if inactive:

```bash
sudo systemctl restart iku-portal-forward iku-n8n-forward iku-nextcloud-forward iku-lfm3-forward
```

## Persistent application data

The default `local-path` StorageClass stores each PVC on the node that first binds it. This survives pod/container restarts but is not replicated and is not a backup. The off-host backup job below must complete successfully before relying on recovery.

### Encrypted VPS backups to the homelab

`backup.yaml` runs a daily Restic backup from the VPS to a private, append-only Rest Server on the homelab. The repository is encrypted by Restic; the local recovery folder is `C:\Users\kjonh\workspace\drisa\iku-backup-credentials`. Keep a separately protected copy of `restic-password`; without it, the repository cannot be restored. The server password and bcrypt `htpasswd` are also stored there. The backup client sends data over the K3s overlay network and the receiver has no public or tailnet Service.

A second copy of the four recovery files is stored at `/home/kiko/iku-recovery-credentials` on the homelab. Its LUKS-encrypted root volume protects the files at rest; the directory is mode `0700` and each file is mode `0600`, owned by `kiko`. SHA-256 hashes match the laptop originals.

Apply the manifest first to create the isolated namespace, then install/update the credentials and SQLite snapshot ConfigMap without writing secrets into Git:

```powershell
Get-Content deploy/k3s/backup.yaml -Raw | ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl apply -f -'
kubectl create secret generic iku-backup-credentials --namespace iku-backup `
  --from-file=htpasswd="$env:USERPROFILE\workspace\drisa\iku-backup-credentials\htpasswd" `
  --from-file=rest-server-password="$env:USERPROFILE\workspace\drisa\iku-backup-credentials\rest-server-password" `
  --from-file=restic-password="$env:USERPROFILE\workspace\drisa\iku-backup-credentials\restic-password" `
  --dry-run=client -o yaml | ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl apply -f -'
kubectl create configmap iku-backup-sqlite --namespace iku-backup `
  --from-file=backup-sqlite.py=deploy/k3s/backup-sqlite.py `
  --dry-run=client -o yaml | ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl apply -f -'
```

The retention CronJob is active and unsuspended, separate from the append-only backup client. Its dry-run was checked against the live repository, and the user approved the 7 daily, 4 weekly, and 6 monthly retention window. The live schedule runs Sunday at 09:17 Europe/Paris. Apply updates with `Get-Content deploy/k3s/backup-prune.yaml -Raw | tailscale ssh ubuntu@vps-4e5174e4 'sudo k3s kubectl apply -f -'`. Pause it with `sudo k3s kubectl patch cronjob iku-backup-prune -n iku-backup --type=merge -p '{"spec":{"suspend":true}}'` if needed.

The initial snapshot can be started with `ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl -n iku-backup create job --from=cronjob/iku-backup iku-backup-manual'`. The job uses SQLite's online backup API for the Iku auth, n8n, Nextcloud and K3s state databases, validates each snapshot, then backs up those snapshots alongside the VPS K3s persistent volumes and configuration. Other application files are read live, so files changing during the run are not a point-in-time filesystem snapshot. Repository writes are limited to the `iku-backup-client` pod by NetworkPolicy; the client can reach only cluster DNS and the receiver, while the receiver has no egress and accepts only the client on port 8000. The backup namespace allows hostPath only because this job must read node-local K3s files. The Restic client mounts storage, K3s, and config read-only. The SQLite init container mounts only the auth, n8n, Nextcloud, and K3s database directories read-write so SQLite WAL mode can update its shared-memory locks; it opens each database with `mode=ro`. Its added capabilities are `DAC_READ_SEARCH`, `DAC_OVERRIDE`, and `CHOWN`: the backup process runs as root to read service-owned files, then restores the WAL sidecar ownership to match the database owner so a backup cannot lock its service out of SQLite. All other source trees remain read-only, and the Restic client excludes the live SQLite databases and WAL files. A full backup run on 2026-11-12 completed after all four SQLite copies passed integrity checks. The direct Nextcloud mount points to the current PVC directory and must be updated if that PVC is recreated. Both backup containers disallow privilege escalation, use read-only root filesystems, and do not mount service-account tokens. The receiver runs non-root and drops all capabilities. Its `local-path` repository is tied to the homelab disk and does not survive loss of that machine. Append-only mode prevents the backup client from pruning. `backup-prune.yaml` defines a separate maintenance CronJob on the homelab node; it mounts only the Restic password and repository and has no network access. It keeps 7 daily, 4 weekly, and 6 monthly snapshots. Pruning deletes snapshots outside that window. Verify restores periodically rather than assuming a successful upload is enough.

`backup-restore-check.yaml` adds an automated restore drill on the first day of each month at 05:17 Europe/Paris, after the daily backup window. It restores the four SQLite snapshots to an 8 GiB temporary volume on the VPS, runs `PRAGMA integrity_check` on each read-only, then the pod is deleted. The PostgreSQL dump is fully restored into an ephemeral, non-root PostgreSQL server on a Unix socket in the same Pod; the job then queries `drisa_messages` and `drisa_conversations` row counts. The scratch server binds no TCP listener and writes only to an emptyDir. On 2026-11-14, the manual drill restored 15.802 MiB from snapshot `d66679e9`; `iku-auth`, `n8n`, `nextcloud` and `k3s-state` all passed `PRAGMA integrity_check`, and `pg_restore --list` accepted the Drisa dump. A separate full restore of that dump into a disposable database on the PostgreSQL instance also succeeded: `drisa_messages` and `drisa_conversations` matched production at 166 and 1 rows. After the AppArmor profile correction, the temporary database was removed successfully; the production database remained accessible with the same row counts. The job has the same restricted backup-client network policy and secret mounts as the backup client, writes no data to production PVCs, and keeps completed job records for seven days. Apply it with `Get-Content deploy/k3s/backup-restore-check.yaml -Raw | ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl apply -f -'`. To run an immediate drill, use `ssh ubuntu@vps-4e5174e4.tail2931da.ts.net 'sudo k3s kubectl -n iku-backup create job --from=cronjob/iku-backup-restore-check iku-backup-restore-check-manual'` and inspect its logs and completion status. The scheduled job exercises the encrypted repository, file restoration, SQLite integrity, and a full PostgreSQL logical restore; it does not test a full application or whole-node recovery.

The current daily backup template completed a manual run on 2026-11-14 as Job `iku-backup-verify-current-20261114`; the following restore drill completed from snapshot `9c9c1c25`, restoring 15.802 MiB and passing all four SQLite integrity checks. `pg_restore --list` accepted the Drisa dump, and a full restore into a disposable database matched production row counts. The temporary database was removed after the PostgreSQL AppArmor signal policy was corrected.

The updated monthly restore job completed on 2026-11-14 as Job `iku-backup-pgrestore-check-20261114c`. Its Pod passed restricted non-root security settings with UID/GID 70 and no added capabilities. The restored dump loaded successfully into scratch PostgreSQL and returned 162 messages and 1 conversation; the live database check returned 166 and 1. The restored counts describe the snapshot, so they can differ from the live database after subsequent writes. The scratch database used a Unix socket only and was discarded with the Job Pod.

## Homelab fallback worker

The VPS control plane is configured to use its private Tailscale address (`100.67.97.92`) for the API certificate and Flannel interface. Its firewall permits K3s traffic only on `tailscale0` from the homelab (`100.72.114.73`); no public K3s ports are opened. The homelab is an Arch Linux x86_64 machine with 4 CPU cores and 7.6 GiB RAM. It is registered and verified `Ready` on K3s v1.37.2+k3s1 with the `homelab.role=fallback:NoSchedule` taint.

On 2026-11-14, Flannel's `flannel.1` interface was recreated after `tailscale0` briefly disappeared, but the VPS lost its remote homelab route and VXLAN forwarding entry while both Kubernetes nodes still reported `Ready`. A K3s server restart restored them. Check cross-node routing with `ip route get 10.42.1.5` and `bridge fdb show dev flannel.1`; the VPS should route the homelab pod subnet through `flannel.1` and show the homelab VTEP MAC. A successful read-only health request from homelab to the VPS and the completed Restic restore drill verified traffic in both directions after recovery. If the route/FDB is missing, inspect service impact before restarting the single control-plane K3s service, then verify node readiness and cross-node requests again.

`join-homelab-worker.sh` documents how to rejoin it if it is rebuilt: stage a fresh K3s node token in `/home/kiko/.k3s-agent-token` with owner `kiko` and mode `0600`, copy the script to `/home/kiko/`, then run `sudo bash /home/kiko/join-homelab-worker.sh`. The script installs the same K3s version as the VPS, applies only tailnet firewall rules for Flannel VXLAN and metrics, and deletes the temporary token file. It adds the node with a `NoSchedule` taint so services stay on the VPS until fallback workloads and storage are deliberately configured.

Adding this worker does not make the cluster highly available: the VPS still owns the only control plane and the application volumes are local to the VPS. If the VPS is offline, Kubernetes cannot reschedule workloads on the homelab.

## Google sign-in for the Iku portal

The portal login uses Google Identity Services to obtain a Google ID token, exchanges it through Firebase Identity Toolkit, and sends the resulting Firebase ID token to Iku Auth for a web-cookie session. The portal reads the public API key and web OAuth client ID from a mounted `google-services.json`; the browser receives only those two public values and the Firebase project ID. Update the ConfigMap with `kubectl create configmap iku-firebase-web -n iku --from-file=google-services.json=android/app/google-services.json --dry-run=client -o yaml | kubectl apply -f -`, then apply `portal.yaml`. The OAuth web client must allow the portal's HTTPS origin, and Firebase Authentication must authorize that domain. Google sign-in is restricted to an existing, enabled Iku user; admin accounts still require TOTP.
