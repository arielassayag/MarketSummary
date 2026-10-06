"""Checagem de publicação do painel no artifact (o que ler, se cabe no orçamento e o que publicar).

O portal principal é o site público (``cdp site construir``); o artifact é um espelho privado
opcional, com o orçamento de leitura integral de quem publica. Movido de ``cdp.__main__`` (que o
reexporta) para que a publicação de novos arquivos do painel evolua sem tocar na CLI. Só lê a
pasta de saída do ``cdp painel``; nunca grava.

Orçamento de leitura (:data:`ORCAMENTO_LEITURA`): tudo o que vai ao espelho numa publicação é lido
por inteiro antes. A parte fixa (casca, ``data.json`` e, quando a página muda, estilo, script e
módulos) precisa caber; os dados da cobertura que mudaram (``cobertura*.json``) só entram quando
cabem junto com ela — senão ficam de fora inteiros (o espelho mantém a última cobertura
publicada, coerente, e o portal público traz a atual) e o marcador ``COBERTURA_PUBLICADA.json``
não registra nada (:func:`plano_cobertura`, usado também por
:func:`cdp.workflow.painel.mark_published`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: Leitura integral máxima numa publicação do espelho (bytes UTF-8 de todos os arquivos lidos).
ORCAMENTO_LEITURA = 1_000_000


def _parte_fixa(out_dir: Path, page_changed: bool) -> list[tuple[Path, int, int]]:
    """Arquivos lidos e publicados sempre (casca e dados) e, com a página nova, estilo, script e
    módulos versionados — com o limite de bytes e de linha de cada um."""
    from .painel import ASSET_RE, DATA_NAME, INDEX_NAME
    from .painel_publicacao import DATA_MAX_BYTES, DATA_MAX_LINE, PAGE_MAX_BYTES, PAGE_MAX_LINE

    assets = sorted(p for p in out_dir.glob("painel-*") if ASSET_RE.fullmatch(p.name))
    files = [(out_dir / INDEX_NAME, PAGE_MAX_BYTES, PAGE_MAX_LINE)]
    files += [(a, PAGE_MAX_BYTES, PAGE_MAX_LINE) for a in assets] if page_changed else []
    files.append((out_dir / DATA_NAME, DATA_MAX_BYTES, DATA_MAX_LINE))
    return files


def _tamanho(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def plano_cobertura(out_dir: Path | str, *, page_changed: bool,
                    orcamento: int = ORCAMENTO_LEITURA) -> dict[str, Any]:
    """Se os dados da cobertura vão nesta publicação do espelho.

    Mudaram (``arquivos``) os ``cobertura*.json`` da pasta cujo SHA-256 difere do registrado em
    ``COBERTURA_PUBLICADA.json``; ``removidos``, os registrados que saíram da pasta. Entram
    (``incluida``) só quando há mudança, cada arquivo cabe no orçamento por arquivo do
    ``data.json`` e o total — parte fixa da publicação mais os que mudaram — cabe em
    ``orcamento``. Senão nada da cobertura vai (nunca um conjunto parcial)."""
    from .painel import cobertura_local, cobertura_publicada
    from .painel_publicacao import DATA_MAX_BYTES, DATA_MAX_LINE, max_line

    out = Path(out_dir)
    local, publicada = cobertura_local(out), cobertura_publicada(out)
    mudaram = [n for n in sorted(local) if local[n] != publicada.get(n)]
    removidos = sorted(n for n in publicada if n not in local)
    fixa = sum(_tamanho(p) or 0 for p, _, _ in _parte_fixa(out, page_changed))
    total, problemas = 0, []
    for n in mudaram:
        try:
            raw = (out / n).read_bytes()
        except OSError as exc:
            problemas.append(f"{n} ilegível ({exc.__class__.__name__})")
            continue
        total += len(raw)
        if len(raw) > DATA_MAX_BYTES:
            problemas.append(f"{n} com {len(raw)} bytes (limite {DATA_MAX_BYTES})")
        elif max_line(raw.decode("utf-8", errors="replace")) > DATA_MAX_LINE:
            problemas.append(f"{n} com linha acima de {DATA_MAX_LINE} caracteres")
    mudou = bool(mudaram or removidos)
    if not mudou:
        motivo = "cobertura sem mudanças desde a última publicação no espelho"
    elif problemas:
        motivo = "cobertura fora do orçamento por arquivo: " + "; ".join(problemas[:5])
    elif fixa + total > orcamento:
        motivo = (f"a cobertura que mudou ({len(mudaram)} arquivo(s), {total} bytes) não cabe na "
                  f"leitura integral do espelho ({fixa} bytes do restante da publicação; "
                  f"orçamento de {orcamento} bytes): fica só no portal público, e o espelho "
                  "mantém a última cobertura publicada")
    else:
        motivo = "ok"
    incluida = mudou and motivo == "ok"
    return {"incluida": incluida, "mudou": mudou, "arquivos": mudaram, "removidos": removidos,
            "bytes": total, "bytes_fixos": fixa, "orcamento": orcamento, "motivo": motivo}


def painel_artifact_check(out_dir: Path, *, page_changed: bool,
                          page_version: str | None = None,
                          orcamento: int = ORCAMENTO_LEITURA) -> dict:
    """O que a mente precisa ler por inteiro antes de publicar, se isso cabe no orçamento e o que
    publicar.

    A ferramenta Artifact exige a página (``file_path``) em toda publicação: ``index.html`` (a
    casca, pequena) e ``data.json`` são lidos e publicados sempre; o estilo, o script e os módulos
    versionados (``painel-<versão>.css``/``.js`` e ``painel-<versão>-<nome>.js``) só quando a
    página mudou em relação à última PUBLICADA (``page_changed``, ver
    :func:`cdp.workflow.painel.mark_published`) — os já publicados ficam no artifact. Publicável
    quando ``data.json`` tem até ``DATA_MAX_BYTES`` bytes e linhas de até ``DATA_MAX_LINE``
    caracteres, os arquivos da página até ``PAGE_MAX_BYTES``/``PAGE_MAX_LINE`` e o total lido
    até ``orcamento`` (:data:`ORCAMENTO_LEITURA`).

    Dados da cobertura (``cobertura*.json``): ver :func:`plano_cobertura` — entram em
    ``arquivos_para_ler`` e em ``publicar.files`` (os que saíram da pasta como ``null``) só
    quando cabem inteiros; ``cobertura_incluida``, ``cobertura_motivo``, ``cobertura_arquivos``
    (os que vão), ``cobertura_pendentes`` (os que mudaram e ficaram de fora) e
    ``cobertura_removidos`` resumem. Devolve também ``bytes_para_ler``, ``publicar``
    (``file_path`` e ``files`` prontos para a ferramenta), a URL de ``ARTIFACT_URL`` (``None`` se
    o arquivo não existe: não publique), a versão da página registrada como publicada
    (``pagina_publicada``) e a versão gerada agora (``pagina_atual``): antes de publicar, a skill
    compara a página viva do artifact com essas duas e não publica se ela for outra (página
    publicada fora das rotinas)."""
    from .painel import ASSET_RE, DATA_NAME, INDEX_NAME, URL_NAME, modulos, published_page_sha
    from .painel_publicacao import (
        DATA_MAX_BYTES,
        DATA_MAX_LINE,
        PAGE_MAX_BYTES,
        PAGE_MAX_LINE,
        max_line,
    )

    out_dir = Path(out_dir)
    limits = {"dados_bytes": DATA_MAX_BYTES, "dados_linha": DATA_MAX_LINE,
              "pagina_bytes": PAGE_MAX_BYTES, "pagina_linha": PAGE_MAX_LINE,
              "leitura_total": orcamento}
    out: dict[str, Any] = {
        "publicavel": False, "motivo": "", "arquivos_para_ler": [], "bytes_para_ler": 0,
        "tamanho_dados": None, "linhas_max": None, "linhas_dados": None,
        "pagina_mudou": bool(page_changed), "pagina_publicada": published_page_sha(out_dir),
        "pagina_atual": page_version, "url": None, "publicar": None,
        "cobertura_mudou": False, "cobertura_incluida": False, "cobertura_motivo": "",
        "cobertura_arquivos": [], "cobertura_pendentes": [], "cobertura_removidos": [],
        "limites": limits}
    url_file = out_dir / URL_NAME
    try:
        url = url_file.read_text(encoding="utf-8").strip() if url_file.is_file() else ""
    except OSError:
        url = ""
    out["url"] = url or None
    assets = sorted(p for p in out_dir.glob("painel-*") if ASSET_RE.fullmatch(p.name))
    esperados = 2 + len(modulos())
    if page_changed and len(assets) != esperados:
        out["motivo"] = (f"estilo, script e módulos da página ausentes em {out_dir.as_posix()} "
                         f"({len(assets)} de {esperados}): rode `cdp painel` de novo")
        return out
    plano = plano_cobertura(out_dir, page_changed=page_changed, orcamento=orcamento)
    vai = plano["incluida"]
    out.update({"cobertura_mudou": plano["mudou"], "cobertura_incluida": vai,
                "cobertura_motivo": plano["motivo"],
                "cobertura_arquivos": plano["arquivos"] if vai else [],
                "cobertura_pendentes": [] if vai else plano["arquivos"],
                "cobertura_removidos": plano["removidos"] if vai else []})
    files = _parte_fixa(out_dir, page_changed)
    if vai:
        files += [(out_dir / n, DATA_MAX_BYTES, DATA_MAX_LINE) for n in plano["arquivos"]]
    problems, longest, total = [], 0, 0
    for path, max_bytes, max_len in files:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            out["motivo"] = f"{path.name} ilegível: {exc.__class__.__name__}"
            return out
        text = raw.decode("utf-8", errors="replace")
        line = max_line(text)
        longest = max(longest, line)
        total += len(raw)
        if path.name == DATA_NAME:  # os da cobertura têm o mesmo orçamento, sem contagem
            out["tamanho_dados"] = len(raw)
            out["linhas_dados"] = text.count("\n")
        if len(raw) > max_bytes:
            problems.append(f"{path.name} com {len(raw)} bytes (limite {max_bytes})")
        if line > max_len:
            problems.append(f"{path.name} com linha de {line} caracteres (limite {max_len})")
        out["arquivos_para_ler"].append(path.as_posix())
    if total > orcamento:
        problems.append(f"{total} bytes a ler no total (limite {orcamento})")
    out["linhas_max"] = longest
    out["bytes_para_ler"] = total
    out["publicavel"] = not problems
    out["motivo"] = ("grande demais para a leitura integral exigida antes de publicar: "
                     + "; ".join(problems)) if problems else "ok"
    if not problems:
        publicar: dict[str, str | None] = {p.name: p.as_posix() for p, _, _ in files[1:]}
        if vai:
            publicar.update({n: None for n in plano["removidos"]})
        out["publicar"] = {"file_path": (out_dir / INDEX_NAME).as_posix(), "files": publicar}
    return out


__all__ = ["ORCAMENTO_LEITURA", "painel_artifact_check", "plano_cobertura"]
