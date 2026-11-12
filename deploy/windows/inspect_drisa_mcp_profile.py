"""Print only read-only tool names from the restricted Docker MCP profile."""
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

with tempfile.TemporaryDirectory(prefix="drisa-mcp-") as directory:
    path = Path(directory) / "profile.yaml"
    profile_id = sys.argv[1] if len(sys.argv) > 1 else "drisa"
    subprocess.run(["docker", "mcp", "profile", "export", profile_id, str(path)], check=True,
                   stdout=subprocess.DEVNULL)
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
for server in profile.get("servers", []):
    data = server.get("snapshot", {}).get("server", {})
    print(data.get("name", "unknown"))
    for tool in data.get("tools", []):
        annotation = tool.get("annotations", {}) or {}
        if annotation.get("readOnlyHint") and not annotation.get("destructiveHint"):
            print("  " + tool["name"])
