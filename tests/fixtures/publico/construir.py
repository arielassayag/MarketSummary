"""Constrói um arquivo público de teste (DADOS SIMULADOS) nos formatos reais das fontes.

Empresas fictícias, layouts reais: ZIPs da CVM (DFP/ITR/FCA/FRE/IPE, ``;``/latin-1, plano de
contas real), ``companyfacts`` da SEC (ifrs-full), respostas serializadas do Yahoo, CSVs do
iShares e da Global X, JSON da B3, FRED/SGS/Focus e um PDF de "Calendário Anual de Eventos
Corporativos" com fonte Type1 (WinAnsi) e Type0/Identity-H com ``ToUnicode``. Nenhum dado
pessoal; nenhuma rede.

Uso: ``construir_arquivo(tmp_path)`` grava ``<tmp_path>/publico/...`` + índice e devolve o
universo de teste (:class:`cdp.universe.Universe`) e a data de referência.
"""

from __future__ import annotations

import io
import json
import zipfile
import zlib
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from cdp.data.publico_arquivo import Arquivo
from cdp.universe import universe_from_frame

AS_OF = date(2026, 10, 9)
COLETA = datetime(2026, 10, 8, 22, 0, tzinfo=UTC)
CNPJ_IND = "11.111.111/0001-11"
CNPJ_BANCO = "22.222.222/0001-22"
CIK_ANDINA = "0000000777"
AVISO = "DADOS SIMULADOS"


def universo():
    rows = [
        dict(issuer_id="BR_SIMU", issuer_name="Simulada Industrial", country="BR",
             gics_sector="Industrials", line_type="LOCAL", yahoo_ticker="SIMU3.SA",
             exchange="B3", currency="BRL", adr_ratio="", primary_line=True, notes=AVISO),
        dict(issuer_id="BR_BSIM", issuer_name="Banco Simulado", country="BR",
             gics_sector="Financials", line_type="LOCAL", yahoo_ticker="BSIM4.SA",
             exchange="B3", currency="BRL", adr_ratio="", primary_line=True, notes=AVISO),
        dict(issuer_id="PE_SAND", issuer_name="Simulada Andina", country="PE",
             gics_sector="Materials", line_type="ADR", yahoo_ticker="SAND", exchange="NYSE",
             currency="USD", adr_ratio="1", primary_line=True, notes=AVISO),
        dict(issuer_id="MX_SIMU", issuer_name="Simulada Mexicana", country="MX",
             gics_sector="Consumer Staples", line_type="LOCAL", yahoo_ticker="SIMU.MX",
             exchange="BMV", currency="MXN", adr_ratio="", primary_line=True, notes=AVISO),
    ]
    return universe_from_frame(pd.DataFrame(rows), source_sha256="teste")


# ----------------------------------------------------------------- CVM

def _csv(header: list[str], rows: list[list]) -> bytes:
    linhas = [";".join(header)] + [";".join("" if v is None else str(v) for v in r)
                                   for r in rows]
    return ("\n".join(linhas) + "\n").encode("latin-1")


