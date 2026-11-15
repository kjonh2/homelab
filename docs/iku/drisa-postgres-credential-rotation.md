# Drisa PostgreSQL credential rotation

Owner: homelab operator  
Frequency: as needed, especially after a credential may have been exposed  
Last updated: 2026-11-14

## Purpose

Rotate the `drisa_memory` PostgreSQL login used by the laptop gateway and the VPS logical-backup sidecar. The database PVC, encrypted conversation rows, and laptop Fernet key must remain unchanged.

## Prerequisites

- Tailscale access to the VPS as `ubuntu`, with working `sudo k3s kubectl` access.
- A verified recent Restic snapshot and a current PostgreSQL logical dump. If either is unavailable, resolve that before rotating.
- A password manager or another private method to create and retain a new high-entropy password. Never put it in chat, a ticket, shell command arguments, terminal output, or repository files.
- Access to the laptop file `C:\Users\kjonh\workspace\drisa\drisa_memory_config.json` and the running Drisa gateway.
- `tailscale` and `scp` installed on the laptop.

## Procedure

### 1. Confirm the current backup and workload

On the VPS:

```bash
sudo k3s kubectl -n iku get pod drisa-memory-postgres-v5-0 -o wide
sudo k3s kubectl -n iku logs drisa-memory-postgres-v5-0 -c logical-backup --since=2h --tail=30
sudo k3s kubectl -n iku get pvc
```

Confirm the PostgreSQL pod is `2/2 Running`, the logical-backup sidecar reports a refreshed dump, and the data PVC is `Bound`. Also confirm a recent verified Restic snapshot using the backup runbook. Stop if the database or backup is unhealthy.

### 2. Create and stage the replacement password

Generate a new random 48-character URL-safe password in a password manager. Do not reuse the exposed password. Create `postgres-password.pending` in a local editor with only that value (no quotes or spaces); avoid a cloud-synced editor. Restrict the file to the current Windows account and remove inheritance:

```powershell
$pending = 'C:\Users\kjonh\workspace\drisa\postgres-password.pending'
icacls $pending /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):(F)"
```

The URL-safe format avoids whitespace and quoting problems in the libpq connection string.

### 3. Change the database role password

Open an interactive psql session. `\password` prompts twice without echoing the password or placing it in the SQL history:

```bash
sudo k3s kubectl -n iku exec -it drisa-memory-postgres-v5-0 -c postgres -- psql -U drisa_memory -d drisa_memory
```

At the `psql` prompt, enter:

```text
\password drisa_memory
```

Paste the new value from the password manager at both hidden prompts, then exit with `\q`. If this step fails, stop and use the recovery instructions below before changing other consumers.

### 4. Update the Kubernetes Secret and restart the StatefulSet

From PowerShell on the laptop, create the Secret manifest in memory and stream it to the VPS over Tailscale SSH. The password is read from the protected file and is not put in command arguments or output:

```powershell
@'
import base64, json, subprocess
from pathlib import Path

password = Path(r"C:\Users\kjonh\workspace\drisa\postgres-password.pending").read_text(encoding="utf-8").strip()
secret = {
    "apiVersion": "v1", "kind": "Secret",
    "metadata": {"name": "drisa-memory-postgres", "namespace": "iku"},
    "type": "Opaque",
    "data": {"password": base64.b64encode(password.encode()).decode()},
}
result = subprocess.run(
    ["tailscale", "ssh", "ubuntu@vps-4e5174e4", "sudo", "k3s", "kubectl", "apply", "-f", "-"],
    input=json.dumps(secret).encode("utf-8"), capture_output=True,
)
if result.returncode:
    raise SystemExit("Secret apply failed; inspect the kubectl error without printing the manifest.")
print(result.stdout.decode("utf-8", errors="replace").strip())
'@ | python -
```

Then, on the VPS, restart the StatefulSet:

```bash
sudo k3s kubectl -n iku rollout restart statefulset/drisa-memory-postgres-v5
sudo k3s kubectl -n iku rollout status statefulset/drisa-memory-postgres-v5 --timeout=180s
```

The restart refreshes the Secret volume and the logical-backup sidecar's `PGPASSWORD` environment. The PostgreSQL pod may be briefly unavailable; its existing PVC must remain attached. Do not delete the PVC or run the initialization script manually.

### 5. Update the laptop configuration and restart Drisa

In the local `drisa_memory_config.json`, replace only the `password=` component in the `dsn` value with the new password. Preserve `conversation_id`, the JSON structure, and `drisa_memory_fernet.key`; replacing the Fernet key makes existing encrypted conversation history unreadable. Save the file with the existing user-only ACL, then restart the Drisa gateway through its normal watchdog/service workflow.

Remove the temporary laptop password file once the gateway connects successfully:

```powershell
Remove-Item -LiteralPath 'C:\Users\kjonh\workspace\drisa\postgres-password.pending' -Force
```

### 6. Verify

On the VPS:

```bash
sudo k3s kubectl -n iku get pod drisa-memory-postgres-v5-0
sudo k3s kubectl -n iku logs drisa-memory-postgres-v5-0 -c logical-backup --since=15m --tail=30
sudo k3s kubectl -n iku exec drisa-memory-postgres-v5-0 -c postgres -- psql -U drisa_memory -d drisa_memory -Atc 'SELECT count(*) FROM drisa_conversations; SELECT count(*) FROM drisa_messages;'
```

Confirm the pod is `2/2 Running`, a new logical dump succeeds, and conversation/message counts are nonzero and consistent with the pre-rotation baseline. From the laptop, confirm the gateway health endpoint and make one Drisa request that reads existing conversation history. Do not print or log the DSN.

The Kubernetes Secret and protected laptop configuration remain the durable credential copies. The temporary local pending file is deleted after the successful gateway check.

## Most recent rotation

On 2026-11-14, the PostgreSQL role password was rotated after the backup and restore checks passed. The Kubernetes Secret and laptop DSN were updated, and the StatefulSet returned to `2/2 Running`. The laptop reconnected with the new credential; a read-only query returned 1 conversation and 166 messages, and two stored message ciphertexts decrypted with the unchanged Fernet key. The logical-backup sidecar refreshed a new dump. The protected local `postgres-password.pending` file was removed after verifying the Secret and laptop connection; a follow-up filesystem check confirmed the file is absent. No password, DSN, conversation text, or key was recorded in this document.

## Recovery

- If the database password changed but the Secret or laptop configuration did not, do not revert to a credential that may have been exposed. Use the local PostgreSQL socket's configured `trust` authentication to open psql again and set a fresh password with `\password`; then repeat the Secret and client updates.
- If the StatefulSet does not become ready, inspect `kubectl describe pod` and container logs. Keep the existing PVC; do not delete or reinitialize it. Restore from the verified PostgreSQL logical dump only if database integrity is actually lost.
- If the laptop client fails after the rotation, compare its password-manager entry with the database rotation and update only the DSN password. Keep the Fernet key unchanged.
- If the laptop's pending file was copied or exposed, discard that value and repeat the procedure with a new password.

## Security notes

- The Postgres role currently has superuser privileges; use it only for Drisa memory operations. Reducing privileges is a separate migration requiring its own review.
- Kubernetes Secrets are encrypted at rest by this cluster configuration, but access to the Secret still grants the database credential.
- Never run `kubectl get secret ... -o yaml`, print the config JSON, or include a DSN/password in diagnostics.
- The deployment manifest's `initdb --pwfile` is for an empty database only. It does not rotate credentials in an existing data directory.
