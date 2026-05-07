import unittest

from access import is_allowed_public_host, is_private_client


class AccessGuardTests(unittest.TestCase):
    def test_private_clients_are_allowed_by_lan_guard(self) -> None:
        self.assertTrue(is_private_client("127.0.0.1"))
        self.assertTrue(is_private_client("192.168.0.10"))

    def test_public_cloudflare_host_requires_known_hostname(self) -> None:
        self.assertTrue(
            is_allowed_public_host(
                "vortax-api.cursar.space",
                {"cf-ray": "abc-GRU", "cf-connecting-ip": "203.0.113.10"},
            )
        )

    def test_public_cloudflare_host_rejects_unknown_hostname(self) -> None:
        self.assertFalse(
            is_allowed_public_host(
                "example.com",
                {"cf-ray": "abc-GRU", "cf-connecting-ip": "203.0.113.10"},
            )
        )

    def test_public_hostname_without_cloudflare_headers_is_not_enough(self) -> None:
        self.assertFalse(is_allowed_public_host("vortax-api.cursar.space", {}))


if __name__ == "__main__":
    unittest.main()
