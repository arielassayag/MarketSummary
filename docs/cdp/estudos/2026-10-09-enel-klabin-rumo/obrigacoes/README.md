# Rumo — obrigações: fontes e reprodução documental

Este mapa distingue passivos de arrendamento, outorgas, litígios e parcelas no
consolidado. A abertura IFRS16 da nota b já pertence à nota5.6; não é dívida extra.
A revisão independente recebida foi favorável nesse escopo documental. As pontes
por contrato/fluxo para EV→patrimônio e FCFF permanecem condicionais.

- [Quadro emitido em código](QUADRO.md): abertura do estoque e contexto histórico.
- [Índice de fontes/recepções](SOURCE_INDEX.json): URLs primárias, SHA, UTC e descoberta ANTT.
- [Evidências delimitadas](EVIDENCIAS.json): linhas/lexemas, originais/comparativos, âncoras e flags.
- [Limites e próximos insumos](LIMITES.md): exceções econômicas, jurídicas e temporais.

O contexto é o retrato09/10/2026, publicação7f0d368c, geradoraf6eb0c e
corte14:19:57.833570Z. A reprodução anterior07 não prova o09. A coleta declarada07
do participante legado é distinta dos três recibos de PDFs recebidos09 depois do
corte. O instante primário exato de publicação desses PDFs é desconhecido. Nenhuma
recepção presente recertifica disponibilidade histórica, E1/PIT/P0 ou G9/G11.

## Reproduzir com arquivos fornecidos

O pin curatorial do leitor vincula as declarações desta versão: metadados de
recepção, proveniência recebida, participante legado, claims e flags. Ele impede
alterações silenciosas desses rótulos e recibos projetados; não transforma as
declarações em prova primária de identidade, evento HTTP, economia ou PIT.

O [leitor independente](../../../../../scripts/cdp/cdp_conferir_obrigacoes_rumo.py) usa Python3.12+,
stdlib e pypdf já declarado pelo projeto. A versão recebida e fixada no lock é
6.19.0. Execute no ambiente preparado do repositório (`uv sync` é a preparação
normal; não é ação do leitor), a partir da raiz. Forneça os três PDFs públicos
exatos em `insumos/`, com os nomes abaixo; os corpos externos não são versionados
neste diretório. URLs e SHAs esperados constam no índice. O leitor não baixa,
reconstitui cache do executor ou grava arquivo.

```bash
python -B scripts/cdp/cdp_conferir_obrigacoes_rumo.py \
  --fontes docs/cdp/estudos/2026-10-09-enel-klabin-rumo/obrigacoes/SOURCE_INDEX.json \
  --evidencias docs/cdp/estudos/2026-10-09-enel-klabin-rumo/obrigacoes/EVIDENCIAS.json \
  --pdf-2t26 insumos/rumo_junho2026.pdf \
  --pdf-4t25 insumos/rumo_dezembro2025.pdf \
  --pdf-2t25 insumos/rumo_junho2025.pdf \
  --formato quadro
```

Use `--formato json` para receber o ledger conferido, âncoras, flags e controles.
A saída padrão é a única saída de resultado; um redirecionamento, se desejado, é
do leitor humano/chamador. Exit0 confirma somente a conferência documental
delimitada. Exit2 recusa corpo, grão, coluna, localizador ou contexto divergente.
Não contorne403 nem substitua um PDF diferente para fazer o comando passar.

Os três controles são os mesmos herdados da revisão; reruns não ganham crédito de
casos financeiros. A linha de apoio5.6 já recebida é relocalizada para torná-los
reproduzíveis com os PDFs públicos, sem dependência de arquivo privado. A ausência
de cifra da Malha Oeste IFRS16 atual permanece `None`/`null`, nunca zero.

O conteúdo é suporte de pesquisa, sem recomendação nova, solver, alvo, publicação
operacional ou aceitação de contrato financeiro. Os textos do CDP seguem a licença
documental do repositório; links de fontes identificam seus próprios titulares.
