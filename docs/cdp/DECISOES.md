# Registro de decisões do CDP

Decisões já tomadas, para qualquer agente ou pessoa que chegue ao projeto (em qualquer app de IA).
Formato: data · contexto → decisão → consequências. Acrescente no fim; não reescreva entradas
antigas (uma decisão revista ganha uma entrada nova que cita a anterior).

## 2026-10-06 · Só dados públicos

Contexto: reprodutibilidade por qualquer pessoa e repositório público. → Decisão: modelos,
pesquisa e notas usam somente fontes públicas (CVM, SEC EDGAR, B3, bancos centrais e institutos
de estatística, RI das empresas, emissores de ETF, Damodaran, Yahoo Finance como consenso
público rotulado, notícias públicas); evidência é URL pública. → Consequências: nenhuma base paga
nem conector proprietário em código, skills, configuração ou documentação; insumos arquivados em
`data/publico/` com fonte, datas e SHA-256.

## 2026-10-06 · Carteira inaugural na sexta, 2026-10-09

Contexto: metodologia completa antes de montar a carteira. → Decisão: `fund.inception_date =
2026-10-09`; montagem no último pregão da semana na NYSE, execução no leilão de fechamento; a
carteira do ensaio anterior não aparece em nenhum texto para investidores. → Consequências: a
rotina diária abre o livro uma única vez (`cdp reinicio --executar`) antes da data de início; o
portal recusa montar enquanto isso estiver pendente.

## 2026-10-06 · Escritor único e executor designado

Contexto: o livro é uma trilha encadeada por hash; dois escritores corrompem a história. →
Decisão: só o executor de `configs/cdp/executor.yaml` grava `book/`, `data/`, `reports/`,
`artifacts/`; a identidade de cada ambiente é explícita (`CDP_EXECUTOR` ou `.cdp/local.yaml`);
publicação só por `cdp publicar` (escopo de caminhos, verify, push em `main`, nunca force). →
Consequências: sessões de desenvolvimento nunca gravam o livro; troca de executor é decisão
humana, por commit revisável (`docs/cdp/AUTOMACAO.md`).

## 2026-10-06 · Operação agnóstica ao harness

Contexto: o projeto precisa rodar em Claude Code, Codex, Gemini CLI, Antigravity ou outro, e
qualquer um deve continuar o trabalho de onde parou. → Decisão: `AGENTS.md` é o manual canônico;
roteiros neutros em `docs/cdp/playbooks/`; agenda como dados em `configs/cdp/rotinas.yaml`;
skills abertas (Agent Skills) geradas em `.agents/skills/`; `CLAUDE.md`, `GEMINI.md` e o plugin
são adaptadores finos; estado por código (`cdp estado`). → Consequências: nada essencial vive só
na memória de um harness; mudanças de agenda passam por `cdp rotinas verificar` e
`cdp skills sincronizar`.

## 2026-10-06 · Nuvem: rotinas do Claude Code como executor principal

Contexto: automação 100% em nuvem usando a capacidade do plano. → Decisão: uma rotina da nuvem
do Claude Code por tarefa (prompts gerados por `cdp rotinas exportar --alvo claude-routines`),
ambiente sem segredos, gate determinístico antes de qualquer uso de modelo, trava distribuída no
ramo `cdp-trava` (máquinas separadas). Alternativas documentadas: GitHub Actions com qualquer
CLI, agendadores do sistema, app desktop. → Consequências: troca de executor com ensaio prévio
(`docs/cdp/AUTOMACAO.md`).

## 2026-10-06 · Portal público no GitHub Pages

Contexto: portal gratuito, estável, sem conta extra e replicável por fork. → Decisão: GitHub
Pages implantado pelo GitHub Actions, montado do repositório por `cdp site construir` (sem cortes
de tamanho; dados abertos com SHA-256; manifesto ligado à versão do repositório). O artifact do
claude.ai vira espelho privado opcional. → Consequências: o CI nunca grava no repositório; o
portal fica a até alguns minutos do último push (`docs/cdp/SITE.md`).

## 2026-10-06 · Montagem no último pregão da semana na NYSE, execução no leilão de fechamento

Contexto: decidir com todos os dados disponíveis e executar a um preço oficial, verificável e
com liquidez concentrada. → Decisão: dia de montagem = último pregão da semana na NYSE
(sexta-feira, ou o pregão anterior em feriado nos EUA); pesquisa a partir das 11:07, decisão
gravada até o prazo efetivo (15:00; 14:15 em fechamento antecipado nos EUA) e execução no
leilão de fechamento de cada linha, limitada à capacidade calculada pelo código; relatório
semanal de resultado na mesma noite. → Consequências: a decisão nunca é registrada depois do
prazo (o código recusa e mantém a carteira); reservas às 12:07, 13:07 e 14:07; regra ativada em
`configs/cdp/fund.yaml` por commit revisável (`docs/cdp/EXECUCAO.md`).

