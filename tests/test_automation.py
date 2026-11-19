import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from automation_gate import MAX_WAIT, night_complete, plan, run

CONFIG = json.loads((ROOT / "data/picks.json").read_text(encoding="utf-8"))
EAST = [t["id"] for t in CONFIG["teams"] if t["conference"] == "East"]
WEST = [t["id"] for t in CONFIG["teams"] if t["conference"] == "West"]
SOURCE = {"url": "https://en.wikipedia.org/wiki/2026%E2%80%9327_NBA_season"}


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def base_records():
    return {team["id"]: {"wins": 5, "losses": 5} for team in CONFIG["teams"]}


def play(records, *games, loser_counted=True):
    """Return a copy of records after each (winner, loser) game."""
    result = copy.deepcopy(records)
    for winner, loser in games:
        result[winner]["wins"] += 1
        if loser_counted:
            result[loser]["losses"] += 1
    return result


def history_with(date, records):
    return {"season": CONFIG["season"], "snapshots": [{"season": CONFIG["season"], "date": date, "updatedAt": date + "T09:00:00+00:00", "source": SOURCE, "records": records}]}


class FakeWikipedia:
    """Clock, sleep and fetch driven by a timeline of (time the edit is live, records or exception)."""
    def __init__(self, start, timeline):
        self.now, self.timeline, self.calls, self.log = start, timeline, 0, []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)

    def fetch(self, config):
        self.calls += 1
        current = [value for moment, value in self.timeline if moment <= self.now][-1]
        if isinstance(current, Exception):
            raise current
        return copy.deepcopy(current), dict(SOURCE)

    def run(self, history, event="schedule"):
        return run(CONFIG, history, event, fetch=self.fetch, clock=self.clock, sleep=self.sleep, log=self.log.append)


YESTERDAY = base_records()
EAST_ONLY = play(YESTERDAY, (EAST[0], EAST[1]))                      # East template edited first
FULL_NIGHT = play(EAST_ONLY, (WEST[0], EAST[2]), (WEST[1], WEST[2]))  # then West: night complete
TYPO = play(FULL_NIGHT, (WEST[3], EAST[3]), loser_counted=False)      # 2026-11-16: one loss missing


class PlanTests(unittest.TestCase):
    def test_push_and_manual_runs_always_publish(self):
        history = history_with("2026-11-19", YESTERDAY)
        for event in ("push", "workflow_dispatch"):
            self.assertEqual(plan(CONFIG, history, event, utc(2026, 11, 19, 10))[0], "always")

    def test_night_trigger_waits_for_results_up_to_five_and_a_half_hours(self):
        now = utc(2026, 11, 19, 1, 2)
        mode, deadline = plan(CONFIG, history_with("2026-11-18", YESTERDAY), "schedule", now)
        self.assertEqual((mode, deadline), ("wait", now + MAX_WAIT))

    def test_late_morning_trigger_waits_until_two_pm_local_winter_and_summer(self):
        winter = plan(CONFIG, history_with("2026-11-18", YESTERDAY), "schedule", utc(2026, 11, 19, 10))
        summer = plan(CONFIG, history_with("2027-04-09", YESTERDAY), "schedule", utc(2027, 4, 10, 10))
        self.assertEqual(winter, ("wait", utc(2026, 11, 19, 13)))  # 14:00 CET
        self.assertEqual(summer, ("wait", utc(2027, 4, 10, 12)))   # 14:00 CEST

    def test_afternoon_trigger_publishes_without_waiting(self):
        self.assertEqual(plan(CONFIG, history_with("2026-11-18", YESTERDAY), "schedule", utc(2026, 11, 19, 15))[0], "once")

    def test_day_already_online_only_looks_for_corrections(self):
        self.assertEqual(plan(CONFIG, history_with("2026-11-19", YESTERDAY), "schedule", utc(2026, 11, 19, 12))[0], "refresh")
        # 23:30 UTC on the 18th is already the 19th in Berlin: a new day to wait for.
        self.assertEqual(plan(CONFIG, history_with("2026-11-18", YESTERDAY), "schedule", utc(2026, 11, 18, 23, 30))[0], "wait")

    def test_empty_history_waits(self):
        self.assertEqual(plan(CONFIG, {}, "schedule", utc(2026, 11, 19, 3))[0], "wait")