def _zip(arquivos: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, conteudo in sorted(arquivos.items()):
            zi = zipfile.ZipInfo(nome, date_time=(2026, 10, 4, 7, 0, 0))
            zf.writestr(zi, conteudo)
    return buf.getvalue()


_H_FLUXO = ["CNPJ_CIA", "DT_REFER", "VERSAO", "DENOM_CIA", "CD_CVM", "GRUPO_DFP", "MOEDA",
            "ESCALA_MOEDA", "ORDEM_EXERC", "DT_INI_EXERC", "DT_FIM_EXERC", "CD_CONTA",
            "DS_CONTA", "VL_CONTA", "ST_CONTA_FIXA"]
_H_SALDO = ["CNPJ_CIA", "DT_REFER", "VERSAO", "DENOM_CIA", "CD_CVM", "GRUPO_DFP", "MOEDA",
            "ESCALA_MOEDA", "ORDEM_EXERC", "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA",
            "ST_CONTA_FIXA"]


def _ind_fluxos(rec: float) -> dict[str, float]:
    ebit = 0.20 * rec
    rf = -0.025 * rec
    lair = ebit + rf
    ir = -0.30 * lair
    ll = lair + ir
    return {"rec": rec, "custo": -0.6 * rec, "bruto": 0.4 * rec, "ebit": ebit, "rf": rf,
            "lair": lair, "ir": ir, "ll": ll, "llc": 0.95 * ll, "da": 0.10 * rec,
            "cfo": ll + 0.10 * rec, "imob": -0.08 * rec, "intang": -0.02 * rec,
            "venda": 5000.0, "div": -0.4 * ll, "rec_acoes": -10000.0}


ACOES_TOTAL_MIL = 100_000      # reportado em milhares (unidade conferida pelo LPA)
ACOES_TES_MIL = 1_000


def _dre_ind(cnpj, dt_refer, ver, ini, fim, v, ordem="ÚLTIMO"):
    base = [cnpj, dt_refer, ver, "SIMULADA INDUSTRIAL S.A.", "099991", "DF Consolidado",
            "REAL", "MIL", ordem, ini, fim]
    acoes = (ACOES_TOTAL_MIL - ACOES_TES_MIL) * 1000.0
    lpa = round(v["llc"] * 1000.0 / acoes, 6)
    contas = [("3.01", "Receita de Venda de Bens e/ou Serviços", v["rec"]),
              ("3.02", "Custo dos Bens e/ou Serviços Vendidos", v["custo"]),
              ("3.03", "Resultado Bruto", v["bruto"]),
              ("3.05", "Resultado Antes do Resultado Financeiro e dos Tributos", v["ebit"]),
              ("3.06", "Resultado Financeiro", v["rf"]),
              ("3.07", "Resultado Antes dos Tributos sobre o Lucro", v["lair"]),
              ("3.08", "Imposto de Renda e Contribuição Social sobre o Lucro", v["ir"]),
              ("3.11", "Lucro/Prejuízo Consolidado do Período", v["ll"]),
              ("3.11.01", "Atribuído a Sócios da Empresa Controladora", v["llc"]),
              ("3.11.02", "Atribuído a Sócios Não Controladores", v["ll"] - v["llc"]),
              ("3.99.01.01", "ON", lpa)]
    return [base + [cd, ds, f"{val:.4f}", "S"] for cd, ds, val in contas]


def _dfc_ind(cnpj, dt_refer, ver, ini, fim, v):
    base = [cnpj, dt_refer, ver, "SIMULADA INDUSTRIAL S.A.", "099991", "DF Consolidado",
            "REAL", "MIL", "ÚLTIMO", ini, fim]
    contas = [("6.01", "Caixa Líquido Atividades Operacionais", v["cfo"]),
              ("6.01.01", "Caixa Gerado nas Operações", v["cfo"]),
              ("6.01.01.02", "Depreciação e amortização", v["da"]),
              ("6.02", "Caixa Líquido Atividades de Investimento",
               v["imob"] + v["intang"] + v["venda"]),
              ("6.02.01", "Aquisição de imobilizado", v["imob"]),
              ("6.02.02", "Aquisição de intangível", v["intang"]),
              ("6.02.03", "Venda de imobilizado", v["venda"]),
              ("6.03", "Caixa Líquido Atividades de Financiamento", v["div"] + v["rec_acoes"]),
              ("6.03.01", "Dividendos pagos", v["div"]),
              ("6.03.02", "Recompra de ações", v["rec_acoes"])]
    return [base + [cd, ds, f"{val:.4f}", "S"] for cd, ds, val in contas]


def _dva_ind(cnpj, dt_refer, ver, ini, fim, v):
    base = [cnpj, dt_refer, ver, "SIMULADA INDUSTRIAL S.A.", "099991", "DF Consolidado",
            "REAL", "MIL", "ÚLTIMO", ini, fim]
    return [base + ["7.04", "Retenções", f"{-v['da']:.4f}", "S"],
            base + ["7.04.01", "Depreciação, Amortização e Exaustão", f"{-v['da']:.4f}", "S"]]


def _bp_ind(cnpj, dt_refer, ver, fim, escala: float):
    base = [cnpj, dt_refer, ver, "SIMULADA INDUSTRIAL S.A.", "099991", "DF Consolidado",
            "REAL", "MIL", "ÚLTIMO", fim]
    bpa = [("1", "Ativo Total", 2_000_000 * escala),
           ("1.01", "Ativo Circulante", 600_000 * escala),
           ("1.01.01", "Caixa e Equivalentes de Caixa", 200_000 * escala),
           ("1.01.02", "Aplicações Financeiras", 50_000 * escala)]
    bpp = [("2", "Passivo Total", 2_000_000 * escala),
           ("2.01", "Passivo Circulante", 400_000 * escala),
           ("2.01.04", "Empréstimos e Financiamentos", 150_000 * escala),
           ("2.01.04.01", "Empréstimos e Financiamentos", 120_000 * escala),
           ("2.01.04.03", "Financiamento por Arrendamento", 30_000 * escala),
           ("2.02", "Passivo Não Circulante", 800_000 * escala),
           ("2.02.01", "Empréstimos e Financiamentos", 600_000 * escala),
           ("2.02.01.01", "Empréstimos e Financiamentos", 500_000 * escala),
           ("2.02.01.03", "Financiamento por Arrendamento", 100_000 * escala),
           ("2.03", "Patrimônio Líquido Consolidado", 800_000 * escala),
           ("2.03.09", "Participação dos Acionistas Não Controladores", 40_000 * escala)]
    return ([base + [cd, ds, f"{val:.4f}", "S"] for cd, ds, val in bpa],
            [base + [cd, ds, f"{val:.4f}", "S"] for cd, ds, val in bpp])


def _banco(dt_refer, fim, escala):
    base_f = [CNPJ_BANCO, dt_refer, 1, "BANCO SIMULADO S.A.", "099992", "DF Consolidado",
              "REAL", "MIL", "ÚLTIMO", f"{fim[:4]}-01-01", fim]
    dre = [("3.01", "Receitas da Intermediação Financeira", 500_000),
           ("3.02", "Despesas da Intermediação Financeira", -300_000),
           ("3.02.01", "Despesas de Juros e Similares", -250_000),
           ("3.02.02", "(Perda) de Crédito Esperada com Operações de Crédito", -50_000),
           ("3.03", "Resultado Bruto Intermediação Financeira", 200_000),
           ("3.04", "Outras Despesas/Receitas Operacionais", -100_000),
           ("3.04.01", "Receitas de Prestação de Serviços", 60_000),
           ("3.05", "Resultado Antes dos Tributos sobre o Lucro", 100_000),
           ("3.06", "Imposto de Renda e Contribuição Social sobre o Lucro", -30_000),
           ("3.09", "Lucro/Prejuízo Consolidado do Período", 70_000),
           ("3.09.01", "Atribuído a Sócios da Empresa Controladora", 69_000)]
    base_s = [CNPJ_BANCO, dt_refer, 1, "BANCO SIMULADO S.A.", "099992", "DF Consolidado",
              "REAL", "MIL", "ÚLTIMO", fim]
    bpa = [("1", "Ativo Total", 5_000_000), ("1.01", "Caixa e Equivalentes de Caixa", 100_000),
           ("1.02", "Ativos Financeiros", 4_000_000),
           ("1.02.03.05", "Operações de Crédito", 3_000_000),
           ("1.02.03.07", "(-) Provisão para Perda Esperada", -150_000)]
    bpp = [("2", "Passivo Total", 5_000_000),
           ("2.08", "Patrimônio Líquido Consolidado", 400_000),
           ("2.08.09", "Participação dos Acionistas Não Controladores", 5_000)]
    dfc = [("6.01", "Caixa Líquido Atividades Operacionais", 90_000)]
    return ([base_f + [cd, ds, f"{v * escala:.4f}", "S"] for cd, ds, v in dre],
            [base_s + [cd, ds, f"{v * escala:.4f}", "S"] for cd, ds, v in bpa],
            [base_s + [cd, ds, f"{v * escala:.4f}", "S"] for cd, ds, v in bpp],
            [base_f + [cd, ds, f"{v * escala:.4f}", "S"] for cd, ds, v in dfc])


def _zip_cvm(doc: str, ano: int, docs: list[dict]) -> bytes:
    """``docs``: [{cnpj, dt_refer, ver, receb, dre, dfc, dva, bpa, bpp, cap}]."""
    pref = f"{doc.lower()}_cia_aberta_"
    idx = [[d["cnpj"], d["dt_refer"], d["ver"], d.get("nome", "SIMULADA"), "099991", doc,
            "1000", d["receb"], f"https://www.rad.cvm.gov.br/simulado/{doc}/{d['dt_refer']}/"
            f"v{d['ver']}"] for d in docs]
    arquivos = {f"{pref}{ano}.csv": _csv(["CNPJ_CIA", "DT_REFER", "VERSAO", "DENOM_CIA",
                                          "CD_CVM", "CATEG_DOC", "ID_DOC", "DT_RECEB",
                                          "LINK_DOC"], idx)}
    for tab, header in (("DRE", _H_FLUXO), ("DFC_MI", _H_FLUXO), ("DVA", _H_FLUXO),
                        ("BPA", _H_SALDO), ("BPP", _H_SALDO)):
        linhas = [r for d in docs for r in d.get(tab.split("_")[0].lower(), [])]
        arquivos[f"{pref}{tab}_con_{ano}.csv"] = _csv(header, linhas)
    cap = [r for d in docs for r in d.get("cap", [])]
    arquivos[f"{pref}composicao_capital_{ano}.csv"] = _csv(
        ["CNPJ_CIA", "DT_REFER", "VERSAO", "DENOM_CIA", "QT_ACAO_ORDIN_CAP_INTEGR",
         "QT_ACAO_PREF_CAP_INTEGR", "QT_ACAO_TOTAL_CAP_INTEGR", "QT_ACAO_ORDIN_TESOURO",
         "QT_ACAO_PREF_TESOURO", "QT_ACAO_TOTAL_TESOURO"], cap)
    return _zip(arquivos)


REC_ANUAL = {2023: 1_000_000.0, 2024: 1_100_000.0, 2025: 1_210_000.0}
REC_TRIM = {"2025-03-31": 280_000.0, "2025-06-30": 300_000.0, "2025-09-30": 310_000.0,
            "2026-03-31": 320_000.0, "2026-06-30": 330_000.0}


def _cap(cnpj, dt_refer, ver):
    return [[cnpj, dt_refer, ver, "SIMULADA", ACOES_TOTAL_MIL, 0, ACOES_TOTAL_MIL,
             ACOES_TES_MIL, 0, ACOES_TES_MIL]]


def _dfp(ano: int, receb: str) -> bytes:
    fim = f"{ano}-12-31"
    v = _ind_fluxos(REC_ANUAL[ano])
    bpa, bpp = _bp_ind(CNPJ_IND, fim, 1, fim, ano / 2025)
    d_ind = {"cnpj": CNPJ_IND, "dt_refer": fim, "ver": 1, "receb": receb,
             "dre": _dre_ind(CNPJ_IND, fim, 1, f"{ano}-01-01", fim, v),
             "dfc": _dfc_ind(CNPJ_IND, fim, 1, f"{ano}-01-01", fim, v),
             "dva": _dva_ind(CNPJ_IND, fim, 1, f"{ano}-01-01", fim, v),
             "bpa": bpa, "bpp": bpp, "cap": _cap(CNPJ_IND, fim, 1)}
    dre, bpa_b, bpp_b, dfc_b = _banco(fim, fim, ano / 2025)
    d_b = {"cnpj": CNPJ_BANCO, "dt_refer": fim, "ver": 1, "receb": receb, "nome": "BANCO",
           "dre": dre, "bpa": bpa_b, "bpp": bpp_b, "dfc": dfc_b}
    return _zip_cvm("DFP", ano, [d_ind, d_b])


def _itr(ano: int) -> bytes:
    docs = []
    trims = sorted(k for k in REC_TRIM if k.startswith(str(ano)))
    acum = 0.0
    for k, fim in enumerate(trims):
        q = REC_TRIM[fim]
        acum += q
        receb = {"03-31": f"{ano}-05-08", "06-30": f"{ano}-08-07",
                 "09-30": f"{ano}-11-06"}[fim[5:]]
        ini_tri = {"03-31": "01-01", "06-30": "04-01", "09-30": "07-01"}[fim[5:]]
        vq, va = _ind_fluxos(q), _ind_fluxos(acum)
        dre = _dre_ind(CNPJ_IND, fim, 1, f"{ano}-{ini_tri}", fim, vq)
        if k > 0:
            dre += _dre_ind(CNPJ_IND, fim, 1, f"{ano}-01-01", fim, va)
        bpa, bpp = _bp_ind(CNPJ_IND, fim, 1, fim, 1.0 + 0.01 * (k + 1))
        docs.append({"cnpj": CNPJ_IND, "dt_refer": fim, "ver": 1, "receb": receb, "dre": dre,
                     "dfc": _dfc_ind(CNPJ_IND, fim, 1, f"{ano}-01-01", fim, va),
                     "dva": _dva_ind(CNPJ_IND, fim, 1, f"{ano}-01-01", fim, va),
                     "bpa": bpa, "bpp": bpp, "cap": _cap(CNPJ_IND, fim, 1)})
    return _zip_cvm("ITR", ano, docs)


def _fca() -> bytes:
    vm = _csv(["CNPJ_Companhia", "Data_Referencia", "Versao", "Nome_Empresarial",
               "Valor_Mobiliario", "Sigla_Classe_Acao_Preferencial", "Codigo_Negociacao",
               "Composicao_BDR_Unit", "Mercado", "Data_Inicio_Negociacao",
               "Data_Fim_Negociacao", "Segmento"],
              [[CNPJ_IND, "2026-01-01", 1, "SIMULADA INDUSTRIAL S.A.", "Ações Ordinárias", "",
                "SIMU3", "", "Bolsa", "2010-01-01", "", "Novo Mercado"],
               [CNPJ_BANCO, "2026-01-01", 1, "BANCO SIMULADO S.A.", "Ações Preferenciais",
                "PN", "BSIM4", "", "Bolsa", "2010-01-01", "", "Nível 1"]])
    geral = _csv(["CNPJ_Companhia", "Codigo_CVM", "Versao", "Setor_Atividade"],
                 [[CNPJ_IND, "099991", 1, "Indústria"], [CNPJ_BANCO, "099992", 1, "Bancos"]])
    return _zip({"fca_cia_aberta_valor_mobiliario_2026.csv": vm,
                 "fca_cia_aberta_geral_2026.csv": geral})


def _fre() -> bytes:
    dist = _csv(["CNPJ_Companhia", "Data_Referencia", "Versao", "ID_Documento",
                 "Nome_Companhia", "Quantidade_Total_Acoes_Circulacao",
                 "Percentual_Total_Acoes_Circulacao"],
                [[CNPJ_IND, "2026-12-31", 1, 1, "SIMULADA", 45000000, "45.500000"],
                 [CNPJ_IND, "2026-12-31", 2, 2, "SIMULADA", 46000000, "46.000000"]])
    idx = _csv(["CNPJ_CIA", "DT_REFER", "VERSAO", "DENOM_CIA", "CD_CVM", "CATEG_DOC", "ID_DOC",
                "DT_RECEB", "LINK_DOC"],
               [[CNPJ_IND, "2026-12-31", 1, "SIMULADA", "099991", "FRE", 1, "2026-05-30",
                 "https://www.rad.cvm.gov.br/simulado/FRE/v1"],
                [CNPJ_IND, "2026-12-31", 2, "SIMULADA", "099991", "FRE", 2, "2026-12-15",
                 "https://www.rad.cvm.gov.br/simulado/FRE/v2"]])
    return _zip({"fre_cia_aberta_distribuicao_capital_2026.csv": dist,
                 "fre_cia_aberta_2026.csv": idx})


URL_CALENDARIO = "https://www.rad.cvm.gov.br/simulado/IPE/calendario/v2"


def _ipe() -> bytes:
    h = ["CNPJ_Companhia", "Nome_Companhia", "Codigo_CVM", "Data_Referencia", "Categoria",
         "Tipo", "Especie", "Assunto", "Data_Entrega", "Tipo_Apresentacao",
         "Protocolo_Entrega", "Versao", "Link_Download"]
    rows = [[CNPJ_IND, "SIMULADA", 99991, "2026-04-29", "Assembleia", "AGO",
             "Edital de Convocação", "", "2026-03-27", "AP", "p1", 1,
             "https://www.rad.cvm.gov.br/simulado/IPE/ago"],
            [CNPJ_IND, "SIMULADA", 99991, "2026-08-10", "Fato Relevante", "", "", "Aquisição",
             "2026-08-10", "AP", "p2", 1, "https://www.rad.cvm.gov.br/simulado/IPE/fr"],
            [CNPJ_IND, "SIMULADA", 99991, "2026-12-31", "Calendário de Eventos Corporativos",
             "", "", "", "2026-07-20", "RE", "p4", 2, URL_CALENDARIO]]
    return _zip({"ipe_cia_aberta_2026.csv": _csv(h, rows)})


URL_CALENDARIO_V1 = "https://www.rad.cvm.gov.br/simulado/IPE/calendario/v1"


def _ipe_2025() -> bytes:
    """IPE de 2025: o calendário de 2026 (v1) foi ENTREGUE em dezembro de 2025."""
    h = ["CNPJ_Companhia", "Nome_Companhia", "Codigo_CVM", "Data_Referencia", "Categoria",
         "Tipo", "Especie", "Assunto", "Data_Entrega", "Tipo_Apresentacao",
         "Protocolo_Entrega", "Versao", "Link_Download"]
    rows = [[CNPJ_IND, "SIMULADA", 99991, "2026-12-31", "Calendário de Eventos Corporativos",
             "", "", "", "2025-12-15", "AP", "p3", 1, URL_CALENDARIO_V1]]
    return _zip({"ipe_cia_aberta_2025.csv": _csv(h, rows)})


# ----------------------------------------------------------------- PDF do calendário

def _lit(s: str) -> bytes:
    b = s.encode("cp1252")
    out = bytearray()
    for c in b:
        if c in (0x28, 0x29, 0x5C):
            out += b"\\" + bytes([c])
        elif c > 126:
            out += b"\\%03o" % c
        else:
            out.append(c)
    return b"(" + bytes(out) + b")"


def _hex16(s: str) -> bytes:
    return b"<" + "".join(f"{ord(ch) + 0x100:04X}" for ch in s).encode() + b">"


def pdf_calendario() -> bytes:
    """PDF padronizado (iTextSharp-like): rótulos em Type1, datas em Type0/Identity-H."""
    esquerda = [(760, "CALENDÁRIO ANUAL DE EVENTOS CORPORATIVOS"),
                (700, "Demonstrações Financeiras Anuais Completas e Demonstrações Financeiras "
                      "Padronizadas"),
                (690, "– DFP relativas ao exercício social findo em 31/12/2025"),
                (650, "Informações Trimestrais – ITR"),
                (630, "Referentes ao 1º trimestre"), (615, "Referentes ao 2º trimestre"),
                (600, "Referentes ao 3º trimestre"),
                (560, "Assembleia Geral Ordinária"),
                (545, "Envio do Edital de Convocação"),
                (530, "Realização da Assembleia Geral Ordinária"),
                (490, "Apresentação Pública sobre Divulgação de Resultados"),
                (470, "Referentes ao 3º trimestre"),
                (430, "Alterações efetuadas:"),
                (420, "Data alterada de 05/11/2026 para 06/11/2026")]
    direita = [(695, "12/03/2026"), (630, "08/05/2026"), (615, "07/08/2026"),
               (600, "06/11/2026"), (545, "27/03/2026"), (530, "29/04/2026"),
               (470, "09/11/2026")]
    ops = [b"q", b"BT"]
    for y, t in esquerda:
        ops.append(b"1 0 0 1 42 %d Tm /F1 9 Tf " % y + _lit(t) + b" Tj")
    for y, t in direita:
        ops.append(b"1 0 0 1 463.3 %d Tm /F2 9 Tf [" % y + _hex16(t[:2]) + b" -50 "
                   + _hex16(t[2:]) + b"] TJ")
    ops += [b"ET", b"Q"]
    conteudo = zlib.compress(b"\n".join(ops))
    cmap = (b"/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            b"1 begincodespacerange\n<0000><FFFF>\nendcodespacerange\n"
            b"1 beginbfrange\n<0120><017F><0020>\nendbfrange\nendcmap\nend\nend\n")
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Count 1/Kids[3 0 R]>>",
        b"<</Type/Page/MediaBox[0 0 595 842]/Resources<</Font<</F1 4 0 R/F2 5 0 R>>>>"
        b"/Contents 6 0 R/Parent 2 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica/Encoding/WinAnsiEncoding>>",
        b"<</Type/Font/Subtype/Type0/BaseFont/Simulada/Encoding/Identity-H/ToUnicode 7 0 R>>",
        b"<</Length %d/Filter/FlateDecode>>stream\n" % len(conteudo) + conteudo
        + b"\nendstream",
        b"<</Length %d>>stream\n" % len(cmap) + cmap + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    for k, o in enumerate(objs, start=1):
        out += b"%d 0 obj\n" % k + o + b"\nendobj\n"
    out += b"trailer\n<</Root 1 0 R/Size 8>>\n%%EOF\n"
    return bytes(out)


# ----------------------------------------------------------------- SEC

def _fato(val, end, filed, form, accn, start=None, fy=None, fp="FY"):
    d = {"val": val, "end": end, "filed": filed, "form": form, "accn": accn, "fy": fy, "fp": fp}
    if start:
        d["start"] = start
    return d


def companyfacts() -> dict:
    a24, a25, a26 = "0000000777-24-000001", "0000000777-25-000001", "0000000777-26-000001"
    fl = {  # (start, end) → por arquivo
        "Revenue": [("2022-01-01", "2022-12-31", 900.0, "2024-04-20", a24),
                    ("2023-01-01", "2023-12-31", 1000.0, "2024-04-20", a24),
                    ("2023-01-01", "2023-12-31", 1000.0, "2025-04-18", a25),
                    ("2024-01-01", "2024-12-31", 1100.0, "2025-04-18", a25),
                    ("2024-01-01", "2024-12-31", 1080.0, "2026-04-15", a26),  # reapresentado
                    ("2025-01-01", "2025-12-31", 1200.0, "2026-04-15", a26)],
        "ProfitLoss": [("2023-01-01", "2023-12-31", 150.0, "2024-04-20", a24),
                       ("2024-01-01", "2024-12-31", 160.0, "2025-04-18", a25),
                       ("2025-01-01", "2025-12-31", 170.0, "2026-04-15", a26)],
        "ProfitLossAttributableToOwnersOfParent": [
            ("2023-01-01", "2023-12-31", 140.0, "2024-04-20", a24),
            ("2024-01-01", "2024-12-31", 150.0, "2025-04-18", a25),
            ("2025-01-01", "2025-12-31", 160.0, "2026-04-15", a26)],
        "ProfitLossFromOperatingActivities": [
            ("2023-01-01", "2023-12-31", 250.0, "2024-04-20", a24),
            ("2024-01-01", "2024-12-31", 260.0, "2025-04-18", a25),
            ("2025-01-01", "2025-12-31", 270.0, "2026-04-15", a26)],
        "IncomeTaxExpenseContinuingOperations": [
            ("2025-01-01", "2025-12-31", 50.0, "2026-04-15", a26)],
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": [
            ("2025-01-01", "2025-12-31", 80.0, "2026-04-15", a26)],
    }
    st = {"Equity": [("2023-12-31", 900.0, "2024-04-20", a24),
                     ("2024-12-31", 950.0, "2025-04-18", a25),
                     ("2025-12-31", 1000.0, "2026-04-15", a26)],
          "Assets": [("2025-12-31", 3000.0, "2026-04-15", a26)],
          "CashAndCashEquivalents": [("2025-12-31", 200.0, "2026-04-15", a26)],
          "Borrowings": [("2025-12-31", 700.0, "2026-04-15", a26)]}
    ifrs = {}
    for tag, lst in fl.items():
        ifrs[tag] = {"units": {"USD": [_fato(v, e, f, "20-F", ac, start=s)
                                       for s, e, v, f, ac in lst]}}
    for tag, lst in st.items():
        ifrs[tag] = {"units": {"USD": [_fato(v, e, f, "20-F", ac) for e, v, f, ac in lst]}}
    dei = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        _fato(500_000_000, "2026-03-31", "2026-04-15", "20-F", a26)]}}}
    return {"cik": 777, "entityName": "Simulada Andina", "facts": {"ifrs-full": ifrs,
                                                                   "dei": dei}}