## 2026-10-06 · PL inicial de US$ 1,0 mi

Contexto: com US$ 100 mi, a carteira esbarrava na liquidez de um único leilão de fechamento
nos nomes menores do universo. → Decisão: `fund.inception_nav_usd = 1000000`. →
Consequências: pisos de liquidez, custo mínimo por ordem e proteção cambial recalibrados para
o tamanho (`docs/cdp/METODOLOGIA.md`, `docs/cdp/EXECUCAO.md`).

## 2026-10-06 · Construção com risco idiossincrático dominante

Contexto: o retorno esperado vem do risco específico de cada emissor; exposições a fatores são
risco não remunerado no mandato. → Decisão: meta de 90% da variância ex-ante como risco
idiossincrático (alerta) e piso de 85% (bloqueio de risco fatorial novo), medidos em dois
modelos de risco; escada de relaxamento que nunca afrouxa os limites de risco do mandato. →
Consequências: na carteira inaugural, a capacidade do leilão pode deixar a volatilidade abaixo
da banda (alerta SOFT divulgado) (`docs/cdp/METODOLOGIA.md`, seções 4.3 a 4.5).

## 2026-10-06 · Cobertura de todo o universo com modelos abertos

Contexto: transparência total e base comparável para todas as ações e ETFs do universo. →
Decisão: modelo de valuation e preço-alvo de 12 meses para cada instrumento, só com dados
públicos arquivados, fórmulas com valores substituídos pelo código, livro encadeado e placar
de acertos; o sinal de valuation entra no alpha em sombra (peso 0) até ser promovido por IC
realizado. → Consequências: retrato da cobertura na rotina diária e notas por emissor de
segunda a quinta à noite (`docs/cdp/COBERTURA.md`, `docs/cdp/NOTAS.md`).

## 2026-10-06 · Mente intercambiável

Contexto: qualquer pessoa com qualquer assinatura de IA deve conseguir reproduzir o processo. →
Decisão: a mente só escreve JSON validado; cada etapa pode ser exportada como pacote
autocontido (`cdp mente pacote`) para ChatGPT, Gemini, Claude ou outro; `--mind` aceita
`claude-code`, `codex`, `gemini`, `chatgpt` e `outro`. → Consequências: nenhum roteiro depende
de ferramenta paga ou proprietária (`docs/cdp/REPRODUZIR.md`).

## 2026-10-06 · Rotinas dentro do app de IA; GitHub Actions só para CI e portal

Contexto: revisão da decisão "Nuvem: rotinas do Claude Code como executor principal" a pedido
do titular: as skills e rotinas devem rodar no próprio app de IA (Claude Code, Codex ou
Gemini), com o projeto agnóstico. → Decisão: caminho principal = agendador do app (rotinas na
nuvem do Claude Code, a nossa escolha; tarefas agendadas do app desktop como reserva local;
tarefas agendadas do app do Codex; Antigravity ou Gemini CLI); o prompt de cada tarefa é gerado
por `cdp rotinas`. O GitHub Actions só faz a integração contínua e publica o portal; o workflow
com IA vira apêndice opcional. → Consequências: `docs/cdp/AUTOMACAO.md` ensina o passo a passo
em cada app; exportações `--alvo codex` e `--alvo gemini` com o prompt a colar.

## 2026-10-06 · Tudo em português do Brasil

Contexto: público de investidores qualificados no Brasil e pedido explícito do titular. →
Decisão: todo texto do repositório em pt-BR — documentação, roteiros, skills, prompts das
rotinas, ajuda e mensagens da CLI, comentários de configuração e de código, docstrings de
teste; identificadores de código ficam como estão. O texto oficial em inglês da Apache-2.0 é a
única exceção (texto jurídico). → Consequências: `tests/cdp/test_docs_consistencia.py` confere a
documentação de integração; seções em inglês são removidas.

## 2026-10-06 · Licenças (confirmadas pelo titular em 06/10/2026)

