"""Decide whether to publish, and wait for last night's NBA results when needed.

First job of the workflow. GitHub starts scheduled workflows only a few times a
day, at irregular hours that are often 6-10 hours apart, so a scheduled run that
finds today's update still missing does not give up: it re-reads Wikipedia every
10 minutes, for at most 5.5 hours, until both conferences show last night's games
with balanced totals. Later runs on the same day only publish corrections.

This job never writes the data files. It hands the validated snapshot to the
publish job, which commits it only after GitHub Pages has accepted the site, so
the committed history always matches what is online.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from update_records import ROOT, fetch_standings, snapshot, unbalance

CHECK_EVERY = timedelta(minutes=10)
MAX_WAIT = timedelta(hours=5, minutes=30)  # GitHub stops any job after 6 hours
WAIT_UNTIL_HOUR = 14  # local time; Wikipedia almost always has the night's games by then


def utcnow():
    return datetime.now(timezone.utc)


def local_day(config, moment):
    return moment.astimezone(ZoneInfo(config["timezone"])).date().isoformat()


def local_time(config, moment):
    return moment.astimezone(ZoneInfo(config["timezone"])).strftime("%H:%M")


def split_history(config, history, today):
    """Return (latest snapshot, last snapshot from before today); either may be None."""
    if history.get("season") != config["season"]:
        return None, None
    snapshots = history.get("snapshots") or []
    earlier = [item for item in snapshots if item["date"] < today]
    return (snapshots[-1] if snapshots else None), (earlier[-1] if earlier else None)


def today_complete(config, history, today):
    """Today's snapshot is online and contains a complete night of results."""
    latest, previous = split_history(config, history, today)
    if latest is None or latest["date"] != today:
        return False
    return previous is None or night_complete(config, previous, latest["records"])


def plan(config, history, event, now):
    """Return (mode, deadline).

    always  - push or manual run: publish the site, with fresh records when available
    refresh - last night's results are online: publish only a balanced correction
    wait    - last night's results are missing: wait for them until the deadline
    once    - still missing in the afternoon: publish whatever new Wikipedia has now
    """
    local = now.astimezone(ZoneInfo(config["timezone"]))
    if event != "schedule":
        return "always", now
    if today_complete(config, history, local.date().isoformat()):
        return "refresh", now
    window_end = local.replace(hour=WAIT_UNTIL_HOUR, minute=0, second=0, microsecond=0)
    if local < window_end:
        return "wait", min(now + MAX_WAIT, window_end.astimezone(timezone.utc))
    return "once", now


def changed_conferences(config, before, after):
    conference = {team["id"]: team["conference"] for team in config["teams"]}
    return {conference[code] for code, record in after.items() if before.get(code) != record}


def night_complete(config, baseline, records):
    """Both conferences moved on since the last update and every game is counted on both sides."""
    if unbalance(records) != 0:
        return False
    if baseline is None:
        return True
    conferences = {team["conference"] for team in config["teams"]}
    return changed_conferences(config, baseline["records"], records) == conferences


def describe(config, baseline, records):
    wins = sum(r["wins"] for r in records.values())
    losses = sum(r["losses"] for r in records.values())
    changed = sorted(changed_conferences(config, baseline["records"], records)) if baseline else []
    return f"{wins} vittorie / {losses} sconfitte; aggiornate rispetto al {baseline['date'] if baseline else '-'}: {', '.join(changed) or 'nessuna conference'}"


def wait_for_night(config, baseline, deadline, fetch, clock, sleep, log):
    """Return (records, source, fetched_at, complete) for the newest valid download."""
    best, last_error = None, None
    while True:
        try:
            records, source = fetch(config)
            best = (records, source, clock())
            complete = night_complete(config, baseline, records)
            log(f"{local_time(config, best[2])} · {describe(config, baseline, records)}" + (" -> completo" if complete else ""))
            if complete:
                return (*best, True)
        except Exception as error:  # network, rate limit or page mid-edit: simply try again later
            last_error = error
            log(f"{local_time(config, clock())} · download non riuscito, riprovo: {error}")
        remaining = deadline - clock()
        if remaining <= timedelta(0):
            break
        sleep(min(CHECK_EVERY, remaining).total_seconds())
    if best is None:
        raise RuntimeError(f"Nessun dato valido da Wikipedia fino alla scadenza. Ultimo errore: {last_error}")
    return (*best, False)


def run(config, history, event, fetch=fetch_standings, clock=utcnow, sleep=time.sleep, log=print):
    """Return (publish, snapshot or None)."""
    now = clock()
    mode, deadline = plan(config, history, event, now)
    latest, previous = split_history(config, history, local_day(config, now))
    has_today = latest is not None and latest["date"] == local_day(config, now)
    if mode == "wait":
        log(f"Risultati della notte non ancora online: controllo Wikipedia ogni {CHECK_EVERY.seconds // 60} minuti fino alle {local_time(config, deadline)} (ora locale).")
        records, source, fetched_at, complete = wait_for_night(config, previous, deadline, fetch, clock, sleep, log)
        if complete:
            return True, snapshot(config, records, source, fetched_at)
        if latest is not None and records == latest["records"]:
            # Leave the day open: the next trigger waits again instead of settling for old data.
            log("Nessuna novita su Wikipedia entro la scadenza: il prossimo avvio riprova.")
            return False, None
        log("::warning::Risultati della notte ancora incompleti su Wikipedia alla scadenza: pubblico i dati piu recenti; un avvio successivo completera l'aggiornamento.")
        return True, snapshot(config, records, source, fetched_at)
    try:
        records, source = fetch(config)
    except Exception as error:
        if mode == "always":
            log(f"::warning::Wikipedia non disponibile ({error}): pubblico il sito con gli ultimi record validi.")
            return True, None
        if has_today:
            log(f"Dati di oggi gia online; download di controllo non riuscito ({error}). Riprovo al prossimo avvio.")
            return False, None
        raise
    current = snapshot(config, records, source, clock())
    if mode == "always":
        return True, current
    if has_today and records == latest["records"]:
        log("Wikipedia non ha novita rispetto ai dati gia online.")
        return False, None
    if mode == "refresh" and unbalance(records) != 0:
        log("Wikipedia sta aggiornando la classifica (totali non bilanciati): attendo il prossimo avvio.")
        return False, None
    log(f"Novita su Wikipedia: {describe(config, previous, records)}.")
    return True, current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", default="schedule")
    args = parser.parse_args()
    config = json.loads((ROOT / "data/picks.json").read_text(encoding="utf-8"))
    path = ROOT / "data/history.json"
    history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    publish, current = run(config, history, args.event, log=lambda text: print(text, flush=True))
    encoded = json.dumps(current, ensure_ascii=False, separators=(",", ":")) if current else ""
    print(f"Pubblicazione: {'si' if publish else 'non necessaria'}." + (f" Snapshot del {current['date']}." if current else ""))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"publish={'true' if publish else 'false'}\n")
            stream.write(f"snapshot={encoded}\n")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, RuntimeError, OSError) as error:
        print(f"Aggiornamento non riuscito; il sito resta all'ultima versione valida e il prossimo avvio riprova. {error}", file=sys.stderr)
        sys.exit(1)
