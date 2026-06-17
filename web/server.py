#!/usr/bin/env python3
"""
Apple Cleanup Web Dashboard — HTTP Server (v2.0.0)
Serves the web UI and proxies API requests to clean_mac.sh

Security features:
  - Whitelist validation for all sub-item parameters
  - Content-Type enforcement on POST endpoints
  - Request body size limit (1MB)
  - Path traversal prevention for static files
  - Integer coercion for category indices
  - Boolean normalization for scan JSON fields
"""

import hmac
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import urllib.parse
from pathlib import Path

# Bind to loopback only — this API can delete files and must never be
# reachable from the local network.
HOST = "127.0.0.1"
PORT = 8080
WEB_DIR = Path(__file__).parent.resolve()
SCRIPT_PATH = (WEB_DIR.parent / "clean_mac.sh").resolve()

# Maximum allowed request body size (1 MB)
MAX_BODY_SIZE = 1 * 1024 * 1024  # 1,048,576 bytes

# Per-process CSRF/session token. Regenerated on every server start and
# embedded into the served index.html; destructive endpoints require it.
SESSION_TOKEN = secrets.token_urlsafe(32)
TOKEN_PLACEHOLDER = "__CLEANUP_TOKEN__"

# Loopback host names accepted in the Host / Origin headers. Anything else is
# rejected to defeat DNS-rebinding attacks against the loopback binding.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "ip6-localhost"})


def _host_only(value: str) -> str:
    """Strip scheme, port and IPv6 brackets, returning the bare host."""
    if not value:
        return ""
    # Drop scheme (http://host) if present
    if "://" in value:
        value = value.split("://", 1)[1]
    value = value.strip().rstrip("/")
    # Bracketed IPv6 literal, optionally with :port
    if value.startswith("["):
        return value[1:].split("]", 1)[0]
    # host:port — split on the last colon only if it looks like a port
    if value.count(":") == 1:
        value = value.split(":", 1)[0]
    return value


def _is_allowed_host(host_header: str) -> bool:
    """True if the Host header points at a loopback address."""
    return _host_only(host_header) in _LOOPBACK_HOSTS


def _is_allowed_origin(origin_header) -> bool:
    """
    True if the Origin header is absent (non-browser client) or points at a
    loopback address. Blocks cross-site requests from real web pages.
    """
    if not origin_header:
        return True
    if origin_header == "null":
        return False
    return _host_only(origin_header) in _LOOPBACK_HOSTS


def _extra_env_for_clean(payload: dict) -> dict:
    """
    Derive environment overrides for a clean request. Currently exposes the
    dry-run preview mode. Requires a real boolean True (not a truthy string)
    so a stray field can never silently disable real cleaning or enable it.
    """
    env = {}
    if isinstance(payload, dict) and payload.get("dry_run") is True:
        env["APPLE_CLEANUP_DRYRUN"] = "1"
    return env


def _token_matches(token) -> bool:
    """Constant-time comparison of a supplied token against the session token."""
    if not token or not isinstance(token, str):
        return False
    return hmac.compare_digest(token, SESSION_TOKEN)

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

# ── Input Validation ─────────────────────────────────────────────────────────
# Regex for app leftover dir names and app names
_APP_LEFTOVER_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$')
_APP_NAME_RE     = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$')

# Developer sub-item whitelist — MUST be 100% in sync with clean_mac.sh
# Corresponds to the case statement in clean_developer() JSON mode
_DEVELOPER_WHITELIST = frozenset({
    "derived_data",        # Xcode DerivedData
    "broken_links",        # Broken symlinks
    "brew_cache",          # Homebrew cache
    "docker_prune",        # Docker system prune
    "npm_cache",           # npm _cacache
    "pip_cache",           # pip cache
    "device_support",      # iOS DeviceSupport
    "coresim_caches",      # CoreSimulator Caches
    "xcode_archives",      # Xcode Archives
    "cocoapods_cache",     # CocoaPods Cache
    "pnpm_cache",          # pnpm Store
    "yarn_cache",          # Yarn Cache
    "gradle_cache",        # Gradle caches
    "maven_repo",          # Maven repository
    "simctl_unavailable",  # Delete unavailable simulators
})

