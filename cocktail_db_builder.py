#!/usr/bin/env python3
"""
Cocktail DB Builder
- Bewertet Quellen anhand einfacher SEO/SEA/Review-Signale
- Nutzt bevorzugt API/offizielle Quellen statt aggressivem Scraping
- Übernimmt nur Rezepte mit metrischen Mengenangaben (ml/cl/dash/splash optional)
- Speichert Cocktails in SQLite
- Sucht passende Cocktails anhand von 2-3 Zutaten/Infos

Usage:
  python cocktail_db_builder.py build --db cocktails.sqlite
  python cocktail_db_builder.py search --db cocktails.sqlite --ingredients gin lime mint
  python cocktail_db_builder.py template --file meine_cocktails.csv
  python cocktail_db_builder.py import-csv --file meine_cocktails.csv --db cocktails.sqlite
  python cocktail_db_builder.py add --db cocktails.sqlite --name "Mein Drink" --ingredient "Gin=50" --ingredient "Lime juice=25"
"""
from __future__ import annotations

import argparse
import dataclasses
import csv
import json
import math
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.robotparser
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

USER_AGENT = "CocktailResearchBot/1.0 (+personal research; respects robots.txt)"
REQUEST_DELAY_SECONDS = 1.2

ML_RE = re.compile(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>ml|milliliter|millilitres|milliliters)\b", re.I)
CL_RE = re.compile(r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>cl|centiliter|centilitres|centiliters)\b", re.I)
OZ_RE = re.compile(r"\b(?:\d+(?:[./]\d+)?|\d+(?:\.\d+)?)\s*(?:oz|ounce|ounces|fl oz)\b", re.I)
FRACTION_RE = re.compile(r"(\d+)\s*/\s*(\d+)")

# Startquellen: Score kann später mit SEO/SEA APIs überschrieben/ergänzt werden.
SOURCE_CANDIDATES = [
    {
        "name": "TheCocktailDB",
        "base_url": "https://www.thecocktaildb.com/",
        "type": "api",
        "review_score": 4.1,
        "seo_score": 82,
        "sea_score": 20,
        "notes": "Freie Cocktail-API; gute strukturierte Daten, aber Qualität schwankt, da crowd-sourced.",
    },
    {
        "name": "IBA Official Cocktails",
        "base_url": "https://iba-world.com/cocktails/",
        "type": "official",
        "review_score": 4.7,
        "seo_score": 78,
        "sea_score": 5,
        "notes": "Offizielle Cocktail-Liste; sehr gut für Klassiker und ml-Angaben.",
    },
    {
        "name": "Difford's Guide",
        "base_url": "https://www.diffordsguide.com/cocktails",
        "type": "reference",
        "review_score": 4.8,
        "seo_score": 91,
        "sea_score": 15,
        "notes": "Sehr große Cocktail-Datenbank; nur gemäß robots.txt/Terms nutzen, standardmäßig nicht massenhaft scrapen.",
    },
]


def source_quality(row: dict[str, Any]) -> float:
    """Gewichtete Quellebewertung. SEA nur leicht gewichtet, weil Anzeigenpräsenz kein Qualitätsmerkmal ist."""
    review = float(row.get("review_score", 0)) / 5 * 100
    seo = float(row.get("seo_score", 0))
    sea = float(row.get("sea_score", 0))
    return round(0.55 * review + 0.35 * seo + 0.10 * sea, 2)


def can_fetch(url: str, user_agent: str = USER_AGENT) -> bool:
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.set_url(robots_url)
        rp.read()
        return rp.can_fetch(user_agent, url)
    except Exception:
        # Konservativ: Wenn robots.txt nicht geprüft werden kann, nicht crawlen.
        return False


def request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    r = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=25)
    r.raise_for_status()
    return r.json()


def fetch_html(url: str) -> str:
    if not can_fetch(url):
        raise RuntimeError(f"robots.txt blockiert oder konnte nicht geprüft werden: {url}")
    time.sleep(REQUEST_DELAY_SECONDS)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    r.raise_for_status()
    return r.text


