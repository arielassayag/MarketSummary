"""Contrato opt-in do corpo público quoteSummary earningsTrend por período.

Bytes HTTP são arquivados intactos pelo Arquivo. Não lê cache privado SDK, não
replica moeda de trimestre e não autentica nominalidade/PPP ou publicação.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import quote, urlencode

from .publico_arquivo import Arquivo, RegistroArquivo

COLUNAS = ["eps_origem_moeda", "eps_contexto"]
PERIODOS = ("0y", "+1y")
BASE_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"


def identidade(ticker: str) -> tuple[str, str]:
    if not isinstance(ticker, str) or not re.fullmatch(r"[A-Za-z0-9_.=\-]+", ticker):
        raise ValueError("Ticker inválido no contrato EPS")
    return (
        "YAHOO/earningsTrend/" + ticker + ".json",
        BASE_URL
        + quote(ticker, safe="")
        + "?"
        + urlencode({"modules": "earningsTrend,quoteType", "formatted": "false", "symbol": ticker}),
    )


def _constante(value):
    raise ValueError("Constante JSON não finita: " + value)


def _pares(items):
    out = {}
    for k, v in items:
        if k in out:
            raise ValueError("Chave JSON duplicada")
        out[k] = v
    return out


def _numero(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Valor numérico EPS sem objeto raw")
    raw = value.get("raw")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, Decimal)):
        raise ValueError("Valor raw EPS inválido")
    if not Decimal(raw).is_finite():
        raise ValueError("Valor raw EPS não finito")
    try:
        result = float(raw)
    except OverflowError as exc:
        raise ValueError("Valor raw EPS fora de escala float") from exc
    if not math.isfinite(result):
        raise ValueError("Valor raw EPS fora de escala float")
    return result


def _moeda(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("Código de moeda EPS inválido")
    return value  # Declaração do provider, não prova de base nominal/poder aquisitivo.


def _fim(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("endDate EPS inválido")
    return date.fromisoformat(value).isoformat()


def ler_corpo(conteudo: bytes, ticker: str) -> tuple[dict, dict]:
    """Seleciona só EPS do corpo HTTP; receita auxiliar não integra esta opção."""
    identidade(ticker)
    if not isinstance(conteudo, bytes):
        raise ValueError("HTTP EPS exige bytes intactos")
    doc = json.loads(
        conteudo, parse_float=Decimal, parse_constant=_constante, object_pairs_hook=_pares
    )
    if not isinstance(doc, dict) or not isinstance(doc.get("quoteSummary"), dict):
        raise ValueError("Envelope quoteSummary ausente")
    q = doc["quoteSummary"]
    if q.get("error") is not None or not isinstance(q.get("result"), list) or len(q["result"]) != 1:
        raise ValueError("Resposta quoteSummary com erro/identidade ambígua")
    result = q["result"][0]
    if not isinstance(result, dict) or not isinstance(result.get("quoteType"), dict):
        raise ValueError("Identidade quoteType ausente")
    if result["quoteType"].get("symbol") != ticker:
        raise ValueError("symbol do corpo EPS divergente")
    trend_module = result.get("earningsTrend")
    if not isinstance(trend_module, dict):
        raise ValueError("earningsTrend ausente")
    trend = trend_module.get("trend")
    if not isinstance(trend, list):
        raise ValueError("earningsTrend.trend ausente")
    selected = {}
    for n, item in enumerate(trend):
        if not isinstance(item, dict):
            raise ValueError("Período earningsTrend inválido")
        period = item.get("period")
        if period not in PERIODOS:
            continue  # Moeda trimestral nunca preenche a de um exercício.
        if period in selected:
            raise ValueError("Período EPS duplicado")
        b = item.get("earningsEstimate")
        if not isinstance(b, dict):
            raise ValueError("earningsEstimate do exercício ausente")
        value = _numero(b.get("avg"))
        count = _numero(b.get("numberOfAnalysts"))
        if count is not None and (count < 0 or not count.is_integer()):
            raise ValueError("Número de analistas EPS inválido")
        selected[period] = {
            "avg": value,
            "numberOfAnalysts": count,
            "currency": _moeda(b.get("earningsCurrency")),
            "period_end": _fim(item.get("endDate")),
            "ancora": f"/quoteSummary/result/0/earningsTrend/trend/{n}",
            "valor_raw_literal": None
            if b.get("avg") is None
            else str(b["avg"]["raw"])
            if b["avg"].get("raw") is not None
            else None,
        }
    pair = [selected.get(p, {}) for p in PERIODOS]
    currency = [r.get("currency") for r in pair]
    ends = [r.get("period_end") for r in pair]
    if all(c is not None for c in currency) and currency[0] != currency[1]:
        raise ValueError("Moedas individuais dos exercícios divergem")
    if all(d is not None for d in ends) and ends[0] >= ends[1]:
        raise ValueError("Encerramentos dos exercícios contraditórios")
    # O agregado recebe moeda somente com o par completo; OR do legado não é usado.
    common = currency[0] if all(c is not None for c in currency) else None
    est = {
        "earnings_estimate": {
            p: {k: selected.get(p, {}).get(k) for k in ("avg", "currency", "numberOfAnalysts")}
            for p in PERIODOS
        }
    }
    # O corpo bruto permanece integral no Arquivo. Receita requer outro contrato;
    # não a entregar ao normalizador legado evita razões monetárias não vinculadas.
    return est, {"periodos": selected, "moeda_comum": common}


def consenso_do_registro(
    conteudo: bytes, ticker: str, reg: RegistroArquivo, *, conhecimento_ate: datetime
) -> tuple[dict, dict]:
    """Vincula o parse aos bytes/identidade/recibo nativo; não certifica HTTP ao vivo."""
    if (
        not isinstance(conhecimento_ate, datetime)
        or conhecimento_ate.tzinfo is None
        or conhecimento_ate.utcoffset() is None
    ):
        raise ValueError("EPS individual exige corte UTC explícito")
    key, url = identidade(ticker)
    if reg.chave != key or reg.fonte != "YAHOO" or reg.url != url:
        raise ValueError("Registro HTTP EPS com identidade/URL/fonte divergente")
    if reg.bytes != len(conteudo) or reg.sha256 != hashlib.sha256(conteudo).hexdigest():
        raise ValueError("Bytes/SHA do registro EPS divergentes")
    if reg.data_coleta.tzinfo is None or reg.data_coleta.utcoffset() is None:
        raise ValueError("Registro EPS sem fuso")
    if reg.limite_captura > conhecimento_ate or reg.limite_captura > datetime.now(UTC):
        raise ValueError("Recepção EPS posterior ao corte/relógio")
    est, cells = ler_corpo(conteudo, ticker)
    context = {
        "schema": "cdp.yahoo.eps_por_periodo/v1",
        "ticker": ticker,
        "fonte": "YAHOO",
        "provider": "Yahoo Finance",
        "dataset": "quoteSummary.earningsTrend",
        "nivel_origem_moeda": "earningsEstimate.earningsCurrency por período no corpo HTTP",
        "corpo_sha256": reg.sha256,
        "bytes": reg.bytes,
        "url": reg.url,
        "recebido_em": reg.data_coleta.isoformat(),
        "precisao": reg.precisao,
        "disponivel_desde": reg.limite_captura.isoformat(),
        "publicacao_primaria": None,
        "base_nominal_id": None,
        "poder_aquisitivo_data": None,
        "unidade_por_instrumento": None,
        "ponte_FY_12m_FX": None,
        **cells,
    }
    extras = {
        "eps_origem_moeda": "http_por_periodo",
        "eps_contexto": json.dumps(
            context, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ),
    }
    return est, extras


def contexto_da_linha(row) -> dict | None:
    """Confere redundâncias do opt-in; não reautentica HTTP por metadados isolados.

    Aceita os dois formatos efetivamente emitidos: float do parser ou a mesma
    célula serializada pelo CSV normal (10 algarismos significativos).
    """
    import pandas as pd

    def ausente(v):
        return v is None or v is pd.NA or v is pd.NaT or (isinstance(v, float) and math.isnan(v))

    marker, encoded = (row.get(k) for k in COLUNAS)
    if ausente(marker) and ausente(encoded):
        return None
    if not isinstance(marker, str) or marker != "http_por_periodo" or not isinstance(encoded, str):
        raise ValueError("Contexto EPS parcial ou origem inválida")
    # Esta linha autentica somente EPS. Receita auxiliar no CSV não recebe autoridade
    # dos mesmos bytes/contexto e não pode alcançar o crescimento do consumidor legado.
    for field, value in row.items():
        if isinstance(field, str) and (
            field.startswith(("receita_", "moeda_receita")) or field.endswith("_receita")
        ) and not ausente(value):
            raise ValueError(f"Contrato EPS por período não admite campo de receita: {field}")
    c = json.loads(encoded, parse_constant=_constante, object_pairs_hook=_pares)
    if not isinstance(c, dict) or c.get("schema") != "cdp.yahoo.eps_por_periodo/v1":
        raise ValueError("Schema EPS individual inválido")
    ticker = row.get("ticker")
    _, url = identidade(ticker)
    if (
        c.get("ticker") != ticker
        or c.get("fonte") != "YAHOO"
        or row.get("fonte") != "YAHOO"
        or c.get("provider") != "Yahoo Finance"
        or c.get("dataset") != "quoteSummary.earningsTrend"
        or c.get("url") != url
        or row.get("url") != url
        or c.get("corpo_sha256") != row.get("sha256")
        or not re.fullmatch(r"[a-f0-9]{64}", str(c.get("corpo_sha256")))
    ):
        raise ValueError("Identidade/SHA/origem EPS contraditórios")
    try:
        receipt = datetime.fromisoformat(c.get("recebido_em", ""))
        received = pd.Timestamp(row.get("data_coleta"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Recepção EPS inválida") from exc
    if (
        receipt.tzinfo is None
        or received.tzinfo is None
        or receipt != received
        or c.get("publicacao_primaria") is not None
    ):
        raise ValueError("Recepção/publicação EPS contraditória")
    cells = c.get("periodos")
    if not isinstance(cells, dict):
        raise ValueError("Períodos EPS ausentes")
    cc, ee = [], []
    for period, field in zip(PERIODOS, ("eps_fy1", "eps_fy2"), strict=True):
        cell = cells.get(period, {})
        if not isinstance(cell, dict):
            raise ValueError("Célula EPS inválida")
        cc.append(_moeda(cell.get("currency")))
        ee.append(_fim(cell.get("period_end")))
        actual, expected = row.get(field), cell.get("avg")
        if expected is None:
            if not ausente(actual):
                raise ValueError("EPS ausente preenchido na linha")
        elif (
            ausente(actual)
            or isinstance(expected, bool)
            or not isinstance(expected, (int, float))
            or not math.isfinite(expected)
            or float(actual) not in (float(expected), float(format(expected, ".10g")))
        ):
            raise ValueError("Valor EPS contraditório com a célula HTTP")
    if (
        all(x is not None for x in cc)
        and cc[0] != cc[1]
        or all(x is not None for x in ee)
        and ee[0] >= ee[1]
    ):
        raise ValueError("Par EPS explicitamente contraditório")
    common = cc[0] if all(x is not None for x in cc) else None
    if (
        c.get("moeda_comum") != common
        or (None if ausente(row.get("moeda_estimativas")) else row.get("moeda_estimativas"))
        != common
    ):
        raise ValueError("Moeda EPS agregada contraditória")
    expected_count = cells.get("0y", {}).get("numberOfAnalysts")
    actual_count = row.get("n_analistas_eps")
    if (
        (expected_count is None and not ausente(actual_count))
        or expected_count is not None
        and (ausente(actual_count) or actual_count != expected_count)
    ):
        raise ValueError("Número de analistas EPS contraditório com a célula HTTP")
    return c


def autenticar_linha(row, raiz) -> dict | None:
    """Reabre somente bytes públicos locais; contexto isolado não autentica documento."""
    c = contexto_da_linha(row)
    if c is None:
        return None
    if raiz is None:
        raise ValueError("EPS tipado exige Arquivo público físico para autenticar o corpo")
    try:
        cut = datetime.fromisoformat(c.get("disponivel_desde", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("Disponibilidade EPS inválida") from exc
    if cut.tzinfo is None or cut.utcoffset() is None:
        raise ValueError("Disponibilidade EPS sem fuso")
    a = Arquivo(raiz, offline=True, conhecimento_ate=cut)
    reg = a.por_sha(c["corpo_sha256"])
    if reg is None:
        raise ValueError("Corpo HTTP EPS ausente do Arquivo no consumo tipado")
    _, extra = consenso_do_registro(a.ler(reg), c["ticker"], reg, conhecimento_ate=cut)
    if json.loads(extra["eps_contexto"]) != c:
        raise ValueError("Contexto EPS diverge do corpo/recibo nativo recebido")
    return c


__all__ = [
    "COLUNAS",
    "autenticar_linha",
    "consenso_do_registro",
    "contexto_da_linha",
    "identidade",
    "ler_corpo",
]
