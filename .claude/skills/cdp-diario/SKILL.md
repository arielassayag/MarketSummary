---
name: cdp-diario
description: Atalho do projeto para o fechamento diário do CDP — Cabra da Peste após o pregão (19h20 de Brasília) — marcação, risco, atribuição, registro encadeado por hash, comentário da mente e relatório diário. Com o plugin `cdp` instalado (PC local), delega para a skill `cdp:diario`; sem o plugin (nuvem, Codex), segue o roteiro perene docs/cdp/playbooks/DIARIO.md. Use todo pregão ou quando pedirem o fechamento/comentário do dia do CDP.
---

Fonte única do procedimento:

1. **Plugin `cdp` disponível nesta sessão** (PC local, ver `docs/cdp/LOCAL.md`): invoque a skill
   `cdp:diario` e siga-a integralmente. Não execute os passos abaixo em duplicidade.
2. **Sem o plugin** (sessão na nuvem, Codex ou outro harness): siga **exatamente**
   `docs/cdp/playbooks/DIARIO.md` e a metodologia `docs/cdp/METODOLOGIA.md`.

Em ambos os casos:

- Registre `mind: "claude-code"` no `comentario.json` (`codex` se for o Codex).
- Números somente via `{{fact:<id>}}` de `facts.md`; tom sóbrio e institucional; sem recomendação.
- Valide com `uv run python -m cdp validate-daily --date AAAA-MM-DD` antes de
  `uv run python -m cdp daily publish --date AAAA-MM-DD` (a publicação é imutável) e rode
  `uv run python -m cdp verify` antes do commit.
- Se `cdp agenda` listar a semana corrente em `teses_pendentes`, conclua a tese de investimento
  antes do painel, como no roteiro semanal (`docs/cdp/TESE.md`; com `rascunho_adotado: true` no
  `tese prepare`, `validate-tese` antes de escrever qualquer coisa); semanas anteriores, só relate.
- Sempre rode `verify` antes do painel, mesmo se a tese falhou; push só se esse `verify` disser
  `ÍNTEGRO`.
