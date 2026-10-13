# Técnicas portáteis

`cdp.tecnicas` expõe três kernels determinísticos: custo do patrimônio em USD,
P/VPA justificado e estimativa de ações preenchidas pela capacidade. As funções
delegam aos modelos nativos; não coletam dados, escolhem fonte, atribuem rating,
decidem carteira ou gravam o livro. Argumentos são declarados pelo chamador.

```python
from cdp.tecnicas import calcular_ke, avaliar_pb_justificado, estimar_preenchimento
```

Taxas são decimais; capacidade e preço são USD e a ordem é quantidade inteira de
ações. O múltiplo preserva broadcast, forma, NaN e recusa do modo estrito. Na rota
portátil de preenchimento, ausência e valores não finitos são recusados mesmo para
ordem zero; capacidade finita não positiva segue a restrição zero nativa. Nenhuma
ausência de dados financeiros é preenchida como zero.

O recurso nomeado `latam_simulado_v1` demonstra somente os schemas de configuração
e carregamento do universo. Diz **DADOS SIMULADOS**, tem execução ausente e não é
política de valuation completa, mandato operacional ou fonte financeira recebida.
Os hashes identificam seus bytes; não certificam disponibilidade, PIT ou aprovação.

```sh
cdp-tecnicas listar
cdp-tecnicas exemplo latam_simulado_v1
```

`carregar_exemplo(nome)` usa recursos do pacote, sem buscar um clone.
`carregar_arquivos_locais` exige os caminhos de fund, valuation, cobertura,
universo, nomes e mapa fechado de catálogos. Todos os cinco membros de cobertura
são declarados; falta encerra sem arquivo vazio, catálogo default de outra origem
ou download. O parser e os hashes textuais são os nativos; SHA de bytes, hash
textual e hash canônico de configuração mantêm seus papéis distintos.

A CLI operacional continua exigindo o workspace e o executor apropriados. O wheel
não contém livro, raw financeiro, credencial, identidade local, executor ou permissão
de publicação. Um recurso de exemplo nunca fornece identidade operacional.

A fachada P2 também expõe as funções nativas decompor_risco, estimar_modelo_risco,
construir_candidata, conferir_limites, somar_atribuicao e somar_componentes por
importação lazy. Modelo, painel, configuração e demais objetos são declarados;
a assinatura/unidades nativas são preservadas. Candidato do otimizador não é
decisão, compliance não aprova e soma de contribuições diárias não é retorno
composto. A cobertura parcial conserva days. A CLI listar continua mostrando os
três kernels simples; essas seis APIs exigem objetos nativos e não são entradas
livres do transporte. Nove skills e adaptadores
são descritos abaixo; não concedem autoridade de execução.
A fundação foi verificada em macOS ARM64/Python 3.13.12: wheel e sdist
construídos offline, membros/RECORD e código instalado conferidos, recursos
carregados em diretório vazio, sem checkout no caminho de imports ou instalação
editável. A rota de venv usou dependências congeladas e hashes em modo offline.
A primeira tentativa de `uv tool` offline não tinha metadados de registro no cache;
foi preservada. A instalação por `uv tool` consultou o PyPI oficial com versões
fixadas e sem build; o uso posterior por CLI e `uvx` passou offline.

A comparação de parsers no smoke cobre o exemplo e os arquivos declarados que
usam os mesmos helpers; não é confronto independente de todas as políticas
legadas. O focal incluiu compatibilidade de configuração e o peer comparou os
blocos nativos por AST. A resolução autônoma por `get_type_hints` dos aliases
`Arr`/`np` de `avaliacao.py` foi corrigida e conferida em teste dirigido; o MCP
usa tipos de transporte próprios. Outros sistemas e versões de Python
ainda não foram verificados. Nenhuma dessas checagens certifica P0/PIT, aprova
um modelo ou fornece autoridade de operação.

## Técnicas e adaptadores

As nove técnicas cobrem avaliação LatAm, custo de capital, construção neutra a
fatores, risco long/short, execução MOC, tese, nota de pesquisa, comunicação
institucional e auditoria/reprodução. A fonte única está nos recursos do pacote,
em recursos/tecnicas/skills. Os espelhos de Codex/Copilot/Cursor, Claude e extensão
Gemini são gerados; os corpos são literais e não devem ser editados separadamente.
Cada técnica trabalha em leitura ou rascunho privado, sem conceder shell, decisão,
publicação ou desligamento do kill switch. Não substitui as skills das rotinas.

```sh
cdp-tecnicas adaptadores --saida /tmp/cdp-tecnicas-rascunho
cdp-tecnicas adaptadores --saida /tmp/cdp-tecnicas-rascunho --verificar
```

