# Replicar o CDP — o seu portal e a sua carteira, com qualquer app de IA

Três níveis, do mais simples ao completo. Todos usam só dados públicos, código aberto e o plano
de IA que você já tem (Claude, ChatGPT/Codex, Gemini ou outro).

| Nível | Para quê | Guia |
|---|---|---|
| 1. Auditar | conferir e recalcular o que o CDP publicou | `docs/cdp/REPRODUZIR.md` |
| 2. Espelhar o portal | ter uma cópia do portal publicada de graça | seção 2 abaixo |
| 3. Operar a sua carteira | rodar o processo inteiro com a sua data de início | seção 3 abaixo |

Custos: hospedagem zero (GitHub Pages e Actions em repositório público); IA = o seu plano.

## Licenças e aviso legal

- **Código** (programas, scripts, modelos de página e testes) de todo o repositório — o CDP e o
  app Fechamento: Apache License 2.0 (`LICENSE`, com os avisos de `NOTICE`). Pode usar, modificar
  e redistribuir, mantendo o aviso de licença e o `NOTICE` e indicando as alterações.
- **Documentação, metodologia e conteúdos do CDP** (textos, roteiros, a parte "CDP" do
  `AGENTS.md`, teses, notas, relatórios e dados derivados): Creative Commons Atribuição 4.0
  Internacional (`LICENSE-docs`, com o texto legal oficial em português). Os textos do app
  Fechamento não entram nessa licença. Atribuição sugerida: "CDP — Cabra da Peste, de Ariel
  Assayag (https://github.com/arielassayag/MarketSummary), licenciado sob CC BY 4.0", com as
  alterações indicadas.
- **Marca reservada:** o nome "CDP — Cabra da Peste", o logotipo e as ilustrações não são
  licenciados — os arquivos de `docs/cdp/marca/`, os ícones do portal em `site/` e as versões
  embutidas no código (o bloco entre os marcadores `>>> marca` e `<<< marca` de
  `src/cdp/workflow/painel_template.html`, gerado por `scripts/cdp_marca.py`). O programa
  `scripts/cdp_marca.py` é código (Apache-2.0); as imagens que ele gera a partir do logotipo,
  não. Exceção: um **espelho não modificado** do portal (seção 2) pode manter a marca, com
  atribuição, sem indexação por buscadores e sem se apresentar como o portal oficial. Uma cópia
  com carteira, livro ou textos próprios usa nome e identidade próprios (seção 3, passo 3).
- **Dados de terceiros** (CVM, SEC, B3, bancos centrais, emissores, Yahoo Finance, notícias)
  seguem os termos de cada fonte.
- **Aviso legal fixo** (o mesmo do `README.md` e de `LICENSE-docs`; mantenha-o no seu portal,
  em `configs/cdp/site.yaml` → `aviso_legal`):

  > O CDP é uma carteira simulada (paper trading com preços reais), mantida para pesquisa e
  > transparência metodológica. Não há oferta, distribuição ou captação de recursos, nem gestão
  > de recursos de terceiros: o CDP não é fundo de investimento constituído nos termos da
  > Resolução CVM nº 175/2022 nem registrado na CVM, e os termos "fundo", "gestão" e "PL"
  > descrevem apenas a carteira simulada. Ratings, preços-alvo e notas por emissor são
  > produzidos automaticamente por modelos quantitativos internos de código aberto e por um
  > agente de IA sob regras determinísticas, para transparência metodológica; não são
  > elaborados por analista de valores mobiliários nos termos da Resolução CVM nº 20/2021 e
  > não consideram objetivos, situação financeira ou necessidades de qualquer investidor.
  > Resultados simulados não garantem resultados futuros.

  Não capte recursos nem ofereça investimento com a sua cópia.

## 1. Auditar

`docs/cdp/REPRODUZIR.md`: clonar, `uv sync`, `uv run python -m cdp verify`, recalcular modelos e
decisões a partir dos insumos públicos arquivados e reproduzir qualquer etapa da mente em qualquer
assistente com `cdp mente pacote`. No portal, a página **Dados abertos e auditoria** traz cada
arquivo com o seu código de verificação e o link para a versão do repositório que o gerou.

## 2. Espelhar o portal

Um espelho é uma cópia **não modificada** do portal original (o mesmo livro, os mesmos textos):
pode manter a marca, desde que não seja indexado por buscadores, mantenha a atribuição e os
links para o portal original (já estão nas páginas) e não se apresente como o portal oficial.

1. Faça um fork de `arielassayag/MarketSummary` no GitHub.
2. No seu fork, em `configs/cdp/site.yaml`, troque `indexar: true` por `indexar: false` (as
   páginas saem com `noindex`; o endereço canônico continua apontando para o portal original) —
   é a única alteração do espelho.
3. Settings → Pages → Source: **GitHub Actions**.
4. Actions → habilite os workflows (forks começam com agendamentos desligados) → `cdp-site` →
   Run workflow. O espelho fica em `https://<seu-usuário>.github.io/<repositório>/`.
5. Para acompanhar o livro original, use "Sync fork" quando quiser; o workflow republica.
   Qualquer outra alteração (carteira, livro, textos) faz da cópia um portal próprio: siga a
   seção 3, com nome e identidade próprios.
6. Antes de haver carteira, rode o `cdp-site` com a opção de demonstração: um portal completo
   marcado DADOS SIMULADOS, montado só como artefato da execução (baixe e abra localmente; nunca
   vai ao endereço público).

## 3. Operar a sua carteira

1. **Fork e ambiente**: clone o seu fork; `uv sync --extra dev --extra ai`;
   `uv run python -m cdp demo` (confere que tudo roda offline).
2. **Livro novo**: num ramo próprio, remova o livro, a pesquisa, o painel e os relatórios da
   carteira herdados — `--ignore-unmatch` evita que o comando inteiro falhe quando uma das
   pastas não existe no momento do fork (algumas só aparecem depois das primeiras rotinas):

   ```sh
   git rm -r -q --ignore-unmatch book pesquisa arquivo artifacts/painel reports/daily reports/weekly reports/semanal reports/risk 'docs/cdp/teses/*.json'
   ```

   Mantenha `data/` (dados públicos de mercado) e a pesquisa de metodologia
   (`reports/backtest`). O painel (`artifacts/painel/`) é regenerado pelas suas rotinas; o
   herdado aponta para a página do original.

   **Gênese:** depois de concluir a configuração e registrar o seu executor (passos 3 e 4),
   abra o livro vazio explicitamente com `cdp genese`, no clone dedicado da sua réplica.
   O plano é somente leitura. A abertura grava `book/genese.json` e o primeiro evento
   `FUND_GENESIS`, ancorando a data de início, o hash do mandato e o commit do próprio clone
   (`docs/cdp/REPRODUZIR.md`, seção 1). Com a gênese, o livro recusa chaves anteriores ao início.
   Não use esse comando para remover história herdada, reparar trilha ou desligar kill switch.

3. **Configuração e identidade próprias** — ajuste à mão, no mesmo ramo:
   - `configs/cdp/fund.yaml` → `fund.inception_date` (a sua data de início; mudar o mandato é
     decisão sua e entra no histórico), `fund.name` e `fund.manager_name`;
   - `configs/cdp/site.yaml` → `titulo`, `titulo_curto`, `descricao`, `base_url`,
     `repositorio`, `og.alt` e `aviso_legal` (com o aviso legal fixo acima);
   - `configs/cdp/rotinas.yaml` → `repositorio`;
   - `configs/cdp/executor.yaml` → o seu executor (`claude-cloud`, `local-pc`…) e o seu nome;
   - marca: troque `docs/cdp/marca/cdp-logo.png` pelo seu logotipo e rode
     `uv run python scripts/cdp_marca.py --mascaras` (máscaras e o bloco embutido no modelo do
     painel) e `uv run python -m cdp site estaticos` (ícones e imagem de compartilhamento em
     `site/`; requer Playwright);
   - manifestos do plugin: `plugins/cdp/.claude-plugin/plugin.json` e
     `.claude-plugin/marketplace.json` (nome, autor e endereço do repositório);
   - constantes ainda fixas no código (enquanto não forem lidas da configuração; pendência em
     `docs/cdp/EM_ANDAMENTO.md`): `REPO` e `PORTAL_URL` em `src/cdp/workflow/painel.py`,
     `REPOSITORIO` em `src/cdp/workflow/painel_cobertura.py`, o cabeçalho do portal em
     `src/cdp/site.py`, o cabeçalho do painel em `src/cdp/workflow/painel_template.html` e o
     endereço padrão em `src/cdp/research/providers/openrouter_provider.py`; ajuste também o
     endereço esperado em `tests/cdp/test_painel.py`;
   - inventário documental: `scripts/cdp_mapear_modelos.py` recebe `--repo-url` para os
     links da versão que você está auditando. Use o repositório próprio para um retrato da
     réplica; preserve o repositório original ao reproduzir a auditoria histórica do CDP;
   - o que sobrar: `git grep -n -i -e "cabra da peste" -e "arielassayag"` lista cada ocorrência
     do nome e do endereço originais em código, configuração e textos.

   Confira com `uv run python -m cdp rotinas verificar`, `uv run python -m cdp verify` e
   `uv run pytest tests/cdp -q`; faça o commit e o merge no seu `main`.
4. **Escolha o app de IA e agende as rotinas dentro dele** (passo a passo em
   `docs/cdp/AUTOMACAO.md`):
   - **Claude Code** (rotinas na nuvem em claude.ai/code; a escolha do CDP):
     `uv run python -m cdp rotinas exportar --alvo claude-routines --formato md`;
   - **Codex** (tarefas agendadas do app, num clone e numa conta de usuário dedicados, com
     acesso total): `uv run python -m cdp rotinas exportar --alvo codex --formato md`;
   - **Gemini** (Antigravity — tarefas agendadas do app ou `agy` pelo agendador do sistema;
     Gemini CLI com chave paga): `uv run python -m cdp rotinas exportar --alvo gemini --formato md`
     ou `uv run python -m cdp rotinas exportar --alvo cron --harness agy`;
   - **app desktop do Claude Code** no seu computador:
     `uv run python -m cdp rotinas exportar --alvo claude-desktop` (`docs/cdp/LOCAL.md`).
   Registre a identidade do executor (`CDP_EXECUTOR` no ambiente das rotinas na nuvem — nunca
   no ambiente das suas sessões interativas —, ou
   `uv run python -m cdp executor registrar --como local-pc --harness codex` no clone dedicado
   às rotinas, trocando o app). Antes de ligar, crie a regra do ramo `main` no seu repositório
   (`docs/cdp/AUTOMACAO.md`, seção 3, passo 1). Ligue as rotinas em um app só: o escritor é
   único.

   **Abrir a gênese da réplica:** faça isso após o mandato e o código estarem registrados no
   seu `main`, sincronizado com `origin/main`, antes da primeira montagem ou fechamento.
   No executor designado, confira o plano:

   ```sh
   uv run python -m cdp genese
   ```

   O estado esperado é `vazio`. Livro com arquivos herdados, gênese parcial, link simbólico,
   área temporária de abertura interrompida ou kill switch ativo é recusado e preservado.
   Leia `cdp estado` e `cdp agenda` e use o gate da tarefa exclusiva que a agenda autoriza.
   Na sessão de operador, o gate usa `--manual` quando estiver fora do horário, mantendo as
   mesmas pendências e guardas. Se o gate devolver `executar: false`, encerre; não force uma
   abertura. Com a execução e a trava autorizadas, rode:

   ```sh
   uv run python -m cdp genese --executar --execucao <execucao> --trava <trava.id>
   ```

   A abertura confere identidade local e de `origin/main`, mandato do clone, código limpo,
   registro de execução exclusivo e escopo do livro, e trava vigente da mesma tarefa,
   executor e harness. Gênese e evento são preparados, conferidos e promovidos juntos.
   Não há remoção de arquivos do livro; repetir com gênese íntegra não altera bytes nem datas.
   Continue o roteiro autorizado e publique somente por `cdp publicar`, usando a mesma
   execução e trava. Libere a trava ao encerrar, inclusive em falha. Sem pendência exclusiva
   autorizada, a abertura fica pendente; o comando não cria um gate nem uma nova rotina.

5. **Portal**: ligue o Pages (seção 2, passos 3 e 4); a cada gravação das rotinas o portal
   atualiza. O GitHub Actions só monta o portal e roda os testes; a IA roda no app que você
   escolheu.
6. **Conferência**: `uv run python -m cdp estado --rede --formato md`; no portal, `manifest.json`
   deve trazer a última versão de `origin/main` que muda o portal, e `sha256sum -c SHA256SUMS`
   deve passar (`docs/cdp/SITE.md`, "Conferir uma publicação").

## Continuidade entre apps de IA

O processo não depende do app: `AGENTS.md` é o manual de qualquer um, os roteiros ficam em
`docs/cdp/playbooks/`, a agenda em `configs/cdp/rotinas.yaml` e as skills abertas em
`.agents/skills/`. Para trocar de app no meio do caminho, peça ao novo: "leia `AGENTS.md` e
continue a operação do CDP" — ele começa por `uv run python -m cdp estado` — e troque o executor
como manda `docs/cdp/AUTOMACAO.md`, seção 13.
