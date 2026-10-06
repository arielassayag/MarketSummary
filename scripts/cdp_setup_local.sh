#!/usr/bin/env bash
# CDP — Cabra da Peste: preparação do clone dedicado às rotinas no PC local (macOS/Linux).
#
# Uso (na raiz do clone ou de qualquer pasta):
#   bash scripts/cdp_setup_local.sh
# Variáveis opcionais:
#   CDP_HARNESS=claude-code   app que vai rodar as rotinas neste clone: claude-code (padrão),
#                             codex ou antigravity (identidade gravada em .cdp/local.yaml)
#   CDP_SKIP_PLUGIN=1         não registra o marketplace nem instala o plugin `cdp` no Claude Code
#   CDP_SKIP_TESTS=1          pula o teste rápido offline
#   CDP_SKIP_TRAVA_TESTE=1    não testa o push no ramo cdp-trava (só lê a trava)
#
# O que faz: confere git, instala o uv (instalador oficial) se faltar, sincroniza o ambiente,
# roda `cdp status`, `cdp agenda` e `cdp verify`, um teste offline (DADOS SIMULADOS), testa o
# push em main (--dry-run) e o push real no ramo cdp-trava (adquire a trava distribuída por 1
# minuto, em nome da tarefa só de leitura cdp-status, e a libera em seguida; rode fora dos
# horários das rotinas), registra a identidade do clone (`cdp executor registrar --como
# local-pc`), registra o marketplace e instala o plugin `cdp` (Claude Code) e imprime os próximos
# passos. Não altera o livro, a trilha nem os dados; no GitHub, só o ramo cdp-trava recebe os
# dois commits do teste da trava.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONUTF8=1
HARNESS="${CDP_HARNESS:-claude-code}"
case "$HARNESS" in
  claude-code|codex|antigravity|gemini) ;;
  *) echo "CDP_HARNESS inválido: $HARNESS (use claude-code, codex, antigravity ou gemini)" >&2; exit 2 ;;
esac

step() { printf '\n== %s\n' "$*"; }
warn() { printf 'AVISO: %s\n' "$*" >&2; }

step "CDP — Cabra da Peste: preparação local em $ROOT (app: $HARNESS)"
[ -f pyproject.toml ] && [ -d src/cdp ] || { echo "Pasta inesperada: rode a partir do clone do repositório." >&2; exit 1; }

step "git"
command -v git >/dev/null 2>&1 || { echo "git não encontrado: instale o git e rode de novo." >&2; exit 1; }
git --version
echo "ramo: $(git branch --show-current 2>/dev/null || echo "?")"
if git config --get core.autocrlf >/dev/null 2>&1; then
  echo "core.autocrlf=$(git config --get core.autocrlf) (book/, data/ e reports/ ficam sem conversão via .gitattributes)"
fi

step "uv"
UV_INSTALLED=0
if ! command -v uv >/dev/null 2>&1; then
  echo "uv não encontrado: instalando pelo instalador oficial (https://astral.sh/uv)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  UV_INSTALLED=1
fi
uv --version

step "Dependências (uv sync --extra dev --extra ai)"
uv sync --extra dev --extra ai

step "Estado do fundo"
uv run python -m cdp status
uv run python -m cdp agenda
if ! uv run python -m cdp verify; then
  warn "cdp verify não confirmou a integridade. Não ligue as rotinas antes de entender o motivo."
fi

if [ "${CDP_SKIP_TESTS:-0}" != "1" ]; then
  step "Teste rápido offline (DADOS SIMULADOS)"
  uv run pytest tests/cdp/test_demo_runtime.py -q -W ignore
fi

step "Acesso de escrita ao GitHub: push em main e no ramo cdp-trava (trava distribuída)"
if ! git push --dry-run >/dev/null 2>&1; then
  warn "git push --dry-run falhou: configure a autenticação (gh auth login, chave SSH ou gerenciador de credenciais) e um upstream (git push -u origin main). As rotinas também precisam fazer push no ramo cdp-trava (a trava falha fechada)."
else
  echo "push em main (--dry-run): ok"
fi
if [ "${CDP_SKIP_TRAVA_TESTE:-0}" = "1" ]; then
  uv run python -m cdp trava ver || warn "não foi possível ler a trava (ramo cdp-trava): confira a rede e a credencial do Git."
