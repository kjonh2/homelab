# Drisa audio service and laptop Gaming mode

Last checked: 2026-11-15. The Redmi is connected over USB ADB and Drisa is in the foreground. The installed app is still version 1.01.0; the newer diagnostic APK has not been installed because MIUI rejected the ADB update. The phone's WSS authentication was verified earlier, but a fresh microphone-to-response test is still outstanding.

## Intended layout

- The VPS remains the K3s control plane and serves the LFM text model, PostgreSQL conversation memory, Iku portal, Nextcloud, and n8n.
- The `homelab` worker runs a private `audio.cpp` service for MOSS transcription, Parakeet fallback, and Kokoro speech generation. Its PVC uses the homelab node's local-path storage; it is not replicated to the VPS.
- Only one audio model is kept loaded at a time on the J3710 worker. This follows an OOM kill during concurrent model residency; the pod has a 4 GiB limit and the observed MOSS+Parakeet working set previously approached it.
- The laptop's Drisa gateway sends LLM prompts to the selected text-model host. Its STT and TTS URLs are configured separately, so transcribed text goes to LFM and spoken output goes to Kokoro.
- The laptop reaches the cluster audio Service through an SSH local forward bound to `127.0.0.1:8766`. The Kubernetes Service is ClusterIP-only; neither model API nor its model-management endpoint is published to the Internet or LAN.
- The API-only server enables dynamic model loading so Iku can load a selected installed package. Its WebUI stays disabled. The gateway only allows the three installed package IDs; Kubernetes ingress policy restricts the service to the homelab host-side path used by the SSH forward.
- Kokoro needs the eSpeak-ng runtime library and voice data. A non-root init container extracts Ubuntu's signed `libespeak-ng1`, `libpcaudio0`, `libsonic0`, and `espeak-ng-data` packages into the service PVC. The model server reads them from that PVC.

## Laptop Gaming mode

The watchdog reads `drisa_mode.txt`. In Gaming mode it stops the laptop's local model server and the Drisa 3D world, keeps the authenticated gateway and microphone listener available, and routes MOSS/Parakeet/Kokoro requests through the homelab tunnel. LFM remains on the selected text host (currently the VPS). Returning to normal mode restores the normal voice listener and leaves the local model server alone.

This is an audio-serving fallback, not a full VPS outage plan. If the VPS LFM endpoint is offline, the conversation cannot produce an LLM reply unless a separate LLM fallback is configured. If the homelab is offline, remote STT/TTS is unavailable; Gaming mode deliberately does not turn on local model serving.

## Check the deployed service

From the VPS over Tailscale:

```bash
sudo k3s kubectl -n iku get deploy,pods,svc,pvc -l app.kubernetes.io/name=drisa-audio -o wide
sudo k3s kubectl -n iku logs deploy/drisa-audio -c server --tail=100
```

From the laptop, confirm the local forward is loopback-only, then check the API:

```powershell
Get-NetTCPConnection -State Listen -LocalAddress 127.0.0.1 -LocalPort 8766
Invoke-RestMethod http://127.0.0.1:8766/health
Invoke-RestMethod http://127.0.0.1:8766/v1/models
```

`/health` confirms the server is ready but does not prove a model has loaded. `/v1/models` reports the API IDs `moss`, `parakeet`, and `kokoro`. Keep these IDs in the app and gateway; the package names are only used for model installation/loading.

## Validation results and limits

- The gateway catalog returned `moss` as selected STT, `parakeet` as fallback, and `kokoro` as selected TTS. The app gateway and Gaming-mode voice loop load a selected homelab model before inference. MOSS has a 180-second inference timeout. Parakeet fallback is suppressed when a timeout, connection loss, or HTTP 503 leaves the first inference potentially active; definitive empty or failed responses can still fall back.
- Historical cold-run measurements before the one-model memory limit: on a Portuguese 1.45-second WAV, MOSS did not return within five minutes; Parakeet transcribed “Sistema pronto.” in 4.6 seconds, and the MOSS-to-Parakeet gateway fallback took 81 seconds. Do not use these runs as current latency guarantees.
- LFM on the VPS returned “Sistema pronto.” in 9.7 seconds. The LFM-plus-Kokoro gateway call completed in 54.5 seconds on the cold run; Kokoro audio was produced and the WAV was played locally.
- Earlier catalog/load-handler checks did not include the Redmi UI or microphone. The current on-device check is recorded below; a real microphone utterance remains outstanding.
- This service is private and ClusterIP-only. Do not open port 8080 or add a public ingress.