# ----------------------------------------------------------------- Yahoo

def _quadro(datas: list[str], linhas: dict[str, list]) -> dict:
    return {"colunas": datas, "linhas": dict(sorted(linhas.items()))}


def yahoo_partes() -> dict[str, dict[str, dict]]:
    anos = ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"]
    tri = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"]
    mx = {
        "info": {"ticker": "SIMU.MX", "parte": "info", "fonte": "YAHOO",
                 "info": {"currency": "MXN", "financialCurrency": "MXN",
                          "recommendationMean": 2.1, "numberOfAnalystOpinions": 9,
                          "floatShares": 400_000_000, "sharesOutstanding": 500_000_000,
                          "earningsTimestampStart": 1792627200,  # 2026-10-22
                          "isEarningsDateEstimate": False, "exDividendDate": None}},
        "estimativas": {"ticker": "SIMU.MX", "parte": "estimativas", "fonte": "YAHOO",
                        "earnings_estimate": {"0y": {"avg": 3.1, "numberOfAnalysts": 10,
                                                     "currency": "MXN"},
                                              "+1y": {"avg": 3.5, "numberOfAnalysts": 9}},
                        "revenue_estimate": {"0y": {"avg": 9.0e10}, "+1y": {"avg": 9.6e10}},
                        "analyst_price_targets": {"current": 40.0, "mean": 50.0, "median": 49.0,
                                                  "high": 60.0, "low": 35.0}},
        "demonstracoes": {"ticker": "SIMU.MX", "parte": "demonstracoes", "fonte": "YAHOO",
                          "demonstracoes": {
                              "income_stmt": _quadro(anos, {
                                  "Total Revenue": [8.5e10, 8.0e10, 7.5e10, 7.0e10],
                                  "EBIT": [8.0e9, 7.5e9, 7.0e9, None],
                                  "Reconciled Depreciation": [4.0e9, 3.8e9, 3.6e9, 3.4e9],
                                  "Pretax Income": [6.0e9, 5.5e9, 5.0e9, 4.5e9],
                                  "Tax Provision": [1.8e9, 1.6e9, 1.5e9, 1.4e9],
                                  "Net Income Common Stockholders": [4.0e9, 3.8e9, 3.4e9, 3.0e9],
                                  "Net Income Including Noncontrolling Interests":
                                      [4.2e9, 3.9e9, 3.5e9, 3.1e9]}),
                              "quarterly_income_stmt": _quadro(tri, {
                                  "Total Revenue": [2.3e10, 2.2e10, 2.2e10, 2.1e10, 2.1e10],
                                  "EBIT": [2.2e9, 2.1e9, 2.0e9, 2.0e9, 1.9e9]}),
                              "balance_sheet": _quadro(anos, {
                                  "Total Assets": [9.0e10, 8.5e10, 8.0e10, 7.5e10],
                                  "Stockholders Equity": [3.0e10, 2.8e10, 2.6e10, 2.4e10],
                                  "Total Equity Gross Minority Interest":
                                      [3.1e10, 2.9e10, 2.7e10, 2.5e10],
                                  "Cash And Cash Equivalents": [5.0e9, 4.0e9, 4.5e9, 4.2e9],
                                  "Current Debt": [2.0e9, 2.0e9, 1.0e9, 1.0e9],
                                  "Long Term Debt": [1.0e10, 9.0e9, 9.0e9, 8.0e9],
                                  "Capital Lease Obligations": [3.0e9, 3.0e9, 2.8e9, 2.5e9],
                                  "Ordinary Shares Number": [5.0e8, 5.0e8, 5.0e8, 5.0e8]}),
                              "cashflow": _quadro(anos, {
                                  "Operating Cash Flow": [9.0e9, 8.5e9, 8.0e9, 7.0e9],
                                  "Capital Expenditure": [-5.0e9, -4.8e9, -4.5e9, -4.0e9],
                                  "Cash Dividends Paid": [-1.6e9, -1.5e9, -1.4e9, None]}),
                              "quarterly_balance_sheet": None,
                              "quarterly_cashflow": None}},
        "dividendos": {"ticker": "SIMU.MX", "parte": "dividendos", "fonte": "YAHOO",
                       "dividendos": [["2025-05-10", 0.8], ["2026-05-08", 0.9],
                                      ["2026-11-10", 0.5]]},
        "calendario": {"ticker": "SIMU.MX", "parte": "calendario", "fonte": "YAHOO",
                       "calendar": {"Earnings Date": ["2026-10-22"]},
                       "earnings_dates": [{"data": "2025-10-23", "eps_estimado": 0.7,
                                           "eps_reportado": 0.72},
                                          {"data": "2026-04-24", "eps_estimado": 0.8,
                                           "eps_reportado": 0.81},
                                          {"data": "2026-07-24", "eps_estimado": 0.8,
                                           "eps_reportado": 0.79}]},
    }
    sand = {
        "info": {"ticker": "SAND", "parte": "info", "fonte": "YAHOO",
                 "info": {"currency": "USD", "financialCurrency": "USD",
                          "floatShares": 600_000_000, "sharesOutstanding": 500_000_000}},
        "demonstracoes": {"ticker": "SAND", "parte": "demonstracoes", "fonte": "YAHOO",
                          "demonstracoes": {
                              "quarterly_income_stmt": _quadro(tri, {
                                  "Total Revenue": [320.0, 310.0, 305.0, 300.0, 295.0]}),
                              "income_stmt": None}},
        "calendario": {"ticker": "SAND", "parte": "calendario", "fonte": "YAHOO",
                       "calendar": {}, "earnings_dates": [
                           {"data": "2025-10-30", "eps_estimado": 0.3, "eps_reportado": 0.31}]},
    }
    return {"SIMU.MX": mx, "SAND": sand}


