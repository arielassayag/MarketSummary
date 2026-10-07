# Em andamento — passagem de bastão entre sessões (qualquer app de IA)

Documento vivo. Quem encerra uma sessão de desenvolvimento atualiza este arquivo: o que mudou, o
que falta, riscos. Quem chega — no Claude Code, no Codex, no Gemini ou em outro app — lê aqui
antes de mexer em qualquer coisa (`AGENTS.md`, seção 1). Decisões já tomadas, com data e
motivo: `docs/cdp/DECISOES.md`.

Última atualização: 2026-10-07, 09:12, Brasília — lote `.8` integrado, P0 científico aberto. **Comece por
`docs/cdp/PASSAGEM_CODEX.md`**: ligar as rotinas no Codex, P0 de desenvolvimento antes do
retrato-gênese da cobertura (qua 07/10, 19:22) e cronograma até a carteira inaugural (sex 09/10).

## Desenvolvimento científico e agendas — 07/10/2026, madrugada

- Fechamento técnico atual: suíte ampla 5 completa, 2.565 aprovados, 16 pulados e um
  xfail, zero falhas/erros em 2.582 casos; Ruff aprovado. Antes da atualização documental,
  os 351 arquivos congelados continuavam iguais, assim como os 79 arquivos operacionais,
  cinco arquivos locais do Fechamento e mandato. Conferência independente confirmou
  os 351 hashes e os 189 arquivos da fonte física 8-5. A metodologia é `2026-10.8`;
  8-5 identifica uma cópia física, não uma nova versão metodológica. Código `44fa149`
  integrado por fast-forward, enviado ao GitHub e sincronizado no executor pelo comando
  canônico; identidade, integridade e estado verdes. O portal desse código foi confirmado
  no ar (manifesto, três rotas HTTP e valuation iguais ao executor). Às 09:11, a CI
  37617785317 ainda estava nos testes; o job de livro/rotinas/skills/portal havia passado.
  Registro documental posterior não altera o núcleo testado nem os bytes operacionais.
- Os ensaios finais dessa fonte concluíram 233 empresas/oito ETFs e 23 pregões/cinco
  montagens/94 etapas. Os CSVs de modelos e ETFs são iguais aos da fonte temporal anterior;
  JSONs de cobertura diferem somente nos instantes de conhecimento e hashes derivados.
  A comparação do replay preserva a economia; tempos do solver e hashes de encadeamento
  podem diferir. Os quatro livros históricos `.4`–`.7` foram conferidos sem alteração.
  Confiança C permanece 102/233 (43,78%), acima de 35%; Compra, Venda e revisão passam.
- Novo episódio completo de atraso em fechamento antecipado: 11 pregões, duas montagens,
  48 etapas e 25 posições anteriores; decisão um segundo depois da margem foi recusada,
  preservando ações, sem proposta, booking ou custo naquele dia. Integridade e retomada
  selada passaram, com revisão independente. Dados simulados e alteração contrafactual
  somente da data de início; o episódio fecha esse caso delimitado, não toda a matriz E1.
- Protótipos privados, fora da integração: giro v4 teve 99 focais e revisão independente
  verdes, inclusive fuso omitido e competência futura recusados; faltam insumos e adapter
  reais. Capital por classe teve 41 focais, com associação AFYA→STONE e disponibilidade
  futura recusadas; unidades reais continuam ausentes e G13c bloqueado. Patrimônio AMX
  foi reextraído de PDF oficial e conferido independentemente, com identidades exatas;
  publicação inicial desconhecida. Extrator privado por captura observada passou 39 focais,
  mas a revisão reproduziu associação entidade→IID aberta: não pode alimentar modelos
  ou gates até fechar esse vínculo. Nenhum protótipo altera o livro oficial.
- Atualização do lote temporal: o coletor completo real da fonte física 8.4 concluiu 233
  empresas e oito ETFs, com recálculo integral verde. O replay real dessa fonte concluiu
  23 pregões, cinco montagens e 94 etapas; a comparação somente leitura com a fonte 7
  encontrou posições, propostas, custos, P&L, risco e atribuição exatamente iguais.
  Os quatro livros `.4`–`.7` foram verificados integralmente sem alterar seus bytes.
  São ensaios privados retrospectivos. O executor oficial recebeu o código `.8`, conservando
  o livro em pré-início; nenhum desses ensaios foi adotado como operação oficial.
- A suíte ampla 4 terminou: 2.475 aprovados, 32 falhas, um erro, 16 pulados e um xfail;
  os 349 hashes de origem permaneceram intactos. As fixtures agora reabrem/copiam mercado
  físico com o livro; 109 casos distintos passaram em validações privadas, conservando
  as asserções, exceto duas alterações documentadas no relatório: copiar sua fonte física
  e substituir a premissa de liquidez integral por um oráculo independente que conserva
  o preço/volume ausente e a limitação parcial. Três falhas de risco/rotina também passaram
  em cópia privada. Não somar focais sobrepostos como uma suíte completa.
- Preços zero/infinito no driver completo revelaram falhas nos consumidores de marcação,
  retorno, painel e evento societário. Reparo privado v3 aprovado independentemente:
  quatro contrafactuais e baseline, sete pregões/duas montagens cada, íntegros e idempotentes;
  economia e risco de zero/infinito equivalentes à ausência, sem modificar brutos;
  baseline normal com 6.950 campos numéricos e quatro CSVs financeiros exatamente iguais.
  Os três consumidores, 54 testes materiais e as fixtures delimitadas foram transpostos
  para DEV; a suíte ampla 5 confirmou sua integração técnica. E1 integral e E2 seguem abertos.