def parse_metric_measure(raw: str | None) -> tuple[float | None, str | None]:
    """Gibt Menge in ml zurück. Oz-Rezepte werden ausgeschlossen."""
    if not raw:
        return None, None
    s = raw.strip().lower().replace("½", "0.5").replace("¼", "0.25").replace("¾", "0.75")
    if OZ_RE.search(s):
        return None, "oz"
    m = ML_RE.search(s)
    if m:
        return float(m.group("num").replace(",", ".")), "ml"
    m = CL_RE.search(s)
    if m:
        return float(m.group("num").replace(",", ".")) * 10, "ml"
    if any(word in s for word in ["dash", "splash", "top up", "garnish", "pinch", "sprig", "wedge", "slice", "leaf", "leaves"]):
        return None, "non_volume_ok"
    # Keine verwertbare metrische Angabe -> nicht übernehmen.
    return None, None


def normalize_ingredient_name(name: str) -> str:
    name = name.lower().strip()
    replacements = {
        "freshly squeezed ": "",
        "fresh ": "",
        "juice": "juice",
        "syrup": "syrup",
        "white rum": "rum",
        "light rum": "rum",
        "gin ": "gin ",
    }
    for a, b in replacements.items():
        name = name.replace(a, b)
    name = re.sub(r"\s+", " ", name)
    return name


@dataclasses.dataclass
class Ingredient:
    name: str
    amount_ml: float | None
    note: str | None = None


@dataclasses.dataclass
class Cocktail:
    name: str
    source: str
    source_url: str | None
    category: str | None
    glass: str | None
    instructions: str | None
    ingredients: list[Ingredient]
    rating: float = 0.0

    def has_only_metric_amounts(self) -> bool:
        # Mindestens eine ml-Zutat; keine erkannte oz-Angabe; Garnish/Dash etc. erlaubt.
        return any(i.amount_ml is not None for i in self.ingredients)


def iter_thecocktaildb() -> Iterable[Cocktail]:
    """Sammelt Drinks über die freie Search-by-first-letter API."""
    seen: set[str] = set()
    for letter in "abcdefghijklmnopqrstuvwxyz":
        data = request_json("https://www.thecocktaildb.com/api/json/v1/1/search.php", {"f": letter})
        for drink in data.get("drinks") or []:
            drink_id = drink.get("idDrink")
            if not drink_id or drink_id in seen:
                continue
            seen.add(drink_id)
            ingredients: list[Ingredient] = []
            invalid = False
            for i in range(1, 16):
                ing = drink.get(f"strIngredient{i}")
                measure = drink.get(f"strMeasure{i}")
                if not ing:
                    continue
                amount_ml, unit_state = parse_metric_measure(measure)
                if unit_state == "oz" or (measure and unit_state is None):
                    invalid = True
                    break
                ingredients.append(Ingredient(normalize_ingredient_name(ing), amount_ml, measure.strip() if measure else None))
            if invalid:
                continue
            c = Cocktail(
                name=drink.get("strDrink", "").strip(),
                source="TheCocktailDB",
                source_url=f"https://www.thecocktaildb.com/drink/{drink_id}",
                category=drink.get("strCategory"),
                glass=drink.get("strGlass"),
                instructions=drink.get("strInstructions"),
                ingredients=ingredients,
                rating=source_quality(next(s for s in SOURCE_CANDIDATES if s["name"] == "TheCocktailDB")),
            )
            if c.name and c.has_only_metric_amounts():
                yield c
        time.sleep(0.25)


