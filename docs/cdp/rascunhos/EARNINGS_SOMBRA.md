# Limite por cenários de resultado — diagnóstico em sombra

O módulo `cdp.risk.earnings_diagnostico` é função pura, sem consumidor operacional,
coleta, previsão de salto, alteração de veto ou emissão de ordem. Recebe dataclasses
congeladas, tuplas nativas, floats finitos e instantes `datetime` com `timezone.utc`.
Não abre arquivos, consulta relógio ou autentica referências de fonte. `bool`, int,
subclasses e objetos de cliente não são convertidos em número ou contexto.

O desenho matemático CDP usa, para lado u, perda adversa por unidade
ell=max_s(max(0,-u*j_s)). Custos proporcionais, borrow e financiamento devem ter o
mesmo período e denominador; o custo agregado k deve ser não negativo. O teto
condicional de magnitude é B/(ell+k), combinado por mínimo com todos os tetos
nativos explícitos. O candidato em sombra mantém o lado e não aumenta a magnitude
recebida. Crédito líquido negativo fica insuficiente, sem clamp ou imputação.
Nenhum resultado é sugestão de ordem ou comprovação de adequação econômica.

Evento/cenário, custo ou restrição ausente mantém o limite desconhecido. Retorno
oficial zero é dado; cenário de preço abaixo de -100% é inválido. Estimativa de
evento mantém todas as janelas e sua classificação. Captura e recepção declaradas
devem preceder o corte; hashes e datas declarados não certificam PIT. A linha/classe
e o retorno total USD são contrato explícito a conciliar pelo receptor futuro.
Não converter preço local ou ADR usando uma razão presumida.

Cenários não garantem perda máxima absoluta, especialmente para short sem proteção.
O orçamento absoluto é fora do escopo. Troca de lado exige outro contrato; novo
short bloqueado pelo gate nativo permanece bloqueado. A função recebe a observação
do veto, mas não reexecuta nem aprova o gate. Referências de corpos nunca habilitam
operação. Todos os testes usam **DADOS SIMULADOS**.

Esta fórmula é desenho condicional CDP; não reproduz o modelo probabilístico de
Dubinsky/Johannes. O corpo integral e os insumos públicos de opções necessários
àquela alternativa continuam pendentes. Evento PIT, orçamento, cenários, termos
de custo/borrow e uso econômico do resultado exigem qualificação própria.
