"""Brand mention detection stays identical in service and bundled notebook."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import tldextract

from audit_core.brand_mentions import (
    build_brand_aliases,
    find_brand_mentions,
    mention_order,
)
from audit_core.domains import get_root_domain


ROOT = Path(__file__).resolve().parents[1]


def bundled_mentions():
    notebook = json.loads((ROOT / "competitive_visibility_audit_bd.ipynb").read_text())
    cell = next(cell for cell in notebook["cells"]
                if cell.get("metadata", {}).get("id") == "final-orchestration")
    source = "".join(cell["source"])
    code = source.split("# AUDIT-BRAND-MENTIONS: start\n", 1)[1].split(
        "# AUDIT-BRAND-MENTIONS: end", 1
    )[0]
    namespace = {"get_root_domain": get_root_domain}
    exec(compile(code, "bundled-brand-mentions", "exec"), namespace)
    return namespace


class BrandMentionTests(unittest.TestCase):
    def setUp(self):
        extractor = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=())
        mock = patch("tldextract.extract", extractor)
        mock.start()
        self.addCleanup(mock.stop)

    def test_shared_corporate_domain_does_not_confuse_products(self):
        loop = SimpleNamespace(brand_name="Microsoft Loop", domain="microsoft.com",
                               direct_competitor=False)
        planner = SimpleNamespace(brand_name="Microsoft Planner", domain="microsoft.com",
                                  direct_competitor=True)
        mentions = find_brand_mentions("Microsoft Loop helps teams collaborate.",
                                       [loop, planner])
        self.assertEqual(mention_order(mentions), ["Microsoft Loop"])
        self.assertFalse(next(item for item in mentions
                              if item["brand_name"] == "Microsoft Planner")["mentioned"])

    def test_punctuation_alias_is_preserved(self):
        profile = SimpleNamespace(brand_name="La Roche-Posay", domain="laroche-posay.com",
                                  direct_competitor=False)
        self.assertIn("la roche posay", build_brand_aliases(profile))
        self.assertTrue(find_brand_mentions("Try La Roche Posay for this routine.",
                                            [profile])[0]["mentioned"])

    def test_service_and_notebook_parity(self):
        profiles = [
            SimpleNamespace(brand_name="Idealista", domain="idealista.com",
                            direct_competitor=False),
            SimpleNamespace(brand_name="Fotocasa", domain="fotocasa.es",
                            direct_competitor=True),
        ]
        answer = "For Spain, Idealista and Fotocasa are both worth checking. Idealista first."
        bundled = bundled_mentions()
        self.assertEqual(find_brand_mentions(answer, profiles),
                         bundled["find_brand_mentions"](answer, profiles))
        self.assertEqual(mention_order(find_brand_mentions(answer, profiles)),
                         bundled["mention_order"](bundled["find_brand_mentions"](
                             answer, profiles)))


if __name__ == "__main__":
    unittest.main()