def iter_iba_from_public_page(max_pages: int = 120) -> Iterable[Cocktail]:
    """Best-effort IBA-Crawler. Funktioniert, wenn die IBA-Seiten serverseitig Rezeptdetails ausliefern."""
    base = "https://iba-world.com/cocktails/all-cocktails/"
    html = fetch_html(base)
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.select("a[href]"):
        href = urllib.parse.urljoin(base, a["href"])
        if "/cocktail/" in href or "/cocktails/" in href:
            if href not in links and "all-cocktails" not in href:
                links.append(href)
    for url in links[:max_pages]:
        try:
            detail = fetch_html(url)
        except Exception:
            continue
        dsoup = BeautifulSoup(detail, "html.parser")
        title = (dsoup.find("h1") or dsoup.find("title"))
        name = title.get_text(" ", strip=True) if title else None
        text = dsoup.get_text("\n", strip=True)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        ingredients: list[Ingredient] = []
        for ln in lines:
            if OZ_RE.search(ln):
                ingredients = []
                break
            m = ML_RE.search(ln) or CL_RE.search(ln)
            if m:
                amount_ml, state = parse_metric_measure(ln)
                if amount_ml is not None:
                    ing_name = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:ml|cl|milliliters?|millilitres?|centiliters?|centilitres?)\b", "", ln, flags=re.I).strip(" -:•")
                    ingredients.append(Ingredient(normalize_ingredient_name(ing_name), amount_ml, None))
        if name and ingredients:
            yield Cocktail(
                name=name.replace("– IBA", "").strip(),
                source="IBA Official Cocktails",
                source_url=url,
                category="IBA",
                glass=None,
                instructions=None,
                ingredients=ingredients,
                rating=source_quality(next(s for s in SOURCE_CANDIDATES if s["name"] == "IBA Official Cocktails")),
            )


def init_db(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS sources (
            name TEXT PRIMARY KEY,
            base_url TEXT,
            type TEXT,
            review_score REAL,
            seo_score REAL,
            sea_score REAL,
            quality_score REAL,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS cocktails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            category TEXT,
            glass TEXT,
            instructions TEXT,
            rating REAL,
            UNIQUE(name, source)
        );
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cocktail_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            amount_ml REAL,
            note TEXT,
            FOREIGN KEY(cocktail_id) REFERENCES cocktails(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ing_name ON ingredients(name);
        """
    )
    return con


def upsert_sources(con: sqlite3.Connection) -> None:
    for s in SOURCE_CANDIDATES:
        con.execute(
            """INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                s["name"], s["base_url"], s["type"], s["review_score"], s["seo_score"],
                s["sea_score"], source_quality(s), s["notes"]
            ),
        )
    con.commit()


def insert_cocktail(con: sqlite3.Connection, c: Cocktail, replace_existing: bool = False) -> bool:
    if replace_existing:
        existing = con.execute(
            "SELECT id FROM cocktails WHERE lower(name)=lower(?) AND source=?",
            (c.name, c.source),
        ).fetchone()
        if existing:
            cocktail_id = existing[0]
            con.execute(
                """UPDATE cocktails
                   SET source_url=?, category=?, glass=?, instructions=?, rating=?
                   WHERE id=?""",
                (c.source_url, c.category, c.glass, c.instructions, c.rating, cocktail_id),
            )
            con.execute("DELETE FROM ingredients WHERE cocktail_id=?", (cocktail_id,))
        else:
            cur = con.execute(
                """INSERT INTO cocktails(name, source, source_url, category, glass, instructions, rating)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (c.name, c.source, c.source_url, c.category, c.glass, c.instructions, c.rating),
            )
            cocktail_id = cur.lastrowid
    else:
        cur = con.execute(
            """INSERT OR IGNORE INTO cocktails(name, source, source_url, category, glass, instructions, rating)
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (c.name, c.source, c.source_url, c.category, c.glass, c.instructions, c.rating),
        )
        if cur.rowcount == 0:
            return False
        cocktail_id = cur.lastrowid

    for ing in c.ingredients:
        con.execute(
            "INSERT INTO ingredients(cocktail_id, name, amount_ml, note) VALUES (?, ?, ?, ?)",
            (cocktail_id, normalize_ingredient_name(ing.name), ing.amount_ml, ing.note),
        )
    return True


def build(db_path: str, limit: int | None = None, include_iba: bool = True) -> None:
    con = init_db(db_path)
    upsert_sources(con)
    count = 0
    generators = [iter_thecocktaildb()]
    if include_iba:
        generators.append(iter_iba_from_public_page())
    for gen in generators:
        for cocktail in gen:
            if insert_cocktail(con, cocktail):
                count += 1
                if limit is not None and count >= limit:
                    con.commit()
                    print(f"Fertig: {count} neue Cocktails in {db_path}")
                    return
        con.commit()
    total = con.execute("SELECT COUNT(*) FROM cocktails").fetchone()[0]
    print(f"Fertig: {count} neue Cocktails gesammelt. Insgesamt in der Datenbank: {total}")


