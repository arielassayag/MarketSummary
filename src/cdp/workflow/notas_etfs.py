"""Entrada de pesquisa de ETFs, somente a partir de um retrato conferido da cobertura."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from ..contracts import FactBook


def alvos(snap: Any) -> dict[str, dict[str, str]]:
    """Metadados para a fila; nenhum cadastro presume existência de modelo recebido."""
    if snap is None:
        return {}
    out = {}
    for iid in snap.etfs().index:
        m = snap.etf(str(iid))
        if (not m or m.get("iid") != iid or not re.fullmatch(r"ETF_[A-Z0-9_]{1,60}", str(iid))
                or str(m.get("ticker", "")).split(".")[0] != str(iid).removeprefix("ETF_")):
            raise ValueError("Identidade de ETF incompatível com o retrato de cobertura.")
        if date.fromisoformat(m["as_of"]) > snap.as_of:
            raise ValueError("Modelo de ETF posterior ao retrato de cobertura.")
        out[str(iid)] = {"issuer_name": str(m["nome"]), "country": str(m["pais"]),
                         "gics_sector": "ETF"}
    return out


def entradas(rt: Any, md: Any, snap: Any, iid: str, d: date) -> tuple[FactBook, Any]:
    """Fatos e contexto do produto; não aplica contabilidade de empresa a um fundo de índice."""
    from ..research.factbook import NA_TEXT, _Builder, _num, _val_preco, fatos_etf
    from ..research.notas import ContextoNota, termos_permitidos, ticker_roots
    from .notas import previous_note
    from .tese_analise import country_label

    if snap is None or iid not in alvos(snap):
        raise ValueError(f"ETF sem modelo conferido de cobertura: {iid}.")
    m = snap.etf(iid)
    if md.as_of > d or snap.as_of > d or date.fromisoformat(m["as_of"]) > d:
        raise ValueError("Dados ou modelo do ETF posteriores ao corte da nota.")
    ticker = str(m["ticker"]).split(".")[0]
    k = "etf." + ticker
    src = [f"cobertura/{m['as_of']}/etfs/{iid}.json"]
    b = _Builder()
    preco = _num(m.get("preco"))
    b.add(k + ".preco", None, "Preço de referência do ETF", preco, "preco",
          "fechamento público na moeda da linha", src, point_in_time=False,
          formatted=_val_preco(preco, m.get("moeda")) if preco is not None else NA_TEXT)
    b.add(k + ".ter", None, "Taxa de administração declarada no retrato", m.get("ter"),
          "pct", "parâmetro público do produto; não inclui todos os custos de negociação",
          src, point_in_time=False)
    # O retrato recebido não comprova posse histórica de todos os documentos do produto.
    fatos = {fid: f.model_copy(update={"point_in_time": False}) for fid, f in fatos_etf(m).items()}
    fatos.update(b.facts)
    fb = FactBook(as_of=md.as_of, snapshot_id=f"{md.manifest.snapshot_id}:etf:{iid}:{snap.manifest_sha256}",
                  facts=fatos, is_synthetic=bool(md.is_synthetic or snap.is_synthetic or m.get("is_synthetic")))
    nome = str(m["nome"])
    tickers = tuple(ticker_roots([str(m["ticker"])]))
    composicao = m.get("fonte_composicao") or {}
    lacunas = [str(x) for x in m.get("lacunas") or []]
    lacunas += ["Prospecto, regras de replicação e aderência ao índice exigem pesquisa específica.",
                "Spread, prêmio ou desconto ao patrimônio e custos totais não são presumidos."]
    ctx = ContextoNota(
        issuer_id=iid, nome=nome, pais=str(m["pais"]), pais_pt=country_label(str(m["pais"])),
        setor="ETF", setor_pt="Fundo de índice", data=d, dados_ate=md.as_of,
        is_synthetic=fb.is_synthetic, nomes={iid: nome}, termos=termos_permitidos({iid: nome}, tickers),
        tickers=tickers, nota_anterior=previous_note(rt.book_root, iid, d),
        snapshot={"as_of": snap.as_of.isoformat(), "manifest_sha256": snap.manifest_sha256,
                  "modelo_as_of": str(m["as_of"]), "tipo_ativo": "etf", "indice": str(m["indice"]),
                  "ticker": str(m["ticker"]), "url_produto": composicao.get("url")},
        lacunas=tuple(lacunas), proximo_resultado=None)
    return fb, ctx
