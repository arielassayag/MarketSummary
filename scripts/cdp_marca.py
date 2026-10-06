"""Marca do CDP no portal: máscaras do logo e o bloco CSS do template do painel.

A marca original (xilogravura: "CDP" em tipos de madeira gastos, a cabra nascendo do D, o sol
listrado com mandacaru e chapada dentro do C, "ASSET MANAGEMENT" em capitulares espaçadas e a
régua com a estrela de 8 pontas) fica em ``docs/cdp/marca/cdp-logo.png`` (RGBA, fundo
transparente). O portal não usa a imagem colorida: pinta a marca com máscaras alfa e os tokens
do tema (``--tinta`` e ``--sol``) — tinta sobre papel no claro, tinta de osso sobre carvão no
escuro, o sol queimado nos dois. Guia completo: ``docs/cdp/marca/IDENTIDADE.md``.

Etapas (todas reproduzíveis a partir de ``cdp-logo.png``):

1. **Máscaras** (``--mascaras``; precisa do Pillow com WebP, declarado no extra ``dev``):

   - separa cada pixel em tinta × sol pela cor (o sol é laranja saturado; a tinta, marrom quase
     preto) e mantém a cobertura do alfa original, sem o halo quase invisível (alfa ≤ 8/255) que
     a imagem traz ao redor da marca;
   - recorta a marca com folga de 8 px e reduz para 960 px de largura:
     ``marca_tinta.webp`` (letras, cabra, mandacaru, chapada, ASSET MANAGEMENT) e
     ``marca_sol.webp`` (o sol listrado e a estrela da régua);
   - recorta a cabeça da cabra (chifre inteiro, olho e barba) direto da imagem original e apaga
     a barra superior do D que cruza o pescoço: ``marca_cabra.webp``, o emblema da barra de abas.

2. **Bloco CSS** (só biblioteca padrão): lê as três máscaras gravadas e escreve os data URIs
   base64 em linhas de até 1.800 caracteres (continuação de string do CSS: barra invertida no
   fim da linha) — o estilo publicado aceita linhas de até 2.000 caracteres. O bloco também
   traz as proporções da marca completa e do recorte sem "ASSET MANAGEMENT" (celular).

3. **Template** (``--template``, ou junto com ``--mascaras``): troca o bloco entre os marcadores
   ``>>> marca`` e ``<<< marca`` no ``<style>`` de ``src/cdp/workflow/painel_template.html``.

4. **Ornamentos da camada "Chapada"** (``--ornamentos``; só biblioteca padrão): onze máscaras SVG
   monocromáticas — curva de nível e pincelada de sol do título, olho e lances das curvas de
   nível entre seções, fio riscado à mão, goivas da aba ativa, goiva vertical, recorte, fio e
   pesponto da sela. Seis saem de um gerador com sementes fixas; cinco são desenhos fixos. A
   opção regrava o valor de cada token no ``:root`` da camada; ``--check`` confere os dois blocos.

Só ``--mascaras`` regrava as máscaras de ``docs/cdp/marca/``, e sempre junto com o bloco no
template (o teste confere o template byte a byte contra elas); ``--template`` grava só o bloco.
Sem essas opções o script só lê as máscaras gravadas: imprime o bloco, confere ou faz a prévia.

Uso::

    uv run --extra dev python scripts/cdp_marca.py                         # imprime o bloco CSS
    uv run --extra dev python scripts/cdp_marca.py --check                 # o template está em dia?
    uv run --extra dev python scripts/cdp_marca.py --previa DIR            # PNG claro/escuro p/ revisão
    uv run --extra dev python scripts/cdp_marca.py --template              # bloco → template
    uv run --extra dev python scripts/cdp_marca.py --ornamentos            # ornamentos → template
    uv run --extra dev python scripts/cdp_marca.py --mascaras              # logo → máscaras → template

Mudar o template muda a versão da página (SHA-256): a próxima rotina republica a casca, o
estilo e o script do painel.
"""

from __future__ import annotations

