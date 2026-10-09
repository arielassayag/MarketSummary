"""DADOS SIMULADOS — ledger documental CVM separado de qualquer seleção financeira."""

import copy
import csv
import hashlib
import io
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from cdp.data import publico_cvm as cvm
from cdp.data import publico_cvm_comparativos as comparisons
from cdp.data.publico_arquivo import Arquivo, RegistroArquivo

CNPJ = "11.111.111/0001-11"
T0 = datetime(2026, 10, 7, 12, tzinfo=UTC)
CUT = T0 + timedelta(days=1)


def _csv(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=";", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("latin-1")


def _raw(year=2025, order="ÚLTIMO", value="200.0000000000"):
    period = year if order == "ÚLTIMO" else year - 1
    return dict(
        CNPJ_CIA=CNPJ,
        DT_REFER=f"{year}-12-31",
        VERSAO="1",
        DENOM_CIA="DADOS SIMULADOS S.A.",
        CD_CVM="099999",
        GRUPO_DFP="DF Consolidado",
        MOEDA="REAL",
        ESCALA_MOEDA="MIL",
        ORDEM_EXERC=order,
        DT_INI_EXERC=f"{period}-01-01",
        DT_FIM_EXERC=f"{period}-12-31",
        CD_CONTA="3.01",
        DS_CONTA="Receita de Venda de Bens e/ou Serviços",
        VL_CONTA=value,
        ST_CONTA_FIXA="S",
    )


def _zip(rows=None, year=2025, indices=None):
    rows = rows or [_raw(year), _raw(year, "PENÚLTIMO", "100.0000000000")]
    indices = (
        indices
        if indices is not None
        else [
            dict(
                CNPJ_CIA=CNPJ,
                DT_REFER=f"{year}-12-31",
                VERSAO="1",
                DT_RECEB="2026-03-25",
                ID_DOC="155000",
                LINK_DOC="https://publico.exemplo/documento/155000",
            )
        ]
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        if indices:
            archive.writestr(f"dfp_cia_aberta_{year}.csv", _csv(indices))
        archive.writestr(f"dfp_cia_aberta_DRE_con_{year}.csv", _csv(rows))
    return stream.getvalue()


def _record(body, year=2025, time=T0):
    return RegistroArquivo(
        chave=f"CVM/DFP/dfp_cia_aberta_{year}.zip",
        fonte="CVM",
        url=cvm.url_zip("DFP", year),
        caminho=f"CVM/DFP/{year}.zip",
        sha256=hashlib.sha256(body).hexdigest(),
        bytes=len(body),
        data_coleta=time,
        precisao="microseconds",
    )


def _read(body, record=None, cutoff=CUT, contexts=(), year=2025, cnpjs=(CNPJ,)):
    return cvm.ler_zip_demonstracoes(
        body,
        "DFP",
        year,
        cnpjs,
        conservar_comparativos=True,
        registro_comparativos=record or _record(body, year),
        conhecimento_ate=cutoff,
        contextos_politica=contexts,
    )


def _pdf(text="DADOS SIMULADOS politica documental"):
    content = f"BT /F1 12 Tf 20 750 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    body = b"%PDF-1.4\n"
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n"
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return body + f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


def _context(row, time=T0 + timedelta(hours=1)):
    body = _pdf()
    record = RegistroArquivo(
        chave="RI/politica/exemplo.pdf",
        fonte="RI",
        url="https://ri.exemplo/documento.pdf",
        caminho="RI/exemplo.pdf",
        sha256=hashlib.sha256(body).hexdigest(),
        bytes=len(body),
        data_coleta=time,
        precisao="microseconds",
    )
    cell = {
        "source_sha256": row["source_sha256"],
        "membro": row["localizador"]["membro"],
        "linha_csv_1_based": row["localizador"]["linha_csv_1_based"],
        "raw": copy.deepcopy(row["raw"]),
    }
    return comparisons.ContextoPoliticaCVM(
        record, body, ((1, "DADOS SIMULADOS politica documental"),), (cell,)
    )


def test_optin_preserva_ambos_e_fatos_padrao_literais():
    body = _zip()
    legacy = cvm.ler_zip_demonstracoes(body, "DFP", 2025, (CNPJ,))
    explicit = cvm.ler_zip_demonstracoes(body, "DFP", 2025, (CNPJ,), conservar_comparativos=False)
    opted = _read(body)
    assert "exercicios_reportados" not in legacy
    for key in legacy:
        pd.testing.assert_frame_equal(legacy[key], explicit[key])
        pd.testing.assert_frame_equal(legacy[key], opted[key])
    pd.testing.assert_frame_equal(cvm.fatos_cvm(legacy, "DFP"), cvm.fatos_cvm(opted, "DFP"))
    ledger = opted["exercicios_reportados"]
    assert list(ledger.columns) == comparisons.COLUNAS_EXERCICIOS
    assert list(ledger.ordem_exercicio) == ["ÚLTIMO", "PENÚLTIMO"]
    assert list(ledger.period_end) == ["2025-12-31", "2024-12-31"]
    assert ledger.referencia_documento.eq("2025-12-31").all()
    assert ledger.version_literal.eq("1").all() and ledger.id_doc.eq("155000").all()
    assert ledger.data_recebimento_documento.eq("2026-03-25").all()
    assert ledger.contexto_politica.isna().all() and ledger.data_publicacao_primaria.isna().all()
    assert list(ledger.localizador.map(lambda v: v["linha_csv_1_based"])) == [2, 3]
    assert all("DENOM_CIA" in value for value in ledger.raw)


def test_arquivo_fisico_nativo_offline(tmp_path):
    body = _zip()
    writer = Arquivo(tmp_path, agora=lambda: T0)
    record = writer.gravar(
        _record(body).chave, "CVM", cvm.url_zip("DFP", 2025), body, data_coleta=T0
    )
    archive = Arquivo(tmp_path, offline=True, conhecimento_ate=CUT)
    stored = archive.buscar(record.chave, CUT.date())
    ledger = _read(archive.ler(stored), stored)["exercicios_reportados"]
    assert ledger.source_sha256.eq(record.sha256).all()
    assert ledger.recibo_origem.iloc[0] == stored.como_dict()


@pytest.mark.parametrize("value", [None, "0", "0.0000000000", "-1.0000000000"])
def test_ausencia_zero_negativo_lexemas_preservados(value):
    ledger = _read(_zip([_raw(value=value)]))["exercicios_reportados"]
    assert ledger.valor_reportado.iloc[0] == value


def test_indice_ausente_nao_inventa_filing_recebimento():
    row = _read(_zip(indices=[]))["exercicios_reportados"].iloc[0]
    assert (
        row.id_doc is None
        and row.indice_documento is None
        and row.data_recebimento_documento is None
    )


def test_filtro_cnpj_e_ordem_desconhecida_sem_promocao():
    other = _raw()
    other["CNPJ_CIA"] = "22.222.222/0001-22"
    unknown = _raw()
    unknown["ORDEM_EXERC"] = "ANTEPENÚLTIMO"
    ledger = _read(_zip([_raw(), other, unknown]))["exercicios_reportados"]
    assert len(ledger) == 1 and ledger.entidade.iloc[0] == CNPJ


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "0" * 64),
        ("bytes", 1),
        ("chave", "CVM/ITR/x.zip"),
        ("url", "https://dados.cvm.gov.br/incorreto.zip"),
        ("fonte", "RI"),
        ("data_coleta", T0.replace(tzinfo=None)),
        ("data_coleta", datetime(2099, 1, 1, tzinfo=UTC)),
        ("precisao", "unknown"),
    ],
)
def test_recibo_bytes_rota_fonte_tempo_recusados(field, value):
    body = _zip()
    with pytest.raises(ValueError):
        _read(body, replace(_record(body), **{field: value}))


