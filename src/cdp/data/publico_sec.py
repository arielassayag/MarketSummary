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

import hashlib
import io
import json
import math
import re
import zipfile
from collections.abc import Mapping
from datetime import date
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import pandas as pd

from .fundamentals_pit import _CCY_UNIT, _sec_candidate_frame
from .publico_cvm import FATO_COLUNAS
from .security_master import format_cik

URL_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
URL_TICKERS = "https://www.sec.gov/files/company_tickers_exchange.json"
URL_EFTS = "https://efts.sec.gov/LATEST/search-index?keysTyped={q}"
URL_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
CATALOGO_RI = Path(__file__).resolve().parents[3] / "configs/cdp/sec_ri_xbrl.json"
CATALOGO_CLASSES = Path(__file__).resolve().parents[3] / "configs/cdp/sec_classes_acoes.json"
CATALOGO_FLUXOS = Path(__file__).resolve().parents[3] / "configs/cdp/sec_fluxos_html.json"
FORMULARIOS = frozenset({
    "10-K", "10-K/A", "10-KT", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A",
    "6-K", "6-K/A", "8-K",
})
ANUAIS = frozenset({"10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A"})


def documentos_fluxos_sec(cik10: str, as_of: date) -> list[dict]:
    """Notas sem XBRL catalogadas, com datas/entidade conferidas em submissions."""
    if not CATALOGO_FLUXOS.exists():
        return []
    catalogo = json.loads(CATALOGO_FLUXOS.read_text(encoding="utf-8"))
    if catalogo.get("schema") != "cdp.sec_fluxos_html/v1":
        raise ValueError("catálogo de notas SEC: schema desconhecido")
    return [d for d in catalogo["documentos"] if d["cik"] == cik10
            and date.fromisoformat(d["filed"]) <= as_of]


def fatos_fluxos_documento(conteudo: bytes, entidade: str, catalogado: dict,
                           arquivamento: dict) -> pd.DataFrame:
    """Exige SHA e metadados do documento primário oficial; não infere data pelo nome."""
    from .publico_fluxos import fatos_fluxos_html

    if hashlib.sha256(conteudo).hexdigest() != catalogado["sha256"]:
        raise ValueError("notas SEC: SHA-256 diferente do catálogo")
    for chave in ("accn", "form", "documento"):
        if str(arquivamento[chave]) != catalogado[chave]:
            raise ValueError("notas SEC: metadados de arquivamento divergentes")
    for chave in ("filed", "period_end"):
        if pd.Timestamp(arquivamento[chave]) != pd.Timestamp(catalogado[chave]):
            raise ValueError("notas SEC: datas de arquivamento divergentes")
    url = url_filing(catalogado["cik"], catalogado["accn"]) + catalogado["documento"]
    if catalogado["url"] != url or arquivamento["url"] != url:
        raise ValueError("notas SEC: URL fora do documento primário do CIK")
    fatos = fatos_fluxos_html(conteudo, entidade, documento=catalogado["documento"], url=url,
                             data_publicacao=date.fromisoformat(catalogado["filed"]),
                             data_referencia=date.fromisoformat(catalogado["period_end"]))
    f = pd.DataFrame(fatos, columns=[*FATO_COLUNAS, "nota"])
    if not f.empty:
        f["period_start"] = pd.to_datetime(f["period_start"])
        f["period_end"] = pd.to_datetime(f["period_end"])
        f["received_date"] = pd.to_datetime(f["received_date"])
        f["anual"] = (f["period_end"] - f["period_start"]).dt.days.add(1).between(350, 380)
        f["pit_estimado"] = False
    return f

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
    "d_a_dfc": [((_I, "AdjustmentsForDepreciationAndAmortisationExpense"),),
                 ((_I, "AdjustmentsForDepreciationExpense"), (_I, "AdjustmentsForAmortisationExpense"))],
    "adicoes_direito_uso": [((_I, "AdditionsToRightofuseAssets"),)],
    "depreciacao_direito_uso": [((_I, "DepreciationRightofuseAssets"),)],
    "juros_pagos_operacionais": [((_I, "InterestPaidClassifiedAsOperatingActivities"),)],
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
    "arrendamentos_pagos": [((_I, "PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities"),),
                            ((_U, "FinanceLeasePrincipalPayments"),)],
    "patrimonio_liquido": [((_I, "Equity"),),
                           ((_U, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),),
                           ((_U, "StockholdersEquity"),)],
    "patrimonio_controladores": [((_I, "EquityAttributableToOwnersOfParent"),),
                                 ((_U, "StockholdersEquity"),)],
    "participacao_minoritarios": [((_I, "NoncontrollingInterests"),), ((_U, "MinorityInterest"),)],
    "ativo_total": [((_I, "Assets"),), ((_U, "Assets"),)],
    "acoes_emitidas": [((_I, "NumberOfSharesIssued"),),
                       ((_I, "NumberOfSharesIssuedAndFullyPaid"),),
                       ((_U, "CommonStockSharesIssued"),)],
    "acoes_tesouraria": [((_I, "TreasuryShares"),), ((_U, "TreasuryStockShares"),),
                         ((_U, "TreasuryStockCommonShares"),)],
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
    "d_a_dfc", "adicoes_direito_uso", "depreciacao_direito_uso",
    "variacao_capital_giro_operacional", "juros_pagos_operacionais",
    "recompras", "margem_financeira", "receita_servicos", "despesa_pdd",
    "arrendamentos_pagos",
})
ACOES = frozenset({"acoes_emitidas", "acoes_tesouraria", "acoes_em_circulacao"})
NEGAR = frozenset({"ir_csll", "despesa_pdd"})
MODULO = frozenset({"d_a", "depreciacao_direito_uso",
                   "juros_pagos_operacionais", "capex", "dividendos_pagos", "recompras", "provisao_credito",
                   "arrendamentos_pagos"})
