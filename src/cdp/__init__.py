"""CDP — Cabra da Peste: fundo long/short de ações da América Latina com PM autônomo.

Ponto de entrada estável do projeto (``python -m cdp``). A implementação vive em ``latam_ls``
(dados, risco, alpha, otimizador, pesquisa com IA, rotinas semanal e diária).
"""

from latam_ls import SIMULATED_DATA_NOTICE, __version__

FUND_NAME = "CDP — Cabra da Peste"

__all__ = ["FUND_NAME", "SIMULATED_DATA_NOTICE", "__version__"]
