# Mapa público do snapshot de 07/10/2026

Este diretório organiza 233 empresas, 281 linhas negociadas, oito ETFs e oito vistas de índices por proxy. São 241 modelos financeiros, e não 249 valuations independentes. Os números são extraídos pelo programa de inventário; preços-alvo, ratings, métodos, flags PIT e portões são os valores históricos recebidos. A existência de uma ficha ou a reprodução de uma conta não certifica sua adequação como investimento.

## Arquivos para leitura

- [CONTRATOS_DOCUMENTAIS.md](CONTRATOS_DOCUMENTAIS.md): escopo e limites dos contratos novos de demonstrações, comparativos e consenso; separado do mapa histórico.
- [mapas/EMPRESAS.csv](mapas/EMPRESAS.csv): empresa, linha e moeda, métodos presentes, portões, lacunas, publicação desconhecida e link ao JSON da versão histórica.
- [mapas/ETFS.csv](mapas/ETFS.csv) e [mapas/INDICES.csv](mapas/INDICES.csv): cota do proxy, cobertura bottom-up, composição e limite da identificação do índice.
- [mapas/METODOS.csv](mapas/METODOS.csv): pesos configurados e métodos disponíveis na memória. O peso configurado não é apresentado como o peso final após renormalização.
- [mapas/POSICOES_ETFS_MOEDAS.csv](mapas/POSICOES_ETFS_MOEDAS.csv): participantes e moedas de linha, estimativas originais e demonstrações declaradas, conservando as imputações.
- [mapas/RESUMO.json](mapas/RESUMO.json) e [mapas/METADADOS.json](mapas/METADADOS.json): contagens e hashes das entradas e da fonte geradora, sem paths pessoais.
- [PARECER_HISTORICO.md](PARECER_HISTORICO.md) e [PRIORIDADES_HISTORICAS.json](PRIORIDADES_HISTORICAS.json): reprodução literal da revisão não autora encerrada. Afirmações como “recálculo não exercitado” pertencem ao instante daquele fechamento.
- [ADENDO_REPRODUCAO_ROOT.json](ADENDO_REPRODUCAO_ROOT.json): evidência posterior atribuída ao ROOT, preservada separadamente. Ela não reescreve o parecer histórico.

As prioridades são históricas, com causa e prova necessária; não são uma fila operacional atual automaticamente aprovada. Em particular, A10 era uma hipótese no fechamento original. O estudo causal posterior de ARGT confirmou a mecânica de fator ARS uniforme com origens nominais heterogêneas e conservou o diagnóstico “Not comparable without bridge”, sem escolher USD global ou corrigir um alvo. Esse desenvolvimento não foi inserido retroativamente nas prioridades históricas.

## Vínculo de versões e autoria

