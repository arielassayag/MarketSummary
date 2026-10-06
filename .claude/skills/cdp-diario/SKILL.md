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

- Se `cdp agenda` trouxer `reinicio.pendente: true`, antes de qualquer outra etapa rode
  `uv run python -m cdp reinicio --executar`, `verify` (`ÍNTEGRO`) e o commit
  "CDP: pré-início — carteira inaugural em DD/MM/AAAA" (`book`, `reports` e, se listado,
  `pesquisa`). Com `fase: "pre_inicio"` não há fechamento nem relatório:
  `uv run python -m cdp daily close --date AAAA-MM-DD` (data de hoje) só atualiza a base de
  mercado; depois `verify` e painel.
- Registre `mind: "claude-code"` no `comentario.json` (`codex` se for o Codex).
- Números somente via `{{fact:<id>}}` de `facts.md`; tom sóbrio e institucional; sem recomendação.
- Valide com `uv run python -m cdp validate-daily --date AAAA-MM-DD` antes de
  `uv run python -m cdp daily publish --date AAAA-MM-DD` (a publicação é imutável) e rode
  `uv run python -m cdp verify` antes do commit.
- Se `cdp agenda` listar a semana corrente em `teses_pendentes`, conclua a tese de investimento
  antes do painel, como no roteiro semanal (`docs/cdp/TESE.md`; com `rascunho_adotado: true` no
  `tese prepare`, `validate-tese` antes de escrever qualquer coisa); semanas anteriores, só relate.
- Na noite do dia de montagem, com `relatorio_semanal.pendente: true` em `cdp agenda`:
  `uv run python -m cdp weekly close-report --date AAAA-MM-DD`, leia
  `reports/semanal/<data>/fatos.md`, escreva `reports/semanal/<data>/comentario.json` (mudanças da
  carteira, resultado e atribuição da semana e desde o início; números só via `{{fact:<id>}}`),
  `uv run python -m cdp validate-weekly-report --date AAAA-MM-DD` e
  `uv run python -m cdp weekly close-report --date AAAA-MM-DD --publish`. Com
  `cobertura.snapshot_pendente: true`: `uv run python -m cdp cobertura run --date AAAA-MM-DD`
  (data de `cobertura.data`).
- Sempre rode `verify` antes do painel, mesmo se a tese falhou; push só se esse `verify` disser
  `ÍNTEGRO`.
