# Overlay de um ETF — diagnóstico condicional

`cdp.risk.overlay_diagnostico` recebe uma carteira base que exclui o ETF e uma
matriz conjunta anual de variância/covariância em retorno fracionário USD.
A quadrática V(h)=vp+2h*c+h²*vh tem ponto livre -c/vh; o candidato é limitado
ao intervalo explícito [hmin,hmax]. Não procura outros ETFs, estima covariância,
chama solver, preserva alpha por hipótese ou aprova um tradeoff de custo.

Matriz2x2 PSD é conferida com tolerância relativa fixa 1e-12 sobre a desigualdade
de Cauchy-Schwarz; nenhuma matriz é reparada. Variância negativa por arredondamento
permanece no resultado bruto e sinaliza insuficiência, sem virar zero. Overflow,
tipos/callbacks, base ou corte inválidos recusam. Custos de alteração usam |Δh|;
borrow e financiamento recebidos usam |h candidato| vezes dias pela convenção
ACT360/ACT365/TRADING252. Dias têm limite de forma de 365.000, sem significado de
mandato. Financiamento é assinado e créditos não desaparecem num agregado.

Preço, FX, tracking, coeficiente de custo/borrow/financiamento ou restrições ausentes
mantêm estado incompleto e nomes de ausência. Os números condicionais da quadrática
podem estar disponíveis mesmo assim; não representam preço executável, liquidez,
ordem, número de cotas, hedge escolhido ou implementação pronta. A base recebida
deve conciliar linhas/moeda/período e covariâncias; não se presume beta unitário.

Referências e instantes declarados não autenticam arquivos, disponibilidade histórica
ou PIT. Restrições/intervalo, exposição retida e cenário de falha são recebidos como
declarações, sem poder de aprovação. A API é pura, usa classes frozen/tuplas/tipos
nativos exatos e não lê arquivos, relógio, ambiente, livro ou configuração global.
Todo fixture diz **DADOS SIMULADOS**. O resultado conserva autoridade operacional
falsa. Modelos conjuntos, insumos públicos prévios, mandato e uso econômico real
continuam exigindo qualificação separada.
