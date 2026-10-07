# Notas de pesquisa por emissor — especificação

A nota de pesquisa é a leitura qualitativa da gestão sobre um emissor coberto pelo CDP — Cabra da
Peste: negócio, pilares da tese, vetores de valor, catalisadores datados, matriz de riscos,
cenários, leitura do modelo de valuation, último resultado, governança e gatilhos de revisão, com
uma visão ordinal (`stance` de −2 a +2, convicção de 1 a 5). O modelo de valuation, o preço-alvo
de 12 meses, os cenários e as probabilidades são do **código** (modelo aberto da cobertura,
`docs/cdp/COBERTURA.md`): a nota interpreta, nunca os altera. A visão ordinal é acompanhada
separadamente do preço-alvo.

Todo número da nota vem do código, citado como `{{fact:<id>}}`. Toda evidência é pública e
verificável por qualquer pessoa. Tom: `docs/cdp/ESTILO.md`.

## 1. Arquivos (`book/cobertura/notas/<IID>/<data>/`)

| Arquivo | Quem escreve | Conteúdo |
|---|---|---|
| `fatos.md` | código | briefing: regras, limites, contexto, ficha do modelo, fontes públicas sugeridas, fatos citáveis (emissor, pares, ETFs, câmbio e juros) e exemplo |
| `factbook.json` | código | fatos do emissor e dos pares (modelo aberto da cobertura `val.<IID>.*`, histórico `cob.<IID>.*`, eventos `evento.<IID>.*`, indicadores de mercado `<IID>.*`) |
| `contexto.json` | código | emissor, país, setor, pares, nota anterior, snapshot da cobertura usado, próximo resultado, lacunas, fontes sugeridas |
| `nota.schema.json` | código | JSON Schema de `nota.json` (`NotaEmpresa`) |
| `nota.json` | **mente** | a nota (único arquivo editável) |
| `nota_publicada.json` | código, imutável | forma publicada (placeholders resolvidos), autoria, hashes, problemas |
| `nota.md` | código, imutável | leitura humana |

Cada publicação grava um evento `COVERAGE_NOTE` na trilha de auditoria do fundo
(`book/audit_log.jsonl`) com o emissor, a data, o sha256 de `nota_publicada.json` e de `nota.md`,
o snapshot da cobertura usado e a autoria. A verificação (`verify_notes`, parte de `cdp verify`)
confere que toda nota publicada tem o seu evento e que todo evento aponta para arquivos íntegros;
`cdp nota agenda` mostra o resultado em `integridade_notas`.

## 2. Comandos

```sh
uv run python -m cdp nota agenda
uv run python -m cdp nota prepare --issuer IID --date AAAA-MM-DD
uv run python -m cdp validate-nota --issuer IID --date AAAA-MM-DD
uv run python -m cdp nota publish --issuer IID --date AAAA-MM-DD
```

- `nota agenda [--date D]`: fila determinística, no máximo 12 emissores por execução, em
  quatro grupos, nesta ordem: (1) rascunhos entregues em `docs/cdp/notas/` com data até D ainda
  não publicados; (2) pós-resultado (o próximo resultado registrado na nota anterior caiu nos
  últimos 4 dias corridos); (3) notas vencidas: sem nota (iniciação) ou nota mais velha que 7 dias
  (posições), 14 dias (candidatos do modelo de cobertura, rating Compra ou Venda) ou 90 dias
  (demais); (4) emissores cuja última nota é a automática do código (`autoria: "codigo"`): a
  leitura qualitativa volta à fila a partir do dia seguinte, depois dos demais grupos. Dentro de
  cada grupo: posições, candidatos e demais, do maior volume financeiro médio para o menor. Cada
  item traz `data_nota` (hoje, ou a data do rascunho); a saída lista também
  `rascunhos_pendentes`, `rascunhos_obsoletos` (emissor com nota publicada depois da data do
  rascunho, ou fora do universo — nunca adotados) e `notas_da_mente_por_mente`.
- `nota prepare --issuer IID [--date D]`: grava os arquivos do código (regraváveis até a
  publicação) e adota o rascunho entregue em `docs/cdp/notas/<IID>/<data>.json` se `nota.json`
  ainda não existir (`rascunho_adotado: true`); nunca sobrescreve `nota.json` nem publica.
