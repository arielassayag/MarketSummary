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
_ISO_RE = re.compile(r"(^|[^\w/.-])(\d{4})-(\d{2})-(\d{2})(?![\w/-]|:\d)")
_ZERO_NEG_RE = re.compile(r"−(0(?:,0+)?)(?![\d,])")
_NEG_RE = re.compile(r"(^|[\s(±=:/])-(?=\d)")


def pt_nums(texto: str) -> str:
    """Datas ISO soltas → dd/mm/aaaa; decimal com ponto → vírgula; menos → "−"."""
    if not texto:
        return texto
    t = _ISO_RE.sub(lambda m: f"{m.group(1)}{m.group(4)}/{m.group(3)}/{m.group(2)}", str(texto))
    t = _DEC_RE.sub(lambda m: m.group(0).translate(str.maketrans({",": ".", ".": ","})), t)
    t = _NEG_RE.sub(lambda m: m.group(1) + MINUS, t)
    return _ZERO_NEG_RE.sub(r"\1", t)  # "−0,00%" → "0,00%" (zero arredondado não tem sinal)


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
    mapa = {**nomes_do_universo(), **(nomes or {})}
    t = _IID_RE.sub(lambda m: nome(m.group(0), mapa), str(texto))
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


#: Nome pt-BR de cada controle do mandato (id sem argumento). Ids com argumento (país, setor,
#: estilo, tema, commodity) ganham o argumento traduzido entre parênteses (:func:`controle`).
CONTROLE_PT = {
    "WEIGHTS_VALID": "pesos numéricos válidos",
    "NET_EXPOSURE": "exposição líquida",
    "GROSS_MAX": "exposição bruta máxima",
    "GROSS_MIN": "exposição bruta mínima",
    "BETA": "beta previsto",
    "BETA_OP": "beta previsto (limite operacional)",
    "RISK_MODEL_COVERAGE": "cobertura do modelo de risco",
    "VOL_MAX": "volatilidade ex-ante máxima",
    "VOL_MIN": "volatilidade ex-ante mínima",
    "VOL_TARGET": "distância à meta de volatilidade",
    "NAME_LONG_MAX": "peso máximo por nome (posição comprada)",
    "NAME_SHORT_MAX": "peso máximo por nome (posição vendida)",
    "LIQ_DAYS_LONG": "prazo de liquidação das posições compradas",
    "LIQ_DAYS_SHORT": "prazo de liquidação das posições vendidas",
    "SHORT_NOT_ALLOWED": "venda a descoberto só em linhas alugáveis e sem veto",
    "SHORT_ENTRY_BLOCK": "sem nova venda a descoberto em nome vetado",
    "SHORT_ENTRY_DATA": "dados dos vetos de venda a descoberto",
    "SQUEEZE_HIGH": "sem posição vendida com risco alto de squeeze",
    "SQUEEZE_MEDIUM_CAP": "teto da posição vendida com risco médio de squeeze",
    "BORROW_FEE": "taxa de aluguel das posições vendidas",
    "LONG_NOT_ALLOWED": "compra só em nomes elegíveis e sem veto",
    "TURNOVER": "giro semanal",
    "SINGLE_NAME_RISK": "contribuição máxima de um nome ao risco",
    "FACTOR_RISK_SHARE": "parcela fatorial do risco",
    "IDIO_SHARE": "meta da fatia idiossincrática (modelo de decisão)",
    "IDIO_FLOOR": "piso da fatia idiossincrática (modelo de decisão)",
    "IDIO_SHARE_BASE": "meta da fatia idiossincrática (modelo base)",
    "IDIO_FLOOR_BASE": "piso da fatia idiossincrática (modelo base)",
    "TRADE_CLOSE_CAPACITY": "ordens dentro da capacidade do fechamento",
    "CLOSED_MARKETS_FROZEN": "emissores sem fechamento negociável",
    "DATA_STALENESS": "defasagem dos dados de mercado",
    "DRAWDOWN_SOFT": "nível de revisão do drawdown",
    "DRAWDOWN_HARD": "stop de drawdown (corte da exposição bruta)",
    "SYNTHETIC_DATA": "origem dos dados",
    "COUNTRY_GAP_STRESS": "perda em gap de país",
    "LINKED_GROUP": "grupo de controle (holding e controladas)",
    "EVENT": "exposição ao choque de evento",
}
_CONTROLE_ARG = {
    "COUNTRY_NET": ("exposição líquida por país", "pais"),
    "COUNTRY_OP": ("exposição líquida por país, limite operacional", "pais"),
    "SECTOR_NET": ("exposição líquida por setor", "setor"),
    "SECTOR_OP": ("exposição líquida por setor, limite operacional", "setor"),
    "STYLE": ("exposição ao estilo", "estilo"),
    "STYLE_OP": ("exposição ao estilo, limite operacional", "estilo"),
    "THEME_NET": ("exposição líquida ao tema", "tema"),
    "COMMODITY": ("sensibilidade a commodity", "commodity"),
    "COMMODITY_OP": ("sensibilidade a commodity, limite operacional", "commodity"),
}


