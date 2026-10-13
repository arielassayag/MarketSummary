# Beta distribuído em sombra

`cdp.risk.beta_distribuido_sombra.estimar_beta_distribuido_sombra` recebe retornos
excedentes já calculados em USD, calendário explícito e corte UTC. Não recebe
preços, calcula retornos, coleta fontes ou altera modelo de risco. Os testes
carregam **DADOS SIMULADOS**.

A especificação numérica acompanha a equação pública no apêndice7.2 da aplicação
primária [BIS Working Paper164, página impressa25](https://www.bis.org/publications/working-paper-164-did-investors-regard-real-estate-safe-during-japanese-bubble-1980s.pdf):
regressão conjunta sem intercepto, três colunas do mercado t−1,t,t+1 e soma dos
coeficientes. Esta é uma aplicação distinta de Dimson1979; o texto integral
original não foi recebido. A implementação não adota dados empíricos do paper
nem afirma que o agregado corrige viés ou oferece previsão melhor no CDP.

Cada centro exige carteira na sessão e mercado nas três sessões, todos com
disponibilidade declarada até o corte. Pontas, ausências e observações tardias
ficam em uma máscara explícita. Ordinais não consecutivos são recusados; lacunas
devem aparecer como observações ausentes. A comparação contemporânea usa a mesma
amostra, também sem intercepto. O lead é exclusivamente histórico e explicativo.

O algoritmo é OLS conjunta por SVD, `rcond=1e-12` técnico fixo e pelo menos quatro
centros. Normaliza positivamente os operandos para evitar produtos brutos
extremos. Posto inferior a3 e resultados não representáveis ficam insuficientes;
não há ridge, reparo de matriz, preenchimento de ausências ou clamp de beta.
Perda de observação não zero na normalização, escala ou produto de coeficiente
que arredonde para zero tornam a saída insuficiente. A recusa é conservadora:
não prova que outra ordem de operações seria incapaz de representar o resultado.
Resposta observada inteiramente zero só retorna beta zero depois de confirmar
posto3; não forma uma escala artificial que transforme zero em `0*inf`.

A saída preserva a entrada imutável, centros, exclusões, posto e valores
singulares, com `autoridade_operacional=false`, referências não verificadas e
PIT não demonstrado. SHA e disponibilidade recebidos como campos são declarações;
este módulo não autentica arquivos ou disponibilidade histórica. Não há consumidor
no solver, na carteira, nos gates, no MCP ou na configuração do mandato.
