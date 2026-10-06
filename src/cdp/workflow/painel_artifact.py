"""Checagem de publicação do painel no artifact (o que ler, se cabe no orçamento e o que publicar).

Movido de ``cdp.__main__`` (que o reexporta) para que a publicação de novos arquivos do painel
evolua sem tocar na CLI. Só lê a pasta de saída do ``cdp painel``; nunca grava.
"""

from __future__ import annotations

from pathlib import Path


def painel_artifact_check(out_dir: Path, *, page_changed: bool,
                          page_version: str | None = None) -> dict:
    """O que a mente precisa ler por inteiro antes de publicar, se isso cabe no orçamento e o que
    publicar.

    A ferramenta Artifact exige a página (``file_path``) em toda publicação: ``index.html`` (a
    casca, pequena) e ``data.json`` são lidos e publicados sempre; o estilo e o script versionados
    (``painel-<versão>.css``/``.js``) só quando a página mudou em relação à última PUBLICADA
    (``page_changed``, ver :func:`cdp.workflow.painel.mark_published`) — os já publicados ficam
    no artifact. Publicável quando ``data.json`` tem até ``DATA_MAX_BYTES`` bytes e linhas de até
    ``DATA_MAX_LINE`` caracteres e os arquivos da página até ``PAGE_MAX_BYTES``/``PAGE_MAX_LINE``.
    Devolve também ``publicar`` (``file_path`` e ``files`` prontos para a ferramenta), a URL de
    ``ARTIFACT_URL`` (``None`` se o arquivo não existe: não publique), a versão da página
    registrada como publicada (``pagina_publicada``) e a versão gerada agora (``pagina_atual``):
    antes de publicar, a skill compara a página viva do artifact com essas duas e não publica se
    ela for outra (página publicada fora das rotinas)."""
    from .painel import ASSET_RE, DATA_NAME, INDEX_NAME, URL_NAME, published_page_sha
    from .painel_publicacao import (
        DATA_MAX_BYTES,
        DATA_MAX_LINE,
        PAGE_MAX_BYTES,
        PAGE_MAX_LINE,
        max_line,
    )

    limits = {"dados_bytes": DATA_MAX_BYTES, "dados_linha": DATA_MAX_LINE,
              "pagina_bytes": PAGE_MAX_BYTES, "pagina_linha": PAGE_MAX_LINE}
    out = {"publicavel": False, "motivo": "", "arquivos_para_ler": [], "tamanho_dados": None,
           "linhas_max": None, "linhas_dados": None, "pagina_mudou": bool(page_changed),
           "pagina_publicada": published_page_sha(out_dir), "pagina_atual": page_version,
           "url": None, "publicar": None,
           "limites": limits}
    url_file = out_dir / URL_NAME
    try:
        url = url_file.read_text(encoding="utf-8").strip() if url_file.is_file() else ""
    except OSError:
        url = ""
    out["url"] = url or None
    assets = sorted(p for p in out_dir.glob("painel-*") if ASSET_RE.fullmatch(p.name))
    if page_changed and len(assets) != 2:
        out["motivo"] = (f"estilo e script da página ausentes em {out_dir.as_posix()}: rode "
                         "`cdp painel` de novo")
        return out
    files = [(out_dir / INDEX_NAME, PAGE_MAX_BYTES, PAGE_MAX_LINE)]
    files += [(a, PAGE_MAX_BYTES, PAGE_MAX_LINE) for a in assets] if page_changed else []
    files.append((out_dir / DATA_NAME, DATA_MAX_BYTES, DATA_MAX_LINE))
    problems, longest = [], 0
    for path, max_bytes, max_len in files:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            out["motivo"] = f"{path.name} ilegível: {exc.__class__.__name__}"
            return out
        text = raw.decode("utf-8", errors="replace")
        line = max_line(text)
        longest = max(longest, line)
        if path.name == DATA_NAME:
            out["tamanho_dados"] = len(raw)
            out["linhas_dados"] = text.count("\n")
        if len(raw) > max_bytes:
            problems.append(f"{path.name} com {len(raw)} bytes (limite {max_bytes})")
        if line > max_len:
            problems.append(f"{path.name} com linha de {line} caracteres (limite {max_len})")
        out["arquivos_para_ler"].append(path.as_posix())
    out["linhas_max"] = longest
    out["publicavel"] = not problems
    out["motivo"] = ("grande demais para a leitura integral exigida antes de publicar: "
                     + "; ".join(problems)) if problems else "ok"
    if not problems:
        out["publicar"] = {"file_path": (out_dir / INDEX_NAME).as_posix(),
                           "files": {p.name: p.as_posix() for p, _, _ in files[1:]}}
    return out


__all__ = ["painel_artifact_check"]
