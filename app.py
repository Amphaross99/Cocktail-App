from __future__ import annotations

import sqlite3
from pathlib import Path
import tempfile

import streamlit as st

from cocktail_db_builder import (
    add_manual_cocktail,
    build,
    count_cocktails,
    import_csv,
    search,
)

DB_PATH = "cocktails.sqlite"

st.set_page_config(page_title="Cocktail Finder", page_icon="🍸", layout="wide")

st.title("🍸 Cocktail Finder")
st.caption("Suche Cocktails nach Zutaten, baue deine Datenbank auf und ergänze eigene Rezepte — alles mit ml-Angaben.")


def db_exists() -> bool:
    return Path(DB_PATH).exists()


def get_all_cocktails() -> list[tuple]:
    if not db_exists():
        return []
    con = sqlite3.connect(DB_PATH)
    return con.execute(
        """
        SELECT c.id, c.name, c.source, c.category, c.glass,
               GROUP_CONCAT(i.name || ' (' || COALESCE(CAST(i.amount_ml AS TEXT), '-') || ' ml)', ', ') AS ingredients
        FROM cocktails c
        LEFT JOIN ingredients i ON c.id = i.cocktail_id
        GROUP BY c.id
        ORDER BY c.name COLLATE NOCASE
        """
    ).fetchall()


def render_result(result: dict) -> None:
    with st.container(border=True):
        left, right = st.columns([3, 1])
        with left:
            st.subheader(result["name"])
            meta = []
            if result.get("glass"):
                meta.append(f"Glas: {result['glass']}")
            if result.get("category"):
                meta.append(f"Kategorie: {result['category']}")
            if result.get("source"):
                meta.append(f"Quelle: {result['source']}")
            if meta:
                st.caption(" · ".join(meta))
        with right:
            st.metric("Treffer", result.get("matched_ingredients", 0))
            st.caption(f"Score: {result.get('score', '-')}")

        st.markdown("**Zutaten**")
        for ing in result.get("ingredients", []):
            amount = ing.get("amount_ml")
            amount_text = f"{amount:g} ml" if isinstance(amount, (int, float)) else (ing.get("note") or "nach Bedarf")
            st.write(f"• {ing.get('name', '')}: **{amount_text}**")

        if result.get("instructions"):
            st.markdown("**Zubereitung**")
            st.write(result["instructions"])

        if result.get("source_url"):
            st.link_button("Quelle öffnen", result["source_url"])


with st.sidebar:
    st.header("Datenbank")
    if db_exists():
        try:
            st.success(f"{count_cocktails(DB_PATH)} Cocktails gespeichert")
        except Exception as exc:
            st.warning(f"Datenbank vorhanden, aber nicht lesbar: {exc}")
    else:
        st.warning("Noch keine Datenbank gefunden.")

    if st.button("Datenbank automatisch aufbauen/aktualisieren", use_container_width=True):
        with st.spinner("Sammle Cocktails. Das kann etwas dauern ..."):
            try:
                build(DB_PATH, limit=None, include_iba=True)
                st.success(f"Fertig. Jetzt sind {count_cocktails(DB_PATH)} Cocktails gespeichert.")
            except Exception as exc:
                st.error(f"Fehler beim Aufbau: {exc}")


tab_search, tab_add, tab_import, tab_browse = st.tabs(["🔍 Suchen", "➕ Cocktail hinzufügen", "📥 CSV importieren", "📚 Datenbank ansehen"])

with tab_search:
    st.header("Cocktail suchen")
    st.write("Gib 1–4 Zutaten ein. Am besten auf Englisch, z. B. `gin`, `lime`, `mint`, `rum`, `pineapple juice`.")
    query = st.text_input("Zutaten", placeholder="z. B. gin, lime, mint")
    max_results = st.slider("Maximale Ergebnisse", 3, 30, 10)

    if st.button("Cocktails suchen", type="primary"):
        if not db_exists():
            st.error("Bitte zuerst links die Datenbank aufbauen.")
        else:
            ingredients = [x.strip() for x in query.replace(";", ",").split(",") if x.strip()]
            if not ingredients:
                st.warning("Bitte mindestens eine Zutat eingeben.")
            else:
                results = search(DB_PATH, ingredients, max_results=max_results)
                if not results:
                    st.info("Keine passenden Cocktails gefunden. Probiere englische Zutatennamen oder weniger Zutaten.")
                else:
                    st.success(f"{len(results)} passende Cocktails gefunden")
                    for result in results:
                        render_result(result)

with tab_add:
    st.header("Eigenen Cocktail hinzufügen")
    st.write("Trage jede Zutat in einer eigenen Zeile ein. Format: `Zutat=ml`. Beispiel: `Gin=50`.")
    with st.form("add_cocktail_form"):
        name = st.text_input("Name des Cocktails", placeholder="Mein Gin Sour")
        col1, col2 = st.columns(2)
        with col1:
            category = st.text_input("Kategorie", placeholder="Sour/Fizz")
        with col2:
            glass = st.text_input("Glas", placeholder="Coupe")
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
                add_manual_cocktail(DB_PATH, name=name, ingredients=lines, category=category or None, glass=glass or None, instructions=instructions or None)
                st.success(f"Gespeichert: {name}")
            except Exception as exc:
                st.error(f"Konnte nicht speichern: {exc}")

with tab_import:
    st.header("Cocktails per CSV importieren")
    st.write("Du kannst deine Excel-/CSV-Liste hochladen. Spalten: `name`, `source`, `category`, `glass`, `instructions`, `ingredient`, `amount_ml`, `note`.")
    uploaded = st.file_uploader("CSV-Datei auswählen", type=["csv"])
    if uploaded and st.button("CSV importieren", type="primary"):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
                tmp.write(uploaded.getbuffer())
                tmp_path = tmp.name
            import_csv(DB_PATH, tmp_path, replace_existing=True)
            st.success(f"Import abgeschlossen. Jetzt sind {count_cocktails(DB_PATH)} Cocktails gespeichert.")
        except Exception as exc:
            st.error(f"Import fehlgeschlagen: {exc}")

with tab_browse:
    st.header("Alle Cocktails ansehen")
    rows = get_all_cocktails()
    if not rows:
        st.info("Noch keine Cocktails vorhanden. Baue zuerst links die Datenbank auf.")
    else:
        search_name = st.text_input("In Namen/Zutaten filtern", placeholder="z. B. gin oder margarita")
        filtered = rows
        if search_name:
            q = search_name.lower()
            filtered = [r for r in rows if q in str(r).lower()]
        st.write(f"{len(filtered)} von {len(rows)} Cocktails")
        for _, name, source, category, glass, ingredients in filtered[:200]:
            with st.expander(name):
                st.write(f"**Quelle:** {source or '-'}")
                st.write(f"**Kategorie:** {category or '-'}")
                st.write(f"**Glas:** {glass or '-'}")
                st.write(f"**Zutaten:** {ingredients or '-'}")
