# Mapa completo do CDP — revisão não autora

**Parecer: o pedido de modelos completos e operacionalmente prontos para cada empresa e índice ainda não está demonstrado.** Há cobertura estrutural de todo o universo no retrato oficial de 07/10, mas existem lacunas documentais, de comparabilidade, de análise econômica, de reprodução independente e de aceite operacional/científico. O mapa aponta os próximos trabalhos por item e preserva os bloqueios corretos.

## Abrir o mapa

- `mapa/EMPRESAS.csv` e `EMPRESAS.json`: uma entrada por empresa, com linha, moeda, período, preço do retrato, métodos, motivos de indisponibilidade, gates, fontes ausentes, datas, cenário, sensibilidade e próxima ação. O JSON conserva também os diagnósticos e as notas publicadas.
- `mapa/ETFS.csv`, `INDICES.csv` e `ETFS_E_INDICES.json`: ETFs e índices expressos nas cotas dos respectivos proxies. Não há oito valuations adicionais em pontos dos índices.
- `mapa/LEDGER.csv` e `LEDGER_FONTE_INSUMO_FORMULA_GATE_SAIDA.json`: remetente, URL, documento, hash declarado, recepção/publicação, moeda/base, passos com a mesma fonte e saída. A coincidência de fonte não é declarada como dependência causal exata nem como tie-out com documento primário.
- `mapa/DOMINIO_HASH_LEDGER.csv`: distingue hash do bruto público, transcrição/configuração, base agregada e ausência de vínculo. Hash de transcrição não autentica a planilha de origem.
- `mapa/METODOS.csv`, `PORTOES.csv` e `FORMULAS_SUBSTITUICOES.json`: métodos configurados/disponíveis, notas de indisponibilidade, fórmulas substituídas e todos os estados dos portões. As notas legitimamente sem fórmula não são chamadas de bug.
- `mapa/FAMILIAS_REQUISITOS_CAMADAS.json`: oito arquétipos e suas dependências, mais risco, alpha, otimizador, execução/gestão e avaliação por canal.
- `mapa/REVISAO_ECONOMICA_SEM_NOVOS_CENARIOS.json` e `POSICOES_ETFS_MOEDAS.csv`: drivers e cenários existentes; nenhuma previsão nova, estimação ou stress foi gerado.
- `mapa/PRIORIDADES.csv`/`.json`: dez ações concretas, com causa, escopo e prova necessária.
- `mapa/INTEGRIDADE_E_RASTREABILIDADE_LOCAL.json`, `BRUTOS_INDICE_RASTREABILIDADE.csv`, `PROVA_REPRODUCAO_LOCAL_LIMITES.json`: o que está comprovado localmente e o que requer nova prova de serviço/recálculo na versão geradora.

As contas vêm dos programas, não da redação. `RESUMO_CONTAGENS.json` e os dois logs dão os números reproduzíveis. São **233 empresas, 281 linhas negociadas, oito ETFs e oito vistas de índices via proxy**: **241 modelos financeiros e 249 vistas de auditoria**. A classificação por país da ficha pode diferir do país da linha/universo e do conjunto elegível no monitor; as listas originais são preservadas, sem agregar universos distintos como equivalentes.

## O que o retrato demonstra

Os 632 participantes explicitamente declarados pelo manifesto conferem por SHA-256; todos estão rastreados no HEAD local `af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9`. O commit gerador do snapshot é `5cb2d4ab8c250b3289dc90fb4e655637335a0aec`, disponível na história local. Essa prova não executa os modelos nem presume que o código mais recente reproduza uma versão antiga.

O snapshot possui 200 alvos citáveis, 34 Compra e 32 Venda: 17% e 16% dos citáveis, dentro das faixas de distribuição P0. Confiança C continua em 100/233, **42,918455%**; revisão em 30/233, **12,875536%**: ambos acima dos respectivos objetivos. As três fichas sem alvo são BR_GPA, BR_ONCOCLINICAS e MX_VOLARIS. Os motivos e métodos retirados estão conservados por empresa. Nenhuma quota autoriza mudar dados, fórmulas ou gates.

