# Iku Android

Native Android client for Iku services. The modern flavor includes Firebase sign-in, a private Iku Auth session link, encrypted token storage using Android Keystore, Tailscale Drisa voice access, model status and selection for the laptop/VPS, service shortcuts, files, and printer controls.

The **Início** screen reads live Nextcloud, n8n, and LFM3 health through the private Iku portal. It sends the short-lived Iku access token over HTTPS; connect the phone to Tailscale and link the Iku session in **Perfil** first. It does not query the old LAN Prometheus address.

## Build and install

Build the modern debug APK:

```powershell
.\gradlew.bat :app:assembleModernDebug
```

Install or update a connected device without removing its app data:

```powershell
adb install -r app\build\outputs\apk\modern\debug\app-modern-debug.apk
```

The debug APK is for private testing and is not signed for Play Store release. On MIUI, enable **Install via USB** and accept the device's install confirmation if prompted.

## Iku Auth and Drisa

Sign in with the existing Firebase account, connect the phone to the Iku Tailscale tailnet, then open **Perfil → Ligar sessão Iku** and complete the requested TOTP challenge. The app exchanges only verified Firebase identity for an Iku session; Firebase claims do not grant Iku roles. Access and rotating refresh tokens are encrypted with Android Keystore.

Open **Serviços → Falar com a Drisa** to enter the gateway token once. The app stores it encrypted with Android Keystore. The **Modelos da Drisa** controls show loaded models and allow choosing a model host (laptop or VPS) and category. Keep model and Drisa endpoints private to the tailnet.

The modern debug APK was installed on the Redmi on 2026-11-12; at that time its package hash matched the local build (`29E0892ABA3F6217E890C442C3EB9CE6A5173C5B0E49ED4AA08D9F124185E096`). After linking an active Iku session, Início displayed all three VPS services as available. On 2026-11-14, `:app:assembleModernDebug` succeeded and produced `app/build/outputs/apk/modern/debug/app-modern-debug.apk` (SHA-256 `565FC240FA1BE01A5F3469F0C75E74EE912D59AB8DC54FA1B5D55CEE72E5ECDA`). The Redmi was offline, so this build has not been installed or verified on-device. The laptop gateway token was rotated on 2026-11-12; replace the saved Drisa token from `%USERPROFILE%\workspace\drisa\gateway_token.txt` before using voice or model controls again.

The Iku Auth session bridge and Drisa controls are implemented; the Android client is still in private testing. User/device administration, release signing, and Play Store distribution are not complete.
