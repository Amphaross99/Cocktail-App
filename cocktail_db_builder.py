from __future__ import annotations

import argparse
import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path


ALLOWED_ICE_VALUES = {"crushed ice", "ice cubes", "no ice", ""}


@dataclass
class Ingredient:
    name: str
    amount_ml: float | None
    note: str | None = None


@dataclass
class Cocktail:
    name: str
    source: str | None
    source_url: str | None
    category: str | None
    glass: str | None
    ice: str | None
    instructions: str | None
    ingredients: list[Ingredient]
    rating: float = 100.0


def normalize_name(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def normalize_ice(value: str | None) -> str | None:
    v = normalize_name(value).lower()
    aliases = {
        "crushed": "crushed ice",
        "crushed_ice": "crushed ice",
        "crushed ice": "crushed ice",
        "ice": "ice cubes",
        "ice cube": "ice cubes",
        "ice cubes": "ice cubes",
        "cubes": "ice cubes",
        "cubed ice": "ice cubes",
        "cubed_ice": "ice cubes",
        "no ice": "no ice",
        "none": "no ice",
        "without ice": "no ice",
        "kein eis": "no ice",
        "ohne eis": "no ice",
        "": "",
    }
    return aliases.get(v, v if v in ALLOWED_ICE_VALUES else None)


def parse_amount(value: str | None) -> float | None:
    raw = (value or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_manual_ingredient(line: str) -> Ingredient:
    if "=" not in line:
        return Ingredient(name=normalize_name(line), amount_ml=None, note=None)
    name, amount = line.split("=", 1)
    return Ingredient(name=normalize_name(name), amount_ml=parse_amount(amount), note=None)


def connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _has_unique_name_constraint(con: sqlite3.Connection) -> bool:
    rows = con.execute("PRAGMA index_list(cocktails)").fetchall()
    for row in rows:
        # row: seq, name, unique, origin, partial
        if len(row) >= 3 and row[2]:
            index_name = row[1]
            cols = con.execute(f"PRAGMA index_info({index_name})").fetchall()
            col_names = [c[2] for c in cols]
            if col_names == ["name"]:
                return True
    return False


def ensure_schema(db_path: str | Path) -> None:
    con = connect(db_path)
    cur = con.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cocktails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source TEXT,
            source_url TEXT,
            category TEXT,
            glass TEXT,
            ice TEXT,
            instructions TEXT,
            rating REAL DEFAULT 100
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cocktail_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            amount_ml REAL,
            note TEXT,
            FOREIGN KEY(cocktail_id) REFERENCES cocktails(id) ON DELETE CASCADE
        )
        """
    )

    cur.execute("PRAGMA table_info(cocktails)")
    cols = {row[1] for row in cur.fetchall()}
    if "ice" not in cols:
        cur.execute("ALTER TABLE cocktails ADD COLUMN ice TEXT")

    # Migration for old databases where cocktail name was UNIQUE.
    # SQLite cannot drop that constraint directly, so rebuild the table.
    if _has_unique_name_constraint(con):
        cur.execute("ALTER TABLE cocktails RENAME TO cocktails_old")
        cur.execute(
            """
            CREATE TABLE cocktails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source TEXT,
                source_url TEXT,
                category TEXT,
                glass TEXT,
                ice TEXT,
                instructions TEXT,
                rating REAL DEFAULT 100
            )
            """
        )
        old_cols = {row[1] for row in cur.execute("PRAGMA table_info(cocktails_old)").fetchall()}
        ice_expr = "ice" if "ice" in old_cols else "NULL AS ice"
        cur.execute(
            f"""
            INSERT INTO cocktails(id, name, source, source_url, category, glass, ice, instructions, rating)
            SELECT id, name, source, source_url, category, glass, {ice_expr}, instructions, rating
            FROM cocktails_old
            """
        )
        cur.execute("DROP TABLE cocktails_old")

    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cocktail_recipe_unique
        ON cocktails(
            lower(name),
            lower(COALESCE(source, '')),
            lower(COALESCE(source_url, ''))
        )
        """
    )

    con.commit()
    con.close()


def reset_database(db_path: str | Path) -> None:
    ensure_schema(db_path)
    con = connect(db_path)
    cur = con.cursor()
    cur.execute("DELETE FROM ingredients")
    cur.execute("DELETE FROM cocktails")
    con.commit()
    con.close()


def count_cocktails(db_path: str | Path) -> int:
    ensure_schema(db_path)
    con = connect(db_path)
    count = con.execute("SELECT COUNT(*) FROM cocktails").fetchone()[0]
    con.close()
    return int(count)


def count_unique_cocktail_names(db_path: str | Path) -> int:
    ensure_schema(db_path)
    con = connect(db_path)
    count = con.execute("SELECT COUNT(DISTINCT lower(name)) FROM cocktails").fetchone()[0]
    con.close()
    return int(count)


