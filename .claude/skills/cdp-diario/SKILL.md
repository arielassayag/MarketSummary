---
name: cdp-diario
description: Executa o fechamento diário do CDP — Cabra da Peste após o pregão — marcação a mercado, risco, atribuição, registro encadeado por hash, comentário do dia escrito pela mente e relatório diário. Use todo pregão às 19h20 (Brasília) ou quando pedirem o fechamento/comentário do dia do CDP.
---

Siga **exatamente** `docs/cdp/playbooks/DIARIO.md` e a metodologia `docs/cdp/METODOLOGIA.md`.

- Registre `mind: "claude-code"` no `comentario.json`.
- Números somente via `{{fact:<id>}}` de `facts.md`; tom sóbrio e institucional; sem recomendação.
- Rode `uv run python -m cdp daily publish --date <data>` e `uv run python -m cdp verify` antes do commit.