# Browser key whitelist — MUST be 100% in sync with clean_mac.sh
# Corresponds to browser_keys array in clean_browser_full()
_BROWSER_WHITELIST = frozenset({
    "safari",    # ~/Library/Safari
    "cookies",   # ~/Library/Cookies
    "chrome",    # ~/Library/Application Support/Google/Chrome
    "firefox",   # ~/Library/Application Support/Firefox
    "brave",     # ~/Library/Application Support/BraveSoftware
    "edge",      # ~/Library/Application Support/Microsoft Edge
    "opera",     # ~/Library/Application Support/com.operasoftware.Opera
    "arc",       # ~/Library/Application Support/Arc
})


def _validate_app_leftover(name: str) -> bool:
    """Validate an app leftover directory name (no traversal, no injection)."""
    return bool(_APP_LEFTOVER_RE.match(name)) and ".." not in name and "/" not in name


def _validate_developer_item(item: str) -> bool:
    """Validate a developer sub-item key against the whitelist."""
    return item in _DEVELOPER_WHITELIST


def _validate_browser_key(key: str) -> bool:
    """Validate a browser key against the whitelist."""
    return key in _BROWSER_WHITELIST


def _validate_app_name(name: str) -> bool:
    """Validate an application name for uninstallation."""
    return bool(_APP_NAME_RE.match(name)) and ".." not in name and "/" not in name


