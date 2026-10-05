# Rascunhos da tese de investimento entregues fora do clone das rotinas

Esta pasta guarda teses da carteira escritas **fora** do clone dedicado das rotinas (sessão de
desenvolvimento, sessão manual). O livro oficial (`book/`) tem um único escritor, o clone das
rotinas: uma tese gravada em `book/` noutro clone pararia a sincronização de todas as rotinas, e
um `tese publish` fora dele separaria a trilha encadeada por hash. Regras completas:
`docs/cdp/TESE.md`, seção "Rascunho entregue fora do clone das rotinas".

- **Nome**: `<semana>.json`, com a semana da decisão em AAAA-MM-DD (ex.: `2026-10-05.json`).
- **Conteúdo**: o mesmo schema de `book/<semana>/tese/tese.json` (`docs/cdp/TESE.md`, seção 6),
  com `week` igual ao nome do arquivo e `mind` de quem escreveu. Números só como `{{fact:id}}`;
  datas só como 2026-10-25, 25/10/2026 ou "25 de outubro".
- **Uso pela rotina**: `uv run python -m cdp tese prepare --week AAAA-MM-DD` copia o rascunho
  byte a byte para `book/<semana>/tese/tese.json` quando esse arquivo ainda não existe
  (`rascunho_adotado: true`); nunca sobrescreve nem publica. A mente roda `validate-tese` primeiro
  e só reescreve se o rascunho for inválido; depois, `tese publish`.
- **Escrita**: valide numa cópia do livro (`--book`/`--reports` apontando para a cópia) antes de
  fazer commit; aqui entra só o JSON. Nunca faça commit de `book/` nem rode `tese publish` fora
  do clone das rotinas. As rotinas nunca editam esta pasta.
