# Comparação documental dos retratos de 07 e 09/10/2026

O retrato de 09/10 mantém 233 empresas e oito ETFs, com preços até 08/10 e corte
declarado de coleta em `2026-10-09T14:19:57.833570+00:00`. Suas causas de revisão
mudaram. Este adendo atualiza a fila documental e preserva o mapa histórico;
o P0 financeiro, a comparabilidade, PIT e E1/E2 permanecem abertos.

| Controle recebido | 07/10 | 09/10 |
|---|---:|---:|
| Empresas | 233 | 233 |
| ETFs | 8 | 8 |
| Alvos numéricos | 230 | 229 |
| Alvos citáveis | 200 | 194 |
| Confiança C | 100 / 233 (42.918455%) | 102 / 233 (43.776824%) |
| Em revisão | 30 / 233 (12.875536%) | 35 / 233 (15.021459%) |
| PIT verdadeiro declarado | 120 | 130 |
| Entradas declaradas no manifesto | 632 | 767 |

A comparação conferiu o SHA dos 241 modelos de cada data e seus campos, sem
recalcular valuation, solver ou alvo. São 32 transições de rating,
15 de confiança e 138 de status de portão.
As entradas declaradas de manifesto não são uma contagem de novas empresas.
Conferência posterior pela interface normal do inventário09 validou os767
participantes nos corpos fornecidos e sua presença na árvoreGit7f. Isso não
autentica todos os brutos do índice público, recepçãoHTTP nova ou recálculo financeiro.

## Fontes e versões

O [retrato07](https://github.com/arielassayag/MarketSummary/tree/af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9/book/cobertura/2026-10-07) foi publicado em `af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9`
e declara o gerador `5cb2d4ab8c250b3289dc90fb4e655637335a0aec`.
O [retrato09](https://github.com/arielassayag/MarketSummary/tree/7f0d368c1a5bba0c1bbe948aea38dda232e34852/book/cobertura/2026-10-09) foi recebido da publicação
`7f0d368c1a5bba0c1bbe948aea38dda232e34852` e declara o gerador `af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9`.
O produto posterior `3c27b359` não recalcula esses arquivos imutáveis.
Hashes, contagens, grupos por status físico e as dez prioridades estão em
[PRIORIDADES_CORRENTES.json](PRIORIDADES_CORRENTES.json).

## Causas correntes

- G19 bloqueia oito empresas por idade das demonstrações: AR_BBVA, AR_CEPU,
  AR_GALICIA, AR_LOMA, AR_MACRO, AR_SUPERVIELLE, AR_TGS e CL_ENELCHILE.
  Galicia e Supervielle deixaram G13 bloqueante e passaram a G19; isso mantém
  suas fichas C e em revisão.
- Enel Chile passou de ENIC/USD a ENELCHILE.SN/CLP. A flag PIT declarada passou
  a verdadeira, mas G19 bloqueia demonstrações de dezembro2024. PIT declarado
  e atualidade das demonstrações são controles distintos.
- AR_TEO é a nova ficha sem alvo. G3/status `sem_alvo` é ausência de valor;
  G13c/status `bloqueio` é outra categoria. Os bloqueios G13c09 são AR_TEO e BR_JBS.
  A união das categorias nunca é apresentada como um único status do código.
- YPF passou de revisão a Neutro, conservou C e ficou citável. Seu FCFF normalizado
  permanece indisponível; RIM e regressão têm valores/formulas. Peso configurado
  de método indisponível não é participação efetiva. Contagem líquida e
  comparabilidade documental não receberam aceite por essa transição.
- As 38 grades com colunas invariantes permanecem: sai PE_SCCO e entra AR_YPF.
  A existência de uma grade não certifica adequação econômica do determinante.
- O código posterior corrigiu exposição de ETF sem coluna de preço e acrescentou
  gênese explícita para réplica. Os geradores dos retratos não tinham esses reparos;
  esta comparação não inicia uma réplica nem reescreve o retrato09.
- Há decisão inaugural recebida. Sua aprovação não comprova efetivação,
  diário, resultado ou análise financeira completa de todas as empresas.

Klabin/Rumo mantêm G9/G11. A coexistência legada de D&A DVA e DFC não prova
identidade conceitual ou FCFF completo. Estudos posteriores e candidatos de
reparo conservam seu próprio alcance; não alteram este retrato.

## Reproduzir a derivação documental

O [programa de inventário](../../../../scripts/cdp_mapear_modelos.py) já publicado
lê as versões recebidas, sem importar CDP ou recalcular finanças. O procedimento
do [índice histórico](README.md) continua válido para07. Para09, extraia uma
cópia da publicação7f e outra do geradoraf6 em diretórios próprios:

```sh
git -C cdp-publico worktree add --detach ../cdp-snapshot-7f 7f0d368c1a5bba0c1bbe948aea38dda232e34852
git -C cdp-publico worktree add --detach ../cdp-gerador-af6 af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9
uv run python -B scripts/cdp_mapear_modelos.py \
  --snapshot ../cdp-snapshot-7f/book/cobertura/2026-10-09 \
  --raiz-arquivos ../cdp-snapshot-7f \
  --universo ../cdp-snapshot-7f/data/universe/latam_universe.csv \
  --indice-publico ../cdp-snapshot-7f/data/publico/indice.jsonl \
  --fonte-geradora ../cdp-gerador-af6/src \
  --commit-snapshot 7f0d368c1a5bba0c1bbe948aea38dda232e34852 \
  --prioridades-historicas docs/cdp/auditorias/2026-10-09/PRIORIDADES_HISTORICAS.json \
  --saida ../mapa-cdp-2026-10-09
```

O clone `cdp-publico` e o ambiente devem existir conforme README; o destino deve
ser novo. O nome da opção `--prioridades-historicas` não transforma a fila antiga
em fila atual: o programa recebe aquela prova original literalmente. Compare as
contagens e cada status dos modelos entre as duas saídas. Para os grupos deste
adendo, separe `bloqueio` de `sem_alvo`; portão removido permanece ausente.
Esta derivação não é recálculo financeiro do09. O adendo ROOT anterior comprova
recálculo técnico do07 com seu gerador, com outro alcance temporal.