Situação: **decidida** — o titular escolheu, em 06/10/2026, Apache-2.0 + CC BY 4.0 para todo o
repositório, no escopo abaixo. `LICENSE`, `LICENSE-docs` e `NOTICE` entram em `main` com essa
confirmação (as concessões ficam irrevogáveis para cada versão publicada). Contexto: sem licença, a replicação
não é juridicamente livre. → Escopo: código de todo o repositório (o CDP e o app Fechamento)
sob Apache License 2.0 (`LICENSE`, com `NOTICE`); textos e conteúdos do CDP (documentação,
metodologia, a parte "CDP" do `AGENTS.md`, teses, notas, relatórios e dados derivados) sob
Creative Commons Atribuição 4.0 Internacional, com o texto legal oficial em português
(`LICENSE-docs`); os textos do app Fechamento ficam fora da CC BY 4.0; nome, logotipo e
ilustrações reservados (inclusive o bloco da marca embutido no modelo do painel), com espelho
não modificado do portal permitido sem indexação por buscadores; dados de terceiros sob os
termos das fontes; aviso legal fixo descritivo (`README.md`, "Aviso legal"). → Consequências:
`configs/cdp/site.yaml` declara as licenças (Apache-2.0 e CC-BY-4.0) no catálogo de dados e
nos metadados do portal; README e `docs/cdp/REPLICAR.md` explicam o uso.

## 2026-10-06 · Troca do executor para a nuvem depois da carteira inaugural

Contexto: a carteira inaugural (sexta 09/10) não deve depender de um executor recém-ligado. →
Decisão: o PC local continua executor até o relatório semanal de 09/10; as rotinas da nuvem
rodam em ensaio de quarta a sexta; troca no domingo 11/10, às 10:00, por
`cdp executor transferir --para claude-cloud`, com o PC como reserva quente por duas semanas. →
Consequências: segunda 12/10 é o primeiro dia real na nuvem; sexta 16/10, a primeira montagem
regular (`docs/cdp/AUTOMACAO.md`, seção 13).

## 2026-10-06 · Executor das rotinas: Codex (prevalece sobre as duas entradas de nuvem acima)

- **Decisão do titular:** as rotinas agendadas do CDP rodam no **Codex** (tarefas agendadas do
  app do Codex, `docs/cdp/AUTOMACAO.md` §5; prompts por `cdp rotinas exportar --alvo codex`).
  O desenvolvimento foi feito no Claude Code; a migração da operação para o Codex segue o prompt
  de passagem escrito ao fim do desenvolvimento.
- **Efeito:** `configs/cdp/executor.yaml` passa a designar o Codex quando o titular registrar a
  máquina (`cdp executor registrar`); até lá nenhuma rotina escreve no livro. As entradas
  "Nuvem: rotinas do Claude Code como executor principal" e "Troca do executor para a nuvem
  depois da carteira inaugural" ficam como alternativa documentada, não como plano.

## 2026-10-06 · Ativação do mandato da metodologia vigente

- Aplicada em `configs/cdp/fund.yaml`: montagem no último pregão da semana na NYSE com decisão
  antes do fechamento e execução no leilão (MOC) limitada à capacidade de liquidez; construção
  com meta idiossincrática ≥ 90% e piso de 85% (modelos de decisão e base), limites
  operacionais mais estreitos que o mandato, bloco macro e grupos ligados; stop de squeeze por
  nome e vetos de short; liquidez e custos calibrados para o PL de US$ 1,0 mi.
- **Por quê:** pedido do titular (metodologia profissional de neutralização de fatores, risco
  idiossincrático acima de 90%, montagem no último dia útil da semana no calendário dos EUA ao
  preço de fechamento com cuidado de liquidez). Conferida no ensaio geral sobre cópia do livro.

## Pendentes de decisão humana

Atualizado em 06/10/2026 (o Codex roda as rotinas; ver a entrada "O Codex roda as rotinas").

- **Revisão jurídica antes da publicação de 09/10**: o portal público e indexado mostra ratings
  (Compra, Neutro, Venda), preços-alvo de emissores listados e os termos "fundo", "gestão" e
  "Asset Management" (Resoluções CVM nº 20/2021 e nº 175/2022). Decidir rótulos dos ratings,
  termos, indexação das páginas da cobertura, o texto final do aviso legal e o logotipo e a
  imagem de compartilhamento com "ASSET MANAGEMENT".
- **Senha do operador no PC do Codex** (antes de 09/10): `uv run python -m cdp kill-switch senha`,
  num terminal próprio, fora de qualquer app de IA. Sem ela, um kill switch ligado por gatilho
  HARD não tem como ser desligado.
- Histórico público de commits anterior à data de início: manter ou publicar um ramo novo (depois
  de 09/10, nunca force).
- Distribuição de ratings e de confiança da cobertura no retrato-gênese de 08/10: aceitar ou
  pedir nova calibração antes da publicação (`docs/cdp/COBERTURA.md`).
