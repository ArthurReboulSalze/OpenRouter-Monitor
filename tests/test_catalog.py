import json
import time
import unittest
from unittest.mock import MagicMock, patch

import model_catalog as catalog


class CatalogTests(unittest.TestCase):
    def model(self, **overrides):
        return catalog.enrich_model({"id": "sample/model", "name": "Sample Model", **overrides})

    def test_categories_follow_output_and_not_input(self):
        vision = self.model(architecture={"input_modalities": ["text", "image", "video"], "output_modalities": ["text"]})
        self.assertEqual(catalog.filter_models([vision], category="video"), [])
        self.assertEqual(catalog.filter_models([vision], category="image"), [])
        self.assertEqual(catalog.filter_models([vision], category="text"), [vision])

    def test_multi_output_models_belong_to_both_categories(self):
        image = self.model(architecture={"output_modalities": ["image", "text"]})
        for category in ("image", "text"):
            self.assertEqual(catalog.filter_models([image], category=category), [image])

    def test_legacy_cache_is_usable_without_fabricated_rank_or_date(self):
        legacy = self.model()
        self.assertEqual(legacy["output_modalities"], ["text"])
        self.assertIsNone(legacy["created"])
        self.assertIsNone(legacy["popularity_rank"])
        self.assertFalse(legacy["promotion_known"])

    def test_fallback_modality_string(self):
        model = self.model(architecture={"modality": "text+image->video+audio"})
        self.assertEqual(model["output_modalities"], ["video", "audio"])

    def test_search_includes_id_description_and_category(self):
        model = self.model(id="provider/compact-1", description="Fast coding assistant", output_modalities=["decisions"])
        for query in (" PROVIDER/COMPACT ", "coding", "decisions"):
            self.assertEqual(catalog.filter_models([model], query=query), [model])

    def test_combined_filters_keep_only_matching_favorite_offer(self):
        offered = self.model(id="a/one", output_modalities=["image"], is_promoted=True,
                             promotion_known=True, promotion_checked_at=time.time(), discount_percent=25)
        text = self.model(id="a/two")
        self.assertEqual(catalog.filter_models([text, offered], category="image", favorites={"a/one"},
                                              only_favorites=True, only_promotions=True), [offered])

    def test_newest_sort_uses_dates_and_keeps_unknown_last(self):
        models = [self.model(id="a/old", created=100), self.model(id="a/unknown"), self.model(id="a/new", created=200)]
        self.assertEqual([model["id"] for model in catalog.sort_models(models, "created", True)],
                         ["a/new", "a/old", "a/unknown"])
        self.assertEqual([model["id"] for model in catalog.sort_models(models, "created", False)],
                         ["a/old", "a/new", "a/unknown"])

    def test_popularity_sort_uses_numeric_official_ranks(self):
        models = [self.model(id="a/tenth", popularity_rank=10), self.model(id="a/second", popularity_rank=2), self.model(id="a/missing")]
        self.assertEqual([m["id"] for m in catalog.sort_models(models, "popularity")], ["a/second", "a/tenth", "a/missing"])

    def test_unknown_price_stays_last_in_both_sort_directions(self):
        models = [self.model(id="a/zero", input_price=0), self.model(id="a/unknown", input_price=None), self.model(id="a/paid", input_price=0.01)]
        for reverse in (True, False):
            self.assertEqual(catalog.sort_models(models, "input", reverse)[-1]["id"], "a/unknown")

    def test_expired_promotion_is_not_advertised(self):
        expired = self.model(is_promoted=True, promotion_known=True, discount_percent=50,
                             promotion_checked_at=time.time() - catalog.PROMOTION_MAX_AGE_SECONDS - 1)
        self.assertFalse(expired["is_promoted"])
        self.assertFalse(expired["promotion_known"])
        self.assertIsNone(expired["discount_percent"])

    def test_promotion_sort_prioritizes_offers_then_largest_discount(self):
        now = time.time()
        models = [self.model(id="a/none"), self.model(id="a/20", is_promoted=True, promotion_known=True,
                                                     promotion_checked_at=now, discount_percent=20),
                  self.model(id="a/50", is_promoted=True, promotion_known=True, promotion_checked_at=now, discount_percent=50)]
        self.assertEqual([m["id"] for m in catalog.sort_models(models, "promotion", True)], ["a/50", "a/20", "a/none"])

    def test_promotion_parser_ignores_banner_and_description(self):
        html = '''<div>50% off all models!</div>
        <a href="/vendor/one"><h3>One</h3></a><p>Previously 80% off</p>
        <span class="text-xs text-positive-text">25<!-- -->% off</span>
        <a href="/vendor/two"><h3>Two</h3></a><span>90% off</span>
        <span class="text-positive-text">50% off</span>'''
        self.assertEqual(catalog.parse_promotions(html), {"vendor/one": 25, "vendor/two": 50})

    def test_promotion_parser_detects_changed_markup(self):
        with self.assertRaises(ValueError):
            catalog.parse_promotions("<html>Unavailable</html>")

    def test_empty_promotion_collection_is_valid(self):
        self.assertEqual(catalog.parse_promotions('<script>{"numberOfItems":0}</script>'), {})

    def test_bad_numeric_metadata_is_safe(self):
        for value in ("nan", "inf", "invalid", None):
            model = self.model(created=value, popularity_rank=value)
            self.assertIsNone(model["created"])
            self.assertIsNone(model["popularity_rank"])

    def test_catalog_requests_all_modalities_and_handles_pagination(self):
        first = MagicMock()
        first.json.return_value = {"data": [{"id": "vendor/a"}], "links": {"next": "?page=2"}}
        second = MagicMock()
        second.json.return_value = {"data": [{"id": "vendor/a"}, {"id": "vendor/b"}], "links": {"next": None}}
        promotion = MagicMock()
        promotion.text = '<a href="/vendor/b"><h3>B</h3></a><span class="text-positive-text">40% off</span>'
        session = MagicMock()
        session.get.side_effect = [first, second, promotion]
        with patch.object(catalog.requests, "Session") as factory:
            factory.return_value.__enter__.return_value = session
            models = catalog.fetch_catalog()
        self.assertEqual(session.get.call_args_list[0].kwargs["params"], {"output_modalities": "all", "sort": "most-popular"})
        self.assertEqual([m["popularity_rank"] for m in models], [1, 2])
        self.assertFalse(models[0]["is_promoted"])
        self.assertEqual(models[1]["discount_percent"], 40)

    def test_promotion_failure_does_not_discard_the_catalog(self):
        response = MagicMock()
        response.json.return_value = {"data": [{"id": "vendor/a"}]}
        session = MagicMock()
        session.get.side_effect = [response, catalog.requests.RequestException("offline")]
        with patch.object(catalog.requests, "Session") as factory:
            factory.return_value.__enter__.return_value = session
            models = catalog.fetch_catalog()
        self.assertEqual(len(models), 1)
        self.assertFalse(models[0]["promotion_known"])

    def test_pagination_does_not_send_credentials_to_another_host(self):
        response = MagicMock()
        response.json.return_value = {"data": [], "links": {"next": "https://other.example/models"}}
        session = MagicMock()
        session.get.return_value = response
        with patch.object(catalog.requests, "Session") as factory:
            factory.return_value.__enter__.return_value = session
            with self.assertRaises(ValueError):
                catalog.fetch_catalog("test-key")
        self.assertEqual(session.get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
