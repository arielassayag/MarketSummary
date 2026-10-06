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

- **Painel** (`index.html` + `data.json`): o painel de gestão do fundo com os limites de tamanho
  do artifact liberados (todas as semanas, pregões, comentários, a trilha de auditoria e o
  monitor de risco inteiros); resultados da carteira-sombra ficam de fora. O painel ainda omite
  alguns campos técnicos por nome (escore e beta por posição, ordens da proposta, controles de
  conformidade triviais, pontos de pesquisa a favor e contra, eventos da trilha); todos estão
  nos arquivos de `dados/` (livro, propostas, decisões e `audit_log.jsonl`). Os modelos de
  cobertura e a reprodução ainda não têm aba própria no painel: ficam em `dados/livro/cobertura/`
  e na página de dados abertos.
- **Backtests**: só os da metodologia em vigor (calendário de rebalanceamento atual de
  `configs/cdp/fund.yaml`); calibrações de metodologia substituída ficam só no repositório.
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
- Perfil "site" do painel (sem os cortes técnicos por nome) e as abas de cobertura e de
  auditoria e reprodução: enquanto não existirem, o portal mostra o painel com os limites
  liberados e aponta para `dados/`.

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
