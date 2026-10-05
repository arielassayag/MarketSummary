"""CDP — Cabra da Peste: fundo long/short de ações da América Latina com PM 100% autônomo.

Separação de responsabilidades (ver docs/cdp/ARQUITETURA.md e docs/cdp/METODOLOGIA.md):

- Dados reais e snapshots imutáveis com hashes (``cdp.data``).
- Analytics determinísticos: retornos em USD, liquidez e risco de short squeeze (``cdp.analytics``).
- Modelo de risco fatorial estilo Barra (``cdp.risk``) e sinais de alpha (``cdp.alpha``).
- Otimizador convexo net neutral com meta de volatilidade (``cdp.portfolio``).
- Pesquisa e decisão com IA generativa (a "mente": Claude Code ou Codex) que só produz juízos
  estruturados e auditáveis (``cdp.research``); nenhum número é calculado pelo LLM.
- Rotinas semanal (decisão autônoma sob gates determinísticos) e diária (track record encadeado
  por hash, risco, atribuição, comentário e relatório) em ``cdp.workflow``; CLI ``python -m cdp``.
"""

FUND_NAME = "CDP — Cabra da Peste"
__version__ = "0.1.0"

SIMULATED_DATA_NOTICE = "DADOS SIMULADOS"