- O teste de gate em pasta sem Git próprio herdou o repositório pai e criou uma trava remota.
  O registro comprovou o ID do próprio teste; a trava foi liberada por esse ID, sem force,
  preservando `main` e os arquivos oficiais. Fixtures Git agora são isoladas e a descoberta
  Git fica limitada à raiz informada por chamada. Revisão independente de cinco regressões
  locais, incluindo raiz normal, bare, worktree e ambiente intacto, passou. Guardas e três
  regressões portáveis foram transpostas, validadas na ampla 5 e integradas no executor.

- Próximo lote após `.6`, em desenvolvimento: correção macro diária com modelos base/evento
  sobre posições efetivas, atribuição macro observada antes da regressão estrutural e sidecar
  autenticado sem alterar bytes históricos. Congelamento com 93 focais e revisão independente
  com 28 focais verdes; não confundir esses grupos sobrepostos com uma suíte ampla concluída.
- Ensaio operacional isolado: novo `backtest-operacional`, origem retrospectiva autenticada
  fora do IC prospectivo, prefixos temporais, ações/capacidade/contabilidade canônicas e cadeia
  de etapas. Passaram 62 focais, incluindo capacidade parcial, próxima decisão usando o
  patrimônio/carteira efetivos, recibos de artefatos, vintage da execução e alteração de séries
  futuras sem efeito passado. [Contrato e limites](REPLAY_OPERACIONAL.md). Matriz E1 e
  ensaio real sombra concluiu 23 pregões e cinco montagens canônicas, com 94 etapas. A
  repetição na fonte final de FX/preço também terminou íntegra; revisão independente concluída.
  A economia dos 23 registros foi idêntica à sombra anterior, nas sessões normais observadas;
  isso não exercita as cotações ausentes, cuja correção tem focais próprios.
  A matriz E1 separa episódios completos de provas de APIs e mantém as lacunas explícitas.
  A ampliação de dados ausentes encontrou falha material: sem FX no próprio pregão, o MOC
  negociou usando o valor anterior. O código corrigido exige FX, preço e volume próprios;
  posição sem FX/preço congela o emissor inteiro, inclusive a abertura de outra linha. Passaram
  105 focais distintos de execução, diário e dados ausentes. A suíte ampla 5 concluiu verde;
  as rodadas interrompidas foram preservadas como diagnóstico. A terceira rodada
  parou no painel da demonstração: o leitor físico do risco procura `market/base`, enquanto
  a demo usa mercado em memória. A demo agora arquiva cada prefixo antes do primeiro uso e
  consome o `MarketStore` canônico; 14 focais passaram, incluindo reabertura e recusa de
  perda/adulteração de fonte. Duas demos novas, legada e vigente, passaram offline. A raiz
  temporária da falha original ficou indisponível; log/XML da terceira rodada são a evidência
  histórica preservada. Revisão independente do reparo passou, incluindo painel sem override
  e recusas por remoção de preços/adulteração de FX. A fixture da avaliação foi corrigida
  para reabrir essa mesma fonte física: 23 testes passaram, preservando todas as asserções;
  revisão independente confirmou a custódia. Lote agora integrado, com ampla 5 verde.
- Ponte `.7` de EBIT após ajustes evidenciados: contrato explícito com fonte, período e
  disponibilidade; valores reportados preservados, sem imposto/EPS imputados. Quatro bordas gerais de
  extração/período/captura corrigidas, 193 focais verdes e revisão independente concluída.
  Recálculo completo `.4/.5/.6` repetido, preservando os 768 arquivos de cada retrato. Novo
  ensaio real sombra concluído: 233 emissores e oito ETFs, 188 fontes preservadas. Compra
  40/203 (19,70%), Venda 38/203 (18,72%) e revisão 27/233 (11,59%) passam os limites da
  passagem; confiança C 102/233 (43,78%) continua acima de 35%. Giro comercial parcial
  continua insuficiente para certificar ΔWC/FCFF; não há relaxamento dos gates P0.
- Integração temporal `.8`, em desenvolvimento: a cobertura semanal precisa usar preços do
  fechamento anterior e conhecimento do instante da execução. A ponte `.7` confundia esses
  cortes e recusava o catálogo atual no pacote datado pelo preço. A política nova sela
  `base_preco`, `data_modelo`, `conhecimento_ate` e etapas de coleta, sem retrodatação; inclui
  seleção pelo conhecimento disponível e ligação aos fatos/SHADOW da decisão. Capturas
  posteriores ao corte continuam recusadas. Parâmetros arquivados sem a chave temporal
  conservam a política anterior. A revisão encontrou duas falhas de precisão e seleção:
  captura futura no mesmo dia e truncamento dentro do mesmo segundo. A correção exige o
  instante UTC disponível, preserva microssegundos novos e admite carimbos legados somente
  após o limite superior do segundo truncado. Os focais passaram; revisão independente
  confirmou as recusas. O episódio com preços reais e dois PDFs simulados capturados na
  execução ligou documento, ajuste, fatos e SHADOW à montagem, com reserva idempotente e
  livro íntegro. Esse episódio testa mecanismos; não constitui evidência contábil real.
  A ponte e os ensaios `.7` permanecem históricos. Os ensaios reais da fonte temporal 8.4
  concluíram; a suíte ampla 5 após os reparos delimitados passou e o executor recebeu `.8`.
- As 12 automações foram conferidas novamente: ativas, projeto atual, modo local, executor
  interno `.cdp/rotinas`. Nomes em seis famílias (operação, carteira, risco, fechamento,
  pesquisa, modelos), reservas explícitas e prompts que consultam o procedimento vigente
  pelo código. Agenda local em `.cdp/AGENDAS.md`; entregas em `.cdp/TAREFAS.md`. Horários,
  modelos e preferências de notificação preservados. Primeiro disparo ainda não observado.
