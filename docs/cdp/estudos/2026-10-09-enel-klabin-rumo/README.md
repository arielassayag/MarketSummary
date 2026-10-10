# Enel Chile, Klabin e Rumo — conferência documental delimitada

Esta nota torna recortes dos estudos encerrados acessíveis sem diretórios privados.
É suporte à auditoria do CDP. Não apresenta novos financeiros completos, recomendações,
carteira, normalização ou aceite P0. O retrato recebido é o de
[`7f0d368c`](https://github.com/arielassayag/MarketSummary/tree/7f0d368c1a5bba0c1bbe948aea38dda232e34852),
com gerador `af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9` e corte declarado
`2026-10-09T14:19:57.833570+00:00`. O candidato documental parte de DEV
`3c27b35914eb03b135987df6aefe3e87e2c1e7b6`; esse código posterior não substitui o gerador histórico.

O [quadro gerado por código](QUADRO.md) separa fatos reportados, composições documentais
e desconhecidos. [EVIDENCIAS.json](EVIDENCIAS.json) contém SourceID, URL, SHA-256,
recepções UTC declaradas, entidade, moeda, escala, período, versão, ordem, colunas e
localizadores físicos. Inclui somente recortes factuais, recibos resumidos e pins dos
estudos originais. Não redistribui os corpos externos ou páginas completas.

## O que foi demonstrado

**Enel Chile.** O XML anual em USD de 2025 foi recebido em uma coleta anterior,
em `2026-10-07T03:18:30+00:00`, com precisão de segundos. Sua cópia no estudo não
foi nova recepção HTTP. Na inspeção corrente dos caches, a instância e seu índice
estavam ausentes do executor e do checkout ROOT. O percurso SEC ordinário reconheceu
o documento quando recebeu esses corpos: não foi demonstrado defeito do parser ou
seletor, nem necessidade de novo produtor. A convenção interna `received_date` usa
o `filed` civil; a recepção efetiva pertence a `disponivel_desde`. Uma data de coleta
não substitui a de filing.

O companyfacts corrente recebido não tinha fatos monetários USD de 2025/2026.
O 6-K de junho de 2026 estava marcado como não XBRL nas submissions e não era
selecionado nessa fronteira ordinária. Respostas 403 impediram receber os corpos
contemporâneos de RI/6-K: seus envelopes negativos estão resumidos nas evidências.
Isso não prova um 403 histórico da instância anual, que já havia sido recebida.
O patrimônio dos proprietários e o lucro anual são conceitos e períodos diferentes.
`decimals=-3` expressa precisão; a escala dos fatos XML é 1. A nota 3 declara mudança
funcional CLP para USD em 01/01/2025, prospectiva, e reapresentação retrospectiva da
moeda de apresentação. Essa ponte reportada não autoriza uma conversão arbitrária
dos insumos. A extração de dívida continha contextos dimensionais; dívida consolidada
não foi comprovada. Todos os participantes efetivamente consumidos exigem contrato
de adoção pelo executor; atualizar dois saldos não certifica G19 ou PIT.

**Rumo, DVA.** No PDF original do semestre de 2025, página física 28, a rubrica
escolhida pelo caminho CVM inclui expressamente perda por redução ao valor recuperável.
A DFC, página 26, e a nota por natureza, página 84, separam essa perda da depreciação
e amortização. O montante CVM está correto. A preferência incondicional por
`7.04.01` em `_itens_dva`/`_preferir_dva`, combinada com o nome de D&A puro no modelo,
produz uma classificação econômica incompatível nesse participante original do TTM.
O PDF de junho de 2026, página 33, mostra o comparativo de 2025 reapresentado com
itens separados. Ambas as bases permanecem nas evidências. A nota 2.2.1, página 39,
explica uma mudança na DVA ligada à construção própria; não atribui expressamente
toda a reclassificação da perda a essa mudança. Não se troca o original pelo
comparativo posterior, nem se subtrai impairment por heurística universal.

**Errata obrigatória da autoria.** O pacote conceitual original preserva uma
reexecução negativa: `AssertionError: PROVA_CONCEITUAL.json`. Seu parecer e comandos
afirmaram aprovação incorretamente. A [errata externa](ERRATA_DVA.json) corrige
essas afirmações sem reabrir o pacote: a comparação de chaves de páginas inteiras
com chaves textuais JSON passou após roundtrip JSON. Preservou montantes, períodos,
rótulos, AST do produtor e guardas; não acrescenta caso financeiro. O leitor público
abaixo tem escopo próprio, distinto daquele harness e das APIs ordinárias históricas.

**FCFF de Klabin/Rumo.** As contas delimitadas de D&A restituída na DFC, capex,
pagamentos e estoques participantes fecharam com os originais CVM; isso não valida
todas as premissas dos modelos. Em Klabin há exaustão biológica e componentes
florestais que devem conservar seus conceitos. Em Rumo, o perímetro de arrendamentos
do participante inclui concessões/outorgas e outros passivos; a soma documental
confere na mesma data de 30/06/2026, mas sua dedução econômica no valuation não foi
certificada. O agregado `6.01.02` mistura tributos, passivos financeiros e outras
rubricas: uma identidade contábil que fecha não o transforma em Δgiro operacional.

**ROU Rumo.** As adições ao custo são reportadas separadamente em 6M2026,
2025 anual e 6M2025, nas páginas físicas 81, 101 e 70, nota 5.12.3. O quadro calcula
somente a composição documental condicional `6M2026 + A2025 − 6M2025`.
Adições, reajustes, transferências, amortização, pagamento e passivo não são
intercambiáveis. A igualdade agregada observada entre adições de custo e passivo
nos três termos não estabelece uma regra geral de IFRS 16. As políticas de custo
e valor presente diferem. Não houve adoção desse fluxo no FCFF; giro, classificação
do reinvestimento e demais participantes continuam pendentes.

Os PDFs Rumo foram recebidos depois do corte declarado. Instante exato da primeira
publicação permanece desconhecido; autorização das demonstrações e filing civil
não são recepção UTC. Lucro ou fluxo June2026 da Enel não foram autenticados pelos
envelopes 403. Ausência não recebe zero. Nenhum desses controles certifica PIT,
normalização, P0 ou eficácia da carteira.

## Relê-los em outra máquina

O leitor da V2 reconstrói intervalo e frequência pelos períodos físicos e coeficientes dos termos, e confere entidade, moeda, escala, consolidação, versão/ordem e origem documental. O CNPJ e a denominação são campos do CSV primário; seu vínculo ao `issuer_id` é uma declaração curatorial versionada nas evidências. Esse contexto não prova PIT nem integração financeira. Rótulos econômicos de itens e perímetros continuam declarativos; o fechamento de uma composição não os torna normalizados. Grão conferido por bytes/linhas físicas e pelo mapeamento curatorial versionado não prova comparabilidade econômica, PIT ou validação do código atual dos modelos. D&A DFC, remensuração/imparidade e concessões continuam distintos. A revisão independente da V1 encontrou duas aceitações indevidas de rótulos e falta de contexto no quadro; seus negativos permanecem nos pins da V2.

Use a versão pública do repositório que contém esta nota e as dependências já
declaradas no projeto (`pypdf`, sem novo runtime). Obtenha separadamente, pelas URLs
dos SourceIDs nas evidências, os sete corpos e guarde-os em um diretório de sua
escolha. O programa não baixa nada. Se o servidor negar acesso ou fornecer bytes
com SHA diferente, conserve a negativa; não substitua a versão histórica.

Na raiz do checkout público, com o ambiente do projeto instalado, execute o
[leitor documental](../../../../scripts/cdp/cdp_conferir_estudo_financeiro.py):

```sh
uv run python -B scripts/cdp/cdp_conferir_estudo_financeiro.py \
  --evidencias docs/cdp/estudos/2026-10-09-enel-klabin-rumo/EVIDENCIAS.json \
  --corpo ENEL_XML2025=../fontes/enic-20251231x20f_htm.xml \
  --corpo CVM_ITR2026=../fontes/itr_cia_aberta_2026.zip \
  --corpo CVM_ITR2025=../fontes/itr_cia_aberta_2025.zip \
  --corpo CVM_DFP2025=../fontes/dfp_cia_aberta_2025.zip \
  --corpo RUMO_PDF6M2026=../fontes/rumo_junho2026.pdf \
  --corpo RUMO_PDF2025=../fontes/rumo_dezembro2025.pdf \
  --corpo RUMO_PDF6M2025=../fontes/rumo_junho2025.pdf
```

Troque apenas os caminhos pelos seus arquivos. Pode fornecer um subconjunto;
as fontes restantes ficam explicitamente não fornecidas e as contas dependentes
não são concluídas. O JSON sai na saída padrão. O leitor valida SHA, tamanho,
consistência de URL/recibo UTC, corpo PDF, ordinal/contexto/unidade do XML e
membro/linha/versão/ordem do CSV. Relê lexemas nas páginas e qualificadores PDF
indicados e recalcula as contas em Decimal. Não importa CDP, executa modelo,
consulta rede, inicia processo ou grava arquivos; a guarda recusa esses efeitos.
Registra seis metadados das entradas antes e depois.

As observações de companyfacts, submissions, cache, nota 3 e negativos do harness
Enel estão identificadas como evidência do estudo fechado que este leitor não
reexecuta. O subconjunto XML carregável não certifica todas as ocorrências ou todos
os participantes do estudo anterior.

O recibo público é declaração histórica da autoria, não assinatura do servidor.
Hash demonstra igualdade de bytes, não autenticidade da conexão ou primeira
publicação. Conferir automaticamente uma linha localizada não certifica sua
classificação econômica; a leitura das políticas continua necessária. Este leitor
não reexecuta a coleta, o seletor SEC ordinário, o harness privado completo, o livro
ou os modelos. Consulte também [REPRODUZIR.md](../../REPRODUZIR.md) e os
[contratos documentais](../../auditorias/2026-10-09/CONTRATOS_DOCUMENTAIS.md).
