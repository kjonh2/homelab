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

On 2026-11-14, `:app:assembleModernDebug` succeeded and the APK was installed on the connected Redmi (SHA-256 `35CA81502DC94047CDE10A164B393CFF80A9A55D183B4865A2188FA78D020B29`). The Drisa screen now reports whether a gateway token is stored encrypted without displaying the value. Tapping Connect authenticated to the laptop gateway, refreshed the model catalog, and showed `lfm3-uncensored` loaded and active on the VPS. The full microphone-to-response playback on the phone remains untested. Relaunching the app also showed that its Iku portal session had expired; renew it under **Perfil → Ligar sessão Iku** to restore private portal status.

The Iku Auth session bridge and Drisa controls are implemented; the Android client is still in private testing. User/device administration, release signing, and Play Store distribution are not complete.
