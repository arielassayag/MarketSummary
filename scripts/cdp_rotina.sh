#!/usr/bin/env bash
# CDP — Cabra da Peste: executor universal de uma rotina em qualquer harness (Claude Code, Codex,
# Gemini CLI, Antigravity ou outro), para cron, launchd, GitHub Actions ou à mão.
#
# Uso:
#   scripts/cdp_rotina.sh <tarefa> [--harness claude|codex|gemini|agy|custom]
#       [--modo-prompt neutro|skill|plugin] [--publicacao agente|executor]
#       [--ensaio] [--manual] [--sem-gate] [--seco]
#   <tarefa>: um id de configs/cdp/rotinas.yaml (ex.: cdp-diario, cdp-semanal-b, cdp-risco-1330).
#   --harness também aceita os nomes de identidade claude-code, antigravity e outro.
#
# Dois modos de publicação:
#   agente   (padrão; Claude Code, Gemini CLI, Antigravity, custom): prévia do gate sem a trava
#            (sem trabalho pendente ou trava de outra execução, nenhuma chamada de modelo); a mente
#            segue o prompt inteiro: gate --adquirir → sincronizar → roteiro → publicar → liberar.
#   executor (padrão no Codex, cujo sandbox deixa .git só de leitura): ESTE script roda o gate com
#            a trava, `cdp sincronizar`, o roteiro pela mente (prompt sem git), `cdp publicar` e
#            libera a trava — tudo o que toca o git fica fora do sandbox.
#   --sem-gate (com --publicacao executor): gate, trava e publicação são de quem chamou (o workflow
#            do GitHub Actions); aqui só o roteiro pela mente.
#
# Variáveis:
#   CDP_HARNESS_CMD   comando do harness "custom", com {prompt_file} no lugar do arquivo do prompt
#   CDP_PERMISSION_MODE / CDP_CLAUDE_ARGS / CDP_CLAUDE_BIN   (claude; padrão acceptEdits)
#   CDP_CODEX_SANDBOX  sandbox do codex exec (padrão workspace-write com rede)
#   CDP_AGY_TIMEOUT    --print-timeout do agy (padrão: timeout_min da tarefa, em minutos)
#   CDP_LOCK_WAIT_MIN  minutos esperando outra rotina neste clone (padrão: 60 nos escritores
#                      exclusivos, 0 nas demais)
#   CDP_EXECUTOR / CDP_HARNESS   identidade deste ambiente (docs/cdp/AUTOMACAO.md)
# Códigos: 0 ok ou nada a fazer · 1 falha do harness · 2 uso · 3 sincronização parou ou publicação
#          sem push · 4 sem progresso · 75 trava local ocupada · 78 configuração.
set -uo pipefail

TAREFA="${1:-}"
case "$TAREFA" in
  cdp-*) shift ;;
  *) echo "uso: $0 <tarefa cdp-...> [--harness claude|codex|gemini|agy|custom] [--seco]" >&2
     exit 2 ;;
esac
HARNESS=""
MODO="neutro"
PUBLICACAO=""
ENSAIO=""
MANUAL=""
SEM_GATE=0
SECO=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --harness) HARNESS="${2:-}"; shift 2 ;;
    --modo-prompt) MODO="${2:-}"; shift 2 ;;
    --publicacao) PUBLICACAO="${2:-}"; shift 2 ;;
    --ensaio) ENSAIO="--ensaio"; shift ;;
    --manual) MANUAL="--manual"; shift ;;
    --sem-gate) SEM_GATE=1; shift ;;
    --seco) SECO=1; shift ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
done
# Nomes de identidade (CDP_HARNESS) → nome do harness neste script.
normaliza() {
  case "$1" in
    claude|claude-code) echo claude ;;
    codex) echo codex ;;
    gemini) echo gemini ;;
    agy|antigravity) echo agy ;;
    custom|outro) echo custom ;;
    "") echo "" ;;
    *) echo "?$1" ;;
  esac
}
if [ -z "$HARNESS" ]; then
  HARNESS="$(normaliza "${CDP_HARNESS:-claude-code}")"
  case "$HARNESS" in "?"*) HARNESS=custom ;; esac
else
  HARNESS="$(normaliza "$HARNESS")"
