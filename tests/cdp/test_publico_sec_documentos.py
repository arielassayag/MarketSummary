"""DADOS SIMULADOS: estruturas reais de submissions, XBRL e inline da SEC, sem rede."""

import hashlib
import io
import json
import zipfile
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from cdp.data import publico as P
from cdp.data import publico_sec as sec
from cdp.data.publico_arquivo import Arquivo
from cdp.data.publico_fatos import selecionar_pit

CIK = "0000000999"
ACC = "0000000999-26-000001"
ARQUIVO = {"accn": ACC, "form": "20-F", "filed": "2026-04-20"}


def _historico():
    return {"cik": 999, "filings": {"recent": {
        "accessionNumber": [ACC, "0000000999-26-000002", "0000000999-26-000003"],
        "form": ["20-F", "6-K", "6-K"], "filingDate": ["2026-04-20", "2026-08-10", "2026-10-20"],
        "reportDate": ["2025-12-31", "2026-06-30", "2026-09-30"],
        "primaryDocument": ["anual.htm", "trimestral.htm", "futuro.htm"], "isXBRL": [1, 1, 1]},
        "files": []}}


def _inline(extra=""):
    return f'''<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
        xmlns:xbrli="http://www.xbrl.org/2003/instance"
        xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
        xmlns:ifrs-full="https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full">
      <xbrli:context id="anual"><xbrli:entity><xbrli:identifier>999</xbrli:identifier></xbrli:entity>
        <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate>
        <xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:context id="saldo"><xbrli:entity><xbrli:identifier>999</xbrli:identifier></xbrli:entity>
        <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
      <xbrli:context id="segmento"><xbrli:entity><xbrli:identifier>999</xbrli:identifier>
        <xbrli:segment><xbrldi:explicitMember dimension="pais">paisX</xbrldi:explicitMember>
        </xbrli:segment></xbrli:entity><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant>
        </xbrli:period></xbrli:context>
      <xbrli:unit id="ars"><xbrli:measure>iso4217:ARS</xbrli:measure></xbrli:unit>
      <ix:nonFraction name="ifrs-full:Revenue" contextRef="anual" unitRef="ars" scale="3"
        format="ixt:num-dot-decimal">1,500</ix:nonFraction>
      <ix:nonFraction name="ifrs-full:Assets" contextRef="saldo" unitRef="ars"
        format="ixt:num-comma-decimal">3.000,50</ix:nonFraction>
      <ix:nonFraction name="ifrs-full:Assets" contextRef="segmento" unitRef="ars">99999</ix:nonFraction>
      <ix:nonFraction name="ifrs-full:ProfitLoss" contextRef="anual" unitRef="ars" sign="-">40</ix:nonFraction>
      <ix:nonFraction name="empresa:Assets" contextRef="saldo" unitRef="ars">99999</ix:nonFraction>
      {extra}</html>'''.encode()


def test_datas_de_arquivamento_sem_look_ahead_e_url_do_documento():
    obj = sec.validar_submissions(json.dumps(_historico()).encode(), CIK)
    arq = sec.arquivamentos_sec(obj, CIK, date(2026, 10, 6))
    assert list(arq["form"]) == ["6-K", "20-F"]
    assert arq.iloc[1]["period_end"] == pd.Timestamp("2025-12-31")
    assert arq.iloc[1]["filed"] == pd.Timestamp("2026-04-20")
    assert arq.iloc[1]["url"].endswith("/000000099926000001/anual.htm")
    with pytest.raises(ValueError, match="outro CIK"):
        sec.validar_submissions(json.dumps(obj).encode(), "0000000998")
    obj["filings"]["recent"]["reportDate"].pop()
    with pytest.raises(ValueError, match="desalinhados"):
        sec.validar_submissions(json.dumps(obj).encode())
    with pytest.raises(ValueError):
        sec.validar_submissions(b'{"message":"limite"}')


