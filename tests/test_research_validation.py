"""Task-aware research answer validation shared across execution modes."""

import json
import unittest

from audit_core.research_validation import (
    identify_research_task,
    snapshot_is_materializing,
    validate_research_answer,
)


class ResearchValidationTests(unittest.TestCase):
    def validate(self, answer, prompt):
        return validate_research_answer(
            answer,
            prompt,
            parse_json=json.loads,
            remove_boilerplate=lambda value: value,
        )

    def test_identifies_existing_prompt_families(self):
        self.assertEqual(
            identify_research_task(
                'Return only JSON with "competitors" and rank_by_directness'
            ),
            "competitor_selection_json",
        )
        self.assertEqual(
            identify_research_task(
                'Return JSON only: "candidate_name" and "is_direct_competitor"'
            ),
            "candidate_validation_json",
        )
        self.assertEqual(
            identify_research_task(
                'A customer is researching this need: premium lenses'
            ),
            "customer_question_research",
        )

    def test_competitor_selection_requires_two_domain_backed_records(self):
        prompt = 'Return only JSON with "competitors" and rank_by_directness'
        one = self.validate('{"competitors":[{"domain":"one.example"}]}', prompt)
        two = self.validate(
            '{"competitors":[{"domain":"one.example"},{"official_url":"https://two.example"}]}',
            prompt,
        )
        self.assertFalse(one["valid"])
        self.assertTrue(two["valid"])

    def test_candidate_and_profile_json_require_identity_fields(self):
        candidate_prompt = 'Return JSON only: "candidate_name" and "is_direct_competitor"'
        self.assertFalse(self.validate('{"reason":"unclear"}', candidate_prompt)["valid"])
        self.assertTrue(self.validate('{"is_direct_competitor":true}', candidate_prompt)["valid"])

        profile_prompt = 'Return only JSON with "brand_name" and "relevant_products"'
        self.assertFalse(self.validate('{"relevant_products":[]}', profile_prompt)["valid"])
        self.assertTrue(self.validate('{"brand_name":"Example"}', profile_prompt)["valid"])

    def test_malformed_json_and_short_narrative_are_rejected(self):
        json_prompt = 'Return only JSON with "brand_name" and "relevant_products"'
        self.assertFalse(self.validate('{nope}', json_prompt)["valid"])
        self.assertFalse(self.validate('too short', 'Explain the market')["valid"])

    def test_substantive_narrative_is_cleaned_and_interface_only_text_rejected(self):
        prompt = 'Explain the market'
        content = 'Useful research with enough substantive detail. ' * 4
        result = validate_research_answer(
            content,
            prompt,
            parse_json=json.loads,
            remove_boilerplate=lambda _value: content.strip(),
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["cleaned_answer"], content.strip())
        interface = validate_research_answer(
            'x' * 120,
            prompt,
            parse_json=json.loads,
            remove_boilerplate=lambda _value: 'sign up for free',
        )
        self.assertFalse(interface["valid"])

    def test_materialization_records_remain_retryable(self):
        self.assertTrue(snapshot_is_materializing([{"status": " BUILDING "}]))
        self.assertTrue(snapshot_is_materializing([{"status": "pending"}]))
        self.assertFalse(snapshot_is_materializing([{"status": "ready"}]))
        self.assertFalse(snapshot_is_materializing([{"status": "building"}, {}]))


if __name__ == "__main__":
    unittest.main()
