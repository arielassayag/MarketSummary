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

## 2026-10-07 · G17 conforme dependências econômicas comprovadas

Contexto: alertas de magnitude em capex/D&A podiam limitar a confiança de modelos financeiros
que não usam esses itens. → Decisão: na metodologia `2026-10.6`, certificar a independência
pelo conjunto de métodos configurados e reportados, inclusive dissidentes, custo de capital,
contexto e participações externas; casos desconhecidos conservam a severidade histórica.
→ Consequências: alerta bruto preservado, classificação informativa com razão e caminhos
arquivados. Parâmetros sem a chave nova conservam o recálculo anterior. O ensaio isolado
preservou os números dos 233 modelos e elevou seis casos de C para B; a elegibilidade A/B
altera legitimamente o bottom-up de seis ETFs, confirmada por contrafactual. Os critérios
quantitativos P0 continuam abertos; não há quota usada para escolher emissores ou resultados.

## 2026-10-07 · Semântica contábil antes de compor receitas

Contexto: receita bruta e resultado líquido de seguros podem ocupar a mesma conta 3.01 da
CVM. A composição de quatro trimestres entre esses conceitos gerou receita economicamente
incomparável. → Decisão: manter valor/rubrica publicados, identificar o resultado líquido
pela identidade das filhas oficiais e segregar as séries; a guarda de compatibilidade vale
no provedor e no consumidor. → Consequências: Q reportados preservados, Q/TTM mistos recusados,
fallback homogêneo com período/publicação/hash originais e alerta explícito. Comparativas
reexpressas e imposto não são imputados; a correção de fonte não presume aprovação do modelo.

## 2026-10-07 · Margem de fluxos comparáveis

Contexto: o fallback de receita homogênea podia terminar em exercício diferente do EBIT corrente.
→ Decisão: certificar janela de 12 meses, moeda/base e proveniência antes de formar margem no
contexto e no modelo. Pares anuais conservam o mínimo histórico de três; margem corrente ausente
não recebe fallback parcial da histórica no FCFF normalizado. → Consequências: valores reportados
preservados, razões incompatíveis ausentes com fontes/motivo. A/TTM com mesmo fim certificado são
compatíveis. A política nova exige chave explícita; parâmetros arquivados sem ela ficam iguais.
A guarda não constitui normalização de eventos, imposto ou perímetro econômico entre exercícios.

## 2026-10-07 · Avaliação prospectiva por mente e canal

Contexto: o tracker antigo não era alimentado pelo ciclo operacional nem separava autoria.
→ Decisão: runtime sela sinais, entradas brutas e base antes da otimização; decisão os ancora,
fechamento futuro resolve com fontes autenticadas. Autoria ausente/externa permanece diagnóstico,
fora do IC confirmado; quant não tem informação incremental contra si próprio. → Consequências:
reconciliação idempotente sem outra ordem/decisão, ausência de preço/FX/macro mantém null, leitura
por CLI e recomendação de fase sem escrita no mandato. Probabilidade/evento/horizonte explícitos
são pré-condição do Brier; convicção ordinal não os substitui. Livros antigos não são preenchidos
retroativamente. A avaliação sintética confirma mecanismos, sem demonstrar mérito econômico.

## 2026-10-07 · Origem e recuperação do ensaio operacional

Contexto: um relógio histórico não comprova autoria prospectiva; a integridade do livro não
autentica um resultado de etapa ainda sem selo. → Decisão: origem retrospectiva imutável,
ancorada no início, excluída do IC prospectivo em todos os modos. Etapas exigem arquivo,
âncora e cadeia; recuperação de arquivo sem âncora é recusada. Artefatos canônicos existentes
exigem recibos correspondentes. → Consequências: interrupções ambíguas ficam incompletas,
sem nova ordem ou autoaprovação. A conclusão pode ser recuperada somente pelo recálculo exato
e inventário completo. Ensaios permanecem internos, com configuração contrafactual declarada,
sem publicação ou mudança do mandato oficial. O aceite técnico completo continua pendente.

## 2026-10-07 · Custódia física da demonstração

Contexto: o painel reaberto consultava a fonte física do risco, mas a demo só conservava o
mercado em memória. → Decisão: arquivar cada prefixo antes do seu primeiro uso e executar a
demo com o mesmo `MarketStore` canônico usado na reabertura. → Consequências: leitor,
runtime e autenticação confrontam os mesmos bytes; perda/adulteração continua falhando
fechada. Dados simulados permanecem explícitos; macro ausente não se converte em zero.
A correção não preenche livros históricos e depende do aceite técnico do lote completo.

## 2026-10-07 · Preços e conhecimento com cortes distintos

