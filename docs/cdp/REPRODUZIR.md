# Auditoria e reprodução — CDP — Cabra da Peste

O CDP — Cabra da Peste é auditável de ponta a ponta por qualquer pessoa. O código, a
configuração do mandato, os dados de mercado e os insumos públicos arquivados, os modelos de
cobertura, as decisões, os registros diários, os relatórios e a trilha de auditoria estão no
repositório público <https://github.com/arielassayag/MarketSummary>. Todo número publicado é
calculado por código testado a partir de dados públicos; a inteligência artificial escreve apenas
textos estruturados que citam esses números e é verificada pelos mesmos validadores, seja qual for
o assistente usado.

Este guia mostra como (1) verificar a integridade de tudo o que foi publicado, (2) recalcular os
modelos e a decisão da carteira a partir dos insumos arquivados, (3) coletar de novo os dados
públicos e (4) refazer cada passo da inteligência artificial com qualquer assistente — ChatGPT,
Gemini, Claude ou outro. Para conferir o portal publicado contra o repositório, veja a seção 8;
para operar a sua própria cópia do fundo, `docs/cdp/REPLICAR.md`.

## 1. O que é verificável

| Elemento | Onde está | Como verificar |
|---|---|---|
| Trilha de auditoria (eventos encadeados: gênese, decisões, execuções, registros, teses, relatórios, notas) | `book/audit_log.jsonl` | `cdp verify` (hash de cada evento e do anterior) |
| Decisões semanais (proposta, decisão, configuração do mandato vigente) | `book/<semana>/` | `cdp verify` (hashes contra a trilha); recálculo na seção 4.2 |
| Registros diários e track record | `book/track_record/` | `cdp verify` (cadeia de registros) |
| Base de mercado (preços, volumes, câmbio, fundamentos; base e incrementos diários) | `data/market/` | `cdp verify` (manifesto e sha256 de cada arquivo) |
| Insumos públicos dos modelos (demonstrações da CVM e da SEC, consenso público, composição de ETFs, juros) | `book/cobertura/<data>/insumos/` (extratos usados) e `data/publico/` (índice com URL e SHA-256 de cada coleta; os pacotes anuais da CVM e o `companyfacts` da SEC ficam fora do git — baixe-os da URL do índice) | `cdp cobertura verify` |
| Modelos de cobertura e preços-alvo de 12 meses | `book/cobertura/<data>/` e o livro `book/cobertura/livro.jsonl` | `cdp cobertura verify` (recalcula cada preço-alvo) |
| Tese de investimento, notas de pesquisa, comentários diário e semanal | `book/<semana>/tese/`, `book/cobertura/notas/`, `reports/` | sha256 na trilha; validadores da seção 5 |
| Configuração do mandato e da valuation | `configs/cdp/` e `configs/cdp/historico/<hash>.json` | hash da configuração em cada decisão |
| Metodologia | `docs/cdp/METODOLOGIA.md`, `docs/cdp/COBERTURA.md`, `docs/cdp/NOTAS.md` | leitura |

## 2. Preparar o ambiente

Pré-requisitos: Git e o gerenciador de Python `uv` (as versões exatas das bibliotecas estão
fixadas em `uv.lock`). Nenhuma chave de API ou assinatura é necessária para verificar e
recalcular.

```sh
git clone https://github.com/arielassayag/MarketSummary.git
cd MarketSummary
uv sync --extra dev
uv run python -m cdp verify
uv run python -m cdp cobertura verify
```

`verify` responde `ÍNTEGRO` ou lista cada divergência. Para conferir o ambiente que você usa
contra o registrado, rode `uv pip show numpy pandas scipy cvxpy`; cada snapshot da cobertura grava
as versões de Python, numpy, pandas e scipy em `manifest.json` (campo `ambiente`).

Uma demonstração completa e offline, com mercado sintético (DADOS SIMULADOS), roda o mesmo
caminho operacional em poucos segundos:

```sh
uv run python -m cdp demo --out /tmp/cdp-demo
```