# ----------------------------------------------------------------- ETFs e taxas

ISHARES_ILF = """iShares Latin America 40 ETF
Fund Holdings as of,"Oct 08, 2026"
Inception Date,"Oct 25, 2001"
Shares Outstanding,"111,500,000.00"
Stock,"-"

Ticker,Name,Sector,Asset Class,Market Value,Weight (%),Notional Value,Quantity,Price,Location,Exchange,Currency,FX Rate,Market Currency,Accrual Date
"SAND","SIMULADA ANDINA ADR","Materials","Equity","400,000.00","40.00","400,000.00","1,000.00","400.00","Peru","New York Stock Exchange Inc.","USD","1.00","USD","-"
"SIMU3","SIMULADA INDUSTRIAL ON","Industrials","Equity","350,000.00","35.00","350,000.00","1,000.00","350.00","Brazil","XBSP","BRL","5.30","BRL","-"
"ZZZZ11","FORA DO UNIVERSO","Financials","Equity","240,000.00","24.00","240,000.00","1,000.00","240.00","Brazil","XBSP","BRL","5.30","BRL","-"
"IBOVZ6","IBOV FUT DEC 26","Cash and/or Derivatives","Futures","0.00","0.00","55,000.00","1.00","55000.00","Brazil","Bolsa De Valores Mercadorias","BRL","5.30","BRL","-"
"USD","USD CASH","Cash and/or Derivatives","Cash","10,000.00","1.00","10,000.00","10,000.00","1.00","United States","-","USD","1.00","USD","-"

"The content contained herein is owned or licensed by BlackRock (simulado)."
"""