Contexto: a montagem semanal atualiza os modelos durante a manhã usando o fechamento
anterior; a data do preço não pode representar o conhecimento de documentos capturados no
dia da decisão. → Decisão: a política temporal `.8` sela base do preço, data do modelo,
instante de conhecimento e início/fim da coleta. Execução atual com relógio explícito pode
fechar o corte após a coleta; um corte histórico fixo não avança. A seleção do modelo exige
conhecimento disponível no instante da decisão. → Consequências: capturas não são
retrodatadas, documentos futuros continuam ausentes e reservas reutilizam somente retrato
íntegro da mesma base/configuração. Arquivos e parâmetros legados sem a chave nova mantêm
o contrato anterior. A separação não certifica PIT intradiário dos demais provedores nem
eficácia econômica; integração e aceite técnico da versão ainda estão pendentes.

## 2026-10-07 · Precisão da disponibilidade arquivada

Contexto: truncar uma captura para segundos podia admitir bytes recebidos depois de um
corte no mesmo segundo. → Decisão: novas capturas sob a política temporal preservam UTC
com microssegundos e seu marcador no próprio registro, índice e envelope. Registros legados
sem marcador carregam incerteza de até um segundo e só ficam disponíveis, na política nova,
a partir desse limite superior. → Consequências: leitura por chave, hash e catálogo segue o
mesmo limite; o envelope histórico sem a política mantém formato e hashes anteriores.
Fatos/PDFs simulados verificam o mecanismo e não são adotados como contabilidade real.

## 2026-10-07 · Domínio de cotação finito e janela comum de evento societário

Contexto: drivers isolados com zero/infinito mostraram marcação não finita, erro no logaritmo
e divergência do risco frente à ausência. → Decisão: preços locais, FX e seus produtos derivados
precisam ser finitos e positivos; dado inválido permanece ausente nos derivados, sem alterar
entrada. Retornos negativos legítimos conservam seu sinal. Eventos societários comparam preço
bruto e ajustado nas mesmas duas datas válidas; sem essa janela comum não há evento presumido.
→ Consequências: posição não reprecificada conserva ações/valor e alerta; catch-up usa o retorno
ajustado posterior e nunca cria fill atrasado. As regras de capacidade/custos e o carry limitado
do FX não mudam. Baseline e contrafactuais completos foram conferidos independentemente antes
do transplante delimitado para desenvolvimento; integração ainda depende da suíte ampla.

## 2026-10-07 · Git pertence exclusivamente à raiz informada

Contexto: uma raiz temporária de teste dentro do projeto, sem Git próprio, herdou o remoto pai
e criou a trava distribuída. → Decisão: toda chamada Git do executor limita a descoberta ao
pai da raiz informada, em variável de ambiente exclusiva do subprocesso; tetos existentes são
preservados. As fixtures Git inicializam seu próprio repositório, com remotos exclusivamente
locais nos testes. → Consequências: raiz sem Git próprio falha fechada antes de consultar/gravar
a trava do pai; raiz normal, bare e worktree continuam válidos. A trava acidental foi liberada
pelo ID comprovado no registro do próprio teste, sem force ou exclusão de ramo; `main`, mandato
e arquivos do executor foram preservados. Não é uma autorização para remover a trava de outro.

## 2026-10-07 · Aceite técnico do lote temporal e limites científicos

Contexto: a suíte ampla 5 concluiu sem falhas/erros após os reparos delimitados de fontes,
fixtures, cotações e isolamento Git; os 351 arquivos testados permaneceram iguais.
→ Decisão: aceitar tecnicamente a metodologia `2026-10.8` com a suíte completa de 2.582
casos (2.565 aprovados, 16 pulados, um xfail) e Ruff, mantendo as provas anteriores como
histórico. Conferência independente também confirmou os 189 arquivos da fonte física final.
→ Consequências: o lote pode seguir à integração autorizada; aprovação técnica não libera
P0, cuja confiança C permanece 43,78%, nem certifica eficácia econômica, PIT ou E1 integral.
Provas delimitadas de atraso e dados ausentes não substituem os casos ainda abertos.
Giro, capital por classe e RI por captura observada continuam protótipos privados; associação
de entidade a IID e disponibilidade precisam estar autenticadas antes do consumo operacional.

## 2026-10-07 · Barra provisória na composição e no booking histórico

