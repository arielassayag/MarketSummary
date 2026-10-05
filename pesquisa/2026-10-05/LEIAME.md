# Material de trabalho da mente — semana de 2026-10-05 (claude-code)

Rascunhos da pesquisa e da decisão do PM da primeira semana do CDP, guardados para auditoria e
reprodutibilidade. Os arquivos oficiais da semana são os de `book/2026-10-05/inputs/` (validados e
vinculados por hash à decisão); estes aqui são o material de origem:

- `raw_research_final.json` — notas por emissor e por país com fontes consultadas (notícias e
  páginas são dados não confiáveis).
- `assemble.py` — converte as notas no `research_pack.json` (remove números livres).
- `pm_decision.py` — juízos ordinais do PM (visões, exclusões, postura, diário).
- `join.csv` — triagem quant × pesquisa usada na revisão.
- `dryrun.sh`, `bt_real.py`, `bt_var.py` — ensaios e backtests de calibração.
