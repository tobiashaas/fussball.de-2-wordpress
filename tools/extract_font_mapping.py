"""
Einmaliges Script zum Extrahieren des fussball.de Font-Mappings.

Aufruf:
    pip install httpx fonttools beautifulsoup4 lxml
    python tools/extract_font_mapping.py

Ausgabe: Ein Python-Dict (und JSON) das den Unicode-Codepoint → Ziffer mappt.
Das Ergebnis in FONT_MAPPING im n8n Workflow Code eintragen.
"""
import json
import sys
from io import BytesIO

import httpx
from bs4 import BeautifulSoup
from fontTools import ttLib

BASE = "https://www.fussball.de"

# Eine beliebige fussball.de Spieltagseite laden um einen font-name zu bekommen
# Ersetze die URL mit einer aktuellen Spieltagsseite deines Vereins
SAMPLE_URL = (
    f"{BASE}/ajax.team.prev.games/-/mode/PAGE"
    f"/team-id/00ES8GN9DO000062VV0AG08LVUPGND5I-G"
)

GLYPH_TO_DIGIT = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "hyphen": ":", "colon": ":",
}

headers = {"User-Agent": "Mozilla/5.0 (compatible; FontMapper/1.0)"}

print(f"Lade Seite: {SAMPLE_URL}")
resp = httpx.get(SAMPLE_URL, headers=headers, follow_redirects=True, timeout=15)
if resp.status_code != 200:
    print(f"FEHLER: HTTP {resp.status_code}")
    sys.exit(1)

soup = BeautifulSoup(resp.text, "lxml")
spans = soup.find_all("span", attrs={"data-obfuscation": True})

if not spans:
    print("Keine obfuskierten Spans gefunden – entweder keine Spiele oder URL falsch.")
    sys.exit(1)

# Alle eindeutigen Font-Namen sammeln
font_names = list({s["data-obfuscation"] for s in spans})
print(f"Gefundene Font-Namen: {font_names}")

full_mapping = {}

for font_name in font_names:
    font_url = f"{BASE}/export.fontface/-/format/woff/id/{font_name}/type/font"
    print(f"Lade Font: {font_url}")
    fr = httpx.get(font_url, headers=headers, follow_redirects=True, timeout=15)
    if fr.status_code != 200:
        print(f"  FEHLER: HTTP {fr.status_code}")
        continue

    font = ttLib.TTFont(BytesIO(fr.content))
    cmap = font.getBestCmap()
    if not cmap:
        print("  Keine cmap-Tabelle gefunden.")
        continue

    for codepoint, glyph_name in cmap.items():
        digit = GLYPH_TO_DIGIT.get(glyph_name)
        if digit:
            full_mapping[f"\\u{codepoint:04x}"] = digit
            print(f"  U+{codepoint:04X} ({glyph_name!r}) → {digit!r}")

if not full_mapping:
    print("Kein Mapping extrahiert. Prüfe ob die fussball.de Seite erreichbar ist.")
    sys.exit(1)

print("\n" + "="*60)
print("ERGEBNIS – in n8n Code Node als FONT_MAPPING eintragen:")
print("="*60)

# JavaScript-freundliches Format ausgeben
js_entries = [f'  "\\u{int(k[2:], 16):04x}": "{v}"' for k, v in sorted(full_mapping.items())]
print("const FONT_MAPPING = {")
print(",\n".join(js_entries))
print("};")

print("\nJSON:")
print(json.dumps({k: v for k, v in full_mapping.items()}, ensure_ascii=True, indent=2))
