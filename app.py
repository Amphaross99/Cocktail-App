from __future__ import annotations

import sqlite3
from pathlib import Path
import tempfile
import re

import streamlit as st

from cocktail_db_builder import (
    count_cocktails,
    count_unique_cocktail_names,
    get_sources,
    rename_source,
    import_csv,
    reset_database,
    export_template_csv,
    ensure_schema,
)

DB_PATH = "cocktails.sqlite"

st.set_page_config(page_title="Cocktail Finder", page_icon="🍸", layout="wide")

st.title("🍸 Cocktail Finder")
st.caption("CSV-basierte Cocktail-Datenbank mit mehreren Rezepten pro Cocktail, Quellenfilter, Broad-/Exact-Match-Suche, Glas-Symbolen und Ice-Feld.")


# -----------------------------
# Suche: Broad Match + Exact Match
# -----------------------------

INGREDIENT_SYNONYMS = {
    "kaffee": ["kaffee", "kaffe", "coffee", "espresso", "cold brew", "kahlua", "coffee liqueur", "kaffeelikör", "kaffeelikoer", "coffee beans"],
    "espresso": ["espresso", "coffee", "kaffee", "kaffe", "kahlua", "coffee liqueur", "kaffeelikör", "kaffeelikoer"],
    "limette": ["limette", "lime", "fresh lime juice", "lime juice", "lime wedge", "lime wedges", "lime cordial"],
    "lime": ["lime", "limette", "fresh lime juice", "lime juice", "lime wedge", "lime wedges", "lime cordial"],
    "zitrone": ["zitrone", "lemon", "fresh lemon juice", "lemon juice", "lemon wedge", "lemon zest", "lemon peel"],
    "lemon": ["lemon", "zitrone", "fresh lemon juice", "lemon juice", "lemon wedge", "lemon zest", "lemon peel"],
    "orange": ["orange", "orange juice", "orangensaft", "orange zest", "orange peel", "triple sec", "cointreau", "grand marnier", "orange liqueur", "orangenlikör", "orangenlikoer"],
    "grapefruit": ["grapefruit", "grapefruit juice", "grapefruitsaft", "pink grapefruit", "grapefruit soda"],
    "zucker": ["zucker", "sugar", "sugar syrup", "simple syrup", "zuckersirup", "sirup", "syrup", "powdered sugar", "brown sugar", "demerara syrup", "agave syrup", "honey", "honig", "vanilla syrup"],
    "sirup": ["sirup", "syrup", "sugar syrup", "simple syrup", "zuckersirup", "agave syrup", "vanilla syrup", "grenadine", "orgeat syrup", "honey"],
    "minze": ["minze", "mint", "mint leaves", "mint sprig", "peppermint", "spearmint"],
    "mint": ["mint", "minze", "mint leaves", "mint sprig", "peppermint", "spearmint"],
    "basilikum": ["basilikum", "basil", "basil leaves", "basil leaf"],
    "basil": ["basil", "basilikum", "basil leaves", "basil leaf"],
    "rum": ["rum", "white rum", "light rum", "dark rum", "black rum", "gold rum", "spiced rum", "overproof rum", "bacardi", "havana", "havana club", "cachaca", "cachaça"],
    "gin": ["gin", "dry gin", "london dry gin", "bombay", "gordons", "tanqueray", "hendricks", "sloe gin"],
    "vodka": ["vodka", "wodka", "vanilla vodka", "citron vodka", "absolut", "grey goose", "belvedere"],
    "wodka": ["wodka", "vodka", "vanilla vodka", "citron vodka"],
    "tequila": ["tequila", "blanco tequila", "silver tequila", "reposado tequila", "mezcal"],
    "mezcal": ["mezcal", "tequila"],
    "whiskey": ["whiskey", "whisky", "bourbon", "rye", "scotch", "irish whiskey", "canadian whisky", "jack daniels", "jameson", "makers mark"],
    "whisky": ["whisky", "whiskey", "scotch", "bourbon", "rye", "irish whiskey"],
    "bourbon": ["bourbon", "whiskey", "whisky", "rye"],
    "scotch": ["scotch", "scotch whisky", "whisky", "whiskey"],
    "brandy": ["brandy", "cognac", "weinbrand", "cherry brandy", "apricot brandy", "pisco", "calvados"],
    "cognac": ["cognac", "brandy", "weinbrand"],
    "likör": ["liqueur", "likör", "likoer", "amaretto", "cointreau", "triple sec", "kahlua", "baileys", "chambord", "maraschino", "peach liqueur", "passionfruit liqueur", "apricot liqueur", "elderflower liqueur"],
    "liqueur": ["liqueur", "likör", "likoer", "amaretto", "cointreau", "triple sec", "kahlua", "baileys", "chambord", "maraschino"],
    "cointreau": ["cointreau", "triple sec", "orange liqueur", "orangenlikör", "orangenlikoer", "grand marnier"],
    "triple sec": ["triple sec", "cointreau", "orange liqueur", "grand marnier"],
    "mandel": ["mandel", "almond", "amaretto", "orgeat", "almond syrup", "almond liqueur"],
    "amaretto": ["amaretto", "almond", "mandel", "almond liqueur"],
    "sahne": ["sahne", "cream", "fresh cream", "heavy cream", "half and half", "milk", "milch"],
    "milch": ["milch", "milk", "cream", "sahne", "half and half"],
    "ei": ["ei", "egg", "egg white", "eiweiß", "eiweiss", "egg yolk", "eigelb"],
    "eiweiß": ["eiweiß", "eiweiss", "egg white", "egg"],
    "bitter": ["bitter", "bitters", "angostura", "angostura bitters", "orange bitters", "aromatic bitters", "peychaud bitters"],
    "angostura": ["angostura", "angostura bitters", "bitters", "bitter"],
    "wermut": ["wermut", "vermouth", "sweet vermouth", "dry vermouth", "red vermouth", "white vermouth", "martini rosso", "martini bianco"],
    "vermouth": ["vermouth", "wermut", "sweet vermouth", "dry vermouth", "red vermouth", "white vermouth"],
    "campari": ["campari", "bitter", "red bitter"],
    "aperol": ["aperol", "aperitivo", "bitter"],
    "sekt": ["sekt", "sparkling wine", "champagne", "prosecco", "cava", "schaumwein"],
    "champagner": ["champagner", "champagne", "sparkling wine", "sekt", "prosecco", "cava"],
    "prosecco": ["prosecco", "sparkling wine", "sekt", "champagne", "cava"],
    "wein": ["wein", "wine", "white wine", "red wine", "sparkling wine", "port wine", "sherry"],
    "soda": ["soda", "soda water", "club soda", "sparkling water", "mineral water", "wasser", "sprudel"],
    "tonic": ["tonic", "tonic water"],
    "ginger": ["ginger", "ginger beer", "ginger ale", "ingwer", "ingwerbier", "ginger syrup"],
    "cola": ["cola", "coca cola", "coca-cola", "coke"],
    "sprite": ["sprite", "lemonade", "7up", "7 up", "limonade"],
    "saft": ["juice", "saft", "orange juice", "pineapple juice", "cranberry juice", "grapefruit juice", "apple juice", "lemon juice", "lime juice", "tomato juice"],
    "ananassaft": ["ananassaft", "pineapple juice", "pineapple", "ananas"],
    "pineapple": ["pineapple", "pineapple juice", "ananassaft", "ananas"],
    "cranberry": ["cranberry", "cranberry juice", "cranberrysaft"],
    "apfel": ["apfel", "apple", "apple juice", "apfelsaft"],
    "tomate": ["tomate", "tomato", "tomato juice", "tomatensaft"],
    "erdbeere": ["erdbeere", "strawberry", "strawberry puree", "strawberry liqueur"],
    "himbeere": ["himbeere", "raspberry", "raspberry puree", "raspberry liqueur", "chambord"],
    "passionsfrucht": ["passionsfrucht", "maracuja", "passion fruit", "passionfruit", "passionfruit puree", "passionfruit liqueur", "passoa", "passoã"],
    "pfirsich": ["pfirsich", "peach", "peach liqueur", "peach puree", "peachtree"],
    "kirsche": ["kirsche", "cherry", "cherry brandy", "maraschino", "maraschino cherry"],
    "banane": ["banane", "banana", "banana liqueur", "banana puree"],
    "kokos": ["kokos", "coconut", "coconut cream", "cream of coconut", "coconut syrup", "malibu"],
    "grenadine": ["grenadine", "pomegranate syrup", "granatapfelsirup"],
    "maraschino": ["maraschino", "maraschino liqueur", "maraschino cherry", "cherry"],
    "absinth": ["absinth", "absinthe"],
    "tabasco": ["tabasco", "hot sauce"],
    "salz": ["salz", "salt", "salt rim", "pinch of salt"],
    "pfeffer": ["pfeffer", "pepper", "black pepper"],
    "gurke": ["gurke", "cucumber", "cucumber syrup"],
    "honig": ["honig", "honey", "honey syrup"],
}


