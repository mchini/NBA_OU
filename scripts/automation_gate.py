"""Gate repeated triggers until today's download AND deployment succeed."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
NOT_BEFORE_HOUR = 9


def decision(config, state, event, now=None):
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(ZoneInfo(config["timezone"]))
    day = local.date().isoformat()
    if event != "schedule":
        return True, "Pubblicazione richiesta da una modifica o da un avvio esplicito."
    if local.hour < NOT_BEFORE_HOUR:
        return False, "Attendo le 09:00 locali, dopo la normale finestra delle partite NBA notturne."
    if state.get("date") == day and state.get("season") == config["season"]:
        return False, f"Record gia scaricati e sito pubblicato correttamente oggi ({day})."
    return True, f"Aggiornamento di {day} da completare; recupero automatico degli avvii saltati."


def completion(config, history, now=None):
    latest = history["snapshots"][-1]
    if history["season"] != config["season"] or latest["season"] != config["season"]:
        raise ValueError("Non posso confermare una pubblicazione di una stagione diversa")
    return {
        "season": config["season"], "date": latest["date"],
        "publishedAt": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "recordsFetchedAt": latest["updatedAt"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "complete"))
    parser.add_argument("--event", default="schedule")
    args = parser.parse_args()
    config = json.loads((ROOT / "data/picks.json").read_text(encoding="utf-8"))
    path = ROOT / ".github/update-state.json"
    if args.command == "check":
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        run, reason = decision(config, state, args.event)
        print(reason)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"run={'true' if run else 'false'}\n")
        return
    history = json.loads((ROOT / "data/history.json").read_text(encoding="utf-8"))
    state = completion(config, history)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"Pubblicazione del {state['date']} completata. Nessun altro prelievo necessario oggi.")


if __name__ == "__main__":
    main()
