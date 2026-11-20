# Eventos corporativos e retificação financeira

Mudanças de unidade (desdobramento, grupamento e razão de ADS) são declaradas em
`configs/cdp/eventos_corporativos.yaml`, com anúncio, vigência, fator de quantidade,
fonte primária pública e SHA-256 dos bytes arquivados. A ausência de evento nunca
vira um fator inferido de preço. Razões ADR são aplicadas por data; a razão nova
não modifica observações anteriores à vigência.

O encadeamento usa retorno ajustado da mesma coleta quando disponível. Sem essa
barra, somente evento verificado autoriza ajustar a mudança de unidade. Uma
variação extrema sem base comparável interrompe a composição; retornos sem base
ajustada ficam ausentes no painel e impedem o fechamento de posições mantidas.
Diferença material entre preço e retorno econômico também bloqueia a marcação,
inclusive quando a fonte aparenta ter ajustado o preço. Não há override para
transformar ausência de evidência em retorno. Fração de ação decorrente do evento
exige comprovação do tratamento; não se inventa caixa em substituição.

O mesmo fator transforma quantidade e preço comparável na marcação diária,
intradiária e no preço médio usado em stops de short. A barra provisória conserva
o rótulo provisório. O modelo de risco e o cálculo de retorno total usam a série
em base comparável; dados brutos e seus manifestos não são editados. A recepção bancária conserva a identidade do universo quando nada mudou; corte que exija outra unidade é recusado antes de transferir o contexto físico, até existir recepção própria para essa transformação.

## Retificação da cauda

A retificação financeira exige pedido do operador, executor designado, ramo main,
uma execução diária admitida e sua trava. O gate expõe a pendência financeira;
o modo manual altera somente a admissão de horário, não ignora agenda ou trava.
Rotina sem supervisão que encontre essa pendência deve parar e relatá-la, sem
repetir o fechamento nem publicar o número antigo como novo resultado.

Desenvolvimento nunca grava o livro. Depois da integração das fontes, no clone
executor, a sessão de operador autorizada segue. Quando a versão antiga ainda
não reconhece a pendência financeira, receba primeiro a atualização de fontes
já integrada usando `cdp sincronizar --executar`; isso não admite uma rotina,
não adquire trava e não retifica o livro. A seguir faça uma única admissão:


```sh
uv run python -m cdp executor verificar
uv sync --frozen --extra dev --extra ai
uv run python -m cdp rotinas gate --tarefa cdp-diario --manual --adquirir
uv run python -m cdp sincronizar --executar
uv run python -m cdp daily rectify --date AAAA-MM-DD --mind codex
uv run python -m cdp daily rectify --date AAAA-MM-DD --mind codex --publish --execucao ID --trava ID
uv run python -m cdp verify
uv run python -m cdp painel --sem-local
uv run python -m cdp publicar --tarefa cdp-diario --mensagem "CDP: retificação financeira" --execucao ID --trava ID --mente codex
uv run python -m cdp trava liberar --id ID
```

Com gate recusado, não prosseguir. Trocar os IDs pelos recebidos na própria
execução. A liberação ocorre também em falha; trava perdida não pode ser liberada
por quem deixou de ser o titular. Não usar outra rota de publicação.

A prévia recalcula CDP e sombra com o motor diário, fontes arquivadas e histórico
anterior ao alvo. Não coleta preços novos, não decide nem repete ordens MOC.
A versão atual aceita apenas a cauda, fora de dia de efetivação. Histórico com
sucessores ou execução no alvo exige replay integral autenticado e é recusado.

Cada série recebe anexos imutáveis em sua pasta `retificacoes`, com registro e
diagnóstico integrais. O recibo vincula hash e bytes do original, candidato,
evidência e evento novo na trilha. A leitura corrente usa a versão retificada;
o CSV original permanece intacto e sua projeção corrente incorpora a retificação.
O próximo registro encadeia o hash retificado. A verificação confere as contas,
os originais, a ramificação autenticada e os novos elos. Anexo removido ou
adulterado bloqueia a leitura corrente; repetição literal não duplica evento. A prova matemática da cadeia pode ser reutilizada apenas para o mesmo texto completo lido; cada chamada relê fisicamente a trilha antes do cache. A seleção financeira também é vinculada ao conteúdo da própria leitura, sem confiar em tamanho ou mtime.

O relatório completo novo fica na subpasta `retificacoes/financeira` da data,
com identificação explícita de retificação e recibo próprio. O recibo também
protege os relatórios originais. UI e portal selecionam a edição autenticada
corrente; o original continua disponível nos dados abertos. Integridade da trilha
não equivale à validação econômica de toda informação do provedor.

## Embraer — vigência em 16/11/2026

Fonte primária: [comunicado de 30/10/2026](https://www.embraer.com/media-center/en?detail=33634&mediatype=NEWS),
também arquivado na [SEC](https://www.sec.gov/Archives/edgar/data/1355444/000129281426005066/embj20261029_6k.htm).
O ADS passou de quatro ações locais para uma, com quatro ADSs novos por ADS antigo.
A evidência HTML integral e seu SHA-256 estão vinculados no catálogo. Não houve
emissão de ações ordinárias por esse evento. Os valores corrigidos são produzidos
pelo motor; o diagnóstico preliminar não substitui o registro retificado selado.

### Lacuna da janela de preço em 17/11/2026

O incremento de 17/11 preserva `prev_date=2026-11-16` sem preço anterior na
janela do Yahoo. O incremento de 16/11 tem o fechamento original, já na nova
unidade. A [Nasdaq confirma os dois fechamentos](https://api.nasdaq.com/api/quote/EMBJ/historical?assetclass=stocks&fromdate=2026-11-16&todate=2026-11-17);
a consulta Yahoo arquivada confirma a vigência do split, registra a lacuna em
16/11 e não registra distribuição nem mudança de unidade em 17/11.

O leitor confere as duas respostas arquivadas por SHA-256 e confronta as barras
seladas antes de recompor somente o predecessor dessa janela. O manifesto
composto inclui os hashes e identifica a consulta como retrospectiva. A
quantidade segue na unidade posterior ao split. Arquivos brutos e o relatório
retificado de 16/11 são preservados. A prova não autoriza outras lacunas e não
se apresenta como recepção bancária contemporânea.