@pytest.mark.parametrize("html_invalido", [False, True])
def test_inline_escalas_sinais_moeda_contexto_e_data_publicacao(html_invalido):
    conteudo = _inline()
    if html_invalido:
        conteudo = conteudo.replace(b"<html ", b"<!DOCTYPE html><html ")
        conteudo = conteudo.replace(b"<ix:nonFraction name=", b"<br><ix:nonFraction name=", 1)
    cf = sec.companyfacts_documento(conteudo, CIK, ARQUIVO)
    f = sec.fatos_sec(cf).set_index("item")
    assert f.loc["receita", "value"] == 1_500_000
    assert f.loc["ativo_total", "value"] == 3000.5
    assert f.loc["lucro_liquido", "value"] == -40
    assert f["currency"].eq("ARS").all()
    assert f["received_date"].eq(pd.Timestamp("2026-04-20")).all()
    assert f["nota"].str.contains("IAS 29").all()


def test_duplicata_contraditoria_nao_vira_um_numero_arbitrario():
    cf = sec.companyfacts_documento(_inline('''<ix:nonFraction name="ifrs-full:Assets"
        contextRef="saldo" unitRef="ars">9000</ix:nonFraction>'''), CIK, ARQUIVO)
    assert "Assets" not in cf["facts"]["ifrs-full"]
    with pytest.raises(ValueError, match="sem fatos"):
        sec.companyfacts_documento(b"<html>limite de acesso</html>", CIK, ARQUIVO)


def test_instancia_xbrl_ifrs_namespace_e_arrendamento_como_fluxo():
    xml = b'''<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
        xmlns:i="https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full">
      <xbrli:context id="a"><xbrli:entity><xbrli:identifier>999</xbrli:identifier></xbrli:entity>
        <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate>
        </xbrli:period></xbrli:context><xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
      <i:PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities contextRef="a" unitRef="usd">600</i:PaymentsOfLeaseLiabilitiesClassifiedAsFinancingActivities>
      </xbrli:xbrl>'''
    f = sec.fatos_sec(sec.companyfacts_documento(xml, CIK, ARQUIVO))
    assert f.iloc[0]["item"] == "arrendamentos_pagos"
    assert f.iloc[0]["demonstrativo"] == "DFC"
    f["fonte"], f["sha256"] = "SEC", "a" * 64
    d = selecionar_pit(f, date(2026, 4, 21))
    assert set(d["freq"]) == {"A", "TTM"}
    assert d["value"].eq(600).all()
    assert selecionar_pit(f, date(2026, 4, 19)).empty


def test_historico_arquivado_paginas_antigas_e_offline(tmp_path):
    quando = datetime(2026, 10, 6, 12, tzinfo=UTC)
    arq = Arquivo(tmp_path, agora=lambda: quando)
    obj = _historico()
    nome = f"CIK{CIK}-submissions-001.json"
    obj["filings"]["files"] = [{"name": nome, "filingFrom": "2024-01-01", "filingTo": "2024-12-31"}]
    older = {k: v[:1] for k, v in obj["filings"]["recent"].items()}
    older["filingDate"], older["reportDate"] = ["2024-04-20"], ["2023-12-31"]
    older["accessionNumber"] = ["0000000999-24-000001"]
    arq.gravar(f"SEC/submissions/CIK{CIK}.json", "SEC", None, json.dumps(obj).encode())
    arq.gravar(f"SEC/submissions/{nome}", "SEC", None, json.dumps(older).encode())
    off = Arquivo(tmp_path, offline=True)
    df = P._arquivamentos_sec(off, CIK, date(2026, 10, 6), date(2024, 1, 1),
                             lambda *_: pytest.fail("rede usada no teste offline"))
    assert set(df["filed"].dt.year) == {2024, 2026}