def _normalize_bool_fields(data: dict) -> dict:
    """
    Recursively normalize boolean string fields in scan JSON.
    Converts string "true"/"false" to Python bool True/False.
    Also ensures needs_sudo is always a proper bool.
    """
    if not isinstance(data, dict):
        return data

    for key, value in data.items():
        if isinstance(value, str):
            if value.lower() == "true":
                data[key] = True
            elif value.lower() == "false":
                data[key] = False
        elif isinstance(value, dict):
            _normalize_bool_fields(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _normalize_bool_fields(item)
    return data


class CleanupHandler(http.server.BaseHTTPRequestHandler):
    """Request handler for the Apple Cleanup dashboard."""

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[server] {fmt % args}\n")

    # ── Security headers ────────────────────────────────────
    def _security_headers(self):
        # No wildcard CORS: the dashboard is served same-origin, so cross-origin
        # reads must stay blocked. These headers harden the responses further.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    def do_OPTIONS(self):
        # Same-origin only; no CORS preflight is honoured.
        self.send_response(204)
        self._security_headers()
        self.end_headers()

    def _require_loopback_host(self) -> bool:
        """Reject requests whose Host header is not a loopback address."""
        if _is_allowed_host(self.headers.get("Host", "")):
            return True
        self._send_error_json("Forbidden host", 403)
        return False

    def _require_csrf(self) -> bool:
        """Enforce Origin and session-token checks on state-changing requests."""
        if not _is_allowed_origin(self.headers.get("Origin")):
            self._send_error_json("Cross-origin request blocked", 403)
            return False
        if not _token_matches(self.headers.get("X-Cleanup-Token")):
            self._send_error_json("Missing or invalid session token", 403)
            return False
        return True

    # ── Helpers ─────────────────────────────────────────────
    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._security_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message, status=500):
        self._send_json({"success": False, "error": message}, status)

    def _read_json_body(self) -> tuple:
        """
        Read and parse JSON from POST body with Content-Type and size checks.
        Returns (payload_dict, None) on success or (None, error_message) on failure.
        """
        # Content-Type validation
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return None, "Content-Type must be application/json"

        # Body size check
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (ValueError, TypeError):
            return None, "Invalid Content-Length header"

        if length <= 0:
            return None, "Empty request body"

        if length > MAX_BODY_SIZE:
            return None, f"Request body too large (max {MAX_BODY_SIZE} bytes)"

        # Read and parse
        try:
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body)
        except json.JSONDecodeError:
            return None, "Invalid JSON body"
        except UnicodeDecodeError:
            return None, "Request body must be UTF-8 encoded"

        if not isinstance(payload, dict):
            return None, "JSON body must be an object"

        return payload, None

    def _run_script(self, args, timeout=120, env_extra=None):
        """Run clean_mac.sh with given arguments and return parsed JSON."""
        cmd = ["bash", str(SCRIPT_PATH)] + args
        run_env = dict(os.environ)
        if env_extra:
            run_env.update(env_extra)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(SCRIPT_PATH.parent),
                env=run_env,
            )
            output = result.stdout.strip()
            if not output:
                return None, result.stderr.strip() or "Script returned no output"
            parsed = json.loads(output)

            # Normalize boolean fields (Bash outputs JSON bool literals,
            # but this ensures consistency even if format changes)
            if isinstance(parsed, dict):
                _normalize_bool_fields(parsed)

            return parsed, None
        except subprocess.TimeoutExpired:
            return None, "Script timed out"
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON from script: {e}"
        except Exception as e:
            return None, str(e)

    # ── Routes ──────────────────────────────────────────────
    def do_GET(self):
        if not self._require_loopback_host():
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # API endpoints
        if path == "/api/scan":
            self._handle_scan()
        elif path == "/api/status":
            self._handle_status()
        else:
            self._serve_static(path)

    def do_POST(self):
        if not self._require_loopback_host():
            return
        if not self._require_csrf():
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/clean":
            self._handle_clean()
        elif parsed.path == "/api/spotlight-reindex":
            self._handle_spotlight_reindex()
        elif parsed.path == "/api/flush-dns":
            self._handle_flush_dns()
        elif parsed.path == "/api/purge-ram":
            self._handle_purge_ram()
        elif parsed.path == "/api/launchagents-clean":
            self._handle_launchagents_clean()
        elif parsed.path == "/api/thin-snapshots":
            self._handle_thin_snapshots()
        else:
            self._send_error_json("Not found", 404)

    # ── API Handlers ────────────────────────────────────────
    def _handle_scan(self):
        data, err = self._run_script(["--scan-json"])
        if err:
            self._send_error_json(f"Scan error: {err}")
        else:
            self._send_json(data)

    def _handle_status(self):
        data, err = self._run_script(["--status-json"], timeout=15)
        if err:
            self._send_error_json(f"Status error: {err}")
        else:
            self._send_json(data)

    def _handle_clean(self):
        payload, err = self._read_json_body()
        if err:
            self._send_error_json(err, 400)
            return

        categories = payload.get("categories", [])
        if not categories or not isinstance(categories, list):
            self._send_error_json("Category list required", 400)
            return

        # Integer coercion: frontend may send strings like "3" instead of 3
        safe_cats = []
        for c in categories:
            try:
                safe_cats.append(int(c))
            except (ValueError, TypeError):
                pass  # Skip invalid entries silently
        if not safe_cats:
            self._send_error_json("No valid category indices provided", 400)
            return

        cat_str = ",".join(str(c) for c in safe_cats)
        args = ["--clean-json", cat_str]

        # App leftovers sub-items
        app_leftovers_selected = payload.get("app_leftovers_selected", [])
        if app_leftovers_selected and isinstance(app_leftovers_selected, list):
            safe = [x for x in app_leftovers_selected
                    if isinstance(x, str) and _validate_app_leftover(x)]
            if safe:
                args += ["--app-leftovers", ",".join(safe)]

        # Browser full sub-items
        browser_full_selected = payload.get("browser_full_selected", [])
        if browser_full_selected and isinstance(browser_full_selected, list):
            safe = [x for x in browser_full_selected
                    if isinstance(x, str) and _validate_browser_key(x)]
            if safe:
                args += ["--browser-full-sub", ",".join(safe)]

        # Developer sub-items
        developer_selected = payload.get("developer_selected", [])
        if developer_selected and isinstance(developer_selected, list):
            safe = [x for x in developer_selected
                    if isinstance(x, str) and _validate_developer_item(x)]
            if safe:
                args += ["--developer-sub", ",".join(safe)]

        # iOS backups sub-items
        ios_backups_selected = payload.get("ios_backups_selected", [])
        if ios_backups_selected and isinstance(ios_backups_selected, list):
            _uuid_re = re.compile(r'^[0-9A-Fa-f\-]{1,40}$')
            safe_uuids = [u for u in ios_backups_selected
                         if isinstance(u, str) and _uuid_re.match(u)]
            if safe_uuids:
                args += ["--ios-backups-sub", ",".join(safe_uuids)]

        # App uninstaller sub-items
        app_uninstaller_selected = payload.get("app_uninstaller_selected", [])
        if app_uninstaller_selected and isinstance(app_uninstaller_selected, list):
            safe = [x for x in app_uninstaller_selected
                    if isinstance(x, str) and _validate_app_name(x)]
            if safe:
                args += ["--app-uninstaller-sub", ",".join(safe)]

        data, err = self._run_script(args, env_extra=_extra_env_for_clean(payload))
        if err:
            self._send_error_json(f"Clean error: {err}")
        else:
            self._send_json(data)

    def _handle_spotlight_reindex(self):
        data, err = self._run_script(["--spotlight-reindex"], timeout=45)
        if err:
            self._send_error_json(f"Spotlight Indexing Failure: {err}")
        else:
            self._send_json(data)

    def _handle_flush_dns(self):
        data, err = self._run_script(["--flush-dns"], timeout=15)
        if err:
            self._send_error_json(f"DNS flush error: {err}")
        else:
            self._send_json(data)

    def _handle_purge_ram(self):
        data, err = self._run_script(["--purge-ram"], timeout=30)
        if err:
            self._send_error_json(f"RAM purge error: {err}")
        else:
            self._send_json(data)

    def _handle_launchagents_clean(self):
        data, err = self._run_script(["--launchagents-clean"], timeout=30)
        if err:
            self._send_error_json(f"LaunchAgents clean error: {err}")
        else:
            self._send_json(data)

    def _handle_thin_snapshots(self):
        data, err = self._run_script(["--thin-snapshots-json"], timeout=120)
        if err:
            self._send_error_json(f"Snapshot thinning error: {err}")
        else:
            self._send_json(data)

    # ── Static File Server ──────────────────────────────────
    def _serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"

        file_path = (WEB_DIR / path.lstrip("/")).resolve()

        # Security: prevent directory traversal. Compare against the resolved
        # web dir using path semantics so a sibling like "<dir>_evil" can't pass.
        if file_path != WEB_DIR and WEB_DIR not in file_path.parents:
            self._send_error_json("Forbidden", 403)
            return

        if not file_path.is_file():
            self._send_error_json("Not found", 404)
            return

        ext = file_path.suffix.lower()
        content_type = MIME_TYPES.get(ext, "application/octet-stream")

        try:
            data = file_path.read_bytes()
            # Inject the per-session token into the dashboard so the frontend
            # can authenticate destructive requests.
            if file_path.name == "index.html":
                data = data.replace(
                    TOKEN_PLACEHOLDER.encode("utf-8"),
                    SESSION_TOKEN.encode("utf-8"),
                )
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self._security_headers()
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self._send_error_json(f"File read error: {e}")


def main():
    http.server.HTTPServer.allow_reuse_address = True
    server = http.server.HTTPServer((HOST, PORT), CleanupHandler)
    print(f"🍎 Apple Cleanup Dashboard v2.0.0")
    print(f"   http://localhost:{PORT}  (loopback only)")
    print(f"   Press Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✋ Server stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
