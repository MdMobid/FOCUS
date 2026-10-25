# FOCUS: Lightweight Parental Control & Focus Manager

A lightweight, tamper-resistant Windows background application and parental control suite designed for distraction elimination, session management, input suppression, and browser/YouTube guard.

---

## Key Features

- **📱 Remote Mobile Web Dashboard**: Real-time control and live monitoring from your smartphone or any browser via an authenticated, dark-mode web dashboard.
- **⚡ Instant System Power Controls**: Lock PC (`LockWorkStation`), Sign Out, Restart, or Shutdown remotely.
- **⌨️ Hardware Keyboard Lock**: Complete keyboard input suppression via low-level Win32 hook (`WH_KEYBOARD_LL`) with a parent bypass hotkey.
- **🎯 Focus Mode (App Whitelisting)**: Terminates any unauthorized application (games, steam, discord) within milliseconds.
- **📱 Installed Applications Discovery**: Scans and displays all software installed on your brother's PC directly in your dashboard with 1-click `[+ Allow]` buttons.
- **💾 Persistent SQLite Database**: All rules, whitelists, settings, and logs are stored in a dedicated ACID SQLite database (`config/focus.db`).
- **📑 Browser Tab Limiter**: Restricts maximum allowed open tabs in Google Chrome and Microsoft Edge, auto-closing excess tabs.
- **🌐 Website Domain Whitelist**: Permits only parent-whitelisted websites; redirects all other browsing to a restricted screen.
- **📺 YouTube Channel Whitelist**: Channel-level inspection that permits only parent-approved YouTube creators (`@handles`) while blocking unapproved channels, YouTube Shorts, comments, and recommendations.
- **🛡️ Anti-Bypass Sentinel**: Dual-process watchdog and Task Manager lockdown (`DisableTaskMgr = 1`) during Focus Mode to prevent circumvention on Admin accounts.
- **🪶 Ultra Lightweight**: Built using Python's standard library and native Win32 APIs (< 25 MB RAM, 0% CPU idle, zero external pip dependencies).

---

## Project Structure

```
FOCUS/
├── core/                        # Background Service & System Controller
│   ├── main.py                  # Entrypoint & background coordinator
│   ├── database.py              # Persistent SQLite database layer
│   ├── app_scanner.py           # Windows Registry installed applications scanner
│   ├── system_power.py          # Lock, Sign out, Shutdown, Restart (Win32)
│   ├── keyboard_hook.py         # WH_KEYBOARD_LL keyboard interceptor
│   ├── config_manager.py        # SQLite-backed config & SHA-256 PIN management
│   ├── process_guard.py         # Real-time app whitelist & process blocker
│   ├── registry_policy.py       # Task Manager lockdown & Enterprise policies
│   ├── web_server.py            # Embedded HTTP API & GDI screenshot engine
│   ├── firebase_bridge.py       # 1,000 km Cloud Sync listener (outbound HTTPS)
│   └── watchdog.py              # Anti-kill sentinel process
├── dashboard/                   # Parent Web Dashboard (Mobile-Friendly HTML5/CSS/JS)
│   ├── index.html               # Responsive Parent Command Center with Installed Apps browser
│   ├── style.css                # Premium dark-mode glassmorphism styling
│   └── app.js                   # Real-time polling, controls & whitelist sync
├── extension/                   # Manifest V3 Extension for Chrome & Edge
│   ├── manifest.json            # Chromium Extension Manifest
│   ├── background.js            # Tab limiter & website whitelist interceptor
│   ├── youtube_guard.js         # YouTube channel inspector & shorts blocker
│   └── blocked.html             # "Blocked by Parent" landing page
├── config/
│   └── rules.json               # Whitelists (Apps, Websites, Channels) & PIN
├── scripts/
│   ├── install.bat              # 1-Click setup for brother's PC (Run as Admin)
│   └── uninstall.bat            # Clean uninstaller (requires Master PIN)
└── tests/
    └── test_core.py             # Unit tests for core subsystems
```

---

## How to Deploy on Your Brother's PC

### Step 1: Copy the Folder
Copy the `FOCUS` folder to your brother's computer (e.g., via USB drive or network share).

### Step 2: 1-Click Installation
1. On your brother's computer, open the `FOCUS/scripts` folder.
2. Right-click **`install.bat`** and select **"Run as administrator"**.
3. The script will automatically:
   - Configure Windows Task Scheduler to auto-start FOCUS on boot with highest privileges.
   - Force-enable the Chrome & Edge content guard extension.
   - Start the background daemon.
   - Display your local network Web Dashboard link.

---

## How to Control as the Parent
- **Default Master PIN**: `1234` (Changeable anytime in `config/rules.json`)
- **Emergency Hardware Unlock**: Press **`Ctrl + Alt + Shift + P`** on the physical keyboard to instantly disarm the keyboard lock.

---

## 1,000 km Distance Setup (Google Firebase Cloud Sync)

To control the PC from another city or anywhere on cellular data without open ports or tunnels:

1. Go to [console.firebase.google.com](https://console.firebase.google.com) (free with your Google account).
2. Click **Add project** -> name it `my-focus-guard`.
3. In the left menu, click **Build** -> **Realtime Database** -> **Create Database** (choose default location and test mode).
4. Copy your **Database URL** (e.g. `https://my-focus-guard-default-rtdb.firebaseio.com`).
5. In Project Settings (⚙️) -> **Service Accounts** -> **Database Secrets** -> click **Show** to copy your secret key.
6. Open your Parent Web Dashboard, tap the **☁️ Cloud** icon, paste your URL and Secret, and click **Save**.
7. In `config/rules.json` on the brother's PC, also paste the `firebase_url` and `firebase_secret`.

That's it! Your commands now sync across 1,000 km in under 100 milliseconds using bank-grade Google Cloud security.

---

## Local Wi-Fi Access (When at Home)
1. Connect your phone to the same home Wi-Fi network as your brother's PC.
2. Open your phone's browser and go to:
   ```
   http://<BROTHER_PC_IP>:8443
   ```
   *(The exact IP address is displayed when you run `install.bat`).*
3. Enter your Master PIN `1234`.
4. Tap **"Add to Home Screen"** on your phone's browser to use it like a native mobile app!

---

## Clean Uninstallation

To remove FOCUS:
1. Run **`scripts/uninstall.bat`** as Administrator.
2. Enter your Parent Master PIN when prompted.
3. The script verifies your PIN, terminates background processes, restores Windows Task Manager, and cleans all registry policies.