GLOBALX_ARGT = """Global X MSCI Argentina ETF
Fund Holdings Data as of 10/09/2026
% of Net Assets,Ticker,Name,SEDOL,Market Price ($),Shares Held,Market Value ($)
60.00,SAND,SIMULADA ANDINA,B000001,400.00,"1,000.00","400,000.00"
40.00,OUTRA AR,OUTRA EMPRESA,B000002,10.00,"1,000.00","10,000.00"
"""

B3_IBOV = {"page": {"pageNumber": 1, "pageSize": 200, "totalRecords": 2, "totalPages": 1},
           "header": {"date": "09/10/26", "text": "Quantidade Teórica Total", "part": "100,000"},
           "results": [{"cod": "SIMU3", "asset": "SIMULADA", "type": "ON NM", "part": "60,500",
                        "theoricalQty": "1.000"},
                       {"cod": "BSIM4", "asset": "BANCO SIMULADO", "type": "PN N1",
                        "part": "39,500", "theoricalQty": "1.000"}]}

FRED = "observation_date,DGS10\n2026-10-06,5.28\n2026-10-07,.\n2026-10-08,5.31\n"
SGS432 = [{"data": "07/10/2026", "valor": "13.75"}, {"data": "08/10/2026", "valor": "13.75"},
          {"data": "05/11/2026", "valor": "13.75"}]  # data futura: descartada (look-ahead)
