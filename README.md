# Capeet Gig Radar Österreich

Inoffizieller Filter und Neueinträge-Feed für die Capeet-Gigliste. GitHub Actions ruft die Quelle täglich ab, normalisiert die alte `<br>`-basierte HTML-Struktur, historisiert Änderungen und veröffentlicht Website sowie RSS vollständig statisch über GitHub Pages. Es gibt keinen Server, keine Datenbank, keine Secrets und keine kostenpflichtige API.

- Website: <https://michaelnpunkt.github.io/capeet-gig-radar/>
- Repository: <https://github.com/michaelnpunkt/capeet-gig-radar>
- Gesamtfeed: <https://michaelnpunkt.github.io/capeet-gig-radar/feed.xml>
- Wien-Feed: <https://michaelnpunkt.github.io/capeet-gig-radar/feeds/neu-wien.xml>

## Architektur

`src/fetch.py` führt bedingte HTTP-Abrufe aus. `src/parser.py` zerlegt tolerantes HTML an `<br>`-Tags. Orts- und Genre-Enrichment folgen in `src/locations.py` und `src/genres.py`; `src/history.py` hält stabile Identitäten und Revisionen. `src/site.py` und `src/feeds.py` erzeugen ausschließlich Dateien in `docs/`. Persistenter Zustand liegt als versioniertes JSON in `data/`.

## Datenquelle und Betrieb

- Quelle: <https://www.capeet.com/gigs_list.html>
- Ausgabe: `docs/` für GitHub Pages; lokal muss nichts installiert oder gehostet werden.
- Aktualisierung: täglich um 04:17 UTC, manuell oder bei relevanten Änderungen auf `main`.
- HTTP: transparenter User-Agent sowie bedingte Requests mit ETag und Last-Modified aus `data/source-state.json`.
- Sicherheit: 0 Events, weniger als 20 Events oder ein Rückgang über 40 Prozent brechen den Lauf ab.

Der Cron-Zeitpunkt entspricht im Winter 05:17 Uhr und im Sommer 06:17 Uhr in `Europe/Vienna`.

## Lokales Setup (optional)

Voraussetzung ist Python 3.12.

```zsh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
MINIMUM_EVENTS=20 python -m src.update --input tests/fixtures/events.html
```

Ohne `--input` wird die Live-Quelle abgerufen. `--dry-run` schreibt nichts. Für den normalen Betrieb ist ausschließlich der GitHub-Workflow nötig; er kann im Actions-Tab über **Run workflow** manuell gestartet werden.

## JSON-Schema

Jeder Eintrag in `data/events.json` enthält `id`, `event_date`, `artists`, `title`, `venue`, `city`, `state`, `postal_code`, `status`, `links`, `source_text`, `first_seen_at`, `last_seen_at`, `changed_at`, `revision`, `baseline`, `active` und `genre`. Künstler bestehen aus `name`, optionalem `country` und optionalem `link`. `genre` enthält `family`, höchstens drei `subgenres` und `source`.

## Persistente Dateien

- `data/events.json`: aktueller und 120 Tage zurückreichender Eventbestand
- `data/revisions.json`: Änderungen für die Neuigkeiten-Feeds
- `data/source-state.json`: ETag und Last-Modified, erst nach erfolgreicher Veröffentlichung geschrieben
- `data/genre-overrides.json` und `data/genre-cache.json`: manuelle und gecachte Genrezuordnung
- `data/location-overrides.json`: manuelle Orts- und Bundeslandzuordnung

Overrides verwenden normalisierte Künstler- beziehungsweise Ortsnamen als Schlüssel. Genrewerte können eine Familie als String oder `{ "family": "Metal", "subgenres": ["Doom Metal"] }` sein. Ortswerte können ein Bundesland als String oder ein Objekt mit `venue`, `city`, `postal_code` und `state` sein. Overrides haben Vorrang; unklare Orte bleiben bewusst `Unbekannt`.

MusicBrainz benötigt keinen API-Key. Der Workflow fragt höchstens 25 neue Künstler pro Lauf mit mindestens einer Sekunde Abstand ab, akzeptiert nur sehr sichere Treffer und speichert Resultate dauerhaft in `data/genre-cache.json`.

## Feeds und Oberfläche

`docs/feed.xml` enthält höchstens 100 neue oder geänderte Einträge der letzten 90 Tage. Zusätzlich entstehen neun Bundesland-Feeds unter `docs/feeds/neu-{bundesland}.xml`. Ausgangsbestand wird nicht als neu gemeldet. Die Oberfläche unterstützt Bundesland- und Genre-Mehrfachauswahl, Volltextsuche, Statusfilter, vier Sortierungen, URL-Parameter und lokale Einstellungen.

## Grenzen und Kosten

Capeet stellt weder Eintragungszeitpunkte noch stabile IDs bereit. Matching und Genres sind deshalb konservativ; `Unbekannt` und `Unklassifiziert` sind absichtliche Diagnosewerte. Entfernte zukünftige Events werden als nicht mehr gelistet, nicht automatisch als abgesagt markiert. Die Originalseite bleibt maßgeblich.

Ein öffentliches Repository, Standard-GitHub-Actions-Minuten und GitHub Pages sind für dieses Projekt im üblichen kostenlosen GitHub-Rahmen nutzbar. Es werden keine Werbung, Analytics, Cookies oder Tracking eingesetzt.

## Hinweis

Dieses Projekt ist nicht mit Capeet verbunden. Veranstaltungsdaten können unvollständig oder veraltet sein; maßgeblich sind die [Original-Gigliste](https://www.capeet.com/gigs_list.html) und die verlinkten Veranstalter. Der eigene Code steht unter der MIT-Lizenz. Die Lizenz beansprucht keinerlei Rechte an Capeet-Daten, Marken oder fremden Website-Inhalten.