A verificação não cria o destino. A exportação aceita apenas destino explícito,
recusa diretórios oficiais e links simbólicos antes da primeira escrita; é um
comando de desenvolvimento. Não instala nem ativa extensões no aplicativo.
Marketplace e manifestos somente distribuem essas técnicas, sem hooks ou
permissões automáticas. O catálogo segue o [formato Agent Skills](https://agentskills.io/specification),
o [plugin Claude](https://code.claude.com/docs/en/plugins-reference) e a
[extensão Gemini](https://geminicli.com/docs/extensions/reference/).

A versão CDP 1.7.0 é declarada somente em cdp.__version__; setuptools e os
manifestos gerados a consomem. O plugin operacional acompanha a versão e mantém
suas seis skills intactas. A qualificação de instalação descrita acima refere-se
à fundação anterior 0.1.0; novos arquivos/versionamento exigem nova qualificação
antes de declarar a distribuição 1.7.0 instalada. A correção documental de seis
skills foi recebida em 54 pares literais; ela não qualifica comportamento de um
harness real. A fonte atual ainda aguarda a instalação final fora do clone.

## MCP de kernels

O extra mcp fixa o SDK2.3.0. O comando cdp-tecnicas-mcp e o módulo
cdp.mcp_readonly.__main__ oferecem três kernels simples e recursos públicos do
pacote. Ingressos e saídas têm schemas fechados, sem shell, configuração
operacional, URLs de coleta ou permissão de escrita. Erros numéricos não são
publicados como valores finitos: uma razão finita que transborda é recusada e
a sessão permanece apta à consulta seguinte. Nenhum recurso simulado autentica
um dado financeiro.

O focal desse transporte teve 379 IDs únicos, 378 aprovados e um pulado, sem
falhas/erros. A correção dirigida de OverflowError teve dois controles aprovados.
O recorte STDIO observado cobriu catálogo, custo do patrimônio, recusa de shell
e um recurso; outras rotas foram verificadas em memória. A qualificação instalada
final ainda deve verificar todos os kernels e recursos da mesma versão.

## Consultas operacionais

O contrato separado prevê nove consultas: estado, agenda, integridade, fatos,
validação de documento, carteira, decomposição de risco, modelo de cobertura e
pacote da mente. Seu contexto físico é explícito, recebido por descritor e
limitado a leitura. Não usa CWD como fonte de configuração ou identidade;
nenhum manifesto fornecido pelo cliente concede autoridade operacional.

O núcleo delega aos leitores nativos em modo readonly, preservando tipos,
máscaras, ordem, unidades, hashes nativos e o conjunto efetivamente lido. A saída
de transporte tem catálogo fechado, inclusive NaN/Inf tipados; não pode truncar
dados, stringify objetos desconhecidos ou transformar ausência em zero. Hash de
transporte identifica esses bytes e não substitui aprovação ou hash financeiro.

Plano, adendo e implementação foram recebidos por ROOT e revisão independente.
Autoria é vinculada ao contexto; ETF só aceita visão de modelo; fact_ids é
obrigatório, com lista vazia significando todos. O focal nativo V4 passou 55
casos únicos, sem falhas, erros ou pulados. Incluiu as nove consultas nos
seletores exercitados, ausência, adulteração, integridade nativa negativa e
continuidade. Os 14 registros reais vinculam ingresso, contexto, saída e readset;
não certificam todos os seletores possíveis.

O catálogo fecha 257 representações nominais. A recepção posterior à integração
conferiu os corpos dos 79 proprietários efetivos e os campos em ordem, sem
afrouxar hashes. Essa conferência documental não certifica uma instalação futura.
O transporte SDK foi recebido e integrado: 72 testes focais únicos aprovados,
sem falhas, erros ou pulados. Os corpos e o commit foram recebidos fisicamente;
esses controles não executaram o leitor instalado por STDIO. O comando
cdp-mcp-operacional exige contexto absoluto explícito e sua qualificação
por STDIO instalado continua pendente. Nenhuma consulta
publica, decide, atualiza base, prepara artefato ou opera o kill switch.

## Diagnósticos de risco em sombra

Os módulos puros de κ_F e viés recebem operandos/referências explícitos e
conservam os limites de interpretação. Referências declaradas não autenticam
corpos, disponibilidade histórica ou PIT. κ_F teve 69 focais aprovados. O viés
teve 102 únicos aprovados, incluindo a ordem modelo as-of≤selo≤início; a fórmula
NIST declara a adaptação floor e o intervalo é condicionado à IID declarada,
sem independência ou cobertura financeira comprovadas.

Earnings e overlay têm 36 e38 focais aprovados, respectivamente, revisão
independente recebida e integração local. Seus rascunhos não selecionam evento/ETF,
promovem alpha ou modificam orçamento do mandato. Fase por grupo V3 tem130 focais
aprovados, vínculo semanal/calendário declarado e integração local. Beta distribuído
V2 tem49 focais aprovados e revisão independente recebida, com a perda numérica
da V1 recusada. Ambos foram recebidos por ROOT e integrados em sombra.
Este último acompanha a equação conjunta sem intercepto da
aplicação pública BIS164; não reproduz o original integral Dimson1979 nem comprova
correção de viés. Esses focais não equivalem à suíte conjunta ou instalação nova.
