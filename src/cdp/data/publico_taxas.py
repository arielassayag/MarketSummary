"""Taxas e expectativas públicas: FRED (UST 10a), BCB SGS (Selic, IPCA) e BCB Focus (Olinda).

Séries (valores em decimal, exceto câmbio em BRL por USD):

- ``USD_10Y``: FRED ``DGS10`` (``fredgraph.csv``; % a.a. ÷ 100);
- ``SELIC_META``: BCB SGS 432 (% a.a. ÷ 100; a série traz datas futuras até a próxima reunião,
  descartadas — sem look-ahead);
- ``IPCA_12M``: BCB SGS 13522 (% em 12 meses ÷ 100). O SGS data o índice no 1º dia do mês de
  referência, mas o IBGE o divulga só no mês seguinte: a ``data`` da série é a de
  disponibilidade (fim do mês de referência + 12 dias, prazo conservador de divulgação) — sem
  look-ahead numa releitura;
- ``FOCUS_<IND>_<ANO>``: mediana do Focus (``ExpectativasMercadoAnuais``, ``baseCalculo = 0``)
  para IPCA, Selic, Câmbio e PIB Total, anos ``as_of.ano`` … ``as_of.ano + 4``; data = data da
  pesquisa (``Data``). IPCA/Selic/PIB em decimal; Câmbio em BRL/USD.
- Banxico (SIE) exige token pessoal gratuito: com ``BANXICO_TOKEN`` no ambiente, ``MX_TIIE28``
  (SF43783) e ``MX_BONO10`` (SF43939… conforme catálogo do SIE); sem token, fica de fora
  (registrado como limitação), nunca preenchido.
"""

from __future__ import annotations

import io
import json
import math
import urllib.parse
from datetime import date, timedelta

import pandas as pd

URL_FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={ini}&coed={fim}"
URL_SGS = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?formato=json&"
           "dataInicial={ini}&dataFinal={fim}")
URL_FOCUS = ("https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
             "ExpectativasMercadoAnuais?$filter={filtro}&$format=json&$top=5000"
             "&$select=Indicador,Data,DataReferencia,Mediana,baseCalculo,numeroRespondentes")
URL_BANXICO = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/{sid}/datos/{ini}/{fim}"
"""O token pessoal do SIE vai no cabeçalho ``Bmx-Token`` (nunca no endereço)."""

SGS = {"SELIC_META": 432, "IPCA_12M": 13522}
SGS_DIVULGACAO_DIAS = {"IPCA_12M": 12}
"""Séries mensais datadas pelo mês de referência: dias após o fim do mês até a divulgação."""
FOCUS = {"IPCA": "IPCA", "Selic": "SELIC", "Câmbio": "CAMBIO", "PIB Total": "PIB"}
BANXICO = {"MX_TIIE28": "SF43783", "MX_BONO10": "SF43939"}
COLUNAS = ["serie", "data", "valor", "fonte", "url", "sha256"]


def url_fred(sid: str, ini: date, fim: date) -> str:
    return URL_FRED.format(sid=sid, ini=ini.isoformat(), fim=fim.isoformat())


def url_sgs(code: int, ini: date, fim: date) -> str:
    return URL_SGS.format(code=code, ini=ini.strftime("%d/%m/%Y"), fim=fim.strftime("%d/%m/%Y"))


def url_focus(indicador: str, desde: date) -> str:
    filtro = f"Indicador eq '{indicador}' and Data ge '{desde.isoformat()}'"
    return URL_FOCUS.format(filtro=urllib.parse.quote(filtro, safe="'"))


def ler_fred(conteudo: bytes, serie: str, escala: float = 0.01) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(conteudo), na_values=[".", ""])
    if df.shape[1] < 2:
        raise ValueError("CSV do FRED inesperado.")
    d = pd.to_datetime(df.iloc[:, 0], errors="coerce")
    v = pd.to_numeric(df.iloc[:, 1], errors="coerce") * escala
    out = pd.DataFrame({"serie": serie, "data": d, "valor": v}).dropna()
    return out


def validar_fred(conteudo: bytes) -> None:
    head = conteudo[:200].decode("utf-8", errors="replace")
    if "<html" in head.lower() or "," not in head:
        raise ValueError("Resposta do FRED não é CSV.")


def ler_sgs(conteudo: bytes, serie: str, ate: date, escala: float = 0.01) -> pd.DataFrame:
    data = json.loads(conteudo)
    if not isinstance(data, list):
        raise ValueError("Resposta do SGS inesperada.")
    rows = []
    for item in data:
        try:
            d = pd.to_datetime(str(item.get("data")), format="%d/%m/%Y")
            v = float(str(item.get("valor", "")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        if serie in SGS_DIVULGACAO_DIAS:  # data de disponibilidade, não de referência
            d = d + pd.offsets.MonthEnd(0) + pd.Timedelta(days=SGS_DIVULGACAO_DIAS[serie])
        if math.isfinite(v) and d <= pd.Timestamp(ate):
            rows.append({"serie": serie, "data": d, "valor": v * escala})
    return pd.DataFrame(rows, columns=["serie", "data", "valor"])


def validar_json_lista(conteudo: bytes) -> None:
    if not isinstance(json.loads(conteudo), list):
        raise ValueError("Resposta não é uma lista JSON.")


def ler_focus(conteudo: bytes, as_of: date) -> pd.DataFrame:
    obj = json.loads(conteudo)
    vals = obj.get("value") if isinstance(obj, dict) else None
    if vals is None:
        raise ValueError("Resposta do Focus inesperada.")
    rows = []
    anos = {str(as_of.year + k) for k in range(5)}
    for r in vals:
        ind = r.get("Indicador")
        if ind not in FOCUS or str(r.get("DataReferencia")) not in anos:
            continue
        if int(r.get("baseCalculo", 0) or 0) != 0:
            continue
        try:
            d = pd.Timestamp(str(r.get("Data")))
            v = float(r.get("Mediana"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(v) or d > pd.Timestamp(as_of):
            continue
        escala = 1.0 if ind == "Câmbio" else 0.01
        rows.append({"serie": f"FOCUS_{FOCUS[ind]}_{r.get('DataReferencia')}", "data": d,
                     "valor": v * escala})
    return pd.DataFrame(rows, columns=["serie", "data", "valor"])


def validar_focus(conteudo: bytes) -> None:
    obj = json.loads(conteudo)
    if not isinstance(obj, dict) or "value" not in obj:
        raise ValueError("Resposta do Focus inesperada.")


def ler_banxico(conteudo: bytes, serie: str, ate: date) -> pd.DataFrame:
    obj = json.loads(conteudo)
    rows = []
    for s in (obj.get("bmx") or {}).get("series") or []:
        for p in s.get("datos") or []:
            try:
                d = pd.to_datetime(p["fecha"], format="%d/%m/%Y")
                v = float(str(p["dato"]).replace(",", ""))
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(v) and d <= pd.Timestamp(ate):
                rows.append({"serie": serie, "data": d, "valor": v / 100.0})
    return pd.DataFrame(rows, columns=["serie", "data", "valor"])


def janela(as_of: date, anos: int = 3) -> tuple[date, date]:
    return as_of - timedelta(days=365 * anos), as_of


__all__ = [
    "BANXICO", "COLUNAS", "FOCUS", "SGS", "SGS_DIVULGACAO_DIAS", "URL_BANXICO", "janela", "ler_banxico", "ler_focus",
    "ler_fred", "ler_sgs", "url_focus", "url_fred", "url_sgs", "validar_focus", "validar_fred",
    "validar_json_lista",
]