DEMONSTRATIVO = {i: ("DFC" if i in {"cfo", "capex", "dividendos_pagos", "recompras",
                                   "arrendamentos_pagos"}
                     | {"d_a_dfc", "adicoes_direito_uso", "depreciacao_direito_uso",
                        "variacao_capital_giro_operacional", "juros_pagos_operacionais"}
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


ARQUIVAMENTOS_COLUNAS = ["accn", "form", "filed", "period_end", "documento", "url", "xbrl"]


def instancia_sec(conteudo: bytes, cik10: str, arquivamento: Mapping) -> str | None:
    """Instância extraída que corresponde ao documento principal no índice oficial SEC.

    O HTML inline e o XML extraído são recursos distintos: a SEC pode recusar um e fornecer
    o outro. Nunca escolhe o primeiro XML do diretório (pode ser um linkbase ou outro anexo),
    nem fabrica a existência de um recurso por convenção de nome. A origem e o tamanho
    declarados no índice são conferidos antes de retornar o endereço público.
    """
    obj = json.loads(conteudo)
    diretorio = obj.get("directory") if isinstance(obj, dict) else None
    base = url_filing(cik10, arquivamento.get("accn"))
    if not base or not isinstance(diretorio, dict) or not isinstance(diretorio.get("item"), list):
        raise ValueError("Índice do documento SEC com formato inesperado")
    if str(diretorio.get("name", "")).rstrip("/") != urlparse(base).path.rstrip("/"):
        raise ValueError("Índice do documento SEC pertence a outro CIK ou accession")
    principal = str(arquivamento.get("documento", ""))
    p = PurePosixPath(principal)
    if p.name != principal or p.suffix.lower() not in {".htm", ".html", ".xhtml"}:
        return None
    esperado = p.stem + "_" + p.suffix[1:] + ".xml"
    encontrados = [i for i in diretorio["item"] if isinstance(i, dict)
                   and i.get("name") == esperado]
    if len(encontrados) > 1:
        raise ValueError("Instância XBRL duplicada no índice do documento SEC")
    if not encontrados:
        return None
    try:
        tamanho = int(encontrados[0]["size"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Tamanho da instância XBRL SEC ausente ou inválido") from exc
    if not 0 < tamanho <= 50_000_000:
        raise ValueError("Instância XBRL SEC vazia ou acima do limite")
    return base + esperado


def documento_ri(cik10: str, arquivamento: Mapping) -> dict | None:
    """Espelho público curado, vinculado ao arquivo efetivamente encontrado em submissions.
    Datas do catálogo nunca criam uma publicação: accession, formulário e ambas as datas
    devem conferir com o histórico SEC conhecido no corte da coleta.
    """
    if not CATALOGO_RI.is_file():
        return None
    obj = json.loads(CATALOGO_RI.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or obj.get("schema") != "cdp.sec_ri_xbrl/v1" or not isinstance(obj.get("documentos"), list):
        raise ValueError("catálogo RI XBRL com schema inesperado")
    for d in obj["documentos"]:
        if not isinstance(d, dict):
            raise ValueError("documento RI XBRL deve ser objeto")
        if d.get("cik") != cik10 or d.get("accn") != arquivamento.get("accn"):
            continue
        for campo in ("form", "filed", "period_end", "documento_sec"):
            origem = arquivamento.get("documento" if campo == "documento_sec" else campo)
            esperado = str(origem) if campo in {"form", "documento_sec"} else pd.Timestamp(origem).date().isoformat()
            if d.get(campo) != esperado:
                raise ValueError(f"catálogo RI diverge de submissions: {campo}")
        for campo in ("url", "pagina_ri"):
            u = urlparse(str(d.get(campo, "")))
            if u.scheme != "https" or not u.netloc or u.username or u.password:
                raise ValueError(f"URL RI inválida: {campo}")
        membro = str(d.get("membro_zip", ""))
        if membro and (PurePosixPath(membro).is_absolute() or ".." in PurePosixPath(membro).parts
                       or not membro.lower().endswith((".xml", ".htm", ".html", ".xhtml"))):
            raise ValueError("membro ZIP RI inválido")
        if not re.fullmatch(r"[0-9a-f]{64}", str(d.get("sha256", ""))):
            raise ValueError("SHA-256 RI ausente ou inválido")
        return d
    return None


def companyfacts_ri(conteudo: bytes, cik10: str, arquivamento: Mapping, documento: Mapping) -> dict:
    """Lê bytes públicos conferidos, sem extrair ZIP no disco ou escolher um XML por palpite."""
    if hashlib.sha256(conteudo).hexdigest() != documento["sha256"]:
        raise ValueError("SHA-256 do documento RI não confere com o catálogo")
    membro = documento.get("membro_zip")
    if membro:
        try:
            with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                if z.namelist().count(membro) != 1 or z.getinfo(membro).file_size > 50_000_000:
                    raise ValueError("membro XBRL RI ausente, duplicado ou acima do limite")
                conteudo = z.read(membro)
        except (zipfile.BadZipFile, KeyError, RuntimeError) as exc:
            raise ValueError("ZIP RI ilegível") from exc
    return companyfacts_documento(conteudo, cik10, arquivamento)


def validar_submissions(conteudo: bytes, cik10: str | None = None) -> dict:
    """Histórico oficial; rejeita respostas de erro e vetores desalinhados."""
    obj = json.loads(conteudo)
    if not isinstance(obj, dict):
        raise ValueError("Histórico da SEC com formato inesperado.")
    if cik10 and obj.get("cik") and format_cik(obj["cik"]) != cik10:
        raise ValueError("Histórico da SEC recebido para outro CIK.")
    rec = (obj.get("filings") or {}).get("recent", obj)
    campos = ["accessionNumber", "form", "filingDate", "reportDate", "primaryDocument"]
    if any(not isinstance(rec.get(c), list) for c in campos):
        raise ValueError("Histórico da SEC sem vetores de arquivamentos.")
    if len({len(rec[c]) for c in campos}) != 1:
        raise ValueError("Histórico da SEC com vetores desalinhados.")
    return obj


def arquivamentos_sec(submissions: Mapping, cik10: str, as_of: date) -> pd.DataFrame:
    """Datas oficiais 20-F/6-K e variantes; um arquivamento não prova resultado por si só."""
    rec = (submissions.get("filings") or {}).get("recent", submissions)
    rows = []
    forms = {"20-F", "20-F/A", "6-K", "6-K/A", "40-F", "40-F/A", "10-K", "10-Q"}
    for i, form in enumerate(rec.get("form") or []):
        if form not in forms:
            continue
        accn = rec["accessionNumber"][i]
        doc = str(rec["primaryDocument"][i])
        filed = pd.to_datetime(rec["filingDate"][i], errors="coerce")
        fim = pd.to_datetime(rec["reportDate"][i], errors="coerce")
        if pd.isna(filed) or filed.date() > as_of or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accn):
            continue
        if not doc or PurePosixPath(doc).name != doc or "?" in doc or "#" in doc:
            continue
        flags = rec.get("isXBRL") or []
        rows.append({"accn": accn, "form": form, "filed": filed, "period_end": fim,
                     "documento": doc, "url": f"{url_filing(cik10, accn)}{doc}",
                     "xbrl": i < len(flags) and str(flags[i]) == "1"})
    out = pd.DataFrame(rows, columns=ARQUIVAMENTOS_COLUNAS)
    return out.sort_values(["filed", "accn"], ascending=False).reset_index(drop=True)


def documentos_pendentes(arquivos: pd.DataFrame, fatos: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Documentos XBRL recentes sem núcleo de demonstrações na própria data-base.
    Uma contagem da capa ou um comparativo avulso não representa o balanço do arquivamento.
    """
    alvo = arquivos[arquivos["xbrl"] & arquivos["period_end"].notna()
                    & (arquivos["period_end"] <= pd.Timestamp(as_of))].copy()
    nucleo = fatos[fatos["item"].isin({"receita", "lucro_liquido", "lucro_liquido_controladores",
                                      "ativo_total", "patrimonio_liquido", "patrimonio_controladores"})
                   & (fatos["received_date"] <= pd.Timestamp(as_of))].copy()
    conhecidos = set()
    if not nucleo.empty:
        nucleo["accn"] = nucleo["documento"].str.extract(r"(\d{10}-\d{2}-\d{6})", expand=False)
        for (accn, fim), g in nucleo.groupby(["accn", "period_end"]):
            itens = set(g["item"])
            if "ativo_total" in itens and itens & {"lucro_liquido", "lucro_liquido_controladores"} \
                    and itens & {"receita", "patrimonio_liquido", "patrimonio_controladores"}:
                conhecidos.add((accn, fim))
        ult = nucleo["period_end"].max()
        anuais = nucleo[nucleo["anual"].astype(bool)]
        ult_anual = anuais["period_end"].max() if not anuais.empty else pd.NaT
        recentes = (alvo["period_end"] >= ult) | (alvo["form"].isin(ANUAIS)
                     & (pd.isna(ult_anual) | (alvo["period_end"] >= ult_anual)))
        alvo = alvo[recentes]
    cobertos = [(r.accn, r.period_end) in conhecidos for r in alvo.itertuples(index=False)]
    return alvo.loc[[not v for v in cobertos]].drop_duplicates(["form", "period_end"]).head(4)


class _CapturaInline(HTMLParser):
    """Lê recursos e fatos inline sem executar HTML nem resolver entidades externas."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes: list[ET.Element] = []
        self.stack: list[ET.Element] = []

    def handle_starttag(self, tag, attrs):
        if not self.stack and tag.rsplit(":", 1)[-1] not in {"context", "unit", "nonfraction"}:
            return
        node = ET.Element(tag, dict(attrs))
        if self.stack:
            self.stack[-1].append(node)
        else:
            self.nodes.append(node)
        if tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.stack:
            node = self.stack[-1]
            if len(node):
                node[-1].tail = (node[-1].tail or "") + data
            else:
                node.text = (node.text or "") + data


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()


def _classes_acoes(conteudo: bytes, cik10: str, arquivamento: Mapping) -> Mapping | None:
    """Classes da capa conferidas em documento específico; não generaliza nomes de classes.

    Somar apenas as classes observadas não prova que a lista esteja completa. O catálogo
    liga a enumeração integral da capa aos bytes, entidade, accession e datas do documento.
    Um documento novo ainda não conferido permanece sem essa soma, nunca recebe um palpite.
    """
    if not CATALOGO_CLASSES.is_file():
        return None
    obj = json.loads(CATALOGO_CLASSES.read_text(encoding="utf-8"))
    if obj.get("schema") != "cdp.sec_classes_acoes/v1":
        raise ValueError("Catálogo de classes SEC com schema inesperado")
    for d in obj.get("documentos", []):
        if d.get("cik") != cik10 or d.get("accn") != arquivamento.get("accn"):
            continue
        for campo in ("form", "filed", "period_end", "documento_sec"):
            origem = arquivamento.get("documento" if campo == "documento_sec" else campo)
            esperado = str(origem)[:10] if campo in {"filed", "period_end"} else origem
            if origem is None or d.get(campo) != esperado:
                raise ValueError(f"Catálogo de classes SEC diverge do documento: {campo}")
        membros = d.get("membros")
        if not isinstance(membros, list) or not membros or len(membros) != len(set(membros)) \
                or d.get("eixo") not in {"ifrs-full:ClassesOfShareCapitalAxis", "srt:StatementClassOfStockAxis"}:
            raise ValueError("Enumeração de classes SEC incompleta ou inválida")
        if hashlib.sha256(conteudo).hexdigest() != d.get("sha256"):
            # HTML inline e XML extraído têm bytes diferentes; só o conferido pode somar.
            return None
        return d
    return None


def documentos_classes_sec(arquivos: pd.DataFrame, cik10: str) -> pd.DataFrame:
    """Capa curada também é lida quando Companyfacts já contém o núcleo financeiro.

    Companyfacts pode omitir dimensões DEI das classes e oferecer uma tag IFRS de
    capital emitido com nome 'outstanding'. Só os bytes curados permitem a soma da capa.
    """
    if not CATALOGO_CLASSES.is_file():
        return arquivos.iloc[:0]
    catalogo = json.loads(CATALOGO_CLASSES.read_text(encoding="utf-8"))
    if catalogo.get("schema") != "cdp.sec_classes_acoes/v1":
        raise ValueError("Catálogo de classes SEC com schema inesperado")
    accns = {d["accn"] for d in catalogo["documentos"] if d["cik"] == cik10}
    return arquivos[arquivos["accn"].isin(accns)]


def ciks_classes_sec() -> frozenset[str]:
    """Entidades com enumeração de classes conferida, para complemento do capital CVM."""
    if not CATALOGO_CLASSES.is_file():
        return frozenset()
    catalogo = json.loads(CATALOGO_CLASSES.read_text(encoding="utf-8"))
    if catalogo.get("schema") != "cdp.sec_classes_acoes/v1":
        raise ValueError("Catálogo de classes SEC com schema inesperado")
    return frozenset(d["cik"] for d in catalogo["documentos"])


def companyfacts_documento(conteudo: bytes, cik10: str, arquivamento: Mapping) -> dict:
    """XBRL/inline do arquivo oficial em estrutura companyfacts: só totais sem dimensões,
    tags IFRS/US-GAAP/DEI, unidades explícitas e transformações numéricas conhecidas.

    Taxonomia própria, dimensão de segmento, escala desconhecida, duplicata contraditória e
    fato nulo ficam ausentes. ``filed`` vem do histórico SEC, nunca da data-base do balanço.
    """
    try:
        root = ET.fromstring(conteudo)
        nodes = list(root.iter())
    except ET.ParseError:
        parser = _CapturaInline()
        parser.feed(conteudo.decode("utf-8-sig"))
        nodes = [n for root in parser.nodes for n in root.iter()]
    classes = _classes_acoes(conteudo, cik10, arquivamento)
    contexts, units = {}, {}
    for n in nodes:
        local = _local(n.tag)
        if local == "context":
            descendants = list(n.iter())
            dims = [x for x in descendants if _local(x.tag) in {"explicitmember", "typedmember"}]
            classe = None
            if dims:
                if not classes or len(dims) != 1 or _local(dims[0].tag) != "explicitmember" \
                        or dims[0].get("dimension") != classes["eixo"] \
                        or dims[0].text not in classes["membros"]:
                    continue
                classe = dims[0].text
            campos = {_local(x.tag): (x.text or "").strip() for x in descendants}
            if format_cik(campos.get("identifier")) != cik10:
                continue
            end = campos.get("instant") or campos.get("enddate")
            if not end:
                continue
            contexts[n.get("id")] = {"end": end, "classe": classe,
                                     **({"start": campos["startdate"]} if campos.get("startdate") else {})}
        elif local == "unit":
            measures = [(x.text or "").strip().rsplit(":", 1)[-1]
                        for x in n.iter() if _local(x.tag) == "measure"]
            if len(measures) == 1 and (measures[0] == "shares" or _CCY_UNIT.fullmatch(measures[0])):
                units[n.get("id")] = measures[0]
    facts: dict = {}
    grouped: dict[tuple, set[float]] = {}
    contagens: dict[str, dict[str, set[float]]] = {}
    for n in nodes:
        attrs = {k.lower(): v for k, v in n.attrib.items()}
        context = contexts.get(attrs.get("contextref"))
        unit = units.get(attrs.get("unitref"))
        if not context or not unit or any(_local(k) == "nil" and str(v).lower() in {"true", "1"}
                                         for k, v in attrs.items()):
            continue
        fim_report = arquivamento.get("period_end")
        if unit != "shares" and fim_report is not None and pd.Timestamp(context["end"]) > pd.Timestamp(fim_report):
            continue
        name = attrs.get("name", n.tag)
        if name.startswith("{"):
            ns, tag = name[1:].split("}", 1)
            tax = "ifrs-full" if "ifrs.org" in ns else "us-gaap" if "/us-gaap/" in ns else "dei"
            if tax == "dei" and "/dei/" not in ns:
                continue
        elif ":" in name:
            tax, tag = name.split(":", 1)
        else:
            continue
        if tax not in {_I, _U, _D}:
            continue
        if context["classe"] and (tax != _D or tag != "EntityCommonStockSharesOutstanding"
                                  or unit != "shares" or context.get("start")):
            continue
        raw = "".join(n.itertext()).replace("\u00a0", "").strip()
        fmt = attrs.get("format", "").rsplit(":", 1)[-1].replace("-", "").lower()
        if fmt in {"numdotdecimal", "numdotdecimalin"}:
            raw = raw.replace(",", "").replace(" ", "")
        elif fmt == "numcommadecimal":
            raw = raw.replace(".", "").replace(" ", "").replace(",", ".")
        elif fmt in {"zerodash", "numdash"} and raw in {"-", "—", "–"}:
            raw = "0"
        elif fmt:
            continue
        try:
            val = float(raw) * 10 ** int(attrs.get("scale", "0"))
            if attrs.get("sign") == "-":
                val = -val
        except (ValueError, OverflowError):
            continue
        if not math.isfinite(val):
            continue
        if context["classe"]:
            contagens.setdefault(context["end"], {}).setdefault(context["classe"], set()).add(val)
            continue
        key = (tax, tag, unit, context.get("start"), context["end"])
        grouped.setdefault(key, set()).add(val)
    for (tax, tag, unit, start, end), vals in grouped.items():
        if len(vals) != 1:
            continue
        entry = {"val": next(iter(vals)), "end": end, "filed": str(arquivamento["filed"])[:10],
                 "form": arquivamento["form"], "accn": arquivamento["accn"]}
        if start:
            entry["start"] = start
        facts.setdefault(tax, {}).setdefault(tag, {"units": {}})["units"].setdefault(unit, []).append(entry)
    notas_acoes = {}
    for end, por_classe in contagens.items():
        if set(por_classe) != set(classes["membros"]) \
                or any(len(v) != 1 or next(iter(v)) <= 0 for v in por_classe.values()):
            continue
        valores = {m: next(iter(por_classe[m])) for m in classes["membros"]}
        entrada = {"val": sum(valores.values()), "end": end, "filed": str(arquivamento["filed"])[:10],
                   "form": arquivamento["form"], "accn": arquivamento["accn"]}
        fatos_acao = facts.setdefault(_D, {}).setdefault("EntityCommonStockSharesOutstanding", {"units": {}})
        # Se o próprio documento também traz total, a igualdade é obrigatória.
        anteriores = fatos_acao["units"].setdefault("shares", [])
        if any(e["end"] == end and e["val"] != entrada["val"] for e in anteriores):
            continue
        anteriores.append(entrada)
        notas_acoes[end] = "classes completas da capa: " + " + ".join(
            f"{m}={v:.15g}" for m, v in valores.items()) + f" = {entrada['val']:.15g} ações"
    if not facts:
        raise ValueError("Documento SEC sem fatos XBRL canônicos consolidados legíveis.")
    return {"cik": int(cik10), "facts": facts, "notas_acoes": notas_acoes}


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
    forms = {e["accn"]: e.get("form", "") for tax in facts.values() for node in tax.values()
             for entries in (node.get("units") or {}).values() for e in entries if e.get("accn")}
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
                df = df.assign(form=df["accn"].map(forms).fillna(""))
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
            nota_classes = (companyfacts.get("notas_acoes") or {}).get(r["end"].date().isoformat())
            if item == "acoes_em_circulacao" and nota_classes:
                nota = f"{nota}; {nota_classes}" if nota else nota_classes
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
    return _acoes_plausiveis(_receita_plausivel(out))


def _acoes_plausiveis(f: pd.DataFrame) -> pd.DataFrame:
    """Uma parcela de ações emitidas menor que o total em circulação não é um total.
    Mantém a contagem observada em circulação e registra o conflito; não infere ações faltantes.
    """
    emit = f[f["item"] == "acoes_emitidas"]
    circ = f[f["item"] == "acoes_em_circulacao"]
    if emit.empty or circ.empty:
        return f
    chaves = ["entidade", "period_end", "received_date"]
    comp = emit.reset_index().merge(circ[chaves + ["value"]], on=chaves, suffixes=("", "_circ"))
    ruins = comp.loc[comp["value"] < comp["value_circ"], "index"]
    if ruins.empty:
        return f
    out = f.drop(index=ruins).copy()
    bases = {tuple(r) for r in f.loc[ruins, chaves].itertuples(index=False, name=None)}
    for idx, r in out[out["item"] == "acoes_em_circulacao"].iterrows():
        if tuple(r[c] for c in chaves) in bases:
            aviso = "contagem emitida parcial menor que o total em circulação: descartada"
            out.loc[idx, "nota"] = f"{r['nota']}; {aviso}" if pd.notna(r["nota"]) else aviso
    return out.reset_index(drop=True)


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
    "ANUAIS", "ARQUIVAMENTOS_COLUNAS", "FATO_SEC_COLUNAS", "TAGS", "URL_COMPANYFACTS",
    "URL_EFTS", "URL_SUBMISSIONS", "URL_TICKERS", "arquivamentos_sec", "arquivos_sec",
    "companyfacts_documento", "documentos_pendentes", "fatos_sec", "parse_company_tickers", "parse_efts", "sec_ticker",
    "instancia_sec", "url_filing", "validar_companyfacts", "validar_efts", "validar_submissions",
]