def count_cocktails(db_path: str) -> int:
    con = init_db(db_path)
    return int(con.execute("SELECT COUNT(*) FROM cocktails").fetchone()[0])


def create_csv_template(file_path: str) -> None:
    rows = [
        {
            "name": "Beispiel Gin Fizz",
            "source": "Manual",
            "source_url": "",
            "category": "Sour/Fizz",
            "glass": "Highball",
            "instructions": "Alle Zutaten außer Soda shaken, in ein Glas geben und mit Soda auffüllen.",
            "ingredient": "Gin",
            "amount_ml": "50",
            "note": "",
        },
        {"name": "Beispiel Gin Fizz", "source": "Manual", "source_url": "", "category": "Sour/Fizz", "glass": "Highball", "instructions": "", "ingredient": "Lemon juice", "amount_ml": "25", "note": ""},
        {"name": "Beispiel Gin Fizz", "source": "Manual", "source_url": "", "category": "Sour/Fizz", "glass": "Highball", "instructions": "", "ingredient": "Sugar syrup", "amount_ml": "20", "note": ""},
        {"name": "Beispiel Gin Fizz", "source": "Manual", "source_url": "", "category": "Sour/Fizz", "glass": "Highball", "instructions": "", "ingredient": "Soda water", "amount_ml": "80", "note": "top up"},
    ]
    fieldnames = ["name", "source", "source_url", "category", "glass", "instructions", "ingredient", "amount_ml", "note"]
    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV-Vorlage erstellt: {file_path}")


def import_csv(db_path: str, file_path: str, replace_existing: bool = True) -> None:
    con = init_db(db_path)
    upsert_sources(con)
    with open(file_path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(2048)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=";,	")
        reader = csv.DictReader(f, dialect=dialect)
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in reader:
            name = (row.get("name") or "").strip()
            ingredient = (row.get("ingredient") or "").strip()
            if not name or not ingredient:
                continue
            source = (row.get("source") or "Manual").strip() or "Manual"
            key = (name, source)
            grouped.setdefault(key, {
                "name": name,
                "source": source,
                "source_url": (row.get("source_url") or "").strip() or None,
                "category": (row.get("category") or "").strip() or None,
                "glass": (row.get("glass") or "").strip() or None,
                "instructions": (row.get("instructions") or "").strip() or None,
                "ingredients": [],
            })
            amount_raw = (row.get("amount_ml") or "").strip().replace(",", ".")
            if not amount_raw:
                amount_ml = None
            else:
                try:
                    amount_ml = float(amount_raw)
                except ValueError as exc:
                    raise ValueError(f"Ungültige ml-Angabe bei {name}/{ingredient}: {amount_raw}") from exc
            grouped[key]["ingredients"].append(Ingredient(ingredient, amount_ml, (row.get("note") or "").strip() or None))

    added = 0
    for data in grouped.values():
        c = Cocktail(
            name=data["name"], source=data["source"], source_url=data["source_url"],
            category=data["category"], glass=data["glass"], instructions=data["instructions"],
            ingredients=data["ingredients"], rating=100.0 if data["source"] == "Manual" else 0.0,
        )
        if insert_cocktail(con, c, replace_existing=replace_existing):
            added += 1
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM cocktails").fetchone()[0]
    print(f"Import fertig: {added} Cocktails importiert/aktualisiert. Insgesamt in der Datenbank: {total}")


def parse_cli_ingredient(raw: str) -> Ingredient:
    if "=" not in raw:
        raise ValueError(f"Zutat muss im Format Name=ml angegeben werden, z. B. Gin=50. Fehler: {raw}")
    name, amount = raw.split("=", 1)
    name = name.strip()
    amount = amount.strip().replace(",", ".")
    if not name:
        raise ValueError("Zutat ohne Namen gefunden.")
    return Ingredient(name=name, amount_ml=float(amount), note=None)