O pacote publicado declara PIT verdadeiro para 120 emissores e falso para 113. São flags históricas recebidas, não recertificação desta auditoria. Os campos de publicação desconhecida em todas as fichas incluem consenso e referências legítimas sem data primária; isso não significa que todos os demonstrativos estejam sem recepção. Datas estimadas, ausência de publicação, disponibilidade observada e recebimento atual são conceitos separados.

A canônica de estudo possui 187 fontes Python; o executor capturado possui 185. Oito caminhos diferem, incluindo os novos módulos de dimensões e Galicia. São candidatos privados preservados, em outra frente de integração; não foram apresentados como produto já publicado ou como novo retrato oficial. A política observada global não está habilitada na configuração capturada.

## Achados que afetam a completude

1. **Fontes e comparabilidade por empresa.** O ledger expõe o dado ausente, a data estimada e o período/base/moeda declarado. A maior parte dos itens Yahoo é padronização pública; consenso é estimativa, não fato reportado. CVM/SEC/RI são rótulos de origem recebidos, sem novo tie-out documental geral nesta revisão. As conclusões primárias argentinas anteriores são delimitadas: YPF tem casos de células USD rotuladas ARS; Galicia/Supervielle exigem política e poder aquisitivo coerentes; AR_LAR é commodity, não banco. Não se certifica TTM por proximidade numérica, moeda global, inflação presumida ou rubrica monetária tratada como ações.
2. **Método economicamente aplicável.** Os pesos são renormalizados aos métodos válidos; `peso_configurado` no mapa não é peso final presumido. Método com dado ausente, patrimônio negativo ou fluxo inaplicável permanece indisponível com motivo. Nem a existência de alvo nem a aprovação de G3 prova que os métodos disponíveis capturam adequadamente o negócio.
3. **Sensibilidade sem driver participante.** Há 38 grades cujas colunas são invariantes, incluindo sete commodities: AR_ADECOAGRO, AR_LAR, BR_BRASKEM, BR_CSN, BR_SIGMALITH, CL_CMPC e PE_SCCO. No exemplo Adecoagro, FCFF normalizado foi retirado por patrimônio calculado não positivo; RIM e regressão EV/receita participam. O choque de commodity não atua nesses métodos nesse caminho. É uma lacuna de interpretação/adequação do driver, não uma declaração de erro aritmético nem licença para fabricar FCFF positivo.
4. **ETFs e índices.** Todos os oito têm alvo no retrato, composição não aproximada declarada e cobertura bottom-up parcial. A composição exportada omite hash, data de recepção e publicação; a referência do índice autentica `etfs.yaml`, não um documento do provedor do índice. O raw e a composição padronizada podem estar arquivados separadamente: a falta é de vínculo/exposição no modelo, não prova de inexistência do dado. Os gates E1–E5 do ETF verificam alvo/retorno/múltiplo/payout/concentração; não certificam composição oficial integral.
5. **Bug de visibilidade delimitado.** `avaliar_etfs` filtra as configurações por ticker presente nas colunas de benchmarks. Se uma coluna inteira faltar, o caminho sem preço de `calcular_etf` não é chamado e a ficha desaparece. Os oito atuais não estão ausentes. O ROOT constrói o reparo separado com ausência explícita e defaults literais.
6. **Exposição granular do ETF.** `_modelo_etf` exporta `insumos=[]`, mas mantém agregados, posições, passos, fontes e links de arquivo. Assim, falta a mesma tabela de insumos granulares oferecida às ações; não se conclui que o cálculo carece de insumos. O vínculo com o pacote e os constituintes efetivamente usados merece um contrato uniforme.
7. **Hipótese ARGT, sem erro numérico provado.** A leitura encontra crescimento dos LPA dos filhos em suas moedas e conversão cambial por país, escolhendo ARS para ARGT. O CSV de posições conserva as moedas dos participantes reais. A coerência de crescimento em USD versus choque FX ARS exige estudo causal separado; não houve reexecução nem patch nesta frente.
8. **Caso de investimento e saída decisória.** O modelo possui ponte de 12 meses, percentis MC e diagnósticos implícitos, mas esses controles técnicos não segregam integralmente negócio versus rerating, refinanciamento/liquidez e catalisadores por emissor. As 12 notas qualitativas publicadas não representam underwriting completo das demais fichas. Não há proposta/decisão/booking inaugural de 09/10 na árvore capturada. A fase S1 é política autorizada de adoção da IA; IC normativo não é IC realizado.

