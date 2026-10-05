#!/usr/bin/env bash
# CDP — Cabra da Peste: executa uma skill do plugin `cdp` sem interface (`claude -p`).
#
# Alternativa às tarefas agendadas do app desktop, para cron (Linux) ou launchd (macOS).
# Uso:
#   scripts/cdp_run_task.sh <semanal|diario|risco|status|calibracao> [argumentos da skill]
# Variáveis opcionais:
#   CDP_PERMISSION_MODE   modo de permissão do claude -p (padrão: acceptEdits)
#   CDP_CLAUDE_ARGS       flags extras do claude (ex.: "--permission-prompts none")
#   CDP_CLAUDE_BIN        caminho do executável claude (padrão: o do PATH)
#
# Log: logs/cdp/<tarefa>_<AAAAmmdd_HHMMSS>.log. Uma trava em logs/cdp/.lock impede duas rotinas
# ao mesmo tempo (o livro é encadeado por hash; execuções concorrentes divergiriam).
# As permissões vêm de .claude/settings.json (allow/deny); no modo -p, o que não estiver liberado
# é negado (não há quem aprove), e a skill relata o bloqueio no resumo.
set -uo pipefail

TASK="${1:-}"
case "$TASK" in
  semanal|diario|risco|status|calibracao) shift ;;
  *) echo "uso: $0 <semanal|diario|risco|status|calibracao> [argumentos]" >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
# cron/launchd rodam com PATH mínimo: inclui os locais usuais de uv e claude.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.claude/local:/opt/homebrew/bin:/usr/local/bin:$PATH"
export PYTHONUTF8=1

mkdir -p logs/cdp
LOG="logs/cdp/${TASK}_$(date +%Y%m%d_%H%M%S).log"
LOCK="logs/cdp/.lock"

# Trava órfã (processo morto) com mais de 6 horas é removida.
if [ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +360 2>/dev/null)" ]; then
  rmdir "$LOCK" 2>/dev/null || true
fi
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date '+%F %T') outra rotina do CDP em execução ($LOCK): $TASK não iniciada." >>"$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

CLAUDE="${CDP_CLAUDE_BIN:-claude}"
PROMPT="/cdp:${TASK}"
if [ "$#" -gt 0 ]; then
  PROMPT="$PROMPT $*"
fi

{
  echo "== CDP — rotina $TASK — início $(date '+%F %T %z')"
  # shellcheck disable=SC2086
  "$CLAUDE" -p "$PROMPT" --permission-mode "${CDP_PERMISSION_MODE:-acceptEdits}" \
    --output-format text ${CDP_CLAUDE_ARGS:-}
  RC=$?
  echo "== fim $(date '+%F %T %z') — código $RC"
} >>"$LOG" 2>&1

exit "${RC:-1}"
