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
                "RayOne Galaxy review",
                "Rayner presbyopia-correcting intraocular lenses",
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
                "Moisturizing Cream review",
                "CeraVe moisturizer for dry sensitive skin",
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
                "Used-car marketplace review",
                "Auto Trader buy used cars online uk",
            ],
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
                "RayOne review",
                "Rayner presbyopia-correcting intraocular lenses for cataract surgery",
            ],
        )

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
                "queries": ["Acme review", "Acme pricing"],
                "records": [],
                "snapshots": [],
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
            ["Acme review", "Acme pricing"],
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

        def trigger(queries):
            return {
                "queries": queries,
                "records": [],
                "snapshots": [{"snapshot_id": queries[0]}],
                "race_width": 3,
                "warnings": [],
            }

        def wait(native):
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


class RedditSelectionTests(unittest.TestCase):
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
                    "title": "Acme Widget Pro review",
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

    def test_validator_requires_verbatim_evidence_and_normalizes_labels(self):
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
        self.assertFalse(validator(json.dumps(invalid_payload))["valid"])

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


if __name__ == "__main__":
    unittest.main()