class NightCompleteTests(unittest.TestCase):
    def test_one_conference_is_not_enough(self):
        self.assertFalse(night_complete(CONFIG, {"records": YESTERDAY}, EAST_ONLY))

    def test_both_conferences_with_balanced_totals(self):
        self.assertTrue(night_complete(CONFIG, {"records": YESTERDAY}, FULL_NIGHT))

    def test_unbalanced_totals_are_not_complete(self):
        self.assertFalse(night_complete(CONFIG, {"records": YESTERDAY}, TYPO))


class WaitTests(unittest.TestCase):
    def test_night_trigger_publishes_as_soon_as_both_conferences_are_in(self):
        # 2026-11-07: East edited at 04:59 UTC, West at 06:14 UTC; GitHub fired at 01:44 UTC.
        wiki = FakeWikipedia(utc(2026, 11, 7, 1, 44), [
            (utc(2026, 11, 1), YESTERDAY), (utc(2026, 11, 7, 4, 59), EAST_ONLY), (utc(2026, 11, 7, 6, 14), FULL_NIGHT)])
        publish, current = wiki.run(history_with("2026-11-06", YESTERDAY))
        self.assertTrue(publish)
        self.assertEqual(current["records"], FULL_NIGHT)
        self.assertEqual(current["date"], "2026-11-07")
        self.assertEqual(current["updatedAt"], "2026-11-07T06:14:00+00:00")  # 27th check, 10 minutes apart
        self.assertLess(wiki.calls, 40)  # one request every 10 minutes, no more

    def test_persistent_wikipedia_typo_is_published_at_the_deadline(self):
        # 2026-11-16: totals stayed 193 W / 194 L for 24 hours; the old strict check published nothing.
        start = utc(2026, 11, 16, 8, 29)
        wiki = FakeWikipedia(start, [(utc(2026, 11, 1), TYPO)])
        publish, current = wiki.run(history_with("2026-11-15", YESTERDAY))
        self.assertTrue(publish)
        self.assertEqual(current["records"], TYPO)
        self.assertEqual(wiki.now, utc(2026, 11, 16, 13))  # waited until 14:00 Berlin
        self.assertTrue(any("::warning::" in line for line in wiki.log))

    def test_temporary_errors_are_retried(self):
        wiki = FakeWikipedia(utc(2026, 11, 19, 5), [
            (utc(2026, 11, 1), RuntimeError("429 Too Many Requests")), (utc(2026, 11, 19, 5, 25), FULL_NIGHT)])
        publish, current = wiki.run(history_with("2026-11-18", YESTERDAY))
        self.assertTrue(publish)
        self.assertEqual(current["records"], FULL_NIGHT)

    def test_no_valid_download_at_all_fails_the_run(self):
        wiki = FakeWikipedia(utc(2026, 11, 19, 5), [(utc(2026, 11, 1), ValueError("Colonne W/L inattese"))])
        with self.assertRaisesRegex(RuntimeError, "Colonne W/L inattese"):
            wiki.run(history_with("2026-11-18", YESTERDAY))

    def test_wait_without_news_leaves_the_day_open_for_the_next_trigger(self):
        # 2026-11-05: GitHub fired at 00:53 Berlin, Wikipedia was updated at 07:43 Berlin.
        timeline = [(utc(2026, 11, 1), YESTERDAY), (utc(2026, 11, 5, 6, 43), FULL_NIGHT)]
        history = history_with("2026-11-04", YESTERDAY)
        first = FakeWikipedia(utc(2026, 11, 4, 23, 53), timeline)
        self.assertEqual(first.run(history), (False, None))  # nothing new by 06:23: no stale "update"
        second = FakeWikipedia(utc(2026, 11, 5, 6, 10), timeline)
        publish, current = second.run(history)
        self.assertTrue(publish)
        self.assertEqual((current["records"], current["updatedAt"]), (FULL_NIGHT, "2026-11-05T06:50:00+00:00"))

    def test_night_without_games_gets_its_snapshot_in_the_afternoon_only_once(self):
        timeline = [(utc(2026, 11, 1), YESTERDAY)]
        history = history_with("2026-11-25", YESTERDAY)
        self.assertEqual(FakeWikipedia(utc(2026, 11, 26, 6), timeline).run(history), (False, None))
        publish, current = FakeWikipedia(utc(2026, 11, 26, 15), timeline).run(history)
        self.assertTrue(publish)
        self.assertEqual((current["date"], current["records"]), ("2026-11-26", YESTERDAY))
        history["snapshots"].append(current)
        self.assertEqual(FakeWikipedia(utc(2026, 11, 26, 19), timeline).run(history), (False, None))

    def test_partial_update_online_keeps_waiting_for_the_rest_of_the_night(self):
        history = history_with("2026-11-06", YESTERDAY)
        history["snapshots"].append(dict(history["snapshots"][0], date="2026-11-07", records=EAST_ONLY))
        self.assertEqual(plan(CONFIG, history, "schedule", utc(2026, 11, 7, 8))[0], "wait")
        wiki = FakeWikipedia(utc(2026, 11, 7, 8), [(utc(2026, 11, 1), EAST_ONLY), (utc(2026, 11, 7, 9, 5), FULL_NIGHT)])
        publish, current = wiki.run(history)
        self.assertTrue(publish)
        self.assertEqual(current["records"], FULL_NIGHT)
        history["snapshots"][-1] = current
        self.assertEqual(plan(CONFIG, history, "schedule", utc(2026, 11, 7, 10))[0], "refresh")