- Ramo científico `codex/cdp-modelos-completos`, checkout `.cdp/desenvolvimento`, dentro do
  projeto. O executor continua em `main`; o lote foi integrado após suíte e Ruff verdes.
  As cinco alterações locais anteriores do Fechamento permanecem na raiz, com os mesmos hashes.
- Consenso: os bytes arquivados da Orbia declaram USD. A regra anterior converteu USD para
  MXN duas vezes porque a primeira conversão não enquadrava o LPA numa faixa contra o lucro
  realizado. A política `declaracao_fonte` aplica somente moeda declarada, paridade e câmbio;
  valor distante do realizado sinaliza revisão analítica. Moeda desconhecida fica ausente.
  Ensaio de unidades em `.cdp/ensaios/20261007-consenso`; testes de conversão única, ausência,
  segundo exercício e preservação da política histórica passaram.
- Metodologia `2026-10.5` integrada em `main` e no executor, commit `f317709`: reinvestimento não alavancado pela identidade de capital
  investido, com arrendamentos capitalizados e componentes publicados, alinhados em período,
  moeda e base de consolidação, inclusive dentro das identidades TTM. Principal
  de dívida não é nova aquisição de ativo. Adições ROU, D&A restituída na DFC e capital de
  giro precisam da própria fonte; falta de componente leva lacuna e projeção teórica explícita.
  A média histórica é diagnóstico; a observação recente completa define os anos iniciais.
  Parâmetros arquivados sem as chaves novas mantêm a política anterior: o recálculo integral
  do ensaio .4 passou também com o código novo em conferência explícita de compatibilidade.
- Fontes SEC: índice oficial permite localizar a instância XML do documento principal,
  mesmo quando o HTML recebe 403. Capturados núcleos financeiros de 2025 para sete nomes
  defasados. Classes da capa só se somam com enumeração completa curada, CIK/accession/datas
  e hash; nenhum contexto financeiro dimensional é admitido por essa exceção. Fibra Mty tem
  parser do PDF oficial com datas publicadas e BP/DRE/DFC/CBFIs, sem valores financeiros
  transcritos no catálogo. Os testes de fontes e de ausência/zero passaram. JBS conserva
  divergências nas fontes da mesma N.V.: FRE aprovado em 2025 não confirma junho/2026; capa,
  nota e tags inline diferem em definição/data/escala. A soma mecânica da capa não comprova
  conciliação independente. Evidência em `20261007-fontes/JBS_CONCILIACAO.md`.
- Evidência nova em `.cdp/ensaios/20261007-fontes/cache-real` registra re-arquivo de bytes
  oficiais com horário UTC real. Um cache de ensaio com relógio fixo futuro foi identificado,
  preservado e excluído da evidência real. Insumos capturados em 07/10 não são retrodatados
  para gerar um retrato PIT de 06/10; análise com preços de 06/10 é sombra explicitamente
  datada. Nenhum desses arquivos foi adotado no livro oficial.
- Auditoria independente em `.cdp/validacoes/20261007-auditoria/REQUISITOS.md`: 132 focais e
  recálculo 233 empresas/oito ETFs passaram no baseline congelado. Foram confirmadas lacunas
  de backtest (macro/segundo modelo/efetivação MOC histórica), integração operacional do IC
  por mente e definição de Brier. Macro, modelo-base, modelo de decisão, atribuição e IC
  foram integrados: 55 testes focados e ensaio real com 23 datas, seis decisões e 233
  identidades passaram. A semana truncada gera decisão extra em 06/10; o ensaio não comprova
  calendário/execução MOC, histórico integralmente PIT ou mérito estatístico. Demais lacunas
  permanecem na matriz. Relatório em `20261007-backtest-integracao/RELATORIO.md`.
- Revisão independente corrigiu quatro defeitos estruturais (bases entre componentes,
  datas nulas, sinal de adições ROU e bases internas do TTM); 92 testes focados finais
  passaram. Prova de compatibilidade integral .4 repetida depois das guardas finais, em
  `.cdp/validacoes/20261007-compatibilidade-congelada.json`. Suíte completa final passou:
  2.177 testes, 17 pulados/xfail, sem falha/erro; Ruff, documentação, rotinas e skills verdes.
  O teste G14 foi corrigido para conferir os textos de ambas as políticas, com severidade
  preservada. Evidência em `.cdp/validacoes/20261007-suite-cdp-final.xml`.
- Novo ensaio completo `.cdp/ensaios/20261007-modelos-sombra`: 233 empresas e oito ETFs,
  preços de 06/10 e fontes capturadas em 07/10, datas separadas, código/configuração selados.
  Livro, arquivos, trilha e modelos passaram no recálculo integral. Dos 200 publicáveis,
  Compra 37 (18,50%) e Venda 31 (15,50%) passam; C 107/233 (45,92%) e revisão 30/233
  (12,88%) ainda falham. Aceite científico permanece aberto: analisar causas por emissor;
  não se afrouxam portões, limites ou mandato para atingir quotas. Não é livro oficial.
- Lote `2026-10.6` integrado em `main` e no executor, commit `b78d725`: G17 passa a distinguir capex/D&A
  comprovadamente sem dependência nos métodos financeiros conhecidos. Os alertas originais
  e a prova ficam arquivados; estruturas desconhecidas conservam a severidade. Revisão
  independente e focais passaram. Ensaio com os pacotes .5 exatos em
  `20261007-g17-dependencias/resultado`: 71.037 campos econômicos dos 233 modelos idênticos,
  seis C→B; Compra 19,00%, Venda 17,00%, C 43,35% e revisão 12,88%. P0 segue aberto.
  Seis ETFs mudam pela elegibilidade A/B no bottom-up; top-down permanece igual, e o
  contrafactual com classificações anteriores reproduz os oito ETFs. Sem mudança de mandato.
