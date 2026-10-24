"""Read picks AND bold locks from the original workbook. Python stdlib only."""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PLAYERS = ["Met", "Sasso", "Zach", "Bill", "House"]
TEAM_META = {
    "Atlanta Hawks": ("ATL", "East"), "Boston Celtics": ("BOS", "East"),
    "Brooklyn Nets": ("BKN", "East"), "Charlotte Hornets": ("CHA", "East"),
    "Chicago Bulls": ("CHI", "East"), "Cleveland Cavaliers": ("CLE", "East"),
    "Dallas Mavericks": ("DAL", "West"), "Denver Nuggets": ("DEN", "West"),
    "Detroit Pistons": ("DET", "East"), "Golden State Warriors": ("GSW", "West"),
    "Houston Rockets": ("HOU", "West"), "Indiana Pacers": ("IND", "East"),
    "Los Angeles Clippers": ("LAC", "West"), "Los Angeles Lakers": ("LAL", "West"),
    "Memphis Grizzlies": ("MEM", "West"), "Miami Heat": ("MIA", "East"),
    "Milwaukee Bucks": ("MIL", "East"), "Minnesota Timberwolves": ("MIN", "West"),
    "New Orleans Pelicans": ("NOP", "West"), "New York Knicks": ("NYK", "East"),
    "Oklahoma City Thunder": ("OKC", "West"), "Orlando Magic": ("ORL", "East"),
    "Philadelphia 76ers": ("PHI", "East"), "Phoenix Suns": ("PHX", "West"),
    "Portland Trail Blazers": ("POR", "West"), "Sacramento Kings": ("SAC", "West"),
    "San Antonio Spurs": ("SAS", "West"), "Toronto Raptors": ("TOR", "East"),
    "Utah Jazz": ("UTA", "West"), "Washington Wizards": ("WAS", "East"),
}


def read_workbook(path):
    with ZipFile(path) as book:
        styles = ET.fromstring(book.read("xl/styles.xml"))
        fonts = list(styles.find("m:fonts", NS))
        xfs = list(styles.find("m:cellXfs", NS))
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            shared = ["".join(item.itertext()) for item in ET.fromstring(book.read("xl/sharedStrings.xml"))]
        sheet = ET.fromstring(book.read("xl/worksheets/sheet1.xml"))
        cells = {}
        for cell in sheet.findall(".//m:sheetData/m:row/m:c", NS):
            value_node = cell.find("m:v", NS)
            value = value_node.text if value_node is not None else ""
            if cell.get("t") == "inlineStr":
                value = "".join(t.text or "" for t in cell.findall(".//m:t", NS))
            elif cell.get("t") == "s":
                value = shared[int(value)]
            font = fonts[int(xfs[int(cell.get("s", 0))].get("fontId", 0))]
            bold_node = font.find("m:b", NS)
            bold = bold_node is not None and bold_node.get("val", "1") not in ("0", "false")
            cells[cell.get("r")] = {"value": value, "bold": bold}
    return cells


def extract_picks(path):
    cells = read_workbook(path)
    year_match = re.search(r"20\d{2}", cells["A1"]["value"])
    if not year_match:
        raise ValueError("Anno della stagione mancante in A1")
    year = int(year_match.group())
    player_columns = {}
    for address, cell in cells.items():
        if re.fullmatch(r"[A-Z]+3", address):
            player = "Met" if cell["value"] == "Io" else cell["value"]
            if player in PLAYERS:
                player_columns[player] = re.sub(r"\d", "", address)
    if set(player_columns) != set(PLAYERS):
        raise ValueError("Non trovo tutti e cinque i partecipanti nell'intestazione")
    teams = []
    for row in range(4, 34):
        name = cells[f"A{row}"]["value"]
        if name not in TEAM_META:
            raise ValueError(f"Squadra sconosciuta: {name}")
        code, conference = TEAM_META[name]
        line = float(cells[f"B{row}"]["value"])
        if not 0 < line < 82:
            raise ValueError(f"Linea O/U non valida per {name}")
        picks = {}
        for player, col in player_columns.items():
            cell = cells[f"{col}{row}"]
            side = cell["value"].strip().upper()
            if side not in ("O", "U"):
                raise ValueError(f"Pronostico non valido: {player}, {name}")
            picks[player] = {"side": side, "lock": cell["bold"]}
        teams.append({"id": code, "name": name, "conference": conference, "line": line, "picks": picks})
    if len({team["id"] for team in teams}) != 30:
        raise ValueError("Il file deve contenere 30 squadre diverse")
    return {
        "season": f"{year}-{str(year + 1)[-2:]}", "startYear": year, "games": 82,
        "timezone": "Europe/Berlin", "players": PLAYERS,
        "linesNote": cells.get("A35", {}).get("value", "Linee fisse dal file originale."),
        "teams": teams,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", nargs="?", type=Path, default=ROOT / "NBA_OU.xlsx")
    parser.add_argument("--output", type=Path, default=ROOT / "data/picks.json")
    args = parser.parse_args()
    data = extract_picks(args.workbook)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Importati {len(data['teams'])} team, stagione {data['season']}.")
    print("Locks: " + ", ".join(f"{p} {sum(t['picks'][p]['lock'] for t in data['teams'])}" for p in PLAYERS))


if __name__ == "__main__":
    main()