@pytest.mark.parametrize("delta,accepted", [(-1, False), (0, True), (1, True)])
def test_corte_utc_antes_exato_depois(delta, accepted):
    body = _zip()
    cutoff = T0 + timedelta(microseconds=delta)
    if accepted:
        assert len(_read(body, cutoff=cutoff)["exercicios_reportados"]) == 2
    else:
        with pytest.raises(ValueError):
            _read(body, cutoff=cutoff)


def test_precisao_segundos_usa_limite_superior():
    body = _zip()
    record = replace(_record(body), precisao="seconds")
    with pytest.raises(ValueError):
        _read(body, record, cutoff=T0)
    assert (
        _read(body, record, cutoff=T0 + timedelta(seconds=1))["exercicios_reportados"]
        .disponivel_desde.eq((T0 + timedelta(seconds=1)).isoformat())
        .all()
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("VERSAO", ""),
        ("MOEDA", ""),
        ("ESCALA_MOEDA", ""),
        ("CD_CONTA", ""),
        ("DT_INI_EXERC", "2026-01-01"),
        ("DT_FIM_EXERC", "2026-12-31"),
        ("DT_REFER", "2024-12-31"),
        ("VL_CONTA", "NaN"),
    ],
)
def test_celula_invalida_recusada_somente_ledger_optin(field, value):
    raw = _raw()
    raw[field] = value
    with pytest.raises(ValueError):
        _read(_zip([raw]))


