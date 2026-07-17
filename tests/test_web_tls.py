"""
Unit tests for the web-mode TLS guard in RadSpeed.py.

check_web_tls() decides whether a launch configuration is safe: plain HTTP
with Basic Auth must never be served on a non-loopback address unless the
operator explicitly opts out or TLS is terminated upstream.
"""
import os
import tempfile
import unittest

from RadSpeed import check_web_tls, _is_loopback_host


class TestIsLoopbackHost(unittest.TestCase):
    def test_loopback_addresses(self):
        for host in ("127.0.0.1", "127.1.2.3", "::1", "localhost", ""):
            self.assertTrue(_is_loopback_host(host), host)

    def test_non_loopback_addresses(self):
        for host in ("0.0.0.0", "::", "192.168.1.10", "10.0.0.5", "example.com"):
            self.assertFalse(_is_loopback_host(host), host)


class TestCheckWebTls(unittest.TestCase):
    def setUp(self):
        self.cert = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
        self.key = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
        self.cert.close()
        self.key.close()

    def tearDown(self):
        os.unlink(self.cert.name)
        os.unlink(self.key.name)

    def test_loopback_plain_http_allowed(self):
        self.assertEqual(
            check_web_tls("127.0.0.1", "", "", False, False), "loopback"
        )

    def test_non_loopback_plain_http_refused(self):
        with self.assertRaises(SystemExit) as ctx:
            check_web_tls("0.0.0.0", "", "", False, False)
        self.assertIn("refusing to serve plain HTTP", str(ctx.exception))

    def test_tls_files_allowed_on_any_host(self):
        self.assertEqual(
            check_web_tls("0.0.0.0", self.cert.name, self.key.name, False, False),
            "tls",
        )

    def test_behind_proxy_allowed(self):
        self.assertEqual(
            check_web_tls("0.0.0.0", "", "", True, False), "behind-proxy"
        )

    def test_insecure_optout_allowed(self):
        self.assertEqual(
            check_web_tls("0.0.0.0", "", "", False, True), "insecure"
        )

    def test_certfile_without_keyfile_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            check_web_tls("0.0.0.0", self.cert.name, "", False, False)
        self.assertIn("must be given together", str(ctx.exception))

    def test_keyfile_without_certfile_rejected(self):
        with self.assertRaises(SystemExit):
            check_web_tls("0.0.0.0", "", self.key.name, False, False)

    def test_missing_cert_file_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            check_web_tls("0.0.0.0", "/nonexistent/cert.pem", self.key.name,
                          False, False)
        self.assertIn("not found", str(ctx.exception))

    def test_tls_takes_precedence_over_flags(self):
        # Valid TLS config wins even if the opt-out flags are also set.
        self.assertEqual(
            check_web_tls("0.0.0.0", self.cert.name, self.key.name, True, True),
            "tls",
        )


if __name__ == "__main__":
    unittest.main()
