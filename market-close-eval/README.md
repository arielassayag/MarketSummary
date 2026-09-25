# Market Close Eval — AI Notes

Avaliação de **duas versões de prompt** (V1 baseline x V2 com disciplina factual)
para um agente que escreve o **comentário de fechamento do mercado brasileiro**,
executado em **vários modelos via OpenRouter**, com avaliação em 3 camadas:

1. **Verificações determinísticas por código** (schema, palavras, IDs, valores,
   unidades, direções, retorno ≠ contribuição, recall de fatos críticos);
2. **LLM-as-a-judge** absoluto e anonimizado (rubrica 0–4 em 5 dimensões, com
   *hard fails* que limitam a nota a 49);
3. **Auditoria humana** em amostra estratificada (kappa de Cohen, MAE, Spearman).

Comparação secundária **pareada V1 x V2** com judge cego nas duas ordens (A/B).
Sem LangChain/LlamaIndex: SDK oficial da OpenAI apontado ao OpenRouter, cache
SQLite (biblioteca padrão) para **nunca pagar duas vezes pela mesma chamada**.

---

## Como o eval funciona (visão rápida)

```
casos (20 pregões congelados, dev/holdout)
        │  pacote: data + fatos + unidades + fontes (SEM referência/importância)
        ▼
[modelo candidato] + Prompt V1 ou V2  →  JSON estrito (schema único)
        │
        ├─→ verificações por código (17 checagens)  → hard_fail? nota ≤ 49
        ├─→ judge absoluto (anonimizado, temperature 0) → raw_score 0–100
        └─→ judge pareado V1 x V2 (2 ordens, cego)      → vitória/empate/instável
        ▼
tabelas + gráficos + report.html + article_results.md + amostra de auditoria humana
```

Regras de ouro do projeto:

- **Nunca** fabricar dados/fontes; todo fato tem id, fonte, URL, horário e tipo de medida;
- **Retorno nunca é contribuição** (só existe "contribuição" com `contribution_bps`, e o
  dataset atual não tem nenhum — a palavra não deve aparecer em comentário correto);
- Modelos **navegam** nem usam conhecimento externo: recebem exatamente o mesmo pacote;
- O **holdout não é usado para ajustar o V2** e só abre com `--confirm-holdout`;
- A comparação V1 x V2 muda **somente o prompt** (modelos, parâmetros, dados e schema idênticos);
- Artefatos **sintéticos** (smoke) são sempre marcados e nunca entram em publicação.

---

## Instalação (macOS / Linux / Windows)

Requisitos: Python **3.12+** (desenvolvido e testado em 3.13).

```bash
cd market-close-eval
python3 -m venv .venv
# Windows: py -m venv .venv  e  .venv\Scripts\activate
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # e preencha OPENROUTER_API_KEY
```

Ou simplesmente `make install`.

### Configurar a chave

Edite `.env` (nunca comite este arquivo):

```
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_SITE_URL=https://seusite.com        # opcional (header HTTP-Referer)
OPENROUTER_APP_NAME=AI Notes Market Close Eval # opcional (header X-OpenRouter-Title)
```

---

## Sequência de uso

```bash
python -m market_eval validate-data          # valida o dataset congelado
python -m market_eval list-models            # consulta o catálogo público do OpenRouter
python -m market_eval lock-models            # congela 4 candidatos + judge em configs/models.lock.yaml
python -m market_eval dry-run                # plano completo, ZERO chamadas pagas
python -m market_eval smoke                  # pipeline completo SINTÉTICO (offline, sem custo)

# ---- a partir daqui há custo real (cache evita cobrança dupla) ----
python -m market_eval run --split dev --prompt all --run-id aInotes
python -m market_eval grade --run-id aInotes
python -m market_eval pairwise --run-id aInotes
# holdout: só depois de congelar o Prompt V2 (não ajuste nada olhando o dev!)
python -m market_eval run --split holdout --prompt all --run-id aInotes --confirm-holdout
python -m market_eval grade --run-id aInotes --confirm-holdout
python -m market_eval report --run-id aInotes --confirm-holdout

# auditoria humana
python -m market_eval export-human-audit --run-id aInotes
# ... preencha human_audit_sample.csv seguindo human_audit_instructions.md ...
python -m market_eval import-human-audit outputs/aInotes/human_audit_sample.csv
```

`make check` roda `pytest`, `ruff check .` e `mypy src`.

---

## Interpretando as métricas

| Métrica | Significado |
|---|---|
| `hard_pass_rate` | % de saídas **sem** erro grave (fato inventado, sinal/valor/unidade errado em fato crítico, evidence_id inexistente, retorno como contribuição, causalidade sem suporte, contradição central). **Métrica primária de segurança.** |
| `final_score` | `raw_score` (30·fact/4 + 25·mat/4 + 20·causal/4 + 15·cov/4 + 10·clarity/4); com hard_fail, limitado a **49**. |
| `critical_fact_recall` / `must_mention_recall` | cobertura dos fatos que a referência exige. |
| `numeric_accuracy` | acerto na reprodução de valores do pacote (tolerâncias pequenas por tipo; troca de sinal sempre falha). |
| `delta_final_score` (prompt_delta.csv) | V2−V1 **pareado por caso**, IC95% por bootstrap (2000 reamostragens, seed fixa). |
| pairwise | `v2_win`/`v1_win` exigem consistência nas duas ordens; divergência = `unstable`. |

Dev e holdout são **sempre reportados separadamente**.

---

## Evitando custos duplicados

- Toda chamada (geração, judge absoluto, pairwise) tem uma **chave de cache** que inclui
  caso, split, modelo, prompt + hashes, repetição, seeds e parâmetros — reexecutar o mesmo
  comando **não gera nova cobrança**;
- `--force` e `--no-cache` existem para re-gerar de propósito e **emitem alerta de custo**;
- `--resume` executa apenas tarefas sem registro concluído;
- interrupções: apenas rode o mesmo comando de novo (cache + checkpoint em
  `raw_generations.jsonl`).

---

## Dataset e revisão humana

- 20 pregões reais da B3 (jan/2025–jul/2026), 5 regimes × 4 casos, split estratificado com
  seed 42 **antes** de qualquer execução; 2 showcases pré-marcados;
- Construção reproduzível: `scripts/build_dataset.py` (fontes brutas em `data/raw`);
- **Todos os casos estão em `review.status=draft`**: valide cada fato de
  `data/human_review_queue.csv` contra as fontes (B3/BCB/imprensa) antes de publicar;
- Limitações conhecidas registradas nos casos e em `caveats.md`: índice via agregador
  (Yahoo ^BVSP — a série SGS do BCB para o Ibovespa parou em 2019), PTAX ~13h vs dólar à
  vista, sem curva de juros em bps e sem contribuições em bps neste dataset.

## Limitações e avisos

- Modelos e **preços mudam** no OpenRouter todos os dias; `models.lock.yaml` congela IDs,
  preços e o snapshot do catálogo com data;
- `temperature=0` **não garante** determinismo entre provedores — por isso 2 repetições;
- O judge automático não é validado até a auditoria humana (kappa/MAE/Spearman);
- Conclusões valem **só** para esta tarefa, estes 20 casos, estes 2 prompts e estes modelos;
- Sem `pyarrow` instalado, `all_results.parquet` é pulado (CSV segue disponível);
- Dependência opcional justificada: `pyarrow` (parquet) e stubs de tipo em `[dev]`
  (`pandas-stubs`, `types-PyYAML`).