- Comparabilidade da receita, publicação e margem — lote .6 congelado e integrado:
  conceitos explícitos desconhecidos não permitem derivação; composição identificada registra
  publicação máxima e a trilha de todos os componentes. Receita/EBIT só formam margem quando
  demonstram a mesma janela de 12 meses, moeda e base. Valores originais preservados;
  incompatibilidade corrente/histórica fica ausente com diagnóstico. Não certifica recorrência
  ou homogeneidade do perímetro entre exercícios. Focais e revisão independentes passaram.
  Ensaio completo `20261007-modelos-completos-6-final`: 233 empresas, oito ETFs, 181 fontes congeladas,
  recálculo integral íntegro. Compra 39 (19,40%), Venda 37 (18,41%), C 102/233 (43,78%) e revisão 29/233 (12,45%). Compra/Venda passam; C/revisão ainda falham.
  Preços de 06/10, fontes conhecidas em 07/10, modelos em 07/10; sombra, nunca retrato oficial retroativo.
  O primeiro ensaio de fontes foi preservado como provisório, com bordas corrigidas depois.
- Pré-registro por mente/canal integrado: autoria observada,
  sinais/base ancorados antes da otimização, vínculo à decisão e outcomes futuros autenticados.
  `cdp avaliacao status` e `cdp avaliacao ic --mind codex` é somente leitura; recomendação não muda fase/mandato. Brier ausente,
  N=0, sem converter ordinais. 145 focais do runtime e 217 da revisão independente passaram;
  três testes CLI passaram. Ensaio Friday→Friday com mandato intacto: livro íntegro/idempotente,
  primeiro outcome sem resíduos válidos por ausência dos quatro macros; segunda coorte imatura.
  Probes de identidade são DADOS SIMULADOS, sem evidência de eficácia ou promoção de fase.
- Compatibilidade final .6: recálculos integrais explícitos .4 e .5 passaram com as configurações
  arquivadas; 233 empresas e oito ETFs em cada ensaio, arquivos históricos preservados.
  Suíte ampla final .6: 2.325 passaram, 17 pulados/xfail, zero falhas/erros;
  Ruff, documentação, rotinas e skills verdes. Integração em `main` e no executor por fast-forward;
  181 fontes iguais ao ensaio final, 79 arquivos operacionais/locais e os cinco arquivos de trabalho
  do Fechamento preservados por SHA-256, mandato intacto. Executor íntegro e sem trava.
  CI `37577463582` concluída com sucesso para `fc8b091`; portal `.6` confirmado no ar.

## Retomada no Codex — 06/10/2026, noite

- **Rotinas ligadas:** 12 automações locais ativas no projeto atual do Codex. Por instrução
  expressa do titular, o clone das rotinas fica dentro deste projeto, em `.cdp/rotinas`, com
  `main` e identidade `local-pc`/`codex`. Os prompts usam explicitamente esse clone e as
  variáveis `CDP_HARNESS`, `TZ` e `PYTHONUTF8`; o checkout principal não é executor.
- **Infraestrutura conferida:** `executor verificar` retorna 0; livro íntegro, kill switch
  desligado, trava livre; push simulado autorizado para `main` e `cdp-trava`; ruleset 24618259
  ativo. Gates semanal e de risco sem pendência/fora da janela retornaram `executar: false`.
  As agendas persistidas das 12 automações conferem com a exportação canônica. O primeiro
  disparo agendado ainda deve ser observado; criação da tarefa não prova sua execução.
- **Organização local:** `.cdp/LEIA-ME.md` mapeia a instalação e `.cdp/TAREFAS.md`
  organiza as agendas e entregas. O projeto das rotinas está na seção CDP da barra lateral do
  Codex. A conversa foi nomeada "CDP — rotinas internas e validação P0"; o app ainda associa
  sua movimentação a uma chave provisória, sem confirmar a posição da conversa real. O checkout principal recebeu o
  CDP de `origin/main`, preservando as cinco alterações locais do Fechamento (GDELT), com
  backup em `.cdp/backups/` e stash preservado. Conflitos foram reconciliados mantendo as
  invariantes novas de dados e o código local; os nove testes do coletor passaram.
- **Painel fora do versionamento:** commit `621f3a3` remove apenas o índice Git da cópia local;
  `.gitkeep` e os arquivos físicos do executor foram preservados. Incorporado neste lote P0.
- **Correções técnicas P0 implementadas e validadas:** a suíte completa `tests/cdp` e o Ruff
  passaram; inspeção visual e verificações de rotinas, skills e documentação também passaram.
  G20 com corroboração independente,
  diagnóstico de cenários e metodologia `2026-10.4`; SEC submissions e XBRL/inline documental
  com datas oficiais e preservação de dados anteriores; alternativa XBRL/ZIP do RI oficial
  da Supervielle, vinculada ao arquivamento SEC, datas e SHA-256; séries PEN/UYU/CAD; contagem de ações
  e principal de arrendamentos; índice de referência na ficha de todos os ETFs; revisão
  mensal na integridade geral e no portal; permissões de `revisao.json`; cadência nova;
  nomes institucionais, plurais e notícias neutralizadas só na apresentação pública.
- **Ensaio real reproduzido, aceite científico ainda aberto:** retrato de 06/10 com método
  `2026-10.4`, câmbio suplementar e ZIP bruto de RI; 233 empresas e oito ETFs. Livro, arquivos,
  trilha e modelos passaram no recálculo integral. Compra 36/191 = 18,85% e Venda 32/191 =
  16,75% dos publicáveis passam 15–35%; C 114/233 = 48,93% e Em revisão 38/233 = 16,31%
  falham nos máximos de 35% e 12%. Números vêm dos arquivos gerados pelo código do ensaio.
  O P0 não está concluído só porque a integridade e os testes técnicos estão verdes.
