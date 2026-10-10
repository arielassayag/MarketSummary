# Fase por grupo, somente em sombra

`recomendar_fase_grupo` é kernel consultivo puro. Não lê o livro, relógio, ambiente,
configuração, modelo ou ledger de chamadas; não grava registry e não promove fase.
Entrada e saída são dataclasses congeladas com tuplas nativas. Resultado sempre contém
`autoriza_promocao=False` e `SEM_RECEPCAO_FISICA_SEM_PIT_SEM_ADOCAO`.

## Identidade e referência própria

`ChaveGrupo` conserva mind, provider, snapshot original e canal (`quant`, `pesquisa_ai`,
`mente_final`). Não conhece o executor atual. `None`, identidade ausente/mista, alias não
resolvido, snapshots observados diferentes, linhagem ausente e múltiplas tentativas
permanecem insuficientes. Não escolhe a primeira chamada ou o melhor modelo depois do
outcome. Coortes de outras chaves são informadas separadamente e não entram nas séries.

`fase_referencia` é entrada explícita S0–S3 ou ausente. Sua origem de grupo exige
`GRUPO_REFERENCIA_HUMANA` e referência declarada própria. `GLOBAL_APENAS_CONTEXTO` conserva
a referência recebida, mas não a transforma em fase do grupo; sem referência própria,
`SEM_FASE_DE_GRUPO`. Quant recebe somente diagnóstico quant, nunca uma fase de IA.
`cfg.research.llm_phase` e os ICs usados pela construção atual permanecem intactos.

Referências de coorte, binding, outcome, chamadas, universo de comparações e referência
de fase são textos declarados, sem autenticação pelo kernel. O SHA da política macro
declara uma identidade para comparação, não prova corpo, autoria, disponibilidade ou PIT.
`PUBLICA_RECEBIDA` também é declaração do caller, nunca selo produzido aqui. Uso real
exigirá adapter receptor próprio e evidência original; eles estão fora deste módulo.

## Cronologia, unidades e máscaras

Cada `AmostraIC` contém início/fim UTC do retorno, selo da previsão, as-of original do
modelo, deadline e selo do outcome. Exige `as_of <= selo <= início < fim` e
`deadline <= início`; modelo posterior ao selo e outcome anterior ao fim são contradições.
Selo posterior ao deadline ou fim/selo do outcome posterior ao corte não alimentam IC
da coorte. UTC deve ser literal, sem conversão civil, timezone/callback livre ou fold.

Horizonte, unidade `fracao_residual_USD_mesmo_horizonte` e hash da base macro devem ser
iguais à política explícita. Resíduo de outra janela, equity, preço local, risco atual
ou horizonte8 não substituem o outcome fechado de horizonte5. Os parâmetros não são
recalculados. Identificadores de coorte e início por grupo são únicos; vetores por
emissor têm comprimentos iguais e ids únicos. Tipos malformados recusam antes do cálculo.

`AmostraIC.week` conserva a chave semanal original, como `date` nativa exata.
O início precisa ocorrer no mesmo dia civil UTC dessa chave. O calendário explícito
`CalendarioFaseDeclarado(corpo_ref, selado_utc, chaves)` é congelado: chaves nativas,
únicas, ordenadas e no máximo uma por semana civil segunda–domingo. Cada chave de
coorte deve pertencer ao calendário presente e não vazio. Não impõe sexta-feira:
quinta em feriado ou inception excepcional precisam apenas constar da declaração.
Mesmo sem calendário, duas coortes do mesmo grupo/semana civil são contradição,
recusada antes da máscara e do cálculo, sem escolher a melhor pela performance.

Calendário ausente/vazio ou selado depois da primeira previsão do grupo impede
recomendação. Referência e chaves declaram consistência, não autenticam sessões,
feriados, inception, disponibilidade ou PIT. A convenção de dia civil UTC é explícita;
não se converte um timestamp livre para fazê-lo caber na chave. Contagem de sessões
reais do horizonte permanece fora do kernel, sem buscar a configuração atual.