def add_manual_cocktail(db_path: str, name: str, ingredients: list[str], category: str | None = None, glass: str | None = None, instructions: str | None = None) -> None:
    con = init_db(db_path)
    parsed = [parse_cli_ingredient(x) for x in ingredients]
    c = Cocktail(
        name=name, source="Manual", source_url=None, category=category, glass=glass, instructions=instructions, ingredients=parsed, rating=100.0
    )
    insert_cocktail(con, c, replace_existing=True)
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM cocktails").fetchone()[0]
    print(f"Gespeichert: {name}. Insgesamt in der Datenbank: {total}")


def search(db_path: str, ingredients: list[str], max_results: int = 10) -> list[dict[str, Any]]:
    con = sqlite3.connect(db_path)
    wanted = [normalize_ingredient_name(x) for x in ingredients]
    rows = con.execute(
        """
        SELECT c.id, c.name, c.source, c.source_url, c.category, c.glass, c.instructions, c.rating,
               GROUP_CONCAT(i.name || ':' || COALESCE(i.amount_ml, '') || ':' || COALESCE(i.note, ''), '|') AS ing_blob
        FROM cocktails c JOIN ingredients i ON c.id = i.cocktail_id
        GROUP BY c.id
        """
    ).fetchall()
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        cid, name, source, url, category, glass, instructions, rating, blob = row
        ing_items = []
        ing_names = []
        for item in (blob or "").split("|"):
            parts = item.split(":", 2)
            if len(parts) == 3:
                ing_name, amount, note = parts
                ing_names.append(ing_name)
                ing_items.append({"name": ing_name, "amount_ml": float(amount) if amount else None, "note": note or None})
        matches = 0
        for w in wanted:
            if any(w in ing or ing in w for ing in ing_names):
                matches += 1
        if matches == 0:
            continue
        # Score: Anteil Treffer + Quellenqualität + leichte Strafe für zu komplexe Drinks
        score = (matches / len(wanted)) * 100 + float(rating or 0) * 0.15 - max(0, len(ing_items) - 5) * 2
        scored.append((score, {
            "name": name,
            "score": round(score, 1),
            "source": source,
            "source_url": url,
            "category": category,
            "glass": glass,
            "instructions": instructions,
            "ingredients": ing_items,
            "matched_ingredients": matches,
        }))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:max_results]]


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--db", default="cocktails.sqlite")
    b.add_argument("--limit", type=int, default=None, help="Optionales Limit. Ohne Angabe wird alles gesammelt, was die Quellen liefern.")
    b.add_argument("--no-iba", action="store_true")

    s = sub.add_parser("search")
    s.add_argument("--db", default="cocktails.sqlite")
    s.add_argument("--ingredients", nargs="+", required=True)
    s.add_argument("--max-results", type=int, default=10)

    t = sub.add_parser("template")
    t.add_argument("--file", default="meine_cocktails.csv")

    imp = sub.add_parser("import-csv")
    imp.add_argument("--db", default="cocktails.sqlite")
    imp.add_argument("--file", required=True)
    imp.add_argument("--no-replace", action="store_true", help="Vorhandene manuelle Cocktails nicht überschreiben.")

    a = sub.add_parser("add")
    a.add_argument("--db", default="cocktails.sqlite")
    a.add_argument("--name", required=True)
    a.add_argument("--ingredient", action="append", required=True, help='Format: "Gin=50". Mehrfach angeben.')
    a.add_argument("--category")
    a.add_argument("--glass")
    a.add_argument("--instructions")

    c = sub.add_parser("count")
    c.add_argument("--db", default="cocktails.sqlite")

    args = parser.parse_args()

    if args.cmd == "build":
        build(args.db, args.limit, include_iba=not args.no_iba)
    elif args.cmd == "search":
        results = search(args.db, args.ingredients, args.max_results)
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif args.cmd == "template":
        create_csv_template(args.file)
    elif args.cmd == "import-csv":
        import_csv(args.db, args.file, replace_existing=not args.no_replace)
    elif args.cmd == "add":
        add_manual_cocktail(args.db, args.name, args.ingredient, args.category, args.glass, args.instructions)
    elif args.cmd == "count":
        print(count_cocktails(args.db))


if __name__ == "__main__":
    main()
