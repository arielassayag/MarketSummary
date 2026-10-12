# Viés de risco em sombra — diagnóstico puro

`src/cdp/risk/vies_diagnostico.py` oferece duas APIs independentes de livro,
configuração, relógio e I/O. São diagnósticos em sombra: não recalibram risco,
mudam fase, promovem modelo, autorizam escrita ou executam carteira.

`diagnosticar_vies_risco(pares, politica)` recebe uma tupla de `ParRisco` e uma
`PoliticaVies`. Os objetos de entrada e saída são dataclasses frozen; contêineres
de saída são tuplas. Tipos nativos exatos são conferidos antes de operações:
float finito, inteiro sem bool, string sem subclasse, tupla sem subclasse e
datetime nativo com `tzinfo is datetime.UTC`. Não há coerção nem callback de
objeto, fuso ou string fornecidos.

Cada par declara uma previsão anterior ao período e um retorno de **preços em
USD da mesma carteira de abertura**, na unidade `fracao_USD_mesmo_periodo`.
Exige modelo as-of anterior ou igual ao selo da previsão, selo anterior ou
igual ao início, fim posterior ao início e não posterior ao corte UTC explícito.
Essa ordem recusa contradição declarada, sem autenticar disponibilidade. Horizonte em
sessões e unidade devem ser comuns; ids e períodos duplicados são recusados.
A igualdade de hashes de carteira é só uma declaração de identidade, sem
autenticação de holdings ou documentos.

O retorno é normalizado por `z = retorno_precos_usd / sigma_periodo`. O desvio
previsto deve ser positivo. Zero de retorno observado é válido. Retorno ou
desvio ausente, ou alguma posição não reprecificada, exige motivo de ausência;
o par é excluído explicitamente com id, motivo e contagem. Nenhuma ausência
vira zero. Descrição usa média de z, desvio amostral com ddof=1, RMS de z e
excesso de curtose descritivo populacional. Não incorpora custos ou funding
silenciosamente nem altera o retorno líquido oficial.

Períodos sobrepostos ou hipótese `DEPENDENCIA_CONHECIDA`/`DESCONHECIDA` conservam
a descrição e impedem inferência IID. `DECLARADA_NAO_PROVADA` permite somente
um intervalo **condicionado à declaração**, nunca prova estatística de IID.
Uma previsão feita após observar o fechamento não serve para prever o mesmo
intervalo. Construir pares reais e autenticar origens está fora desta API.

`intervalo_desvio_nist(amostra, alpha=...)` recebe diretamente uma tupla de
floats finitos e calcula um intervalo aproximado para o desvio populacional
sob IID, seguindo a fórmula pública do
[NIST, SD CONFIDENCE LIMITS](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/sdconfli.htm).
Para n>4:

```
q = 1 / (2 sqrt(n - 4)); k = floor(n q)
m = média após excluir k observações de cada cauda somente para essa média
s² = soma((x - média(x))²) / (n - 1)
g4 = n soma((x - m)^4) / soma((x - média(x))²)^2
zcrit = quantil normal de 1 - alpha/2; c = n / (n - zcrit)
se = c sqrt((g4 - (n - 3)/n) / (n - 1))
intervalo de σ = exp(log(s) + log(c)/2 ± zcrit se/2)
```

**`floor` é adaptação explícita CDP.** O paper completo de Bonett não foi
recebido; este código não afirma reprodução integral do paper. O aparo afeta
somente m: todas as observações originais permanecem em s² e g4. O cálculo usa
escala numérica nos momentos sem alterar essa fórmula ou winsorizar caudas.
Não substitui o intervalo por banda normal MSCI nem aplica prior de curtose.

Com n<=4, variância nula ou aritmética não representável, o intervalo retorna
`INSUFICIENTE`, motivo explícito e limites ausentes. Não inventa extremos, não
prende radicando negativo a zero e não muda alpha. Se o diagnóstico descritivo
é válido, sua descrição pode permanecer mesmo sem intervalo. Quando o limite
inferior supera 1, a interpretação é `SUBPREVISAO_CONDICIONAL`; limite superior
abaixo de 1 dá `SOBREPREVISAO_CONDICIONAL`; caso contrário é `INCONCLUSIVO`.

As `ReferenciaCorpo` são declaradas como `ORIGINAL_REF_NOT_REVALIDATED` ou
`SIMULATED_TEST_ONLY`. Nenhum hash/locator abre arquivo, prova disponibilidade,
PIT, origem física, independência ou autoria. `PUBLICA_RECEBIDA` é o rótulo
declarado pelo chamador, sem certificação pelo kernel. Referências de teste
exigem `SIMULADA_TESTE` e o resultado informa **DADOS SIMULADOS**.

Os testes usam o exemplo de metrologia público do NIST para o oráculo numérico
(s=0.5168; intervalo [0.3263, 1.0841], publicados com quatro casas). Pares
financeiros de teste são simulados, não históricos ou evidência PIT. Testam
máscaras, identidade declarada, datas, callbacks recusados, imutabilidade,
overlap, falta de IID e ausência de I/O. Não exercitam modelo de risco,
gerador, solver, getter, consumidor, MOC ou livro. A suíte focal e a revisão
independente permanecem condições da recepção desta entrega; não são
certificação do modelo, da carteira ou de cobertura financeira do intervalo.
