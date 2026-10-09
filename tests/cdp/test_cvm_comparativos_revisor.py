"""DADOS SIMULADOS: controles próprios da ligação documental, sem aprovação financeira."""
import copy
import csv
import io
import os
import zipfile
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from cdp.data import publico_cvm as cvm
from cdp.data import publico_cvm_comparativos as ledger_api
from cdp.data.publico_arquivo import Arquivo

# isort: split
from cdp_audit_guardas import registrar, remover

ENTITY = "88.888.888/0001-88"
RECEPTION = datetime(2026, 10, 6, 9, 1, 2, 123456, tzinfo=UTC)
PDF_RECEPTION = RECEPTION + timedelta(hours=2)
CUTOFF = PDF_RECEPTION + timedelta(days=1)
MEMBER = "dfp_cia_aberta_DRE_con_2025.csv"


def csv_body(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("latin-1")


def source_rows():
    rows = []
    for version, current, prior in (("1", "90.0000", "30.0000"), ("2", "100.0000", "40.0000")):
        for order, year, value in (("ÚLTIMO", 2025, current), ("PENÚLTIMO", 2024, prior)):
            rows.append(dict(CNPJ_CIA=ENTITY, DT_REFER="2025-12-31", VERSAO=version,
                DENOM_CIA="DADOS SIMULADOS REVISOR", MOEDA="REAL", ESCALA_MOEDA="MIL",
                ORDEM_EXERC=order, DT_INI_EXERC=f"{year}-01-01", DT_FIM_EXERC=f"{year}-12-31",
                CD_CONTA="3.01", DS_CONTA="Receita de Venda de Bens e/ou Serviços",
                VL_CONTA=value, COLUNA_EXTRA="literal adicional preservado"))
    return rows


def make_zip(rows, *, indices=True):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zf:
        zf.writestr(MEMBER, csv_body(rows))
        if indices:
            zf.writestr("dfp_cia_aberta_2025.csv", csv_body([
                dict(CNPJ_CIA=ENTITY, DT_REFER="2025-12-31", VERSAO=v,
                    DT_RECEB=f"2026-03-0{v}", ID_DOC=f"9900{v}", LINK_DOC=f"https://publico.exemplo/9900{v}")
                for v in ("1", "2")]))
    return stream.getvalue()


def pdf_body():
    text = b"BT /F1 12 Tf 20 750 Td (DADOS SIMULADOS vinculo documental revisor) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(text)).encode() + b" >>\nstream\n" + text + b"\nendstream"]
    body, offsets = b"%PDF-1.4\n", [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n"
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return body + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def setup_source(tmp_path, rows=None, indices=True):
    rows = source_rows() if rows is None else rows
    body = make_zip(rows, indices=indices)
    writer = Arquivo(tmp_path, agora=lambda: RECEPTION)
    record = writer.gravar("CVM/DFP/dfp_cia_aberta_2025.zip", "CVM", cvm.url_zip("DFP", 2025),
        body, data_coleta=RECEPTION)
    pdf = pdf_body()
    pdf_record = writer.gravar("RI/documentos/revisor.pdf", "RI", "https://ri.exemplo/revisor.pdf",
        pdf, data_coleta=PDF_RECEPTION)
    contexts = []
    for i in (0, len(rows)-1):
        contexts.append(ledger_api.ContextoPoliticaCVM(pdf_record, pdf,
            ((1, "DADOS SIMULADOS vinculo documental revisor"),),
            (dict(source_sha256=record.sha256, membro=MEMBER, linha_csv_1_based=i+2,
                raw={k: v if v != "" else None for k,v in rows[i].items()}),)))
    return body, record, tuple(contexts), Arquivo(tmp_path, offline=True, conhecimento_ate=CUTOFF)


@contextmanager
def guarded():
    state = {"active": True, "reads": 0, "write": 0, "network": 0, "process": 0, "mutation": 0}
    def hook(event, args):
        if not state["active"]:
            return
        group = None
        if event == "open":
            _, mode, flags = args
            if (isinstance(mode,str) and any(c in mode for c in "wax+")) or (
                isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
                group = "write"
            else:
                state["reads"] += 1
        elif event.startswith("socket."):
            group = "network"
        elif event.startswith(("subprocess.","os.exec","os.spawn")) or event in {"os.system","os.fork"}:
            group = "process"
        elif event in {"os.mkdir","os.remove","os.rename","os.rmdir","os.utime","os.chmod","os.link","os.symlink"}:
            group = "mutation"
        if group:
            state[group] += 1
            raise RuntimeError(f"Guarda API: {group}")
    token = registrar(hook)
    try:
        yield state
    finally:
        state["active"] = False
        remover(token)
        assert all(state[key] == 0 for key in ("write","network","process","mutation"))


def read(source, *, contexts=None, record=None, cutoff=CUTOFF, cnpjs=(ENTITY,)):
    body, original, associated, archive = source
    with guarded():
        native = archive.buscar(original.chave, CUTOFF.date())
        physical = archive.ler(native)
        assert physical == body and native.sha256 == original.sha256
        result = cvm.ler_zip_demonstracoes(physical, "DFP", 2025, cnpjs,
            conservar_comparativos=True, registro_comparativos=record or native,
            conhecimento_ate=cutoff, contextos_politica=associated if contexts is None else contexts)
    assert Path(cvm.__file__).resolve().is_relative_to(Path(__file__).resolve().parents[2]/"src")
    return result


def test_revisor_versoes_periodos_ordens_indice_e_raw_sem_promocao(tmp_path):
    source = setup_source(tmp_path)
    frame = read(source)["exercicios_reportados"]
    assert frame.version_literal.tolist() == ["1","1","2","2"]
    assert frame.ordem_exercicio.tolist() == ["ÚLTIMO","PENÚLTIMO","ÚLTIMO","PENÚLTIMO"]
    assert frame.period_end.tolist() == ["2025-12-31","2024-12-31","2025-12-31","2024-12-31"]
    assert frame.id_doc.tolist() == ["99001","99001","99002","99002"]
    assert frame.raw.tolist() == source_rows()
    assert frame.contexto_politica.notna().tolist() == [True,False,False,True]
    assert frame.data_publicacao_primaria.tolist() == [None]*4
    assert all(row["perimetro_economico_constante"] is None for row in frame.contexto_politica if row)


@pytest.mark.parametrize("position", [0,1])
@pytest.mark.parametrize("field,value", [("CNPJ_CIA","99.999.999/0001-99"),("VERSAO","3"),
    ("DT_REFER","2024-12-31"),("DT_INI_EXERC","2023-01-01"),("DT_FIM_EXERC","2023-12-31"),
    ("CD_CONTA","3.99"),("MOEDA","DOLAR"),("ESCALA_MOEDA","UNIDADE"),
    ("ORDEM_EXERC","ÚLTIMO adulterado"),("VL_CONTA","0"),("COLUNA_EXTRA","alteração explícita")])
def test_revisor_contexto_primeira_e_ultima_celula_recusa_contradicao(tmp_path,position,field,value):
    source = setup_source(tmp_path)
    contexts = copy.deepcopy(source[2])
    contexts[position].celulas[0]["raw"][field] = value
    with pytest.raises(ValueError,match="Contexto contradiz"):
        read(source, contexts=contexts)


@pytest.mark.parametrize("field,value", [("source_sha256","f"*64),("membro","arquivo_inexistente.csv"),
    ("linha_csv_1_based",99)])
def test_revisor_localizador_ultimo_contexto_nao_capture_outra_celula(tmp_path,field,value):
    source = setup_source(tmp_path)
    contexts = copy.deepcopy(source[2])
    contexts[-1].celulas[0][field] = value
    with pytest.raises(ValueError,match="Contexto contradiz"):
        read(source, contexts=contexts)


@pytest.mark.parametrize("field,value", [("sha256","e"*64),("bytes",0),
    ("url","https://dados.cvm.gov.br/rota_errada.zip"),("fonte","RI"),
    ("data_coleta",RECEPTION.replace(tzinfo=None)),("precisao","nao-declarada")])
def test_revisor_recebimento_contraditorio_recusa(tmp_path,field,value):
    source = setup_source(tmp_path)
    with pytest.raises(ValueError):
        read(source,record=replace(source[1],**{field:value}))


def test_revisor_corte_depois_zip_antes_pdf_recusa(tmp_path):
    source = setup_source(tmp_path)
    with pytest.raises(ValueError,match="Recepção observada"):
        read(source,cutoff=source[2][0].registro.limite_captura-timedelta(microseconds=1))
    frame = read(source,cutoff=source[2][0].registro.limite_captura)["exercicios_reportados"]
    assert frame.disponivel_desde.tolist() == [source[2][0].registro.limite_captura.isoformat(),
        source[1].limite_captura.isoformat(),source[1].limite_captura.isoformat(),
        source[2][-1].registro.limite_captura.isoformat()]


def test_revisor_default_e_fatos_ignoram_ledger_mesmo_ligado(tmp_path):
    source = setup_source(tmp_path)
    default = cvm.ler_zip_demonstracoes(source[0],"DFP",2025,(ENTITY,))
    opted = read(source)
    assert "exercicios_reportados" not in default
    with guarded():
        for key in default:
            pd.testing.assert_frame_equal(default[key],opted[key])
        pd.testing.assert_frame_equal(cvm.fatos_cvm(default,"DFP"),cvm.fatos_cvm(opted,"DFP"))


@pytest.mark.parametrize("value", [None,"0.0000"])
def test_revisor_ausencia_zero_sem_filing_ou_contexto_inventado(tmp_path,value):
    rows = source_rows()[:1]
    rows[0]["VL_CONTA"] = value
    source = setup_source(tmp_path,rows,indices=False)
    frame = read(source,contexts=())["exercicios_reportados"]
    assert frame.valor_reportado.iloc[0] == value
    assert frame.id_doc.iloc[0] is None and frame.indice_documento.iloc[0] is None
    assert frame.contexto_politica.iloc[0] is None


@pytest.mark.parametrize("field,value", [("MOEDA","DOLAR"),("ESCALA_MOEDA","UNIDADE")])
def test_revisor_granulos_diferentes_nao_juntados_automaticamente(tmp_path,field,value):
    rows = source_rows()[:1] + source_rows()[:1]
    rows[-1][field] = value
    rows[-1]["VL_CONTA"] = "90000.0000"
    frame = read(setup_source(tmp_path,rows),contexts=())["exercicios_reportados"]
    assert len(frame) == 2 and not frame.conflito_reportado.any()
    assert frame.valor_reportado.tolist() == ["90.0000","90000.0000"]


def test_revisor_retorno_contexto_sem_alias_entrada(tmp_path):
    source = setup_source(tmp_path)
    frame = read(source)["exercicios_reportados"]
    source[2][-1].celulas[0]["raw"]["VERSAO"] = "999"
    assert frame.contexto_politica.iloc[-1]["celula_CVM"]["raw"]["VERSAO"] == "2"
