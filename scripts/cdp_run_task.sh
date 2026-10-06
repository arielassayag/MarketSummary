#!/usr/bin/env bash
# CDP — Cabra da Peste: executa uma skill do plugin `cdp` sem interface (`claude -p`).
#
# Alternativa às tarefas agendadas do app desktop, para cron (Linux) ou launchd (macOS).
# Uso:
#   scripts/cdp_run_task.sh <semanal|diario|cobertura|risco|status|calibracao> [argumentos da skill]
# Variáveis opcionais:
#   CDP_PERMISSION_MODE   modo de permissão do claude -p (padrão: acceptEdits)
#   CDP_CLAUDE_ARGS       flags extras do claude (ex.: "--permission-prompts none")
#   CDP_CLAUDE_BIN        caminho do executável claude (padrão: o do PATH)
#   CDP_LOCK_WAIT_MIN     minutos esperando outra rotina terminar (padrão: 60 para semanal,
#                         diario e cobertura, 0 para as demais)
#
# Log: logs/cdp/<tarefa>_<AAAAmmdd_HHMMSS>.log. Uma trava em logs/cdp/.lock impede duas rotinas
# ao mesmo tempo (o livro é encadeado por hash; execuções concorrentes divergiriam). Se a trava
# continuar ocupada depois da espera, a rotina não roda e o script sai com código 75 (o agendador
# mostra a execução como não concluída).
# Calibração: o backtest leva mais que o limite de um comando e, no modo -p, uma tarefa em segundo
# plano morre quando a resposta termina; por isso este script roda o backtest antes da skill.
# As permissões vêm de .claude/settings.json (allow/deny); no modo -p, o que não estiver liberado
# é negado (não há quem aprove), e a skill relata o bloqueio no resumo.
set -uo pipefail

TASK="${1:-}"
case "$TASK" in
  semanal|diario|cobertura|risco|status|calibracao) shift ;;
  *) echo "uso: $0 <semanal|diario|cobertura|risco|status|calibracao> [argumentos]" >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
# cron/launchd rodam com PATH mínimo: inclui os locais usuais de uv e claude.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.claude/local:/opt/homebrew/bin:/usr/local/bin:$PATH"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

mkdir -p logs/cdp
LOG="logs/cdp/${TASK}_$(date +%Y%m%d_%H%M%S).log"
LOCK="logs/cdp/.lock"

case "$TASK" in
  semanal|diario|cobertura) WAIT_MIN="${CDP_LOCK_WAIT_MIN:-60}" ;;
  *) WAIT_MIN="${CDP_LOCK_WAIT_MIN:-0}" ;;
esac

# Trava órfã (processo morto) com mais de 6 horas é removida.
if [ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +360 2>/dev/null)" ]; then
  rmdir "$LOCK" 2>/dev/null || true
fi
DEADLINE=$(( $(date +%s) + WAIT_MIN * 60 ))
until mkdir "$LOCK" 2>/dev/null; do
  if [ "$(date +%s)" -ge "$DEADLINE" ]; then
    echo "$(date '+%F %T') outra rotina do CDP em execução ($LOCK) após ${WAIT_MIN} min de espera: $TASK não iniciada." >>"$LOG"
    exit 75
  fi
  sleep 30
done
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

CLAUDE="${CDP_CLAUDE_BIN:-claude}"
PROMPT="/cdp:${TASK}"
if [ "$#" -gt 0 ]; then
  PROMPT="$PROMPT $*"
fi

{
  echo "== CDP — rotina $TASK — início $(date '+%F %T %z')"
  if [ "$TASK" = "calibracao" ]; then
    TODAY="$(uv run python -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('America/Sao_Paulo')).date())" 2>/dev/null | tail -n 1)"
    OUT="reports/backtest/${TODAY}/mensal"
    if [ -z "$TODAY" ]; then
      echo "== não foi possível obter a data de Brasília: a skill decide sobre o backtest"
    elif [ -f "reports/backtest/${TODAY}/CALIBRACAO_MENSAL.md" ] || [ -f "$OUT/metrics.json" ]; then
      echo "== backtest mensal de $TODAY já existe em $OUT"
    else
      echo "== backtest mensal (antes da skill) em $OUT — início $(date '+%F %T %z')"
      uv run python -m cdp backtest --start 2021-01-04 --out "$OUT"
      echo "== backtest — fim $(date '+%F %T %z') — código $?"
    fi
  fi
  # shellcheck disable=SC2086
  "$CLAUDE" -p "$PROMPT" --permission-mode "${CDP_PERMISSION_MODE:-acceptEdits}" \
    --output-format text ${CDP_CLAUDE_ARGS:-}
  RC=$?
  echo "== fim $(date '+%F %T %z') — código $RC"
} >>"$LOG" 2>&1

exit "${RC:-1}"
