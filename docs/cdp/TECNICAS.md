# Técnicas portáteis — fundação

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
três kernels simples; essas seis APIs exigem objetos nativos, sem transporte MCP.
MCP de leitura permanece etapa posterior. Nove skills e adaptadores
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
`Arr`/`np` de `avaliacao.py` não é fornecida; um futuro adaptador MCP terá de
fornecer tipos de transporte próprios. Outros sistemas e versões de Python
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

A versão CDP 1.6.0 é declarada somente em cdp.__version__; setuptools e os
manifestos gerados a consomem. O plugin operacional acompanha a versão e mantém
suas seis skills intactas. A qualificação de instalação descrita acima refere-se
à fundação anterior 0.1.0; novos arquivos/versionamento exigem nova qualificação
antes de declarar a distribuição 1.6.0 instalada. Avaliação comportamental das
skills e servidor MCP permanecem em trabalho.