fi
case "$HARNESS" in
  claude) export CDP_HARNESS="${CDP_HARNESS:-claude-code}" ;;
  codex) export CDP_HARNESS="${CDP_HARNESS:-codex}" ;;
  gemini) export CDP_HARNESS="${CDP_HARNESS:-gemini}" ;;
  agy) export CDP_HARNESS="${CDP_HARNESS:-antigravity}" ;;
  custom) export CDP_HARNESS="${CDP_HARNESS:-outro}" ;;
  *) echo "harness desconhecido: ${HARNESS#\?} (use claude, codex, gemini, agy ou custom)" >&2
     exit 2 ;;
esac
case "$MODO" in neutro|skill|plugin) ;; *) echo "modo-prompt inválido: $MODO" >&2; exit 2 ;; esac
if [ -z "$PUBLICACAO" ]; then
  case "$HARNESS" in codex) PUBLICACAO=executor ;; *) PUBLICACAO=agente ;; esac
fi
case "$PUBLICACAO" in agente|executor) ;; *) echo "publicacao inválida: $PUBLICACAO" >&2; exit 2 ;; esac
if [ "$SEM_GATE" -eq 1 ] && [ "$PUBLICACAO" != "executor" ]; then
  echo "--sem-gate exige --publicacao executor (gate e publicação de quem chama)" >&2; exit 2
fi
if [ "$PUBLICACAO" = "executor" ] && [ "$MODO" != "neutro" ]; then
  echo "--publicacao executor exige --modo-prompt neutro" >&2; exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1
# cron/launchd rodam com PATH mínimo: acrescenta (no fim, sem passar à frente do PATH dado) os
# locais usuais de uv, claude, codex, gemini e agy.
export PATH="$PATH:$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.claude/local:$HOME/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

mkdir -p logs/cdp
RUN="${TAREFA}_$(date +%Y%m%d_%H%M%S)"
LOG="logs/cdp/${RUN}.log"
PROMPT_FILE="logs/cdp/${RUN}.prompt.md"
LOCK="logs/cdp/.lock"
exec > >(tee -a "$LOG") 2>&1

log() { echo "== $(date '+%F %T %z') $*"; }
campo() {  # campo <arquivo json> <expressão python sobre d>
  uv run python -c "import json,sys; d=json.load(open(sys.argv[1], encoding='utf-8')); v=$2; print('' if v is None else v)" "$1" 2>/dev/null | tail -n 1
}

case "$TAREFA" in
  cdp-semanal*|cdp-diario*|cdp-cobertura*) WAIT_MIN="${CDP_LOCK_WAIT_MIN:-60}" ;;
  *) WAIT_MIN="${CDP_LOCK_WAIT_MIN:-0}" ;;
