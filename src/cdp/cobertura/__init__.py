"""Cobertura de ações e ETFs: modelo e preço-alvo de 12 meses para todo o universo LatAm.

Pacote do motor de research de equity (dono: workstream A). Tudo é código determinístico e
testado (a mente nunca calcula) sobre dados públicos e reproduzíveis: insumos point-in-time com
fonte e hash, custo de capital, métodos de valuation por arquétipo, cenários, rating relativo,
portões de qualidade, ponte do preço-alvo, livro imutável encadeado por hash
(``book/cobertura/``) e placar de acertos.

Contratos congelados no W0 (implementados pelo dono; ver ``DESIGN §2.3``):

- :mod:`cdp.cobertura.livro` — ``SnapshotCobertura`` e ``ultimo_snapshot(root, ate)``;
- :mod:`cdp.cobertura.fatos` — ``factbook_emissor(snap, issuer_id, md)``;
- :mod:`cdp.cobertura.sinal` — ``valuation_gap(snap)`` (z dentro de país × setor);
- :mod:`cdp.cobertura.cli` — ``cdp cobertura run|verify``.
"""
