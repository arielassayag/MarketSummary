"""Extrator mínimo de texto de PDF (sem dependências) para formulários padronizados da CVM.

Cobre o que o "Calendário Anual de Eventos Corporativos" gerado pelo Empresas.NET/B3 usa:
objetos não comprimidos no corpo, fluxos ``FlateDecode``, fontes ``Type0``/``Identity-H`` com
``ToUnicode`` (``bfchar``/``bfrange``) ou ``Type1`` (WinAnsi), operadores ``Tf``, ``Tm``,
``Td``/``TD``, ``T*``, ``Tj``, ``TJ``, ``'`` e ``"``. Devolve as linhas de texto da página na ordem
de leitura (por ``y`` decrescente, depois ``x``). PDF fora desse perfil (fluxos de objetos,
criptografia, outras codificações) ⇒ :class:`PdfIlegivel` — quem chama trata como ausente.
"""

from __future__ import annotations

import re
import zlib

_OBJ_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)
_REF_RE = re.compile(rb"/(\w+)\s+(\d+)\s+0\s+R")


class PdfIlegivel(ValueError):
    """PDF fora do perfil suportado (o texto não pôde ser extraído com segurança)."""


def _objetos(data: bytes) -> dict[int, bytes]:
    objs = {int(m.group(1)): m.group(3) for m in _OBJ_RE.finditer(data)}
    if not objs:
        raise PdfIlegivel("PDF sem objetos legíveis.")
    if any(b"/ObjStm" in v[:300] for v in objs.values()) or b"/Encrypt" in data:
        raise PdfIlegivel("PDF com fluxos de objetos ou criptografia.")
    return objs


def _fluxo(obj: bytes) -> bytes:
    i = obj.find(b"stream")
    if i < 0:
        return b""
    j = i + len(b"stream")
    if obj[j:j + 2] == b"\r\n":
        j += 2
    elif obj[j:j + 1] in (b"\n", b"\r"):
        j += 1
    k = obj.rfind(b"endstream")
    raw = obj[j:k].rstrip(b"\r\n")
    if b"/FlateDecode" in obj[:i]:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            try:
                return zlib.decompressobj().decompress(raw)
            except zlib.error as exc:
                raise PdfIlegivel(f"Fluxo comprimido inválido: {exc}") from exc
    return raw


def _cmap(texto: bytes) -> dict[int, str]:
    m: dict[int, str] = {}
    s = texto.decode("latin-1")
    for bloco in re.findall(r"beginbfchar(.*?)endbfchar", s, re.S):
        for a, b in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", bloco):
            m[int(a, 16)] = bytes.fromhex(b).decode("utf-16-be", errors="replace")
    for bloco in re.findall(r"beginbfrange(.*?)endbfrange", s, re.S):
        for a, b, c in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
                                  bloco):
            ini, fim, dst = int(a, 16), int(b, 16), int(c, 16)
            for k in range(ini, fim + 1):
                m[k] = chr(dst + k - ini)
        for a, _b, arr in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", bloco):
            ini = int(a, 16)
            for k, h in enumerate(re.findall(r"<([0-9A-Fa-f]+)>", arr)):
                m[ini + k] = bytes.fromhex(h).decode("utf-16-be", errors="replace")
    return m


def _fontes(objs: dict[int, bytes], pagina: bytes) -> dict[str, tuple[int, dict[int, str]]]:
    """Nome do recurso ⇒ (bytes por código, mapa código→texto)."""
    out: dict[str, tuple[int, dict[int, str]]] = {}
    m = re.search(rb"/Font\s*<<(.*?)>>", pagina, re.S)
    if m is None:
        ref = re.search(rb"/Resources\s+(\d+)\s+0\s+R", pagina)
        if ref is None:
            return out
        m = re.search(rb"/Font\s*<<(.*?)>>", objs.get(int(ref.group(1)), b""), re.S)
        if m is None:
            return out
    for nome, num in _REF_RE.findall(m.group(1)):
        fo = objs.get(int(num), b"")
        if b"/Identity-H" in fo:
            tu = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", fo)
            cmap = _cmap(_fluxo(objs.get(int(tu.group(1)), b""))) if tu else {}
            out[nome.decode()] = (2, cmap)
        else:
            out[nome.decode()] = (1, {})
    return out


def _literal(s: bytes, i: int) -> tuple[bytes, int]:
    """String literal a partir de ``s[i] == '('``; devolve (bytes, índice após ')')."""
    out = bytearray()
    prof = 1
    i += 1
    while i < len(s) and prof > 0:
        c = s[i]
        if c == 0x5C:  # barra invertida
            i += 1
            if i >= len(s):
                break
            e = s[i]
            mapa = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
            if e in mapa:
                out.append(mapa[e])
            elif 48 <= e <= 55:
                j = i
                while j < len(s) and j < i + 3 and 48 <= s[j] <= 55:
                    j += 1
                out.append(int(s[i:j], 8) & 0xFF)
                i = j - 1
            elif e in (10, 13):
                pass
            else:
                out.append(e)
        elif c == 0x28:
            prof += 1
            out.append(c)
        elif c == 0x29:
            prof -= 1
            if prof > 0:
                out.append(c)
        else:
            out.append(c)
        i += 1
    return bytes(out), i


def _decodificar(b: bytes, fonte: tuple[int, dict[int, str]] | None) -> str:
    if fonte is None or fonte[0] == 1:
        return b.decode("cp1252", errors="replace")
    _, cmap = fonte
    chars = []
    for k in range(0, len(b) - 1, 2):
        code = (b[k] << 8) | b[k + 1]
        chars.append(cmap.get(code, ""))
    return "".join(chars)