def test_indice_contraditorio_recusado():
    first = dict(
        CNPJ_CIA=CNPJ,
        DT_REFER="2025-12-31",
        VERSAO="1",
        DT_RECEB="2026-03-25",
        ID_DOC="1",
        LINK_DOC="https://u/1",
    )
    second = {**first, "ID_DOC": "2"}
    with pytest.raises(ValueError, match="Índice CVM contraditório"):
        _read(_zip(indices=[first, second]))


def test_zero_original_e_comparativo_posterior_conflito_lado_a_lado():
    original = _read(_zip([_raw(2024, value="0")], year=2024), year=2024)["exercicios_reportados"]
    later = _read(_zip())["exercicios_reportados"]
    combined = comparisons.expor_conflitos([original, later])
    same_period = combined[combined.period_end.eq("2024-12-31")]
    assert list(same_period.valor_reportado) == ["0", "100.0000000000"]
    assert same_period.conflito_reportado.all() and len(same_period.fontes_em_conflito.iloc[0]) == 2
    assert list(same_period.referencia_documento) == ["2024-12-31", "2025-12-31"]
    assert len(combined) == len(original) + len(later)


def test_contexto_documental_fisico_sem_politica_declarada():
    body = _zip()
    row = _read(body)["exercicios_reportados"].iloc[1].to_dict()
    context = _context(row)
    linked = _read(body, contexts=(context,))["exercicios_reportados"]
    assert linked.contexto_politica.iloc[0] is None
    policy = linked.contexto_politica.iloc[1]
    assert policy["document_sha256"] == hashlib.sha256(context.conteudo).hexdigest()
    assert policy["celula_CVM"]["raw"] == row["raw"]
    assert policy["perimetro_economico_constante"] is None
    assert linked.disponivel_desde.iloc[1] == context.registro.limite_captura.isoformat()


@pytest.mark.parametrize(
    "field,value",
    [
        ("CNPJ_CIA", "22.222.222/0001-22"),
        ("VERSAO", "2"),
        ("MOEDA", "DOLAR"),
        ("ESCALA_MOEDA", "UNIDADE"),
        ("DT_FIM_EXERC", "2023-12-31"),
        ("VL_CONTA", "0"),
    ],
)
def test_contexto_nao_pode_contradizer_celula(field, value):
    body = _zip()
    context = _context(_read(body)["exercicios_reportados"].iloc[1].to_dict())
    context.celulas[0]["raw"][field] = value
    with pytest.raises(ValueError, match="Contexto contradiz"):
        _read(body, contexts=(context,))


