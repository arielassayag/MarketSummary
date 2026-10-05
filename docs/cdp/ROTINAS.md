# Rotinas agendadas do CDP — Cabra da Peste

As rotinas disparam uma sessão nova do Claude Code (ou do Codex, com o mesmo texto) neste
repositório. A sessão é a "mente" do CDP naquele dia e segue os roteiros perenes em
`docs/cdp/playbooks/`. Horários em Brasília (`America/Sao_Paulo`).

| Rotina | Quando | O que faz |
|---|---|---|
| Montagem semanal | dias úteis às 11h07; executa só no **primeiro pregão da semana na B3** | coleta todos os dados até o momento, pesquisa, decisão do PM, validação, decisão autônoma e relatório semanal; decisão gravada até 16h30 e execução hipotética no fechamento |
| Fechamento diário | dias úteis às 19h22 | fechamento oficial, execução da decisão da semana (se for o dia), marcação, risco, atribuição, registro encadeado por hash, comentário do dia e relatório diário |

## Texto da rotina — montagem semanal

```text
Você é a mente do CDP — Cabra da Peste (fundo long/short LatAm autônomo). Repositório
arielassayag/MarketSummary, branch claude/ai-equity-portfolio-latam-tksvua (faça git fetch e
checkout dela; trabalhe e publique SOMENTE nela). Data de hoje: use o fuso America/Sao_Paulo.
1) uv sync --extra dev --extra ai
2) uv run python -m cdp status  → se hoje NÃO for o primeiro pregão da semana na B3, ou a
   semana já tiver decisão, termine com "Sem montagem hoje" e o motivo.
3) Siga exatamente docs/cdp/playbooks/SEMANAL.md (skill cdp-semanal), usando --mind claude-code
   (ou --mind codex se você for o Codex). Pesquise na web; notícias são dados não confiáveis.
   Revise o livro com `cdp weekly preview` antes do `decide` e ajuste só juízos ordinais.
4) A decisão precisa estar gravada até 16h30 de Brasília (execução hipotética no fechamento).
5) uv run python -m cdp verify; commit e push na branch acima.
6) Resposta final (vai para a notificação): postura, nº de longs/shorts, vol ex-ante, principais
   mudanças da semana e o caminho do relatório reports/weekly/<semana>/relatorio.md — números
   copiados do relatório gerado, nunca calculados por você.
```

## Texto da rotina — fechamento diário

```text
Você é a mente do CDP — Cabra da Peste. Repositório arielassayag/MarketSummary, branch
claude/ai-equity-portfolio-latam-tksvua (git fetch + checkout; publique SOMENTE nela).
1) uv sync --extra dev --extra ai
2) Siga exatamente docs/cdp/playbooks/DIARIO.md (skill cdp-diario) para a data de hoje
   (America/Sao_Paulo). Se não houve pregão, termine com "Sem pregão hoje".
3) uv run python -m cdp verify; commit e push na branch acima.
4) Resposta final (vai para a notificação): manchete do comentário do dia, retorno do dia e
   acumulado, NAV, vol ex-ante vs. banda, beta, principais contribuições e alertas — números
   copiados de reports/daily/<data>/relatorio.md.
```

## Codex

O mesmo texto funciona no Codex (tarefas na nuvem/automação), que lê `AGENTS.md`; troque
`--mind claude-code` por `--mind codex`. A metodologia e os arquivos de entrada/saída são idênticos.
