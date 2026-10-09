# Contratos documentais — conservação, composição e consenso

Estes contratos permitem preservar e conferir fatos públicos antes de usá-los em
modelos. A revisão técnica não conclui a normalização econômica dos emissores.
As opções novas permanecem desligadas por padrão. Não alteram o retrato ou a
decisão inaugural já publicados em
[`7f0d368c`](https://github.com/arielassayag/MarketSummary/tree/7f0d368c1a5bba0c1bbe948aea38dda232e34852).

## Demonstrações bancárias

Os produtores documentais de Galicia e Supervielle mantêm moeda, escala, poder
aquisitivo, período, item contábil, consolidação e participação dos proprietários.
Um agregado só recebe os componentes ligados aos documentos e grãos explícitos;
valor, frequência ou fonte contraditórios impedem a composição.

As diferenças entre bases BCRA e IFRS, o patrimônio, o resultado e o resultado
abrangente continuam separados. Uma identidade contábil que fecha não atribui
todo o efeito a uma norma nem transforma diferença patrimonial em lucro
normalizado. Duas notas semestrais de Galicia apresentam quantias de redução,
mas o destino contábil permanece desconhecido na frase recebida. Não são ajustes
de patrimônio ou resultado autorizados pelo contrato.

Fontes e controles estão em
[publico_galicia.py](../../../../src/cdp/data/publico_galicia.py),
[publico_supervielle.py](../../../../src/cdp/data/publico_supervielle.py) e
[test_vinculo_v2_revisor_independente.py](../../../../tests/cdp/test_vinculo_v2_revisor_independente.py).

## Comparativos da CVM

A conservação opcional registra as linhas de ÚLTIMO e PENÚLTIMO separadamente,
com identidade do emissor, versão, documento, fonte, membro do arquivo, linha do
CSV e valores originais. Zero originalmente reportado e comparativo posterior
são fatos distintos. Conflitos ficam visíveis; a opção não escolhe o fato que
deve alimentar TTM ou crescimento.

O caso JBS vincula quatro receitas reportadas a documentos primários em reais.
Uma política de predecessor sob controle comum não demonstra, por si só,
perímetro econômico constante ou crescimento orgânico. Documento de RI não é
automaticamente o mesmo corpo do protocolo CVM.

O contrato e controles são reproduzíveis em
[publico_cvm_comparativos.py](../../../../src/cdp/data/publico_cvm_comparativos.py) e
[test_cvm_comparativos_revisor.py](../../../../tests/cdp/test_cvm_comparativos_revisor.py).

## Consenso de lucro por ação

A opção de EPS por período lê o corpo público `quoteSummary.earningsTrend`,
preserva moeda e encerramento explícitos de cada exercício e vincula contexto a
bytes, SHA-256 e recibo local. Moeda de trimestre não preenche a de um exercício;
`financialCurrency` não substitui declaração ausente de moeda da estimativa.

Essa autoridade é restrita a EPS. Campos presentes de receita na linha tipada
são recusados antes de o consumidor calcular crescimento. A remoção no produtor
sozinha era insuficiente: a revisão encontrou receita acrescentada ao CSV que
ainda alcançava o consumidor. A correção conserva o caminho legado sem
marcadores e distingue ausência de valor presente, inclusive zero.

Os bytes e a recepção não demonstram primeira publicação, poder aquisitivo, base
nominal, unidade por instrumento ou ponte entre exercício, doze meses e câmbio.
Receita exige contrato próprio; preços-alvo públicos continuam ligados à sua
fonte separada. O módulo é
[publico_eps.py](../../../../src/cdp/data/publico_eps.py).

## Contagem de ações e paridade da JBS

O [Ofício Circular B3 004/2025-VPE, de 03/06/2025](https://www.b3.com.br/data/files/B8/C2/99/5B/C77379106B8BCB69AC094EA8/OC%20004-2025-VPE%20TRATAMENTO%20DE%20POSICOES%20E%20ACOES%20EM%20GARANTIA%20EM%20VIRTUDE%20DA%20REORGANIZACAO%20DE%20JBS%20SA_PORT.pdf)
descreve a paridade de um BDR por ação Class A da JBS N.V., separada da troca de
duas ações antigas JBS S.A. na reorganização. O corpo completo recebido em
09/10/2026 tem SHA-256
`63feb3a459f60c1d069f8f822bf2400f085232e6a70a8e1e7f86166aa1b4705e`.

Essa declaração de 2025 não certifica continuidade integral dos termos, direitos
econômicos A/B ou quantidades de junho de 2026. A conciliação exige capital bruto,
tesouraria e circulação da mesma entidade, classe, data e unidade. Igualdade de
números SEC/CVM com conceitos ou datas diferentes não autoriza mudar o
denominador nem afirmar dupla subtração. O número e o bloqueio G13c permanecem.

## Reprodução e uso permitido

Os corpos construídos e os microcasos sintéticos dos testes são identificados como
DADOS SIMULADOS. PDFs primários, pixels derivados e retratos históricos usados em
testes conservam sua condição de fonte real ou derivação; seu uso como fixture não
os torna simulados. Os controles incluem contradição de campos,
composição, fonte, ausência e reabertura de CSV. Os caminhos legados permanecem
sob testes de igualdade de saída. Execute a suíte do CDP indicada em
[AGENTS.md](../../../../AGENTS.md) para conferir a integração no seu checkout.

A existência de um contrato, a igualdade de bytes e testes aprovados são provas
técnicas delimitadas. Aceite P0, comparabilidade econômica, PIT, calibração e
eficácia da carteira permanecem avaliações próprias. Não usar um comparativo,
nota ou contexto documental para completar informação financeira desconhecida.