GLASS_ICON_RULES = [
    ("rocks", "🥃", "Rocks"),
    ("old fashioned", "🥃", "Rocks"),
    ("wine", "🍷", "Wine Glass"),
    ("highball", "🥤", "Highball"),
    ("collins", "🥤", "Highball"),
    ("champagne flute", "🥂", "Champagne Flute"),
    ("flute", "🥂", "Champagne Flute"),
    ("martini", "🍸", "Chilled Martini/Coupe"),
    ("coupe", "🍸", "Chilled Martini/Coupe"),
    ("nick and nora", "🍸", "Chilled Martini/Coupe"),
    ("shooter", "🥃", "Shooter"),
    ("shot", "🥃", "Shooter"),
]

ICE_ICON_MAP = {
    "crushed ice": ("❄️🧊", "Crushed Ice"),
    "ice cubes": ("🧊", "Ice Cubes"),
    "no ice": ("🚫🧊", "No Ice"),
    "": ("❔🧊", "Ice nicht gepflegt"),
    None: ("❔🧊", "Ice nicht gepflegt"),
}


def clean_term(text: str) -> str:
    text = (text or "").lower().strip()
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("'", "").replace("’", "")
    return " ".join(text.split())


def parse_search_query(query: str) -> list[dict]:
    terms: list[dict] = []
    for match in re.finditer(r'"([^"]+)"|([^,;\n]+)', query or ""):
        quoted, plain = match.groups()
        raw = quoted if quoted is not None else plain
        term = clean_term(raw)
        if term:
            terms.append({"term": term, "exact": quoted is not None})
    return terms


