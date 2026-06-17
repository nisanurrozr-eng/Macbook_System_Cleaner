"""Unit tests for server.py input validation helpers."""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'web'))


class TestValidateAppLeftover(unittest.TestCase):
    def setUp(self):
        from server import _validate_app_leftover
        self.v = _validate_app_leftover

    def test_allows_simple_name(self):
        self.assertTrue(self.v("Slack"))
        self.assertTrue(self.v("com.google.Chrome"))
        self.assertTrue(self.v("My App"))
        self.assertTrue(self.v("App-Name.1"))

    def test_blocks_path_traversal(self):
        self.assertFalse(self.v("../etc/passwd"))
        self.assertFalse(self.v("/absolute/path"))

    def test_blocks_special_chars(self):
        self.assertFalse(self.v("app;rm -rf /"))
        self.assertFalse(self.v("app`id`"))
        self.assertFalse(self.v("app$HOME"))

    def test_blocks_too_long(self):
        self.assertFalse(self.v("a" * 65))

    def test_blocks_empty(self):
        self.assertFalse(self.v(""))


class TestValidateDeveloperItem(unittest.TestCase):
    def setUp(self):
        from server import _validate_developer_item
        self.v = _validate_developer_item

    def test_whitelist_entries(self):
        for item in ("derived_data", "broken_links", "brew_cache",
                     "docker_prune", "npm_cache", "pip_cache"):
            self.assertTrue(self.v(item), f"Expected True for {item}")

    def test_rejects_unknown(self):
        self.assertFalse(self.v("evil_cmd"))
        self.assertFalse(self.v("../../etc"))
        self.assertFalse(self.v("; rm -rf /"))

    def test_new_developer_keys_allowed(self):
        for k in ["device_support", "coresim_caches", "xcode_archives",
                  "simctl_unavailable", "pnpm_cache", "yarn_cache",
                  "cocoapods_cache", "gradle_cache", "maven_repo"]:
            self.assertTrue(self.v(k), k)


class TestValidateBrowserKey(unittest.TestCase):
    def setUp(self):
        from server import _validate_browser_key
        self.v = _validate_browser_key

    def test_whitelist_entries(self):
        for k in ("safari", "cookies", "chrome", "firefox",
                  "brave", "edge", "opera", "arc"):
            self.assertTrue(self.v(k), f"Expected True for {k}")

    def test_rejects_unknown(self):
        self.assertFalse(self.v("not_a_browser"))
        self.assertFalse(self.v("; rm -rf /"))


class TestValidateAppName(unittest.TestCase):
    def setUp(self):
        from server import _validate_app_name
        self.v = _validate_app_name

    def test_allows_valid_app_names(self):
        self.assertTrue(self.v("Firefox"))
        self.assertTrue(self.v("Visual Studio Code"))
        self.assertTrue(self.v("App-Name.1"))

    def test_blocks_traversal(self):
        self.assertFalse(self.v("../Applications"))
        self.assertFalse(self.v("/Applications/Evil"))

    def test_blocks_injection(self):
        self.assertFalse(self.v("App;rm -rf /"))
        self.assertFalse(self.v("App`id`"))

    def test_blocks_empty(self):
        self.assertFalse(self.v(""))


class TestAllowedHost(unittest.TestCase):
    def setUp(self):
        from server import _is_allowed_host
        self.v = _is_allowed_host

    def test_allows_loopback(self):
        self.assertTrue(self.v("localhost"))
        self.assertTrue(self.v("localhost:8080"))
        self.assertTrue(self.v("127.0.0.1"))
        self.assertTrue(self.v("127.0.0.1:8080"))
        self.assertTrue(self.v("[::1]"))
        self.assertTrue(self.v("[::1]:8080"))

    def test_blocks_external_hosts(self):
        self.assertFalse(self.v("example.com"))
        self.assertFalse(self.v("192.168.1.20:8080"))
        self.assertFalse(self.v("evil.attacker.test"))

    def test_blocks_empty(self):
        self.assertFalse(self.v(""))


class TestAllowedOrigin(unittest.TestCase):
    def setUp(self):
        from server import _is_allowed_origin
        self.v = _is_allowed_origin

    def test_absent_origin_allowed(self):
        # curl / native clients omit Origin; allowed (token + Host still guard)
        self.assertTrue(self.v(None))
        self.assertTrue(self.v(""))

    def test_loopback_origin_allowed(self):
        self.assertTrue(self.v("http://localhost:8080"))
        self.assertTrue(self.v("http://127.0.0.1:8080"))
        self.assertTrue(self.v("http://[::1]:8080"))

    def test_external_origin_blocked(self):
        self.assertFalse(self.v("http://evil.example.com"))
        self.assertFalse(self.v("https://attacker.test"))
        self.assertFalse(self.v("null"))


class TestExtraEnvForClean(unittest.TestCase):
    def setUp(self):
        from server import _extra_env_for_clean
        self.f = _extra_env_for_clean

    def test_dry_run_true_sets_env(self):
        self.assertEqual(self.f({"dry_run": True}),
                         {"APPLE_CLEANUP_DRYRUN": "1"})

    def test_dry_run_absent_or_false_empty(self):
        self.assertEqual(self.f({}), {})
        self.assertEqual(self.f({"dry_run": False}), {})
        # Only a real boolean True enables it (no truthy strings)
        self.assertEqual(self.f({"dry_run": "true"}), {})
        self.assertEqual(self.f({"dry_run": 1}), {})


class TestTokenCompare(unittest.TestCase):
    def setUp(self):
        from server import _token_matches, SESSION_TOKEN
        self.v = _token_matches
        self.token = SESSION_TOKEN

    def test_matches_correct_token(self):
        self.assertTrue(self.v(self.token))

    def test_rejects_wrong_token(self):
        self.assertFalse(self.v("wrong"))
        self.assertFalse(self.v(None))
        self.assertFalse(self.v(""))


if __name__ == "__main__":
    unittest.main()