- **Próxima frente científica:** as 38 revisões se dividem por prioridade em oito balanços
  defasados, oito bloqueios de insumos e 22 limites de saída. Confiança C exige revisão dos
  métodos, dispersão, peso terminal e fontes por emissor; não apagar portões para atingir
  metas. Supervielle tem balanço/fluxos de 31/12/2025, mas continua em revisão por LPA de
  consenso incoerente com lucro observado negativo. Petrobras exige conciliar pagamentos
  de arrendamentos (principal/juros/direitos de uso) e a suavização de reinvestimento frente
  ao plano atual; cenário unilateral e reprodução numérica não aprovam essas premissas.
  JBS continua com contagens não conciliadas; Telecom Argentina sem contagem recente;
  Volaris sem principal correspondente ao período mais recente. SEC Archives 403 nos demais
  arquivos fica registrado; nunca substituir ausência por número arbitrário.
- **Evidências locais:** `.cdp/validacoes/` guarda logs, conferências e previews;
  `.cdp/ensaios/` guarda retratos e fontes de reprodução. A validação visual confirmou índices
  de referência de ARGT e BOVA11 e alvo citável oculto para ativo em revisão. Nenhum ensaio
  foi adotado no livro oficial, nenhuma carteira foi decidida ou publicada nesta sessão.
- **Passo humano e disponibilidade:** a senha do operador ainda não estava definida na
  conferência; o titular deve usar `cdp kill-switch senha` num terminal próprio, fora de apps
  de IA. Não foi criada conta separada do sistema operacional: usa-se a instalação atual do
  Codex. App aberto e PC acordado continuam necessários. Primeiro disparo agendado ainda
  não observado.

## Como continuar (qualquer app)

1. `uv sync --extra dev --extra ai` e `uv run python -m cdp estado --formato md` (fase do fundo,
   executor, pendências, incidentes, próximo passo).
2. Leia as tabelas abaixo; escolha uma frente sem dono ativo ou continue a sua.
3. Trabalhe em ramo próprio; nunca grave `book/`, `data/`, `reports/`, `artifacts/` (só o
   executor grava, pelas rotinas).
4. Antes de propor um commit: `uv run pytest tests/cdp -q` e `uv run ruff check .`.
5. Ao encerrar, atualize este arquivo (o que mudou, o que falta, riscos) e, se decidiu algo,
   acrescente a entrada em `docs/cdp/DECISOES.md`.

## O que já está entregue

| Área | O que existe | Onde ler |
|---|---|---|
| Calendário e execução | regra do dia de montagem (último pregão da semana na NYSE), prazo efetivo, execução no leilão de fechamento com capacidade de liquidez | `docs/cdp/EXECUCAO.md`, `src/cdp/calendar.py`, `src/cdp/portfolio/execucao.py` |
| Construção e risco | otimizador com meta de risco idiossincrático (90%) e piso (85%), escada de relaxamento, escada de drawdown, gatilhos de perda, limites de short | `docs/cdp/METODOLOGIA.md` |
| Cobertura | modelos abertos e preços-alvo de 12 meses de todo o universo (ações e ETFs) só com dados públicos, livro encadeado, placar | `docs/cdp/COBERTURA.md`, `uv run python -m cdp cobertura verify` |
| Camada da mente | notas por emissor, relatório semanal de resultado, pacote da mente para qualquer assistente, guia de estilo | `docs/cdp/NOTAS.md`, `docs/cdp/REPRODUZIR.md`, `docs/cdp/ESTILO.md` |
| Pré-início | abertura do livro na data de início, uma única vez, pela primeira rotina do executor | `cdp reinicio` (simulação por padrão) |
| Operação em qualquer app | `cdp estado`, `cdp rotinas` (gate, prompts, exportação), `cdp executor`, `cdp trava`, `cdp sincronizar`, `cdp publicar`, `cdp entrega`, skills neutras em `.agents/skills/` | `AGENTS.md`, `docs/cdp/AUTOMACAO.md` |
| Portal público | `cdp site construir/conferir`, `.github/workflows/cdp-site.yml` (GitHub Pages) | `docs/cdp/SITE.md` |
| Integração contínua | `.github/workflows/cdp-ci.yml` (lint, testes, integridade, rotinas, skills, portal da demonstração) | — |
| Documentação | `AGENTS.md` como fonte única, arquitetura, automação dentro do app de IA, teste de consistência; licenças (Apache-2.0 + CC BY 4.0, confirmadas pelo titular em 06/10/2026) e aviso legal | `docs/cdp/ARQUITETURA.md`, `tests/cdp/test_docs_consistencia.py` |
| Cronograma e construção | stop de squeeze por nome, série de risco idiossincrático no monitor, kill switch desligado só por humano num terminal interativo, pedido de kill switch mesclável (`reports/risk/<data>/kill_switch_<HHMM>.yaml`, aplicado pela execução exclusiva seguinte ou por `cdp kill-switch aplicar-pedidos`; a agenda lista os pendentes) | `docs/cdp/EXECUCAO.md`, `docs/cdp/METODOLOGIA.md` |

## Correções do ensaio geral (06/10/2026, Codex como executor)

Feitas no código, nos roteiros e nas skills (suíte `tests/cdp` e ruff verdes):

- `weekly prepare` monta o briefing numa área temporária e promove de uma vez; falha no meio não
  trava a semana (briefing parcial antigo é afastado); cotação intradiária vazia é falha de coleta
  (análise no fechamento anterior); a agenda só conta briefing completo.
