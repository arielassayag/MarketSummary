"""DADOS SIMULADOS — query literal das notas anuais DFP, sem fontes externas."""

import base64
import copy
import csv
import hashlib
import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from cdp.data.publico_arquivo import RegistroArquivo
from cdp.data.publico_cvm import ler_zip_demonstracoes, url_zip
from cdp.data.publico_cvm_comparativos import ContextoPoliticaCVM

ENTITY = "11.111.111/0001-11"
NSD = "155686"
MEMBER = "dfp_cia_aberta_DRE_con_2025.csv"
T0 = datetime(2026, 10, 7, 12, tzinfo=UTC)
LINK = "http://www.rad.cvm.gov.br/ENETCONSULTA/frmDownloadDocumento.aspx?CodigoInstituicao=1&NumeroSequencialDocumento=155686"
URL = "https://www.rad.cvm.gov.br/ENET/frmExibirArquivoFRE.aspx?NumeroSequencialDocumento=155686&CodigoGrupo=412&CodigoQuadro=0&Tipo=PDF&RelatorioRevisaoEspecial=Sem+Ressalva&CodTipoDocumento=4&Hash=hash-opaco-DADOS-SIMULADOS"
TEXT = "DADOS SIMULADOS politica documental anual CVM"


def _sha(body):
    return hashlib.sha256(body).hexdigest()