- Datas: `prepare`, `validate-nota` e `publish` recusam uma nota nova com data posterior a hoje
  (Brasília) ou anterior à última nota publicada do emissor (a sequência só anda para a frente).
- `validate-nota --issuer IID --date D`: schema e verificação completa, sem gravar (código 0 = ok).
- `nota publish --issuer IID --date D`: recalcula os fatos em memória (nunca confia no disco);
  `nota.json` válido ⇒ narrativa da mente (`autoria: "mente"`); ausente ou inválido ⇒ nota
  automática do código (`autoria: "codigo"`, só fatos, visão neutra) e os problemas registrados.
  Placeholder que sobre na narrativa da mente ⇒ nota automática; criação exclusiva; evento
  `COVERAGE_NOTE`; publicação interrompida antes do evento é retomada se os arquivos conferirem
  byte a byte.

## 3. Fatos

Com snapshot da cobertura até a data da nota, o FactBook é o do modelo aberto
(`cobertura/fatos.py`): `val.<IID>.{preco, preco_alvo, upside, alvo_otimista, alvo_pessimista,
prob_otimista, prob_pessimista, ke, wacc, g, etr, alpha, alpha_rel, rating_codigo,
confianca_codigo, pl_fwd, pb, cv_metodos, consenso_alvo, diff_consenso, sens.*}`,
`cob.<IID>.*` e `evento.<IID>.*`, mais os indicadores de mercado do emissor e dos pares do modelo.
Sem snapshot (ou com o emissor fora dele), os indicadores de mercado do emissor e dos pares do
código (mesmo país e setor) — e a lacuna fica registrada, nunca vira zero: o texto da nota diz
apenas "Modelo de valuation da cobertura indisponível nesta data; ficha com indicadores de
mercado." e o motivo técnico fica em `avisos_tecnicos` (`contexto.json` e saída do `nota
prepare`). Fatos de outros emissores só dos pares; câmbio, juros, índices e ETFs são livres.

## 4. Schema `NotaEmpresa` (resumo)

| Campo | Regras |
|---|---|
| `mind` | mente que escreveu: `claude-code`, `codex`, `api`, `demo`, `chatgpt`, `gemini` ou `outro` |
| `issuer_id`, `data` | iguais aos da pasta |
| `tipo` | `iniciacao` (sem nota anterior), `atualizacao`, `pos_resultado` ou `evento` (com nota anterior; exigem `o_que_mudou`) |
| `titulo`, `resumo`, `negocio` | até 160, 1.200 e 1.500 caracteres |
| `pilares_tese` | 1 a 5; cada um com ao menos uma evidência |
| `vetores` | 1 a 8 (direção positivo/negativo/incerto; sensibilidade alta/media/baixa) |
| `catalisadores` | até 10; data entre a nota e 12 meses depois, ou `null` |
| `riscos` | 1 a 8 (probabilidade alta/media/baixa; impacto alto/medio/baixo) |
| `cenarios` | otimista, base, pessimista em texto (valores só pelos fatos do modelo) |
| `comentario_valuation` | leitura do modelo aberto |
| `ultimo_resultado`, `guidance`, `tom_gestao` | `pos_resultado` exige `ultimo_resultado` e `guidance` avaliado |
| `governanca`, `o_que_mudou`, `gatilhos_revisao`, `lacunas_de_dados` | texto |
| `stance`, `conviccao` | inteiros −2…+2 e 1…5 |
| `fontes` | até 20: `id` (F1…F20), `tipo`, `instituicao`, `titulo` (sem números), `url` https, `publicado_em` |
| `modelo_ia` | opcional, governança: o modelo de IA usado (registrado, nunca exibido no texto) |

## 5. Verificação

- Números fora de `{{fact:<id>}}` (inclusive por extenso; nomes de formulários como 20-F, 6-K
  e 10-K são permitidos), fatos inexistentes, links, URLs, HTML, emojis e injeção de instruções
  em qualquer texto, inclusive títulos e instituições das fontes (que também não aceitam
  placeholders: são texto literal).
- Guia de estilo: jargão de tecnologia, registro coloquial, tom promocional e exclamação.
- Fatos de emissor fora dos pares; em pilares, vetores, catalisadores e riscos, todo fato citado
  no texto precisa estar nas `evidencias` do item, e toda evidência precisa ser um fato do
  FactBook ou uma fonte declarada.
- Fontes: URL https com domínio público (nunca endereço IP, `localhost`, rede local, intranet
  ou domínio de teste); publicação não posterior à nota (sem look-ahead); fontes `regulatorio` e
  `bolsa` só com URL do domínio oficial (CVM, agências e BCB sob gov.br; sec.gov e finra.org;
  gob.mx; cmfchile.cl e gob.cl; gov.co; gob.pe; gov.ar e gob.ar; B3, BMV, BIVA, Bolsa de
  Santiago, BVC, BVL, BYMA, NYSE e Nasdaq); emissor real exige ao menos uma fonte primária
  (`regulatorio` ou `bolsa` em domínio oficial, ou `relacoes_com_investidores`). Emissor sintético
  da demonstração dispensa fontes.
- Tipo coerente com a existência de nota anterior; catalisadores dentro de 12 meses.

## 6. Fontes públicas

Reguladores (CVM — RAD, IPE e dados abertos; SEC EDGAR — 20-F, 6-K, 10-K e dados XBRL; CNBV,
CMF, Superintendencia Financiera, SMV, CNV), bolsas (B3, BMV, Bolsa de Santiago, BVC, BVL, BYMA),
páginas de relações com investidores (releases, apresentações, transcrições públicas de
teleconferências), bancos centrais (BCB, Banxico, BCCh, BanRep, BCRP, BCRA), institutos de
estatística (IBGE, INEGI, INE, DANE, INEI, INDEC), FRED, Damodaran Online e imprensa. `fatos.md`
lista as fontes do país do emissor com a URL. Nenhuma base paga, de acesso restrito ou conector
proprietário: qualquer pessoa consegue abrir cada fonte citada.

## 7. Rotina, rascunhos e qualquer assistente

- Pós-resultado: quando um emissor divulga resultado (CVM, SEC ou Yahoo), a rotina diária
  reavalia o modelo no fechamento do pregão seguinte (retrato parcial da cobertura,
  `cobertura.snapshot_pendente` com `tipo: "parcial"` em `cdp agenda`) e a rotina de notas
  escreve a nota de pós-resultado na mesma noite ou na seguinte: `cobertura.notas_pos_resultado`
  lista os emissores com resultado dos últimos 4 dias já incorporado ao modelo e sem nota
  posterior, tratados antes da fila (tipo `pos_resultado`, ou `iniciacao` sem nota anterior).
- Rotina `cdp-cobertura`: segunda a quinta, 22:37 de Brasília, até 12 emissores por execução,
  no app de IA de quem opera (Claude Code, Codex ou Gemini; `docs/cdp/ROTINAS.md`). O
  procedimento é o roteiro neutro `docs/cdp/playbooks/COBERTURA.md`, o mesmo em qualquer app; as
  skills `cdp-cobertura` (`.claude/skills/`, `.agents/skills/`) e `/cdp:cobertura` (plugin) só
  fazem a entrada e a saída da execução.
- Nota escrita fora do clone das rotinas: rascunho em `docs/cdp/notas/<IID>/<data>.json`
  (`docs/cdp/notas/README.md`).
- Qualquer assistente de IA: `cdp mente pacote --etapa nota` exporta o pacote autocontido
  (`docs/cdp/REPRODUZIR.md`); o JSON devolvido é validado por `validate-nota`, como o da rotina.

```sh
uv run python -m cdp mente pacote --etapa nota --emissor IID --data AAAA-MM-DD --saida /tmp/pacote_nota.md
```

Na demonstração offline (DADOS SIMULADOS), a nota usa o snapshot sintético da cobertura, se
houver, e é escrita pela mente `demo` com a nota automática.

## 8. Visões por mente

`stance` e `conviccao` publicadas ficam em `nota_publicada.json` com a mente (`mind`) e, quando
informado, o modelo (`modelo_ia`). Só as notas da mente (`autoria: "mente"`) contam como visão; a
nota automática do código não conta. O acompanhamento é por mente: visões de mentes diferentes
nunca se somam (`notas.mind_history`; `notas_da_mente_por_mente` em `nota agenda`).