## 3. Verificação exata (hash)

Tudo o que foi gravado é verificado byte a byte:

- cada evento da trilha guarda o sha256 do evento anterior; qualquer edição, remoção ou
  reordenação quebra a cadeia;
- cada decisão referencia os hashes da proposta, da pesquisa, da configuração e dos insumos da
  semana; cada registro diário, o do registro anterior;
- cada snapshot da cobertura tem manifesto com o sha256 de cada arquivo (insumos, configuração
  usada, modelos), selado na trilha do fundo; o livro da cobertura é encadeado;
- cada nota de pesquisa publicada tem o seu evento na trilha com o sha256 de `nota_publicada.json`
  e de `nota.md` (conferido por `cdp verify`; `cdp nota agenda` mostra `integridade_notas`).

```sh
uv run python -m cdp verify
uv run python -m cdp cobertura verify --sem-recalculo
uv run python -m cdp nota agenda
```

## 4. Recalcular a partir dos insumos arquivados (tolerância)

Números recalculados não são comparados por hash: álgebra linear e solvers de otimização convexa
podem diferir no último dígito entre versões de biblioteca, sistema e processador. A comparação é
por tolerância documentada.

### 4.1 Modelos de cobertura

```sh
uv run python -m cdp cobertura verify
```

Refaz cada modelo aberto — custo de capital, cada método de valuation, pesos, roll-forward ao
preço-alvo de 12 meses, cenários e grade de sensibilidade — a partir dos insumos públicos e da
configuração arquivados no próprio snapshot. Tolerância: 1e-5 relativo por valor (o armazenamento
guarda seis algarismos significativos). As simulações dos cenários usam semente fixa por emissor
e data: o recálculo reproduz os mesmos sorteios.

### 4.2 Decisão da carteira

A decisão de cada semana usou o código, a configuração e o estado do livro do momento da decisão.
Para recalcular, trabalhe numa cópia do repositório no commit da decisão (mensagem
"CDP: decisão da semana AAAA-MM-DD"):

```sh
git log --oneline --grep "CDP: decisão da semana"
git worktree add /tmp/cdp-copia <commit>
```

Na cópia, rode `uv sync --extra dev` e a prévia, que refaz o mesmo processo da decisão — insumos
reconstruídos e conferidos pelos hashes do manifesto da semana, sinais, modelo de risco,
otimizador e verificações de conformidade — sem gravar nada:

```sh
uv run python -m cdp --book /tmp/cdp-copia/book --market /tmp/cdp-copia/data/market --reports /tmp/cdp-copia/reports weekly preview --week AAAA-MM-DD --mind claude-code --out /tmp/previa.json
```

Compare `posicoes[].peso` de `/tmp/previa.json` com as posições de
`book/<semana>/proposal_v1.json` (a proposta aprovada). Tolerância de referência: 1e-4 do NAV por
posição (1 ponto-base) e 1e-4 relativo nas métricas de risco (vol ex-ante, beta, gross, net).
Diferenças maiores indicam versão de biblioteca ou solver diferente da fixada em `uv.lock`.

### 4.3 Tese, relatórios e painel

Os fatos e as análises da tese e dos relatórios são recalculados pelo código a partir da decisão
e dos registros gravados no momento da publicação (nunca lidos de arquivos editáveis) e o sha256
de cada arquivo publicado está na trilha. O painel é gerado só a partir do livro, da trilha e dos
relatórios (`cdp painel`); a página nunca calcula números.

## 5. Refazer os passos da inteligência artificial com qualquer assistente

A mente do fundo escreve seis tipos de texto estruturado: pesquisa da semana, decisão do gestor
(juízos ordinais: regime, postura, visões e exclusões), tese de investimento, nota de pesquisa
por emissor, comentário do resultado do dia e comentário semanal. Em todos, números só como
`{{fact:<id>}}` calculados pelo código. Qualquer assistente refaz qualquer passo:

