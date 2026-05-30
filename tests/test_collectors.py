from __future__ import annotations

import unittest

from src.collectors import parse_115_shares


class Parse115SharesTest(unittest.TestCase):
    def test_parses_plain_115_share_link(self) -> None:
        shares = parse_115_shares("资源：https://115.com/s/abc123")

        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0].share_code, "abc123")
        self.assertEqual(shares[0].receive_code, "")
        self.assertEqual(shares[0].share_url, "https://115.com/s/abc123")

    def test_parses_password_query_as_receive_code(self) -> None:
        shares = parse_115_shares("资源：https://115.com/s/abc123?password=xy9z")

        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0].share_code, "abc123")
        self.assertEqual(shares[0].receive_code, "xy9z")
        self.assertEqual(shares[0].share_url, "https://115.com/s/abc123?password=xy9z")

    def test_parses_fragment_as_receive_code(self) -> None:
        shares = parse_115_shares("资源：https://115.com/s/abc123#xy9z")

        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0].share_code, "abc123")
        self.assertEqual(shares[0].receive_code, "xy9z")
        self.assertEqual(shares[0].share_url, "https://115.com/s/abc123#xy9z")

    def test_parses_115cdn_share_link_with_password_query(self) -> None:
        shares = parse_115_shares("资源：https://115cdn.com/s/swfu86g3wov?password=fe00")

        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0].share_code, "swfu86g3wov")
        self.assertEqual(shares[0].receive_code, "fe00")
        self.assertEqual(shares[0].share_url, "https://115cdn.com/s/swfu86g3wov?password=fe00")

    def test_returns_unique_links_in_first_seen_order(self) -> None:
        shares = parse_115_shares(
            "https://115.com/s/first # ignore text\n"
            "https://115.com/s/second?password=22\n"
            "https://115.com/s/first"
        )

        self.assertEqual([share.share_code for share in shares], ["first", "second"])
        self.assertEqual([share.receive_code for share in shares], ["", "22"])


if __name__ == "__main__":
    unittest.main()
