# Portal público do CDP — GitHub Pages

O portal do CDP é um site estático publicado de graça no **GitHub Pages**, montado pelo
**GitHub Actions** a partir do próprio repositório público, a cada gravação das rotinas em `main`:

**https://arielassayag.github.io/MarketSummary/**

## Por que GitHub Pages

| Critério | GitHub Pages (escolhido) |
|---|---|
| Custo | zero para repositório público (Pages e Actions) |
| Conta extra | nenhuma além do GitHub; implantação por OIDC, sem segredo |
| Automação | `push` em `main` → workflow `cdp-site` → portal no ar em poucos minutos |
| Independência de harness | o portal sai do repositório, qualquer que seja o agente que gravou |
| Replicação | quem faz fork liga o Pages e tem o próprio portal (`docs/cdp/REPLICAR.md`) |
| Limites | site até 1 GB e 100 GB/mês de tráfego (o portal tem poucos MB) |

Alternativas avaliadas: Cloudflare Workers (bom espelho, mas exige conta e segredos), Netlify
(teto de implantações por mês), Vercel (uso não comercial), Firebase e Render (tráfego baixo). O
artifact do claude.ai continua como espelho privado opcional, nunca publicado por rotinas.

## O que o portal publica

- **Painel** (`index.html` + `data.json` no perfil `site`, mais os módulos e os dados da
  cobertura): o portal principal do fundo, sem os cortes de texto e de colunas do espelho
  privado — a trilha de auditoria recente, o monitor de risco, as notas de calibração, todas as
  colunas das posições (sinal, beta, escore de squeeze, prazo de liquidação, participação no
  volume), as ordens, todas as verificações de conformidade, os pontos a favor e contra da
  pesquisa, as teses e a formulação completa de cada decisão. Ficam de fora os campos técnicos
  (códigos de verificação, nomes das ferramentas de IA), os **resultados da carteira de
  referência** (sombra/desafiante: série, comparação diária, desempenho relativo, quadros e
  eventos da trilha) e o histórico de mudanças de metodologia; o custo de cada restrição
  (preço-sombra) é publicado.
- **Tamanho do `data.json`** (lido inteiro antes da primeira pintura, também no celular): o que
  cresce com o tempo fica limitado — as 8 semanas mais recentes em detalhe (as anteriores numa
  linha, com o link para o registro completo nos dados abertos), dois anos de pregões em linhas
  diárias (os meses anteriores consolidados no fim do mês), os 60 relatórios diários mais
  recentes com o comentário (todos os relatórios no índice, com o texto completo em
  `dados/relatorios/`), os 500 eventos mais recentes da trilha (a trilha inteira em
  `dados/livro/audit_log.jsonl`) e as notas por emissor completas só na semana da carteira
  vigente. Orçamento de referência: 3 MB com dois anos de operação (teste).
- **Abas** (dez): Visão geral · Tese · Carteira · Cobertura de ativos · Risco · Performance ·
  Comitê · Relatórios · Pesquisa quantitativa · Mandato e metodologia. Endereços diretos:
  `#<aba>`, `#cobertura:<emissor>` (ficha do ativo, ex.: `#cobertura:BR_VALE`) e `#auditoria`
  (seção "Auditoria e reprodução" do Mandato).
