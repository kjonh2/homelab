"""Copy only the current Drisa PostgreSQL password into the backup namespace."""
import base64
import json
import os
import subprocess
from pathlib import Path

home = Path(os.environ.get("DRISA_HOME", Path.home() / "workspace" / "drisa"))
config = json.loads((home / "drisa_memory_config.json").read_text(encoding="utf-8"))
parts = dict(item.split("=", 1) for item in config["dsn"].split() if "=" in item)
password = parts["password"]
secret = {
    "apiVersion": "v1", "kind": "Secret",
    "metadata": {"name": "drisa-memory-backup-credentials", "namespace": "iku-backup"},
    "type": "Opaque",
    "data": {"password": base64.b64encode(password.encode()).decode()},
}
result = subprocess.run(
    ["tailscale", "ssh", "ubuntu@vps-4e5174e4", "sudo", "k3s", "kubectl", "apply", "-f", "-"],
    input=json.dumps(secret).encode("utf-8"), capture_output=True, check=True,
)
print(result.stdout.decode("utf-8", errors="replace").strip())
