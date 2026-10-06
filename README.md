# 🛡️ Discord Settings Saver & Restorer

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](https://microsoft.com/windows)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-Electron%20LevelDB-5865F2.svg)](https://discord.com)

A standalone Windows utility built to back up, protect, and restore your Discord settings after disk errors, blue screens (BSOD), hard crashes, or corrupted resets.

---

## ⚡ The Problem: Why Does Discord Reset?

Discord is built on Electron/Chromium and stores its local configuration (voice settings, input/output devices, individual per-user volume levels, Krisp toggles, themes, hotkeys, and appearance) in a **LevelDB** database under:
```
%APPDATA%\discord\Local Storage\leveldb
```

When a Windows disk error, sudden power loss, or crash occurs:
1. LevelDB's write-ahead log (WAL) or SSTable becomes uncommitted or flags a write cache flush error.
2. Upon next launch, Chromium detects an uncommitted LevelDB transaction and applies its default recovery strategy: **it wipes the database and recreates a blank one**.
3. All your voice settings, noise suppression toggles, per-user volumes, keybinds, and display preferences are **instantly reset back to zero**.

---

## ✨ Features

- **💾 1-Click Backup & Restore**: Save all Discord preferences into a portable, human-readable snapshot and restore it in seconds.
- **🔒 Zero-Login Touch (Credentials Protected)**:
  - Authentication tokens (`token`, `tokens`, `user_id_cache`, `MultiAccountStore`) are **actively stripped from backup files**.
  - When restoring, whatever login session is currently active in Discord is **100% preserved**. You will never be logged out.
- **🔇 Permanent Rule: ALWAYS Disable Krisp**:
  - Automatically forces `vadUseKrisp: false` in `MediaEngineStore` so Discord will never default Krisp noise cancellation back on after resets.
- **🎙️ Full Voice & Audio Settings Restored**:
  - Voice input mode (Push-to-Talk vs Voice Activity) and threshold
  - Selected input & output audio devices
  - Input/output volume sliders & individual per-user volume levels (including 200% boosted volumes)
  - Echo cancellation, noise suppression, automatic gain control
  - Audio subsystem preferences (`experimental`, `standard`, `legacy`)
- **🎨 Appearance, Keybinds & Layout**:
  - Custom font scaling, zoom level, compact/cozy modes
  - Themes (`midnight`, `dark`, `light`)
  - Push-to-Talk hotkeys, mute/deafen keybinds, in-game overlay settings, and window bounds
- **🛡️ Automatic Safety Rollback**: Automatically creates a rollback point in `backups/safety_pre_restore_*` prior to every restore.
- **⚡ Pure Python LevelDB Engine**: Includes a pure-Python LevelDB reader and writer with custom Snappy decompressor and CRC32C checksums—**no Visual Studio C++ compilers or external native binaries required**.

---

## 🚀 Quick Start

### 1. Download & Installation

Clone the repository or download the ZIP from GitHub:

```bash
git clone https://github.com/BlackwellArchitecture/Discord-Settings-Saver.git
cd Discord-Settings-Saver
```

### 2. Launch (GUI)

Double-click **`DiscordSettingsSaver.bat`** in the folder.
- The launcher will verify Python 3 and automatically install required GUI dependencies (`customtkinter`, `darkdetect`) if missing.
- **To Save Settings**: Click **"💾 Save Discord Settings Now"**.
- **To Restore Settings**: When Discord wipes out after a crash, open the app and click **"⚡ Restore Saved Settings"**. Discord will be closed, your settings restored, active login preserved, and Discord relaunched automatically.

---

## 🖥️ Command Line (CLI) Usage

For automated scripts, task scheduler jobs, or headless setups:

```powershell
# Save current Discord settings to latest_backup.json and backups/
py main.py save

# Restore latest saved settings
py main.py restore

# List all available backups
py main.py list

# Check Discord status and paths
py main.py status

# Restore a specific backup file without restarting Discord
py main.py restore --file "backups\discord_settings_2026-10-06_14-22-35.json" --no-relaunch
```

---

## 📂 Project Architecture

```
Discord-Settings-Saver/
│
├── DiscordSettingsSaver.bat # 1-click Windows batch launcher
├── main.py                  # Main entry point (auto-detects GUI vs CLI)
├── discord_saver_gui.py     # Modern CustomTkinter dark-mode GUI
├── discord_saver_cli.py     # Command-line interface with subcommands
├── settings_manager.py      # Core manager for filtering, backup, restore & rules
├── leveldb_engine.py        # Pure-Python LevelDB SSTable/WAL parser & builder
├── requirements.txt         # GUI dependencies (customtkinter, darkdetect)
├── LICENSE                  # MIT License
└── README.md                # Documentation
```

---

## 🔒 Security & Privacy

1. **No Token Harvesting**: The app explicitly skips all authentication tokens, session identifiers, and account secrets during export.
2. **Local Only**: Runs 100% offline on your local machine. No analytics, network requests, or telemetry.
3. **Open Source**: Every line of code is available for audit in this repository.

---

## 📜 License

Released under the [MIT License](LICENSE). Feel free to use, modify, and distribute.