- **Modelo aberto da carteira**, montado em Python (`modelo` em `data.json`; a página só exibe):
  - *Mandato e metodologia*: cronograma (dia de montagem, prazo da decisão, leilão de fechamento,
    capacidade por linha, mercados fechados, fechamentos oficiais do próximo dia de montagem),
    construção (neutralização em camadas, meta de risco específico e piso, κ_F, objetivo,
    dimensionamento, limites operacionais e do mandato), gestão de risco (escada de drawdown,
    stops de squeeze, modo somente redução de risco, gatilhos diários, estresse, liquidez, vetos
    de short), fontes públicas com links, fase vigente de adoção de IA e a seção **Auditoria e
    reprodução** (resultado da verificação — "Registro íntegro — N eventos conferidos" —, o que é
    publicado, como conferir, os arquivos da semana para baixar — carteira, ordens, decisão,
    proposta com a formulação, tese, verificação da publicação, mandato, trilha e códigos de
    verificação, lidos do catálogo `dados/datapackage.json` —, links para os documentos, a
    configuração e os módulos do código no repositório público **fixados na versão que gerou a
    publicação** e o roteiro de reprodução com qualquer assistente de IA);
  - *Antes da ativação do mandato* (configuração com o cronograma anterior): o portal publica só
    a data da carteira inaugural, executada no leilão de fechamento do dia — nada do cronograma
    recorrente, da convenção de execução nem da fração fatorial da configuração anterior, e
    nenhum backtest de outro calendário de montagem;
  - *Controle de perdas*: os níveis, gatilhos e ações em um só texto de Python, o mesmo no Mandato
    e na aba Risco (escada sobre a volatilidade ex-ante com o mandato ativado);
  - *Risco*: decomposição da variância por grupo nos modelos de decisão e base, κ_F, meta e piso,
    custo da neutralização, série diária do risco específico (ex-ante, realizado e sem modelo) e os
    parâmetros e fatores do modelo de risco;
  - *Carteira*: dimensionamento e execução por posição (alpha, sinal, contribuição ao risco, teto
    que limita e a sua origem, ordem, capacidade do fechamento usada, fechamentos), emissores sem
    pregão local e vetos de short;
  - *Comitê*: a formulação resolvida do otimizador — objetivo com cada termo, parâmetros da
    resolução (com a conta da meta de volatilidade da semana: mandato → postura → viés a priori)
    e cada restrição com limite, valor atingido, folga, se vincula e o **custo da restrição**
    (preço-sombra em pontos-base por ano do PL por 1% de folga no limite); os grupos abrem com as
    restrições que vinculam e um botão para o grupo inteiro (no celular, todos fechados);
  - rótulos de fatores e restrições em pt-BR montados em Python (`meta.rotulos`): nenhum código
    interno aparece na página.
- **Cobertura de ativos**: aba carregada sob demanda (`painel-<versão>-cobertura.js`) que lê os
  arquivos `cobertura*.json` ao lado da página — universo, tabela de cobertura, ficha do ativo
  com o modelo aberto (memória de cálculo, insumos com fonte e data, cenários, sensibilidade),
  histórico de acertos e metodologia de avaliação.
- **Antes da carteira inaugural**: cada aba da carteira mostra um aviso institucional com a data
  da carteira inaugural; Mandato e metodologia, Cobertura de ativos e Pesquisa quantitativa já
  ficam completos.
- **Relatórios**: o índice traz todos; o texto completo de cada relatório abre a partir da aba
  ("Ler o relatório completo"), direto dos dados abertos da mesma publicação.
- **Backtests**: só os da metodologia em vigor (calendário de rebalanceamento atual de
  `configs/cdp/fund.yaml`, e nunca o de montagem na segunda-feira); calibrações de metodologia
  substituída ficam só no repositório.
- **Dados abertos e auditoria** (`dados/`): cópias fiéis dos arquivos do livro, dos relatórios,
  dos modelos de cobertura e do mandato — nada é recalculado na montagem do site —, com tamanho e
  código de verificação (SHA-256) de cada arquivo, link para a origem no repositório na mesma
  versão, catálogo `dados/datapackage.json` (Frictionless Data Package) e a página
  `dados/index.html`.
- **Procedência**: `manifest.json` (versão do repositório, instante, verificação de integridade,
  SHA-256 de cada arquivo) e `SHA256SUMS` (seção "Conferir uma publicação").
- **Descoberta**: título e descrição em pt-BR, Open Graph com imagem (`site/og.png`), dados
  estruturados schema.org (`WebSite` e `Dataset`), `sitemap.xml` e página 404. Num site de
  projeto do Pages (`usuario.github.io/repositorio/`), os buscadores só leem o `robots.txt` da
  raiz do domínio: o `robots.txt` do portal não tem efeito, e o `sitemap.xml` precisa ser
  enviado no Google Search Console (ou use um domínio próprio, em que o `robots.txt` fica na
  raiz).
- **Aviso legal fixo** (`configs/cdp/site.yaml`): carteira simulada, não é fundo registrado nem
  oferta ou recomendação.

## Garantias

- O workflow só **lê** o repositório (`contents: read`); a escrita no Pages usa o ambiente
  `github-pages`.
- O site não é montado com o livro aguardando a abertura na data de início do mandato (o workflow
  pula a publicação) e não é publicado com `cdp verify` falhando (o workflow falha).
- Montagem determinística por versão do repositório: dois builds da mesma versão geram os mesmos
  arquivos.
- Depois de publicar, o workflow confere no ar que `manifest.json` traz a versão que acabou de ser
  publicada.
- A demonstração (`--demo`) é marcada "DADOS SIMULADOS" em todas as páginas, leva `noindex` nas
  páginas HTML e **nunca vai ao endereço público**: no workflow, a opção de demonstração só
  monta o site como artefato `github-pages` da execução (baixe e abra localmente).