1. O código prepara os fatos da etapa (na sua cópia do livro; nada vai para o livro oficial).
2. `cdp mente pacote` exporta **um único arquivo markdown autocontido**: papel, regras
   invioláveis, guia de estilo (`docs/cdp/ESTILO.md`), os fatos do código, o JSON Schema, um
   esqueleto de exemplo e o comando exato de validação. O pacote vai para fora do repositório
   (por exemplo `/tmp/…`) ou para `outputs/` (pasta ignorada pelo git); o comando só substitui um
   pacote gerado antes.
3. Você cola o pacote no assistente e salva a resposta (só o objeto JSON) no caminho indicado.
4. O validador da CLI — o mesmo das rotinas — aceita ou lista apontamentos precisos (número fora
   de placeholder, fato inexistente, evidência inválida, data posterior, marcação, injeção de
   instruções, guia de estilo). Cole os apontamentos no assistente e repita até a validação passar.

| Etapa | Fatos (código) | Pacote | Validação |
|---|---|---|---|
| Pesquisa da semana | `weekly prepare` | `--etapa pesquisa --semana D` | `validate --week D --mind M --so-pesquisa` |
| Decisão do gestor | `weekly prepare` e a pesquisa salva | `--etapa decisao --semana D` | `validate --week D --mind M` |
| Tese de investimento | `tese prepare --week D` | `--etapa tese --semana D` | `validate-tese --week D` |
| Nota por emissor | `nota prepare --issuer IID --date D` | `--etapa nota --emissor IID --data D` | `validate-nota --issuer IID --date D` |
| Comentário do dia | `daily close --date D` | `--etapa comentario-diario --data D` | `validate-daily --date D` |
| Comentário semanal | `weekly close-report --date D` | `--etapa comentario-semanal --data D` | `validate-weekly-report --date D` |

A pesquisa vem antes da decisão: a decisão cita os ids das notas da pesquisa, então uma pesquisa
nova invalida a decisão gravada antes dela. Valide a pesquisa sozinha (`--so-pesquisa`), depois
exporte o pacote da decisão — que traz um resumo da pesquisa salva — e valide a semana inteira.

**Tamanho e janela de contexto.** Cada pacote informa o tamanho estimado em tokens (também na
saída do comando, `tokens_estimados`; `alerta_tamanho` acima de 150 mil). Os pacotes de nota e de
comentário cabem em qualquer assistente atual; os da semana (pesquisa, decisão e tese) pedem
janela de contexto ampla — use um assistente com janela maior que o tamanho informado ou anexe o
arquivo do pacote em vez de colá-lo. O pacote da decisão resume a pesquisa gravada (id citável,
visão, tese resumida, catalisadores, riscos e sentinela de squeeze de cada nota); com anexos, junte
também `research_pack.json` para o texto integral e as evidências.

Exemplo — a tese de uma semana, refeita no ChatGPT numa cópia do livro:

```sh
uv run python -m cdp --book /tmp/cdp-copia/book mente pacote --etapa tese --semana AAAA-MM-DD --mente chatgpt --saida /tmp/pacote_tese.md
uv run python -m cdp --book /tmp/cdp-copia/book validate-tese --week AAAA-MM-DD
```

Exemplo — a nota de um emissor, no Gemini:

```sh
uv run python -m cdp --book /tmp/cdp-copia/book nota prepare --issuer BR_VALE --date AAAA-MM-DD
uv run python -m cdp --book /tmp/cdp-copia/book mente pacote --etapa nota --emissor BR_VALE --data AAAA-MM-DD --mente gemini --saida /tmp/pacote_nota.md
uv run python -m cdp --book /tmp/cdp-copia/book validate-nota --issuer BR_VALE --date AAAA-MM-DD
```

O campo `mind` registra o assistente (`claude-code`, `codex`, `chatgpt`, `gemini` ou `outro`); o
campo opcional `modelo_ia` da nota registra o modelo usado. Textos de assistentes diferentes
nunca mudam um número: o preço-alvo, os pesos e o risco continuam do código. Como juízos de
assistentes diferentes podem divergir, a reprodução de um texto não é idêntica byte a byte; o que
se reproduz é o processo, as regras e a validação.

