"""SEC EDGAR: ``companyfacts`` (XBRL, us-gaap e ifrs-full) → itens canônicos; mapa ticker → CIK.

- ``https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`` (``User-Agent`` descritivo;
  ``SEC_USER_AGENT`` define o contato; limite global ≤ 8 req/s).
- Cada fato traz ``filed`` (data do arquivamento) ⇒ ``received_date``; reapresentações em
  arquivos posteriores viram novas versões com a data do novo arquivo (sem look-ahead).
- Moeda **por arquivo** (``accn``): a unidade monetária predominante nos fatos do próprio
  arquivo (ativo, receita e PL pesam mais; traduções de conveniência ficam de fora). Quem muda a
  moeda de apresentação (ex.: ARS → USD, MXN → USD, CAD → USD) tem cada arquivo na sua moeda; o
  motor PIT usa só a moeda vigente em ``as_of`` (:func:`.publico_fatos.selecionar_pit`). Ações em
  ``shares``; a contagem da capa (``dei``, data da capa) vai para a data-base do arquivo, com a
  data da capa em ``nota``. Emissores em ARS (IAS 29): ``nota`` registra a data-base do arquivo
  (unidade de medida corrente daquela data). Sinais normalizados para a convenção da CVM: despesas negativas
  (``ir_csll``, ``despesa_pdd``); ``d_a``, ``capex``, ``dividendos_pagos`` e ``recompras`` em
  módulo (saída de caixa positiva).
- Mapa ticker → CIK: ``company_tickers_exchange.json`` (exige contato no ``User-Agent``); sem
  ele, índice de entidades do EDGAR (``efts.sec.gov``) só para os tickers do universo,
  correspondência EXATA.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping

import pandas as pd

from .fundamentals_pit import _CCY_UNIT, _sec_candidate_frame
from .publico_cvm import FATO_COLUNAS
from .security_master import format_cik

URL_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
URL_TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
URL_EFTS = "https://efts.sec.gov/LATEST/search-index?keysTyped={q}"
FORMULARIOS = frozenset({
    "10-K", "10-K/A", "10-KT", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A",
    "6-K", "6-K/A", "8-K",
})
ANUAIS = frozenset({"10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A"})

_I, _U, _D = "ifrs-full", "us-gaap", "dei"

TAGS: dict[str, list[tuple[tuple[str, str], ...]]] = {
    "receita": [((_I, "Revenue"),), ((_I, "RevenueFromContractsWithCustomers"),),
                ((_U, "Revenues"),), ((_U, "RevenueFromContractWithCustomerExcludingAssessedTax"),),
                ((_U, "SalesRevenueNet"),)],
    "lucro_bruto": [((_I, "GrossProfit"),), ((_U, "GrossProfit"),)],
    "ebit": [((_I, "ProfitLossFromOperatingActivities"),), ((_U, "OperatingIncomeLoss"),)],
    "d_a": [((_I, "DepreciationAndAmortisationExpense"),),
            ((_I, "AdjustmentsForDepreciationAndAmortisationExpense"),),
            ((_I, "DepreciationExpense"), (_I, "AmortisationExpense")),
            ((_U, "DepreciationDepletionAndAmortization"),),
            ((_U, "DepreciationAndAmortization"),),
            ((_U, "DepreciationAmortizationAndAccretionNet"),),
            ((_I, "DepreciationPropertyPlantAndEquipment"),
             (_I, "AmortisationIntangibleAssetsOtherThanGoodwill")),
            ((_I, "DepreciationPropertyPlantAndEquipment"),),
            ((_I, "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"),)],
    "resultado_financeiro": [((_I, "FinanceIncomeCost"),),
                             ((_U, "InterestIncomeExpenseNonoperatingNet"),)],
    "lucro_antes_ir": [
        ((_I, "ProfitLossBeforeTax"),),
        ((_U, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"),),
        ((_U, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),)],
    "ir_csll": [((_I, "IncomeTaxExpenseContinuingOperations"),), ((_U, "IncomeTaxExpenseBenefit"),)],
    "lucro_liquido": [((_I, "ProfitLoss"),), ((_U, "ProfitLoss"),), ((_U, "NetIncomeLoss"),)],
    "lucro_liquido_controladores": [((_I, "ProfitLossAttributableToOwnersOfParent"),),
                                    ((_U, "NetIncomeLoss"),)],
    "cfo": [((_I, "CashFlowsFromUsedInOperatingActivities"),),
            ((_U, "NetCashProvidedByUsedInOperatingActivities"),),
            ((_U, "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),)],
    "capex": [((_I, "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),
               (_I, "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities")),
              ((_I, "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets"),),
              ((_I, "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"),),
              ((_U, "PaymentsToAcquirePropertyPlantAndEquipment"),
               (_U, "PaymentsToAcquireIntangibleAssets")),
              ((_U, "PaymentsToAcquirePropertyPlantAndEquipment"),),
              ((_U, "PaymentsToAcquireProductiveAssets"),),
              ((_I, "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities"),)],
    "dividendos_pagos": [((_I, "DividendsPaidClassifiedAsFinancingActivities"),),
                         ((_I, "DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities"),),
                         ((_I, "DividendsPaid"),),
                         ((_U, "PaymentsOfDividendsCommonStock"),), ((_U, "PaymentsOfDividends"),)],
    "recompras": [((_I, "PaymentsToAcquireOrRedeemEntitysShares"),),
                  ((_U, "PaymentsForRepurchaseOfCommonStock"),)],
    "caixa": [((_I, "CashAndCashEquivalents"),), ((_U, "CashAndCashEquivalentsAtCarryingValue"),)],
    "aplicacoes_cp": [((_I, "CurrentInvestments"),), ((_U, "ShortTermInvestments"),),
                      ((_U, "MarketableSecuritiesCurrent"),)],
    "divida_bruta": [((_I, "Borrowings"),),
                     ((_I, "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings"),
                      (_I, "NoncurrentPortionOfNoncurrentBorrowings")),
                     ((_I, "ShorttermBorrowings"), (_I, "LongtermBorrowings")),
                     ((_U, "LongTermDebt"),),
                     ((_U, "LongTermDebtCurrent"), (_U, "LongTermDebtNoncurrent"))],
    "arrendamentos": [((_I, "LeaseLiabilities"),),
                      ((_I, "CurrentLeaseLiabilities"), (_I, "NoncurrentLeaseLiabilities")),
                      ((_U, "OperatingLeaseLiability"), (_U, "FinanceLeaseLiability")),
                      ((_U, "OperatingLeaseLiability"),)],
    "patrimonio_liquido": [((_I, "Equity"),),
                           ((_U, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),),
                           ((_U, "StockholdersEquity"),)],
    "patrimonio_controladores": [((_I, "EquityAttributableToOwnersOfParent"),),
                                 ((_U, "StockholdersEquity"),)],
    "participacao_minoritarios": [((_I, "NoncontrollingInterests"),), ((_U, "MinorityInterest"),)],
    "ativo_total": [((_I, "Assets"),), ((_U, "Assets"),)],
    "acoes_emitidas": [((_I, "NumberOfSharesIssued"),), ((_U, "CommonStockSharesIssued"),)],
    "acoes_tesouraria": [((_U, "TreasuryStockShares"),), ((_U, "TreasuryStockCommonShares"),)],
    "acoes_em_circulacao": [((_D, "EntityCommonStockSharesOutstanding"),),
                            ((_I, "NumberOfSharesOutstanding"),),
                            ((_U, "CommonStockSharesOutstanding"),)],
    "carteira_credito": [((_I, "LoansAndAdvancesToCustomers"),),
                         ((_U, "LoansAndLeasesReceivableNetReportedAmount"),),
                         ((_U, "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss"),)],
    "provisao_credito": [((_I, "AllowanceAccountForCreditLossesOfFinancialAssets"),),
                         ((_U, "FinancingReceivableAllowanceForCreditLosses"),),
                         ((_U, "AllowanceForLoanAndLeaseLosses"),)],
    "margem_financeira": [((_I, "InterestRevenueExpense"),), ((_U, "InterestIncomeExpenseNet"),)],
    "receita_servicos": [((_I, "FeeAndCommissionIncome"),), ((_U, "FeesAndCommissions"),)],
    "despesa_pdd": [((_I, "ImpairmentLossImpairmentGainAndReversalOfImpairmentLossDeterminedInAccordanceWithIFRS9"),),
                    ((_U, "ProvisionForLoanLeaseAndOtherLosses"),),
                    ((_U, "ProvisionForLoanAndLeaseLosses"),)],
}
FLUXO_SEC = frozenset({
    "receita", "lucro_bruto", "ebit", "d_a", "resultado_financeiro", "lucro_antes_ir", "ir_csll",
    "lucro_liquido", "lucro_liquido_controladores", "cfo", "capex", "dividendos_pagos",
    "recompras", "margem_financeira", "receita_servicos", "despesa_pdd",
})
ACOES = frozenset({"acoes_emitidas", "acoes_tesouraria", "acoes_em_circulacao"})
NEGAR = frozenset({"ir_csll", "despesa_pdd"})
MODULO = frozenset({"d_a", "capex", "dividendos_pagos", "recompras", "provisao_credito"})
DEMONSTRATIVO = {i: ("DFC" if i in {"cfo", "capex", "dividendos_pagos", "recompras"}
                     else "DRE" if i in FLUXO_SEC else "BP") for i in TAGS}
MAIOR_TOTAL = frozenset({"receita", "divida_bruta"})
"""Itens em que a tag "de maior prioridade" às vezes é um fato parcial (nota explicativa,
só uma parcela da dívida): entre as tags candidatas do mesmo período e arquivo vale o MAIOR
total (ex.: JBS 2025 ``Borrowings`` 191 mi × curto + longo prazo 21,1 bi)."""
RECEITA_MIN_ATIVO = 0.001
"""Receita anualizada < 0,1% do ativo total do mesmo período ⇒ fato parcial (ex.: receita de
contratos com clientes de um banco); descartada (ausente)."""
_TAGS_CHAVE = frozenset({"Assets", "Revenue", "Revenues", "Equity", "StockholdersEquity",
                         "ProfitLoss", "NetIncomeLoss"})


def validar_companyfacts(conteudo: bytes, cik10: str | None = None) -> dict:
    obj = json.loads(conteudo)
    if not isinstance(obj, dict) or not isinstance(obj.get("facts", {}), dict):
        raise ValueError("companyfacts com formato inesperado.")
    got = format_cik(obj.get("cik"))
    if cik10 is not None and got is not None and got != cik10:
        raise ValueError(f"companyfacts do CIK {got} recebido para o CIK {cik10}.")
    return obj


def url_filing(cik10: str, accn: str | None) -> str | None:
    if not accn:
        return None
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/"
            f"{str(accn).replace('-', '')}/")


def arquivos_sec(facts: Mapping) -> tuple[dict[str, str], dict[str, pd.Timestamp]]:
    """Por arquivo (``accn``): moeda de apresentação e data-base.

    Moeda = unidade monetária ISO mais frequente nos fatos ``ifrs-full``/``us-gaap`` do
    arquivo (tags-chave — ativo, receita, PL, lucro — pesam 10×; traduções de conveniência em
    USD ao lado da moeda funcional ficam em minoria). Data-base = o maior ``end`` dos fatos-chave
    do arquivo (senão o ``end`` mais frequente)."""
    from collections import Counter

    moedas: dict[str, Counter] = {}
    fins_chave: dict[str, str] = {}
    fins: dict[str, Counter] = {}
    for tax in (_I, _U):
        for tag, node in (facts.get(tax) or {}).items():
            chave = tag in _TAGS_CHAVE
            for unit, entries in (node.get("units") or {}).items():
                ccy = bool(_CCY_UNIT.match(unit))
                for e in entries:
                    accn, end = e.get("accn"), e.get("end")
                    if not accn or not end:
                        continue
                    if ccy:
                        moedas.setdefault(accn, Counter())[unit] += 10 if chave else 1
                    if chave:
                        fins_chave[accn] = max(fins_chave.get(accn, end), end)
                    fins.setdefault(accn, Counter())[end] += 1
    moeda = {a: sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
             for a, c in moedas.items()}
    data_base = {a: pd.Timestamp(fins_chave.get(a) or c.most_common(1)[0][0])
                 for a, c in fins.items()}
    return moeda, data_base


def _walk(df: pd.DataFrame) -> list[dict]:
    """Versões PIT por (início, fim): em ordem de ``filed``, só a melhor tag vista até então."""
    out: list[dict] = []
    df = (df.sort_values(["start_k", "end", "filed", "priority", "accn"])
          .drop_duplicates(["start_k", "end", "filed"], keep="first"))
    for _, g in df.groupby(["start_k", "end"], sort=False):
        best = math.inf
        last: float | None = None
        ver = 0
        for r in g.itertuples(index=False):
            if r.priority > best:
                continue
            best = r.priority
            if last is not None and math.isclose(r.val, last, rel_tol=1e-12, abs_tol=1e-9):
                continue
            ver += 1
            last = r.val
            out.append({"start_k": r.start_k, "end": r.end, "val": float(r.val),
                        "filed": r.filed, "version": ver, "form": r.form, "accn": r.accn,
                        "tag": r.tag, "unit": getattr(r, "unit", None)})
    return out


def _nota_ars(moeda: str | None, accn: str | None, form: str,
              data_base: Mapping[str, pd.Timestamp]) -> str | None:
    """IAS 29 (economia hiperinflacionária): valores na moeda de poder aquisitivo da data-base
    do arquivo que os publicou — períodos de arquivos diferentes não são comparáveis sem
    reexpressão."""
    if moeda != "ARS" or not accn or accn not in data_base:
        return None
    return (f"IAS 29: ARS em moeda de poder aquisitivo de {data_base[accn].date().isoformat()} "
            f"({form or 'XBRL'} {accn})")


FATO_SEC_COLUNAS = [*FATO_COLUNAS, "nota"]


def fatos_sec(companyfacts: Mapping) -> pd.DataFrame:
    """Fatos canônicos (``FATO_COLUNAS`` + ``nota``; ``entidade`` = CIK de 10 dígitos)."""
    facts = companyfacts.get("facts", {}) if companyfacts else {}
    cik = format_cik(companyfacts.get("cik")) if companyfacts else None
    moeda_arq, data_base = arquivos_sec(facts)
    rows: list[dict] = []
    for item, cands in TAGS.items():
        is_sh = item in ACOES
        flow = item in FLUXO_SEC

        def unit_ok(u: str, is_sh: bool = is_sh) -> bool:
            return u == "shares" if is_sh else bool(_CCY_UNIT.match(u))

        frames = []
        for prio, cand in enumerate(cands):
            df = _sec_candidate_frame(facts, cand, flow, unit_ok)
            if df.empty:
                continue
            if not is_sh:  # só a moeda de apresentação do próprio arquivo
                df = df[df["unit"] == df["accn"].map(moeda_arq)]
            if "form" not in df.columns:
                df = df.assign(form="")
            df = df[df["form"].fillna("").isin(FORMULARIOS) | (df["form"].fillna("") == "")]
            if flow:
                dur = (df["end"] - df["start"]).dt.days + 1
                df = df[dur.between(80, 380)]
            if is_sh:
                df = df[df["val"] > 0]
                if cand[0][0] == _D and not df.empty:
                    # contagem da capa: vai para a data-base do arquivo (a data da capa fica
                    # registrada) — alinha a contagem anual com o exercício
                    base = df["accn"].map(data_base)
                    df = df.assign(capa=df["end"], end=base.where(base.notna(), df["end"]))
                df = (df.groupby(["end", "filed", "accn"], as_index=False, dropna=False)
                      .agg(val=("val", lambda s: float(pd.Series(s).drop_duplicates().sum())),
                           unit=("unit", "first"), start=("start", "first"),
                           form=("form", "first"),
                           capa=("capa", "first") if "capa" in df.columns else ("end", "first")))
                if cand[0][0] != _D:
                    df["capa"] = pd.NaT
            if df.empty:
                continue
            frames.append(df.assign(priority=prio, tag="+".join(t for _, t in cand)))
        if not frames:
            continue
        allc = pd.concat(frames, ignore_index=True)
        if item in MAIOR_TOTAL:
            # maior total entre as tags candidatas do mesmo período e arquivo
            allc = (allc.sort_values("val", ascending=False, kind="stable")
                    .drop_duplicates(["start", "end", "filed", "accn"], keep="first")
                    .assign(priority=0))
        allc["start_k"] = allc["start"].fillna(pd.Timestamp(0)) if flow else pd.Timestamp(0)
        allc["form"] = allc["form"].fillna("")
        capa = (allc.dropna(subset=["capa"]).set_index(["end", "filed", "accn"])["capa"]
                if "capa" in allc.columns else pd.Series(dtype="datetime64[ns]"))
        for r in _walk(allc):
            v = r["val"]
            if item in NEGAR:
                v = -v
            if item in MODULO:
                v = abs(v)
            start = r["start_k"] if flow and r["start_k"] != pd.Timestamp(0) else pd.NaT
            moeda = None if is_sh else r["unit"]
            nota = _nota_ars(moeda, r["accn"], r["form"], data_base)
            k = (r["end"], r["filed"], r["accn"])
            if is_sh and k in capa.index and pd.notna(capa.loc[k]) and capa.loc[k] != r["end"]:
                nota = f"contagem na data da capa ({pd.Timestamp(capa.loc[k]).date().isoformat()})"
            rows.append({
                "entidade": cik, "demonstrativo": DEMONSTRATIVO[item], "item": item,
                "period_start": start, "period_end": r["end"], "value": v,
                "currency": moeda, "received_date": r["filed"],
                "version": int(r["version"]),
                "documento": f"SEC {r['form'] or 'XBRL'} {r['accn'] or ''} ({r['tag']})".strip(),
                "url": url_filing(cik, r["accn"]) if cik else None,
                "consolidado": True, "anual": r["form"] in ANUAIS, "nota": nota,
            })
    if not any(r["item"] == "resultado_financeiro" for r in rows):
        rows.extend(_resultado_financeiro(facts, cik, moeda_arq, data_base))
    if not rows:
        return pd.DataFrame(columns=FATO_SEC_COLUNAS)
    out = pd.DataFrame(rows, columns=FATO_SEC_COLUNAS)
    for c in ("period_start", "period_end", "received_date"):
        out[c] = pd.to_datetime(out[c])
    return _receita_plausivel(out)


def _receita_plausivel(f: pd.DataFrame) -> pd.DataFrame:
    """Descarta receita anualizada < ``RECEITA_MIN_ATIVO`` × ativo total do mesmo período e
    arquivo (fato parcial de nota explicativa)."""
    rec = f[f["item"] == "receita"]
    at = f[f["item"] == "ativo_total"]
    if rec.empty or at.empty:
        return f
    ativo = at.sort_values("received_date").drop_duplicates(["period_end", "currency"],
                                                             keep="last")
    ativo = ativo.set_index(["period_end", "currency"])["value"]
    dur = ((rec["period_end"] - rec["period_start"]).dt.days + 1).clip(lower=1)
    anual = rec["value"] * 365.0 / dur
    ref = pd.Series([ativo.get((e, c), float("nan")) for e, c in
                     zip(rec["period_end"], rec["currency"], strict=True)], index=rec.index)
    ruim = ref.notna() & (anual.abs() < RECEITA_MIN_ATIVO * ref)
    return f.drop(index=ruim[ruim].index).reset_index(drop=True)


def _resultado_financeiro(facts: Mapping, cik: str | None, moeda_arq: Mapping[str, str],
                          data_base: Mapping[str, pd.Timestamp]) -> list[dict]:
    """``FinanceIncome − FinanceCosts`` (ifrs-full) no mesmo período e arquivo."""
    def ok(u: str) -> bool:
        return bool(_CCY_UNIT.match(u))

    inc = _sec_candidate_frame(facts, ((_I, "FinanceIncome"),), True, ok)
    cus = _sec_candidate_frame(facts, ((_I, "FinanceCosts"),), True, ok)
    if inc.empty or cus.empty:
        return []
    inc = inc[inc["unit"] == inc["accn"].map(moeda_arq)]
    cus = cus[cus["unit"] == cus["accn"].map(moeda_arq)]
    k = ["start", "end", "filed", "accn", "unit"]
    m = (inc.dropna(subset=["start"]).drop_duplicates(k)[k + ["val", "form"]]
         .merge(cus.dropna(subset=["start"]).drop_duplicates(k)[k + ["val"]], on=k,
                suffixes=("", "_c")))
    m = m[((m["end"] - m["start"]).dt.days + 1).between(80, 380)]
    if m.empty:
        return []
    m = m.assign(val=m["val"] - m["val_c"].abs(), start_k=m["start"], priority=0,
                 tag="FinanceIncome-FinanceCosts")
    m["form"] = m["form"].fillna("")
    out = []
    for r in _walk(m):
        out.append({"entidade": cik, "demonstrativo": "DRE", "item": "resultado_financeiro",
                    "period_start": r["start_k"], "period_end": r["end"], "value": r["val"],
                    "currency": r["unit"], "received_date": r["filed"],
                    "version": int(r["version"]),
                    "documento": f"SEC {r['form'] or 'XBRL'} {r['accn'] or ''} ({r['tag']})".strip(),
                    "url": url_filing(cik, r["accn"]) if cik else None, "consolidado": True,
                    "anual": r["form"] in ANUAIS,
                    "nota": _nota_ars(r["unit"], r["accn"], r["form"], data_base)})
    return out


def parse_efts(conteudo: bytes, ticker: str) -> dict | None:
    """``{"cik", "nome", "ticker"}`` com correspondência EXATA do ticker; senão ``None``."""
    payload = json.loads(conteudo)
    alvo = ticker.upper().strip()
    for hit in payload.get("hits", {}).get("hits", []):
        src = hit.get("_source", {})
        listed = [t.strip().upper() for t in str(src.get("tickers", "")).split(",")]
        if alvo in listed:
            return {"cik": format_cik(hit.get("_id")), "nome": str(src.get("entity", "")),
                    "ticker": alvo}
    return None


def parse_company_tickers(conteudo: bytes) -> dict[str, str]:
    obj = json.loads(conteudo)
    fields = list(obj.get("fields", []))
    out: dict[str, str] = {}
    if "ticker" not in fields or "cik" not in fields:
        raise ValueError("company_tickers_exchange.json sem campos ticker/cik.")
    it, ic = fields.index("ticker"), fields.index("cik")
    for row in obj.get("data", []):
        c = format_cik(row[ic])
        if c:
            out[str(row[it]).upper().strip()] = c
    return out


def sec_ticker(yahoo_ticker: str) -> str:
    """Ticker da SEC a partir do ticker Yahoo (``BRK-B`` → ``BRK-B``; ``PBR-A`` → ``PBR-A``)."""
    return str(yahoo_ticker).upper().strip()


def validar_efts(conteudo: bytes) -> None:
    """Resposta do índice de entidades do EDGAR: JSON com ``hits.hits`` (página de erro ou de
    limite de requisições nunca é arquivada)."""
    obj = json.loads(conteudo)
    hits = obj.get("hits") if isinstance(obj, dict) else None
    if not isinstance(hits, dict) or not isinstance(hits.get("hits"), list):
        raise ValueError("Resposta do índice de entidades da SEC sem 'hits.hits'.")


__all__ = [
    "ANUAIS", "FATO_SEC_COLUNAS", "TAGS", "URL_COMPANYFACTS", "URL_EFTS", "URL_TICKERS",
    "arquivos_sec", "fatos_sec", "parse_company_tickers", "parse_efts", "sec_ticker",
    "url_filing", "validar_companyfacts", "validar_efts",
]