def expand_broad_term(term: str) -> set[str]:
    term = clean_term(term)
    expanded = {term}
    for key, values in INGREDIENT_SYNONYMS.items():
        group = {clean_term(key), *[clean_term(v) for v in values]}
        if term in group:
            expanded.update(group)
    return {x for x in expanded if x}


def matches_cocktail_name(cocktail_name: str, term: str, exact: bool) -> bool:
    name_clean = clean_term(cocktail_name)
    term_clean = clean_term(term)
    if not term_clean:
        return False

    if exact:
        return name_clean == term_clean

    # Broad Match für Cocktailnamen:
    # margarita findet Frozen Fruit Margarita, espresso findet Espresso Martini.
    return term_clean in name_clean


def get_glass_icon(glass: str | None) -> tuple[str, str]:
    g = clean_term(glass or "")
    for keyword, icon, label in GLASS_ICON_RULES:
        if keyword in g:
            return icon, label
    return "🍹", glass or "Glas nicht gepflegt"


def normalize_ice(ice: str | None) -> str:
    value = clean_term(ice or "")
    if value in ["crushed", "crushed ice", "crushed_ice"]:
        return "crushed ice"
    if value in ["ice", "ice cubes", "ice cube", "cubes", "cubed ice", "cubed_ice"]:
        return "ice cubes"
    if value in ["no ice", "none", "without ice", "kein eis", "ohne eis"]:
        return "no ice"
    return ""


