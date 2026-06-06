# fussball.de → WordPress Meta Box Sync

Tägliche, vollautomatische Synchronisation von fussball.de-Daten für alle Mannschaften des **FC Königsfeld** in WordPress Meta Box Felder – orchestriert durch einen n8n Workflow.

**Synchronisiert werden:** Ergebnisse · Torschützen · Nächste Spiele · Ligatabelle

---

## Wie es funktioniert

```
n8n (Hetzner) – täglich 03:00 Uhr
  └── Execute Command → python -m src.main
        ├── Liest alle Teams aus WordPress (REST API)
        ├── Holt pro Team von fussball.de:
        │     • Letzte Spiele + Torschützen
        │     • Nächste Spiele
        │     • Ligatabelle
        └── Schreibt Daten in WordPress Meta Box Felder (REST API)
```

**fussball.de obfuskiert Spielstände** mit einer Custom-Font. Das Mapping wird einmalig lokal extrahiert (→ `tools/extract_font_mapping.py`) und als Konstante im Code hinterlegt. Kein `fontTools` auf dem Server nötig.

---

## Setup

### 1. Einmalig: Font-Mapping lokal extrahieren

Auf deinem Mac/PC (nicht auf dem Server):

```bash
pip install httpx fonttools beautifulsoup4 lxml
python tools/extract_font_mapping.py
```

Die Ausgabe (~10 Zeilen) in `src/crawler.py` bei `FONT_MAPPING = { ... }` eintragen.

### 2. Auf dem Hetzner-Server installieren

```bash
git clone https://github.com/tobiashaas/fussball.de-2-wordpress.git /opt/fussball-sync
cd /opt/fussball-sync

python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env  # Zugangsdaten eintragen
```

### 3. `.env` befüllen

```env
CLUB_ID=00ES8GN9DO000062VV0AG08LVUPGND5I
WP_URL=https://fc-koenigsfeld.de
WP_USER=admin
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
```

Das WordPress **Application Password** unter *WP-Admin → Benutzer → Profil → Anwendungspasswörter* erstellen.

### 4. WordPress einrichten

1. **Meta Box** Plugin aktivieren (kostenlos)
2. **MB REST API** Addon aktivieren (kostenpflichtig oder via MB AIO)
3. `MB_FieldGroups/fussball-de-sync.json` in Meta Box importieren → neue readonly Felder erscheinen bei jedem Team-Post
4. `MB_FieldGroups/teams.json` importieren (fügt `fussball_de_team_id` Feld hinzu)
5. Bei jedem Team-Post die **fussball.de Team-ID** eintragen (letztes Segment der Team-URL auf fussball.de)

### 5. Test-Lauf

```bash
cd /opt/fussball-sync
venv/bin/python -m src.main --dry-run   # Kein Schreiben nach WordPress
venv/bin/python -m src.main             # Echter Lauf
```

### 6. n8n Workflow aktivieren

Workflow: https://workflow.tobiashaas.dev/workflow/GRFypptop5qxdU5r

- Läuft täglich um **03:00 Uhr**
- Führt `cd /opt/fussball-sync && venv/bin/python -m src.main 2>&1` aus
- Sendet bei Fehler eine E-Mail

---

## Dateien

```
src/
  crawler.py        # fussball.de Scraper (HTML-Parsing + Font-Deobfuskierung)
  wp_sync.py        # WordPress REST API Client
  main.py           # CLI Entry Point (Exit 0 = OK, Exit 1 = Fehler)
  config.py         # Konfiguration via .env

tools/
  extract_font_mapping.py   # Einmaliges Hilfsskript – lokal ausführen

MB_FieldGroups/
  fussball-de-sync.json     # Neue Meta Box Fields (Sync-Daten, readonly)
  teams.json                # Erweitert um fussball_de_team_id Feld
```

## Meta Box Felder (neu, automatisch befüllt)

Alle neuen Felder sind **readonly** und werden täglich überschrieben.

| Feld | Typ | Inhalt |
|---|---|---|
| `fd_letzte_spiele` | Group (cloneable) | Letzte 10 Spiele mit Ergebnis |
| `fd_letzte_spiele.fd_torschuetzen` | Group (cloneable) | Torschützen pro Spiel |
| `fd_naechste_spiele` | Group (cloneable) | Nächste 5 Spiele |
| `fd_tabelle` | Group (cloneable) | Komplette Ligatabelle |
| `fd_zuletzt_aktualisiert` | Datetime | Timestamp letzter Sync |
| `fussball_de_team_id` | Text | **Manuell** setzen (einmalig) |

---

## Font-Mapping aktualisieren

Falls fussball.de das Font-Mapping ändert (erkennbar an leeren Spielständen):

```bash
# Lokal, einmalig:
python tools/extract_font_mapping.py
# → Ausgabe in src/crawler.py bei FONT_MAPPING eintragen
```
