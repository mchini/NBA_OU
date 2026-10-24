"""Package the source files needed for a new GitHub repository."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [ROOT / name for name in ("index.html", "README.md", ".gitignore", "NBA_OU.xlsx")]
    for folder, pattern in (("assets", "*"), ("data", "*.json"), ("scripts", "*.py"), ("tests", "*.py"), ("tests", "*.mjs"), (".github/workflows", "*.yml")):
        files.extend(p for p in (ROOT / folder).glob(pattern) if p.is_file())
    destination = ROOT / "NBA-OU-GitHub.zip"
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, path.relative_to(ROOT).as_posix())
    with ZipFile(destination) as archive:
        assert archive.testzip() is None
        assert ".github/workflows/daily-pages.yml" in archive.namelist()
        assert not any("__pycache__" in name or name.startswith("_site/") for name in archive.namelist())
        print(f"Archivio verificato: {destination.name}, {len(archive.namelist())} file, {destination.stat().st_size:,} byte")


if __name__ == "__main__":
    main()
