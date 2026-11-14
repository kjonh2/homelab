# Drisa audio service and laptop Gaming mode

Last checked: 2026-11-14. Audio service and laptop loopback routing are reachable. The Redmi is offline on Tailscale and not connected over ADB, so physical phone validation remains pending.

## Intended layout

- The VPS remains the K3s control plane and serves the LFM text model, PostgreSQL conversation memory, Iku portal, Nextcloud, and n8n.
- The `homelab` worker runs a private `audio.cpp` service for MOSS transcription, Parakeet fallback, and Kokoro speech generation. Its PVC uses the homelab node's local-path storage; it is not replicated to the VPS.
- Up to two audio models can be loaded at once on the J3710 worker so Parakeet can run as fallback while MOSS is still busy. The pod limit is 4 GiB; the observed MOSS+Parakeet working set was about 3.4 GiB and CPU use approached the node's 4 vCPU limit.
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

- The gateway catalog returned `moss` as selected STT, `parakeet` as fallback, and `kokoro` as selected TTS. Both the app gateway and Gaming-mode voice loop now load each homelab model before inference. MOSS has a 30-second transcription deadline; on timeout the path loads and tries Parakeet.
- On a Portuguese 1.45-second WAV, MOSS loaded but did not return within five minutes. Parakeet transcribed “Sistema pronto.” in 4.6 seconds. The gateway's real MOSS-to-Parakeet fallback returned the same transcript in 81 seconds on its first cold run. Future runs should be faster while both models remain loaded, but CPU is near saturation.
- LFM on the VPS returned “Sistema pronto.” in 9.7 seconds. The LFM-plus-Kokoro gateway call completed in 54.5 seconds on the cold run; Kokoro audio was produced and the WAV was played locally.
- The app's model catalog and load handlers were unit tested, but the Redmi was not connected for UI or full microphone validation. Do not treat the Android conversation path as verified until a physical-device test passes.
- This service is private and ClusterIP-only. Do not open port 8080 or add a public ingress.

At the 2026-11-14 live check, laptop `127.0.0.1:8766/health` and `/v1/models` returned HTTP 200 through the SSH forward; `127.0.0.1:8765` is the authenticated WebSocket gateway and returns HTTP 426 to a plain HTTP health probe. The audio API reported MOSS, Parakeet, and Kokoro configured, with Kokoro loaded and both transcription models unloaded. The homelab node was at 40% memory and the audio pod used 700 MiB; `max_loaded_models: 2` is intentional so lazy loading can switch ASR/TTS models without retaining all three on this small worker. Gaming mode is available but inactive (`drisa_mode.txt` is absent), so the laptop is in normal mode. This check confirms listener/tunnel reachability and model catalog state, not microphone-to-response behavior.

A read-only catalog check through the laptop gateway code on 2026-11-14 returned model choices for all configured hosts: the PC lists `AtomicChat/LFM3-1.7B-Uncensored-GGUF` and the MOSS/Parakeet transcription packages; the VPS lists `lfm3-omni`, `lfm3-text`, and `lfm3-uncensored`; the homelab lists `moss`, `parakeet`, and `kokoro`. At that check, `lfm3-uncensored` was loaded on the VPS and Kokoro was loaded on both the PC and homelab; the other listed models were available but unloaded. The PC LLM selection is intentionally empty while the saved text host is the VPS. These results show that catalog data reaches the gateway; they do not verify the Android picker or a physical-device model load.