At the 2026-11-14 live check, laptop `127.0.0.1:8766/health` and `/v1/models` returned HTTP 200 through the SSH forward; `127.0.0.1:8765` is the authenticated WebSocket gateway and returns HTTP 426 to a plain HTTP health probe. The audio API reported MOSS, Parakeet, and Kokoro configured, with Kokoro loaded and both transcription models unloaded. Those memory values predate the OOM fix. The current manifest sets `max_loaded_models: 1` and `busy_timeout_ms: 120000`. Gaming mode is available but inactive (`drisa_mode.txt` is absent), so the laptop is in normal mode. These checks confirm listener/tunnel reachability and model catalog state, not microphone-to-response behavior.

After the VAD/wake-word fix on 2026-11-14, the laptop listener was restarted. Its log confirms Vosk startup and bounded 15-second audio chunks reaching the local wake-word check; a real wake-word hit and response are still unverified. The old 60-second drop behavior is no longer present in the deployed listener.

On 2026-11-15, repeated PortAudio input overflows were traced to file I/O and VAD work running inside the microphone callback. Capture now copies frames into a bounded queue and performs VAD, bridge meter writes, and logging on the consumer thread. This change is deployed on the laptop; the bridge meter continued updating and the restarted listener initialized successfully. The Android app has `RECORD_AUDIO` permission, but Android reported no active recording in this check. Microphone-to-response behavior on either client still needs a spoken test.

A read-only catalog check through the laptop gateway code on 2026-11-14 returned model choices for all configured hosts: the PC lists `AtomicChat/LFM3-1.7B-Uncensored-GGUF` and the MOSS/Parakeet transcription packages; the VPS lists `lfm3-omni`, `lfm3-text`, and `lfm3-uncensored`; the homelab lists `moss`, `parakeet`, and `kokoro`. At that check, `lfm3-uncensored` was loaded on the VPS and Kokoro was loaded on both the PC and homelab; the other listed models were available but unloaded. The PC LLM selection is intentionally empty while the saved text host is the VPS.

On-device verification later on 2026-11-14: the app renewed its Iku session and authenticated to the laptop gateway over WSS using its saved token. The home screen showed LFM3, n8n, and Nextcloud available after the portal-to-Nextcloud health probe was allowed by NetworkPolicy. The model picker listed Portátil, VPS, and Homelab; the VPS offered LFM3 Omni, text, and uncensored, with uncensored loaded. The Homelab reported MOSS loaded and active for transcription and Kokoro loaded for TTS. The saved gateway config selects VPS `lfm3-uncensored`, Homelab MOSS with Parakeet as fallback, and laptop Kokoro. A static “Sistema pronto” response was synthesized through the configured Kokoro route and played on the laptop. The real phone microphone-to-Drisa-response path has not been exercised, so do not treat the WSS handshake and catalog checks as proof of a complete voice conversation.

Current Redmi recheck: USB ADB detects the phone and the Drisa screen is open. Tailscale Serve on the laptop is active at `https://iknowu.tail2931da.ts.net`, and the phone's configured WSS URL uses that hostname. The field stays visually empty for a saved credential; the new UI status explicitly confirmed the token is stored encrypted. Tapping Connect produced **“Ligada e autenticada”** and refreshed the model catalog; the VPS reported `lfm3-uncensored` loaded and active for Drisa. No token was read from or copied to the screen during this check. The MIUI `uiautomator` dump failed, so the screen was inspected using screenshots instead. A real microphone utterance and phone playback remain unverified. The Iku home screen separately reports its portal session expired; renew the Iku session in Perfil before using private portal status.

