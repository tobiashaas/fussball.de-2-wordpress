"""
Liest WordPress-Teams via REST API und schreibt fussball.de-Daten in Meta Box Felder.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .config import WP_URL, WP_USER, WP_APP_PASSWORD
from .crawler import Game, MatchEvent, TableEntry, Team

logger = logging.getLogger(__name__)

_WP_TEAMS_ENDPOINT = f"{WP_URL}/wp-json/wp/v2/teams"


def _client() -> httpx.Client:
    return httpx.Client(
        auth=(WP_USER, WP_APP_PASSWORD),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )


# ---------------------------------------------------------------------------
# WordPress-Teams lesen
# ---------------------------------------------------------------------------

def get_wp_teams() -> List[Dict[str, Any]]:
    """Gibt alle Teams aus dem WordPress-CPT zurück (paginiert)."""
    teams: List[Dict[str, Any]] = []
    page = 1
    with _client() as c:
        while True:
            resp = c.get(_WP_TEAMS_ENDPOINT, params={"per_page": 100, "page": page, "_fields": "id,title,meta"})
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            teams.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return teams


# ---------------------------------------------------------------------------
# Daten-Konverter (Python-Dataclass → Meta Box REST-Format)
# ---------------------------------------------------------------------------

def _game_to_meta(game: Game, is_past: bool) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "fd_spiel_datum": game.datetime_utc.strftime("%Y-%m-%d %H:%M:%S") if game.datetime_utc else "",
        "fd_spiel_liga": game.competition or "",
        "fd_heim": game.home_team,
        "fd_auswaerts": game.away_team,
    }
    if is_past:
        heim = game.home_score or ""
        ausw = game.away_score or ""
        entry["fd_ergebnis"] = f"{heim}:{ausw}" if (heim or ausw) else ""
        # Nur Tor-Events als Torschützen übernehmen
        entry["fd_torschuetzen"] = [
            {
                "fd_tor_minute": ev.time,
                "fd_tor_spieler": ev.description or "",
                "fd_tor_team": ev.team,
            }
            for ev in game.match_events
            if ev.type == "goal"
        ]
    return entry


def _table_to_meta(entries: List[TableEntry]) -> List[Dict[str, Any]]:
    return [
        {
            "fd_platz": e.place,
            "fd_team": e.team,
            "fd_spiele": e.games,
            "fd_siege": e.won,
            "fd_unentschieden": e.draw,
            "fd_niederlagen": e.lost,
            "fd_tore": e.goal,
            "fd_punkte": e.points,
        }
        for e in entries
    ]


# ---------------------------------------------------------------------------
# WordPress-Post aktualisieren
# ---------------------------------------------------------------------------

def update_team_meta(wp_team_id: int, meta: Dict[str, Any]) -> bool:
    url = f"{_WP_TEAMS_ENDPOINT}/{wp_team_id}"
    with _client() as c:
        resp = c.post(url, json={"meta": meta})
        if resp.is_success:
            return True
        logger.error("WP update failed for team %s: %s %s", wp_team_id, resp.status_code, resp.text[:200])
        return False


# ---------------------------------------------------------------------------
# Hauptfunktion: Sync für alle Teams
# ---------------------------------------------------------------------------

def sync_all(
    get_prev_games_fn,
    get_next_games_fn,
    get_table_fn,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Liest alle WP-Teams, holt fussball.de-Daten und schreibt sie zurück.
    Gibt eine Zusammenfassung zurück: {team_name: status}.
    """
    wp_teams = get_wp_teams()
    logger.info("Gefunden: %d WordPress-Teams", len(wp_teams))

    results: Dict[str, Any] = {}
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    for wpt in wp_teams:
        name = wpt.get("title", {}).get("rendered", f"ID:{wpt['id']}")
        meta = wpt.get("meta", {})
        fd_team_id: Optional[str] = meta.get("fussball_de_team_id", "").strip() or None

        if not fd_team_id:
            logger.info("Team '%s' hat keine fussball_de_team_id – übersprungen", name)
            results[name] = "skipped (keine fussball_de_team_id)"
            continue

        logger.info("Syncing '%s' (fussball.de ID: %s)…", name, fd_team_id)
        try:
            prev_games = get_prev_games_fn(fd_team_id)
            next_games = get_next_games_fn(fd_team_id)
            table = get_table_fn(fd_team_id)

            new_meta: Dict[str, Any] = {
                "fd_letzte_spiele": [_game_to_meta(g, is_past=True) for g in prev_games[:10]],
                "fd_naechste_spiele": [_game_to_meta(g, is_past=False) for g in next_games[:5]],
                "fd_tabelle": _table_to_meta(table),
                "fd_zuletzt_aktualisiert": now_str,
            }

            if dry_run:
                results[name] = {"status": "dry-run", "prev": len(prev_games), "next": len(next_games), "table": len(table)}
            else:
                ok = update_team_meta(wpt["id"], new_meta)
                results[name] = "ok" if ok else "error"
        except Exception as exc:
            logger.error("Fehler bei Team '%s': %s", name, exc)
            results[name] = f"error: {exc}"

    return results