- Kill switch: `kill-switch off` exige a senha do operador (hash fora do repositório;
  `cdp kill-switch senha`), e `CDP_HARNESS`/`CODEX_*`/`ANTIGRAVITY_*` contam como contexto de
  agente; kill switch antes da carteira inaugural sai como status estruturado; prazo vencido no
  `weekly decide` sai como JSON (`prazo_vencido`), com texto próprio da inaugural.
- Modo ensaio: `CDP_AGORA` (relógio do cenário), `CDP_ENSAIO_SUBSTITUTO=1` (substituto de dados
  rotulado) e commit local com o trailer `CDP-Ensaio` (um clone com ensaio nunca publica).
- Mente: os validadores e as publicações recusam `mind` diferente da execução (`--mind` ou
  `CDP_HARNESS`), salvo rascunho entregue; exemplos com a mente da execução; o Codex é o app das
  rotinas (`configs/cdp/executor.yaml`, documentação neutra); `CDP_EXECUTOR` inválido é recusado.
- Dados: brutos volumosos da CVM e da SEC fora do git (índice versionado); portal publica só o
  último retrato completo da cobertura; BDI com tempo-limite curto e parada após 3 datas com
  falha; manchetes com padrão de instrução vão para a quarentena; filtro de relevância de notícias.
- Texto ao investidor: relatórios semanal e diário em pt-BR (nomes de empresas, rótulos, horário
  de Brasília, sem o nome do app); avisos técnicos de dados numa frase só; VOL_TARGET contra a meta
  aplicada; "(USD)" só nos benchmarks cotados em dólar e validador que recusa "em dólares" para
  fato em moeda local; nomes com acento (`configs/cdp/nomes.yaml`); portão G20 de plausibilidade
  do alvo (consenso, cenários, margem do G11); ADR com o alvo da própria classe (PBR ← PETR3).

Robustez para a carteira inaugural (mesma data, sobre as correções acima):

- **Rede ou Yahoo fora no `weekly prepare`**: fundamentos sem nenhuma linha com dado são falha de
  coleta (`yahoo.FundamentosVaziosError`), nunca um retrato vazio; linha sem dado (ou sem valor de
  mercado onde o gravado o tem) nunca substitui a gravada; short interest e notícias sem resposta
  mantêm os gravados; com Yahoo, FINRA e B3 sem resposta, as notícias nem são tentadas (rede
  fora). O prepare termina com os últimos dados gravados e devolve `aviso_coleta`; com a rede
  fora, `uv run python -m cdp weekly prepare --date 2026-10-09 --mind codex --offline` é a
  alternativa. Conferido numa cópia do livro com o proxy numa porta fechada: código 0 em 3m21s.
- **Kill switch no leilão do dia de montagem**: regra de caducidade (`docs/cdp/EXECUCAO.md`,
  seção 12) — o dia é registrado com a recusa (`efetivacao_recusada.json`, evento
  `BOOKING_LAPSED`) e a decisão nunca é efetivada depois; na inaugural, o histórico começa em
  caixa e a próxima data de montagem decide de novo.
- **Modo ensaio**: o substituto de dados copia os preços por série (cada linha parte da sua
  última barra real); o gancho `pre-push` instalado no ensaio recusa, mesmo fora do ensaio, o
  push de qualquer commit com o trailer `CDP-Ensaio`.
- **Portal**: a conferência de termos vedados isenta só as manchetes e os veículos de terceiros
  citados nas notícias públicas (`*news.jsonl`); o texto da casa continua conferido.
- **Texto ao investidor** (relatório da decisão, memorando da proposta, relatórios diário e
  semanal): controles, detalhes, cenários e fatores em pt-BR (`src/cdp/workflow/rotulos.py`),
  empresas pelo nome, sem nome de app ou provedor de IA (a autoria é "a gestão"), "carteira
  simulada" no lugar do termo em inglês, concordância de número ("1 pregão") e meta de vol
  aplicada ao lado da do mandato; o memorando resolve os fatos citados pela pesquisa.

Pendências que dependem do titular ou do commit (não são código):

- Decidir o histórico público de commits anterior à data de início (manter ou publicar um ramo
  novo) antes de 09/10. O painel local já saiu do versionamento, preservando `.gitkeep` e os
  arquivos físicos.
- **Senha do operador no PC do Codex**, num terminal próprio, antes de 09/10:
  `uv run python -m cdp kill-switch senha`. Sem ela, ninguém desliga o kill switch.
- Logotipo e imagem de compartilhamento com "ASSET MANAGEMENT" (arte da marca) e
  `fund.minds` (valor do mandato, entra no hash da configuração da gênese).
- Fora do escopo desta passagem: páginas estáticas por ativo (SEO), identidade visual dos
  relatórios HTML e da página de dados, gráfico de potencial no celular, tabela anual do lucro
  residual na memória de cálculo e arquivo das planilhas Damodaran no retrato.

## Frentes em andamento (2026-10-06)

| Frente | Estado | Próximo passo |
|---|---|---|
| Portal: aba "Modelo aberto" da cobertura e "Auditoria e reprodução"; perfil "site" do painel sem cortes | em desenvolvimento | revisar no portal real montado de uma cópia do livro; no portal da demonstração, só depois de a demonstração gerar cobertura e notas (integração pendente abaixo) |
| Calibração da cobertura (parâmetros de valuation e arquétipos) | em desenvolvimento | suíte da cobertura verde; retrato de 08/10 conferido por `cdp cobertura verify` |
| Skills, plugin e roteiros no envelope gate → `cdp sincronizar` → roteiro → `cdp publicar` → `cdp trava liberar`; exportação para as tarefas agendadas do Codex e do Antigravity (`--alvo codex`, `--alvo gemini`) | em desenvolvimento | `uv run python -m cdp skills verificar`, versão do plugin, tabela de `docs/cdp/ROTINAS.md` gerada |
| Ativação do mandato em `configs/cdp/fund.yaml` | **aplicada em 06/10/2026**; `agenda --agora 2026-10-09T11:07` dá `acao: montar` e prazo efetivo 15:00 | — |

