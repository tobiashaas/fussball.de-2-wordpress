"""
Crawlt fussball.de AJAX-Endpoints für Spiele, Tabellen und Torschützen.
Adaptiert von github.com/Zetabytes/fussball_de_api (MIT/Unlicense).
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup, NavigableString, Tag

from .config import FUSSBALL_DE_BASE_URL, CACHE_TTL

# ---------------------------------------------------------------------------
# Font-Mapping (einmalig mit tools/extract_font_mapping.py extrahieren)
#
# Aufruf (lokal, einmalig):
#   pip install httpx fonttools beautifulsoup4 lxml
#   python tools/extract_font_mapping.py
#
# Die Ausgabe hier eintragen. Das Mapping ändert sich selten;
# bei leeren Spielständen einfach erneut extrahieren.
# ---------------------------------------------------------------------------
FONT_MAPPING: Dict[str, str] = {
    # Beispiel-Einträge – mit tatsächlicher Ausgabe des Extraction-Scripts ersetzen:
    # "": "2",
    # "": "3",
    # ... (10-12 Einträge für Ziffern 0-9 und ":")
}

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Datenmodelle
# ---------------------------------------------------------------------------

@dataclass
class MatchEvent:
    time: str
    type: str           # goal | yellow-card | red-card | substitution | unknown
    team: str           # home | away
    description: Optional[str] = None
    score: Optional[str] = None


@dataclass
class Game:
    id: str
    datetime_utc: Optional[datetime]
    competition: Optional[str]
    home_team: str
    away_team: str
    home_score: Optional[str] = None
    away_score: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    match_events: List[MatchEvent] = field(default_factory=list)


@dataclass
class TableEntry:
    place: int
    team: str
    games: int
    won: int
    draw: int
    lost: int
    goal: str
    goal_difference: int
    points: int


@dataclass
class Team:
    id: str
    name: str


# ---------------------------------------------------------------------------
# HTTP + Cache
# ---------------------------------------------------------------------------

_http_cache: Dict[str, dict] = {}
_http_client = httpx.Client(
    timeout=30,
    headers={"User-Agent": "Mozilla/5.0 (compatible; FCKoenigsfeld-Sync/1.0)"},
    follow_redirects=True,
)


def _fetch(url: str) -> Optional[httpx.Response]:
    entry = _http_cache.get(url)
    if entry and entry["expires"] > time.time():
        return entry["response"]
    try:
        resp = _http_client.get(url)
        resp.raise_for_status()
        _http_cache[url] = {"response": resp, "expires": time.time() + CACHE_TTL}
        return resp
    except httpx.HTTPError as exc:
        logger.warning("HTTP error for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Font-Deobfuskierung (nutzt hardcodiertes FONT_MAPPING oben)
# ---------------------------------------------------------------------------

def _deobfuscate(parent_tag) -> str:
    """Dekodiert alle obfuskierten <span data-obfuscation> Elemente via FONT_MAPPING."""
    if not parent_tag:
        return ""

    if not FONT_MAPPING:
        logger.warning(
            "FONT_MAPPING ist leer! tools/extract_font_mapping.py einmalig "
            "ausführen und Ergebnis in src/crawler.py eintragen."
        )

    parts: List[str] = []
    stack = list(parent_tag.children) if hasattr(parent_tag, "children") else []

    while stack:
        node = stack.pop(0)
        if isinstance(node, Tag):
            if node.name == "span" and node.has_attr("data-obfuscation"):
                decoded = "".join(
                    FONT_MAPPING.get(c, "") for c in (node.get_text() or "")
                )
                parts.append(decoded)
            else:
                stack[0:0] = list(node.children)
        elif isinstance(node, NavigableString):
            txt = str(node).strip()
            if txt and not all("" <= c <= "" for c in txt):
                parts.append(txt)

    return "".join(parts).strip()


# ---------------------------------------------------------------------------
# Spieler-Name aus Profil
# ---------------------------------------------------------------------------

def _player_name(profile_url: str) -> Optional[str]:
    resp = _fetch(profile_url)
    if not resp:
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    tag = soup.find("p", class_="profile-name")
    return tag.get_text(strip=True) if tag else None


# ---------------------------------------------------------------------------
# Match-Verlauf (Torschützen, Karten, ...)
# ---------------------------------------------------------------------------

def _match_course(game_id: str) -> List[MatchEvent]:
    url = f"{FUSSBALL_DE_BASE_URL}/ajax.match.course/-/mode/PAGE/spiel/{game_id}"
    resp = _fetch(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events: List[MatchEvent] = []

    for row in soup.select("#match_course_body .row-event"):
        side = "home" if "event-left" in row.get("class", []) else "away"
        time_tag = row.select_one(".column-time .valign-inner")
        time_text = time_tag.get_text(strip=True) if time_tag else ""

        ev_type = "unknown"
        score = None
        desc = None

        if row.select_one(".column-event"):
            score_text = _deobfuscate(row.select_one(".column-event"))
            if ":" in score_text:
                ev_type = "goal"
                score = score_text

        if row.select_one(".icon-card.yellow-card"):
            ev_type = "yellow-card"
            desc = "Gelbe Karte"
        elif row.select_one(".icon-card.red-card"):
            ev_type = "red-card"
            desc = "Rote Karte"
        elif row.select_one(".icon-substitute"):
            ev_type = "substitution"
            links = row.select(".column-player .substitute a[href*='spielerprofil']")
            names = [_player_name(a["href"]) for a in links]
            names = [n for n in names if n]
            desc = f"{names[0]} für {names[1]}" if len(names) == 2 else " / ".join(names)

        if not desc:
            txt_tag = row.select_one(".column-player")
            if txt_tag:
                link = txt_tag.find("a", href=lambda h: h and "spielerprofil" in h)
                desc = _player_name(link["href"]) if link else _deobfuscate(txt_tag)

        events.append(MatchEvent(time=time_text, type=ev_type, team=side, description=desc, score=score))

    return events


# ---------------------------------------------------------------------------
# Spiele parsen (generisch für Heim/Auswärts-Listen)
# ---------------------------------------------------------------------------

def _parse_games(html: str, fetch_events: bool = True) -> List[Game]:
    soup = BeautifulSoup(html, "lxml")
    games: List[Game] = []
    current_meta: dict = {}

    for row in soup.find_all("tr"):
        if "visible-small" in row.get("class", []):
            cell = row.find("td")
            if not cell:
                continue
            text = cell.get_text(strip=True)
            try:
                date_part, rest = text.split(" - ", 1)
                date_str = date_part.split(", ")[1]
                parts = rest.split(" | ")
                time_str = parts[0].replace(" Uhr", "").strip()
                dt_naive = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
                dt_local = dt_naive.replace(tzinfo=ZoneInfo("Europe/Berlin"))
                dt_utc = dt_local.astimezone(ZoneInfo("UTC"))
                competition = parts[-1].strip() if len(parts) >= 2 else None
                current_meta = {"datetime_utc": dt_utc, "competition": competition}
            except (ValueError, IndexError):
                current_meta = {}
            continue

        score_cell = row.find("td", class_="column-score")
        if not score_cell or not current_meta:
            continue

        home_cell = row.find("td", class_="column-club-left") or (
            row.find_all("td", class_="column-club")[0:1] or [None]
        )[0]
        away_cell = row.find("td", class_="column-club-right") or (
            row.find_all("td", class_="column-club")[1:2] or [None]
        )[0]

        if not home_cell or not away_cell:
            continue

        try:
            home_name = home_cell.find(class_="club-name").get_text(strip=True)
            away_name = away_cell.find(class_="club-name").get_text(strip=True)
        except AttributeError:
            continue

        game_id: Optional[str] = None
        link_tag = score_cell.find("a")
        if link_tag and link_tag.get("href"):
            game_id = link_tag["href"].strip("/").split("/")[-1]

        home_score = None
        away_score = None
        decoded = _deobfuscate(score_cell)
        if ":" in decoded:
            h, a = decoded.split(":", 1)
            home_score = h.strip() or None
            away_score = a.strip() or None

        events: List[MatchEvent] = []
        if fetch_events and game_id and home_score is not None:
            try:
                events = _match_course(game_id)
            except Exception as exc:
                logger.warning("match_course error for %s: %s", game_id, exc)

        fallback_id = game_id or f"{current_meta['datetime_utc']}_{home_name}_{away_name}"
        games.append(Game(
            id=fallback_id,
            **current_meta,
            home_team=home_name,
            away_team=away_name,
            home_score=home_score,
            away_score=away_score,
            match_events=events,
        ))

    return games


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def get_club_teams(club_id: str) -> List[Team]:
    url = f"{FUSSBALL_DE_BASE_URL}/ajax.club.teams/-/action/search/id/{club_id}"
    resp = _fetch(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    teams: List[Team] = []
    for item in soup.find_all("div", class_="item"):
        link = item.find("h4", recursive=True)
        link = link.find("a") if link else None
        if not link or not link.get("href"):
            continue
        team_id = link["href"].strip("/").split("/")[-1]
        teams.append(Team(id=team_id, name=link.get_text(strip=True)))
    return teams


def get_team_prev_games(team_id: str, fetch_events: bool = True) -> List[Game]:
    url = f"{FUSSBALL_DE_BASE_URL}/ajax.team.prev.games/-/mode/PAGE/team-id/{team_id}"
    resp = _fetch(url)
    return _parse_games(resp.text, fetch_events=fetch_events) if resp else []


def get_team_next_games(team_id: str) -> List[Game]:
    url = f"{FUSSBALL_DE_BASE_URL}/ajax.team.next.games/-/mode/PAGE/team-id/{team_id}"
    resp = _fetch(url)
    return _parse_games(resp.text, fetch_events=False) if resp else []


def get_team_table(team_id: str) -> List[TableEntry]:
    url = f"{FUSSBALL_DE_BASE_URL}/ajax.team.table/-/team-id/{team_id}"
    resp = _fetch(url)
    if not resp or not resp.text.strip():
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    entries: List[TableEntry] = []

    for row in soup.find_all("tr"):
        if "thead" in row.get("class", []):
            continue
        cols = row.find_all("td")
        if len(cols) < 10:
            continue
        try:
            name_tag = cols[2].find(class_="club-name")
            entries.append(TableEntry(
                place=int(cols[1].get_text(strip=True).replace(".", "")),
                team=name_tag.get_text(strip=True) if name_tag else cols[2].get_text(strip=True),
                games=int(cols[3].get_text(strip=True)),
                won=int(cols[4].get_text(strip=True)),
                draw=int(cols[5].get_text(strip=True)),
                lost=int(cols[6].get_text(strip=True)),
                goal=cols[7].get_text(strip=True),
                goal_difference=int(cols[8].get_text(strip=True)),
                points=int(cols[9].get_text(strip=True)),
            ))
        except (ValueError, AttributeError) as exc:
            logger.warning("Table row parse error: %s", exc)
    return entries