def _arg_pt(tipo: str, arg: str) -> str:
    if tipo == "pais":
        return COUNTRY_PT.get(arg, arg)
    if tipo == "setor":
        return SECTOR_PT.get(arg, arg).lower()
    if tipo == "estilo":
        return STYLE_PT.get(arg, arg).lower()
    if tipo == "tema":
        return THEME_PT.get(arg, arg)
    return COMMODITY_PT.get(arg, arg)


def controle(check_id: str, nome_: str | None = None) -> str:
    """Nome pt-BR de um controle do mandato (``COUNTRY_NET:AR`` → exposição líquida por país
    (Argentina)). Id desconhecido: o nome gravado no controle (``nome_``) em pt-BR, ou o rótulo
    genérico do painel — nunca o id técnico."""
    base, _, arg = str(check_id).partition(":")
    if base in _CONTROLE_ARG and arg:
        rotulo, tipo = _CONTROLE_ARG[base]
        return f"{rotulo} ({_arg_pt(tipo, arg)})"
    if base in CONTROLE_PT:
        return CONTROLE_PT[base]
    if nome_:
        return pt_texto(str(nome_))
    return limit_label_pt(check_id)


_DETALHE_PT: tuple[tuple[str, str], ...] = (
    (r"\bNet país\b", "Líquido no país"),
    (r"\bNet setor\b", "Líquido no setor"),
    (r"\bNet (AR|BR|CL|CO|MX|PE|UY|PA|LATAM)\b", r"Líquido no país \1"),
    (r"\bNet (?=[-+−]?\d)", "Líquido "),
    (r"\bGross (?=[-+−]?\d)", "Exposição bruta "),
    (r"\bGross máximo\b", "Exposição bruta máxima"),
    (r"\bgross máximo\b", "exposição bruta máxima"),
    (r"; long (?=[-+−]?\d)", "; comprado "),
    (r", short (?=[-+−]?\d)", ", vendido "),
    (r"\bShorts MEDIUM/NA\b", "Posições vendidas com risco de squeeze médio ou sem dado"),
    (r"\bNenhum long\b", "Nenhuma posição comprada"),
    (r"\bNenhum short novo ou aumentado\b", "Nenhuma venda a descoberto nova ou aumentada"),
    (r"\bNenhum short\b", "Nenhuma posição vendida"),
    (r"\bTodos os longs são permitidos\b", "Todas as compras são permitidas"),
    (r"\bTodos os shorts são alugáveis e sem veto\b",
     "Todas as posições vendidas são alugáveis e sem veto"),
    (r"\bSnapshot de\b", "Dados de mercado de"),
    (r"\bInception: montagem inicial\b", "Carteira inaugural: montagem inicial"),
    (r"\bInception\b", "Carteira inaugural"),
    (r"\bstop-out\b", "zeragem"),
    (r"\bvs\. meta\b", "contra a meta"),
    (r"\bVol ex-ante\b", "Volatilidade ex-ante"),
    (r"\bshort squeeze\b", "squeeze"),
    (r"\bReação residual de \d{4}-\d{2}-\d{2}", "Reação residual ao choque do evento"),
)


def detalhe(texto: str, nomes: Mapping[str, str] | None = None) -> str:
    """Detalhe de um controle (texto do código) em pt-BR para o investidor."""
    if not texto:
        return texto
    t = str(texto)
    for padrao, troca in _DETALHE_PT:
        t = re.sub(padrao, troca, t)
    return plural(pt_texto(t, nomes))


