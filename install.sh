#!/bin/bash
set -e

INSTALL_DIR="/opt/fussball-sync"

echo "=== FC Königsfeld fussball.de Sync – Installation ==="

# Repo klonen oder updaten
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "[1/4] Repository aktualisieren..."
    git -C "$INSTALL_DIR" pull
else
    echo "[1/4] Repository klonen..."
    git clone https://github.com/tobiashaas/fussball.de-2-wordpress.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# Python venv
echo "[2/4] Python venv erstellen..."
python3 -m venv venv
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q

# .env anlegen
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "[3/4] .env aus Vorlage erstellen..."
    cp .env.example .env
    echo ""
    echo "  WICHTIG: Bitte jetzt die .env Datei befüllen:"
    echo "  nano $INSTALL_DIR/.env"
    echo ""
else
    echo "[3/4] .env existiert bereits – wird nicht überschrieben."
fi

# Test-Lauf
echo "[4/4] Test-Lauf (nur fussball.de Teams abrufen)..."
venv/bin/python -m src.main --dry-run && echo "  ✓ Test erfolgreich" || echo "  ✗ Test fehlgeschlagen – bitte .env prüfen"

echo ""
echo "=== Installation abgeschlossen ==="
echo "n8n Execute Command:"
echo "  cd $INSTALL_DIR && venv/bin/python -m src.main 2>&1"
