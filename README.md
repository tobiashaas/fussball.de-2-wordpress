# fussball.de → WordPress Meta Box Sync

Tägliche, vollautomatische Synchronisation von fussball.de-Daten für alle Mannschaften des **FC Königsfeld** in WordPress Meta Box Felder – orchestriert durch einen n8n Workflow.

**Synchronisiert werden:** Ergebnisse · Nächste Spiele · Ligatabelle

---

## Wie es funktioniert

```
n8n (täglich 03:00 Uhr)
  └── WordPress Teams laden (REST API)
        └── Nur Teams mit fussball_de_team_id
              └── Pro Team:
                    ├── fussball.de: Letzte Spiele (HTML) → parsen
                    ├── fussball.de: Nächste Spiele (HTML) → parsen
                    └── fussball.de: Tabelle (HTML) → parsen
                          └── WordPress Meta Box Felder aktualisieren (REST API)
```

**fussball.de obfuskiert Spielstände** mit einer Custom-Font. Das Mapping wird einmalig lokal extrahiert (`tools/extract_font_mapping.py`) und als Konstante im n8n **Font Mapping** Node hinterlegt. Kein Python auf dem Server nötig.

---

## n8n Workflow

**URL:** https://workflow.tobiashaas.dev/workflow/7wMDyaqf6II6y4Nw

Der Workflow läuft komplett in n8n – keine externen Scripts, kein Server. Alle fussball.de-Anfragen und die WordPress-Aktualisierung laufen über HTTP Request Nodes, das HTML-Parsing und die Font-Deobfuskierung über JavaScript Code Nodes.

---

## Setup

### 1. Einmalig: Font-Mapping lokal extrahieren

Auf deinem Mac/PC (nicht auf dem Server):

```bash
pip install httpx fonttools beautifulsoup4 lxml
python tools/extract_font_mapping.py
```

Die Ausgabe sieht so aus:

```javascript
const FONT_MAPPING = {
  "": "2",
  "": "3",
  // ...
};
```

### 2. Font-Mapping in n8n eintragen

1. Workflow öffnen: https://workflow.tobiashaas.dev/workflow/7wMDyaqf6II6y4Nw
2. Node **„Font Mapping"** öffnen
3. `FONT_MAPPING = { ... }` mit den Werten aus Schritt 1 befüllen
4. Speichern

### 3. WordPress einrichten

1. **Meta Box** Plugin aktivieren (kostenlos)
2. **MB REST API** Addon aktivieren (kostenpflichtig oder via MB AIO)
3. `MB_FieldGroups/fussball-de-sync.json` in Meta Box importieren → neue readonly Felder erscheinen bei jedem Team-Post
4. `MB_FieldGroups/teams.json` importieren (fügt `fussball_de_team_id` Feld hinzu)
5. Bei jedem Team-Post die **fussball.de Team-ID** eintragen

Die Team-ID ist das letzte Segment der Team-URL auf fussball.de:
`https://www.fussball.de/mannschaft/.../-/saison/.../team-id/`**`00ES8GN9DO000062VV0AG08LVUPGND5I-G`**

### 4. Workflow aktivieren und testen

Im n8n Workflow:
- **Manuell testen:** „Test Workflow" klicken → Execution Log prüfen
- **Aktivieren:** Toggle oben rechts auf „Active" setzen

---

## Dateien

```
tools/
  extract_font_mapping.py   # Einmaliges Hilfsskript – lokal ausführen

MB_FieldGroups/
  fussball-de-sync.json     # Meta Box Field Group (Sync-Daten, readonly)
  teams.json                # Meta Box Field Group (erweitert um fussball_de_team_id)
```

---

## Meta Box Felder (automatisch befüllt)

Alle Felder sind **readonly** und werden täglich überschrieben.

| Feld | Typ | Inhalt |
|---|---|---|
| `fd_letzte_spiele` | Group (cloneable, max 10) | Letzte Spiele mit Ergebnis |
| `fd_letzte_spiele.fd_torschuetzen` | Group (cloneable) | Torschützen pro Spiel |
| `fd_naechste_spiele` | Group (cloneable, max 5) | Nächste 5 Spiele |
| `fd_tabelle` | Group (cloneable, max 25) | Komplette Ligatabelle |
| `fd_zuletzt_aktualisiert` | Datetime | Timestamp letzter Sync |
| `fussball_de_team_id` | Text | **Manuell** setzen (einmalig pro Team) |

---

## Font-Mapping aktualisieren

Falls fussball.de das Font-Mapping ändert (erkennbar an leeren oder falschen Spielständen):

```bash
# Lokal, einmalig:
python tools/extract_font_mapping.py
# → Ausgabe in den "Font Mapping" Node im n8n Workflow eintragen
```
