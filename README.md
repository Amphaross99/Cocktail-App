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


## v8

Der Suchhinweis wurde kompakter und UI-freundlicher gestaltet.


## v10

- Eigene Glas-Symbole im luxuriöseren Outline-Stil
- Quelle in den Rezeptkarten dezenter als Sidefact
- Treffer/Score-Zeile in der Suche entfernt


## v11

Zusätzliche UI-Veredelungen:

- einheitlichere Kartenoptik
- elegantere Trennlinien und Abstände
- farbige Kategorien-Badges
- dezentere und edlere Darstellung von Quelle und Ice
- bessere Mobile-Optimierung durch kompaktere Abstände und 2-Spalten-Layout


## v12

Favoriten-Funktion ergänzt:

- Rezeptkarten können als Favorit gespeichert werden.
- Favoriten werden in der SQLite-Datenbank gespeichert.
- Neuer Tab `★ Favoriten`.
- In der Datenbankansicht kann auf `Nur Favoriten` gefiltert werden.


## v13

Bugfix:

- Glas-SVGs werden jetzt als echte Symbole gerendert.
- Die Rohanzeige von SVG/HTML in Rezeptkarten wurde behoben.


## v14

- Linke Sidebar entfernt.
- Datenbankstatus wird jetzt kompakt oben angezeigt.
- Datenbank leeren wurde in `Quellen verwalten` verschoben.


## v15

Bugfix:

- Glas-Symbole werden jetzt ohne SVG gerendert.
- Dadurch kann kein SVG-Code mehr als Text in der App erscheinen.


## v16

- Glas-Symbole wurden wieder auf Emojis zurückgestellt.
- Shooter nutzt jetzt 🔫.
- SVG/CSS-Icon-Experimente entfernt, damit kein Code mehr in der App angezeigt wird.


## v17

- Untertitel unter dem App-Titel entfernt.
- Fehler `count_favorites is not defined` behoben.
- Gelbe Warnbox für den Favoriten-Zähler entfernt.


## v18

Code bereinigt und verschlankt:

- alte SVG-/CSS-Icon-Versuche entfernt
- Glas-Symbole bleiben als einfache Emojis
- `glass_icon_html` ist jetzt ein kurzer Emoji-Wrapper
- überflüssige Reste und Kommentare entfernt
