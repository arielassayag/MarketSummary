#!/usr/bin/env bash
# CDP — Cabra da Peste: preparação do PC local (macOS/Linux).
#
# Uso (na raiz do clone ou de qualquer pasta):
#   bash scripts/cdp_setup_local.sh
# Variáveis opcionais:
#   CDP_SKIP_PLUGIN=1   não registra o marketplace nem instala o plugin `cdp` no Claude Code
#   CDP_SKIP_TESTS=1    pula o teste rápido offline
#
# O que faz: confere git, instala o uv (instalador oficial) se faltar, sincroniza o ambiente,
# roda `cdp status`, `cdp agenda` e `cdp verify`, um teste offline (DADOS SIMULADOS), registra o
# marketplace do repositório e instala o plugin `cdp` (se o Claude Code CLI estiver no PATH) e
# imprime os próximos passos. Não altera o livro, a trilha nem os dados.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONUTF8=1

step() { printf '\n== %s\n' "$*"; }
warn() { printf 'AVISO: %s\n' "$*" >&2; }

step "CDP — Cabra da Peste: preparação local em $ROOT"
[ -f pyproject.toml ] && [ -d src/cdp ] || { echo "Pasta inesperada: rode a partir do clone do repositório." >&2; exit 1; }

step "git"
command -v git >/dev/null 2>&1 || { echo "git não encontrado: instale o git e rode de novo." >&2; exit 1; }
git --version
echo "branch: $(git branch --show-current 2>/dev/null || echo "?")"
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

step "Acesso de escrita ao GitHub (git push --dry-run)"
if ! git push --dry-run >/dev/null 2>&1; then
  warn "git push --dry-run falhou: configure a autenticação (gh auth login, chave SSH ou gerenciador de credenciais) e um upstream (git push -u origin main)."
else
  echo "ok"
fi

step "Claude Code"
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

step "Próximos passos (docs/cdp/LOCAL.md)"
if [ "$UV_INSTALLED" = "1" ]; then
  warn "o uv acabou de ser instalado: feche e reabra o app do Claude (o PATH novo só vale para processos novos)."
fi
cat <<EOF
1. Desative as rotinas do CDP na nuvem, se existirem (duas mentes não podem gravar o mesmo livro).
   Use um clone só para as rotinas (na main), separado do clone de desenvolvimento.
2. No app desktop do Claude: Code → Routines → New routine → Local, pasta = $ROOT,
   worktree DESLIGADO, modo de permissão "Accept edits" (Aceitar edições), e crie:
     cdp-status          segundas 08:30     instruções: /cdp:status
     cdp-semanal         dias úteis 11:07   instruções: /cdp:semanal
     cdp-semanal-b       dias úteis 12:07   instruções: /cdp:semanal   (reserva)
     cdp-semanal-c       dias úteis 13:07   instruções: /cdp:semanal   (reserva)
     cdp-risco-1330      dias úteis 13:30   instruções: /cdp:risco
     cdp-semanal-d       dias úteis 14:07   instruções: /cdp:semanal   (reserva)
     cdp-risco-1600      dias úteis 16:00   instruções: /cdp:risco
     cdp-diario          dias úteis 19:22   instruções: /cdp:diario
     cdp-diario-reforco  dias úteis 21:07   instruções: /cdp:diario
     cdp-cobertura       seg a qui 21:30    instruções: /cdp:cobertura
     cdp-calibracao      mensal, dia 1, 09:15  instruções: /cdp:calibracao
   Horários de Brasília: se o PC estiver em outro fuso, converta (campo
   pc_menos_brasilia_horas de 'uv run python -m cdp agenda').
3. Clique em "Run now" em cdp-status e em cdp-risco-1330 e responda "always allow" a cada pedido
   de permissão; ative "Keep computer awake".
4. Sem o app aberto? Use scripts/cdp_run_task.sh com cron/launchd (exemplos em docs/cdp/LOCAL.md).
EOF