Contexto: a composição do MarketStore reconstruía o manifesto sem os marcadores de barra
provisória e permitia concluir um fechamento indevido no driver. O primeiro reparo conservou
as marcas, mas transportava o carimbo de uma barra futura para a visão histórica parcial.
→ Decisão: conservar todas as datas provisórias elegíveis; sem mapa de horário por data,
qualquer corte da lista original deixa o carimbo único desconhecido na visão composta.
A visão completa conserva o horário literal e o manifesto bruto/SHA permanecem na custódia.
A conformidade de cada booking exige fechamento oficial no vintage do próprio pregão; uma
marca futura não reinterpreta o booking anterior. → Consequências: fechamento provisório
recusa MOC e NAV, inclusive na manutenção da carteira; decisão já selada não é reescrita.
Testes portáveis devem criar suas próprias fontes/livros e demonstrar as falhas antigas com
as mesmas asserções. Drivers novos e revisão independente delimitam o aceite; integração
ainda depende de suíte ampla e Ruff. Metodologia financeira, mandato e gates permanecem.

## 2026-10-07 · Confirmação documental de escala não encerra diagnóstico econômico

Contexto: a heurística descartou as aplicações reportadas pela Intelbras como erro de escala;
reextração independente dos formatos do mesmo filing confirmou o saldo e sua unidade.
→ Decisão: uma futura confirmação documental deve ligar entidade, conta, base, competência,
unidade e bytes autenticados no corte antes de resolver somente o descarte de escala.
Concordância dos formatos não certifica primeira publicação/PIT nem equivale a corroboradores
econômicos independentes. → Consequências: movimentação não reconciliada e mensuração
conflitante permanecem explícitas; aplicações já incluídas em caixa não são somadas novamente.
O contrato é privado, sem implementação ou alteração de modelos/confiança/gates nesta decisão.

## 2026-10-07 · Limite da CI compatível com a suíte completa

Contexto: o runner público cancelou a CI após 45 minutos, com último progresso em 58% e
sem resultado final. → Decisão: ampliar o limite a 90 minutos, manter os mesmos testes e
gravação de JUnit/tempos com artefato para conferência. → Consequências: cancelamento permanece
resultado incompleto; aprovação requer término e resultado integral. A alteração ainda em
DEV segue no próximo lote, sem diminuir casos nem transformar aprovação local em remota.

## 2026-10-07 · Mente explícita nos comandos de tese e nota

Contexto: a suíte completa em `CDP_HARNESS=codex` recusou exemplos de outras mentes,
pois instruções do pacote omitiam o argumento aceito pela CLI e herdavam o ambiente.
→ Decisão: comandos gerados de validação e publicação carregam a mesma mente escolhida
para o exemplo. Fixtures com outro autor também o declaram explicitamente; testes
exercitam ambientes distintos, mantendo a comparação de autoria. → Consequências:
`--mind` explícito continua prioritário, mente divergente continua recusada e nenhum
rascunho recebe autoria do ambiente por conveniência. A CI usa o harness Codex para
exercitar essa situação. Ampla 6 permanece falha; focais privados e revisão delimitada
não substituem nova suíte completa antes da integração.

## 2026-10-07 · Espera opcional da própria janela de rotina

Contexto: uma chamada nativa entrou poucos minutos antes do horário nominal e o gate
recusou corretamente o slot anterior. Origem automática/Run Now não foi certificada.
→ Decisão: `--aguardar-horario` aguarda somente o próximo cron da própria tarefa hoje,
em até 300 segundos, antes de construir Runtime, avaliar, adquirir ou registrar.
Depois da espera, configuração e relógio são novos; o gate é avaliado uma vez, com
as guardas existentes. Sem flag/fora desse recorte, comportamento ordinário preservado.
→ Consequências: nenhum horário, tolerância, TTL, mandato ou RRULE muda. Interrupção
da espera recusa sem efeitos; interrupção posterior mantém propagação original.
Prompts com publicação pelo agente usam a flag; manual/executor permanecem iguais.
Plugin 1.5.3 e testes portáveis foram revisados; transposição literal ao DEV, integração
depende da suíte ampla. Não certifica pontualidade nem prontidão financeira.

## 2026-10-07 · Aceite técnico após a ampla 7

A suíte completa com harness Codex concluiu verde: 2.628 aprovados, 16 pulados e
um xfail em 2.645 casos, sem falhas ou erros; 629 arquivos preservados durante o
teste e Ruff completo aprovado. → Decisão: integrar normalmente o lote de barras
provisórias, mente explícita e espera da própria rotina. Este registro documental
posterior não altera código ou configuração testados. Conferir identidade e livro
após sincronizar o executor. → Limite: o aceite é técnico; não promove protótipos
RI/custos, não certifica disparo pontual e não encerra P0, E1 integral, PIT/E2 ou carteira.

## 2026-10-07 · Identificação explícita da D&A restituída na DFC

