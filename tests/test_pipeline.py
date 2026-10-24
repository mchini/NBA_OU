import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from import_picks import extract_picks
from update_records import parse_standings, validate_records, merge_history, snapshot, main

CONFIG = json.loads((ROOT / "data/picks.json").read_text(encoding="utf-8"))


def fixture():
    rows = "".join(f'<tr><td>{i + 1}</td><td><a>{t["name"]}</a> *</td><td>1</td><td>1</td><td>.500</td></tr>' for i, t in enumerate(CONFIG["teams"]))
    return '<table><tr><td>Unrelated table</td><td><table><tr><th>#</th><th>Team</th><th>W</th><th>L</th><th>PCT</th></tr>' + rows + '</table></td></tr></table>'


class PipelineTests(unittest.TestCase):
    def test_excel_exactly_matches_published_picks(self):
        self.assertEqual(extract_picks(ROOT / "NBA_OU.xlsx"), CONFIG)

    def test_parser_ignores_nested_wrapper_and_other_statistics(self):
        records = parse_standings(fixture(), CONFIG)
        self.assertEqual(len(records), 30)
        self.assertEqual(records["PHI"], {"wins": 1, "losses": 1})

    def test_missing_team_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "incompleta"):
            parse_standings(fixture().replace("Philadelphia 76ers", "Unknown team"), CONFIG)

    def test_contradictory_duplicates_fail_closed(self):
        html = fixture() + '<table><tr><th>Team</th><th>W</th><th>L</th></tr><tr><td>Philadelphia 76ers</td><td>2</td><td>0</td></tr></table>'
        with self.assertRaisesRegex(ValueError, "discordanti"):
            parse_standings(html, CONFIG)

    def test_unbalanced_or_invalid_records_fail_closed(self):
        records = parse_standings(fixture(), CONFIG)
        records["PHI"]["wins"] = 2
        with self.assertRaisesRegex(ValueError, "non quadra"):
            validate_records(records, CONFIG)
        records["PHI"]["wins"] = 83
        with self.assertRaisesRegex(ValueError, "non valido"):
            validate_records(records, CONFIG)

    def test_same_day_replaces_snapshot_and_preserves_other_days(self):
        history = {"season": "2026-27", "snapshots": [{"date": "2026-10-23", "x": 1}, {"date": "2026-10-24", "x": 2}]}
        current = {"season": "2026-27", "date": "2026-10-24", "x": 3}
        merged = merge_history(history, current)
        self.assertEqual([s["x"] for s in merged["snapshots"]], [1, 3])

    def test_day_boundary_is_local_time_and_dst_is_handled(self):
        records = parse_standings(fixture(), CONFIG)
        current = snapshot(CONFIG, records, {}, datetime(2026, 10, 24, 23, 30, tzinfo=timezone.utc))
        self.assertEqual(current["date"], "2026-10-25")

    def test_failed_fetch_preserves_last_good_data(self):
        with tempfile.TemporaryDirectory() as folder:
            data_dir = Path(folder)
            (data_dir / "picks.json").write_text(json.dumps(CONFIG), encoding="utf-8")
            path = data_dir / "history.json"
            original = '{"season":"2026-27","snapshots":["unchanged"]}'
            path.write_text(original, encoding="utf-8")
            with patch("sys.argv", ["update_records.py", "--data-dir", folder]), patch("update_records.fetch_standings", side_effect=ValueError("Bad source")):
                with self.assertRaises(ValueError):
                    main()
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_downloaded_snapshot_contains_all_valid_teams(self):
        history = json.loads((ROOT / "data/history.json").read_text(encoding="utf-8"))
        self.assertEqual(history["season"], CONFIG["season"])
        for item in history["snapshots"]:
            validate_records(item["records"], CONFIG)
            self.assertTrue(item["source"]["url"].startswith("https://en.wikipedia.org/"))


if __name__ == "__main__":
    unittest.main()
