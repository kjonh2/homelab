# I Know You - Android

A custom Android application designed to bridge intelligence and hardware control. This project is part of a larger ecosystem aimed at creating a seamless, cross-device experience for monitoring and automation.

## 🚀 Current Status & Timeline

### **Timeline:**
- ✅ **Resolved NDK Compatibility** (Done)
  - Updated `minSdk` to 21 to align with modern NDK requirements (v28).
  - Fixed `[CXX1110]` platform version error.
- ✅ **Goal Integration** (Done)
  - Connected the project to the **Hermes Kanban** system for automated task tracking.
  - Initialized repository structure for remote deployment.

### **In Development:**
- 🔨 **OS Upgrade**
  - Researching and testing Android 5.0+ custom ROMs for the tablet to support modern libraries.
- 🔨 **3D Printer Control Interface**
  - Preparing the integration with **Geeetech i3 Pro W**.
  - Developing the "Mini PC" mode for the tablet controller.

### **Next in the Timeline:**
- 📅 **Dual-Device Deployment:** Enable simultaneous "Run" from Android Studio to both the tablet and development phone.
- 📅 **Cloud Sync:** Integrate with the Gemini-CLI-UI for remote project management.
- 📅 **Auto-Updates:** Set up CI/CD pipeline for automatic deployment via Vercel/Local Lab.

## 🛠 Features
- **Native Hardware Integration:** Direct communication with 3D printer firmware.
- **Hermes Agent Support:** Automated workflows via the Hermes AI agent.
- **Cross-Device Performance:** Optimized for both high-end mobile devices and legacy hardware.

## 📜 Future Steps & Suggestions
1. **Unified Dashboard:** Centralize 3D printer status and Android logs in the web UI.
2. **Predictive Maintenance:** Use local AI models to predict printer failures or filament runs.
3. **Remote Wake-on-LAN:** Allow the tablet to wake up the local lab server for processing tasks.

## ❓ Troubleshooting

### **`INSTALL_FAILED_USER_RESTRICTED`**
If you see this error when running `./gradlew installOnAll`, it means your device (likely your phone) is blocking the installation for security reasons.
- **Solution:** Keep your phone screen on and look for a popup that asks to **"Install via USB"**. You must tap **"Install"** or **"Allow"** manually.

### **Skipped Devices (API < 21)**
The `installOnAll` task will automatically skip any device running an Android version older than **5.0 (Lollipop)**.
- **Solution:** Upgrade the device OS or use a different device that meets the `minSdk` requirement.

---
*Developed with assistance from Gemini CLI and Hermes.*
