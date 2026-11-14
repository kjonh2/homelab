"""Provision the local Drisa memory credentials and bootstrap the VPS Secret."""
from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
from pathlib import Path


def main() -> None:
    home = Path(os.environ.get("DRISA_HOME", Path.home() / "workspace" / "drisa"))
    home.mkdir(parents=True, exist_ok=True)
    password = secrets.token_urlsafe(36)
    secret = {
        "apiVersion": "v1", "kind": "Secret",
        "metadata": {"name": "drisa-memory-postgres", "namespace": "iku"},
        "type": "Opaque",
        "data": {"password": base64.b64encode(password.encode()).decode()},
    }
    proc = subprocess.run(
        ["tailscale", "ssh", "ubuntu@vps-4e5174e4", "sudo", "k3s", "kubectl", "apply", "-f", "-"],
        input=json.dumps(secret).encode("utf-8"), capture_output=True, check=True,
    )
    print(proc.stdout.decode("utf-8", errors="replace").strip())
    dsn = (f"host=100.67.97.92 port=5432 dbname=drisa_memory user=drisa_memory "
           f"password={password} sslmode=disable connect_timeout=3")
    config_path = home / "drisa_memory_config.json"
    config_path.write_text(json.dumps({"dsn": dsn, "conversation_id": "kiko-main"}, indent=2), encoding="utf-8")
    key_path = home / "drisa_memory_fernet.key"
    from cryptography.fernet import Fernet
    key_path.write_bytes(Fernet.generate_key())
    if os.name == "nt":
        for path in (config_path, key_path):
            subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print("Local PostgreSQL DSN and Fernet key created with user-only ACL.")


if __name__ == "__main__":
    main()