class SingleDownloadTests(unittest.TestCase):
    def setUp(self):
        self.today = history_with("2026-11-19", FULL_NIGHT)

    def test_nothing_new_means_no_deployment(self):
        wiki = FakeWikipedia(utc(2026, 11, 19, 18), [(utc(2026, 11, 1), FULL_NIGHT)])
        self.assertEqual(wiki.run(self.today), (False, None))
        self.assertEqual(wiki.calls, 1)

    def test_balanced_correction_is_published(self):
        corrected = play(FULL_NIGHT, (EAST[4], WEST[4]))
        wiki = FakeWikipedia(utc(2026, 11, 19, 18), [(utc(2026, 11, 1), corrected)])
        publish, current = wiki.run(self.today)
        self.assertTrue(publish)
        self.assertEqual(current["records"], corrected)

    def test_half_finished_correction_waits_for_next_trigger(self):
        wiki = FakeWikipedia(utc(2026, 11, 19, 18), [(utc(2026, 11, 1), TYPO)])
        self.assertEqual(wiki.run(self.today), (False, None))

    def test_wikipedia_error_after_todays_update_is_not_a_failure(self):
        wiki = FakeWikipedia(utc(2026, 11, 19, 18), [(utc(2026, 11, 1), RuntimeError("down"))])
        self.assertEqual(wiki.run(self.today), (False, None))

    def test_push_publishes_code_even_if_wikipedia_is_down(self):
        wiki = FakeWikipedia(utc(2026, 11, 19, 18), [(utc(2026, 11, 1), RuntimeError("down"))])
        self.assertEqual(wiki.run(self.today, event="push"), (True, None))

    def test_afternoon_without_todays_snapshot_fails_loudly_if_wikipedia_is_down(self):
        wiki = FakeWikipedia(utc(2026, 11, 19, 18), [(utc(2026, 11, 1), RuntimeError("down"))])
        with self.assertRaises(RuntimeError):
            wiki.run(history_with("2026-11-18", YESTERDAY))


if __name__ == "__main__":
    unittest.main()
