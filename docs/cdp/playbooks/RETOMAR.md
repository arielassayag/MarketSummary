# Roteiro para retomar — pegar o bonde andando (qualquer harness)

Use ao abrir uma sessão neste repositório sem saber o que está acontecendo — numa rotina, numa
conversa com o operador ou no meio de um desenvolvimento. O manual canônico é `AGENTS.md`; este
roteiro é a sua seção 1 em passos.

## 1. Estado

```sh
uv sync --extra dev --extra ai
uv run python -m cdp estado --formato md
```

Leia, nesta ordem: **incidentes** (severidade alta primeiro), **fase** do fundo, **executor**
(`sou_o_executor`: este ambiente grava o livro?), **pendências**, **próximas rotinas** e o
**próximo passo** (`playbook_sugerido`). Com rede, acrescente `--rede` (remoto, trava e portal).

## 2. Papel

| Situação | O que fazer |
|---|---|
| O prompt cita uma tarefa `cdp-…` (rotina agendada) | A skill da tarefa (`.agents/skills/cdp-…`): `uv run python -m cdp rotinas gate --tarefa cdp-diario --adquirir` (com a tarefa certa), sem perguntar nada |
| Uma pessoa pede algo da operação (sessão de operador) | Leitura por padrão. Grave o livro só se `sou_o_executor` for verdadeiro e a pessoa pedir, rodando o roteiro da tarefa com `--manual` no gate |
| Desenvolvimento (código, documentação, testes) | Nunca grave `book/`, `data/`, `reports/`, `artifacts/`; nunca rode `publish`, `decide` ou `reinicio`. Leia `docs/cdp/EM_ANDAMENTO.md` e `docs/cdp/DECISOES.md` |

## 3. Desenvolvimento: continuidade entre harnesses

1. `docs/cdp/EM_ANDAMENTO.md` — frentes abertas, próximos passos e riscos. Continue de lá.
2. `docs/cdp/DECISOES.md` — decisões já tomadas (não reabra sem motivo novo).
3. Antes de encerrar, atualize `docs/cdp/EM_ANDAMENTO.md` (o que mudou, o que falta, riscos).
   Um fato que outra sessão precisa saber vai para um arquivo do repositório — nunca só para a
   memória de um harness, um rascunho fora do repositório ou a conversa.
4. Mudou `configs/cdp/rotinas.yaml`: `uv run python -m cdp rotinas verificar` e
   `uv run python -m cdp skills sincronizar`. Antes de propor um commit:
   `uv run pytest tests/cdp -q` e `uv run ruff check .`.

## 4. Operador: tarefas comuns

- Rodar uma rotina fora do horário (só no executor): o roteiro da tarefa, com
  `uv run python -m cdp rotinas gate --tarefa cdp-diario --manual --adquirir`.
- Trocar o executor (por exemplo, do PC para a nuvem): `docs/cdp/AUTOMACAO.md`, seção "Troca de
  executor"; confira a janela com `uv run python -m cdp executor janela`.
- Kill switch: só um humano desliga (`docs/cdp/LOCAL.md`).