SGS13522 = [{"data": "01/08/2026", "valor": "5,10"}, {"data": "01/09/2026", "valor": "4,99"}]
FOCUS_IPCA = {"value": [
    {"Indicador": "IPCA", "Data": "2026-10-02", "DataReferencia": "2026", "Mediana": 4.99,
     "baseCalculo": 0, "numeroRespondentes": 140},
    {"Indicador": "IPCA", "Data": "2026-10-02", "DataReferencia": "2026", "Mediana": 5.20,
     "baseCalculo": 1, "numeroRespondentes": 80},
    {"Indicador": "IPCA", "Data": "2026-10-02", "DataReferencia": "2027", "Mediana": 4.30,
     "baseCalculo": 0, "numeroRespondentes": 140}]}
FOCUS_CAMBIO = {"value": [
    {"Indicador": "Câmbio", "Data": "2026-10-02", "DataReferencia": "2026", "Mediana": 5.20,
     "baseCalculo": 0, "numeroRespondentes": 110}]}


def construir_arquivo(raiz: Path) -> dict:
    """Grava o arquivo de teste sob ``raiz`` e devolve ``{"universo", "as_of", "arquivo"}``."""
    arq = Arquivo(raiz)

    def g(chave, fonte, url, conteudo: bytes, quando: datetime = COLETA):
        arq.gravar(chave, fonte, url, conteudo, data_coleta=quando)

    g("CVM/FCA/fca_cia_aberta_2026.zip", "CVM", "https://dados.cvm.gov.br/simulado/fca", _fca())
    receb_dfp = {2023: "2024-03-20", 2024: "2025-03-19", 2025: "2026-03-12"}
    for ano in (2023, 2024, 2025):
        g(f"CVM/DFP/dfp_cia_aberta_{ano}.zip", "CVM", f"https://dados.cvm.gov.br/simulado/dfp{ano}",
          _dfp(ano, receb_dfp[ano]))
    for ano in (2025, 2026):
        g(f"CVM/ITR/itr_cia_aberta_{ano}.zip", "CVM", f"https://dados.cvm.gov.br/simulado/itr{ano}",
          _itr(ano))
    g("CVM/FRE/fre_cia_aberta_2026.zip", "CVM", "https://dados.cvm.gov.br/simulado/fre", _fre())
    g("CVM/IPE/ipe_cia_aberta_2026.zip", "CVM", "https://dados.cvm.gov.br/simulado/ipe", _ipe())
    g("CVM/IPE/ipe_cia_aberta_2025.zip", "CVM", "https://dados.cvm.gov.br/simulado/ipe2025",
      _ipe_2025())
    g("CVM/IPE_calendario/11111111000111_2026_v2.pdf", "CVM", URL_CALENDARIO, pdf_calendario())
    g("CVM/IPE_calendario/11111111000111_2026_v1.pdf", "CVM", URL_CALENDARIO_V1,
      pdf_calendario())
    g("SEC/efts/SAND.json", "SEC", "https://efts.sec.gov/simulado",
      json.dumps({"hits": {"hits": [{"_id": "777", "_source": {
          "entity": "Simulada Andina (SAND)", "tickers": "SAND"}}]}}).encode())
    g(f"SEC/companyfacts/CIK{CIK_ANDINA}.json", "SEC", "https://data.sec.gov/simulado",
      json.dumps(companyfacts()).encode())
    for t, partes in yahoo_partes().items():
        for parte, doc in partes.items():
            g(f"YAHOO/{parte}/{t}.json", "YAHOO", f"https://finance.yahoo.com/quote/{t}",
              (json.dumps(doc, sort_keys=True, ensure_ascii=False) + "\n").encode())
    g("ISHARES/ILF/ILF_holdings.csv", "ISHARES", "https://www.ishares.com/simulado/ILF",
      ISHARES_ILF.encode())
    g("GLOBALX/ARGT/argt_full-holdings_20261009.csv", "GLOBALX",
      "https://assets.globalxetfs.com/simulado/argt", GLOBALX_ARGT.encode())
    g("B3/carteira_teorica/IBOV.json", "B3", "https://sistemaswebb3-listados.b3.com.br/simulado",
      json.dumps(B3_IBOV, ensure_ascii=False).encode())
    g("FRED/DGS10/DGS10.csv", "FRED", "https://fred.stlouisfed.org/simulado", FRED.encode())
    g("BCB/SGS/sgs432.json", "BCB", "https://api.bcb.gov.br/simulado/432",
      json.dumps(SGS432).encode())
    g("BCB/SGS/sgs13522.json", "BCB", "https://api.bcb.gov.br/simulado/13522",
      json.dumps(SGS13522).encode())
    g("BCB/focus/focus_IPCA.json", "BCB", "https://olinda.bcb.gov.br/simulado/ipca",
      json.dumps(FOCUS_IPCA, ensure_ascii=False).encode())
    g("BCB/focus/focus_CAMBIO.json", "BCB", "https://olinda.bcb.gov.br/simulado/cambio",
      json.dumps(FOCUS_CAMBIO, ensure_ascii=False).encode())
    return {"universo": universo(), "as_of": AS_OF, "arquivo": arq}