## Cronograma até a primeira montagem regular (horário de Brasília)

| Data | O que acontece | Quem |
|---|---|---|
| ter 06/10 | integração das frentes acima; push em `main` só com a suíte e o ruff verdes | desenvolvimento |
| logo depois do push (no máximo qua 07/10) | **preparar o PC do Codex**: no clone dedicado das rotinas, `git pull --ff-only`; identidade com `uv run python -m cdp executor registrar --como local-pc --harness codex`; no `~/.codex/config.toml` da conta dedicada, acesso total, aprovação "never" e `CDP_HARNESS = "codex"`; recriar as 12 tarefas agendadas do app com os blocos de `uv run python -m cdp rotinas exportar --alvo codex --formato md`; **definir a senha do operador** (`cdp kill-switch senha`, terminal próprio); "Run now" em `cdp-status` e conferir em `uv run python -m cdp estado --formato md` que `executor.sou_o_executor` é verdadeiro (`docs/cdp/AUTOMACAO.md`, seção 5) | operador |
| qui 08/10, até 18:00 | código completo, revisado, suíte verde | desenvolvimento e titular |
| qui 08/10, noite | 19:22 rotina diária com o retrato da cobertura de 08/10; 22:37 notas de cobertura | executor (Codex) |
| sex 09/10 | **carteira inaugural**: 11:07 pesquisa e preparação, decisão até o prazo efetivo (15:00), execução no leilão de fechamento; 19:22 efetivação, primeiro registro diário, relatório semanal, portal | executor (Codex) |
| sáb 10/10, 10:07 | repescagem do fechamento, se necessário | executor |
| seg 12/10 | feriado na B3 com a NYSE aberta (pregão de dados) | rotinas |
| qui 15/10 | fechamento, retrato da cobertura e notas | rotinas |
| sex 16/10 | **primeira montagem regular** (com limites de giro), execução no leilão de fechamento e relatório semanal | rotinas |

## Riscos conhecidos

- **PC do Codex sem a identidade do clone**: se o PC não registrar o executor nem recriar as
  tarefas, as rotinas de quinta à noite (fechamento e notas) e as de sexta (11:07 a 14:07)
  respondem "Sem execução" e a decisão da carteira inaugural se perde (`decisao_perdida`).
- **Tarefas agendadas do Codex** rodam no computador, com o app aberto e o PC ligado; queda de
  energia ou de rede na sexta usa as reservas (12:07, 13:07, 14:07; 21:07 e sábado 10:07 no
  fechamento). Rede fora no prepare: o briefing sai com os últimos dados gravados (aviso no
  resultado) ou com `weekly prepare --offline`.
- **Senha do operador ainda não definida no PC das rotinas**: até lá, um kill switch ligado por
  gatilho HARD não tem como ser desligado. Kill switch ligado no leilão do dia de montagem faz a
  decisão caducar (regra de caducidade): a carteira não é montada naquela semana.
- **Regra do ramo `main` ativa desde 06/10/2026** (ruleset 24618259: bloqueia force push e
  exclusão, sem exigir pull request; ramo `cdp-trava` livre). `cdp publicar` nunca força; um
  push direto também não reescreve `main`.
- Kill switch pedido pela rotina de risco enquanto outra rotina segura a trava: o relatório e o
  pedido (`reports/risk/<data>/kill_switch_<HHMM>.yaml`) saem na hora, mas o kill switch só entra
  no livro na execução exclusiva seguinte (montagem ou fechamento), que aplica os pedidos
  pendentes antes de gravar qualquer coisa.
- `artifacts/painel/` é ignorada pelo git (cópia local do painel), mantendo só `.gitkeep`
  versionado; o HTML antigo foi preservado no disco do executor. `cdp site conferir` falha se
  um termo vedado aparecer no texto da casa de qualquer arquivo do portal. Notícias públicas
  neutralizam nomes de fontes vedadas na apresentação; dados brutos e hashes são preservados.
- **Licenças confirmadas pelo titular em 06/10/2026**: `LICENSE` (Apache-2.0, todo o código do
  repositório, inclusive o app Fechamento), `LICENSE-docs` (CC BY 4.0, textos e conteúdos do
  CDP) e `NOTICE` (marca reservada) — ver `docs/cdp/DECISOES.md`.
- **Enquadramento regulatório do portal** (Resoluções CVM nº 20/2021 e nº 175/2022): o portal
  público e indexado mostra ratings (Compra, Neutro, Venda), preços-alvo e os termos "fundo",
  "gestão" e "Asset Management"; um aviso legal não muda a natureza do conteúdo. Revisão
  jurídica pendente antes da publicação de 09/10 (`docs/cdp/DECISOES.md`); o aviso legal das
  docs foi reescrito como descrição (sem conclusões jurídicas).

## Integração pendente com outros donos

- `configs/cdp/site.yaml` (sem dono nesta onda): depois da confirmação do titular,
  `licenca: {codigo: Apache-2.0, conteudo: CC-BY-4.0}` (hoje `null`: o schema.org e
  `dados/datapackage.json` saem sem licença) e `aviso_legal` igual ao aviso legal fixo do
  `README.md` (hoje mais curto); depois, estender `test_licenses_and_disclaimer` a esse arquivo.