def _pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 20 750 Td ({TEXT}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _csv(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("latin1")


def _zip(link=LINK):
    rows = [dict(CNPJ_CIA=ENTITY, DT_REFER="2025-12-31", VERSAO="1",
                 DENOM_CIA="DADOS SIMULADOS S.A.", CD_CVM="099999",
                 GRUPO_DFP="DF Consolidado", MOEDA="REAL", ESCALA_MOEDA="MIL",
                 ORDEM_EXERC=order, DT_INI_EXERC=f"{year}-01-01", DT_FIM_EXERC=f"{year}-12-31",
                 CD_CONTA="3.01", DS_CONTA="Receita de Venda de Bens e/ou Serviços",
                 VL_CONTA=value, ST_CONTA_FIXA="S")
            for order, year, value in (("PENÚLTIMO", 2024, "100.0000000000"),
                                       ("ÚLTIMO", 2025, "200.0000000000"))]
    indices = [dict(CNPJ_CIA=ENTITY, DT_REFER="2025-12-31", VERSAO="1",
                    DT_RECEB="2026-03-25", ID_DOC=NSD, LINK_DOC=link)]
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(zipfile.ZipInfo(MEMBER, (2000, 1, 1, 0, 0, 0)), _csv(rows))
        archive.writestr(zipfile.ZipInfo("dfp_cia_aberta_2025.csv", (2000, 1, 1, 0, 0, 0)), _csv(indices))
    return output.getvalue()


def _zip_record(body):
    return RegistroArquivo("CVM/DFP/dfp_cia_aberta_2025.zip", "CVM", url_zip("DFP", 2025),
                           "DADOS_SIMULADOS/dfp2025.zip", _sha(body), len(body),
                           T0 - timedelta(hours=1), "microseconds")


def _read(body, contexts=()):
    return ler_zip_demonstracoes(body, "DFP", 2025, (ENTITY,),
                                 conservar_comparativos=True,
                                 registro_comparativos=_zip_record(body),
                                 conhecimento_ate=T0, contextos_politica=contexts)


def _cell(row):
    return dict(source_sha256=row["source_sha256"], membro=row["localizador"]["membro"],
                linha_csv_1_based=row["localizador"]["linha_csv_1_based"],
                raw=copy.deepcopy(row["raw"]))


def _context(body, url=URL):
    pdf = _pdf()
    html = ('<html><p>DADOS SIMULADOS</p><input type="hidden" id="hdnConteudoArquivo" '
            'name="hdnConteudoArquivo" value="' + base64.b64encode(pdf).decode() + '"></html>').encode()
    rec = RegistroArquivo("CVM/notas/DADOS_SIMULADOS.html", "CVM", url,
                           "DADOS_SIMULADOS/notas.html", _sha(html), len(html), T0, "microseconds")
    cells = tuple(_cell(r) for r in _read(body)["exercicios_reportados"].to_dict("records"))
    return ContextoPoliticaCVM(rec, html, ((1, TEXT),), cells), pdf


def _oracle(tables):
    return {key: dict(columns=list(frame.columns), records=frame.to_dict("records"),
                      index=frame.index.tolist(), dtypes=[str(dtype) for dtype in frame.dtypes],
                      attrs=copy.deepcopy(frame.attrs)) for key, frame in tables.items()}


def _preserve(tmp_path, body, ctx, result, *, name):
    (tmp_path / f"{name}.zip").write_bytes(body)
    (tmp_path / f"{name}.html").write_bytes(ctx.conteudo)
    request = dict(zip_record=_zip_record(body).como_dict(), html_record=ctx.registro.como_dict(),
                   cutoff=T0.isoformat(), anchors=ctx.ancoras, cells=ctx.celulas,
                   alcance="DADOS SIMULADOS; ligacao documental, sem uso financeiro")
    (tmp_path / f"{name}-request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2))
    (tmp_path / f"{name}-oracle.json").write_text(json.dumps(_oracle(result), ensure_ascii=False, indent=2))


@pytest.mark.parametrize("target,old,new", [
    ("HTML", "NumeroSequencialDocumento=155686", "NumeroSequencialDocumento=%31%35%35%36%38%36"),
    ("HTML", "NumeroSequencialDocumento=", "%4EumeroSequencialDocumento="),
    ("HTML", "CodigoGrupo=412", "CodigoGrupo=%34%31%32"),
    ("HTML", "Tipo=PDF", "Tipo=P%44F"),
    ("LINK_DOC", "NumeroSequencialDocumento=155686", "NumeroSequencialDocumento=%31%35%35%36%38%36"),
    ("LINK_DOC", "CodigoInstituicao=1", "CodigoInstituicao=%31"),
], ids=["nsd_html", "nome_html", "grupo_html", "tipo_html", "nsd_link", "instituicao_link"])
def test_notas_cvm_seis_aliases_percentuais_recusados(tmp_path, target, old, new):
    body = _zip(LINK.replace(old, new)) if target == "LINK_DOC" else _zip()
    ctx, _ = _context(body, URL.replace(old, new) if target == "HTML" else URL)
    # Conservar a origem causal entregue à API, incluindo negativa no baseline.
    _preserve(tmp_path, body, ctx, _read(body), name="entrada")
    with pytest.raises(ValueError, match="literais"):
        _read(body, (ctx,))


@pytest.mark.parametrize("old,new", [
    ("CodigoQuadro=0", "CodigoQuadro=%30"),
    ("CodTipoDocumento=4", "CodTipoDocumento=%34"),
], ids=["quadro", "documento"])
def test_notas_cvm_demais_campos_finitos_brutos_recusados(tmp_path, old, new):
    body = _zip()
    ctx, _ = _context(body, URL.replace(old, new))
    _preserve(tmp_path, body, ctx, _read(body), name="entrada")
    with pytest.raises(ValueError, match="literais"):
        _read(body, (ctx,))


def test_notas_cvm_positivo_portatil_preserva_html_pdf_filing_e_default(tmp_path):
    body = _zip()
    ctx, pdf = _context(body)
    default = ler_zip_demonstracoes(body, "DFP", 2025, (ENTITY,))
    result = _read(body, (ctx,))
    assert set(result) == set(default) | {"exercicios_reportados"}
    for key in default:
        pd.testing.assert_frame_equal(default[key], result[key])
    assert default["DRE_con"]["ORDEM_EXERC"].tolist() == ["ÚLTIMO"]
    rows = result["exercicios_reportados"].to_dict("records")
    assert [r["ordem_exercicio"] for r in rows] == ["PENÚLTIMO", "ÚLTIMO"]
    assert [r["valor_reportado"] for r in rows] == ["100.0000000000", "200.0000000000"]
    for row in rows:
        doc = row["contexto_politica"]
        assert row["url_filing"] == LINK and row["indice_documento"]["LINK_DOC"] == LINK
        assert row["id_doc"] == doc["numero_sequencial_documento"] == NSD
        assert doc["url"] == URL and doc["recibo"] == ctx.registro.como_dict()
        assert doc["document_sha256"] == _sha(pdf) != _sha(ctx.conteudo)
        assert doc["resposta_HTTP_sha256"] == _sha(ctx.conteudo)
        assert doc["resposta_HTTP_bytes"] == len(ctx.conteudo)
        assert doc["derivacao"]["document_bytes"] == len(pdf)
        assert row["disponivel_desde"] == T0.isoformat()
        assert row["data_publicacao_primaria"] is None
        assert doc["publicacao_primaria_UTC"] is None and doc["perimetro_economico_constante"] is None
        assert row["raw"] == doc["celula_CVM"]["raw"]
    _preserve(tmp_path, body, ctx, result, name="positivo")
    (tmp_path / "default-oracle.json").write_text(json.dumps(_oracle(default), ensure_ascii=False, indent=2))
    (tmp_path / "positivo.pdf").write_bytes(pdf)


@pytest.mark.parametrize("opaque", [
    URL.replace("Hash=hash-opaco-DADOS-SIMULADOS", "Hash=hash%2Bopaco%3D"),
    URL.replace("RelatorioRevisaoEspecial=Sem+Ressalva", "RelatorioRevisaoEspecial=%53em%20Ressalva"),
], ids=["hash", "relatorio"])
def test_notas_cvm_campos_opacos_codificados_preservados(tmp_path, opaque):
    body = _zip()
    ctx, _ = _context(body, opaque)
    result = _read(body, (ctx,))
    doc = result["exercicios_reportados"].iloc[0].contexto_politica
    assert doc["url"] == opaque and doc["recibo"]["url"] == opaque
    if "Hash=hash%2Bopaco%3D" in opaque:
        assert doc["derivacao"]["parametros_url"]["Hash"] == "hash+opaco="
    else:
        assert doc["derivacao"]["parametros_url"]["RelatorioRevisaoEspecial"] == "Sem Ressalva"
    _preserve(tmp_path, body, ctx, result, name="opaco")


def test_notas_cvm_ri_legado_permanece_pdf_direto(tmp_path):
    body = _zip()
    ctx, pdf = _context(body)
    rec = RegistroArquivo("RI/DADOS_SIMULADOS.pdf", "RI", "https://publico.exemplo/DADOS_SIMULADOS.pdf",
                           "DADOS_SIMULADOS/ri.pdf", _sha(pdf), len(pdf), T0, "microseconds")
    ctx = replace(ctx, registro=rec, conteudo=pdf)
    result = _read(body, (ctx,))
    doc = result["exercicios_reportados"].iloc[0].contexto_politica
    assert doc["document_sha256"] == rec.sha256 and doc["recibo"] == rec.como_dict()
    assert "resposta_HTTP_sha256" not in doc and "numero_sequencial_documento" not in doc
    _preserve(tmp_path, body, ctx, result, name="ri")