def get_sources(db_path: str | Path) -> list[str]:
    ensure_schema(db_path)
    con = connect(db_path)
    rows = con.execute(
        """
        SELECT DISTINCT COALESCE(NULLIF(TRIM(source), ''), 'Unbekannte Quelle') AS source_name
        FROM cocktails
        ORDER BY source_name COLLATE NOCASE
        """
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def rename_source(db_path: str | Path, old_source: str, new_source: str) -> int:
    ensure_schema(db_path)
    old_source = normalize_name(old_source)
    new_source = normalize_name(new_source)
    if not old_source or not new_source:
        raise ValueError("Alte und neue Quelle dürfen nicht leer sein.")

    con = connect(db_path)
    cur = con.cursor()

    if old_source == "Unbekannte Quelle":
        cur.execute(
            "UPDATE cocktails SET source=? WHERE source IS NULL OR TRIM(source)=''",
            (new_source,),
        )
    else:
        cur.execute(
            "UPDATE cocktails SET source=? WHERE lower(source)=lower(?)",
            (new_source, old_source),
        )

    changed = cur.rowcount
    con.commit()
    con.close()
    return int(changed)


def upsert_cocktail(db_path: str | Path, cocktail: Cocktail, replace_existing: bool = True) -> None:
    ensure_schema(db_path)
    con = connect(db_path)
    cur = con.cursor()

    ice_value = normalize_ice(cocktail.ice)
    if ice_value is None:
        raise ValueError(f"Ungültiger ice-Wert bei '{cocktail.name}'. Erlaubt: crushed ice, ice cubes, no ice.")

    source = normalize_name(cocktail.source) or "CSV"
    source_url = normalize_name(cocktail.source_url) or None

    existing = cur.execute(
        """
        SELECT id FROM cocktails
        WHERE lower(name)=lower(?)
          AND lower(COALESCE(source, ''))=lower(COALESCE(?, ''))
          AND lower(COALESCE(source_url, ''))=lower(COALESCE(?, ''))
        """,
        (cocktail.name, source, source_url),
    ).fetchone()

    if existing and replace_existing:
        cocktail_id = existing[0]
        cur.execute(
            """
            UPDATE cocktails
               SET source=?, source_url=?, category=?, glass=?, ice=?, instructions=?, rating=?
             WHERE id=?
            """,
            (source, source_url, cocktail.category, cocktail.glass, ice_value, cocktail.instructions, cocktail.rating, cocktail_id),
        )
        cur.execute("DELETE FROM ingredients WHERE cocktail_id=?", (cocktail_id,))
    elif existing:
        con.close()
        return
    else:
        cur.execute(
            """
            INSERT INTO cocktails(name, source, source_url, category, glass, ice, instructions, rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (cocktail.name, source, source_url, cocktail.category, cocktail.glass, ice_value, cocktail.instructions, cocktail.rating),
        )
        cocktail_id = cur.lastrowid

    for ingredient in cocktail.ingredients:
        if not ingredient.name:
            continue
        cur.execute(
            """
            INSERT INTO ingredients(cocktail_id, name, amount_ml, note)
            VALUES (?, ?, ?, ?)
            """,
            (cocktail_id, ingredient.name, ingredient.amount_ml, ingredient.note),
        )

    con.commit()
    con.close()


def export_template_csv(file_path: str | Path) -> None:
    rows = [
        {
            "name": "Espresso Martini",
            "source": "Hausrezept",
            "source_url": "",
            "category": "Modern Classic",
            "glass": "Chilled Martini/Coupe",
            "ice": "no ice",
            "instructions": "Shake with ice and fine strain into a chilled glass.",
            "ingredient": "Vodka",
            "amount_ml": "50",
            "note": "",
        },
        {
            "name": "Espresso Martini",
            "source": "Hausrezept",
            "source_url": "",
            "category": "Modern Classic",
            "glass": "Chilled Martini/Coupe",
            "ice": "no ice",
            "instructions": "Shake with ice and fine strain into a chilled glass.",
            "ingredient": "Coffee liqueur",
            "amount_ml": "25",
            "note": "",
        },
        {
            "name": "Espresso Martini",
            "source": "Hausrezept",
            "source_url": "",
            "category": "Modern Classic",
            "glass": "Chilled Martini/Coupe",
            "ice": "no ice",
            "instructions": "Shake with ice and fine strain into a chilled glass.",
            "ingredient": "Espresso",
            "amount_ml": "25",
            "note": "",
        },
        {
            "name": "Espresso Martini",
            "source": "IBA",
            "source_url": "",
            "category": "Modern Classic",
            "glass": "Chilled Martini/Coupe",
            "ice": "no ice",
            "instructions": "Shake with ice and strain into a chilled glass.",
            "ingredient": "Vodka",
            "amount_ml": "50",
            "note": "",
        },
        {
            "name": "Espresso Martini",
            "source": "IBA",
            "source_url": "",
            "category": "Modern Classic",
            "glass": "Chilled Martini/Coupe",
            "ice": "no ice",
            "instructions": "Shake with ice and strain into a chilled glass.",
            "ingredient": "Coffee liqueur",
            "amount_ml": "30",
            "note": "",
        },
    ]
    fieldnames = ["name", "source", "source_url", "category", "glass", "ice", "instructions", "ingredient", "amount_ml", "note"]
    with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def import_csv(db_path: str | Path, file_path: str | Path, replace_existing: bool = True) -> int:
    ensure_schema(db_path)
    grouped: dict[tuple[str, str, str], dict] = {}

    with open(file_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"name", "ingredient"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV fehlt Pflichtspalten: {', '.join(sorted(missing))}")

        for row in reader:
            name = normalize_name(row.get("name"))
            ingredient_name = normalize_name(row.get("ingredient"))
            if not name or not ingredient_name:
                continue

            source = normalize_name(row.get("source")) or "CSV"
            source_url = normalize_name(row.get("source_url")) or ""
            key = (name.lower(), source.lower(), source_url.lower())

            if key not in grouped:
                grouped[key] = {
                    "name": name,
                    "source": source,
                    "source_url": source_url or None,
                    "category": normalize_name(row.get("category")) or None,
                    "glass": normalize_name(row.get("glass")) or None,
                    "ice": normalize_ice(row.get("ice")),
                    "instructions": normalize_name(row.get("instructions")) or None,
                    "ingredients": [],
                }

            for field in ["category", "glass", "instructions"]:
                if not grouped[key].get(field) and normalize_name(row.get(field)):
                    grouped[key][field] = normalize_name(row.get(field))

            if not grouped[key].get("ice") and normalize_ice(row.get("ice")):
                grouped[key]["ice"] = normalize_ice(row.get("ice"))

            grouped[key]["ingredients"].append(
                Ingredient(
                    name=ingredient_name,
                    amount_ml=parse_amount(row.get("amount_ml")),
                    note=normalize_name(row.get("note")) or None,
                )
            )

    imported = 0
    for data in grouped.values():
        ice_value = data.get("ice")
        if ice_value is None:
            raise ValueError(f"Ungültiger ice-Wert bei '{data['name']}'. Erlaubt: crushed ice, ice cubes, no ice.")
        cocktail = Cocktail(
            name=data["name"],
            source=data["source"],
            source_url=data["source_url"],
            category=data["category"],
            glass=data["glass"],
            ice=ice_value,
            instructions=data["instructions"],
            ingredients=data["ingredients"],
        )
        upsert_cocktail(db_path, cocktail, replace_existing=replace_existing)
        imported += 1

    return imported


def add_manual_cocktail(
    db_path: str | Path,
    name: str,
    ingredients: list[str],
    category: str | None = None,
    glass: str | None = None,
    ice: str | None = None,
    source: str | None = None,
    source_url: str | None = None,
    instructions: str | None = None,
) -> None:
    parsed = [parse_manual_ingredient(line) for line in ingredients]
    cocktail = Cocktail(
        name=normalize_name(name),
        source=source or "Manual",
        source_url=source_url,
        category=category,
        glass=glass,
        ice=ice,
        instructions=instructions,
        ingredients=parsed,
    )
    upsert_cocktail(db_path, cocktail, replace_existing=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="CSV-only Cocktail Database Tool")
    sub = parser.add_subparsers(dest="command", required=True)

    p_count = sub.add_parser("count")
    p_count.add_argument("--db", default="cocktails.sqlite")

    p_reset = sub.add_parser("reset")
    p_reset.add_argument("--db", default="cocktails.sqlite")

    p_template = sub.add_parser("template")
    p_template.add_argument("--file", default="cocktail_template.csv")

    p_import = sub.add_parser("import-csv")
    p_import.add_argument("--db", default="cocktails.sqlite")
    p_import.add_argument("--file", required=True)
    p_import.add_argument("--keep-existing", action="store_true", help="Rezepte mit gleichem Name+Quelle+URL nicht ersetzen")

    p_rename = sub.add_parser("rename-source")
    p_rename.add_argument("--db", default="cocktails.sqlite")
    p_rename.add_argument("--old", required=True)
    p_rename.add_argument("--new", required=True)

    p_add = sub.add_parser("add")
    p_add.add_argument("--db", default="cocktails.sqlite")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--ingredient", action="append", required=True)
    p_add.add_argument("--category")
    p_add.add_argument("--glass")
    p_add.add_argument("--ice", choices=["crushed ice", "ice cubes", "no ice"])
    p_add.add_argument("--source", default="Manual")
    p_add.add_argument("--source-url")
    p_add.add_argument("--instructions")

    args = parser.parse_args()

    if args.command == "count":
        print(count_cocktails(args.db))
    elif args.command == "reset":
        reset_database(args.db)
        print("Database cleared.")
    elif args.command == "template":
        export_template_csv(args.file)
        print(f"Template written to {args.file}")
    elif args.command == "import-csv":
        imported = import_csv(args.db, args.file, replace_existing=not args.keep_existing)
        print(f"Imported {imported} recipes. Total recipes: {count_cocktails(args.db)}")
    elif args.command == "rename-source":
        changed = rename_source(args.db, args.old, args.new)
        print(f"Renamed source for {changed} recipes.")
    elif args.command == "add":
        add_manual_cocktail(args.db, args.name, args.ingredient, args.category, args.glass, args.ice, args.source, args.source_url, args.instructions)
        print(f"Added: {args.name}. Total recipes: {count_cocktails(args.db)}")


if __name__ == "__main__":
    main()
