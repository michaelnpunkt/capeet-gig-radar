# Mosh Pit Crew Gig Radar

Inoffizieller Filter und Neueinträge-Feed für die österreichische [Capeet-Gigliste](https://www.capeet.com/gigs_list.html). GitHub Actions ruft die Quelle bewusst nur einmal täglich ab, normalisiert die alte `<br>`-basierte HTML-Struktur, historisiert Änderungen und schreibt Website sowie RSS vollständig statisch nach `docs/`.

Der Betrieb benötigt keinen Server, keine Datenbank, kein lokales Hosting und keine kostenpflichtige API. Ein kostenloser Last.fm-API-Key wird ausschließlich als verschlüsseltes GitHub-Actions-Secret verwendet.

- Website: <https://michaelnpunkt.github.io/capeet-gig-radar/>
- Changelog: <https://michaelnpunkt.github.io/capeet-gig-radar/changes.html>
- Repository: <https://github.com/michaelnpunkt/capeet-gig-radar>
- Gesamtfeed: <https://michaelnpunkt.github.io/capeet-gig-radar/feed.xml>
- Wien-Feed: <https://michaelnpunkt.github.io/capeet-gig-radar/feeds/neu-wien.xml>

## Architektur

- `src/fetch.py` führt bedingte HTTP-Abrufe mit ETag und Last-Modified aus.
- `src/parser.py` zerlegt das tolerante, alte Capeet-HTML an `<br>`-Tags.
- `src/locations.py` ordnet österreichische Orte und Postleitzahlen Bundesländern zu.
- `src/genres.py` klassifiziert jeden Künstler über Last.fm-Tags und einen permanenten Cache.
- `src/history.py` hält stabile Eventidentitäten, Baseline, Revisionen und verschwundene Einträge nach.
- `src/site.py` und `src/feeds.py` erzeugen ausschließlich statische Dateien unter `docs/`.
- Persistenter Zustand liegt als versioniertes JSON unter `data/`.
- GitHub Pages veröffentlicht direkt den Ordner `docs/` aus dem Branch `main`.

## Datenquelle und Betrieb

- Quelle: <https://www.capeet.com/gigs_list.html>
- Ausgabe: `docs/` für GitHub Pages; lokal muss nichts installiert oder gehostet werden.
- Aktualisierung: genau einmal täglich um 04:17 UTC sowie optional manuell über `workflow_dispatch`.
- HTTP: transparenter User-Agent sowie bedingte Requests mit ETag und Last-Modified aus `data/source-state.json`.
- HTTP 304: Bei unveränderter Quelle bleibt die bestehende Website erhalten; ausstehende Last.fm-Klassifizierungen können trotzdem ergänzt werden.
- Sicherheit: 0 Events, weniger als 20 Events oder ein Rückgang über 40 Prozent brechen den Lauf ab.

Der Cron-Zeitpunkt entspricht im Winter 05:17 Uhr und im Sommer 06:17 Uhr in `Europe/Vienna`.

## Genre-Klassifizierung mit Last.fm

Capeet liefert nur Künstlernamen. Der Workflow fragt deshalb für bisher unbekannte Künstler die Community-Tags von Last.fm ab. Last.fm benötigt einen kostenlosen API-Key, aber weder OAuth noch einen Login im Workflow. Der Key wird ausschließlich als Repository-Secret `LASTFM_API_KEY` gespeichert und erscheint weder im Code noch in den generierten Dateien.

1. Auf <https://www.last.fm/api/account/create> einen kostenlosen API-Key erstellen.
2. Im Repository **Settings → Secrets and variables → Actions → New repository secret** öffnen.
3. Name `LASTFM_API_KEY` und den API-Key als Wert eintragen.
4. Unter **Actions → Update gig radar → Run workflow** den Lauf manuell starten.

Der Workflow verarbeitet pro Lauf höchstens 1.200 neue Künstler mit höchstens vier Anfragen pro Sekunde. Bei HTTP 304 läuft ausschließlich noch ausstehende Genre-Anreicherung weiter; sobald alle Künstler gecacht sind, entstehen keine unnötigen Änderungen. Jeder Act eines Line-ups wird separat und dauerhaft in `data/genre-cache.json` gespeichert. Für die Eventkarte bestimmt der zuerst gelistete Act die Genre-Familie. Spezifische Tags wie `deathcore`, `street punk` oder `post-hardcore` werden vor breiten Tags wie `metal`, `punk` oder `rock` ausgewertet.

Temporäre Last.fm-Fehler werden nicht dauerhaft gecacht. Bei gleichnamigen Künstlern kann `data/genre-overrides.json` eine falsche Zuordnung jederzeit korrigieren.

## JSON-Schema

Jeder Eintrag in `data/events.json` enthält `id`, `event_date`, `artists`, `title`, `venue`, `city`, `state`, `postal_code`, `status`, `links`, `source_text`, `first_seen_at`, `last_seen_at`, `changed_at`, `revision`, `baseline`, `active` und `genre`. Künstler bestehen aus `name`, optionalem `country` und optionalem `link`. `genre` enthält `family`, höchstens drei `subgenres` und `source`.

## Persistente Dateien

- `data/events.json`: aktueller und 120 Tage zurückreichender Eventbestand
- `data/revisions.json`: bis zu 730 Tage aufbewahrte Änderungen für Changelog und Neuigkeiten-Feeds
- `data/source-state.json`: ETag und Last-Modified, erst nach erfolgreicher Veröffentlichung geschrieben
- `data/genre-overrides.json` und `data/genre-cache.json`: manuelle und gecachte Genrezuordnung
- `data/location-overrides.json` und `data/location-cache.json`: manuelle und über OpenStreetMap gecachte Ortszuordnung

Overrides verwenden normalisierte Künstler- beziehungsweise Ortsnamen als Schlüssel. Genrewerte können eine Familie als String oder `{ "family": "Metal", "subgenres": ["Doom Metal"] }` sein. Ortswerte können ein Bundesland als String oder ein Objekt mit `venue`, `city`, `postal_code` und `state` sein. Genre-Overrides haben immer Vorrang vor Last.fm und dem Cache; unklare Orte bleiben bewusst `Unbekannt`. Temporäre Last.fm-Fehler werden nicht gecacht und beim nächsten Lauf erneut versucht.

## Feeds und Oberfläche

`docs/changes.html` zeigt die Änderungschronik mit Filtern für 7, 30 oder 90 Tage beziehungsweise die gesamte verfügbare Historie, Bundesland und Änderungstyp. Erfasst werden neue und geänderte Termine, Absagen, Verschiebungen, Wiederlistungen sowie zukünftige Events, die bei Capeet nicht mehr gelistet sind. Änderungen zeigen verständliche Vorher-/Nachher-Werte. Der beim ersten Import übernommene Ausgangsbestand wird nicht künstlich als neu gemeldet; spätere Änderungen an diesen Events erscheinen jedoch normal im Changelog.

Als signifikant gelten Änderungen an Konzertdatum, tatsächlichen Line-up-Namen, Titel, Venue, Ort, Postleitzahl, Status oder Listung. Rein kosmetische beziehungsweise technische Änderungen an Länderkennungen, Künstlerlinks, Bundesland-Enrichment oder Capeet-Rohtext erzeugen keine Revision. Groß-/Kleinschreibung, Akzente und reine Zeichensetzungsunterschiede bei Titel und Ort werden ebenfalls ignoriert.

Eine Absage gilt nur dann als Eventabsage, wenn Capeet die gesamte Terminzeile entsprechend markiert. Entfällt lediglich ein Act innerhalb eines weiterhin stattfindenden Line-ups, bleibt das Event aktiv und erscheint als normale Line-up-Änderung. Die Hauptseite und das Changelog zeigen entfernte Werte durchgestrichen und neue Werte direkt daneben; das gilt auch für signifikante Änderungen an Datum, Venue und Ort.

`docs/feed.xml` enthält höchstens 100 Chronikeinträge der letzten 90 Tage. Zusätzlich entstehen neun Bundesland-Feeds unter `docs/feeds/neu-{bundesland}.xml`. Jede Revision hat eine eigene stabile GUID und verlinkt direkt auf ihren Eintrag im Changelog. Dadurch zeigen Feedreader spätere Änderungen als neue Meldung und ersetzen nicht still den ursprünglichen Eintrag.

Die responsive Oberfläche bietet:

- Bundesland- und Genre-Mehrfachauswahl
- Volltextsuche über Künstler, Titel, Venue und Ort
- Monatsfilter und Zeiträume für die kommenden 7, 14, 30, 60 oder 90 Tage
- standardmäßig ausgeblendete vergangene Gigs
- optionale Anzeige abgesagter sowie neuer oder geänderter Events
- Sortierung nach Entdeckung, letzter Änderung und Konzertdatum
- umschaltbare Kachel- und kompakte Listenansicht mit gespeicherter Auswahl
- verständliche Hilfetexte zu Historie und Sortierungen
- teilbare URL-Parameter und ergänzende Speicherung im Browser
- direkte Links zur Capeet-Originalquelle sowie zum Gesamt- und zu den Bundesland-Feeds
- eigene responsive Changelog-Seite für Besucher, die nicht täglich nachsehen
- responsives, kontrastreiches Metalcore-Design ohne Tracking, Werbung oder Cookies

## Deployment

Der Workflow in `.github/workflows/update.yml` führt Tests und Update aus und committet tatsächliche Änderungen in `data/` und `docs/`. GitHub Pages veröffentlicht anschließend direkt `main:/docs`. Dadurch bleibt die Website auch bei einem HTTP-304-Abruf deploybar, ohne einen leeren Daten-Commit zu erzeugen.

## Feedback und Fehler

Technische Fehler können über das strukturierte GitHub-Formular **Fehler melden** eingereicht werden; Ideen und allgemeines Feedback über **Idee vorschlagen**. Beide Links stehen im Footer der Website und des Changelogs. Bei inhaltlich falschen Konzertdaten bleibt die originale Capeet-Gigliste maßgeblich. Bitte keine privaten Daten in öffentliche Issues schreiben.

## Grenzen und Kosten

Capeet stellt weder Eintragungszeitpunkte noch stabile IDs bereit. Matching und Genres sind deshalb konservativ; `Unbekannt` und `Unklassifiziert` sind absichtliche Diagnosewerte. Entfernte zukünftige Events werden als „nicht mehr gelistet“, nicht automatisch als abgesagt markiert. Die Originalseite bleibt maßgeblich.

Ein öffentliches Repository, Standard-GitHub-Actions-Minuten und GitHub Pages sind für dieses Projekt im üblichen kostenlosen GitHub-Rahmen nutzbar. Es werden keine Werbung, Analytics, Cookies oder Tracking eingesetzt.

## Hinweis

Dieses Projekt ist nicht mit Capeet verbunden. Veranstaltungsdaten können unvollständig oder veraltet sein; maßgeblich sind die [Original-Gigliste](https://www.capeet.com/gigs_list.html) und die verlinkten Veranstalter. Der eigene Code steht unter der MIT-Lizenz. Die Lizenz beansprucht keinerlei Rechte an Capeet-Daten, Marken oder fremden Website-Inhalten.