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
- WebSocket messages are capped at 8 MiB and decoded audio at 6 MiB. Audio must be valid base64 containing a RIFF/WAVE file with a matching declared length. Synchronous STT, LLM, and TTS calls run in worker threads so long inference does not block WebSocket keepalives.
- The Iku app authenticates before model management or replies. Add trusted `device_id` values to the runtime `allowlist` and configure their policies before enabling voice replies; the tracked defaults trust no devices.

The gateway records voice content in the configured Obsidian vault and recordings folder, matching the existing Drisa policy. Use the Iku app to inspect model catalogs and load models; do not place model API keys in Git.

## Gaming mode

Copy `drisa_mode.ps1`, `drisa_remote_config.ps1`, `drisa_watchdog.ps1`, and `register_drisa_watchdog.ps1` into `%USERPROFILE%\workspace\drisa`. Run `powershell -ExecutionPolicy Bypass -File $env:USERPROFILE\workspace\drisa\register_drisa_watchdog.ps1` once to start the gateway and selected voice listener at logon and check them every minute while signed in. The watchdog reads model settings and local API credentials from that runtime folder before launching processes, so a recovered gateway gets the same environment as the normal launcher. Run `drisa_mode.ps1 gaming` to stop local model serving and the 3D world while keeping the gateway and microphone listener available; gaming mode uses local Whisper.cpp, Windows Portuguese speech, and the private VPS LLM endpoint. Use `drisa_mode.ps1 normal` to restore local serving and the 3D world.
