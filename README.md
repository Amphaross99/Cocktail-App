# Cocktail DB Builder mit Web-Oberfläche

Dieses Projekt erstellt eine SQLite-Datenbank mit Cocktails und zeigt sie über eine einfache lokale Web-App an.

## Installation

```powershell
py -m pip install -r requirements.txt
```

## Web-App starten

```powershell
py -m streamlit run app.py
```

Danach öffnet sich der Browser. Falls nicht, kopiere die angezeigte Local-URL in den Browser.

## Datenbank aufbauen

In der Web-App links auf **Datenbank automatisch aufbauen/aktualisieren** klicken.

Alternativ über die Konsole:

```powershell
py cocktail_db_builder.py build --db cocktails.sqlite
```

## Suche

In der Web-App den Tab **Suchen** öffnen und Zutaten kommagetrennt eingeben, z. B.:

```text
gin, lime, mint
```

## Manuell erweitern

In der Web-App den Tab **Cocktail hinzufügen** nutzen.

Zutatenformat:

```text
Gin=50
Lemon juice=25
Sugar syrup=20
```

## CSV-Import

Über den Tab **CSV importieren** kannst du eigene Listen hochladen.
