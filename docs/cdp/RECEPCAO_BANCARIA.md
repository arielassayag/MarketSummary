# Recepção prospectiva de produtos bancários

O opt-in `recepcao_bancaria=True` vincula metadados dos saldos **Ordinary Shares Number** de
GGAL.BA aos produtos Yahoo arquivados e vincula `market_cap`/`close` de GGAL ao membro físico
escolhido pelo `MarketStore`. Valores, moedas, períodos, estimativas e prioridades não mudam.
GGAL ADR e GGAL.BA doméstica continuam linhas distintas: o vínculo não estabelece razão ADR,
classes, denominadores, owners ou equivalência econômica.

`MarketStore.load` exige tipo nativo exato, `verify=True`, produto não sintético e
`conhecimento_ate` com fuso explícito. O campo opcional `MarketData.contexto_bancario` nasce
somente nessa leitura. O contexto fixa todos os membros/manifests escolhidos e o universo
físico. O fechamento é a célula `close` original da barra; `adj_close` derivado e o
`created_at` da composição não fornecem disponibilidade. Fundamentos continuam vindo do
último quadro inteiro, incluindo suas ausências. `SourceRecord` inteiro é conservado; os
produtores específicos são identificados por `yahoo_prices` e `yahoo_fundamentals`.
Cada membro é recebido por FD com `O_NOFOLLOW`, travessia `openat` de pais/raiz e
conferência `fstat` antes/depois e `lstat` final. O recibo liga SHA/corpo à identidade
dev/inode/mode/size/mtime/ctime/nlink e ao namespace recebido; atime não fornece evidência.
Raiz e diretórios próprios mantêm M6 completo. Ancestrais externos compartilhados são
conferidos por dev/inode/tipo/mode via FD/path; seus nlink antes/depois são observações,
pois criação/remoção de diretórios irmãos pode alterá-los sem mudar o produto. Essas
observações iniciais permanecem literais no recibo e não renovam a recepção/cache.
Preços, fundamentos e Universe são confrontados com a desserialização dos mesmos bytes
fixados. Manifesto, quadros completos e universo em memória ficam selados em custódia
privada. `truncate` nativo registra uma vista filha com o readset original; mutação de
quadros, manifesto, universo ou fabricação por DTO não transfere essa custódia.

`publico.demonstrativos` exige o mesmo universo/contexto físico quando o opt-in está ligado.
`cobertura.coletar` encaminha o contexto do mercado e exige a política temporal e de
recepção observada já existente. O contexto de mercado não autentica raw Yahoo ainda não
lido: cada recepção Yahoo lê o índice inteiro, a linha `RegistroArquivo` efetivamente
escolhida, demonstrações e info. Um mesmo SHA repetido no índice não escolhe a coleta mais
antiga. A rubrica, o ordinal, o período, o valor original e a moeda do raw são confrontados.
A seleção conserva a ordenação nativa `(data_coleta, caminho)` e o ordinal físico no
índice inteiro. Duas linhas indistinguíveis da mesma coleta são recusadas; a cauda sem
newline não é promovida a registro persistido, embora seus bytes integrem o recibo.

Captura declarada e recepção física própria são instantes separados. O relógio da recepção
é interno, UTC, depois da leitura integral e revalidação. `disponivel_desde` é o máximo dos
limites declarados e dessa recepção real. Um corte anterior à recepção é recusado; não se
ajusta o corte ao resultado. O mesmo contexto pode servir a um consumidor posterior com
corte explícito posterior, mantendo o primeiro recibo verdadeiro e os mesmos bytes/readset.
Criar outro contexto exige outra recepção real. Coletas em precisão de segundos usam o
limite superior conservador; precisão indeterminada não recebe hora inventada.

`received_date` estimada e `pit_estimado=True` continuam conservados. A estimativa aparece
também como `data_publicacao_estimada`; publicação primária continua ausente. O envelope
e `recepcao_fisica_utc` conservam o instante UTC integral. `data_recebimento_documento`
transporta separadamente a data civil de São Paulo exigida pelo consumidor nativo; essa
representação civil não cria hora nem altera o corte.
O envelope
do parquet não restaura o raw `marketCap` de `Ticker.info`, que permanece não arquivado.
Os readsets públicos e de mercado são explícitos. Nenhum sidecar ou parquet oficial é
escrito pelo leitor. Futuro ensaio financeiro precisa receber ambos os readsets físicos.

O manifesto opcional v4 transporta envelopes/readset e exige contexto nativo vivo em
`conferir(..., recepcao_bancaria=True, contexto_bancario=ctx)`. Um JSON/DTO/hash/data caller
não substitui a recepção. Na validação prospectiva, ausência ou downgrade para v3 é recusa.
Sem opt-in, o contrato v3 e a seleção legada permanecem. O gate financeiro não é ativado
automaticamente pela adição desses metadados.
O participante v4 conserva valor/moeda/frequência e grão original completo, com
tabela/rubrica/ordinal/período, RegistroArquivo/SourceRecord e fonte literal. O registro
nativo confronta a linha com o envelope recebido e sela um binding privado. Refazer
um manifesto autoconsistente não autoriza valores, moedas, fontes ou locators alterados.
Esse binding se limita ao estoque ou célula original: não certifica quantidade por ADR,
conversão, TTM, NI, ROE ou valor calculado.
Vestígios de binding/envelope recebido não viram participantes legados pela remoção do
envelope superior ou troca de classificação. Linhas e componentes fora desse recorte,
sem vestígios, continuam sujeitos ao gate anterior; o contexto bancário não os autentica.

Permanecem os conflitos econômicos de classe ADS versus ações domésticas/total A+B,
quantidade Galicia 2024 Yahoo versus primária comparativa, diferença Supervielle de
20 ações, cancelamentos/datas e owners. A recepção técnica não escolhe um denominador
nem qualifica G13. As ausências históricas e o raw marketCap não arquivado permanecem.

Os testes específicos são offline e usam cópias literais de produtos públicos versionados;
testam custódia, transporte e adulteração sem TTM, NI, ROE, BVPS, rating, solver, gerador,
aquisição ou escrita de livro. Esses controles não certificam modelo, G13/G19, P0, PIT da
carteira inaugural nem disponibilidade das lacunas anteriores.