_PLURAL_PT = {
    "dias corridos": "dia corrido", "dias úteis": "dia útil", "dias": "dia",
    "pregões": "pregão", "fechamentos": "fechamento", "semanas": "semana",
    "posições": "posição", "emissores": "emissor", "nomes": "nome", "linhas": "linha",
    "ordens": "ordem", "avisos": "aviso", "alertas": "alerta", "controles": "controle",
    "registros": "registro", "visões": "visão", "notas": "nota", "manchetes": "manchete",
}
_PLURAL_RE = re.compile(r"(?<![\d.,])(1|um|uma) (" + "|".join(
    sorted(map(re.escape, _PLURAL_PT), key=len, reverse=True)) + r")\b")


def plural(texto: str) -> str:
    """Concordância de "1 pregões" → "1 pregão" (e afins) em texto gerado pelo código."""
    if not texto:
        return texto
    return _PLURAL_RE.sub(lambda m: f"{m.group(1)} {_PLURAL_PT[m.group(2)]}", str(texto))


def contagem(n: int, singular: str, plural_: str) -> str:
    """``1 pregão`` / ``3 pregões``."""
    return f"{n} {singular if n == 1 else plural_}"


#: Termos de mercado em inglês que o investidor lê em pt-BR (aviso de dados, rótulos).
_TERMOS_PT: tuple[tuple[str, str], ...] = (
    (r"\b[Pp]aper trading com preços reais\b", "carteira simulada com preços reais"),
    (r"\b[Pp]aper trading com\b", "carteira simulada com"),
    (r"\b(?:em )?[Pp]aper trading\b", "carteira simulada"),
)


def aviso(texto: str | None) -> str:
    """Aviso de dados gravado pelo código, com a terminologia ao investidor ("carteira
    simulada", nunca "paper trading")."""
    t = str(texto or "")
    for padrao, troca in _TERMOS_PT:
        t = re.sub(padrao, troca, t)
    return t


def nomes_no_texto(texto: str | None, nomes: Mapping[str, str] | None = None) -> str:
    """Só troca identificadores internos (``BR_PETROBRAS``) pelo nome — para texto escrito pela
    gestão (IA), cujos números já vêm formatados em pt-BR e não podem ser reconvertidos."""
    if not texto:
        return texto or ""
    mapa = {**nomes_do_universo(), **(nomes or {})}
    return _IID_RE.sub(lambda m: nome(m.group(0), mapa), str(texto))


_CENARIO_PT: tuple[tuple[str, str], ...] = (
    (r"\b5 maiores longs\b", "5 maiores posições compradas"),
    (r"\b5 maiores shorts\b", "5 maiores posições vendidas"),
    (r"^COVID crash\b", "Crise da covid"),
    (r"^Momentum crash\b", "Colapso do fator momentum"),
    (r"^Mercado LatAm\b", "Mercado da América Latina"),
    (r"^Taper/estresse\b", "Estresse de juros nos EUA"),
    (r"^Gap (AR|BR|CL|CO|MX|PE|UY|PA)\b", "Gap {pais}"),
)


def cenario(nome_: str) -> str:
    """Nome pt-BR de um cenário de estresse (``Gap AR +41%`` → ``Gap Argentina +41%``)."""
    t = str(nome_)
    for padrao, troca in _CENARIO_PT:
        m = re.search(padrao, t)
        if m:
            rep = troca.format(pais=COUNTRY_PT.get(m.group(1), m.group(1))) if "{pais}" in troca \
                else troca
            t = t[:m.start()] + rep + t[m.end():]
    return pt_nums(t)


MACRO_PT = {"BZ=F": "petróleo Brent", "CL=F": "petróleo WTI", "HG=F": "cobre", "GC=F": "ouro",
            "SI=F": "prata", "DX-Y.NYB": "índice do dólar (DXY)", "ZS=F": "soja",
            "TIO=F": "minério de ferro"}


def fator(rotulo: str) -> str:
    """Rótulo de fator sem códigos de cotação (``Macro — BZ=F`` → ``Macro — petróleo Brent``)."""
    t = str(rotulo)
    for cod, nome_pt in MACRO_PT.items():
        t = t.replace(cod, nome_pt)
    return t.replace("Mercado LatAm", "Mercado da América Latina")


__all__ = ["CAMINHO_PT", "CONTROLE_PT", "DECISAO_PT", "GRUPO_PT", "LADO_PT", "MACRO_PT",
           "MODO_PT", "SEVERIDADE_PT", "aviso", "cenario", "contagem", "controle", "detalhe",
           "exposicao", "fator", "lado", "nome", "nomes_no_texto", "plural", "pt_nums",
           "pt_texto", "quando"]
