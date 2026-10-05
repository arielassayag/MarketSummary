# Instruções para Claude Code

@AGENTS.md

## CDP — Cabra da Peste

Você pode ser a "mente" do CDP (alternando com o Codex). A metodologia é perene e não depende do harness:

- Metodologia: `docs/cdp/METODOLOGIA.md`
- Roteiro semanal (primeiro pregão da semana na B3): `docs/cdp/playbooks/SEMANAL.md` — skill `cdp-semanal`
- Roteiro diário (fechamento): `docs/cdp/playbooks/DIARIO.md` — skill `cdp-diario`
- PC local: plugin `cdp` deste repositório (marketplace `cdp-cabra-da-peste`), skills
  `/cdp:semanal`, `/cdp:diario`, `/cdp:risco`, `/cdp:status` e `/cdp:calibracao`, disparadas por
  tarefas agendadas do app desktop — guia completo em `docs/cdp/LOCAL.md`. As skills do projeto
  `cdp-semanal`/`cdp-diario` delegam para o plugin quando ele está instalado.
- Painel (artifact): `uv run python -m cdp painel` → `artifacts/painel/cdp_painel.html`; republique
  sempre no mesmo artifact cuja URL está em `artifacts/painel/ARTIFACT_URL` (nunca crie outro).
- Rotinas sem supervisão: não pergunte; pare e explique no resumo. Nunca desligue o kill switch,
  nunca force push, nunca edite arquivos gravados pelo código (`.claude/settings.json` bloqueia).

Sempre registre `mind: "claude-code"` nos arquivos que escrever para o CDP. Nunca calcule números:
use os fatos (`{{fact:id}}`) gerados pelo código.