## 6. Coletar de novo os dados públicos

Os arquivos arquivados são os insumos oficiais. Para conferir que vieram das fontes públicas,
colete de novo numa pasta separada e compare:

```sh
uv run python -m cdp --market /tmp/cdp-mercado fetch-base --as-of AAAA-MM-DD
uv run python -m cdp --book /tmp/cdp-vazio/book --market /tmp/cdp-mercado cobertura run --date AAAA-MM-DD --raiz /tmp/cdp-publico
```

Fornecedores revisam séries (ajustes por proventos, reapresentações de demonstrações), então a
coleta nova pode diferir em bytes; compare valores com tolerância e confira datas de publicação
— os insumos usados num modelo nunca têm data de publicação posterior à data do modelo.

## 7. De onde vem cada dado público

| Dado | Fonte pública |
|---|---|
| Preços, volumes, câmbio, fundamentos de mercado e consenso público de analistas | Yahoo Finance (finance.yahoo.com), coletado pela biblioteca aberta yfinance; o consenso é rotulado "consenso público Yahoo Finance" |
| Demonstrações financeiras de emissores brasileiros (DFP, ITR, FRE) e fatos relevantes (IPE) | CVM — dados abertos (dados.cvm.gov.br) e RAD |
| Demonstrações e documentos de emissores registrados nos EUA (20-F, 6-K, 10-K; XBRL) | SEC EDGAR (www.sec.gov, data.sec.gov) |
| Aluguel de ações e cadastro de empresas listadas | B3 (arquivos públicos da B3) |
| Short interest nos EUA | FINRA (dados públicos) |
| Juros, inflação e expectativas (Focus) no Brasil | Banco Central do Brasil (SGS e Olinda) |
| Juros e câmbio no México | Banxico |
| Juros dos EUA | FRED (Federal Reserve Bank of St. Louis) |
| Composição de ETFs | arquivos públicos dos emissores (iShares, Global X) |
| Prêmios de risco por país, prêmio de risco de mercado e betas setoriais | Damodaran Online (NYU Stern), datados na configuração |
| Calendário de pregões | biblioteca aberta exchange_calendars, com horários de fechamento verificados |
| Notícias | feeds públicos de notícias, tratados como dado não confiável |
| Notas de pesquisa | apenas fontes públicas citadas com URL e data (`docs/cdp/NOTAS.md`) |

Nenhum dado pago, de acesso restrito ou de conector proprietário entra em qualquer modelo ou
texto do fundo.

## 8. Conferir o portal e operar a sua cópia

- **O portal publicado corresponde ao repositório?** O site traz `manifest.json` (com o commit de
  origem, `source_commit`) e `SHA256SUMS` com o sha256 de cada arquivo publicado. O passo a passo
  está em `docs/cdp/SITE.md`, seção "Conferir uma publicação".
- **Operar a sua própria cópia** — fork, configuração, escolha do app de IA (Claude Code, Codex,
  Gemini ou outro), agenda das rotinas e portal próprio: `docs/cdp/REPLICAR.md`. As rotinas rodam
  dentro do app de IA, com o mesmo roteiro em qualquer um (`docs/cdp/ROTINAS.md`).

## Conferências documentais delimitadas

O [estudo Enel Chile, Klabin e Rumo de 09/10/2026](estudos/2026-10-09-enel-klabin-rumo/README.md)
vincula recortes primários, recibos declarados e localizadores a um leitor de
corpos fornecidos pelo terceiro. Ele preserva DVA original/comparativa e errata
externa da autoria. Reproduz contas delimitadas sem coleta, cache operacional ou
modelo; ROU permanece condicional, giro misto e dívida Enel não comprovada continuam
visíveis. Sua conferência técnica não certifica financeiros completos, PIT ou P0.
