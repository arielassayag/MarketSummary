# RUN ME — sequência mínima

> Contexto desta entrega: projeto implementado, dataset congelado (20 pregões),
> **chave de API configurada em `.env`** e experimento completo executado.
> Os comandos abaixo reproduzem tudo do zero (ou retomam de onde parou).

```bash
cd market-close-eval
source .venv/bin/activate          # ou: make install (cria o venv)

# 0) qualidade (sem custo)
make check                          # pytest + ruff + mypy
python -m market_eval validate-data
python -m market_eval dry-run

# 1) congelar modelos (consulta catálogo público; regenere se trocar de dia)
python -m market_eval lock-models

# 2) EXPERIMENTO (há custo; o cache evita cobrança dupla em reexecuções)
python -m market_eval run --split dev --prompt all --run-id aInotes
python -m market_eval grade --run-id aInotes
python -m market_eval pairwise --run-id aInotes

# 3) HOLDOUT — exige flag explícita; NÃO ajuste o V2 depois de ver o dev
python -m market_eval run --split holdout --prompt all --run-id aInotes --confirm-holdout
python -m market_eval grade --run-id aInotes --confirm-holdout

# 4) RELATÓRIOS
python -m market_eval report --run-id aInotes --confirm-holdout
#   -> outputs/aInotes/article_results.md   (texto pronto p/ o AI Notes)
#   -> outputs/aInotes/report.html          (abre offline, gráficos embutidos)
#   -> outputs/aInotes/charts/*.png

# 5) AUDITORIA HUMANA (valida o judge; obrigatória antes de publicar)
python -m market_eval export-human-audit --run-id aInotes --confirm-holdout
#   preencha outputs/aInotes/human_audit_sample.csv (colunas human_*)
python -m market_eval import-human-audit outputs/aInotes/human_audit_sample.csv
```

Status atual desta entrega (27/08/2026) — **EXPERIMENTO COMPLETO**:

- Dev 224/224 + holdout 96/96 gerações concluídas e em cache;
- **320/320 outputs julgados** (judge único: `moonshotai/kimi-k2.6`) + 160 pares pareados;
- Relatórios gerados em `outputs/aInotes/` (article_results.md, report.html, 7 gráficos,
  tabelas) e amostra de auditoria humana exportada (40 outputs anonimizados);
- Gasto total da chave: US$ 25,29 (inclui ~US$ 5 de tentativas descartadas na calibragem);
- Pendências **humanas** (não há mais custo de API): (1) validar os 144 fatos de
  `data/human_review_queue.csv` e marcar casos como `reviewed`
  (`python -m market_eval build-manifest` depois de editar); (2) preencher
  `outputs/aInotes/human_audit_sample.csv` e importar:
  `python -m market_eval import-human-audit outputs/aInotes/human_audit_sample.csv`.
  Enquanto isso, os artefatos seguem marcados **RASCUNHO — NÃO PUBLICAR**.