Os participantes do snapshot foram recebidos da publicação vinculada ao commit [`af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9`](https://github.com/arielassayag/MarketSummary/tree/af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9/book/cobertura/2026-10-07). O próprio manifesto declara o código gerador [`5cb2d4ab8c250b3289dc90fb4e655637335a0aec`](https://github.com/arielassayag/MarketSummary/tree/5cb2d4ab8c250b3289dc90fb4e655637335a0aec/src/cdp). Código mais recente não substitui automaticamente o gerador histórico.

A revisão histórica é não autora dos modelos financeiros. A portabilidade do inventário e este índice foram preparados por Codex como derivação documental explícita. O recálculo financeiro posterior é do ROOT: 632 participantes manifestados efetivamente recebidos e conferidos, 233 empresas e oito ETFs recalculados com o gerador histórico, nenhuma divergência dentro da tolerância relativa nativa de `1e−5`, arquivos antes/depois literais e nenhuma nova fonte ou semente. Os hashes dos recibos originais e o escopo exato constam do adendo. O autor deste inventário não reexecutou esse cálculo financeiro, nem o apresentou como oráculo independente de todas as fórmulas.

## Gerar o mapa em outra máquina

O programa [scripts/cdp_mapear_modelos.py](../../../../scripts/cdp_mapear_modelos.py) usa Python e PyYAML, já incluído nas dependências do projeto. Ele não importa CDP, não consulta rede, não constrói modelos e não grava entradas. As saídas são JSON/CSV determinísticos; o destino precisa ser novo. A raiz documental confina os arquivos do manifesto, incluindo os caminhos irmãos legítimos `../publico`.

Obtenha o repositório público e mantenha duas cópias de leitura das versões, em diretórios escolhidos por você:

```sh
git clone https://github.com/arielassayag/MarketSummary.git cdp-publico
git -C cdp-publico worktree add --detach ../cdp-snapshot-af6 af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9
git -C cdp-publico worktree add --detach ../cdp-gerador-5cb 5cb2d4ab8c250b3289dc90fb4e655637335a0aec
```

Na versão do repositório que contém este script, execute com o ambiente instalado do projeto:

```sh
uv run python -B scripts/cdp_mapear_modelos.py \
  --snapshot ../cdp-snapshot-af6/book/cobertura/2026-10-07 \
  --raiz-arquivos ../cdp-snapshot-af6 \
  --universo ../cdp-snapshot-af6/data/universe/latam_universe.csv \
  --indice-publico ../cdp-snapshot-af6/data/publico/indice.jsonl \
  --fonte-geradora ../cdp-gerador-5cb/src \
  --commit-snapshot af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9 \
  --prioridades-historicas docs/cdp/auditorias/2026-10-09/PRIORIDADES_HISTORICAS.json \
  --saida ../mapa-cdp-2026-10-07
```

Nenhuma entrada depende de um diretório privado do Codex, de um executor registrado, de arquivos de ensaios ou de recibos absolutos. O programa lê os participantes do manifesto, os dois pacotes de insumos, os modelos/configuração recebidos, o universo, o índice de hashes de brutos e a fonte geradora. Ele não exige baixar os corpos de todos os 1.480 registros do índice público para gerar o mapa. Verificar o conteúdo primário de cada registro é trabalho documental diferente.

É possível fornecer as mesmas entradas por extração dos arquivos públicos, sem os worktrees, mantendo os caminhos relativos do manifesto e conferindo os hashes. Se qualquer participante necessário não for obtido, o programa recusa a reprodução e informa a ausência; uma resposta HTTP atual ou um corpo com SHA diferente não substitui os bytes antigos. A origem Git do diretório de fonte deve ser conferida pelo terceiro; o inventário de SHA não faz essa origem surgir por declaração.

O gerador produz também o ledger de insumos, portões e seus hashes, além dos resumos publicados aqui. Para conferir a derivação histórica, compare as contagens de [mapas/RESUMO.json](mapas/RESUMO.json), os hashes de entrada em [mapas/METADADOS.json](mapas/METADADOS.json) e a igualdade literal das prioridades. Os testes portáteis usam exclusivamente DADOS SIMULADOS e exercem os mesmos contratos de caminhos, hashes, ausência e tipos de evidência.

## Limites que continuam explícitos

Dados Yahoo padronizados, consenso, fatos reportados declarados, cálculos e políticas são categorias distintas. Hash de `etfs.yaml` ou de outra transcrição autentica a configuração, não a planilha primária ou o documento do provedor do índice. Um registro de bruto com o mesmo hash cria um vínculo declarado; não prova que cada célula financeira foi relida no original.

As oito vistas de índice são proxies na moeda e na cota dos ETFs. Não se inventaram níveis em pontos, múltiplos independentes ou preços ausentes. Fontes/publicações ausentes permanecem desconhecidas; as flags PIT recebidas não foram recertificadas. Os estados dos portões e motivos de métodos retirados permanecem históricos, sem relaxamento para atingir quotas.

O recálculo ROOT demonstra reprodução técnica daquele retrato. Underwriting por empresa, coerência econômica, FX prospectivo de ARGT, PIT/vintage/holdout, eficácia da camada IA e aceite E1/E2 operacional/científico não são concluídos por essa reprodução. Também não se infere a carteira atual, uma publicação posterior ou a integração de candidatos privados a partir deste material.
