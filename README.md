# 🍎 Clean Mac

> A comprehensive macOS system cleanup tool — simple, safe, and effective.

[![ShellCheck](https://img.shields.io/badge/ShellCheck-passing-brightgreen)](https://www.shellcheck.net/)
[![macOS](https://img.shields.io/badge/macOS-Ventura%20%7C%20Sonoma%20%7C%20Sequoia-blue)](https://www.apple.com/macos/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

Clean Mac safely removes unnecessary data on macOS such as caches, logs, temporary files, leftover application data, and Trash contents. It can be used from an interactive terminal interface or a lightweight web dashboard.

---

## ✨ Features

- 🔍 Scans first and asks for confirmation — no surprises
- 📊 Flexible cleanup across **17 categories**
- 🧑‍💻 Deep **developer cleanup** — 40+ caches: Xcode/simulators, Homebrew, npm/pnpm/yarn/bun/deno, pip/uv/poetry/conda, Go, Rust Cargo, Gradle/Maven/SBT/Bazel, CocoaPods/Carthage, Composer, Flutter, JetBrains, Playwright/Puppeteer/Prisma, HuggingFace, and more — each with a plain-language description of what it is and how it rebuilds, plus a per-project breakdown of Xcode DerivedData (e.g. *MyApp: 2.3 GB, ClientSDK: 1.1 GB*)
- 🗑️ **App Uninstaller** — remove apps and their leftovers, with Homebrew-cask awareness, from the dashboard
- 🧱 **Project Artifact Scanner** — finds stale `node_modules`/`target`/`.build`/`build`/`vendor`/`.dart_tool`/`.terraform` next to a project manifest in your code folders; stale (>30 days) ones are pre-selected
- 📈 **Storage forecast** — records disk-usage history and predicts when your disk will fill (least-squares trend over the last 90 days)
- 🌐 Lightweight web dashboard (start with a single command), animated with **GSAP** (vendored locally — no CDN/network), with reduced-motion support and full graceful fallback if scripts fail to load
- 🛡️ Avoids touching critical system files by default
- 🍎 Compatible with Bash 3.2+ (works on all macOS releases)

---

## 🚀 Installation

```bash
git clone https://github.com/<username>/apple-cleanup.git
cd apple-cleanup
chmod +x clean_mac.sh
```

---

## 📖 Usage

### Terminal (interactive)

```bash
# Run interactive cleanup (scans first, then prompts)
bash clean_mac.sh

# Show help
bash clean_mac.sh --help
```

### Web Dashboard

```bash
python3 web/server.py
# Open your browser at http://localhost:8080
```

---

## 📦 Cleanup Categories

The script targets a wide array of system and user items, categorized by safety levels:

| # | Category | Target / Description | Notes |
|---|----------|----------------------|-------|
| 1 | 📦 User Caches | `~/Library/Caches/*` | Safe |
| 2 | 🖥️ System Caches | `/Library/Caches/*` | requires `sudo` |
| 3 | 📂 App Leftovers | `~/Library/Application Support/` | interactive selection |
| 4 | 📋 Logs | `~/Library/Logs/*`, `/Library/Logs/*` | Safe |
| 5 | 🗃️ Temporary Files | `$TMPDIR`, user var/folders | Safe |
| 6 | 🛠️ Developer | Xcode DerivedData | interactive selection |
| 7 | 🗑️ Trash | `~/.Trash/*` | Safe |
| 8 | 🌐 Browser Cache | `~/Library/Caches` for Safari, Chrome, etc. | Safe |
| 9 | ⚠️ Browser Full Data | Complete browser profiles (cookies, history) | **Danger** (requires opt-in) |
| 10| 📱 iOS Backups | `~/Library/MobileSync/Backup` | interactive selection |
| 11| 🗑️ App Uninstaller | Remove apps & associated leftover files | interactive selection |
| 12| 📨 Mail Downloads | Mail attachment downloads cache | Safe |
| 13| 🩺 Diagnostic Reports| `~/Library/Logs/DiagnosticReports` | Safe |
| 14| 🖼️ QuickLook Cache | `qlmanage` thumbnail cache | Safe |
| 15| 💾 Saved App State | `~/Library/Saved Application State` | Caution |
| 16| 💽 Other Trashes | `/Volumes/*/.Trashes` | Safe |
| 17| 🧱 Project Artifacts | Stale `node_modules`, `target`, `.build`, `build`, `vendor`, `.dart_tool`, `.terraform` in code folders | interactive selection |

---

## 🏗️ Project Structure

```
apple-cleanup/
├── clean_mac.sh        # Main cleanup script
├── web/
│   ├── server.py       # Python web server for the dashboard
│   ├── index.html      # Dashboard UI
│   ├── style.css       # Styles
│   └── script.js       # Frontend logic
├── README.md
├── LICENSE
└── .gitignore
```

---

## 🔧 Web API

The web dashboard invokes `clean_mac.sh` in JSON mode for programmatic control:

```bash
# Get scan results
bash clean_mac.sh --scan-json

# Clean specific categories (comma-separated indices)
bash clean_mac.sh --clean-json 1,4,7

# Get system status
bash clean_mac.sh --status-json
```

The dashboard also exposes two HTTP endpoints used by the **App Uninstaller**
tab (loopback + session-token protected, like every other write endpoint):

- `GET /api/apps` — enumerate installed apps (`/Applications`, `~/Applications`)
  and Homebrew casks, with sizes and bundle IDs.
- `POST /api/uninstall` — remove an app and its leftovers and/or run
  `brew uninstall`. App and Homebrew names are validated before use.
- `GET /api/forecast` — records a disk-usage snapshot (max once/hour, 90-day
  retention in `~/.cache/apple-cleanup/`) and returns a least-squares estimate
  of days until the disk is full, plus the daily growth rate.

---

## ⚠️ Safety Notes

- The script only removes caches, logs, and temporary files by default.
- macOS will recreate many of these files as needed.
- The `Downloads` folder is not touched.
- System Cache cleanup requires `sudo` (terminal mode).
- The web dashboard skips categories that require `sudo` unless explicitly enabled.
- **Dry-run preview:** set `APPLE_CLEANUP_DRYRUN=1` (or tick *Önizleme* in the
  dashboard) to see exactly what would be removed — nothing is deleted.
- **Exclusion list:** set `APPLE_CLEANUP_EXCLUDE` to a colon-separated list of
  paths/globs to protect from deletion, e.g.
  `APPLE_CLEANUP_EXCLUDE="$HOME/Library/Caches/com.myapp:*/Important*"`.

## 🔒 Web Dashboard Security

The dashboard exposes an API that can delete files, so it is locked down:

- Binds to **loopback only** (`127.0.0.1`) — never reachable from the LAN.
- Rejects requests whose `Host`/`Origin` is not loopback (anti DNS-rebinding/CSRF).
- Requires a **per-session token** (regenerated on each start) on every
  destructive request; no wildcard CORS is sent.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