Revalidation on 2026-11-15: the laptop config selects Homelab MOSS with Parakeet fallback for STT, VPS `lfm3-uncensored` for LLM, and PC Kokoro for TTS. PC `/v1/models` reported Kokoro loaded; the Homelab catalog listed MOSS, Parakeet, and Kokoro as available but unloaded before a new request. The audio API health endpoint returned HTTP 200. The diagnostic Android APK built locally, but `adb install -r` was rejected with `INSTALL_FAILED_USER_RESTRICTED`; the phone remains on 1.01.0. Its Drisa screen is in the foreground and `RECORD_AUDIO` is granted. At the latest check, Android AppOps showed no recent recording (last use was over five hours earlier), so it does not verify the user's current voice test. The newer button text and diagnostic error details are not available until that APK is installed. The existing Kokoro “Sistema pronto” WAV was played locally; the laptop-to-phone microphone and reply path still needs a verified spoken exchange.

Live check at 2026-11-15 02:48 Europe/Paris: the phone remained on app version 1.01.0 with Drisa foregrounded. Android `RECORD_AUDIO` permission was granted, but AppOps recorded the last microphone use more than five hours earlier. The laptop gateway returned HTTP 426 to a plain HTTP probe (expected for its WebSocket endpoint); the homelab audio API `/health` returned `status=ok`, and `/v1/models` showed Parakeet loaded while MOSS and Kokoro were unloaded. This confirms service reachability only. It does not prove the configured MOSS-first Android conversation or audio playback; check model loading and the phone's next spoken exchange when the user reports the result.

Live WSS model-catalog verification later on 2026-11-15: the laptop gateway now reads its model inventory from Unsloth's native APIs rather than Docker MCP, whose local resolver is degraded. Authenticated WSS catalog requests returned 13 installed PC text models (including local LFM3 and Omni), one PC TTS model (Kokoro, loaded), three VPS LFM3 models (uncensored loaded), two homelab STT models (MOSS selected; Parakeet loaded), and homelab Kokoro (available, unloaded). This verifies the gateway protocol and model state sent to the Android UI; the phone has not yet been refreshed on-screen, and this is not a microphone/playback test. PC LLM loading uses `/api/inference/load`; PC TTS loading performs a short discarded speech request because Unsloth exposes no standalone TTS-load route.

Laptop mode recheck on 2026-11-14: `drisa_mode.txt` is absent, so the laptop is in normal mode; the `Drisa Watchdog` task is Running. The gateway (`127.0.0.1:8765`) and Gaming-mode audio SSH forward (`127.0.0.1:8766`) are listening. Unsloth listens on TCP/8888 across loopback, LAN, and Tailscale interface addresses, but the enabled inbound Windows Firewall block covers RFC1918, link-local, and Tailscale IPv4/IPv6 ranges. A local TCP connect to `127.0.0.1:8888` succeeded; a connect from the VPS over Tailscale to the laptop Tailscale address timed out, consistent with the inbound block. Loopback remains available for the local gateway. Do not remove the rule just because Unsloth continues to bind non-loopback interfaces.

## Watchdog and intermittent console windows

The `\Drisa Watchdog` Task Scheduler task runs at user logon and repeats every minute. Its `wscript.exe //B` action calls `drisa_watchdog_hidden.vbs`, which launches the PowerShell watchdog with `-WindowStyle Hidden`; the watchdog also starts the gateway, voice listener, and SSH audio forward with hidden windows. The task checks that these listeners are alive and restarts them if needed, so keep it enabled for the laptop's always-on Drisa role. On 2026-11-14, process-start monitoring confirmed the task's WScript launch and a 65-second visible-window check saw no new visible console window. This identifies the recurring watchdog process but does not prove it caused the previously reported visible prompt; capture the owning process if that prompt appears again before changing the task.
