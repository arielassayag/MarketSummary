"""Rótulos e formatação ao investidor (pt-BR) para os relatórios em Markdown e HTML.

O código grava os registros com identificadores técnicos (``BR_ITAU``, ``LONG``, ``APPROVE``,
``COUNTRY_NET:AR``, ``tema:state_owned``) e números com ponto decimal nos detalhes dos controles.
O texto lido pelo investidor usa nomes de empresas, rótulos em português, vírgula decimal, datas
dd/mm/aaaa e horário de Brasília. Os mesmos dados técnicos continuam nos dados abertos.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from .painel import COMMODITY_PT, SECTOR_PT, STYLE_PT, THEME_PT, limit_label_pt
from .tese_analise import COUNTRY_PT

FUSO = ZoneInfo("America/Sao_Paulo")
MINUS = "−"

LADO_PT = {"LONG": "comprada", "SHORT": "vendida"}
MODO_PT = {"AUTONOMOUS": "autônoma", "HUMAN": "humana", "MANUAL": "humana"}
DECISAO_PT = {"APPROVE": "aprovada", "REJECT": "rejeitada", "HOLD": "carteira mantida",
              "ABSTAIN": "abstenção"}
SEVERIDADE_PT = {"HARD": "obrigatório", "SOFT": "alerta", "INFO": "indicador"}
GRUPO_PT = {"country": "País", "sector": "Setor", "style": "Estilo", "market": "Temas e commodities",
            "theme": "Tema", "commodity": "Commodity"}
CAMINHO_PT = {"cdp": "pesquisa e decisão do gestor", "quant": "modelo quantitativo",
              "hold": "carteira mantida"}

_IID_RE = re.compile(r"\b(?:(?:AR|BR|CL|CO|MX|PE|UY|PA|LATAM)_[A-Z0-9_]+|SIM\d{3})\b")
_DEC_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+")
_ISO_RE = re.compile(r"(^|[^\w/.-])(\d{4})-(\d{2})-(\d{2})(?![\w/:-])")
_NEG_RE = re.compile(r"(^|[\s(±=:/])-(?=\d)")


def pt_nums(texto: str) -> str:
    """Datas ISO soltas → dd/mm/aaaa; decimal com ponto → vírgula; menos → "−"."""
    if not texto:
        return texto
    t = _ISO_RE.sub(lambda m: f"{m.group(1)}{m.group(4)}/{m.group(3)}/{m.group(2)}", str(texto))
    t = _DEC_RE.sub(lambda m: m.group(0).translate(str.maketrans({",": ".", ".": ","})), t)
    return _NEG_RE.sub(lambda m: m.group(1) + MINUS, t)


@lru_cache(maxsize=1)
def _universo_nomes() -> tuple[tuple[str, str], ...]:
    try:
        from ..universe import load_universe

        u = load_universe()
    except Exception:  # noqa: BLE001 - sem universo: os ids ficam
        return ()
    return tuple((str(i), str(n)) for i, n in u.issuers["issuer_name"].items())


def nomes_do_universo() -> dict[str, str]:
    """``{emissor: nome}`` do universo do repositório (com a grafia de ``configs/cdp/nomes.yaml``);
    vazio sem o arquivo (demonstração, testes)."""
    return dict(_universo_nomes())


def nome(iid: str, nomes: Mapping[str, str] | None) -> str:
    """Nome da empresa pelo identificador interno (o próprio id se não houver nome)."""
    n = (nomes or {}).get(iid)
    return str(n) if n else str(iid)


def pt_texto(texto: str, nomes: Mapping[str, str] | None = None) -> str:
    """Texto do código para o investidor: nomes no lugar de ids, rótulos e números em pt-BR."""
    if not texto:
        return texto
    t = _IID_RE.sub(lambda m: nome(m.group(0), nomes), str(texto))
    t = re.sub(r"commodity:(\w+)", lambda m: COMMODITY_PT.get(m.group(1), m.group(1)), t)
    t = re.sub(r"'?tema:state_owned'?|'?state_owned'?", THEME_PT["state_owned"], t)
    t = re.sub(r"\bNAV\b", "PL", t)
    t = re.sub(r"(?<=[Ss]etor )(" + "|".join(map(re.escape, SECTOR_PT)) + r")\b",
               lambda m: SECTOR_PT[m.group(1)], t)
    t = re.sub(r"(?<=[Pp]aís )(AR|BR|CL|CO|MX|PE|UY|PA|LATAM)\b",
               lambda m: COUNTRY_PT.get(m.group(1), m.group(1)), t)
    return pt_nums(t)


def lado(valor: object) -> str:
    v = getattr(valor, "value", valor)
    return LADO_PT.get(str(v), str(v).lower())


def quando(dt: datetime | None) -> str:
    """Instante no horário de Brasília (``09/10/2026 13:02``)."""
    if dt is None:
        return "n/d"
    return f"{dt.astimezone(FUSO):%d/%m/%Y %H:%M} (Brasília)"


def exposicao(grupo: str, nome_: str) -> tuple[str, str]:
    """(grupo, nome) de uma linha de exposição em pt-BR."""
    g = GRUPO_PT.get(grupo, grupo)
    s = str(nome_)
    if s.startswith("tema:"):
        return "Tema", THEME_PT.get(s[5:], s[5:]).capitalize()
    if s.startswith("commodity:"):
        return "Commodity", COMMODITY_PT.get(s[10:], s[10:]).capitalize()
    if s.startswith("evento:"):
        return "Evento", s[7:]
    if grupo == "country":
        return g, COUNTRY_PT.get(s, s)
    if grupo == "sector":
        return g, SECTOR_PT.get(s, s)
    if grupo == "style":
        return g, STYLE_PT.get(s, s)
    return g, s


def controle(check_id: str) -> str:
    """Nome pt-BR de um controle do mandato (``COUNTRY_NET:AR`` → exposição líquida por país)."""
    base, _, arg = str(check_id).partition(":")
    if base in ("COUNTRY_NET",) and arg:
        return f"exposição líquida — {COUNTRY_PT.get(arg, arg)}"
    return limit_label_pt(check_id)


__all__ = ["CAMINHO_PT", "DECISAO_PT", "GRUPO_PT", "LADO_PT", "MODO_PT", "SEVERIDADE_PT",
           "controle", "exposicao", "lado", "nome", "pt_nums", "pt_texto", "quando"]