- Portal indexado por buscadores (padrão: sim, com aviso legal fixo; depende da revisão
  jurídica acima) e domínio próprio (padrão: não; endereço do GitHub Pages).
- Identificadores de modelo dos níveis `forte` e `leve` em cada app (nunca no repositório).

Resolvidos: a regra do ramo `main` está ativa desde 06/10/2026 (entrada "Regra do ramo main
ativa"); a troca de executor para a nuvem prevista para 11/10 não ocorre (o executor é o Codex).

## 2026-10-06 · O Codex roda as rotinas

Contexto: escolha do titular entre os apps documentados, depois do ensaio geral com o Codex como
executor; revê a escolha "rotinas na nuvem do Claude Code" da entrada "Rotinas dentro do app de
IA". → Decisão: as rotinas rodam nas tarefas agendadas do app do Codex, num clone dedicado do PC
local, com acesso total (`configs/cdp/executor.yaml`: `local-pc`, harness `codex`); o Claude
Code e o Gemini seguem documentados como alternativas, sem mudança de processo. →
Consequências: prompts com `uv run python -m cdp rotinas exportar --alvo codex --formato md`; a
mente registrada nos JSON é a do gate (`codex`), conferida pelos validadores; o desligamento do
kill switch exige a senha do operador (o Codex com acesso total não exporta variáveis de
sandbox).

## 2026-10-06 · Regra do ramo `main` ativa

Contexto: o executor das rotinas (Codex) roda com acesso total ao clone e à credencial de push. →
Decisão: ruleset 24618259 ativo em `main` desde 06/10/2026 — bloqueia force push e exclusão, sem
exigir pull request; o ramo `cdp-trava` fica livre (a trava distribuída grava nele). →
Consequências: nenhum histórico publicado é reescrito, nem por engano de um app de IA; `cdp
publicar` continua sem força. Conferência: `gh api repos/arielassayag/MarketSummary/rulesets`.

## 2026-10-06 · Caducidade da decisão recusada no leilão

Contexto: com o kill switch ligado no fechamento do dia de montagem, a efetivação é recusada; sem
registro do dia, a decisão ficava pendente e era efetivada depois, quando um humano desligasse o
kill switch — com o preço daquele fechamento já conhecido. → Decisão: a decisão vale só para o
leilão de fechamento do seu dia de montagem. Recusada nesse leilão pelo kill switch, o dia é
registrado com a recusa ("efetivação recusada"; `book/<semana>/efetivacao_recusada.json` e evento
`BOOKING_LAPSED`) e a decisão caduca: nunca é efetivada depois. Na carteira inaugural, o histórico
começa nesse dia em caixa; numa semana regular, a carteira anterior segue marcada. A próxima data
de montagem decide de novo, com dados novos. Recusa por dado ausente (preço ou câmbio) na
inaugural não caduca: a reserva do mesmo fechamento tenta de novo. → Consequências: nenhuma
efetivação retroativa; `docs/cdp/EXECUCAO.md`, seção 12.

## 2026-10-06 · Falha de coleta nunca apaga dado gravado

Contexto: com a rede fora, a coleta de fundamentos do Yahoo devolvia linhas vazias que apagavam o
valor de mercado gravado e derrubavam o modelo de risco na preparação da semana. → Decisão: fonte
sem resposta é falha de coleta registrada, nunca um retrato vazio; a análise usa o último dado
gravado de cada fonte que falhou e o `weekly prepare` devolve um aviso legível (`aviso_coleta`);
com a rede fora, `weekly prepare --offline` monta o briefing só com a base gravada. →
Consequências: a preparação da sexta não depende da rede para terminar; ausente nunca vira zero
nem substitui um valor gravado.


## 2026-10-06 · Instalação das rotinas dentro do projeto atual do Codex

Contexto: o titular pediu que todas as tarefas fossem vinculadas ao projeto atual e que o
clone fosse trazido para uma pasta interna. → Decisão: as 12 automações do Codex pertencem ao
projeto atual; executam exclusivamente no clone `.cdp/rotinas`, em `main`, sem worktree.
O clone tem identidade `local-pc`, harness `codex`; o checkout de desenvolvimento permanece
sem identidade de executor. → Consequências: a pasta interna fica fora do versionamento;
identidade, dependências e prompts foram reconferidos após a mudança; as agendas continuam
vindo de `configs/cdp/rotinas.yaml`. Conta separada do sistema operacional não foi criada.

## 2026-10-06 · Plausibilidade do alvo por corroboração, metodologia 2026-10.4

Contexto: P0 da passagem para o Codex, para evitar que divergência do consenso force a visão
da casa a Neutro. → Decisão: consenso divergente e margem estreita do G11 são sinais para
revisão analítica; rebaixam confiança só sem pelo menos dois métodos brutos distintos do
mesmo lado do preço e coeficiente de variação de todos os métodos calculados de no máximo
0,5. Faixa de cenários unilateral só rebaixa quando há inconsistência comprovada de insumos
ou da simulação. → Consequências: diagnóstico aberto dos cenários, parâmetros na versão
2026-10.4; percentis não são truncados para envolver o preço de mercado. As metas de
composição da distribuição são critérios de conferência do retrato real, nunca cotas de
ratings nem justificativa para fabricar insumos. Nenhum parâmetro do mandato foi afrouxado.


## 2026-10-06 · RI público quando o XBRL da SEC está indisponível

Contexto: Companyfacts de emissores estrangeiros pode conter apenas contagens da capa, e
SEC Archives pode recusar acesso a documentos financeiros com HTTP 403. → Decisão: usar
catálogo público de documentos XBRL/ZIP do RI oficial, cruzado com CIK, accession,
formulário e datas de SEC submissions, com SHA-256 conferido. O primeiro documento curado
é o 20-F de 2025 da Supervielle. Capa DEI, data de arquivamento ou balanço comparativo isolado
não comprovam atualização financeira. → Consequências: fonte alternativa reprodutível,
bytes brutos arquivados e ausência preservada quando não existe documento verificável;
nenhuma leitura de PDF vira número inferido, nem valores são preenchidos por meta de rating.

## 2026-10-06 · Aceite técnico e científico da cobertura são distintos

Contexto: o retrato real .4 com RI bruto e PEN/UYU/CAD é íntegro no recálculo, mas ainda
falha nos critérios de confiança C e Em revisão da passagem. → Decisão: registrar o P0
científico como pendente, mesmo com integrações técnicas testadas. A análise de Petrobras
mostra uma premissa material de reinvestimento e uma conciliação incompleta de arrendamentos;
nenhum cenário é truncado para forçar cruzamento do preço. → Consequências: próximas revisões
partem das evidências por emissor; não se alteram severidades, mandato ou dados para atingir
as metas de distribuição. Ensaios permanecem separados do livro oficial.

## 2026-10-07 · Agendas independentes e procedimento canônico consultado no disparo

Contexto: o titular pediu pesquisa e organização das tarefas agendadas no Codex. A
[documentação oficial](https://learn.chatgpt.com/docs/automations?surface=app) orienta manter
ações duráveis em skills. → Decisão: organizar os nomes em seis famílias, com reservas
explícitas, e consultar `cdp rotinas prompt` em cada disparo. Manter os 12 IDs e agendas
existentes: a documentação não garante que uma nova reserva da mesma automação se inicie
enquanto sua execução anterior ainda trabalha. → Consequências: instalação conferida,
sem cópias adicionais; agenda canônica continua em `rotinas.yaml`. O primeiro disparo é
uma verificação operacional pendente, distinta da configuração salva.

## 2026-10-07 · Unidade de consenso pela declaração da fonte

Contexto: Orbia teve LPA declarado em USD convertido duas vezes para MXN pela heurística
de plausibilidade. Recuperação de prejuízo pode gerar uma razão extrema contra o lucro
realizado sem implicar erro de moeda. → Decisão: uma única conversão pela moeda declarada,
paridade de ações e câmbio; sem declaração, preservar ausência. A distância do realizado
é sinal de revisão, não autorização para alterar unidade. → Consequências: política nova
versionada, intermediários no modelo e testes de regressão; parâmetros históricos sem
a chave nova conservam seu recálculo. Portões de plausibilidade econômica permanecem.

## 2026-10-07 · Identidade não alavancada e arrendamentos capitalizados

Contexto: CFO menos capex/principal pode misturar juros, impostos, capital de giro e
aquisições de direitos de uso, enquanto arrendamentos já entram na dívida e no WACC.
→ Decisão: observar `FCFF = NOPAT + D&A − capex − Δgiro operacional − adições ROU`, com
componentes publicados no mesmo período, moeda e base de consolidação, inclusive dentro
do TTM; usar o período recente completo, com histórico
como diagnóstico. A [definição de capital de giro de Damodaran](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/valquestions/noncashwc.htm)
exclui caixa e dívida; diferença de balanços sem conciliação de câmbio/perímetro fica em
sombra, distinta de fluxo operacional observado. → Consequências: metodologia implementada
2026-10.5, lacuna explícita quando a identidade não fecha; principal pago não é capex;
observação e projeção teórica são distinguidas. Política antiga preservada por parâmetros
arquivados; mandato e portões não são afrouxados.