import argparse
import base64
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARCA = ROOT / "docs" / "cdp" / "marca"
LOGO = MARCA / "cdp-logo.png"
TINTA = MARCA / "marca_tinta.webp"
SOL = MARCA / "marca_sol.webp"
CABRA = MARCA / "marca_cabra.webp"
TEMPLATE = ROOT / "src" / "cdp" / "workflow" / "painel_template.html"

INICIO = "/* >>> marca: gerado por scripts/cdp_marca.py a partir de docs/cdp/marca/ (não editar) */"
FIM = "/* <<< marca */"

LARGURA = 960            # largura das máscaras da marca completa (3x a 320 px)
FOLGA = 8                # px de folga em volta da marca, na imagem original
ALFA_PISO = 8            # alfa (0–255) abaixo do qual o pixel é halo, não tinta
SOL_CROMA = (40, 110)    # R − B: até 40 é tinta (marrom), a partir de 110 é sol (laranja)
QUALIDADE_ALFA = 60      # WebP com perda no alfa: sem perda visível a 2x (40 KB na tinta)
LINHA = 1_800            # caracteres por linha do base64 no CSS (limite do estilo: 2.000)

# Cabeça da cabra, em pixels da imagem original (1536×1024): do bico do chifre ao queixo, e o
# polígono da barra superior do D que atravessa o pescoço (apagada no emblema).
CABRA_CAIXA = (688, 142, 1051, 438)
CABRA_BARRA = [(684, 282), (831, 294), (839, 328), (829, 375), (684, 381)]
CABRA_LARGURA = 120      # px do emblema (exibido com ~32 px de altura: 3x)


# ------------------------------------------------------------------------------- máscaras
def _canais(logo: Path):
    """Cobertura da tinta e do sol (0–1, ``numpy``) na resolução da imagem original."""
    import numpy as np
    from PIL import Image

    rgba = np.asarray(Image.open(logo).convert("RGBA"), dtype=np.float64)
    alfa = np.clip((rgba[..., 3] - ALFA_PISO) / (255.0 - ALFA_PISO), 0.0, 1.0)
    croma = rgba[..., 0] - rgba[..., 2]
    sol = np.clip((croma - SOL_CROMA[0]) / (SOL_CROMA[1] - SOL_CROMA[0]), 0.0, 1.0)
    return alfa * (1.0 - sol), alfa * sol, rgba[..., 3]


def _webp(cobertura, tamanho: tuple[int, int], caixa, *, qualidade_alfa: int,
          apagar: list[tuple[int, int]] | None = None) -> bytes:
    """Máscara só-alfa (RGB preto) em WebP, recortada em ``caixa`` e reduzida a ``tamanho``."""
    import numpy as np
    from PIL import Image, ImageDraw

    alfa = Image.fromarray(np.rint(cobertura * 255.0).astype(np.uint8), "L")
    if apagar:
        ImageDraw.Draw(alfa).polygon(apagar, fill=0)
    alfa = alfa.resize(tamanho, Image.LANCZOS, box=caixa)
    img = Image.new("RGBA", tamanho, (0, 0, 0, 0))
    img.putalpha(alfa)
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=60, alpha_quality=qualidade_alfa, method=6)
    return buf.getvalue()


