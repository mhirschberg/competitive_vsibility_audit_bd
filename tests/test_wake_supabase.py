import unittest
from unittest.mock import patch

from scripts.wake_supabase import wake_project


class WakeSupabaseTests(unittest.TestCase):
    @patch("scripts.wake_supabase.management_request")
    def test_active_project_is_not_restored(self, request):
        request.return_value = {"status": "ACTIVE_HEALTHY"}
        self.assertIn("already active", wake_project("projectref", "token", restore=True))
        request.assert_called_once_with("projectref", "token")

    @patch("scripts.wake_supabase.management_request")
    def test_check_does_not_restore_paused_project(self, request):
        request.return_value = {"status": "INACTIVE"}
        self.assertIn("paused", wake_project("projectref", "token", restore=False))
        request.assert_called_once_with("projectref", "token")

    @patch("scripts.wake_supabase.time.sleep")
    @patch("scripts.wake_supabase.management_request")
    def test_restore_waits_for_healthy_project(self, request, sleep):
        request.side_effect = [
            {"status": "INACTIVE"}, {}, {"status": "COMING_UP"},
            {"status": "ACTIVE_HEALTHY"},
        ]
        self.assertIn("restored", wake_project("projectref", "token", restore=True))
        self.assertEqual(request.call_args_list[1].args, ("projectref", "token", "POST"))
        self.assertEqual(sleep.call_count, 2)

    @patch("scripts.wake_supabase.management_request")
    def test_unknown_state_is_not_mutated(self, request):
        request.return_value = {"status": "ACTIVE_UNHEALTHY"}
        with self.assertRaisesRegex(RuntimeError, "refusing automatic restore"):
            wake_project("projectref", "token", restore=True)
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