else
  # Push real no ramo cdp-trava: adquire a trava por 1 minuto (tarefa só de leitura cdp-status)
  # e a libera. Uma rotina que dispare neste instante encontra a trava ocupada e é pulada: rode
  # fora dos horários das rotinas.
  set +e
  TRAVA_JSON="$(uv run python -m cdp trava adquirir --tarefa cdp-status --ttl 1 2>/dev/null)"
  TRAVA_RC=$?
  set -e
  TRAVA_ID="$(printf '%s' "$TRAVA_JSON" | uv run python -c 'import json, sys; print(json.load(sys.stdin).get("id") or "")' 2>/dev/null || true)"
  case "$TRAVA_RC" in
    0)
      if uv run python -m cdp trava liberar --id "$TRAVA_ID" >/dev/null 2>&1; then
        echo "push no ramo cdp-trava: ok (trava adquirida e liberada)"
      else
        warn "a trava foi adquirida, mas não liberada: ela expira sozinha em 1 minuto."
      fi ;;
    10)
      warn "outra rotina segura a trava agora: o push no ramo cdp-trava não foi testado. Rode o script de novo fora dos horários das rotinas." ;;
    *)
      warn "o push no ramo cdp-trava falhou (rede, credencial ou regra do repositório): sem ele, a montagem, o fechamento e as notas não rodam. Confira com 'uv run python -m cdp trava ver'." ;;
  esac
fi

step "Identidade deste clone (executor local)"
if [ -f .cdp/local.yaml ]; then
  echo "já registrada (.cdp/local.yaml):"
  cat .cdp/local.yaml
else
  uv run python -m cdp executor registrar --como local-pc --harness "$HARNESS" || \
    warn "registro recusado: use um clone dedicado às rotinas, no ramo main e fora de worktree."
fi
uv run python -m cdp executor mostrar || true

if [ "$HARNESS" = "claude-code" ]; then
  step "Claude Code (plugin cdp)"
  if command -v claude >/dev/null 2>&1; then
    claude --version || true
    if [ "${CDP_SKIP_PLUGIN:-0}" != "1" ]; then
      claude plugin marketplace add "$ROOT" || warn "não foi possível registrar o marketplace (veja docs/cdp/LOCAL.md)."
      claude plugin install cdp@cdp-cabra-da-peste || warn "não foi possível instalar o plugin cdp (veja docs/cdp/LOCAL.md)."
      claude plugin list || true
    fi
  else
    warn "Claude Code CLI não encontrado no PATH. Instale o app desktop/CLI e rode:"
    echo "  claude plugin marketplace add \"$ROOT\""
    echo "  claude plugin install cdp@cdp-cabra-da-peste"
  fi
fi

step "Próximos passos (docs/cdp/LOCAL.md e docs/cdp/ROTINAS.md)"
if [ "$UV_INSTALLED" = "1" ]; then
  warn "o uv acabou de ser instalado: feche e reabra o app do Claude (ou do Codex/Antigravity): o PATH novo só vale para processos novos."
fi
cat <<TXT
1. Uma mente por vez: desligue as rotinas do CDP em qualquer outro app (nuvem do Claude Code,
   Codex, Antigravity). Este clone é só das rotinas (na main), separado do de desenvolvimento.
   O executor designado em configs/cdp/executor.yaml precisa ser local-pc.
2. Tarefas agendadas, uma por tarefa da agenda, com o id da tarefa na instrução:
     cdp-status          segundas 08:30
     cdp-semanal         dias úteis 11:07   (reservas cdp-semanal-b 12:07, cdp-semanal-c 13:07,
                                             cdp-semanal-d 14:07)
     cdp-risco-1330      dias úteis 13:30   (e cdp-risco-1603 às 16:03)
     cdp-diario          dias úteis 19:22   (reforço cdp-diario-reforco 21:07;
                                             repescagem cdp-diario-sabado sábados 10:07)
     cdp-cobertura       segunda a quinta 22:37
     cdp-calibracao      dia 1 de cada mês 09:15
   - Claude Code (app desktop): Code → Routines → New routine → Local, pasta = $ROOT, worktree
     DESLIGADO, modo "Aceitar edições", instrução = /cdp:<skill> <tarefa> (ex.:
     /cdp:diario cdp-diario-reforco). Tabela pronta:
     uv run python -m cdp rotinas exportar --alvo claude-desktop
   - Codex: uv run python -m cdp rotinas exportar --alvo codex --formato md
   - Antigravity: uv run python -m cdp rotinas exportar --alvo cron --harness agy
   Horários de Brasília: se o PC estiver em outro fuso, converta (campo pc_menos_brasilia_horas
   de 'uv run python -m cdp agenda').
3. "Run now" em cdp-status para conferir; mantenha o computador acordado nos horários.
4. Sem o app aberto: scripts/cdp_rotina.sh <tarefa> --harness <app> pelo agendador do sistema
   (uv run python -m cdp rotinas exportar --alvo cron|launchd|windows --harness <app>).
TXT
