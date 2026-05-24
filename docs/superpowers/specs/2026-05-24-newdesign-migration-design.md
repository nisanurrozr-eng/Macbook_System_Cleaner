# Design: New UI Migration + Data-Driven Categories

**Date:** 2026-05-24  
**Status:** Approved

---

## Goal

Replace the old `web/` UI (dark, emoji-based card grid, no mock fallback, hard-coded categories in HTML) with the refined `newdesign/` UI (macOS-style list rows, hero section, disk donut, collapsible terminal, mock API fallback). Simultaneously make categories data-driven so adding or removing a cleanup category requires editing a single array entry in `script.js` — no HTML changes.

---

## File Structure

**Before:**
```
web/
  index.html   ← old UI
  style.css    ← old styles
  script.js    ← old logic
  server.py    ← HTTP server (unchanged)
newdesign/
  index.html   ← new UI
  style.css    ← new styles
  script.js    ← new logic
```

**After:**
```
web/
  index.html   ← new UI (catList ul is empty; categories rendered by JS)
  style.css    ← new styles (unchanged from newdesign/)
  script.js    ← new logic + data-driven categories
  server.py    ← unchanged
```

`newdesign/` is deleted once files are confirmed working in `web/`.

---

## Architecture

### Categories Config (single source of truth)

A `CATEGORIES` array at the top of `script.js` replaces both:
- The 10 `<li>` elements in `index.html`
- The `CATEGORY_MAP` object in `script.js`

Each entry shape:
```js
{
  key:            string,   // e.g. 'user_cache'
  index:          number,   // 1-based, used by backend API
  name:           string,   // display name
  desc:           string,   // subtitle
  icon:           string,   // SVG symbol id, e.g. 'i-cache'
  color:          string,   // hex — stacked bar + bar-fill
  defaultChecked: boolean,  // initial toggle state
  danger:         boolean,  // adds .cat-danger class
  tags:           Array<{ icon: string, label: string, style: 'amber'|'red' }>,
}
```

To add a new category: append one object to `CATEGORIES`. To remove one: delete its entry. No other files change.

### `renderCategories()`

Runs once at init, before any DOM queries. Builds `<li class="cat ...">` rows from `CATEGORIES` and appends them to `<ul id="catList">`. After render, `el.cats` is populated via `$$('.cat[data-category]')`.

### Category Count Label

`#categoryCount` text is set to `CATEGORIES.length + ' kategori'` by `renderCategories()`. Stays accurate automatically.

### SVG Icon Sprite

SVG `<symbol>` definitions stay in `index.html`. Icons are referenced by `id` from the `CATEGORIES` config. No change needed.

### Mock API

Mock scan sizes remain keyed by string (`user_cache`, etc.), not by HTML position. They are co-located with the `CATEGORIES` array (or just above it) so they're easy to find when adding a new category.

### `el.cats` Query Timing

Currently queried at module init before render. After refactor, it is queried after `renderCategories()` completes so the array is always populated.

---

## What Does NOT Change

- `web/server.py` — zero edits. Already serves `web/` directory.
- `style.css` — copied verbatim from `newdesign/style.css`.
- All API endpoints and payload shapes — backend contract is unchanged.
- Tweaks panel (palette picker + postMessage host integration) — kept as-is.
- Keyboard shortcuts (⌘S scan, ⌘↩ clean) — kept as-is.
- Mock API fallback — kept as-is.

---

## Out of Scope

- Backend changes (`server.py`, `clean_mac.sh`)
- Adding new categories (the refactor makes this easy, but no new categories are added in this task)
- External JSON config file for categories