def test_contagem_emitida_parcial_nao_contradiz_total_em_circulacao():
    entry = {"val": 100, "end": "2025-12-31", **ARQUIVO}
    cf = {"cik": 999, "facts": {"ifrs-full": {
        "NumberOfSharesIssued": {"units": {"shares": [{**entry, "val": 10}]}},
        "NumberOfSharesOutstanding": {"units": {"shares": [entry]}}}}}
    f = sec.fatos_sec(cf)
    assert list(f["item"]) == ["acoes_em_circulacao"]
    assert f.iloc[0]["value"] == 100
    assert "emitida parcial" in f.iloc[0]["nota"]


def test_capa_recente_e_comparativo_nao_ocultam_balanco_pendente():
    arquivos = sec.arquivamentos_sec(_historico(), CIK, date(2026, 10, 6))
    cf = sec.companyfacts_documento(_inline(), CIK, ARQUIVO)
    f = sec.fatos_sec(cf)
    # Companyfacts contém só os comparativos financeiros de 2024 do arquivo de 2025.
    f["period_end"] = pd.Timestamp("2024-12-31")
    sh = f.iloc[0].to_dict()
    sh.update(item="acoes_em_circulacao", period_end=pd.Timestamp("2026-04-20"), currency=None)
    f = pd.concat([f, pd.DataFrame([sh])], ignore_index=True)
    alvo = sec.documentos_pendentes(arquivos, f, date(2026, 10, 6))
    assert ACC in set(alvo["accn"])
    # O núcleo financeiro completo na data própria dispensa a coleta do mesmo documento.
    f = sec.fatos_sec(cf)
    alvo = sec.documentos_pendentes(arquivos, f, date(2026, 10, 6))
    assert ACC not in set(alvo["accn"])


def _espelho(tmp_path, monkeypatch, conteudo):
    doc = {"cik": CIK, "accn": ACC, "form": "20-F", "filed": "2026-04-20",
           "period_end": "2025-12-31", "documento_sec": "anual.htm", "url": "https://ri.exemplo.test/20f.zip",
           "pagina_ri": "https://ri.exemplo.test/arquivamentos", "membro_zip": "anual.xml",
           "sha256": hashlib.sha256(conteudo).hexdigest()}
    p = tmp_path / "catalogo.json"
    p.write_text(json.dumps({"schema": "cdp.sec_ri_xbrl/v1", "documentos": [doc]}), encoding="utf-8")
    monkeypatch.setattr(sec, "CATALOGO_RI", p)
    return doc


def _zip(conteudo):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("anual.xml", date_time=(2026, 4, 20, 0, 0, 0)), conteudo)
    return b.getvalue()


def test_espelho_ri_exige_vinculo_sec_e_bytes_conferidos(tmp_path, monkeypatch):
    b = _zip(_inline())
    d = _espelho(tmp_path, monkeypatch, b)
    r = sec.arquivamentos_sec(_historico(), CIK, date(2026, 4, 21)).iloc[0].to_dict()
    assert sec.documento_ri(CIK, r) == d
    assert sec.documento_ri("0000000998", r) is None
    f = sec.fatos_sec(sec.companyfacts_ri(b, CIK, r, d))
    assert f.period_end.max() == pd.Timestamp("2025-12-31")
    assert f.received_date.eq(pd.Timestamp("2026-04-20")).all()
    with pytest.raises(ValueError, match="SHA-256"):
        sec.companyfacts_ri(b + b"alterado", CIK, r, d)
    with pytest.raises(ValueError, match="diverge"):
        sec.documento_ri(CIK, {**r, "filed": pd.Timestamp("2026-04-19")})
    with pytest.raises(ValueError, match="sem fatos"):
        sec.companyfacts_ri(b, "0000000998", r, d)


