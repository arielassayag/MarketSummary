#!/usr/bin/env bash
# CDP — Cabra da Peste: atalho do Claude Code com o plugin `cdp` para o agendador do sistema.
#
# Uso:
#   scripts/cdp_run_task.sh <semanal|diario|cobertura|risco|status|calibracao> [tarefa] [opções]
#   ex.: scripts/cdp_run_task.sh diario cdp-diario-reforco
# Equivale a:
#   scripts/cdp_rotina.sh <tarefa> --harness claude --modo-prompt plugin [opções]
# O script de rotina faz tudo (trava local com espera em CDP_LOCK_WAIT_MIN e saída 75 se
# continuar ocupada, uv sync, prévia do gate sem chamar o modelo, backtest da calibração antes
# da skill, `claude -p "/cdp:<skill> <tarefa>"`, liberação da trava distribuída, log em
# logs/cdp/). Prefira passar a tarefa: sem ela, este atalho escolhe a da família pelo horário de
# Brasília (para manter funcionando agendas antigas, de uma linha por skill).
# As opções seguem para scripts/cdp_rotina.sh (--ensaio, --manual, --seco).
set -euo pipefail

SKILL="${1:-}"
case "$SKILL" in
  semanal|diario|cobertura|risco|status|calibracao) shift ;;
  *) echo "uso: $0 <semanal|diario|cobertura|risco|status|calibracao> [tarefa cdp-...] [opções]" >&2
     exit 2 ;;
esac

TAREFA=""
case "${1:-}" in
  cdp-*) TAREFA="$1"; shift ;;
esac
if [ -z "$TAREFA" ]; then
  HORA="$(TZ=America/Sao_Paulo date +%H%M)"
  DIA="$(TZ=America/Sao_Paulo date +%u)"   # 1 = segunda … 6 = sábado
  case "$SKILL" in
    semanal)
      if [ "$HORA" -lt 1207 ]; then TAREFA=cdp-semanal
      elif [ "$HORA" -lt 1307 ]; then TAREFA=cdp-semanal-b
      elif [ "$HORA" -lt 1407 ]; then TAREFA=cdp-semanal-c
      else TAREFA=cdp-semanal-d; fi ;;
    diario)
      if [ "$DIA" -eq 6 ]; then TAREFA=cdp-diario-sabado
      elif [ "$HORA" -ge 2107 ] || [ "$HORA" -lt 1000 ]; then TAREFA=cdp-diario-reforco
      else TAREFA=cdp-diario; fi ;;
    risco)
      if [ "$HORA" -ge 1603 ]; then TAREFA=cdp-risco-1603; else TAREFA=cdp-risco-1330; fi ;;
    *) TAREFA="cdp-$SKILL" ;;
  esac
fi
case "$TAREFA" in
  "cdp-$SKILL"|"cdp-$SKILL"-*) ;;
  *) echo "a tarefa $TAREFA não é da skill $SKILL" >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$ROOT/scripts/cdp_rotina.sh" "$TAREFA" --harness claude --modo-prompt plugin "$@"