IA, quant e retorno usam a mesma máscara, junto da autoria confirmada. Uma ausência
retira o emissor das três séries, conservando id/motivo e as contagens. Autoria externa
não vira autoria do executor. `None` permanece ausência; retorno zero finito é legítimo.
Menos de3 pares e postos constantes tornam IC ausente. Quant isolado só cruza quant e
retorno; n IA/incremental são zero e não há promoção.

## Matemática e política preservadas

O contrato de `research/evaluation.py` recebido como texto é a referência nativa:
Spearman sobre average ranks; resíduo MQO IA~[1,quant] sobre a mesma máscara; resíduo
puramente numérico abaixo de `64*epsilon*max(1,norma_IA)` não é informação incremental.
Uma escala local positiva mantém a MQO matemática; não altera as tuplas. Quant constante
deixa somente a média/intercepto, enquanto IA inteiramente linear no quant tem incremental
ausente, não mérito zero. Não há importação do tracker/escritores/financeiro neste kernel.

Agregação semanal mantém média/desvio ddof1, ICIR média/desvio e t IID média/(sd/√n).
`n_semanas` conta ICs disponíveis de chaves/semana civil distintas; treze retornos
diários disjuntos não viram treze semanas. Lacunas não recebem IC zero e não há
consecutividade artificial além das chaves recebidas.
Menos de2 semanas ou desvio zero tornam t/ICIR ausentes. T é explicitamente diagnóstico
IID, sem provar independência ou fornecer significância corrigida para seleção.

Política matemática nativa: S0→S1 mínimo13/ICIR≥0,5; S1→S2 mínimo26/t incremental≥1,5;
S2→S3 mínimo52/t incremental≥2. Últimas13 com IC médio negativo e t≤−1,5 recomendam S0;
promoção é no máximo um nível. S3 permanece S3, salvo o rebaixamento nativo. Não se muda
threshold, mínimo, família estatística ou inferência por curtose nesta entrega.

As séries descritivas mostram todas as coortes maduras da chave solicitada. A série
elegível declarada exclui coortes com impedimentos. Sobreposição explícita, dependência
conhecida, IID desconhecida e universo de comparações não selado antes da primeira
previsão impedem recomendação. Não se inventa tamanho efetivo de amostra. Coortes
`SIMULADA_TESTE` e `REPLAY` podem descrever o mecanismo, mas não sustentam sugestão de fase.
Uma sugestão sobre declarações elegíveis é `CONDICIONAL_A_DECLARACOES`; não é adoção,
aprovação, certificado de modelo, autorização financeira ou conclusão do P1.

## Validação e limites

Fixtures são TESTE/DADOS SIMULADOS e nunca recebem flag pública para obter promoção.
Controles de cadência conservam origem simulada e recusam datas diárias, chaves
artificiais desalinhadas, duplicidade civil, tipos livres e calendário contraditório.
Quinta/inception e semanas com lacunas exercitam somente consistência declarada.
Os oráculos de rank/MQO/DDOF/thresholds exercitam kernels matemáticos isolados; o fluxo
principal simulado confirma insuficiência e preservação de identidade/ausência/máscara.
A focal carrega o módulo inteiro por loader de arquivo, pois o agregador de pesquisa
importa agentes fora do recorte. Não há AST parcial ou import financeiro pelo módulo.

Entradas integrais devem ser conservadas para reproduzir a saída: resultado isolado não
retém vetores, cada referência ou todo o conjunto de comparações. Nenhum teste de política
prova vínculo físico legítimo, previsão realmente anterior, snapshot universal, autoria,
independência, macro PIT ou mérito econômico. Um futuro receptor/consumidor exigirá outro
contrato e revisão; fase efetiva por modelo e configuração global não foram integradas.
