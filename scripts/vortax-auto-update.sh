#!/usr/bin/env bash
#
# vortax-auto-update.sh
# Monitora o repositorio GitHub e reinicia o backend quando ha novas alteracoes no main.
# Executado como servico systemd user.
#

set -euo pipefail

REPO_PATH="/media/server/HD Backup/Servidores_NAO_MEXA/Vortax"
BRANCH="main"
SLEEP_INTERVAL="${VORTAX_POLL_INTERVAL:-60}"
BACKEND_SERVICE="vortax-backend.service"
FRONTEND_DIR="$REPO_PATH/frontend"

log() {
    echo "[vortax-auto-update] $(date '+%Y-%m-%d %H:%M:%S') $*"
}

cd "$REPO_PATH"

# Garante que o git esteja configurado para pull sem conflito
export GIT_MERGE_AUTOEDIT=no

log "Iniciando monitoramento do repositorio (intervalo: ${SLEEP_INTERVAL}s, branch: $BRANCH)"

while true; do
    sleep "$SLEEP_INTERVAL"

    # Busca estado remoto sem aplicar
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
        continue  # Sem mudancas
    fi

    log "Nova atualizacao detectada: $LOCAL -> $REMOTE"

    # Pull das mudancas
    if ! git pull --ff-only origin "$BRANCH" 2>&1; then
        log "ERRO: git pull falhou. Tentando reset para estado remoto..."
        if git reset --hard "origin/$BRANCH" 2>&1; then
            log "Reset para origin/$BRANCH concluido."
        else
            log "ERRO CRITICO: Nao foi possivel sincronizar. Pulando este ciclo."
            continue
        fi
    fi

    # Verifica se houve mudanca nos arquivos do backend
    CHANGED_BACKEND=$(git diff --name-only "$LOCAL" "$REMOTE" 2>/dev/null | grep -c '^backend/' || true)

    log "Pull concluido. Arquivos backend alterados: ${CHANGED_BACKEND:-0}"

    # Reinicia o backend se houve mudanca
    if [ "${CHANGED_BACKEND:-0}" -gt 0 ]; then
        log "Reiniciando backend ($BACKEND_SERVICE)..."
        if systemctl --user restart "$BACKEND_SERVICE" 2>&1; then
            log "Backend reiniciado com sucesso."
            # Aguarda o backend iniciar e verifica health
            sleep 3
            if curl -sf http://localhost:8010/health > /dev/null 2>&1; then
                log "Health check OK."
            else
                log "AVISO: Health check falhou apos restart."
            fi
        else
            log "ERRO: Falha ao reiniciar backend."
        fi
    fi

    # Build e deploy do frontend se houve mudanca
    CHANGED_FRONTEND=$(git diff --name-only "$LOCAL" "$REMOTE" 2>/dev/null | grep -c '^frontend/' || true)
    if [ "${CHANGED_FRONTEND:-0}" -gt 0 ]; then
        log "Mudancas no frontend detectadas. Buildando..."
        if cd "$FRONTEND_DIR" && npm run build 2>&1; then
            log "Build concluido. Deployando no Firebase..."
            if cd "$REPO_PATH" && firebase deploy --project notazap-2520f --only hosting 2>&1; then
                log "Firebase deploy concluido."
            else
                log "ERRO: Firebase deploy falhou."
            fi
        else
            log "ERRO: Build do frontend falhou."
        fi
        cd "$REPO_PATH"
    fi
done
