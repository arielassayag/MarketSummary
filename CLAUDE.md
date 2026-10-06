# Instruções para Claude Code

@AGENTS.md

## Só para o Claude Code

O manual é o `AGENTS.md` acima (vale para qualquer harness). Aqui, só o que é específico do
Claude Code:

- Comece pela seção 1 do `AGENTS.md`: `uv run python -m cdp estado --formato md`. Use
  `--mind claude-code` e `"mind": "claude-code"` nos arquivos que escrever para o CDP.
- Skills: as skills neutras ficam em `.agents/skills/cdp-*` (geradas por
  `uv run python -m cdp skills sincronizar`; não edite à mão). O plugin `cdp` (`plugins/cdp`,
  marketplace `cdp-cabra-da-peste`) serve às tarefas agendadas do app desktop no PC local
  (`docs/cdp/LOCAL.md`); o espelho das skills do projeto fica em `.claude/skills/`.
- Rotina na nuvem (claude.ai/code): o plugin não existe ali; siga o prompt da rotina, a skill
  do projeto e o roteiro. Nunca publique artifacts numa rotina; push só por `cdp publicar`
  (ramo `main`, com `--trava` e `--execucao` do gate). O gate devolve os trailers de
  procedência do commit, inclusive o link desta sessão.
- Sessão interativa na nuvem: abra no ambiente Default (ou "CDP-dev"), nunca no "CDP" — esse
  tem `CDP_EXECUTOR` e é só das rotinas; `cdp estado` avisa se a sessão estiver nele.
- O painel no artifact (`artifacts/painel/ARTIFACT_URL`) é um espelho privado opcional, só em
  sessão interativa; o portal público é o GitHub Pages (`docs/cdp/SITE.md`).
- Tese escrita fora do clone das rotinas: rascunho em `docs/cdp/teses/<semana>.json`; nunca
  grave `book/` nem publique fora do executor.
- `.claude/settings.json` nega force push, apagar o livro, desligar o kill switch e editar
  arquivos gravados pelo código; não contorne. Memórias do Claude não substituem o repositório:
  fatos que outra sessão precisa saber vão para `docs/cdp/EM_ANDAMENTO.md` ou
  `docs/cdp/DECISOES.md`.
