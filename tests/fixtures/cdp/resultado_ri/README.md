# Fixture de resultado — DADOS SIMULADOS

Os dois PDFs são documentos mínimos originais, criados por `gerar_fixture.py`. Os valores,
as entidades, os eventos e as datas são fictícios. Nenhuma página de relatório de empresa
foi reproduzida. O catálogo contém apenas períodos, rubricas, unidades e localizadores de
prova; os valores são extraídos dos PDFs pelo leitor real.

Para regenerar os quatro arquivos de entrada e conferir os testes, a partir da raiz:

```sh
python tests/fixtures/cdp/resultado_ri/gerar_fixture.py
uv run pytest tests/cdp/test_cobertura_resultado.py -q
```

O gerador usa apenas a biblioteca padrão. `oraculos_independentes.json` registra a aritmética
Decimal dos valores fictícios, separada do parser. Os 19 testes (31 casos parametrizados)
exercitam anual e TTM, subtotais, notas, reconhecimento temporal do evento, ganho/perda,
unidades, base, ausência, duplicação, reapresentação, disponibilidade, hashes e consumidores.
A fixture cobre contratos e gramática mínima; não certifica a fidelidade dos layouts de RI.
A prova de ingestão de documentos primários permanece nos ensaios locais ignorados pelo Git.
