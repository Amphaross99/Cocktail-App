# Cocktail Finder – CSV-only Version v6

Diese Version enthält kein Scraping mehr. Die Datenbank wird ausschließlich über CSV-Dateien oder manuelle Eingabe gepflegt.

## Neu in v6

- Mehrere Rezepte pro Cocktail sind möglich.
- Mehrere Rezepte werden in der Suche nebeneinander angezeigt.
- Die Quelle wird deutlich sichtbar auf jeder Rezeptkarte angezeigt.
- In der Datenbankansicht kann nach Quelle gefiltert werden.
- Quellen können in der App gesammelt umbenannt werden.
- `ice` ist ein sauberes Datenfeld: `crushed ice`, `ice cubes`, `no ice`.

## Start lokal

```cmd
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## CSV-Import

Pflichtspalten:

- `name`
- `ingredient`
- `amount_ml`

Empfohlene Spalten:

- `source`
- `source_url`
- `category`
- `glass`
- `ice`
- `instructions`
- `note`

## Mehrere Rezepte pro Cocktail

Mehrere Rezepte werden unterschieden über:

- `name`
- `source`
- `source_url`

Beispiel: Es kann drei Zeilenblöcke mit `Espresso Martini` geben, solange `source` unterschiedlich ist, z. B. `Hausrezept`, `IBA`, `The 66`.

## Erlaubte Werte für `glass`

- `Rocks`
- `Wine Glass`
- `Highball`
- `Champagne Flute`
- `Chilled Martini/Coupe`
- `Shooter`

## Erlaubte Werte für `ice`

- `crushed ice`
- `ice cubes`
- `no ice`

## Suche

- `kaffee` = Broad Match, findet z. B. Coffee, Espresso, Kahlua.
- `"espresso"` = Exact Match, findet nur die exakt gepflegte Zutat Espresso.


## Neu in v7

Die Suche durchsucht jetzt nicht nur Zutaten, sondern auch Cocktailnamen.

Beispiele:

- `kaffee` findet Rezepte mit Coffee/Espresso/Kahlua.
- `margarita` findet auch Frozen Fruit Margarita.
- `"Espresso Martini"` sucht exakt nach diesem Cocktailnamen.
- `"espresso"` sucht exakt nach der gepflegten Zutat Espresso.