def get_ice_icon(ice: str | None) -> tuple[str, str]:
    return ICE_ICON_MAP.get(normalize_ice(ice), ICE_ICON_MAP[""])


def db_exists() -> bool:
    return Path(DB_PATH).exists()


def app_search(db_path: str, query_terms: list[dict], max_results: int = 10) -> list[dict]:
    ensure_schema(db_path)
    con = sqlite3.connect(db_path)
    rows = con.execute(
        """
        SELECT c.id, c.name, c.source, c.source_url, c.category, c.glass, c.ice, c.instructions, c.rating,
               GROUP_CONCAT(i.name || ':' || COALESCE(i.amount_ml, '') || ':' || COALESCE(i.note, ''), '|') AS ing_blob
        FROM cocktails c
        LEFT JOIN ingredients i ON c.id = i.cocktail_id
        GROUP BY c.id
        """
    ).fetchall()
    con.close()

    scored: list[tuple[float, dict]] = []
    for row in rows:
        cid, name, source, url, category, glass, ice, instructions, rating, blob = row
        ing_items = []
        ing_names_clean = []

        for item in (blob or "").split("|"):
            if not item:
                continue
            parts = item.split(":", 2)
            if len(parts) == 3:
                ing_name, amount, note = parts
                ing_names_clean.append(clean_term(ing_name))
                try:
                    amount_value = float(amount) if amount else None
                except ValueError:
                    amount_value = None
                ing_items.append({"name": ing_name, "amount_ml": amount_value, "note": note or None})

        matches = 0
        exact_matches = 0
        broad_matches = 0

        for q in query_terms:
            term = q["term"]
            name_matched = matches_cocktail_name(name, term, q["exact"])

            if q["exact"]:
                ingredient_matched = term in ing_names_clean
                matched = ingredient_matched or name_matched
                if matched:
                    exact_matches += 1
            else:
                expanded_terms = expand_broad_term(term)
                ingredient_matched = any(
                    candidate in ingredient or ingredient in candidate
                    for candidate in expanded_terms
                    for ingredient in ing_names_clean
                )
                matched = ingredient_matched or name_matched
                if matched:
                    broad_matches += 1

            if matched:
                matches += 1

        if matches == 0:
            continue

        score = (matches / len(query_terms)) * 100
        score += exact_matches * 8 + broad_matches * 3
        score += float(rating or 0) * 0.15
        score -= max(0, len(ing_items) - 5) * 2

        scored.append((score, {
            "name": name,
            "score": round(score, 1),
            "source": source,
            "source_url": url,
            "category": category,
            "glass": glass,
            "ice": ice,
            "instructions": instructions,
            "ingredients": ing_items,
            "matched_ingredients": matches,
            "recipe_id": cid,
        }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [x[1] for x in scored[:max_results]]


def get_all_cocktails() -> list[tuple]:
    ensure_schema(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        """
        SELECT c.id, c.name, c.source, c.category, c.glass, c.ice,
               GROUP_CONCAT(i.name || ' (' || COALESCE(CAST(i.amount_ml AS TEXT), '-') || ' ml)', ', ') AS ingredients
        FROM cocktails c
        LEFT JOIN ingredients i ON c.id = i.cocktail_id
        GROUP BY c.id
        ORDER BY c.name COLLATE NOCASE
        """
    ).fetchall()
    con.close()
    return rows



def render_recipe_card(result: dict) -> None:
    with st.container(border=True):
        glass_icon, glass_label = get_glass_icon(result.get("glass"))
        ice_icon, ice_label = get_ice_icon(result.get("ice"))

        st.markdown(f"### {glass_icon} {result.get('source') or 'Quelle unbekannt'}")
        if result.get("source_url"):
            st.link_button("Quelle öffnen", result["source_url"], use_container_width=True)

        st.caption(f"{glass_icon} Glas: {result.get('glass') or glass_label} · {ice_icon} Ice: {ice_label}")
        if result.get("category"):
            st.caption(f"📂 Kategorie: {result['category']}")
        st.caption(f"Treffer: {result.get('matched_ingredients', 0)} · Score: {result.get('score', '-')}")

        st.markdown("**Zutaten**")
        for ing in result.get("ingredients", []):
            amount = ing.get("amount_ml")
            amount_text = f"{amount:g} ml" if isinstance(amount, (int, float)) else (ing.get("note") or "nach Bedarf")
            st.write(f"• {ing.get('name', '')}: **{amount_text}**")

        if result.get("instructions"):
            st.markdown("**Zubereitung**")
            st.write(result["instructions"])


def render_grouped_results(results: list[dict]) -> None:
    grouped: dict[str, list[dict]] = {}
    display_names: dict[str, str] = {}

    for result in results:
        key = clean_term(result["name"])
        grouped.setdefault(key, []).append(result)
        display_names[key] = result["name"]

    for key, recipes in grouped.items():
        st.markdown(f"## {display_names[key]}")
        if len(recipes) > 1:
            st.success(f"{len(recipes)} Rezepte gefunden – nebeneinander nach Quelle angezeigt.")
        else:
            st.caption("1 Rezept gefunden.")

        for i in range(0, len(recipes), 3):
            cols = st.columns(min(3, len(recipes) - i))
            for col, recipe in zip(cols, recipes[i:i + 3]):
                with col:
                    render_recipe_card(recipe)


ensure_schema(DB_PATH)

with st.sidebar:
    st.header("Datenbank")
    try:
        st.success(f"{count_unique_cocktail_names(DB_PATH)} Cocktails · {count_cocktails(DB_PATH)} Rezepte gespeichert")
    except Exception as exc:
        st.warning(f"Datenbank vorhanden, aber nicht lesbar: {exc}")

    st.divider()
    st.write("Diese Version nutzt **nur CSV-Import**. Scraping und automatische Online-Quellen wurden entfernt.")

    with st.expander("Datenbank leeren"):
        st.warning("Löscht alle Cocktails und Zutaten aus der lokalen Datenbank dieser App.")
        confirm_reset = st.checkbox("Ja, ich möchte die Datenbank wirklich leeren.")
        if st.button("Datenbank leeren", type="secondary", disabled=not confirm_reset, use_container_width=True):
            reset_database(DB_PATH)
            st.success("Datenbank wurde geleert. Lade jetzt deine CSV-Dateien neu hoch.")
            st.rerun()


tab_search, tab_add, tab_import, tab_browse, tab_sources = st.tabs(["🔍 Suchen", "➕ Cocktail hinzufügen", "📥 CSV importieren", "📚 Datenbank ansehen", "🏷️ Quellen verwalten"])

with tab_search:
    st.header("Cocktail suchen")
    st.markdown(
        '''
        <div style="padding: 0.9rem 1rem; border-radius: 0.75rem; background: rgba(49, 51, 63, 0.08); border: 1px solid rgba(49, 51, 63, 0.15); margin-bottom: 0.75rem;">
            <strong>Suche nach Zutaten oder Cocktailnamen.</strong><br>
            Normal gesucht wird breit, z. B. <code>kaffee</code> findet auch Espresso/Kahlua. Für eine exakte Suche setze den Begriff in Anführungszeichen, z. B. <code>"espresso"</code> oder <code>"Espresso Martini"</code>.
        </div>
        ''',
        unsafe_allow_html=True,
    )
    query = st.text_input("Suche", placeholder='z. B. kaffee, margarita, "vodka" oder "Espresso Martini"')
    max_results = st.slider("Maximale Ergebnisse", 3, 30, 10)

    if st.button("Cocktails suchen", type="primary"):
        query_terms = parse_search_query(query)
        if not query_terms:
            st.warning("Bitte mindestens eine Zutat eingeben.")
        else:
            with st.expander("So wurde deine Suche interpretiert", expanded=False):
                for q in query_terms:
                    if q["exact"]:
                        st.write(f'Exact Match: `{q["term"]}`')
                    else:
                        expanded_preview = sorted(expand_broad_term(q["term"]))[:20]
                        st.write(f'Broad Match: `{q["term"]}` → {", ".join(expanded_preview)}')

            results = app_search(DB_PATH, query_terms, max_results=max_results)
            if not results:
                st.info('Keine passenden Cocktails gefunden. Tipp: Probiere einen breiteren Begriff wie `kaffee` oder `margarita`, oder nutze Anführungszeichen für eine exakte Suche.')
            else:
                st.success(f"{len(results)} passende Rezepte gefunden")
                render_grouped_results(results)

with tab_add:
    st.header("Eigenen Cocktail hinzufügen")
    st.write("Trage jede Zutat in einer eigenen Zeile ein. Format: `Zutat=ml`. Beispiel: `Gin=50`.")

    with st.form("add_cocktail_form"):
        name = st.text_input("Name des Cocktails", placeholder="Mein Gin Sour")
        col1, col2, col3 = st.columns(3)
        with col1:
            category = st.text_input("Kategorie", placeholder="Sour/Fizz")
        with col2:
            glass = st.selectbox(
                "Glas",
                ["", "Rocks", "Wine Glass", "Highball", "Champagne Flute", "Chilled Martini/Coupe", "Shooter"],
            )
        with col3:
            ice = st.selectbox(
                "Ice",
                ["", "crushed ice", "ice cubes", "no ice"],
                format_func=lambda x: {
                    "": "Bitte auswählen",
                    "crushed ice": "❄️🧊 Crushed Ice",
                    "ice cubes": "🧊 Ice Cubes",
                    "no ice": "🚫🧊 No Ice",
                }.get(x, x),
            )

        source = st.text_input("Quelle", placeholder="z. B. Hausrezept, IBA, The 66")
        source_url = st.text_input("Quell-URL optional", placeholder="https://...")

        ingredients_text = st.text_area(
            "Zutaten",
            placeholder="Gin=50\nLemon juice=25\nSugar syrup=20",
            height=140,
        )
        instructions = st.text_area("Zubereitung", placeholder="Shaken und in ein gekühltes Glas abseihen.")
        submitted = st.form_submit_button("Cocktail speichern", type="primary")

    if submitted:
        lines = [line.strip() for line in ingredients_text.splitlines() if line.strip()]
        if not name or not lines:
            st.error("Bitte Name und mindestens eine Zutat eintragen.")
        else:
            try:
                from cocktail_db_builder import add_manual_cocktail
                add_manual_cocktail(
                    DB_PATH,
                    name=name,
                    ingredients=lines,
                    category=category or None,
                    glass=glass or None,
                    ice=ice or None,
                    instructions=instructions or None,
                )
                st.success(f"Gespeichert: {name}")
            except Exception as exc:
                st.error(f"Konnte nicht speichern: {exc}")

with tab_import:
    st.header("Cocktails per CSV importieren")
    st.write("Die Datenbank wird ausschließlich über CSV gepflegt. Pflichtspalten sind `name`, `ingredient`, `amount_ml`. Empfohlene Zusatzspalten: `glass`, `ice`, `category`, `instructions`, `source`, `source_url`, `note`.")
    st.info("Für die saubere Ice-Anzeige nutze in der Spalte `ice` nur: `crushed ice`, `ice cubes` oder `no ice`.")

    col_a, col_b = st.columns(2)
    with col_a:
        uploaded = st.file_uploader("CSV-Datei auswählen", type=["csv"])
    with col_b:
        template_path = Path("cocktail_template.csv")
        export_template_csv(template_path)
        st.download_button(
            "CSV-Vorlage herunterladen",
            data=template_path.read_bytes(),
            file_name="cocktail_template.csv",
            mime="text/csv",
            use_container_width=True,
        )

    replace_existing = st.checkbox("Vorhandene Cocktails mit gleichem Namen ersetzen", value=True)

    if uploaded and st.button("CSV importieren", type="primary"):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp.write(uploaded.getbuffer())
                tmp_path = tmp.name
            imported_count = import_csv(DB_PATH, tmp_path, replace_existing=replace_existing)
            st.success(f"Import abgeschlossen: {imported_count} Cocktails verarbeitet. Jetzt sind {count_cocktails(DB_PATH)} Rezepte gespeichert.")
        except Exception as exc:
            st.error(f"Import fehlgeschlagen: {exc}")

with tab_browse:
    st.header("Alle Cocktails ansehen")
    rows = get_all_cocktails()
    if not rows:
        st.info("Noch keine Cocktails vorhanden. Lade zuerst eine CSV-Datei hoch.")
    else:
        sources = ["Alle Quellen"] + get_sources(DB_PATH)
        col_filter_1, col_filter_2 = st.columns(2)
        with col_filter_1:
            selected_source = st.selectbox("Nach Quelle filtern", sources)
        with col_filter_2:
            search_name = st.text_input("In Namen/Zutaten filtern", placeholder="z. B. gin oder margarita")

        filtered = rows
        if selected_source != "Alle Quellen":
            filtered = [r for r in filtered if (r[2] or "Unbekannte Quelle").lower() == selected_source.lower()]
        if search_name:
            q = search_name.lower()
            filtered = [r for r in filtered if q in str(r).lower()]

        st.write(f"{len(filtered)} von {len(rows)} Rezepten")

        for _, name, source, category, glass, ice, ingredients in filtered[:500]:
            glass_icon, _ = get_glass_icon(glass)
            ice_icon, ice_label = get_ice_icon(ice)
            source_label = source or "Unbekannte Quelle"
            with st.expander(f"{glass_icon} {name} · 📚 {source_label} · {ice_icon} {ice_label}"):
                st.markdown(f"### 📚 Quelle: {source_label}")
                st.write(f"**Kategorie:** {category or '-'}")
                st.write(f"**Glas:** {glass or '-'}")
                st.write(f"**Ice:** {ice_label}")
                st.write(f"**Zutaten:** {ingredients or '-'}")


with tab_sources:
    st.header("Quellen verwalten")
    st.write("Hier kannst du Quellen filtern/prüfen und eine Quelle gesammelt umbenennen. Das ändert alle Rezepte mit dieser Quelle.")

    sources = get_sources(DB_PATH)
    if not sources:
        st.info("Noch keine Quellen vorhanden. Lade zuerst eine CSV hoch.")
    else:
        source_counts = {}
        for row in get_all_cocktails():
            source_name = row[2] or "Unbekannte Quelle"
            source_counts[source_name] = source_counts.get(source_name, 0) + 1

        st.markdown("**Vorhandene Quellen**")
        for source_name in sources:
            st.write(f"📚 **{source_name}** – {source_counts.get(source_name, 0)} Rezepte")

        st.divider()
        old_source = st.selectbox("Quelle auswählen", sources, key="rename_old_source")
        new_source = st.text_input("Neuer Quellenname", placeholder="z. B. Hausrezept")
        if st.button("Quelle umbenennen", type="primary"):
            if not new_source.strip():
                st.error("Bitte neuen Quellenname eingeben.")
            else:
                try:
                    changed = rename_source(DB_PATH, old_source, new_source)
                    st.success(f"Quelle wurde umbenannt. Geänderte Rezepte: {changed}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Umbenennen fehlgeschlagen: {exc}")
