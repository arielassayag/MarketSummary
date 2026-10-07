# Ensaio operacional isolado

O comando `backtest-operacional` reproduz o ciclo do Runtime com arquivos locais: preparação,
decisão, ações fixadas, efetivação no fechamento, contabilidade, risco diário e relatórios.
As saídas ficam exclusivamente em uma pasta nova dentro de `.cdp/ensaios`. Não há coleta,
publicação do portal, alteração do livro oficial ou adoção automática dos resultados.
O backtest simplificado anterior permanece disponível.

## Modos e cronologia

| Modo | Dados | Alcance da afirmação |
|---|---|---|
| `simulado` | Captura sintética | Regressão determinística, com DADOS SIMULADOS |
| `sombra_real` | Captura real reconstruída hoje | Ensaio técnico; dependências sem vintage são declaradas |
| `pit_auditado` | Capturas historicamente disponíveis e autenticadas | Falha fechada quando falta prova temporal essencial |

Data contábil, publicação, captura real e relógio lógico são distintos. Cortar uma série de
preços não transforma fundamentos, universo ou empréstimo atuais em dados históricos conhecidos.
O manifesto guarda bytes e metadados integrais da origem, código, configuração, horários,
calendário, prefixos e limitações. A política temporal autentica capturas completas; vintages
por documento/campo e uma amostra econômica adequada permanecem trabalho posterior.

A única mudança contrafactual do mandato é a data inaugural na configuração interna do ensaio.
Ela usa a primeira montagem canônica elegível; uma terça-feira no fim de uma janela não cria
outra decisão. O arquivo oficial do mandato permanece intacto. `replay_origin.json` e o evento
inicial `REPLAY_ORIGIN` autenticam o modo e o instante real de início. Mesmo com dados reais,
o ensaio retrospectivo fica fora do IC prospectivo e não promove a fase das mentes.

Antes do horário de fechamento, o armazenamento expõe apenas o pregão anterior. A proposta
fixa ações e ticker; o fechamento aplica capacidade realizada, lotes, custos e caducidade pelas
rotinas canônicas. A próxima decisão parte do patrimônio e das ações efetivas arquivados.
Preço, volume e câmbio usados para negociar precisam ser observados no próprio pregão;
carry usado na marcação ou no ADV não autoriza um fill. Uma linha detida sem fechamento ou
câmbio próprios congela o emissor inteiro, inclusive a abertura de outra linha. USD/USD=1 é
a identidade da unidade; moeda desconhecida não recebe câmbio presumido.
Os relatórios e teses deste comando são modelos determinísticos dos fatos, sem previsão de IA.

## Execução e conferência

Execute no checkout de desenvolvimento, com uma captura local preservada e uma saída nova:

```sh
uv run python -m cdp backtest-operacional \
  --snapshot /caminho/absoluto/da/captura \
  --start 2026-09-04 --end 2026-10-06 \
  --modo sombra_real --out .cdp/ensaios/nome-novo
```

Este exemplo define a chamada; não certifica que essa janela já foi executada. A retomada
usa os mesmos argumentos e `--resume`. Fonte, configuração, código, janela e horários precisam
ser idênticos. `verify_replay(pasta)` é a API de conferência somente leitura.

Cada etapa tem arquivo imutável, âncora `REPLAY_STEP` no livro e registro encadeado em
`steps.jsonl`. Um arquivo já ancorado pode concluir o registro na cadeia. Um arquivo de etapa
sem âncora fica incompleto: sua existência e a integridade do livro não autenticam os bytes;
a retomada recusa aceitá-lo ou reexecutá-lo. Não apagar arquivos para forçar a conclusão.
Briefings, relatórios e teses existentes exigem seus recibos canônicos correspondentes.

A conclusão guarda inventário integral, `result.json` e uma única âncora `REPLAY_COMPLETE`.
Uma interrupção nessa conclusão só é recuperada após comparar inventário, etapas e recálculo
operacional exato. Remoção, adulteração, caminho redirecionado e resultado sem seus selos são
recusados. Uma falha durante a preparação inicial, antes do manifesto, exige uma nova pasta;
a pasta parcial é preservada como evidência.

## Estado do aceite

Em 07/10/2026, passaram 62 testes focais de origem, política temporal e replay, incluindo
seis pregões, duas decisões e capacidade parcial calculada por oráculo independente.
A conferência independente confirmou a recusa de arquivos de etapa sem selo, mantendo os
bytes e sem chamar novamente a ação. Recibos de artefatos, vintage por execução e marcadores
provisórios passaram. Alterar apenas séries futuras de preço, volume, câmbio e macro preservou
a primeira proposta, risco, patrimônio e componentes do resultado passado.

O primeiro ensaio real sombra concluiu 23 pregões, cinco montagens canônicas e 94 etapas,
com conferência independente, quatro outcomes maduros e o último ainda imaturo. Ele conserva
a fonte anterior aos reparos de FX/preço no MOC e é diagnóstico. As falhas originais foram
preservadas. A mesma janela foi repetida na fonte temporal 8.4 congelada: integridade,
23 pregões, cinco montagens e 94 etapas confirmados. A comparação por leitura com a fonte 7
confirmou economia diária, propostas e CSVs de posições/trades exatamente iguais, preservando
os dois livros e seus onze arquivos originais de mercado. Essa prova antecede o reparo dos
consumidores de cotações inválidas. A fonte física final 8-5 da metodologia `.8` repetiu
os 23 pregões/cinco montagens/94 etapas com integridade verde e economia preservada;
tempos do solver e hashes de encadeamento são distintos das grandezas financeiras.
A suíte ampla 5 da integração passou: 2.565 aprovados, 16 pulados, um xfail,
zero falhas e zero erros. Isso não amplia os casos contrafactuais efetivamente exercitados.

Quatro contrafactuais completos com FX ausente ou preço NaN/zero/infinito passaram no reparo
privado v3, com sete pregões e duas montagens cada. Ausência conservou ações e impediu fills e
custos posteriores; zero/infinito produziram o mesmo risco/resultado da ausência. O baseline
normal preservou 6.950 campos numéricos e os CSVs financeiros. Fonte reapresentada a um run
selado foi recusada sem escrever no livro. Revisão independente passou; os consumidores e
54 testes materiais foram transpostos para desenvolvimento. Não houve alvo de migração para
outro papel nesse driver, e ele não oferece reserva inaugural intrassessão com novo vintage:
esses limites não são substituídos por uma ordem inventada ou pela alteração de fontes seladas.

O caso de decisão atrasada com carteira anterior foi repetido no driver final: 11 pregões,
duas montagens e 48 etapas, com 25 posições anteriores. No fechamento antecipado de
27/11/2026, o instante um segundo depois da margem foi recusado, sem proposta, decisão,
booking ou custo nessa data, conservando as posições. Livro, fontes e retomada selada
permaneceram íntegros, com revisão independente. O episódio usa DADOS SIMULADOS e data
de início contrafactual; não altera o mandato oficial nem certifica todos os casos E1.

O aceite integral E1 permanece pendente: a matriz distingue episódios completos do driver,
provas de APIs e oráculos. Feriados/fechamento antecipado, dados ausentes e episódios de
squeeze/kill switch têm provas delimitadas; a extensão da sequência completa é explícita.
Esses testes técnicos não comprovam eficácia econômica,
não sanam os gates científicos P0 e não liberam a carteira inaugural.
