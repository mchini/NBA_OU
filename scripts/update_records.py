"""Fetch NBA regular-season standings from the Wikimedia Action API, once per run.

Only complete, internally consistent standings are published. No external packages.
On any error the previous data is left intact and the command exits nonzero.
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"


class StandingsTables(HTMLParser):
    """Collect table rows without mixing text from nested tables."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.stack.append({"rows": [], "row": None, "cell": None})
        elif self.stack:
            frame = self.stack[-1]
            if tag == "tr":
                frame["row"] = []
            elif tag in ("td", "th") and frame["row"] is not None:
                frame["cell"] = []
            elif tag == "br" and frame["cell"] is not None:
                frame["cell"].append(" ")

    def handle_data(self, value):
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"].append(value)

    def handle_endtag(self, tag):
        if not self.stack:
            return
        frame = self.stack[-1]
        if tag in ("td", "th") and frame["cell"] is not None:
            frame["row"].append(re.sub(r"\s+", " ", "".join(frame["cell"])).strip())
            frame["cell"] = None
        elif tag == "tr" and frame["row"] is not None:
            frame["rows"].append(frame["row"])
            frame["row"] = None
        elif tag == "table":
            self.tables.append(self.stack.pop()["rows"])


def normalized(value):
    value = re.sub(r"[\u200b-\u200f\ufeff]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def validate_records(records, config):
    expected = {team["id"] for team in config["teams"]}
    if set(records) != expected:
        missing = ", ".join(sorted(expected - set(records)))
        raise ValueError(f"Classifica incompleta: {len(records)}/30 squadre. Mancano: {missing}")
    for code, record in records.items():
        wins, losses = record.get("wins"), record.get("losses")
        if type(wins) is not int or type(losses) is not int or min(wins, losses) < 0 or wins + losses > config["games"]:
            raise ValueError(f"Record non valido per {code}: {record}")
    wins = sum(record["wins"] for record in records.values())
    losses = sum(record["losses"] for record in records.values())
    if wins != losses:
        raise ValueError(f"La classifica non quadra: {wins} vittorie, {losses} sconfitte. Riprova piu tardi.")


def parse_standings(html, config):
    parser = StandingsTables()
    parser.feed(html)
    records = {}
    aliases = {team["name"]: team["id"] for team in config["teams"]}
    aliases.update({"LA Clippers": "LAC", "L.A. Clippers": "LAC", "LA Lakers": "LAL"})
    for rows in parser.tables:
        win_col = loss_col = None
        for row in rows:
            cells = [normalized(cell) for cell in row]
            win_headers = [i for i, cell in enumerate(cells) if re.fullmatch(r"W(?:\s*\(Games won\))?|Wins", cell, re.I)]
            loss_headers = [i for i, cell in enumerate(cells) if re.fullmatch(r"L(?:\s*\(Games lost\))?|Losses", cell, re.I)]
            if len(win_headers) == len(loss_headers) == 1:
                win_col, loss_col = win_headers[0], loss_headers[0]
                continue
            if win_col is None or max(win_col, loss_col) >= len(cells):
                continue
            found = {code for name, code in aliases.items() if any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", cell) for cell in cells)}
            if len(found) != 1:
                continue
            if not re.fullmatch(r"\d{1,2}", cells[win_col]) or not re.fullmatch(r"\d{1,2}", cells[loss_col]):
                raise ValueError("Colonne W/L inattese: " + " | ".join(cells))
            code = found.pop()
            record = {"wins": int(cells[win_col]), "losses": int(cells[loss_col])}
            if code in records and records[code] != record:
                raise ValueError(f"Record discordanti fra le tabelle per {code}")
            records[code] = record
    validate_records(records, config)
    return records


def source_url(config):
    title = f"{config['startYear']}\u2013{str(config['startYear'] + 1)[-2:]}_NBA_season"
    return "https://en.wikipedia.org/wiki/" + quote(title)


def fetch_standings(config):
    title = f"{config['startYear']}\u2013{str(config['startYear'] + 1)[-2:]} NBA season"
    url = "https://en.wikipedia.org/w/api.php?" + urlencode({
        "action": "parse", "page": title, "prop": "text|revid", "format": "json", "formatversion": "2", "maxlag": "5"
    })
    repo = os.environ.get("GITHUB_REPOSITORY")
    contact = f"https://github.com/{repo}" if repo else source_url(config)
    agent = f"NBA-OU-Friends/1.0 ({contact}; daily personal standings dashboard) Python-urllib"
    for attempt in range(3):
        try:
            request = Request(url, headers={"User-Agent": agent, "Accept": "application/json"})
            with urlopen(request, timeout=45) as response:
                payload = json.load(response)
            if "error" in payload:
                raise ValueError("Wikimedia API: " + json.dumps(payload["error"], ensure_ascii=False))
            parsed = payload["parse"]
            if parsed.get("title", "").replace("_", " ") != title:
                raise ValueError("La fonte ha restituito una stagione diversa")
            records = parse_standings(parsed["text"], config)
            return records, {
                "name": "Wikipedia · autori della pagina NBA " + config["season"],
                "url": source_url(config), "revision": parsed.get("revid"),
                "license": "CC BY-SA 4.0", "licenseUrl": LICENSE,
                "note": "Record estratti dalle classifiche di regular season; proiezioni elaborate da questo sito. La fonte e aggiornata dalla comunita.",
            }
        except HTTPError as error:
            # Respect Retry-After; never switch endpoints to bypass a rate limit.
            if error.code == 429 or (error.code == 503 and error.headers.get("Retry-After")):
                retry = error.headers.get("Retry-After", "60")
                try:
                    seconds = max(1, int(retry))
                except ValueError:
                    try:
                        seconds = max(1, int((parsedate_to_datetime(retry) - datetime.now(timezone.utc)).total_seconds()))
                    except (TypeError, ValueError):
                        seconds = 60
                if seconds > 60 or attempt == 2:
                    raise RuntimeError(f"Wikipedia limita le richieste. Retry-After: {retry}. Dati precedenti conservati.") from error
                print(f"Limite API: attendo {seconds}s prima di riprovare.", flush=True)
                time.sleep(seconds)
            elif error.code in (500, 502, 503, 504) and attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("Nessuna risposta valida da Wikipedia")


def snapshot(config, records, source, now=None):
    validate_records(records, config)
    now = now or datetime.now(timezone.utc)
    return {
        "season": config["season"], "date": now.astimezone(ZoneInfo(config["timezone"])).date().isoformat(),
        "updatedAt": now.isoformat(timespec="seconds"), "source": source, "records": records,
    }


def merge_history(history, current):
    if history.get("season") != current["season"]:
        history = {"season": current["season"], "snapshots": []}
    dates = {item["date"]: item for item in history["snapshots"]}
    dates[current["date"]] = current
    return {"season": current["season"], "snapshots": [dates[day] for day in sorted(dates)]}


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    config = json.loads((args.data_dir / "picks.json").read_text(encoding="utf-8"))
    records, source = fetch_standings(config)
    current = snapshot(config, records, source)
    history_path = args.data_dir / "history.json"
    history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {}
    history = merge_history(history, current)
    # History is the canonical data file; the page reads its last snapshot.
    atomic_json(history_path, history)
    print(f"Aggiornate 30 squadre, {sum(r['wins'] for r in records.values())} partite concluse. {current['updatedAt']}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, RuntimeError, OSError) as error:
        print(f"Aggiornamento fallito; dati precedenti conservati. {error}", file=sys.stderr)
        sys.exit(1)
