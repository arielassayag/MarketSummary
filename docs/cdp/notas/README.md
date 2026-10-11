# Rascunhos de notas de pesquisa entregues fora do clone das rotinas

O livro (`book/`) tem um único escritor: o clone que roda as rotinas. Uma nota de pesquisa
escrita em outro lugar — uma sessão de desenvolvimento, o Codex, ou qualquer assistente com o
pacote de `cdp mente pacote` — chega aqui como rascunho versionado:

```
docs/cdp/notas/<IID>/<AAAA-MM-DD>.json
```

com o mesmo schema de `book/cobertura/notas/<IID>/<data>/nota.json` (`NotaEmpresa`,
`docs/cdp/NOTAS.md`) e `"mind"` preenchido (`claude-code`, `codex`, `chatgpt`, `gemini` ou
`outro`).

- `cdp nota agenda` põe todo rascunho com data até hoje e ainda não publicado na frente da fila
  (`data_nota` = a data do rascunho; um rascunho por emissor por execução) e o lista em
  `rascunhos_pendentes`; a rotina `cdp-cobertura` roda `nota prepare` nessa data e adota o
  rascunho quando a nota ainda não tem `nota.json`: copia byte a byte (`rascunho_adotado:
  true`), nunca sobrescreve um `nota.json` existente e nunca publica. A mente roda
  `validate-nota` antes de escrever qualquer coisa: `ok: true` ⇒ publica sem reescrever; senão
  corrige só a cópia no livro.
- A validação usa o FactBook calculado pelo código **da própria rotina** na data da nota: um
  rascunho com fato inexistente, número livre ou fonte inválida não passa.
- A data do arquivo é a data da nota; um rascunho para uma data já publicada é ignorado, e um
  rascunho com data anterior à última nota publicada do emissor fica obsoleto
  (`rascunhos_obsoletos` em `nota agenda`; nunca é adotado). Rascunho com data futura espera a
  data chegar.
- Nunca faça commit de `book/` fora do clone das rotinas (a sincronização de todas as rotinas
  pararia) e nunca edite esta pasta a partir do clone das rotinas.

Fluxo para escrever o rascunho com qualquer assistente (fatos preparados numa cópia do livro):

```sh
uv run python -m cdp --book /tmp/cdp-copia/book nota prepare --issuer IID --date AAAA-MM-DD
uv run python -m cdp --book /tmp/cdp-copia/book mente pacote --etapa nota --emissor IID --data AAAA-MM-DD --saida /tmp/pacote_nota.md
uv run python -m cdp --book /tmp/cdp-copia/book validate-nota --issuer IID --date AAAA-MM-DD
```

Depois de `ok: true`, copie `book/cobertura/notas/<IID>/<data>/nota.json` da cópia para
`docs/cdp/notas/<IID>/<AAAA-MM-DD>.json` e faça commit só desse arquivo.

## Estudos de ETFs entregues em 11/10/2026

Os diretórios `ETF_ARGT`, `ETF_BOVA11`, `ETF_COLO`, `ETF_ECH`, `ETF_EPU`, `ETF_EWW`,
`ETF_EWZ` e `ETF_ILF` contêm rascunhos de iniciação. Cada estudo reúne hipótese de
investimento, condição decisiva, contraponto, cenários qualitativos, riscos, interpretação
do modelo, produto, exposição, custos, aderência ao índice e acompanhamento. Os documentos
preservam as lacunas de prospecto, replicação e negociação; visão neutra não equivale a
recomendação nem a diligência concluída. Fontes públicas dos administradores foram
consultadas na data da nota; data de consulta não é data de publicação.

A extensão de notas aceita o produto somente com identidade e modelo íntegros no retrato,
na fila existente e no mesmo limite de execução. Verificação de desenvolvimento não é
publicação: o executor continua responsável pela adoção, validação e trilha imutável.