esac
TRAVA=""
liberar_trava() {
  if [ -n "$TRAVA" ]; then
    uv run python -m cdp trava liberar --id "$TRAVA" >/dev/null 2>&1 || true
    TRAVA=""
  fi
}
if [ "$SECO" -eq 0 ]; then
  if [ -d "$LOCK" ] && [ -n "$(find "$LOCK" -maxdepth 0 -mmin +360 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null || true   # trava órfã (> 6 h)
  fi
  DEADLINE=$(( $(date +%s) + WAIT_MIN * 60 ))
  until mkdir "$LOCK" 2>/dev/null; do
    if [ "$(date +%s)" -ge "$DEADLINE" ]; then
      log "outra rotina do CDP em execução ($LOCK) após ${WAIT_MIN} min: $TAREFA não iniciada"
      exit 75
    fi
    sleep 30
  done
  trap 'liberar_trava; rmdir "$LOCK" 2>/dev/null || true' EXIT
  log "rotina $TAREFA — harness $HARNESS — publicação $PUBLICACAO — início"
  uv sync --frozen --extra dev --extra ai -q || { log "uv sync falhou"; exit 78; }
fi

GRAVA=""
TIMEOUT_MIN=""
ANTES="logs/cdp/${RUN}.execucoes_antes"
ls .cdp/execucoes 2>/dev/null >"$ANTES" || : >"$ANTES"

if [ "$SEM_GATE" -eq 0 ] && [ "$SECO" -eq 0 ]; then
  GATE="logs/cdp/${RUN}.gate.json"
  if [ "$PUBLICACAO" = "executor" ]; then
    # Este script segura a trava e publica: a mente só faz o roteiro.
    # shellcheck disable=SC2086
    uv run python -m cdp rotinas gate --tarefa "$TAREFA" --adquirir $MANUAL $ENSAIO >"$GATE"
  else
    # Prévia sem a trava (a mente roda o gate com --adquirir, passo 2 do prompt).
    # shellcheck disable=SC2086
    uv run python -m cdp rotinas gate --tarefa "$TAREFA" --previa $MANUAL $ENSAIO >"$GATE"
  fi
  RC=$?
  if [ "$RC" -eq 10 ]; then
    log "sem execução: $(campo "$GATE" 'd.get("motivo")')"
    exit 0
  elif [ "$RC" -ne 0 ]; then
    log "gate com erro de configuração (código $RC)"
    exit 78
  fi
  log "gate: executar — $(campo "$GATE" 'd.get("motivo")')"
  GRAVA="$(campo "$GATE" 'd.get("grava")')"
  TIMEOUT_MIN="$(campo "$GATE" 'd.get("timeout_min")')"
  if [ "$PUBLICACAO" = "executor" ]; then
    TRAVA="$(campo "$GATE" '(d.get("trava") or {}).get("id")')"
    export CDP_TRAVA_ID="$TRAVA"
    CDP_EXECUCAO="$(campo "$GATE" 'd.get("execucao")')"
    export CDP_EXECUCAO
    if [ "$GRAVA" = "True" ]; then
      SINC="logs/cdp/${RUN}.sincronizar.json"
      uv run python -m cdp sincronizar --executar >"$SINC"
      if [ "$?" -ne 0 ]; then
        log "sincronização parou: $(campo "$SINC" 'd.get("motivo")')"
        exit 3
      fi
    fi
  fi
fi

PRE="$(uv run python -m cdp rotinas pre --tarefa "$TAREFA" 2>/dev/null | tail -n 1)"
if [ -n "$PRE" ] && [ "$SECO" -eq 0 ]; then
  if [ "$PUBLICACAO" = "agente" ] && [ "$SEM_GATE" -eq 0 ] && [ "$GRAVA" = "True" ] \
     && [ "$(campo "$GATE" 'd.get("exclusiva")')" = "False" ]; then
    # Registra a execução ANTES do pré-comando (tarefa compartilhada, sem trava): o retrato que
    # `cdp publicar` compara fica sem o resultado do pré-comando (ex.: o backtest da calibração),
    # que então sai na publicação. O gate da mente reutiliza esta execução (CDP_EXECUCAO).
    REG="logs/cdp/${RUN}.registro.json"
    # shellcheck disable=SC2086
    uv run python -m cdp rotinas gate --tarefa "$TAREFA" $MANUAL $ENSAIO >"$REG"
    RC=$?
    if [ "$RC" -eq 10 ]; then
      log "sem execução: $(campo "$REG" 'd.get("motivo")')"
      exit 0
    elif [ "$RC" -ne 0 ]; then
      log "gate com erro de configuração (código $RC)"
      exit 78
    fi
    CDP_EXECUCAO="$(campo "$REG" 'd.get("execucao")')"
    export CDP_EXECUCAO
    log "execução $CDP_EXECUCAO registrada antes do pré-comando (o gate da mente a reutiliza)"
  fi
  case "$PRE" in
    "uv run python -m cdp "*) log "pré-comando: $PRE"; bash -c "$PRE" || log "pré-comando falhou (código $?)" ;;
    *) log "pré-comando recusado (não é um comando do cdp): $PRE" ;;
  esac
fi

# shellcheck disable=SC2086
uv run python -m cdp rotinas prompt --tarefa "$TAREFA" --harness "$HARNESS" --modo "$MODO" \
  --publicacao "$PUBLICACAO" $ENSAIO $MANUAL >"$PROMPT_FILE" || { log "prompt falhou"; exit 78; }

if [ "$HARNESS" = "agy" ] && [ -z "$TIMEOUT_MIN" ]; then
  TINFO="logs/cdp/${RUN}.tarefa.json"
  uv run python -m cdp rotinas listar --formato json >"$TINFO" 2>/dev/null
  TIMEOUT_MIN="$(campo "$TINFO" "[t for t in d if t['id'] == '$TAREFA'][0]['timeout_min']")"
