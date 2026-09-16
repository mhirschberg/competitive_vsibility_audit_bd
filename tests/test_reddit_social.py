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
            mock.patch.object(social, "BD_SCRAPE_URL", "https://example.test/scrape", create=True),
            mock.patch.object(social, "bd_client", client, create=True),
            mock.patch.object(social.reddit_requests, "post", return_value=response) as post,
        ):
            result = social._trigger_native_reddit_discovery(["Acme review"])

        self.assertEqual(result, {"records": [], "snapshot_id": None})
        request = post.call_args.kwargs
        self.assertEqual(request["params"]["discover_by"], "keyword")
        self.assertEqual(request["json"]["input"][0]["date"], "Past year")


class RedditSelectionTests(unittest.TestCase):
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
            }
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
        self.assertEqual(social.insert_reddit_report_section(report, result), report)

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


if __name__ == "__main__":
    unittest.main()
