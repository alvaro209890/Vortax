#!/usr/bin/env bash
#
# vortax-auto-update.sh
# Monitora o repositorio GitHub e reinicia o backend quando ha novas alteracoes no main.
# Executado como servico systemd user.
#

set -euo pipefail

REPO_PATH="/media/server/HD Backup/Vortax"
BRANCH="main"
SLEEP_INTERVAL="${VORTAX_POLL_INTERVAL:-60}"
BACKEND_SERVICE="vortax-backend.service"
FRONTEND_SERVICE="vortax-frontend.service"
FRONTEND_DIR="$REPO_PATH/frontend"

log() {
    echo "[vortax-auto-update] $(date '+%Y-%m-%d %H:%M:%S') $*"
}

cd "$REPO_PATH"

export GIT_MERGE_AUTOEDIT=no

log "Iniciando monitoramento do repositorio (intervalo: ${SLEEP_INTERVAL}s, branch: $BRANCH)"

while true; do
    sleep "$SLEEP_INTERVAL"

    if ! git fetch origin "$BRANCH" --quiet 2>/dev/null; then
        log "ERRO: Falha ao buscar do remote. Verifique conectividade com GitHub."
        continue
    fi

    LOCAL=$(git rev-parse HEAD 2>/dev/null || echo "")
    REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "")

    if [ -z "$LOCAL" ] || [ -z "$REMOTE" ]; then
        log "ERRO: Nao foi possivel obter hash local ou remoto."
        continue
    fi

    if [ "$LOCAL" = "$REMOTE" ]; then
        continue
    fi

    log "Nova atualizacao detectada: $LOCAL -> $REMOTE"

    if ! git pull --ff-only origin "$BRANCH" 2>&1; then
        log "ERRO: git pull falhou. Tentando reset..."
        if git reset --hard "origin/$BRANCH" 2>&1; then
            log "Reset para origin/$BRANCH concluido."
        else
            log "ERRO CRITICO: Nao foi possivel sincronizar."
            continue
        fi
    fi

    CHANGED_BACKEND=$(git diff --name-only "$LOCAL" "$REMOTE" 2>/dev/null | grep -c '^backend/' || true)
    log "Pull concluido. Arquivos backend alterados: ${CHANGED_BACKEND:-0}"

    if [ "${CHANGED_BACKEND:-0}" -gt 0 ]; then
        log "Reiniciando backend..."
        systemctl --user restart "$BACKEND_SERVICE" 2>&1 || log "ERRO: Falha ao reiniciar backend."
        sleep 3
        curl -sf http://localhost:8010/health > /dev/null 2>&1 && log "Health check OK." || log "AVISO: Health check falhou."
    fi

    CHANGED_FRONTEND=$(git diff --name-only "$LOCAL" "$REMOTE" 2>/dev/null | grep -c '^frontend/' || true)
    if [ "${CHANGED_FRONTEND:-0}" -gt 0 ]; then
        log "Mudancas no frontend detectadas. Rebuildando..."
        if cd "$FRONTEND_DIR" && npm run build 2>&1; then
            log "Build concluido. Reiniciando frontend..."
            systemctl --user restart "$FRONTEND_SERVICE" 2>&1 || log "ERRO: Falha ao reiniciar frontend."
        else
            log "ERRO: Build do frontend falhou."
        fi
        cd "$REPO_PATH"
    fi
done
