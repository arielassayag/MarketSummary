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

Esta fundação não entrega todas as técnicas P2. Risco/construção/limites, atribuição
pura, MCP de leitura, skills e empacotamento por app permanecem etapas posteriores.
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
