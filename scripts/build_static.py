"""Prepare only public site assets for Pages (never the Excel source or scripts)."""
import json
import shutil
from pathlib import Path

from update_records import ROOT, validate_records


def main():
    config = json.loads((ROOT / "data/picks.json").read_text(encoding="utf-8"))
    history = json.loads((ROOT / "data/history.json").read_text(encoding="utf-8"))
    if history["season"] != config["season"] or not history["snapshots"]:
        raise ValueError("Storico della stagione mancante")
    dates = [item["date"] for item in history["snapshots"]]
    if dates != sorted(set(dates)):
        raise ValueError("Lo storico deve avere una sola voce per giorno, in ordine")
    for item in history["snapshots"]:
        validate_records(item["records"], config)
    output = ROOT / "_site"
    for folder in ("assets", "data"):
        (output / folder).mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "assets/app.mjs", "assets/model.mjs", "assets/style.css", "assets/favicon.svg", "data/picks.json", "data/history.json"):
        shutil.copy2(ROOT / name, output / name)
    (output / ".nojekyll").touch()
    print(f"Sito statico pronto: {output}")


if __name__ == "__main__":
    main()