def test_inline_rejeita_valor_monetario_posterior_ao_periodo_reportado():
    futuro = '''<xbrli:context id="futuro"><xbrli:entity><xbrli:identifier>999</xbrli:identifier></xbrli:entity>
        <xbrli:period><xbrli:instant>2026-12-31</xbrli:instant></xbrli:period></xbrli:context>
        <ix:nonFraction name="ifrs-full:Assets" contextRef="futuro" unitRef="ars">9000</ix:nonFraction>'''
    f = sec.fatos_sec(sec.companyfacts_documento(_inline(futuro), CIK,
                                               {**ARQUIVO, "period_end": "2025-12-31"}))
    assert f.period_end.max() == pd.Timestamp("2025-12-31")
    assert f[f.item == "ativo_total"].value.eq(3000.5).all()


@pytest.mark.parametrize("so_capa", [False, True])
def test_sec_indisponivel_usa_zip_ri_arquivado_e_reproduz_offline(tmp_path, monkeypatch, so_capa):
    from cdp.data.security_master import HttpError

    quando = datetime(2026, 10, 6, 12, tzinfo=UTC)
    arq = Arquivo(tmp_path, agora=lambda: quando)
    monkeypatch.setattr(P, "_arquivo", lambda root, offline: Arquivo(tmp_path, offline=offline,
                                                                    agora=lambda: quando))
    monkeypatch.setattr(P, "mestre_publico", lambda *a, **k: pd.DataFrame(
        {"cik": [CIK], "cnpj": [None]}, index=["AR_SUPERVIELLE"]))
    cf = sec.companyfacts_documento(_inline(), CIK, ARQUIVO)
    for tax in cf["facts"].values():
        for node in tax.values():
            for entries in node["units"].values():
                original = entries[0]
                entries[:] = [{**original, "start": f"{y}-01-01", "end": f"{y}-12-31",
                               "filed": "2025-04-20", "accn": "0000000999-25-000001"}
                              for y in (2023, 2024)]
    arq.gravar(f"SEC/companyfacts/CIK{CIK}.json", "SEC", None, json.dumps(cf).encode())
    arq.gravar(f"SEC/submissions/CIK{CIK}.json", "SEC", None, json.dumps(_historico()).encode())
    b = _zip(_inline())
    d = _espelho(tmp_path, monkeypatch, b)
    chamadas = []

    def baixar(url, headers):
        chamadas.append(url)
        if url == d["url"]:
            return b
        if so_capa and url.endswith("/anual.htm"):
            return b'''<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
                xmlns:d="http://xbrl.sec.gov/dei/2025">
                <xbrli:context id="s"><xbrli:entity><xbrli:identifier>999</xbrli:identifier></xbrli:entity>
                <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
                <xbrli:unit id="a"><xbrli:measure>shares</xbrli:measure></xbrli:unit>
                <d:EntityCommonStockSharesOutstanding contextRef="s" unitRef="a">100</d:EntityCommonStockSharesOutstanding>
                </xbrli:xbrl>'''
        raise HttpError(403, url)

    f = P.demonstrativos(["AR_SUPERVIELLE"], date(2026, 10, 6), root=tmp_path,
                         http_get=baixar, complementar_yahoo=False)
    novo = f[(f.period_end == pd.Timestamp("2025-12-31")) & ~f.item.isin(sec.ACOES)]
    assert not novo.empty and novo.fonte.eq("SEC").all()
    assert novo.sha256.eq(hashlib.sha256(b).hexdigest()).all()
    assert novo.url.eq(d["url"] + "#anual.xml").all()
    assert novo.data_publicacao.eq(date(2026, 4, 20)).all()
    if so_capa:
        assert f[f.item == "acoes_em_circulacao"].value.eq(100).all()
    chamadas.clear()
    off = P.demonstrativos(["AR_SUPERVIELLE"], date(2026, 10, 6), root=tmp_path,
                           offline=True, http_get=lambda *_: pytest.fail("rede offline"),
                           complementar_yahoo=False)
    pd.testing.assert_frame_equal(f, off)
    assert not chamadas