def gerar_mascaras(logo: Path = LOGO) -> dict[str, object]:
    """Grava as três máscaras em ``docs/cdp/marca/`` e devolve a geometria da marca."""
    import numpy as np

    tinta, sol, alfa_bruto = _canais(logo)
    ys, xs = np.nonzero(alfa_bruto > ALFA_PISO // 2)
    if not len(xs):
        raise SystemExit(f"{logo}: imagem sem marca (alfa vazio)")
    caixa = (max(int(xs.min()) - FOLGA, 0), max(int(ys.min()) - FOLGA, 0),
             min(int(xs.max()) + 1 + FOLGA, alfa_bruto.shape[1]),
             min(int(ys.max()) + 1 + FOLGA, alfa_bruto.shape[0]))
    largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    tamanho = (LARGURA, round(LARGURA * altura / largura))

    TINTA.write_bytes(_webp(tinta, tamanho, caixa, qualidade_alfa=QUALIDADE_ALFA))
    SOL.write_bytes(_webp(sol, tamanho, caixa, qualidade_alfa=QUALIDADE_ALFA))
    cx = CABRA_CAIXA
    cabra = (CABRA_LARGURA, round(CABRA_LARGURA * (cx[3] - cx[1]) / (cx[2] - cx[0])))
    CABRA.write_bytes(_webp(tinta, cabra, cx, qualidade_alfa=85, apagar=CABRA_BARRA))

    # recorte do celular: a marca sem "ASSET MANAGEMENT" termina no primeiro vão horizontal sem
    # tinta abaixo das letras (entre o chão da chapada e a linha de capitulares)
    linhas = (tinta + sol)[caixa[1]:caixa[3], caixa[0]:caixa[2]].max(axis=1) > 0.02
    corte, ini = None, None
    for i in range(len(linhas) // 2, len(linhas)):
        if not linhas[i] and ini is None:
            ini = i
        elif linhas[i] and ini is not None:
            if i - ini >= 12:
                corte = (ini + i) / 2  # meio do vão, em pixels da imagem original
                break
            ini = None
    if corte is None:
        raise SystemExit("não achei o vão entre as letras e ASSET MANAGEMENT")
    topo = round(tamanho[0] * corte / largura)
    return {"caixa": caixa, "tamanho": tamanho, "topo": topo, "cabra": cabra}


# ------------------------------------------------------------------------------- bloco CSS
def _data_uri(raw: bytes, mime: str = "image/webp") -> str:
    b64 = base64.b64encode(raw).decode("ascii")
    partes = [b64[i:i + LINHA] for i in range(0, len(b64), LINHA)]
    return f'url("data:{mime};base64,\\\n' + "\\\n".join(partes) + '")'


def _dimensoes_webp(raw: bytes) -> tuple[int, int]:
    """Largura × altura de um WebP (VP8X, VP8L ou VP8) sem depender do Pillow."""
    if raw[:4] != b"RIFF" or raw[8:12] != b"WEBP":
        raise ValueError("não é WebP")
    chunk = raw[12:16]
    if chunk == b"VP8X":
        w = int.from_bytes(raw[24:27], "little") + 1
        h = int.from_bytes(raw[27:30], "little") + 1
        return w, h
    if chunk == b"VP8L":
        bits = int.from_bytes(raw[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 ":
        return (int.from_bytes(raw[26:28], "little") & 0x3FFF,
                int.from_bytes(raw[28:30], "little") & 0x3FFF)
    raise ValueError(f"WebP com bloco inesperado {chunk!r}")


def bloco_css(topo: int | None = None) -> str:
    """Bloco CSS da marca, a partir das máscaras gravadas em ``docs/cdp/marca/``.

    ``topo``: altura (px da máscara) do recorte sem "ASSET MANAGEMENT"; sem ela, mantém a que o
    template já usa (``--marca-proporcao-topo``), calculada na última geração das máscaras."""
    tinta, sol, cabra = (p.read_bytes() for p in (TINTA, SOL, CABRA))
    w, h = _dimensoes_webp(tinta)
    if topo is None:
        topo = _topo_do_template(w)
    return "\n".join([
        INICIO,
        ".brand-mark, .foot-in {",
        f"  --marca-proporcao: {w} / {h};",
        f"  --marca-proporcao-topo: {w} / {topo};",
        f"  --marca-tinta: {_data_uri(tinta)};",
        f"  --marca-sol: {_data_uri(sol)};",
        "}",
        f".tabs-in {{ --marca-cabra: {_data_uri(cabra)}; }}",
        FIM,
    ])


def _template_texto() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _bloco_atual(texto: str) -> re.Match[str] | None:
    return re.search(re.escape(INICIO) + r".*?" + re.escape(FIM), texto, re.DOTALL)


def _topo_do_template(largura: int) -> int:
    m = _bloco_atual(_template_texto())
    if m:
        t = re.search(rf"--marca-proporcao-topo: {largura} / (\d+);", m.group(0))
        if t:
            return int(t.group(1))
    raise SystemExit("sem a proporção do recorte no template: rode com --mascaras --template")


def gravar_template(bloco: str) -> bool:
    """Troca o bloco da marca no template; devolve se o arquivo mudou."""
    texto = _template_texto()
    m = _bloco_atual(texto)
    if not m:
        raise SystemExit(f"{TEMPLATE}: marcadores da marca não encontrados ({INICIO!r})")
    novo = texto[:m.start()] + bloco + texto[m.end():]
    if novo == texto:
        return False
    TEMPLATE.write_text(novo, encoding="utf-8", newline="\n")
    return True


def verificar(bloco: str) -> list[str]:
    """Problemas do bloco/template (vazio = ok)."""
    erros = []
    longas = [n for n in (len(x) for x in bloco.splitlines()) if n > 2_000]
    if longas:
        erros.append(f"linhas acima de 2.000 caracteres no bloco: {longas}")
    m = _bloco_atual(_template_texto())
    if not m:
        erros.append("template sem o bloco da marca")
    elif m.group(0) != bloco:
        erros.append("o bloco do template difere das máscaras em docs/cdp/marca/ "
                     "(rode scripts/cdp_marca.py --template)")
    return erros


# ------------------------------------------------------------------------------- ornamentos
# Camada "Chapada" do portal: máscaras SVG monocromáticas (a cor vem do fundo do pseudoelemento,
# por token). Seis são geradas abaixo com sementes fixas (reprodutíveis byte a byte); cinco são
# desenhos fixos. Os esticáveis usam preserveAspectRatio='none': a espessura vem da altura da
# camada, nunca do comprimento. Guia: docs/cdp/marca/IDENTIDADE.md §5.
ORDEM_ORNAMENTOS = ("--orn-curva", "--orn-traco", "--orn-ilha", "--orn-curvas", "--orn-risco",
                    "--orn-goiva-e", "--orn-goiva-d", "--orn-gv", "--orn-sela", "--orn-sela-fio",
                    "--orn-pesponto")
_SVG = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {w} {h}'"
#: Desenhos fixos: olho e lances das curvas de nível entre seções, recorte e fio do assento da
#: sela e a curva do pesponto (os pontos vêm do fundo, em px fixos).
ORNAMENTOS_FIXOS = {
    "--orn-ilha": _SVG.format(w=400, h=40) + " fill='none' stroke='#000' stroke-width='1.1'>"
    "<path stroke-opacity='.6' d='M0 10C60 10 110 10 138 9C168 7 178 3 200 3S232 7 262 9 340 10 "
    "400 10M0 30C60 30 110 30 138 31C168 33 178 37 200 37S232 33 262 31 340 30 400 30'/><path d="
    "'M0 20C80 20 118 20 142 20C163 20 172 10.5 200 10.5S237 20 258 20 320 20 400 20M142 20C163 "
    "20 172 29.5 200 29.5S237 20 258 20'/></svg>",
    "--orn-curvas": _SVG.format(w=600, h=40) + " preserveAspectRatio='none' fill='none' "
    "stroke='#000' stroke-width='1.1'><path stroke-opacity='.6' d='M0 10C120 9.2 240 10.8 360 "
    "10.2S520 9.6 600 10M0 30C100 30.7 260 29.3 380 29.9S530 30.4 600 30'/><path d='M0 20C150 "
    "20.8 300 19.2 450 19.8S560 20.2 600 20'/></svg>",
    "--orn-sela": _SVG.format(w=200, h=12) + " preserveAspectRatio='none'><path d='M0 0C55 9 145 "
    "9 200 0V12H0Z'/></svg>",
    "--orn-sela-fio": _SVG.format(w=200, h=12) + " preserveAspectRatio='none'><path d='M0 .7C55 "
    "9.7 145 9.7 200 .7' fill='none' stroke='#000' stroke-width='1.2'/></svg>",
    "--orn-pesponto": _SVG.format(w=200, h=18) + " preserveAspectRatio='none'><path d='M0 "
    "5.5C55 14.5 145 14.5 200 5.5' fill='none' stroke='#000' stroke-width='1.1'/></svg>",
}


def _uri_svg(svg: str) -> str:
    s = svg.replace("<", "%3C").replace(">", "%3E").replace("#", "%23").replace('"', "'")
    return f'url("data:image/svg+xml,{s}")'


def _f(v: float) -> str:
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s if s not in ("", "-") else "0"


def _fita(xs, topo, base) -> str:
    """Contorno fechado de uma fita: a borda de cima da esquerda para a direita e a de baixo de
    volta."""
    cima = " ".join(f"{_f(x)} {_f(y)}" for x, y in zip(xs, topo, strict=True))
    baixo = " ".join(f"{_f(x)} {_f(y)}" for x, y in zip(reversed(xs), reversed(base), strict=True))
    return f"M{cima} L{baixo}Z"


def _ruido(n: int, semente: int, amp: float, k: int = 3) -> list[float]:
    """Ruído suave e reprodutível (média móvel de uniformes com semente fixa)."""
    import random

    r = random.Random(semente)
    bruto = [r.uniform(-1, 1) for _ in range(n + 2 * k)]
    return [amp * sum(bruto[i:i + 2 * k + 1]) / (2 * k + 1) * 1.8 for i in range(n)]


def gerar_ornamentos() -> dict[str, str]:
    """Os onze ornamentos da camada "Chapada" (``token → url("data:...")``), na ordem de
    :data:`ORDEM_ORNAMENTOS`. Determinístico: sementes fixas, só biblioteca padrão."""
    import math

    orn: dict[str, str] = {}
    esticado = " preserveAspectRatio='none'><path d='{d}'/></svg>"
    # pincelada de sol (300×16): cabeça cheia, corpo que sobe com o pulso e cerdas que se abrem
    w = 300

    def eixo(x):
        t = x / w
        return 8.7 - 2.0 * t + 0.3 * math.sin(t * 6.5)

    def meia(x):
        return 5.0 - 1.6 * (x / w) + 0.3 * math.sin(math.pi * min(x, 118) / 118)

    xs = [0, 1.5, 4, 8, 13, 20, 32, 48, 66, 86, 104, 118]
    rz = _ruido(len(xs), 7, 0.4, 1)
    topo, base = [], []
    for i, x in enumerate(xs):
        hh = meia(x) * math.sqrt(max(0.0, 1 - ((13 - x) / 13.4) ** 2)) + 0.3 if x < 13 else meia(x)
        topo.append(eixo(x) - hh + rz[i] * 0.45)
        base.append(eixo(x) + hh * 1.04 + rz[i] * 0.3)
    partes = [_fita(xs, topo, base)]
    for pos, fim, esp in ((-0.7, 300, 0.34), (-0.2, 236, 0.3), (0.27, 282, 0.3), (0.74, 214, 0.27)):
        sx = [108 + (fim - 108) * j / 9 for j in range(10)]
        ys = [eixo(x) + meia(x) * pos for x in sx]
        ts = [meia(x) * esp * (1 - ((x - 108) / (fim - 108)) ** 1.6) + 0.05 for x in sx]
        partes.append(_fita(sx, [y - t for y, t in zip(ys, ts, strict=True)],
                            [y + t for y, t in zip(ys, ts, strict=True)]))
    orn["--orn-traco"] = _uri_svg(_SVG.format(w=300, h=16) + esticado.format(d="".join(partes)))
    # curva de nível do título (1200×10): fio que engrossa depois da pincelada e some à direita
    xs = [0, 40, 90, 150, 220, 300, 390, 480, 580, 680, 780, 880, 980, 1080, 1150, 1200]
    topo, base = [], []
    for x in xs:
        t = x / 1200
        c = 6.0 + 0.55 * math.sin(t * 5.1 + 0.6) + 0.25 * math.sin(t * 13.3)
        hh = min(0.12 + 0.82 * math.exp(-((t - 0.3) / 0.2) ** 2) + 0.42 * (1 - t) ** 2, 0.95)
        topo.append(c - hh)
        base.append(c + hh)
    orn["--orn-curva"] = _uri_svg(_SVG.format(w=1200, h=10)
                                  + esticado.format(d=_fita(xs, topo, base)))
    # fio riscado à mão (ladrilho periódico 640×4): espessura e linha de base oscilam < 1 px
    xs = [640 * i / 20 for i in range(21)]
    topo, base = [], []
    for x in xs:
        a = 2 * math.pi * x / 640
        c = 2.0 + 0.32 * math.sin(a) + 0.18 * math.sin(3 * a + 1.1) + 0.1 * math.sin(5 * a + 0.3)
        hh = 0.5 + 0.16 * math.sin(2 * a + 0.7) + 0.08 * math.sin(7 * a)
        topo.append(c - hh)
        base.append(c + hh)
    orn["--orn-risco"] = _uri_svg(_SVG.format(w=640, h=4) + esticado.format(d=_fita(xs, topo, base)))
    # goivas da aba ativa (500×50): grossas junto da estrela, cauda afilada; a direita é o espelho
    xs = [0, 30, 70, 120, 180, 240, 300, 350, 395, 430, 455, 472, 484, 492, 497, 500]
    rz = _ruido(len(xs), 11, 1.6, 1)
    topo, base = [], []
    for i, x in enumerate(xs):
        t = x / 500
        c = 25 + 3.5 * math.sin(t * 4.2 + 0.4) + rz[i]
        if t < 0.94:
            hh = 2 + 21 * (t / 0.94) ** 1.6
        else:  # ataque curto: arredondado, levemente lascado
            hh = 23 * math.sqrt(max(0.0, 1 - ((t - 0.94) / 0.06) ** 2)) + 1
        topo.append(c - hh)
        base.append(c + hh * 0.92)
    orn["--orn-goiva-e"] = _uri_svg(_SVG.format(w=500, h=50)
                                    + esticado.format(d=_fita(xs, topo, base)))
    orn["--orn-goiva-d"] = _uri_svg(_SVG.format(w=500, h=50)
                                    + esticado.format(d=_fita([500 - x for x in xs], topo, base)))
    # goiva vertical (12×600): ataque em cima, cauda embaixo (citação, comentário, carregamento)
    ys = [0, 3, 8, 16, 40, 90, 160, 240, 320, 400, 470, 530, 570, 592, 600]
    rz = _ruido(len(ys), 5, 0.5, 1)
    esq, dir_ = [], []
    for i, y in enumerate(ys):
        t = y / 600
        c = 6 + 0.6 * math.sin(t * 5) + rz[i]
        larg = (5.2 * math.sqrt(max(0.0, 1 - ((0.03 - t) / 0.032) ** 2)) + 0.3 if t < 0.03
                else 5.4 * (1 - t) ** 0.55 + 0.25)
        esq.append(c - larg)
        dir_.append(c + larg * 0.9)
    pe = " ".join(f"{_f(x)} {_f(y)}" for x, y in zip(esq, ys, strict=True))
    pd_ = " ".join(f"{_f(x)} {_f(y)}" for x, y in zip(reversed(dir_), reversed(ys), strict=True))
    orn["--orn-gv"] = _uri_svg(_SVG.format(w=12, h=600) + esticado.format(d=f"M{pe} L{pd_}Z"))
    orn.update({k: _uri_svg(v) for k, v in ORNAMENTOS_FIXOS.items()})
    return {k: orn[k] for k in ORDEM_ORNAMENTOS}


def linhas_ornamentos() -> str:
    """As onze linhas de token (``  --orn-x: url(...);``) do ``:root`` da camada "Chapada"."""
    return "\n".join(f"  {k}: {v};" for k, v in gerar_ornamentos().items())


def _ornamentos_do_template(texto: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(
        r"^  (--orn-(?:curva|traco|ilha|curvas|risco|goiva-e|goiva-d|gv|sela|sela-fio|pesponto)): "
        r"(url\(\"data:image/svg\+xml,[^\n]*\"\));$", texto, re.MULTILINE)}


def gravar_ornamentos() -> bool:
    """Troca, no template, o valor de cada ornamento da camada pelo gerado (devolve se mudou)."""
    texto = _template_texto()
    novo = texto
    for k, v in gerar_ornamentos().items():
        novo, n = re.subn(rf"^  {re.escape(k)}: url\(\"data:image/svg\+xml,[^\n]*\"\);$",
                          lambda _m, k=k, v=v: f"  {k}: {v};", novo, flags=re.MULTILINE)
        if n != 1:
            raise SystemExit(f"{TEMPLATE}: esperado 1 token {k} na camada, achado(s) {n}")
    if novo == texto:
        return False
    TEMPLATE.write_text(novo, encoding="utf-8", newline="\n")
    return True


def verificar_ornamentos() -> list[str]:
    """Os ornamentos do template conferem com o gerador (vazio = ok)."""
    atuais = _ornamentos_do_template(_template_texto())
    erros = []
    for k, v in gerar_ornamentos().items():
        if k not in atuais:
            erros.append(f"template sem o ornamento {k}")
        elif atuais[k] != v:
            erros.append(f"ornamento {k} difere do gerador (rode scripts/cdp_marca.py "
                         "--ornamentos)")
    return erros


# ------------------------------------------------------------------------------- prévia
def previa(destino: Path) -> list[Path]:
    """Composições da marca pelas máscaras, nas cores dos dois temas (para revisão)."""
    from PIL import Image

    temas = {"claro": ((244, 239, 229), (29, 22, 17), (185, 105, 47)),
             "escuro": ((18, 16, 13), (239, 230, 213), (233, 160, 67))}
    destino.mkdir(parents=True, exist_ok=True)
    feitos = []
    for nome, (papel, tinta, sol) in temas.items():
        for arq, mascaras in (("marca", (TINTA, SOL)), ("cabra", (CABRA,))):
            masks = [Image.open(p).convert("RGBA").getchannel("A") for p in mascaras]
            img = Image.new("RGB", masks[0].size, papel)
            for mask, cor in zip(masks, (tinta, sol), strict=False):
                img.paste(Image.new("RGB", mask.size, cor), mask=mask)
            alvo = destino / f"{arq}_{nome}.png"
            img.save(alvo)
            feitos.append(alvo)
    return feitos


# ------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--mascaras", action="store_true",
                   help="regrava as três máscaras em docs/cdp/marca/ a partir de cdp-logo.png e o "
                        "bloco no template (máscaras e template andam juntos)")
    p.add_argument("--template", action="store_true", help="grava o bloco no template")
    p.add_argument("--ornamentos", action="store_true",
                   help="grava no template os ornamentos da camada \"Chapada\" (gerador com "
                        "sementes fixas)")
    p.add_argument("--check", action="store_true", help="confere o template (não grava nada)")
    p.add_argument("--previa", type=Path,
                   help="pasta para as composições PNG de revisão (só lê as máscaras)")
    a = p.parse_args(argv)
    if a.check and (a.mascaras or a.template or a.ornamentos):
        p.error("--check só confere: não combina com --mascaras, --template nem --ornamentos")

    if a.check:
        erros = verificar(bloco_css()) + verificar_ornamentos()
        for e in erros:
            print(e, file=sys.stderr)
        return 1 if erros else 0
    if a.ornamentos:
        mudou = gravar_ornamentos()
        print(f"/* ornamentos: template {'atualizado' if mudou else 'já estava em dia'} */",
              file=sys.stderr)
        if not (a.mascaras or a.template):
            return 0
    topo = None
    if a.mascaras:
        geo = gerar_mascaras()
        topo = geo["topo"]
        print(f"/* caixa {geo['caixa']} → {geo['tamanho']}; recorte do celular até {topo} px; "
              f"cabra {geo['cabra']} */", file=sys.stderr)
    bloco = bloco_css(topo)
    for f in (TINTA, SOL, CABRA):
        print(f"/* {f.relative_to(ROOT)}: {f.stat().st_size} B */", file=sys.stderr)
    print(f"/* bloco: {len(bloco.encode())} B; maior linha "
          f"{max(len(x) for x in bloco.splitlines())} */", file=sys.stderr)
    if a.previa:
        for f in previa(a.previa):
            print(f"/* prévia: {f} */", file=sys.stderr)
    if a.template or a.mascaras:
        mudou = gravar_template(bloco)
        print(f"/* template {'atualizado' if mudou else 'já estava em dia'} */", file=sys.stderr)
    else:
        print(bloco)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
