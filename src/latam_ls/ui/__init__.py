"""Interface Streamlit do CDP — Cabra da Peste: janela transparente para o PM autônomo.

O app só lê os artefatos produzidos pelo pipeline (livro, track record, relatórios, mandato e
base de mercado). A única ação de escrita é o KILL SWITCH de emergência, auditado na trilha.

Módulos:

- ``settings``: caminhos (variáveis ``CDP_BOOK_DIR``, ``CDP_REPORTS_DIR``, ``CDP_CONFIG``,
  ``CDP_MARKET_DIR``).
- ``fmt``: formatação pt-BR e paleta institucional.
- ``data``: leitura defensiva dos artefatos (sem Streamlit; testável).
- ``charts``: figuras Plotly.
- ``state``: cache ``st.cache_data`` por impressão digital de arquivos.
- ``components``: cabeçalho, KPIs, selos "IA"/"Calculado" e estados vazios.
- ``page_*``: as nove páginas; ``app``: navegação multipágina.
"""