Contexto: o adapter Yahoo identificava a rubrica da DFC, mas a camada de fatos publicava
apenas o item genérico `d_a`, impedindo o consumidor de reconhecer `d_a_dfc`. A revisão
financeira encontrou sete raw que demonstram o problema, sem erro aritmético de FCFF.
→ Decisão: preservar literalmente o item genérico e seus consumidores; acrescentar
`d_a_dfc` somente da rubrica explicitamente extraída da DFC e aprovada nos filtros
existentes. DRE não completa DFC, dado ausente não vira zero e publicação estimada
permanece estimada. → Consequências: o alias não altera fórmula, não certifica por si
só restituição primária completa ou identidade FCFF e não elimina falta de Δgiro/ROU.
AURA conserva a seleção defasada e a prioridade legada dos rótulos. Revisão independente,
oráculo Decimal e regressão portátil delimitam o reparo; transposição em DEV depende de
nova validação integral e integração. Mandato, metodologia `2026-10.8` e gates mantidos.

## 2026-10-07 · Resultado remoto do lote 887f744

CI remota dos dois jobs concluída com sucesso; JUnit efetivamente baixado confirma
2.645 casos sem falhas ou erros, 17 skipped incluindo xfail. O aceite técnico refere-se
somente ao commit testado e seus arquivos, com recibos da integração 11. Não transfere
esse resultado para novos candidatos privados ou transpostos ao DEV, nem encerra
P0/E1 integral/PIT/E2 ou libera publicação/carteira inaugural.

## 2026-10-07 · Comissão por ordem planejada e preenchida; ausência preservada

Contexto: o pico mexicano podia compartilhar indevidamente o mínimo com a ordem padrão.
A correção financeira v2 e os leitores receberam revisão independente delimitada.
→ Decisão: decompor as ordens e somar, em cada uma, o maior entre comissão variável e piso.
Na previsão, substituir apenas a comissão efetivamente incluída na mesma base; no débito,
usar preenchimentos, preços, câmbio e mandato arquivados do pregão. O contrato prospectivo
é incorporado antes do hash/aprovação. Ausência literal v0 e descritor histórico v1 conservam
suas fórmulas e selos; não se reestampa uma proposta antiga. → Consequências: previsão v2
integralmente indisponível continua None/n/d; zero explícito e ausência de ordens continuam
zero, previsão mista conserva subtotal e indicação parcial. Solver, mandato e gates não mudam.
Transposição em DEV com 201 focais e Ruff verdes ainda depende de ampla/integração. Não libera
P0/E1 integral/PIT/E2 nem autoriza carteira ou publicação fora do fluxo canônico.

## 2026-10-07 · API RI opt-in e guarda ETF vazia

Contexto: modelos do universo misto precisam consumir somente fatos reextraídos com
autoridade externa, identidade, moeda e corte explícitos. A API anterior deixava o caminho
vazio de ETF ignorar parte das guardas. → Decisão: validar também a entrada vazia, manter
o default sem opt-in literal e exigir fornecedor tipado ligado à autoridade externa no
opt-in. Publicação/recebimento desconhecidos permanecem nulos e PIT falso. → Consequências:
API v2 e anexo portátil revisados foram transpostos ao DEV, com 44 focais e Ruff verdes.
A coleta/gravação/reprodução normal permanece privada; metadados do livro não podem ser
autoridade de si mesmos. Ampla e integração ainda pendentes. Não muda metodologia,
mandato, gates ou limite P0 e não libera carteira inaugural.

## 2026-10-07 · Aceite técnico delimitado após a ampla 8

A ampla local concluiu 2.801 casos: 2.784 aprovados, 16 pulados, um xfail e zero falhas/
erros; 652 arquivos permaneceram intactos e Ruff completo passou. → Decisão: integrar
normalmente o lote revisado de custos por ordem/leitores, Yahoo D&A DFC e API RI opt-in,
sem force push e preservando estado operacional. Este registro posterior altera somente
documentação; fonte, fixtures e configuração testados são os mesmos. → Limite: ligação
RI ao fluxo normal, CVM nativo prospectivo, atribuição por estágios, CI deste novo commit,
P0/E1 integral/PIT/E2 e carteira inaugural não recebem aceite desta suíte técnica.

## 2026-10-07 · Limite estrutural não substitui recebimento prospectivo da autoridade

O CVM nativo v2 privado recusa criação futura e disponibilidade anterior à completude
local. A revisão independente confirmou o reparo estrutural R1, mas a entrega externa do
digest é posterior ao limite físico. → Decisão: manter o candidato privado; integração
prospectiva exige handoff tipado externo, SHA fixado e recebimento autenticado como
dependência temporal. Nenhum horário de arquivo, captura ou entrega se torna publicação
financeira. → Consequências: origens locais e ausência de certificado entre hosts ficam
explícitas; PIT falso, pub/received nulos, residual e classificação não são promovidos.
