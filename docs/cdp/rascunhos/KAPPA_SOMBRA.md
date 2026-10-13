# Rascunho técnico — κ_F em sombra

`cdp.risk.diagnostico.comparar_kappa_sombra` compara o κ vigente com o modo
analítico já existente em `cdp.risk.idio`. É diagnóstico somente leitura: nenhum
consumidor financeiro o chama e ele não promove valores para mandato, gates,
solver, ordens ou relatórios. Dimson, vetos, sizing e overlays estão fora deste delta.

O chamador fornece `RiskModel`, `FundConfig` e o argumento obrigatório
`unidade_retornos="decimal_diario"`. Os retornos fatoriais são um DataFrame de
valores reais diários em fração decimal, indexado por datas civis únicas e
ordenadas, sem fuso/hora e até `model.as_of`. Não há busca de configuração por
CWD, leitura de arquivo, rede ou relógio. Declarar unidade/tipos não comprova a
origem física, PIT, calibração nem a coerência dos demais campos B/F/D do modelo.

O κ vigente e seu marcador de origem vêm de `idio.kappa_f(model, cfg)`. Uma nova
configuração em memória altera somente `second_order_inflation_mode` para
`analytic`; o produtor nativo calcula o valor sombra. O hash dessa configuração
identifica essa derivação, sem conferir autorização para execução. A configuração
original e todos os campos do modelo permanecem intactos.

A fórmula bruta e T_ef vêm de `idio.kappa_formula`, com K/curtose observados pelo
produtor nativo e o mesmo clip de curtose. `limites_sombra` é o truncamento
configurado existente, **não um intervalo de confiança** nem uma banda estimada
ou calibrada. O resultado congelado conserva `valor_nativo_sombra` e
`origem_sombra`. Quando o produtor usa fallback, `candidato_analitico` é None e
`candidato_disponivel` é falso; o fallback não vira evidência analítica.

NaN não é preenchido nem convertido em zero. Histórico None/vazio,
ausência de fatores na última data, curtose indisponível e T_ef insuficiente
ficam explícitos em `motivo`. Contagens de linhas/fatores podem ser zero quando
isso foi observado; uma contagem não é um valor financeiro imputado.
Infinito, texto, booleano, complexo, unidade incorreta e índice ambíguo são
recusados antes do cálculo. `n_observacoes` é número de linhas, não o número de
observações válidas de cada fator. O schema nativo mantém suas próprias restrições;
o diagnóstico verifica ainda a finitude dos escalares de configuração consumidos.

## Limite metodológico

[Shepard (2009), seção 4.2](https://arxiv.org/html/0908.2455) deriva a correção de
risco por otimização sob hipóteses específicas. A adaptação nativa de T_ef por
EWMA, lags Newey–West e curtose é uma heurística conservadora do CDP. Esta comparação
não valida essas hipóteses, não estima um IC do viés e não demonstra eficácia fora
da amostra. P1 permanece incompleto. Qualquer adoção futura exige estudo e decisão
técnica independentes, sem adaptação automática.

## Validação delimitada

Fixtures de **DADOS SIMULADOS** fixos verificam paridade com os ramos nativos,
fórmula/clip/truncamento, unidade obrigatória, faltas/NaN, índices/corte,
não mutação, retorno imutável e ausência de I/O próprio. Os testes nativos de
`test_limites.py` permanecem no recorte de regressão. Resultado terminal/XML e
pins serão registrados fora deste rascunho; procedimento não é resultado observado.