fi
FINAL="logs/cdp/${RUN}.final.md"
case "$HARNESS" in
  claude)
    # shellcheck disable=SC2206
    CMD=("${CDP_CLAUDE_BIN:-claude}" -p "$(cat "$PROMPT_FILE")" --permission-mode
         "${CDP_PERMISSION_MODE:-acceptEdits}" --output-format text ${CDP_CLAUDE_ARGS:-}) ;;
  codex)
    CMD=(codex exec --sandbox "${CDP_CODEX_SANDBOX:-workspace-write}"
         -c sandbox_workspace_write.network_access=true --skip-git-repo-check
         -o "$FINAL" "$(cat "$PROMPT_FILE")") ;;
  gemini)
    CMD=(gemini -p "$(cat "$PROMPT_FILE")" --approval-mode yolo --output-format text) ;;
  agy)
    # Experimental: confira as opções com `agy --help` (padrão do --print-timeout: 5 min).
    CMD=(agy -p "$(cat "$PROMPT_FILE")" --dangerously-skip-permissions
         --print-timeout "${CDP_AGY_TIMEOUT:-${TIMEOUT_MIN:-60}m}") ;;
  custom)
    if [ -z "${CDP_HARNESS_CMD:-}" ]; then log "defina CDP_HARNESS_CMD para o harness custom"; exit 78; fi
    CMD=(bash -c "${CDP_HARNESS_CMD//\{prompt_file\}/$PROMPT_FILE}") ;;
esac

if [ "$SECO" -eq 1 ]; then
  printf 'harness:'; printf ' %q' "${CMD[0]}"; printf '\n'
  printf 'publicacao: %s\n' "$PUBLICACAO"
  printf 'prompt: %s\n' "$PROMPT_FILE"
  exit 0
fi

log "harness: ${CMD[0]} (prompt em $PROMPT_FILE)"
"${CMD[@]}"
HRC=$?
log "harness terminou — código $HRC"

if [ "$PUBLICACAO" = "executor" ]; then
  if [ "$SEM_GATE" -eq 1 ]; then
    # Workflow: a trava e a publicação são do job publicador; nada a liberar aqui.
    [ "$HRC" -eq 0 ] || exit 1
    log "fim (publicação pelo workflow)"
    exit 0
  fi
  PUBRC=0
  if [ "$GRAVA" = "True" ] && [ -z "$ENSAIO" ]; then
    PUB="logs/cdp/${RUN}.publicar.json"
    PUB_ARGS=(--tarefa "$TAREFA" --mensagem-automatica --execucao "$CDP_EXECUCAO")
    [ -n "$TRAVA" ] && PUB_ARGS+=(--trava "$TRAVA")
    uv run python -m cdp publicar "${PUB_ARGS[@]}" >"$PUB"
    PUBRC=$?
    log "publicação (código $PUBRC): $(campo "$PUB" 'd.get("motivo")')"
  fi
  liberar_trava
  EID="$CDP_EXECUCAO"
else
  # A trava distribuída é da mente (gate --adquirir); se ela não liberou, este script libera.
  NOVA="$(uv run python - "$TAREFA" "$ANTES" <<'PY' 2>/dev/null | tail -n 1
import json, sys
from pathlib import Path
antes = set(Path(sys.argv[2]).read_text(encoding="utf-8").split())
regs = []
for p in Path(".cdp/execucoes").glob("*.json"):
    if p.name in antes:
        continue
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        continue
    if d.get("tarefa") == sys.argv[1]:
        regs.append((d.get("inicio") or "", p.stem, d.get("trava") or ""))
if regs:
    _, eid, trava = max(regs)
    print(f"{eid} {trava}".strip())
PY
)"
  EID="${NOVA%% *}"
  TRAVA="${NOVA#"$EID"}"
  TRAVA="${TRAVA# }"
  liberar_trava
  PUBRC=0
fi
if [ "$HRC" -ne 0 ]; then
  exit 1
fi
if [ "$PUBRC" -ne 0 ] && [ "$PUBRC" -ne 6 ]; then
  exit 3
fi
if [ -n "${EID:-}" ] && [ -f ".cdp/execucoes/${EID}.json" ]; then
  uv run python -m cdp rotinas conferir --tarefa "$TAREFA" --execucao "$EID" >/dev/null
  if [ "$?" -eq 4 ]; then
    log "sem progresso: as mesmas pendências continuam e nenhum commit novo"
    exit 4
  fi
fi
log "fim"
exit 0