## Conferir uma publicação

Qualquer pessoa confere o portal publicado contra o repositório público:

```sh
git clone https://github.com/arielassayag/MarketSummary.git
cd MarketSummary
git checkout <source_commit do manifest.json>
uv sync
uv run python -m cdp verify
```

Na pasta do portal baixado (por exemplo, o artefato do workflow), `sha256sum -c SHA256SUMS`
confere cada byte; `dados/datapackage.json` (Frictionless Data Package) traz tamanho, SHA-256 e
origem de cada arquivo. Para recalcular etapas da mente em qualquer assistente:
`docs/cdp/REPRODUZIR.md`.

## Antes de ligar o portal (dono do repositório)

- `configs/cdp/fund.yaml` com o calendário vigente (sem comentários de calendários antigos) e a
  calibração da metodologia em vigor em `reports/backtest/` — senão a aba de backtest sai vazia.
- Nada mais do painel: o perfil `site`, a aba de cobertura e a seção de auditoria e reprodução
  já são montados pelo `cdp site construir`.

## Página e módulos

A página é uma casca pequena (`index.html`, < 8 KB) que referencia o estilo e o script
versionados (`painel-<versão>.css`/`.js`) e busca `data.json` ao lado dela. Código novo de
exibição nunca entra no script central (orçamento de 260 KB): vai para módulos carregados sob
demanda na primeira abertura da aba, com o mesmo carimbo de versão — `painel-<versão>-modelo.js`
(modelo aberto da carteira) e `painel-<versão>-cobertura.js` (aba de cobertura). A versão é o
SHA-256 do formato de publicação, do template e dos módulos: mudar qualquer um deles republica a
página inteira.

O espelho privado opcional (artifact do claude.ai) usa o perfil `publicacao`, com o orçamento de
leitura integral de quem publica (cada arquivo ≤ 260 KB e linhas ≤ 1.500 caracteres nos dados):
a formulação completa da decisão fica só no portal (o espelho leva a decomposição do risco e os
ajustes escalares da decisão e, nos níveis finais, só as restrições que vinculam ou estão perto
do limite, com a contagem das exibidas). Tudo o que vai ao espelho numa publicação é lido por
inteiro, com teto total de 1 MB (`painel_artifact.ORCAMENTO_LEITURA`). Os dados da cobertura que
mudaram vão inteiros só quando cabem nesse teto junto com o resto da publicação; senão nada da
cobertura vai (o espelho mantém a última cobertura publicada, ou mostra o aviso que aponta o
portal público) e o marcador local `COBERTURA_PUBLICADA.json` só registra o que de fato foi
publicado (`cdp painel --publicado` refaz a mesma conta). Falha no registro da cobertura nunca
derruba o painel nem o portal: a aba fica "em conferência" e o resto segue publicado.

## Montar e conferir localmente

```sh
uv run python -m cdp site construir --saida _site
uv run python -m cdp site conferir --saida _site
uv run python -m cdp site construir --demo --saida _site_demo
```

`_site/` e `_site_demo/` não são versionados. Para ver no navegador:
`python3 -m http.server -d _site 8000`. Ícones e imagem de compartilhamento ficam em `site/`
(regerados por `uv run python -m cdp site estaticos`, que usa o Playwright do grupo de
desenvolvimento).

## Configuração única (dono do repositório)

```bash
gh api -X POST repos/arielassayag/MarketSummary/pages -f build_type=workflow \
  || gh api -X PUT repos/arielassayag/MarketSummary/pages -f build_type=workflow
gh repo edit arielassayag/MarketSummary --homepage https://arielassayag.github.io/MarketSummary/
gh variable set CDP_PORTAL_NOINDEX --body 0 -R arielassayag/MarketSummary
gh workflow run cdp-site.yml -R arielassayag/MarketSummary
```

Equivale a Settings → Pages → Source: **GitHub Actions**. `CDP_PORTAL_NOINDEX=1` tira o portal
dos buscadores sem mudar código. Domínio próprio é opcional (Settings → Pages → Custom domain,
com verificação do domínio).

## Quando o portal atualiza

- A cada push em `main` que toque o livro, os relatórios, os dados, a configuração, o código do
  CDP ou `site/`.
- Rede de segurança agendada às 20:41 de Brasília nos dias úteis e às 23:41 de sexta.
- Manualmente: Actions → cdp-site → Run workflow.
- `uv run python -m cdp estado --rede` aponta `PORTAL_DEFASADO` quando o portal não corresponde a
  `origin/main`.
