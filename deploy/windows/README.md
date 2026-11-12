# Drisa Windows voice gateway

The Windows voice gateway that connects the Iku Android app to Drisa is tracked here. Runtime configuration, recordings, tokens, API keys, and local model state stay outside Git in `%USERPROFILE%\workspace\drisa` by default.

## Install or update

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r deploy\windows\requirements-drisa-gateway.txt
$env:DRISA_HOME = "$env:USERPROFILE\workspace\drisa"
Copy-Item -Force deploy\windows\drisa_voice_gateway.py "$env:DRISA_HOME\drisa_voice_gateway.py"
& "$env:DRISA_HOME\venv\Scripts\python.exe" "$env:DRISA_HOME\drisa_voice_gateway.py"
```

The existing startup launcher may run the gateway instead of the final command. Do not start a second instance while port 8765 is in use.

## Paths and network

- `DRISA_HOME` selects the runtime folder. It contains `gateway_config.json` and local credentials such as `gateway_token.txt`, `iku_lfm3.key`, and `unsloth.key`; never commit these files.
- `DRISA_VAULT_PATH` overrides the Obsidian voice-log folder.
- `DRISA_WHISPER_EXE` and `DRISA_WHISPER_MODEL` override the optional local Whisper fallback.
- The gateway listens on `127.0.0.1:8765`; Tailscale Serve forwards the tailnet-only HTTPS name to loopback. It is not exposed on LAN interfaces.
- The Iku app authenticates before model management or replies. Add trusted `device_id` values to the runtime `allowlist` and configure their policies before enabling voice replies; the tracked defaults trust no devices.

The gateway records voice content in the configured Obsidian vault and recordings folder, matching the existing Drisa policy. Use the Iku app to inspect model catalogs and load models; do not place model API keys in Git.
