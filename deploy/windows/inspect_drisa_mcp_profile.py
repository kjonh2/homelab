"""Validate and print the restricted, read-only Docker MCP profile allowlist."""
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SAFE_TOOLS_WITHOUT_ANNOTATIONS = {
    "obsidian": {
        "obsidian_batch_get_file_contents",
        "obsidian_complex_search",
        "obsidian_get_file_contents",
        "obsidian_get_periodic_note",
        "obsidian_get_recent_changes",
        "obsidian_get_recent_periodic_notes",
        "obsidian_list_files_in_dir",
        "obsidian_list_files_in_vault",
        "obsidian_simple_search",
    },
    "youtube_transcript": {
        "get_available_languages",
        "get_timed_transcript",
        "get_transcript",
        "get_video_info",
    },
}

if len(sys.argv) > 1 and sys.argv[1] != "drisa":
    raise SystemExit("Only the restricted 'drisa' profile is supported by this verifier.")

with tempfile.TemporaryDirectory(prefix="drisa-mcp-") as directory:
    path = Path(directory) / "profile.yaml"
    profile_id = "drisa"
    subprocess.run(["docker", "mcp", "profile", "export", profile_id, str(path)], check=True,
                   stdout=subprocess.DEVNULL)
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))

seen_servers = set()
for server in profile.get("servers", []):
    data = server.get("snapshot", {}).get("server", {})
    name = data.get("name", "unknown")
    allowed = set(server.get("tools", []))
    if not allowed:
        raise SystemExit(f"Server {name!r} has no tools in its active allowlist.")

    definitions = {tool["name"]: tool for tool in data.get("tools", []) if "name" in tool}
    if name == "github-official":
        unsafe = sorted(
            tool_name for tool_name in allowed
            if tool_name not in definitions
            or not (definitions[tool_name].get("annotations", {}) or {}).get("readOnlyHint")
            or (definitions[tool_name].get("annotations", {}) or {}).get("destructiveHint")
        )
    else:
        safe_names = SAFE_TOOLS_WITHOUT_ANNOTATIONS.get(name, set())
        unsafe = sorted(allowed - safe_names)

    if unsafe:
        raise SystemExit(f"Profile {profile_id!r} has unapproved tools for {name!r}: {', '.join(unsafe)}")
    seen_servers.add(name)
    print(name)
    for tool_name in sorted(allowed):
        print("  " + tool_name)

if seen_servers != set(SAFE_TOOLS_WITHOUT_ANNOTATIONS) | {"github-official"}:
    missing = sorted((set(SAFE_TOOLS_WITHOUT_ANNOTATIONS) | {"github-official"}) - seen_servers)
    raise SystemExit(f"Profile {profile_id!r} is missing expected read-only servers: {', '.join(missing)}")
