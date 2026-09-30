"""Redirect and safety checks for pre-audit official-domain resolution."""

import socket
import unittest
from unittest.mock import patch

from audit_core.official_domains import (
    OfficialDomainResolutionError,
    _public_ip_for,
    resolve_official_site,
)


class OfficialDomainTests(unittest.TestCase):
    def test_cross_tld_redirect_with_blocked_destination_is_verified(self):
        responses = {
            "https://idealista.es/": (301, "https://www.idealista.com/"),
            "https://www.idealista.com/": (403, None),
        }
        result = resolve_official_site(
            "idealista.es", request_headers=responses.__getitem__
        )
        self.assertEqual(result["canonical_hostname"], "www.idealista.com")
        self.assertEqual(result["canonical_url"], "https://www.idealista.com/")
        self.assertEqual(result["verification"], "verified_redirect")
        self.assertEqual(len(result["redirect_chain"]), 1)

    def test_direct_success_keeps_submitted_host(self):
        result = resolve_official_site(
            "https://example.org/", request_headers=lambda _url: (200, None)
        )
        self.assertEqual(result["canonical_hostname"], "example.org")
        self.assertEqual(result["verification"], "verified_response")

    def test_unverified_direct_block_stops_before_audit(self):
        with self.assertRaisesRegex(OfficialDomainResolutionError, "HTTP 403"):
            resolve_official_site(
                "example.org", request_headers=lambda _url: (403, None)
            )

    def test_redirect_to_internal_or_insecure_address_is_rejected(self):
        for destination in ("https://localhost/", "https://service.internal/", "http://example.org/"):
            with self.subTest(destination=destination):
                with self.assertRaises(OfficialDomainResolutionError):
                    resolve_official_site(
                        "example.org", request_headers=lambda _url: (301, destination)
                    )

    def test_redirect_loop_is_rejected(self):
        with self.assertRaisesRegex(OfficialDomainResolutionError, "redirect loop"):
            resolve_official_site(
                "example.org", request_headers=lambda _url: (301, "/")
            )

    def test_custom_port_is_rejected(self):
        with self.assertRaisesRegex(OfficialDomainResolutionError, "custom port"):
            resolve_official_site("https://example.org:8443/")

    def test_private_dns_answer_is_rejected(self):
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))]
        with patch("audit_core.official_domains.socket.getaddrinfo", return_value=records):
            with self.assertRaisesRegex(OfficialDomainResolutionError, "non-public"):
                _public_ip_for("example.org")


if __name__ == "__main__":
    unittest.main()
