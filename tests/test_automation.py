import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from automation_gate import decision, completion

CONFIG = {"season": "2026-27", "timezone": "Europe/Berlin"}


class AutomationTests(unittest.TestCase):
    def test_waits_until_nine_local(self):
        now = datetime(2026, 10, 26, 7, 30, tzinfo=timezone.utc)
        self.assertFalse(decision(CONFIG, {}, "schedule", now)[0])

    def test_first_morning_run_is_automatic(self):
        now = datetime(2026, 10, 26, 8, 7, tzinfo=timezone.utc)
        self.assertTrue(decision(CONFIG, {}, "schedule", now)[0])

    def test_missed_run_is_recovered_later_without_user_input(self):
        now = datetime(2026, 10, 26, 12, 37, tzinfo=timezone.utc)
        previous = {"season": "2026-27", "date": "2026-10-25"}
        self.assertTrue(decision(CONFIG, previous, "schedule", now)[0])

    def test_download_without_deployment_does_not_close_gate(self):
        now = datetime(2026, 10, 26, 9, 37, tzinfo=timezone.utc)
        previous = {"season": "2026-27", "date": "2026-10-25"}
        self.assertTrue(decision(CONFIG, previous, "schedule", now)[0])

    def test_successful_publication_skips_further_downloads(self):
        now = datetime(2026, 10, 26, 10, 37, tzinfo=timezone.utc)
        state = {"season": "2026-27", "date": "2026-10-26"}
        self.assertFalse(decision(CONFIG, state, "schedule", now)[0])

    def test_next_morning_reopens_gate(self):
        now = datetime(2026, 10, 27, 8, 7, tzinfo=timezone.utc)
        state = {"season": "2026-27", "date": "2026-10-26"}
        self.assertTrue(decision(CONFIG, state, "schedule", now)[0])

    def test_summer_and_winter_time_are_automatic(self):
        summer = datetime(2026, 10, 24, 7, 7, tzinfo=timezone.utc)
        winter = datetime(2026, 10, 26, 8, 7, tzinfo=timezone.utc)
        self.assertTrue(decision(CONFIG, {}, "schedule", summer)[0])
        self.assertTrue(decision(CONFIG, {}, "schedule", winter)[0])

    def test_code_changes_can_deploy_after_daily_success(self):
        now = datetime(2026, 10, 26, 10, 37, tzinfo=timezone.utc)
        state = {"season": "2026-27", "date": "2026-10-26"}
        self.assertTrue(decision(CONFIG, state, "push", now)[0])

    def test_marker_uses_snapshot_date_not_later_deployment_date(self):
        history = {"season": "2026-27", "snapshots": [{"season": "2026-27", "date": "2026-10-26", "updatedAt": "2026-10-26T22:59:59+00:00"}]}
        now = datetime(2026, 10, 26, 23, 0, tzinfo=timezone.utc)
        self.assertEqual(completion(CONFIG, history, now)["date"], "2026-10-26")


if __name__ == "__main__":
    unittest.main()
