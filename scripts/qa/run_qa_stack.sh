#!/usr/bin/env bash
# Sobe uma pilha de QA isolada do Vortax: site local, modelo roteirizado (fixture),
# backend real com banco/workspace próprios e o frontend em modo dev.
# Não toca no .env, no banco nem na pasta de projetos de produção.
#
#   QA_DIR=/tmp/vortax-qa PYTHON=/caminho/venv/bin/python scripts/qa/run_qa_stack.sh
#
# Portas: site 8765 (no IP da máquina), modelo 8799, backend 8011, frontend 5174.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
QA_DIR="${QA_DIR:-/tmp/vortax-qa}"
PYTHON="${PYTHON:-python3}"
HOST_IP="${QA_HOST_IP:-$(hostname -I | awk '{print $1}')}"
SITE_URL="http://${HOST_IP}:8765"
CHROME="${CHROME_BINARY:-$(ls /opt/pw-browsers/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)}"

mkdir -p "$QA_DIR"/{data,projetos,runtime,logs}

"$PYTHON" -m http.server 8765 --bind "$HOST_IP" --directory "$ROOT/scripts/qa/local_site" \
  > "$QA_DIR/logs/site.log" 2>&1 &
echo $! > "$QA_DIR/site.pid"

"$PYTHON" "$ROOT/scripts/qa/scripted_model_server.py" --port 8799 --site "$SITE_URL" \
  > "$QA_DIR/logs/model.log" 2>&1 &
echo $! > "$QA_DIR/model.pid"

(
  cd "$ROOT/backend"
  env \
    APP_ENV=qa ALLOW_NO_AUTH=true LAN_ONLY=true \
    DEEPSEEK_API_KEY=qa-scripted DEEPSEEK_BASE_URL=http://127.0.0.1:8799/v1 \
    DEEPSEEK_MODEL=qa-scripted DEEPSEEK_MODEL_BRAIN=qa-scripted DEEPSEEK_MODEL_FAST=qa-scripted \
    GROQ_API_KEY= \
    DATABASE_BASE_PATH="$QA_DIR/data" WORKSPACE_PATH="$QA_DIR/projetos" RUNTIME_PATH="$QA_DIR/runtime" \
    CHROME_BINARY="$CHROME" CHROME_PROFILE_PATH="$QA_DIR/runtime/chrome-profile" \
    BACKEND_PORT=8011 \
    NO_PROXY="127.0.0.1,localhost,${HOST_IP}" no_proxy="127.0.0.1,localhost,${HOST_IP}" \
    "$PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8011 \
    > "$QA_DIR/logs/backend.log" 2>&1 &
  echo $! > "$QA_DIR/backend.pid"
)

(
  cd "$ROOT/frontend"
  VITE_API_BASE_URL= VORTAX_API_TARGET=http://127.0.0.1:8011 npx vite --host 127.0.0.1 --port 5174 --strictPort \
    > "$QA_DIR/logs/frontend.log" 2>&1 &
  echo $! > "$QA_DIR/frontend.pid"
)

echo "site: $SITE_URL  modelo: http://127.0.0.1:8799/v1  backend: http://127.0.0.1:8011  front: http://127.0.0.1:5174"
echo "logs em $QA_DIR/logs; para parar: kill \$(cat $QA_DIR/*.pid)"
