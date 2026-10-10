"""DADOS SIMULADOS — ligação DFP não migra para um ZIP ITR com o mesmo NSD."""

import base64
import json
from dataclasses import replace

import pandas as pd
import pytest
from test_notas_cvm_query_literal import (
    ENTITY,
    T0,
    TEXT,
    URL,
    _context,
    _oracle,
    _pdf,
    _read,
    _sha,
    _zip,
    _zip_record,
)

from cdp.data.publico_arquivo import RegistroArquivo
from cdp.data.publico_cvm import ler_zip_demonstracoes, url_zip
from cdp.data.publico_cvm_comparativos import ContextoPoliticaCVM


def _zip_itr():
    import io
    import zipfile

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_zip())) as original, zipfile.ZipFile(output, "w") as archive:
        for name in original.namelist():
            info = zipfile.ZipInfo(name.replace("dfp_cia_aberta", "itr_cia_aberta"),
                                   (2000, 1, 1, 0, 0, 0))
            archive.writestr(info, original.read(name))
    return output.getvalue()


def _registro_itr(body):
    return replace(_zip_record(body), chave="CVM/ITR/itr_cia_aberta_2025.zip",
                   url=url_zip("ITR", 2025), caminho="DADOS_SIMULADOS/itr2025.zip")


def _read_itr(body, contexts=()):
    return ler_zip_demonstracoes(body, "ITR", 2025, (ENTITY,),
                                 conservar_comparativos=True,
                                 registro_comparativos=_registro_itr(body),
                                 conhecimento_ate=T0, contextos_politica=contexts)


def _context_itr(body, *, ri=False):
    pdf = _pdf()
    html = ('<input type="hidden" id="hdnConteudoArquivo" name="hdnConteudoArquivo" '
            'value="' + base64.b64encode(pdf).decode() + '">').encode()
    content = pdf if ri else html
    rec = RegistroArquivo("RI/DADOS_SIMULADOS.pdf" if ri else "CVM/notas/DADOS_SIMULADOS.html",
                           "RI" if ri else "CVM",
                           "https://publico.exemplo/DADOS_SIMULADOS.pdf" if ri else URL,
                           "DADOS_SIMULADOS/contexto", _sha(content), len(content),
                           T0, "microseconds")
    cells = tuple(dict(source_sha256=row["source_sha256"],
                       membro=row["localizador"]["membro"],
                       linha_csv_1_based=row["localizador"]["linha_csv_1_based"],
                       raw=row["raw"])
                  for row in _read_itr(body)["exercicios_reportados"].to_dict("records"))
    return ContextoPoliticaCVM(rec, content, ((1, TEXT),), cells)


def _save(tmp_path, body, registro, contexts, tables):
    (tmp_path / "entrada.zip").write_bytes(body)
    for number, context in enumerate(contexts):
        (tmp_path / f"contexto-{number}.bin").write_bytes(context.conteudo)
    request = dict(registro=registro.como_dict(), corte=T0.isoformat(),
                   contextos=[dict(registro=c.registro.como_dict(), ancoras=c.ancoras,
                                   celulas=c.celulas) for c in contexts],
                   alcance="DADOS SIMULADOS; somente vínculo documental")
    (tmp_path / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2))
    (tmp_path / "oracle.json").write_text(json.dumps(_oracle(tables), ensure_ascii=False, indent=2))


def test_itr_mesmo_nsd_recusa_notas_anuais_cvm(tmp_path):
    body = _zip_itr()
    ctx = _context_itr(body)
    _save(tmp_path, body, _registro_itr(body), (ctx,), _read_itr(body))
    with pytest.raises(ValueError, match="origem documental DFP"):
        _read_itr(body, (ctx,))


def test_dfp_mantem_contexto_integral(tmp_path):
    body = _zip()
    ctx, _ = _context(body)
    result = _read(body, (ctx,))
    rows = result["exercicios_reportados"].to_dict("records")
    assert len(rows) == 2
    for row in rows:
        assert row["contexto_politica"]["celula_CVM"]["raw"] == row["raw"]
        assert row["contexto_politica"]["url"] == URL
    _save(tmp_path, body, _zip_record(body), (ctx,), result)


def test_itr_ri_pdf_direto_permanece(tmp_path):
    body = _zip_itr()
    ctx = _context_itr(body, ri=True)
    result = _read_itr(body, (ctx,))
    for row in result["exercicios_reportados"].to_dict("records"):
        assert row["contexto_politica"]["document_sha256"] == ctx.registro.sha256
        assert row["contexto_politica"]["celula_CVM"]["raw"] == row["raw"]
        assert "numero_sequencial_documento" not in row["contexto_politica"]
    _save(tmp_path, body, _registro_itr(body), (ctx,), result)


def test_itr_sem_contexto_preserva_default_e_ledger(tmp_path):
    body = _zip_itr()
    default = ler_zip_demonstracoes(body, "ITR", 2025, (ENTITY,))
    result = _read_itr(body)
    for key, table in default.items():
        pd.testing.assert_frame_equal(table, result[key])
    rows = result["exercicios_reportados"].to_dict("records")
    assert len(rows) == 2 and all(row["contexto_politica"] is None for row in rows)
    assert all(row["source_url"] == url_zip("ITR", 2025) for row in rows)
    _save(tmp_path, body, _registro_itr(body), (), result)


@pytest.mark.parametrize("bad", [None, "registro_incompativel"], ids=["contexto_none", "registro"])
def test_contexto_parcial_conserva_erro_documental(bad):
    body = _zip_itr()
    context = None if bad is None else replace(_context_itr(body), registro=object())
    with pytest.raises(ValueError, match="Contexto documental parcial|Registro de contexto"):
        _read_itr(body, (context,))
