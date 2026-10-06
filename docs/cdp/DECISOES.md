# Registro de decisões do CDP

Decisões já tomadas, para qualquer agente ou pessoa que chegue ao projeto (em qualquer harness).
Formato: data · contexto → decisão → consequências. Acrescente no fim; não reescreva entradas
antigas (uma decisão revista ganha uma entrada nova que cita a anterior).

## 2026-10-06 · Só dados públicos

Contexto: reprodutibilidade por qualquer pessoa e repositório público. → Decisão: modelos,
pesquisa e notas usam somente fontes públicas (CVM, SEC EDGAR, B3, bancos centrais e institutos
de estatística, RI das empresas, emissores de ETF, Damodaran, Yahoo Finance como consenso
público rotulado, notícias públicas); evidência é URL pública. → Consequências: nenhuma base paga
nem conector proprietário em código, skills, configuração ou documentação; insumos arquivados em
`data/publico/` com fonte, datas e SHA-256.

## 2026-10-06 · Carteira inaugural na sexta, 2026-10-09

Contexto: metodologia completa antes de montar a carteira. → Decisão: `fund.inception_date =
2026-10-09`; montagem no último pregão da semana na NYSE, execução no leilão de fechamento; a
carteira do ensaio anterior não aparece em nenhum texto para investidores. → Consequências: a
rotina diária abre o livro uma única vez (`cdp reinicio --executar`) antes da data de início; o
portal recusa montar enquanto isso estiver pendente.

## 2026-10-06 · Escritor único e executor designado

Contexto: o livro é uma trilha encadeada por hash; dois escritores corrompem a história. →
Decisão: só o executor de `configs/cdp/executor.yaml` grava `book/`, `data/`, `reports/`,
`artifacts/`; a identidade de cada ambiente é explícita (`CDP_EXECUTOR` ou `.cdp/local.yaml`);
publicação só por `cdp publicar` (escopo de caminhos, verify, push em `main`, nunca force). →
Consequências: sessões de desenvolvimento nunca gravam o livro; troca de executor é decisão
humana, por commit revisável (`docs/cdp/AUTOMACAO.md`).

## 2026-10-06 · Operação agnóstica ao harness

Contexto: o projeto precisa rodar em Claude Code, Codex, Gemini CLI, Antigravity ou outro, e
qualquer um deve continuar o trabalho de onde parou. → Decisão: `AGENTS.md` é o manual canônico;
roteiros neutros em `docs/cdp/playbooks/`; agenda como dados em `configs/cdp/rotinas.yaml`;
skills abertas (Agent Skills) geradas em `.agents/skills/`; `CLAUDE.md`, `GEMINI.md` e o plugin
são adaptadores finos; estado por código (`cdp estado`). → Consequências: nada essencial vive só
na memória de um harness; mudanças de agenda passam por `cdp rotinas verificar` e
`cdp skills sincronizar`.

## 2026-10-06 · Nuvem: rotinas do Claude Code como executor principal

Contexto: automação 100% em nuvem usando a capacidade do plano. → Decisão: uma rotina da nuvem
do Claude Code por tarefa (prompts gerados por `cdp rotinas exportar --alvo claude-routines`),
ambiente sem segredos, gate determinístico antes de qualquer uso de modelo, trava distribuída no
ramo `cdp-trava` (máquinas separadas). Alternativas documentadas: GitHub Actions com qualquer
CLI, agendadores do sistema, app desktop. → Consequências: troca de executor com ensaio prévio
(`docs/cdp/AUTOMACAO.md`).

## 2026-10-06 · Portal público no GitHub Pages

Contexto: portal gratuito, estável, sem conta extra e replicável por fork. → Decisão: GitHub
Pages implantado pelo GitHub Actions, montado do repositório por `cdp site construir` (sem cortes
de tamanho; dados abertos com SHA-256; manifesto ligado à versão do repositório). O artifact do
claude.ai vira espelho privado opcional. → Consequências: o CI nunca grava no repositório; o
portal fica a até alguns minutos do último push (`docs/cdp/SITE.md`).

## Pendentes de decisão humana

- Licença do repositório (recomendado: Apache-2.0 para o código e CC BY 4.0 para textos e dados
  derivados; dados de terceiros sob os termos das fontes). Sem licença, a replicação não é
  juridicamente livre.
- Data da troca do executor para a nuvem (recomendado: depois do ensaio, no domingo seguinte à
  carteira inaugural).
- Portal indexado por buscadores (padrão: sim, com aviso legal fixo).