@pytest.mark.parametrize("change", ["sha", "anchor", "page", "naive", "future", "partial"])
def test_contexto_adulterado_ou_parcial_recusado(change):
    body = _zip()
    context = _context(_read(body)["exercicios_reportados"].iloc[1].to_dict())
    if change == "sha":
        context = replace(context, conteudo=context.conteudo + b"x")
    if change == "anchor":
        context = replace(context, ancoras=((1, "politica inexistente"),))
    if change == "page":
        context = replace(context, ancoras=((2, "DADOS SIMULADOS"),))
    if change == "naive":
        context = replace(
            context, registro=replace(context.registro, data_coleta=T0.replace(tzinfo=None))
        )
    if change == "future":
        context = replace(
            context,
            registro=replace(context.registro, data_coleta=datetime(2099, 1, 1, tzinfo=UTC)),
        )
    if change == "partial":
        context = replace(context, ancoras=())
    with pytest.raises(ValueError):
        _read(body, contexts=(context,))


def test_corte_apos_zip_antes_contexto_e_ultimo_contexto_adulterado():
    body = _zip()
    rows = _read(body)["exercicios_reportados"].to_dict("records")
    first, last = _context(rows[0]), _context(rows[1])
    with pytest.raises(ValueError, match="Recepção observada"):
        _read(body, cutoff=T0, contexts=(first,))
    last = replace(last, conteudo=last.conteudo + b"adulterado")
    with pytest.raises(ValueError, match="Bytes/SHA"):
        _read(body, contexts=(first, last))


def test_opcao_explicitamente_tipado_sem_metadata_silencioso():
    body = _zip()
    with pytest.raises(ValueError):
        cvm.ler_zip_demonstracoes(body, "DFP", 2025, conservar_comparativos="sim")
    with pytest.raises(ValueError):
        cvm.ler_zip_demonstracoes(body, "DFP", 2025, registro_comparativos=_record(body))
    with pytest.raises(ValueError):
        cvm.ler_zip_demonstracoes(body, "DFP", 2025, conservar_comparativos=True)


def test_contexto_retorno_nao_alias_celula_do_caller():
    body = _zip()
    context = _context(_read(body)["exercicios_reportados"].iloc[1].to_dict())
    returned = _read(body, contexts=(context,))["exercicios_reportados"].iloc[1]
    context.celulas[0]["raw"]["VL_CONTA"] = "999"
    assert returned.contexto_politica["celula_CVM"]["raw"]["VL_CONTA"] == "100.0000000000"


def test_pdf_invalido_com_sha_valido_e_tipo_corpo_recusados():
    body = _zip()
    context = _context(_read(body)["exercicios_reportados"].iloc[1].to_dict())
    invalid = b"nao e PDF"
    context = replace(
        context,
        conteudo=invalid,
        registro=replace(
            context.registro, bytes=len(invalid), sha256=hashlib.sha256(invalid).hexdigest()
        ),
    )
    with pytest.raises(ValueError, match="Contexto PDF inválido"):
        _read(body, contexts=(context,))
    with pytest.raises(ValueError, match="Corpo de origem exige bytes"):
        comparisons.conservar_exercicios("nao-bytes", "DFP", 2025, (CNPJ,), _record(body), CUT)


def test_saldo_sem_inicio_preserva_none_e_merge_sem_alias():
    body = _zip([_raw()])
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(body)) as old, zipfile.ZipFile(stream, "w") as new:
        for name in old.namelist():
            if "DRE_con" in name:
                raw = _raw()
                raw.pop("DT_INI_EXERC")
                raw["CD_CONTA"] = "1"
                raw["DS_CONTA"] = "Ativo Total DADOS SIMULADOS"
                new.writestr(name.replace("DRE_con", "BPA_con"), _csv([raw]))
            else:
                new.writestr(name, old.read(name))
    ledger = _read(stream.getvalue())["exercicios_reportados"]
    assert ledger.period_start.iloc[0] is None
    combined = comparisons.expor_conflitos([ledger])
    combined.raw.iloc[0]["VL_CONTA"] = "999"
    assert ledger.raw.iloc[0]["VL_CONTA"] == "200.0000000000"
