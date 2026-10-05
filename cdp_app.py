"""CDP — Cabra da Peste: janela de monitoramento do PM autônomo (Streamlit, multipágina).

Executar:

    uv run streamlit run cdp_app.py --server.address 127.0.0.1

Somente leitura dos artefatos do pipeline (livro, track record, relatórios, mandato e base de
mercado); a única ação de escrita é o KILL SWITCH de emergência, auditado na trilha. Caminhos
configuráveis por ``CDP_BOOK_DIR``, ``CDP_REPORTS_DIR``, ``CDP_CONFIG`` e ``CDP_MARKET_DIR``.
"""

from latam_ls.ui.app import main

main()