- Um só aviso legal no código: hoje há redações próprias em `PAPER_TRADING_TEXT`
  (`src/cdp/workflow/reports.py`), no texto de reserva de `src/cdp/workflow/painel_template.html`,
  em `AVISO_CVM` (`src/cdp/workflow/painel_cobertura.py`) e em `DISCLAIMER`
  (`src/cdp/research/notas.py`) — todas devem derivar do texto de `configs/cdp/site.yaml`.
- Revisão jurídica (titular) e, conforme o resultado, os donos do portal e da cobertura: rótulos
  de rating que não soem como recomendação (por exemplo, posição em relação ao valor do modelo),
  sem "Asset Management", "gestão" e "fundo" nos textos do portal, ou `noindex` nas páginas da
  cobertura.
- Portal e painel com repositório, endereço e título lidos de `configs/cdp/site.yaml` e
  `configs/cdp/fund.yaml`, sem constantes fixas: `REPO` e `PORTAL_URL`
  (`src/cdp/workflow/painel.py`), `REPOSITORIO` (`src/cdp/workflow/painel_cobertura.py`),
  cabeçalho do portal em `src/cdp/site.py` e do painel em
  `src/cdp/workflow/painel_template.html`; `tests/cdp/test_painel.py` derivando o endereço de
  `configs/cdp/site.yaml`. Também um comentário no bloco `>>> marca` do template dizendo que a
  marca embutida fica fora da Apache-2.0 (`NOTICE`).
- `cdp reinicio --executar` abrindo um livro vazio com a gênese (ou um comando novo de
  preparação da cópia, como o previsto no desenho da replicação), para uma cópia do projeto
  começar com `book/genese.json` e o evento `FUND_GENESIS` (`docs/cdp/REPLICAR.md`, seção 3).
- Guarda nos validadores da pesquisa e das notas que recuse, nas evidências e no texto livre,
  ferramentas e bases pagas de dados (hoje a guarda só confere o endereço das URLs);
  `tests/cdp/test_docs_consistencia.py` já varre `artifacts/`, `reports/` e o livro a partir da
  data de início.
- `run_demo` (`src/cdp/workflow/demo.py`) gerar a cobertura sintética (`cdp.cobertura.demo`) e
  notas (`write_demo_note`, em `src/cdp/workflow/notas.py`) nas sextas da demonstração — dono:
  cobertura e mente. Sem isso, o portal da demonstração (DADOS SIMULADOS) sai sem cobertura e sem
  notas.
- `src/cdp/rotinas.py` (prompts gerados): "use nada (ensaio)" e "use nada (o executor publica)"
  → "não faça nada (ensaio: nada é publicado)" e "não faça nada: o executor publica"; depois,
  `uv run python -m cdp skills sincronizar` e exportações de novo.
- `docs/cdp/REPRODUZIR.md`: retirar a seção em inglês (tudo em português) e ajustar o teste que
  a exige.
- `GEMINI.md` (sem dono nesta onda; **antes do push**): hoje diz que o caminho sem supervisão é
  o GitHub Actions ou o agendador "sem credencial de escrita" e aponta para a seção 5 de
  `docs/cdp/AUTOMACAO.md` (que agora é o Codex). Quem seguir isso não configura a credencial de
  push e a trava (falha fechada) barra todo escritor exclusivo. Texto certo: sem supervisão =
  tarefas agendadas do Antigravity ou `agy`/`gemini -p` pelo agendador do sistema, num clone
  dedicado com credencial de push em `main` e no ramo `cdp-trava` (seção 6); IA no Actions só no
  apêndice A. O teste `test_gemini_md_points_to_the_app_scheduler` já confere (hoje marcado como
  falha esperada). `CLAUDE.md`: citar as saídas da mente (`AGENTS.md`, seção 3).
- Redação antiga do dia de montagem em docstrings de `src/cdp/data/intraday.py`; o backtest
  (`src/cdp/backtest/engine.py`) ainda usa a regra antiga de dia de montagem.
- Workflows: passo `name: Checkout` → `name: Baixar o repositório`.
- Roteiros (dono: roteiros e skills): no `docs/cdp/playbooks/SEMANAL.md`, a alternativa
  `weekly prepare --offline` quando o prepare ao vivo falhar por rede e a leitura de
  `aviso_coleta`; no `docs/cdp/playbooks/DIARIO.md`, o caso `registrado` com
  `efetivacao_recusada` (o comentário explica que a carteira não foi montada e que a decisão
  caducou). Depois, `uv run python -m cdp skills sincronizar`.
- "paper trading" ainda aparece em textos gerados fora destes módulos: `DISCLAIMER`
  (`src/cdp/workflow/tese.py`), `PAPER_TRADING_LABEL` e o prompt do comentário
  (`src/cdp/research/commentary.py`), a etiqueta do app (`src/cdp/ui/components.py`) e o
  `track_record_type` padrão (`src/cdp/config.py`, entra no hash do mandato: só com decisão do
  titular). Os relatórios já traduzem na renderização.

## Próximo lote confirmado — após .6

A pesquisa de DFC em `PONTE_GIRO_OPERACIONAL_PLANO.md` fecha contabilmente os períodos de
Petrobras/WEG, mas o giro comercial identificado é parcial; não habilita ΔWC/FCFF. Próxima
ponte preservará itens incluídos/excluídos/pendentes, impostos/financiamento e natureza do caixa.
O contrato de EBIT não recorrente permanece em pesquisa separada, sem imposto/EPS imputados.

A revisão de paridade encontrou omissão confirmada do bloco macro em `DailyRunner._model_at`,
com reflexos nos consumidores de risco e atribuição; a ampliação já existe na preparação
semanal e no kernel do backtest. A próxima correção do motor diário exige base/decisão,
retornos macro observados, corte temporal e compatibilidade verificados, sem alterar mandato.
O replay completo de MOC/commodities/stops permanece em plano, além dessa correção prioritária.
