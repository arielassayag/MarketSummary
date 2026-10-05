"""LatAm L/S — gestor de carteira long/short de ações latino-americanas assistido por IA.

Separação de responsabilidades (ver docs/latam_ls/ARQUITETURA.md):

- Dados reais e snapshots imutáveis com hashes (``latam_ls.data``).
- Analytics determinísticos: retornos em USD, liquidez e risco de short squeeze (``latam_ls.analytics``).
- Modelo de risco fatorial estilo Barra (``latam_ls.risk``) e sinais de alpha (``latam_ls.alpha``).
- Otimizador convexo net neutral com meta de volatilidade (``latam_ls.portfolio``).
- Camada de pesquisa com IA generativa que só produz visões qualitativas
  estruturadas e auditáveis (``latam_ls.research``); nenhum número é calculado pelo LLM.
- Fluxo semanal com aprovação humana vinculada a hashes (``latam_ls.workflow``).
"""

__version__ = "0.1.0"

SIMULATED_DATA_NOTICE = "DADOS SIMULADOS"
