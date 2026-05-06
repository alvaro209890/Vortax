#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
fi

echo "Preparando backend..."
cd "$ROOT_DIR/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8010 --reload &
BACKEND_PID=$!

echo "Preparando frontend..."
cd "$ROOT_DIR/frontend"
npm install --silent
npm run dev &
FRONTEND_PID=$!

LAN_IP="$(hostname -I | awk '{print $1}')"

echo ""
echo "Vortax rodando:"
echo "  Backend local:  http://localhost:8010"
echo "  Frontend local: http://localhost:5173"
echo "  Outro PC LAN:   http://${LAN_IP}:5173"
echo "  Modo: MVP local sem autenticacao"
echo ""

cleanup() {
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT

wait