_TOKEN = re.compile(rb"\s*(\(|<<|<[0-9A-Fa-f\s]*>|\[|\]|/[^\s/\[\]()<>]+|[-+]?\d*\.?\d+|"
                    rb"[A-Za-z'\"*]+)")


def _texto_pagina(conteudo: bytes, fontes: dict) -> list[tuple[float, float, str]]:
    itens: list[tuple[float, float, str]] = []
    pilha: list = []
    fonte = None
    x = y = 0.0
    lx = ly = 0.0
    lead = 0.0
    i = 0
    n = len(conteudo)
    while i < n:
        m = _TOKEN.match(conteudo, i)
        if m is None:
            i += 1
            continue
        tok = m.group(1)
        if tok == b"(":
            s, i = _literal(conteudo, m.start(1))
            pilha.append(("str", s))
            continue
        i = m.end()
        if tok.startswith(b"<") and tok != b"<<":
            hexs = re.sub(rb"\s", b"", tok[1:-1])
            if len(hexs) % 2:
                hexs += b"0"
            pilha.append(("str", bytes.fromhex(hexs.decode())))
        elif tok == b"[":
            pilha.append(("[", None))
        elif tok == b"]":
            arr = []
            while pilha and pilha[-1][0] != "[":
                arr.append(pilha.pop())
            if pilha:
                pilha.pop()
            pilha.append(("arr", list(reversed(arr))))
        elif tok.startswith(b"/"):
            pilha.append(("nome", tok[1:].decode("latin-1")))
        elif re.fullmatch(rb"[-+]?\d*\.?\d+", tok):
            pilha.append(("num", float(tok)))
        else:
            op = tok.decode("latin-1")
            nums = [v for t, v in pilha if t == "num"]
            if op == "BT":
                x = y = lx = ly = 0.0
            elif op == "Tf" and len(pilha) >= 2 and pilha[-2][0] == "nome":
                fonte = fontes.get(pilha[-2][1])
            elif op == "Tm" and len(nums) >= 6:
                x, y = nums[-2], nums[-1]
                lx, ly = x, y
            elif op in ("Td", "TD") and len(nums) >= 2:
                lx, ly = lx + nums[-2], ly + nums[-1]
                x, y = lx, ly
                if op == "TD":
                    lead = -nums[-1]
            elif op == "TL" and nums:
                lead = nums[-1]
            elif op == "T*":
                ly -= lead
                x, y = lx, ly
            elif op in ("Tj", "'", '"'):
                if op in ("'", '"'):
                    ly -= lead
                    x, y = lx, ly
                ss = [v for t, v in pilha if t == "str"]
                if ss:
                    itens.append((y, x, _decodificar(ss[-1], fonte)))
            elif op == "TJ":
                arr = [v for t, v in pilha if t == "arr"]
                if arr:
                    partes = []
                    for t, v in arr[-1]:
                        if t == "str":
                            partes.append(_decodificar(v, fonte))
                        elif t == "num" and v < -200:
                            partes.append(" ")
                    itens.append((y, x, "".join(partes)))
            pilha = []
    return itens


def celulas(data: bytes) -> list[tuple[int, float, float, str]]:
    """Trechos de texto ``(página, y, x, texto)`` em ordem de leitura (y decrescente, x)."""
    if not data.startswith(b"%PDF"):
        raise PdfIlegivel("Conteúdo não é PDF.")
    objs = _objetos(data)
    paginas = [k for k, v in sorted(objs.items())
               if re.search(rb"/Type\s*/Page\b", v) and b"/Contents" in v]
    if not paginas:
        raise PdfIlegivel("PDF sem páginas.")
    out: list[tuple[int, float, float, str]] = []
    for n_pg, k in enumerate(paginas):
        pg = objs[k]
        fontes = _fontes(objs, pg)
        refs = re.search(rb"/Contents\s*(\[(.*?)\]|(\d+)\s+0\s+R)", pg, re.S)
        nums = ([int(n) for n in re.findall(rb"(\d+)\s+0\s+R", refs.group(2))]
                if refs and refs.group(2) is not None
                else [int(refs.group(3))] if refs else [])
        conteudo = b"\n".join(_fluxo(objs.get(n, b"")) for n in nums)
        for y, x, txt in sorted(_texto_pagina(conteudo, fontes), key=lambda t: (-t[0], t[1])):
            if txt.strip():
                out.append((n_pg, y, x, txt))
    return out


def linhas_texto(data: bytes, tolerancia_y: float = 2.5) -> list[str]:
    """Linhas de texto de todas as páginas, em ordem de leitura."""
    saida: list[str] = []
    por_pagina: dict[int, list[tuple[float, float, str]]] = {}
    for pg, y, x, txt in celulas(data):
        por_pagina.setdefault(pg, []).append((y, x, txt))
    for pg in sorted(por_pagina):
        itens = por_pagina[pg]
        linha: list[tuple[float, str]] = []
        y_ref = None
        for y, x, txt in itens:
            if y_ref is not None and abs(y - y_ref) > tolerancia_y:
                saida.append(" ".join(t for _, t in sorted(linha)).strip())
                linha = []
            if y_ref is None or abs(y - y_ref) > tolerancia_y:
                y_ref = y
            linha.append((x, txt))
        if linha:
            saida.append(" ".join(t for _, t in sorted(linha)).strip())
    return [s for s in (re.sub(r"\s+", " ", ln) for ln in saida) if s.strip()]


__all__ = ["PdfIlegivel", "celulas", "linhas_texto"]
