# Dashboards de pesquisa e carteira

O portal oferece `cases/` para navegar pela pesquisa e pelos comparáveis e `risco/` para
examinar a carteira, as exposições e os fatores. Ambos são montados em Python a partir das
representações públicas conferidas pelo produtor do site. Cada vista tem `dashboard.json`,
vínculo ao manifesto da publicação e fontes no ponto de uso. Sua montagem não grava o livro.

## Cases e comparáveis

O catálogo permite buscar por negócio, ticker e método e filtrar país, setor, instrumento
e visão do modelo. Cada ativo abre sua página de análise e permite examinar um grupo de
comparáveis. A tese narrativa completa aparece após a adoção e publicação da nota pela
rotina; páginas sem nota adotada identificam a análise como preliminar. No checkpoint
conferido em 12/10/2026 há 156 narrativas adotadas e 85 análises preliminares, entre os
241 ativos do catálogo. Companhias precisam compartilhar setor e enquadramento econômico;
o grupo local restringe também o país ou a região registrada, inclusive o agrupamento LATAM.
A ampliação à América Latina é uma escolha explícita.
Esse filtro não comprova equivalência de negócios, risco, crescimento ou contabilidade.

ETFs têm grupo próprio de comparação de produtos. A inclusão não presume índices idênticos
nem converte o ILF no benchmark contratual. A diligência do índice, replicação, composição
e custos permanece no documento de cada produto.

As linhas conservam moeda, datas de preço, modelo e narrativa, métodos, confiança e portões
de qualidade. Preços nominais são apenas referências. Retornos esperados só entram quando
citáveis no modelo, com indicação de retorno total e horizonte de doze meses; múltiplos sem
denominador, unidade e período equivalentes ficam `n/d`.
O grupo econômico deste dashboard difere do grupo estatístico usado pelo modelo de alpha
relativo; não reproduz a amostra de pares do briefing como se ela fosse o universo completo.
As ordens são produzidas em Python. JavaScript apenas busca, filtra e permuta as linhas.

## Risco e fatores

A carteira registrada e a proposta têm seções distintas, com semana, data e base próprias.
Pesos-alvo e estimativas ex-ante não são apresentados como posições efetivadas. O dashboard
mostra posições long e short, exposição líquida e bruta, limites, liquidez, contribuições
de risco por posição e fator, exposições por grupo e cenários de estresse recebidos.

A memória de `modelo.risco` só acompanha a proposta da mesma semana. Ela não substitui
o risco diário da carteira registrada. Contribuições negativas conservam o sinal; ausência
continua `n/d`, inclusive sem carteira ou sem fator publicado. O dashboard não estima novos
betas, covariâncias ou choques, não dimensiona posições e não altera o mandato.

Frações do patrimônio e sensibilidades Σwβ têm gráficos e escalas próprios. Sensibilidades
e limites de commodities são coeficientes com quatro casas decimais, também no painel,
na metodologia e no quadro de conformidade. Beta e estilos operacionais conservam a
mesma unidade dos respectivos limites do mandato. O KPI de parcela fatorial e as
contribuições por fator e posição vêm da
decomposição sem ajuste κ_F. A memória de grupos usa o ajuste κ_F e explicita o valor e
a origem recebidos; essas normalizações não são diretamente comparáveis nem parcelas
complementares. Ausência de parâmetro ou de origem continua sinalizada como ausência.

Reconciliações e escalas de apresentação são determinísticas no produtor Python. Limites
e alertas preservam o estado recebido, inclusive excessos; integridade do livro não significa
aderência da carteira ao mandato. Os gráficos têm tabelas, rótulos e fontes acessíveis.

## Referências e validação

O desenho usa o [guia do CFA Institute para relatórios de ações](https://www.cfainstitute.org/sites/default/files/-/media/documents/support/research-challenge/challenge/rc-equity-research-report-essentials.pdf)
e sua [orientação de análise industrial e competitiva](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/industry-and-competitive-analysis)
para ligar narrativa, drivers, valuation, riscos e comparáveis. O workflow de gestão de risco
do plugin Public Equity Investing orienta a apresentação de dados com cortes, fontes e bases
explícitas, adaptado aos contratos e aos insumos públicos do CDP.

Os testes cobrem separação de datas e carteiras, comparabilidade, valores ausentes, sinais,
conteúdo externo escapado, determinismo, arquivos, navegação e manifesto. A conferência visual
inclui desktop e celular, filtros, seleção de comparáveis e leitura dos gráficos. O site
publicado é conferido contra seus hashes; um build local ou push isolado não prova o deploy.