## Reprodução pública e aceite

O índice público possui 1.480 registros de brutos; 1.455 são rastreados no checkout, e 25 ficam fora do Git, conforme exceções documentadas para grandes brutos. Datas e hashes esperados foram conservados. Recuperar uma URL hoje não garante obter a versão arquivada anteriormente; a recuperação exata dos endpoints mutáveis e o recálculo na versão geradora precisam de prova própria, sem converter nova recepção em disponibilidade histórica.

O fluxo de gênese de uma cópia vazia permanece uma lacuna concreta: REPLICAR descreve a ausência; `reinicio.plano` retorna `nada` quando não há chaves anteriores e `executar` encerra nesse estado antes de gravar gênese. A origem tem `book/genese.json`; sua integridade não está sendo questionada. A réplica própria precisa de um caminho explícito, sem resetar o livro existente.

E1 operacional integral, PIT/vintages/holdout e avaliação E2 permanecem distintos dos gates E1–E5 de ETF. Os backtests recebidos explicitam sobrevivência, capitalização/BP contemporâneos e aluguel/short interest não PIT; não incluem o valor agregado da IA. Estudos de álgebra NW/PSD/covariância e testes verdes não certificam estimação, calibração, adequação do investimento ou cumprimento integral do mandato.

A conferência HTTP do ROOT sobre o portal `af6eb0c` foi recebida em `evidencia_portal_root/` e conferida nesta frente por bytes/hash: 52 respostas HTTP 200, sendo 51 arquivos relacionados por hash ao manifesto e às somas e o auxiliar `SHA256SUMS`, cujo conteúdo confere com o manifesto. O manifesto foi recebido em 09/10/2026 entre 10:04:13.053800 e 10:04:13.472025 UTC. O recibo próprio do ROOT declara 241 fichas sem duplicação/ausência, incluindo bloqueadas e sem alvo; a união foi conferida pelo programa do ROOT, não reexecutada por nós. O recibo complementar conserva essa autoria e os limites.

Esta auditoria efetuou zero GET e não usa o painel local ou um push como substituto de uma prova pública. A prova recebida confirma serviço e fichas atuais daquele commit, sem recálculo financeiro, recepção histórica/PIT ou publicação dos candidatos privados. Os arquivos de download do livro ligados pelas fichas estão manifestados; o recebimento efetivo dos 632 downloads e seu recálculo são outra frente do ROOT, ainda fora do aceite deste pacote.

No fechamento desta auditoria, ROOT informou uma falha da suíte ampla12 após 1.719 casos, anterior à mutação do teste Galicia: a seleção TTM inicial da fixture ficou vazia. Isso não foi investigado aqui, não é automaticamente o defeito financeiro antigo nem sustenta aceite global de integração. É prioridade técnica separada, sobre a fonte que ROOT indicar.

## Reprodução desta auditoria

As fontes físicas estão em `fontes/`; o recálculo do mapa usa somente JSON/CSV/gzip/YAML e código próprio. `mapear_modelos.py` e `complementar_auditoria.py` recusam import CDP, socket, subprocesso e escrita fora de `mapa/`. A captura inicial usa apenas três comandos Git de leitura, registrados no recibo. Os programas recusam sobrescrever uma captura/mapa existentes; para reproduzir, use nova pasta com as fontes preservadas e os programas, sem as saídas `mapa/`.

O lint final ajustou apenas aliases UTC/imports não usados/ordem de imports dos programas da auditoria; as versões efetivamente executadas antes do lint estão preservadas. Nenhum código de produto, configuração, dado bruto ou livro foi editado. O primeiro erro sintático do programa complementar ocorreu antes de executar qualquer análise; foi corrigido localmente, sem resultado financeiro ou alteração do produto.

**Este pacote é privado e ignorado pelo Git.** Ele organiza a auditoria e os requisitos de uma futura publicação revisável; não satisfaz sozinho o pedido de tudo acessível no GitHub. O ROOT recebe o mapa para desenvolvimento e publicação pelos caminhos autorizados.
