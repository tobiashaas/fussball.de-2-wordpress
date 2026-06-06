"""
CLI-Einstiegspunkt für den fussball.de → WordPress Sync.
Aufruf: python -m src.main [--dry-run]
Exit 0 = Erfolg, Exit 1 = Fehler.
"""
import argparse
import json
import logging
import sys

from .config import CLUB_ID
from .crawler import get_club_teams, get_team_prev_games, get_team_next_games, get_team_table
from .wp_sync import sync_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="fussball.de → WordPress Meta Box Sync")
    parser.add_argument("--dry-run", action="store_true", help="Kein Schreiben nach WordPress")
    args = parser.parse_args()

    logger.info("=== FC Königsfeld fussball.de Sync gestartet ===")
    logger.info("Club-ID: %s | dry-run: %s", CLUB_ID, args.dry_run)

    # Teams auf fussball.de anzeigen (Info-Ausgabe)
    fd_teams = get_club_teams(CLUB_ID)
    if not fd_teams:
        logger.error("Keine Teams auf fussball.de gefunden für Club-ID %s", CLUB_ID)
        return 1
    logger.info("fussball.de Teams gefunden: %s", [t.name for t in fd_teams])

    results = sync_all(
        get_prev_games_fn=get_team_prev_games,
        get_next_games_fn=get_team_next_games,
        get_table_fn=get_team_table,
        dry_run=args.dry_run,
    )

    print(json.dumps(results, ensure_ascii=False, indent=2))

    errors = [k for k, v in results.items() if isinstance(v, str) and v.startswith("error")]
    if errors:
        logger.error("Fehler bei folgenden Teams: %s", errors)
        return 1

    logger.info("=== Sync abgeschlossen ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
