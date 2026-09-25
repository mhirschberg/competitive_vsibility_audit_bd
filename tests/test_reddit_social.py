import json
import unittest
from types import SimpleNamespace
from unittest import mock

import reddit_social as social


def profile(name="Acme", products=None):
    return SimpleNamespace(
        brand_name=name,
        relevant_products=products or ["Widget Pro"],
    )


class RedditUrlTests(unittest.TestCase):
    def test_explicit_audit_focus_drives_first_queries(self):
        target = profile(
            "Rayner",
            ["RayOne family of preloaded intraocular lenses (IOLs)"],
        )

        queries = social.build_reddit_queries(
            target,
            ["presbyopia-correcting intraocular lenses"],
            "RayOne Galaxy",
        )

        self.assertEqual(
            queries,
            [
                "Rayner RayOne Galaxy",
                "Rayner presbyopia-correcting intraocular lenses",
                "Rayner review",
            ],
        )

    def test_skincare_queries_do_not_inherit_industry_terms(self):
        target = profile("CeraVe", ["Moisturizing Cream"])

        queries = social.build_reddit_queries(
            target,
            ["moisturizer for dry sensitive skin"],
            "Moisturizing Cream",
        )

        self.assertEqual(
            queries,
            [
                "CeraVe Moisturizing Cream",
                "CeraVe moisturizer for dry sensitive skin",
                "CeraVe review",
            ],
        )

    def test_marketplace_queries_use_the_same_neutral_template(self):
        target = profile("Auto Trader", ["Used-car marketplace"])

        queries = social.build_reddit_queries(
            target,
            ["buy used cars online uk"],
            "Used-car marketplace",
        )

        self.assertEqual(
            queries,
            [
                "Auto Trader Used-car marketplace",
                "Auto Trader buy used cars online uk",
                "Auto Trader review",
            ],
        )

    def test_market_suffix_is_not_required_for_brand_discovery(self):
        target = profile("Carwow Germany", ["Online automotive marketplace"])

        queries = social.build_reddit_queries(
            target,
            ["Gebrauchtwagen online kaufen"],
            "Online-Fahrzeugmarkt",
        )

        self.assertEqual(
            queries,
            [
                "Carwow Online-Fahrzeugmarkt",
                "Carwow Gebrauchtwagen online kaufen",
                "Carwow review",
            ],
        )
        self.assertGreater(
            social._target_relevance_score_text(
                "Has anyone bought a car through Carwow?",
                target,
            ),
            0,
        )

    def test_early_queries_are_available_before_profiles(self):
        queries = social.build_early_reddit_queries(
            "AutoScout24",
            [
                "gebrauchte autos online kaufen",
                "gebrauchtwagen mit finanzierung suchen",
            ],
        )

        self.assertEqual(
            queries,
            [
                "AutoScout24 gebrauchte autos online kaufen",
                "AutoScout24 gebrauchtwagen mit finanzierung suchen",
                "AutoScout24 review",
            ],
        )

    def test_queries_use_specific_product_and_category_terms(self):
        target = profile(
            "Rayner",
            ["RayOne family of preloaded intraocular lenses (IOLs)"],
        )
        queries = social.build_reddit_queries(
            target,
            ["presbyopia-correcting intraocular lenses for cataract surgery"],
        )
        self.assertEqual(
            queries,
            [
                "Rayner RayOne",
                "Rayner presbyopia-correcting intraocular lenses for cataract surgery",
                "Rayner review",
            ],
        )

    def test_empty_reddit_serp_response_retries_and_warns(self):
        response = mock.Mock(
            ok=True,
            status_code=200,
            text="",
            headers={
                "x-brd-error-code": "captcha",
                "x-brd-error": "redirect location was rejected",
            },
        )
        client = SimpleNamespace(
            headers={"Authorization": "Bearer test"},
            country="DE",
            serp_zone="serp",
        )
        with (
            mock.patch.object(social, "BD_REQUEST_URL", "https://example.test/request", create=True),
            mock.patch.object(social, "bd_client", client, create=True),
            mock.patch.object(social.reddit_requests, "post", return_value=response) as post,
            mock.patch.object(social.time, "sleep"),
            mock.patch.object(social, "BrightDataAPIError", RuntimeError, create=True),
        ):
            result = social._discover_reddit_with_serp(["AutoScout24 Gebrauchtwagen"])

        self.assertEqual(result["records"], [])
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("after 3 attempt(s)", result["warnings"][0])
        self.assertIn("captcha", result["warnings"][0])
        self.assertEqual(post.call_count, 3)

    def test_reddit_serp_uses_second_result_after_empty_http_200(self):
        empty = mock.Mock(ok=True, status_code=200, text="", headers={})
        valid = mock.Mock(ok=True, status_code=200, text="json")
        client = SimpleNamespace(
            headers={"Authorization": "Bearer test"},
            country="DE",
            serp_zone="serp",
        )
        with (
            mock.patch.object(social, "BD_REQUEST_URL", "https://example.test/request", create=True),
            mock.patch.object(social, "bd_client", client, create=True),
            mock.patch.object(social.reddit_requests, "post", side_effect=[empty, valid]) as post,
            mock.patch.object(social.time, "sleep"),
            mock.patch.object(social, "BrightDataAPIError", RuntimeError, create=True),
            mock.patch.object(social, "is_google_goto_url", return_value=False, create=True),
            mock.patch.object(
                social,
                "decode_bright_data_response",
                return_value={"organic": [{
                        "link": "https://www.reddit.com/r/CataractSurgery/comments/abc123/a_review/",
                        "title": "A review",
                    }]},
                create=True,
            ),
        ):
            result = social._discover_reddit_with_serp(["Rayner Galaxy"])

        self.assertEqual(post.call_count, 2)
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["records"][0]["post_id"], "abc123")

    def test_extracts_and_canonicalizes_post_urls(self):
        self.assertEqual(social.reddit_post_id("t3_AbC123"), "abc123")
        self.assertEqual(
            social.canonical_reddit_url(
                "https://old.reddit.com/r/widgets/comments/AbC123/a_title/?utm_source=x"
            ),
            "https://www.reddit.com/r/widgets/comments/AbC123/a_title/",
        )
        self.assertEqual(
            social.canonical_reddit_url("https://redd.it/abc123"),
            "https://www.reddit.com/comments/abc123/",
        )

    def test_merges_three_discovery_paths_by_post_id(self):
        native = [
            {
                "post_id": "same123",
                "title": "Native title",
                "url": "https://www.reddit.com/r/a/comments/same123/native/",
            }
        ]
        serp = [
            {
                "post_id": "same123",
                "url": "https://www.reddit.com/r/a/comments/same123/serp/",
                "title": "SERP title",
                "description": "Snippet",
                "source": "serp",
                "source_rank": 2,
            }
        ]
        existing = {
            "results": [
                {"url": "https://www.reddit.com/r/a/comments/same123/existing/"},
                {"url": "https://www.reddit.com/r/b/comments/other99/another/"},
            ]
        }

        merged = social.merge_reddit_candidates(native, serp, existing)
        by_id = {item["post_id"]: item for item in merged}

        self.assertEqual(set(by_id), {"same123", "other99"})
        self.assertEqual(
            set(by_id["same123"]["sources"]),
            {"native_reddit", "serp", "audit_serp"},
        )
        self.assertEqual(by_id["same123"]["description"], "Snippet")

    def test_native_keyword_discovery_sends_required_date_filter(self):
        response = mock.Mock(ok=True, status_code=200, text="[]")
        response.json.return_value = []
        client = SimpleNamespace(
            headers={"Authorization": "Bearer test"},
            normalize_records=lambda value: value,
        )
        with (
            mock.patch.object(social, "BD_TRIGGER_URL", "https://example.test/trigger", create=True),
            mock.patch.object(social, "bd_client", client, create=True),
            mock.patch.object(social.reddit_requests, "post", return_value=response) as post,
        ):
            result = social._trigger_native_reddit_discovery(
                ["Acme review", "Acme pricing"]
            )

        self.assertEqual(
            result,
            {
                "queries": ["Acme review"],
                "records": [],
                "snapshots": [],
                "snapshot_manifest": [],
                "race_width": 3,
                "warnings": [],
            },
        )
        self.assertEqual(post.call_count, 3)
        request = post.call_args.kwargs
        self.assertEqual(request["params"]["discover_by"], "keyword")
        self.assertEqual(request["json"]["input"][0]["date"], "Past year")
        self.assertEqual(
            [item["keyword"] for item in request["json"]["input"]],
            ["Acme review"],
        )

    def test_compact_term_removes_profile_markup_and_dangling_conjunction(self):
        self.assertEqual(
            social._compact_reddit_term(
                "[Shark FlexStyle 4-in-1 Air Styler & Hair Dryer]",
                6,
            ),
            "Shark FlexStyle 4-in-1 Air Styler",
        )

    def test_offering_label_removes_embedded_shopping_link(self):
        self.assertEqual(
            social._clean_reddit_offering(
                "[BaByliss Air Wand](/search?ibp=oshop&product=123)"
            ),
            "BaByliss Air Wand",
        )

    def test_only_competitive_landscape_profile_links_are_cleaned(self):
        report = """# Audit

## Competitive Landscape

- Relevant offerings: [BaByliss Air Wand](/search?product=123)

## Observed AI Sources

- [Publisher article](https://example.com/article)
"""

        cleaned = social.clean_competitive_landscape_profile_links(report)

        self.assertIn("Relevant offerings: BaByliss Air Wand", cleaned)
        self.assertIn(
            "[Publisher article](https://example.com/article)",
            cleaned,
        )

    def test_native_snapshot_race_uses_first_ready_result(self):
        native = {
            "queries": ["Acme review"],
            "records": [],
            "snapshots": [
                {"snapshot_id": "slow-1"},
                {"snapshot_id": "winner"},
                {"snapshot_id": "slow-2"},
            ],
            "race_width": 3,
            "warnings": [],
        }
        client = SimpleNamespace(
            snapshot_status=lambda snapshot_id: {
                "status": "ready" if snapshot_id == "winner" else "running"
            },
            download_snapshot=lambda snapshot_id: [
                {"post_id": "abc123", "snapshot": snapshot_id}
            ],
        )
        with mock.patch.object(social, "bd_client", client, create=True):
            result = social._wait_for_native_reddit_discovery(native)

        self.assertEqual(result["winner_snapshot_id"], "winner")
        self.assertEqual(result["records"][0]["snapshot"], "winner")

    def test_prefetch_starts_target_competitors_and_category_together(self):
        target = profile("Acme")
        target.category = "Widgets"
        competitors = [profile("Other"), profile("Third")]

        def trigger(queries, race_width=None, context="Reddit discovery"):
            return {
                "queries": queries,
                "records": [],
                "snapshots": [{"snapshot_id": queries[0]}],
                "snapshot_manifest": [],
                "race_width": 3,
                "warnings": [],
            }

        def wait(native, context="Reddit discovery"):
            return {
                **native,
                "records": [{"post_id": native["queries"][0]}],
                "winner_snapshot_id": native["snapshots"][0]["snapshot_id"],
            }

        with (
            mock.patch.object(
                social,
                "_trigger_native_reddit_discovery",
                side_effect=trigger,
            ) as trigger_mock,
            mock.patch.object(
                social,
                "_wait_for_native_reddit_discovery",
                side_effect=wait,
            ),
        ):
            result = social.run_reddit_discovery_prefetch_sync(
                target,
                competitors,
                ["best widgets", "cheap widgets"],
                "Widget Pro",
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(trigger_mock.call_count, 4)
        self.assertEqual(
            set(result["cohorts"]),
            {
                "target:acme",
                "competitor:other",
                "competitor:third",
                "category",
            },
        )

    def test_comparable_offering_validator_requires_same_typed_scope(self):
        social.parse_ai_json = json.loads
        validator = social._competitor_focus_validator(
            {"Dealer B": ["Used-car marketplace"]}
        )

        valid = validator(
            json.dumps(
                {
                    "comparison_type": "marketplace",
                    "selections": [
                        {
                            "brand": "Dealer B",
                            "offering": "Used-car marketplace",
                        }
                    ],
                }
            )
        )
        invalid = validator(
            json.dumps(
                {
                    "comparison_type": "automotive",
                    "selections": [
                        {
                            "brand": "Dealer B",
                            "offering": "Used-car marketplace",
                        }
                    ],
                }
            )
        )

        self.assertTrue(valid["valid"])
        self.assertFalse(invalid["valid"])

    def test_comparable_offering_validator_allows_evidence_derived_scope(self):
        social.parse_ai_json = json.loads
        validator = social._competitor_focus_validator(
            {"Samsung": [], "Google": []}
        )

        valid = validator(
            json.dumps(
                {
                    "comparison_type": "physical_product",
                    "selections": [
                        {"brand": "Samsung", "offering": "Galaxy S series"},
                        {"brand": "Google", "offering": "Pixel series"},
                    ],
                }
            )
        )
        brand_only = validator(
            json.dumps(
                {
                    "comparison_type": "physical_product",
                    "selections": [
                        {"brand": "Samsung", "offering": "Samsung"},
                        {"brand": "Google", "offering": "Google products"},
                    ],
                }
            )
        )

        self.assertTrue(valid["valid"])
        self.assertFalse(brand_only["valid"])

    def test_missing_profiles_infer_competitor_offerings_from_evidence(self):
        target = profile("Apple", ["iPhone"])
        samsung = profile("Samsung", [])
        samsung.relevant_products = []
        samsung.competitor_reason = (
            "Samsung offers flagship smartphones such as the Galaxy S and Z "
            "series that directly substitute for iPhone."
        )
        samsung.evidence = []
        google = profile("Google", [])
        google.relevant_products = []
        google.competitor_reason = (
            "Google manufactures the Pixel series of high-end smartphones."
        )
        google.evidence = []
        race_answer = json.dumps(
            {
                "comparison_type": "physical_product",
                "selections": [
                    {"brand": "Samsung", "offering": "Galaxy S series"},
                    {"brand": "Google", "offering": "Pixel series"},
                ],
            }
        )

        with mock.patch.object(
            social,
            "race_utility_ai",
            return_value={
                "answer": race_answer,
                "engine_name": "Gemini",
                "snapshot_id": "scope-1",
                "all_snapshot_ids": {"gemini": "scope-1"},
                "race_duration_seconds": 1.5,
            },
            create=True,
        ) as race_mock:
            offerings, metadata, warnings = (
                social.choose_competitor_reddit_offerings(
                    target,
                    [samsung, google],
                    "iPhone",
                    ["high-end smartphone"],
                )
            )

        self.assertEqual(
            offerings,
            {"Samsung": "Galaxy S series", "Google": "Pixel series"},
        )
        self.assertEqual(metadata["comparison_type"], "physical_product")
        self.assertEqual(
            metadata["evidence_inferred_brands"], ["Samsung", "Google"]
        )
        self.assertEqual(warnings, [])
        prompt = race_mock.call_args.kwargs["prompt"]
        self.assertIn("Galaxy S and Z series", prompt)
        self.assertIn("Pixel series", prompt)

    def test_deterministic_fallback_uses_evidence_not_bare_brand(self):
        target = profile("Apple", ["iPhone"])
        samsung = profile("Samsung", [])
        samsung.relevant_products = []
        samsung.competitor_reason = (
            "Samsung offers phones such as the Galaxy S series."
        )
        samsung.evidence = []
        google = profile("Google", [])
        google.relevant_products = []
        google.competitor_reason = (
            "Google manufactures the Pixel series of high-end smartphones."
        )
        google.evidence = []

        with mock.patch.object(
            social,
            "race_utility_ai",
            side_effect=RuntimeError("scope race unavailable"),
            create=True,
        ):
            offerings, metadata, warnings = (
                social.choose_competitor_reddit_offerings(
                    target,
                    [samsung, google],
                    "iPhone",
                    ["high-end smartphone"],
                )
            )

        self.assertEqual(
            offerings,
            {"Samsung": "Galaxy S series", "Google": "Pixel series"},
        )
        self.assertEqual(metadata["engine"], "deterministic-fallback")
        self.assertEqual(
            metadata["evidence_inferred_brands"], ["Samsung", "Google"]
        )
        self.assertEqual(len(warnings), 1)


class RedditSelectionTests(unittest.TestCase):
    def test_fallback_profile_requires_recovered_product_focus(self):
        fallback = profile("Google", [])
        fallback.relevant_products = []
        scoped = social._scoped_reddit_profile(fallback, "Pixel series")
        posts = [
            {
                "post_id": "reviews",
                "title": "How to get more Google Reviews for my business?",
                "description": "Local SEO discussion",
                "community_name": "localseo",
                "num_upvotes": 100,
                "num_comments": 30,
                "sources": ["native_reddit"],
                "best_rank": 1,
            },
            {
                "post_id": "pixel",
                "title": "Pixel 10 Pro long-term review",
                "description": "Thinking of switching to a Google phone",
                "community_name": "GooglePixel",
                "num_upvotes": 5,
                "num_comments": 2,
                "sources": ["serp"],
                "best_rank": 3,
            },
        ]

        selected = social.select_reddit_sample(posts, scoped)

        self.assertEqual([item["post_id"] for item in selected], ["pixel"])

    def test_selection_excludes_similar_but_different_product_names(self):
        target = profile(
            "Rayner",
            ["RayOne family of preloaded intraocular lenses (IOLs)"],
        )
        posts = [
            {
                "post_id": "right1",
                "url": "https://www.reddit.com/comments/right1/",
                "title": "RayOne Galaxy after cataract surgery",
                "description": "",
                "community_name": "CataractSurgery",
                "num_upvotes": 1,
                "num_comments": 2,
                "sources": ["serp"],
                "best_rank": 2,
            },
            {
                "post_id": "wrong1",
                "url": "https://www.reddit.com/comments/wrong1/",
                "title": "RayNeo GT glasses review",
                "description": "",
                "community_name": "RayNeo",
                "num_upvotes": 500,
                "num_comments": 200,
                "sources": ["serp", "native_reddit"],
                "best_rank": 1,
            },
        ]

        selected = social.select_reddit_sample(posts, target)

        self.assertEqual([item["post_id"] for item in selected], ["right1"])

    def test_candidate_sorting_prioritizes_explicit_target_match(self):
        target = profile(
            "Rayner",
            ["RayOne family of preloaded intraocular lenses (IOLs)"],
        )
        candidates = [
            {
                "post_id": "wrong1",
                "url": "https://www.reddit.com/comments/wrong1/",
                "title": "RayNeo GT review",
                "description": "",
                "sources": ["serp", "native_reddit"],
                "best_rank": 1,
            },
            {
                "post_id": "right1",
                "url": "https://www.reddit.com/comments/right1/",
                "title": "RayOne Galaxy experience",
                "description": "",
                "sources": ["serp"],
                "best_rank": 8,
            },
        ]

        ordered = social._sorted_reddit_candidates(candidates, target)

        self.assertEqual(ordered[0]["post_id"], "right1")

    def test_selection_caps_each_community_before_filling_remainder(self):
        posts = []
        for index in range(12):
            posts.append(
                {
                    "post_id": f"post{index}",
                    "url": f"https://www.reddit.com/comments/post{index}/",
                    "title": f"Acme Widget Pro review {index}",
                    "description": "",
                    "community_name": "widgets" if index < 8 else f"group{index}",
                    "num_upvotes": 100 - index,
                    "num_comments": 10,
                    "sources": ["serp"],
                    "best_rank": index + 1,
                }
            )

        selected = social.select_reddit_sample(posts, profile())

        self.assertEqual(len(selected), 10)
        first_pass_widgets = [
            item for item in selected[:7] if item["community_name"] == "widgets"
        ]
        self.assertLessEqual(len(first_pass_widgets), 3)

    def test_selection_removes_same_title_crossposts(self):
        posts = [
            {
                "post_id": "crosspost1",
                "url": "https://www.reddit.com/comments/crosspost1/",
                "title": "Is this Acme deal too good to be true?",
                "description": "",
                "community_name": "group-one",
                "num_upvotes": 20,
                "num_comments": 5,
                "sources": ["serp"],
                "best_rank": 1,
            },
            {
                "post_id": "crosspost2",
                "url": "https://www.reddit.com/comments/crosspost2/",
                "title": "Is this Acme deal too good to be true?",
                "description": "",
                "community_name": "group-two",
                "num_upvotes": 10,
                "num_comments": 2,
                "sources": ["serp"],
                "best_rank": 2,
            },
        ]

        selected = social.select_reddit_sample(posts, profile())

        self.assertEqual([item["post_id"] for item in selected], ["crosspost1"])


class RedditAnalysisTests(unittest.TestCase):
    def setUp(self):
        social.parse_ai_json = json.loads

    def test_prompt_remains_complete_json_under_engine_limit(self):
        posts = [
            {
                "post_id": f"p{index}",
                "title": "T" * 300,
                "description": "B" * 900,
                "comments": [{"text": "C" * 500}, {"text": "D" * 500}],
            }
            for index in range(5)
        ]

        prompt_text = social._reddit_analysis_prompt(
            posts,
            profile(),
            [profile("Other")],
        )

        self.assertLessEqual(len(prompt_text), 4096)
        compact = json.loads(prompt_text.split("\nPosts: ", 1)[1])
        self.assertEqual([item["post_id"] for item in compact], [f"p{i}" for i in range(5)])

    def test_validator_sanitizes_non_verbatim_evidence_and_normalizes_labels(self):
        posts = [
            {
                "post_id": "abc123",
                "title": "Acme is comfortable",
                "description": "I have used it for a year.",
                "comments": [],
            }
        ]
        validator = social._reddit_analysis_validator(posts)
        valid = validator(
            json.dumps(
                {
                    "items": [
                        {
                            "post_id": "abc123",
                            "relevant": True,
                            "content_type": "firsthand_experience",
                            "experience_type": "firsthand",
                            "stance": "favorable",
                            "themes": ["Comfort"],
                            "pain_points": [],
                            "desired_outcomes": ["Easy daily use"],
                            "compared_brands": ["Other"],
                            "evidence_excerpt": "used it for a year",
                            "confidence": 0.9,
                        }
                    ]
                }
            )
        )

        self.assertTrue(valid["valid"])
        cleaned = json.loads(valid["cleaned_answer"])["items"][0]
        self.assertEqual(cleaned["themes"], ["comfort"])
        self.assertEqual(cleaned["desired_outcomes"], ["easy daily use"])

        invalid_payload = json.loads(valid["cleaned_answer"])
        invalid_payload["items"][0]["evidence_excerpt"] = "invented quote"
        sanitized = validator(json.dumps(invalid_payload))
        self.assertTrue(sanitized["valid"])
        self.assertEqual(
            json.loads(sanitized["cleaned_answer"])["items"][0]["evidence_excerpt"],
            "",
        )

    def test_validator_normalizes_equivalent_enum_labels(self):
        posts = [
            {
                "post_id": "abc123",
                "title": "I used this for a year",
                "description": "It worked well.",
                "comments": [],
            }
        ]
        validator = social._reddit_analysis_validator(posts)
        result = validator(
            json.dumps(
                {
                    "items": [
                        {
                            "post_id": "abc123",
                            "relevant": True,
                            "content_type": "personal experience",
                            "experience_type": "first-hand",
                            "stance": "positive",
                            "themes": [],
                            "pain_points": [],
                            "desired_outcomes": [],
                            "compared_brands": [],
                            "evidence_excerpt": "used this for a year",
                            "confidence": 0.8,
                        }
                    ]
                }
            )
        )

        self.assertTrue(result["valid"])
        cleaned = json.loads(result["cleaned_answer"])["items"][0]
        self.assertEqual(cleaned["content_type"], "firsthand_experience")
        self.assertEqual(cleaned["experience_type"], "firsthand")
        self.assertEqual(cleaned["stance"], "favorable")

    def test_failed_batch_retries_individually_and_stays_unclassified(self):
        posts = [
            {
                "post_id": f"post{index}",
                "title": f"Acme discussion {index}",
                "description": "",
                "comments": [],
            }
            for index in range(2)
        ]

        with mock.patch.object(
            social,
            "race_utility_ai",
            side_effect=RuntimeError("classification unavailable"),
            create=True,
        ) as race:
            analyses, races, warnings = social.analyze_reddit_posts(
                posts,
                profile(),
                [profile("Other")],
                "Acme",
            )

        self.assertEqual(race.call_count, 3)
        self.assertEqual(races, [])
        self.assertEqual(len(warnings), 3)
        self.assertTrue(
            all(item["classification_status"] == "unclassified" for item in analyses)
        )
        self.assertTrue(all(item["relevant"] is None for item in analyses))

        sample = [
            {"post_id": item["post_id"], "analysis": item}
            for item in analyses
        ]
        metrics = social.aggregate_reddit_analysis(sample)
        self.assertEqual(metrics["classified_posts"], 0)
        self.assertEqual(metrics["unclassified_posts"], 2)
        self.assertEqual(metrics["relevant_posts"], 0)

    def test_failed_race_snapshot_ids_are_recoverable_for_manifest(self):
        error = RuntimeError(
            'Neither engine returned a valid result. '
            '[{"engine":"Gemini","snapshot_id":"gem-1","status":"invalid"},'
            '{"engine":"ChatGPT","snapshot_id":"gpt-1","status":"timeout"}]'
        )

        metadata = social._failed_race_metadata(
            error,
            "classification batch 1/2",
        )

        self.assertEqual(
            metadata["all_snapshot_ids"],
            {"gemini": "gem-1", "chatgpt": "gpt-1"},
        )
        self.assertEqual(
            metadata["attempt_statuses"],
            {"gemini": "invalid", "chatgpt": "timeout"},
        )

    def test_social_snapshot_manifest_keeps_operation_and_context(self):
        response = mock.Mock(status_code=202, text='{"snapshot_id":"snap-1"}')
        client = SimpleNamespace(
            headers={"Authorization": "Bearer test"},
            snapshot_status=lambda snapshot_id: {"status": "ready"},
            download_snapshot=lambda snapshot_id: [{"post_id": "abc123"}],
            normalize_records=lambda value: value,
            log=lambda *args, **kwargs: None,
        )
        manifest = []
        with (
            mock.patch.object(social, "BD_SCRAPE_URL", "https://example.test/scrape", create=True),
            mock.patch.object(social, "bd_client", client, create=True),
            mock.patch.object(social.reddit_requests, "post", return_value=response),
            mock.patch.object(
                social,
                "decode_bright_data_response",
                return_value={"snapshot_id": "snap-1"},
                create=True,
            ),
        ):
            records = social._scrape_reddit_dataset(
                social.REDDIT_POSTS_DATASET_ID,
                {"input": [{"url": "https://reddit.test/post"}]},
                60,
                "AutoScout24",
                "post hydration",
                manifest,
            )

        self.assertEqual(records, [{"post_id": "abc123"}])
        self.assertEqual(
            manifest[0],
            {
                "context": "AutoScout24",
                "operation": "post hydration",
                "dataset_id": social.REDDIT_POSTS_DATASET_ID,
                "snapshot_id": "snap-1",
                "status": "ready",
                "duration_seconds": mock.ANY,
                "record_count": 1,
            },
        )

    def test_social_log_does_not_pass_none_as_a_rich_color(self):
        calls = []

        def log(*args):
            calls.append(args)
            if len(args) > 1 and args[1] is None:
                raise AssertionError("None must not be passed as a Rich color")

        with mock.patch.object(
            social,
            "bd_client",
            SimpleNamespace(log=log),
            create=True,
        ):
            social._reddit_log("Mobile.de", "snapshot started")

        self.assertEqual(
            calls,
            [("[Social · Mobile.de] snapshot started",)],
        )

    def test_social_snapshot_timeout_uses_the_notebook_exception_contract(self):
        class ExpectedTimeout(TimeoutError):
            def __init__(self, snapshot_id, timeout_seconds):
                self.snapshot_id = snapshot_id
                self.timeout_seconds = timeout_seconds

        entry = {"status": "triggered"}
        client = SimpleNamespace(
            snapshot_status=lambda snapshot_id: {"status": "running"},
            log=lambda *args: None,
        )
        with (
            mock.patch.object(social, "bd_client", client, create=True),
            mock.patch.object(
                social,
                "SnapshotTimeoutError",
                ExpectedTimeout,
                create=True,
            ),
            mock.patch.object(
                social.time,
                "monotonic",
                side_effect=[0, 61],
            ),
        ):
            with self.assertRaises(ExpectedTimeout) as raised:
                social._wait_reddit_snapshot(
                    "snap-timeout",
                    60,
                    "Kleinanzeigen",
                    "comment collection",
                    entry,
                )

        self.assertEqual(raised.exception.snapshot_id, "snap-timeout")
        self.assertEqual(raised.exception.timeout_seconds, 60)
        self.assertEqual(entry["status"], "timeout")

    def test_report_discloses_and_excludes_unclassified_threads(self):
        sample = [
            {
                "post_id": "unknown1",
                "title": "Unclassified thread",
                "analysis": {
                    "classification_status": "unclassified",
                    "relevant": None,
                },
            }
        ]
        metrics = social.aggregate_reddit_analysis(sample)
        result = {
            "status": "partial",
            "mode": "competitive",
            "comparison_type": "marketplace",
            "unique_thread_count": 1,
            "cohorts": [
                {
                    "role": "target",
                    "brand": "Acme",
                    "focus": "Marketplace",
                    "sample": sample,
                    "metrics": metrics,
                }
            ],
        }

        report = social.build_competitive_reddit_report_section(result)

        self.assertIn("Classification note", report)
        self.assertIn("### Cohort Coverage", report)
        self.assertIn("### Conversation Signals", report)
        self.assertIn("| Acme | target | Marketplace | 1 | 0 | 1 | 0 |", report)
        self.assertNotIn("| Brand | Role | Comparable offering | Sampled | Classified | Unclassified | Relevant | First-hand", report)
        self.assertNotIn("[Unclassified thread]", report)

    def test_aggregation_and_report_are_deterministic(self):
        posts = [
            {
                "post_id": "abc123",
                "url": "https://www.reddit.com/comments/abc123/",
                "title": "A useful thread",
                "community_name": "widgets",
                "analysis": {
                    "relevant": True,
                    "content_type": "firsthand_experience",
                    "experience_type": "firsthand",
                    "stance": "mixed",
                    "themes": ["comfort"],
                    "pain_points": ["price"],
                    "desired_outcomes": ["easy use"],
                    "compared_brands": ["Other"],
                    "evidence_excerpt": "A useful thread",
                },
            },
            {
                "post_id": "irrelevant1",
                "url": "https://www.reddit.com/comments/irrelevant1/",
                "title": "Unrelated thread",
                "community_name": "widgets",
                "analysis": {
                    "relevant": False,
                    "content_type": "other",
                    "experience_type": "none",
                    "stance": "unclear",
                    "themes": [],
                    "pain_points": [],
                    "desired_outcomes": [],
                    "compared_brands": [],
                    "evidence_excerpt": "",
                },
            },
        ]
        metrics = social.aggregate_reddit_analysis(posts)
        result = {"status": "success", "sample": posts, "metrics": metrics}

        self.assertEqual(metrics["firsthand_posts"], 1)
        self.assertEqual(metrics["theme_counts"], {"comfort": 1})
        report = social.insert_reddit_report_section(
            "# Audit\n\n## Methodology and Limitations\n\nNotes.",
            result,
        )
        self.assertIn("## Reddit Conversation Snapshot", report)
        self.assertLess(
            report.index("## Reddit Conversation Snapshot"),
            report.index("## Methodology and Limitations"),
        )
        self.assertEqual(report.count("## Reddit Conversation Snapshot"), 1)
        self.assertNotIn("Unrelated thread", report)
        self.assertEqual(social.insert_reddit_report_section(report, result), report)

        empty_report = social.insert_reddit_report_section(
            "# Audit\n\n## Methodology and Limitations\n\nNotes.",
            {"status": "failed", "sample": [], "metrics": {}},
        )
        replaced = social.insert_reddit_report_section(empty_report, result)
        self.assertEqual(replaced.count("## Reddit Conversation Snapshot"), 1)
        self.assertIn("A useful thread", replaced)
        self.assertNotIn("No usable Reddit threads", replaced)

    def test_collection_failures_degrade_to_candidate_evidence(self):
        native = {
            "records": [
                {
                    "post_id": "abc123",
                    "url": "https://www.reddit.com/r/widgets/comments/abc123/review/",
                    "title": "Acme review",
                    "description": "Useful experience",
                }
            ],
            "snapshot_id": "snapshot-1",
        }
        analysis = {
            "post_id": "abc123",
            "relevant": True,
            "content_type": "firsthand_experience",
            "experience_type": "firsthand",
            "stance": "mixed",
            "themes": ["comfort"],
            "pain_points": [],
            "desired_outcomes": [],
            "compared_brands": [],
            "evidence_excerpt": "Useful experience",
            "confidence": 0.8,
        }

        with (
            mock.patch.object(social, "_trigger_native_reddit_discovery", return_value=native),
            mock.patch.object(social, "_discover_reddit_with_serp", return_value=[]),
            mock.patch.object(social, "_collect_reddit_posts", side_effect=RuntimeError("posts down")),
            mock.patch.object(social, "_collect_reddit_comments", side_effect=RuntimeError("comments down")),
            mock.patch.object(
                social,
                "analyze_reddit_posts",
                return_value=([analysis], [], []),
            ),
        ):
            result = social.run_reddit_social_sync(profile(), [], ["widget"], {})

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["sample"]), 1)
        self.assertEqual(result["metrics"]["relevant_posts"], 1)
        self.assertTrue(any("hydration failed" in item for item in result["warnings"]))
        self.assertTrue(any("comment collection failed" in item for item in result["warnings"]))

    def test_native_snapshot_monitor_runs_alongside_fast_serp_sample(self):
        candidates = [
            {
                "post_id": f"post{index}",
                "url": f"https://www.reddit.com/r/widgets/comments/post{index}/thread/",
                "title": f"Acme experience {index}",
                "description": "Useful experience",
                "source": "serp",
                "source_rank": index + 1,
                "query": "Acme Widget",
            }
            for index in range(10)
        ]
        posts = [
            {
                "post_id": item["post_id"],
                "url": item["url"],
                "title": item["title"],
                "description": item["description"],
                "community_name": f"group{index}",
                "num_upvotes": 10,
                "num_comments": 2,
                "sources": ["serp"],
                "best_rank": index + 1,
            }
            for index, item in enumerate(candidates)
        ]
        analyses = [
            {
                "post_id": post["post_id"],
                "relevant": True,
                "content_type": "discussion",
                "experience_type": "unclear",
                "stance": "neutral",
                "themes": [],
                "pain_points": [],
                "desired_outcomes": [],
                "compared_brands": [],
                "evidence_excerpt": "Useful experience",
                "confidence": 0.8,
            }
            for post in posts
        ]
        with (
            mock.patch.object(
                social,
                "_trigger_native_reddit_discovery",
                return_value={
                    "records": [],
                    "snapshots": [
                        {"query": "Acme Widget", "snapshot_id": "snapshot-running"}
                    ],
                    "warnings": [],
                },
            ),
            mock.patch.object(
                social,
                "_discover_reddit_with_serp",
                return_value={"records": candidates, "warnings": []},
            ),
            mock.patch.object(
                social,
                "_wait_for_native_reddit_discovery",
                return_value={
                    "records": [],
                    "snapshots": [
                        {"query": "Acme Widget", "snapshot_id": "snapshot-running"}
                    ],
                    "warnings": [],
                },
            ) as wait,
            mock.patch.object(social, "_collect_reddit_posts", return_value=posts),
            mock.patch.object(social, "_collect_reddit_comments", return_value={}),
            mock.patch.object(
                social,
                "analyze_reddit_posts",
                return_value=(analyses, [], []),
            ),
        ):
            result = social.run_reddit_social_sync(profile(), [], ["widget"], {})

        wait.assert_called_once()
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["discovery"]["native_snapshot_waited"])

    def test_recovered_discovery_warning_keeps_complete_cohort_successful(self):
        candidates = [
            {
                "post_id": f"post{index}",
                "url": f"https://www.reddit.com/r/widgets/comments/post{index}/thread/",
                "title": f"Acme experience {index}",
                "description": "Useful experience",
                "source": "native_reddit",
            }
            for index in range(10)
        ]
        analyses = [
            {
                "post_id": item["post_id"],
                "relevant": True,
                "classification_status": "classified",
            }
            for item in candidates
        ]
        with (
            mock.patch.object(
                social,
                "_trigger_native_reddit_discovery",
                return_value={"records": candidates, "warnings": []},
            ),
            mock.patch.object(
                social,
                "_discover_reddit_with_serp",
                return_value={
                    "records": [],
                    "warnings": ["Reddit SERP query failed: HTTP 502"],
                },
            ),
            mock.patch.object(social, "_collect_reddit_posts", return_value=candidates),
            mock.patch.object(social, "_collect_reddit_comments", return_value={}),
            mock.patch.object(
                social,
                "analyze_reddit_posts",
                return_value=(analyses, [], []),
            ),
        ):
            result = social.run_reddit_social_sync(profile(), [], ["widget"], {})

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["warnings"])

    def test_normalize_result_status_keeps_recovered_warnings_as_diagnostics(self):
        sample = [
            {
                "post_id": f"post{index}",
                "analysis": {"classification_status": "classified"},
            }
            for index in range(10)
        ]
        result = social.normalize_reddit_result_status(
            {
                "status": "partial",
                "cohorts": [
                    {
                        "role": "target",
                        "brand": "Acme",
                        "status": "partial",
                        "sample": sample,
                        "warnings": ["Reddit SERP query failed: HTTP 502"],
                    },
                    {
                        "role": "competitor",
                        "brand": "Other",
                        "status": "partial",
                        "sample": sample,
                        "warnings": [
                            "Reddit AI classification batch failed; "
                            "retrying each post"
                        ],
                    },
                ],
                "warnings": ["diagnostic only"],
            }
        )

        self.assertEqual(result["status"], "success")
        self.assertTrue(all(item["status"] == "success" for item in result["cohorts"]))
        self.assertEqual(result["warnings"], ["diagnostic only"])

    def test_failed_prefetch_does_not_repeat_native_race(self):
        prefetch = {
            "queries": ["Acme Widget"],
            "records": [],
            "snapshots": [{"snapshot_id": "timed-out"}],
            "winner_snapshot_id": None,
            "race_width": 3,
            "warnings": ["prefetch timed out"],
        }
        with (
            mock.patch.object(
                social,
                "_trigger_native_reddit_discovery",
            ) as trigger,
            mock.patch.object(
                social,
                "_discover_reddit_with_serp",
                return_value={"records": [], "warnings": []},
            ),
        ):
            result = social._run_reddit_profile_cohort(
                profile(),
                [],
                ["widget"],
                {},
                native_prefetch=prefetch,
            )

        trigger.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertIn("prefetch timed out", result["warnings"])

    def test_competitive_mode_builds_equal_brand_and_category_cohorts(self):
        target = profile("Acme", ["Widget Pro"])
        target.category = "Widgets"
        competitor = profile("Other", ["Other Basic", "Other Plus"])

        def cohort_result(
            cohort_profile,
            peers,
            keywords,
            serp,
            focus,
            queries,
            require_match,
            role,
            native_prefetch,
        ):
            post_id = "shared1" if role != "category" else "category1"
            sample = [
                {
                    "post_id": post_id,
                    "title": f"{cohort_profile.brand_name} thread",
                    "analysis": {"relevant": True},
                }
            ]
            return {
                "status": "success",
                "role": role,
                "brand": cohort_profile.brand_name,
                "focus": focus,
                "queries": queries or [focus],
                "sample": sample,
                "metrics": social.aggregate_reddit_analysis(sample),
                "warnings": [],
                "duration_seconds": 1,
            }

        with (
            mock.patch.object(
                social,
                "choose_competitor_reddit_offerings",
                return_value=({"Other": "Other Plus"}, None, []),
            ),
            mock.patch.object(
                social,
                "_run_reddit_profile_cohort",
                side_effect=cohort_result,
            ),
        ):
            result = social.run_reddit_social_sync(
                target,
                [competitor],
                ["best widgets"],
                {},
                "Widget Pro",
            )

        self.assertEqual(result["mode"], "competitive")
        self.assertEqual(len(result["cohorts"]), 3)
        self.assertEqual(len(result["comparison"]), 2)
        self.assertEqual(result["comparison"][1]["focus"], "Other Plus")
        self.assertEqual(result["unique_thread_count"], 2)

        report = social.build_reddit_report_section(result)
        self.assertIn("| Acme | target | Widget Pro |", report)
        self.assertIn("| Other | competitor | Other Plus |", report)
        self.assertIn("### Neutral Category Sample", report)

    def test_no_explicit_focus_uses_one_shared_category_scope(self):
        target = profile("mobile.de", ["Vehicle listings", "Financing"])
        target.category = "Online-Fahrzeugmarkt"
        competitor = profile("AutoScout24", ["Used cars", "Leasing"])
        observed = []

        def cohort_result(
            cohort_profile,
            peers,
            keywords,
            serp,
            focus,
            queries,
            require_match,
            role,
            native_prefetch,
        ):
            observed.append((role, cohort_profile.brand_name, focus))
            return {
                "status": "success",
                "role": role,
                "brand": cohort_profile.brand_name,
                "focus": focus,
                "queries": queries or [focus],
                "sample": [],
                "metrics": social.aggregate_reddit_analysis([]),
                "warnings": [],
                "duration_seconds": 0,
            }

        with (
            mock.patch.object(
                social,
                "choose_competitor_reddit_offerings",
            ) as choose_offerings,
            mock.patch.object(
                social,
                "_run_reddit_profile_cohort",
                side_effect=cohort_result,
            ),
        ):
            result = social.run_reddit_social_sync(
                target,
                [competitor],
                ["Gebrauchtwagen kaufen"],
                {},
                "",
            )

        choose_offerings.assert_not_called()
        self.assertIn(("target", "mobile.de", "Online-Fahrzeugmarkt"), observed)
        self.assertIn(("competitor", "AutoScout24", "Online-Fahrzeugmarkt"), observed)
        self.assertEqual(result["comparison_type"], "marketplace")

    def test_partial_reddit_warnings_are_summarized_once(self):
        result = {
            "status": "partial",
            "cohorts": [
                {
                    "role": "target",
                    "brand": "mobile.de",
                    "metrics": {"relevant_posts": 8},
                },
                {
                    "role": "competitor",
                    "brand": "AutoScout24",
                    "metrics": {"relevant_posts": 0},
                },
            ],
            "warnings": ["technical warning one", "technical warning two"],
        }

        warning = social.summarize_reddit_audit_warning(result)

        self.assertIn("1/2 brand cohorts", warning)
        self.assertIn("AutoScout24", warning)
        self.assertNotIn("technical warning", warning)


if __name__ == "__main__":
    unittest.main()
