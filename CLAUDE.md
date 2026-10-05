# Instruções para Claude Code

@AGENTS.md

## CDP — Cabra da Peste

Você pode ser a "mente" do CDP (alternando com o Codex). A metodologia é perene e não depende do harness:

- Metodologia: `docs/cdp/METODOLOGIA.md`
- Roteiro semanal (primeiro pregão da semana na B3): `docs/cdp/playbooks/SEMANAL.md` — skill `cdp-semanal`
- Roteiro diário (fechamento): `docs/cdp/playbooks/DIARIO.md` — skill `cdp-diario`

Sempre registre `mind: "claude-code"` nos arquivos que escrever para o CDP. Nunca calcule números:
use os fatos (`{{fact:id}}`) gerados pelo código.
