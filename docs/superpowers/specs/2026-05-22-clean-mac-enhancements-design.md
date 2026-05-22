# Clean Mac — Enhancement Design Spec
**Date:** 2026-05-22  
**Status:** Approved

---

## Overview

Extend the Clean Mac tool with four capabilities:
1. iOS Backup scanning and cleanup (`ios_backups` category)
2. Spotlight re-indexing trigger (async maintenance action)
3. Hardened security heuristic filter in `is_app_installed`
4. Web UI cards and API wiring for both new features

---

## 1. iOS Backups (`ios_backups`)

### What
Scan `~/Library/MobileSync/Backup/` — each UUID subfolder is one iPhone/iPad backup. Report total size and allow selective deletion per backup.

### Category Definition
- **ID:** `ios_backups`
- **Index:** 10
- **Needs sudo:** false
- **Has subitems:** yes (one per backup UUID folder)

### Subitem Schema
Each subitem returned in JSON:
```json
{
  "id": "<UUID>",
  "name": "<UUID> (YYYY-MM-DD HH:MM)",
  "path": "/Users/.../MobileSync/Backup/<UUID>",
  "size_bytes": 1234567890,
  "size_human": "1.1 GB",
  "is_orphaned": true
}
```
`is_orphaned` is always `true` (user decides which backups to keep).

### Shell Functions
- `scan_ios_backups()` — fills `CAT_SIZES[9]`
- `scan_ios_backups_subitems_json()` — emits JSON subitem array
- `clean_ios_backups()` — in JSON mode reads `--ios-backups-sub` arg, deletes selected UUID dirs

### CLI Flag
`--ios-backups-sub "UUID1,UUID2"` — comma-separated UUID folder names to delete

---

## 2. Spotlight Re-indexing

### What
Run `sudo mdutil -i off /` then `sudo mdutil -i on /` then `sudo mdutil -E /` to fix ghost disk space. Non-blocking — script fires the commands and returns immediately.

### Shell Function
```bash
do_spotlight_reindex() {
  # Fire-and-forget: runs in background subshell
  (sudo mdutil -i off / 2>/dev/null; sudo mdutil -i on / 2>/dev/null; sudo mdutil -E / 2>/dev/null) &
  echo '{"success": true, "status": "started", "message": "Spotlight yeniden indeksleme başlatıldı."}'
}
```
Triggered by `--spotlight-reindex` flag. Returns JSON immediately, process continues in background.

### Server Endpoint
`POST /api/spotlight-reindex` — calls `_run_script(["--spotlight-reindex"], timeout=10)`. Since script exits immediately, no timeout risk.

---

## 3. Security Heuristic Filter

### Problem
`is_app_installed()` currently protects `com.apple.*` bundles but not plain-name Apple system folders like `Audio`, `Fonts`, `Input Methods`.

### Fix
Expand the hardcoded whitelist in `is_app_installed()`:

```bash
case "$dir_name" in
  # Bundle IDs
  Apple|com.apple.*|com.google.*|com.microsoft.*|com.adobe.*| \
  Helper|CrashReporter|MobileSync|SyncServices|Oracle|com.oracle.*|Homebrew| \
  # Plain-name Apple system directories — NEVER touch
  Audio|Fonts|"Input Methods"|Compositions|ColorSync|Keyboard\ Layouts| \
  Spelling|Dictionaries|CoreData|AddressBook|Calendars|Safari|Mail| \
  Messages|FaceTime|Photos|Music|Podcasts|News|Maps|Reminders| \
  Notes|Stocks|Home|"TV"|"Clips"|iTunesLibrary|Instruments| \
  "Final Cut"|Logic|GarageBand|"Motion"|"Compressor"|"MainStage")
    return 0
    ;;
esac
```

---

## 4. Web UI

### New Category Card: iOS Backups
- Standard card format, `data-category="ios_backups"` `data-index="10"`
- Icon: 📱
- Warning label: "iPhone/iPad yedekleri — silmeden önce kontrol edin"
- Subitems: rendered same as `app_leftovers` (each UUID row, all checked by default)

### New Maintenance Card: Spotlight
- Separate `<div class="maintenance-card">` section, below the grid
- Not a checkbox category — has a standalone **"🔦 Yenile"** button
- On click: POST `/api/spotlight-reindex`, show terminal log + success state
- Disables during request, re-enables after

### script.js
- Add `ios_backups: { index: 10, name: 'iOS Yedekleri (MobileSync)' }` to `CATEGORY_MAP`
- `getSelectedSubitems('ios_backups')` → `ios_backups_selected` in clean payload
- New `handleSpotlightReindex()` async function wired to the Spotlight button

### server.py
- Add `POST /api/spotlight-reindex` → `_handle_spotlight_reindex()`
- Add `ios_backups_selected` extraction in `_handle_clean()` → `--ios-backups-sub` arg

---

## Data Flow

```
UI checkbox → getSelectedCategories() [includes index 10]
           → POST /api/clean { categories: [..., 10], ios_backups_selected: ["UUID1"] }
           → server.py _handle_clean() → args += ["--ios-backups-sub", "UUID1"]
           → clean_mac.sh --clean-json "...,10" --ios-backups-sub "UUID1"
           → clean_ios_backups() → deletes selected UUID dirs
```

```
UI "🔦 Yenile" button → POST /api/spotlight-reindex
                      → server.py _handle_spotlight_reindex()
                      → clean_mac.sh --spotlight-reindex
                      → do_spotlight_reindex() → background mdutil → immediate JSON return
```

---

## Bash Compatibility

All new code uses Bash 3.2+ patterns:
- No `declare -A` (associative arrays)
- No `mapfile`/`readarray`
- Parallel arrays for category data
- `IFS` saves/restores for CSV parsing
- `set -euo pipefail` maintained throughout
