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
- Tese de investimento da carteira decidida (depois de `weekly decide`, antes do painel):
  `docs/cdp/TESE.md`. Você escreve só `book/<semana>/tese/tese.json`, com números apenas como
  `{{fact:id}}` de `book/<semana>/tese/fatos.md`; o código valida (`validate-tese`) e publica
  (`tese publish`, imutável). Fora do clone dedicado das rotinas (desenvolvimento), entregue a
  tese como rascunho em `docs/cdp/teses/<semana>.json`; nunca grave `book/` nem publique ali.
- Painel de gestão (artifact; investimento e risco, com a tese da semana, para investidores e
  comitê de investimento): `uv run python -m cdp painel` → `artifacts/painel/` (casca
  `index.html`, estilo e script versionados, `data.json` e a cópia local `cdp_painel_local.html`);
  republique sempre no mesmo artifact cuja URL está em `artifacts/painel/ARTIFACT_URL` (nunca crie
  outro), lendo por inteiro `artifact.arquivos_para_ler` e publicando `artifact.publicar`.
- Rotinas sem supervisão: não pergunte; pare e explique no resumo. Nunca desligue o kill switch,
  nunca force push, nunca edite arquivos gravados pelo código (`.claude/settings.json` bloqueia).

Sempre registre `mind: "claude-code"` nos arquivos que escrever para o CDP. Nunca calcule números:
use os fatos (`{{fact:id}}`) gerados pelo código.
