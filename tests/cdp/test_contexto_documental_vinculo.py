"""PDFs primários reais; somente transporte/recepções DADOS SIMULADOS.

Autoria do candidato: P0 bancos. Não são nova revisão independente do candidato.
Nenhum path privado ou função alvo injetada: imports normais e APIs normais.
"""

from copy import deepcopy
from decimal import Decimal, localcontext

import galicia_fixture_observada as galicia
import pytest
import supervielle_fixture_observada as supervielle

from cdp.cobertura.disponibilidade_demonstrativos import _grupos, conferir
from cdp.cobertura.insumos import Demonstrativos, _prov_linha
from cdp.data.dimensoes_contabeis import dimensoes
from cdp.data.publico_contexto_documental import contexto_composicao, contexto_documental


@pytest.fixture(scope="module", params=[galicia, supervielle], ids=["galicia", "supervielle"])
def normal(request):
    modulo = request.param
    with pytest.MonkeyPatch.context() as patch:
        frame, _ = modulo.coletor(patch)
    row = modulo.row_ttm(frame).copy()
    assert conferir(modulo.pacote(row))[0]
    return modulo, frame, row


def test_valor_original_Decimal_e_fonte_formatada_normais(normal):
    modulo, frame, row = normal
    with localcontext() as ctx:
        ctx.prec = 80
        if modulo is galicia:
            parcelas = list(map(Decimal, ("329308168000", "229072116000", "437224719000")))
        else:
            parcelas = list(map(Decimal, ("-5371246000", "-56766551000", "29405976000")))
        esperado = parcelas[0] + parcelas[1] - parcelas[2]
    filhos = _grupos(row)[0][1]
    assert [Decimal(str(c["valor"])) for c in filhos] == parcelas
    assert [c["coeficiente"] for c in filhos] == [1.0, 1.0, -1.0]
    assert Decimal(str(row.value)) == esperado
    assert conferir(modulo.pacote(row, fonte=_prov_linha(row)))[0]
    for _, primario in frame[frame.freq.eq("A")].iterrows():
        # Documento de proveniência é rótulo; não deve virar filename por heurística.
        fonte = _prov_linha(primario)
        copia = primario.copy()
        copia["fonte"] = fonte
        assert contexto_documental(copia) == contexto_documental(primario)


def test_aliases_valor_explicito_recusam_zero_ausente_naive_numerico(normal):
    _, _, row = normal
    value = row.value
    alias = deepcopy(row.to_dict())
    alias.pop("value")
    alias["valor"] = value
    assert contexto_documental(alias)
    for key in ("value", "valor"):
        for invalido in (0, None, float("nan"), float("inf"), True, float(Decimal(str(value)) + Decimal("1"))):
            alterado = deepcopy(row.to_dict())
            alterado[key] = invalido
            with pytest.raises(ValueError):
                contexto_documental(alterado)
    # O formato de proveniência não transmite valor; isso é ausência preservada.
    fonte = _prov_linha(row)
    assert "value" not in fonte and "valor" not in fonte
    assert contexto_documental(fonte)


def test_segundo_e_ultimo_componentes_realmente_consumidos(normal):
    modulo, _, row = normal
    for posicao in (1, 2):
        for key, invalido in (("sha256", "0" * 64), ("url", "https://invalid.test/nao-documento"),
                              ("documento", "OUTRO_DOCUMENTO_DADOS_SIMULADOS.pdf")):
            filhos = deepcopy(_grupos(row)[0][1])
            filhos[posicao]["fonte"][key] = invalido
            changed = row.copy()
            changed["componentes_fluxo"] = filhos
            try:
                aceito, _ = conferir(modulo.pacote(changed))
            except ValueError:
                aceito = False
            assert not aceito


def test_fonte_identificadores_omitidos_nao_sao_inventados(normal):
    modulo, _, row = normal
    filhos = deepcopy(_grupos(row)[0][1])
    for c in filhos:
        for key in ("sha256", "url", "documento"):
            c["fonte"].pop(key)
    changed = row.copy()
    changed["componentes_fluxo"] = filhos
    assert conferir(modulo.pacote(changed))[0]
    assert all(not {"sha256", "url", "documento"} & set(c["fonte"]) for c in filhos)


def test_cabecalho_e_fonte_agregada_sha_url_explicitos_conferem(normal):
    modulo, _, row = normal
    for key, invalido in (("sha256", "0" * 64), ("url", "https://invalid.test/nao-documento")):
        changed = row.copy()
        changed[key] = invalido
        with pytest.raises(ValueError):
            contexto_documental(changed)
        fonte = _prov_linha(row)
        fonte[key] = invalido
        try:
            aceito, _ = conferir(modulo.pacote(row, fonte=fonte))
        except ValueError:
            aceito = False
        assert not aceito


def test_roundtrip_agregado_filhos_e_contextos_preservados(normal):
    modulo, _, row = normal
    pack = modulo.pacote(row, fonte=_prov_linha(row))
    import json

    reaberto = json.loads(json.dumps(pack))
    assert conferir(reaberto)[0]
    assert reaberto == pack
    assert row.contexto_documental["pit_certificado"] is False
    assert row.contexto_documental["publicacao_primaria"] is None


def test_componente_com_fonte_formatada_nativa_do_consumidor(normal):
    modulo, frame, _ = normal
    consumer = Demonstrativos(frame, modulo.universo().issuers.index[0])
    anual = consumer.df[consumer.df.freq.eq("A")].iloc[0]
    # Mesma representação de componentes() em Demonstrativos._ttm_derivado,
    # usando linha anual A real selecionada; nenhum trimestre/freq/start criado.
    componente = {
        "item": str(anual["item"]), "freq": str(anual["freq"]),
        "period_end": anual.period_end.date().isoformat(),
        "valor": float(anual.value), "coeficiente": 1.0,
        "fonte": _prov_linha(anual), **dimensoes(anual), **contexto_documental(anual),
    }
    assert componente["fonte"]["documento"] != anual.documento
    assert contexto_documental(componente)
    # Guardar ausência de start/currency/consolidado no componente periódico.
    assert not {"period_start", "currency", "consolidado"} & set(componente)
    contexto = contexto_composicao([componente])
    agregado = frame[frame.freq.eq("TTM") & frame.period_end.eq(anual.period_end)].iloc[0].copy()
    agregado["componentes_fluxo"] = [componente]
    for key, value in contexto.items():
        agregado[key] = value
    assert conferir(modulo.pacote(agregado))[0]
    errado = deepcopy(componente)
    errado["fonte"]["documento"] = errado["fonte"]["documento"].replace(str(anual.documento), "OUTRO_DOCUMENTO.pdf")
    with pytest.raises(ValueError):
        contexto_documental(errado)


def test_contexto_ausente_legado_literal():
    for row in ({}, {"value": None}, {"value": 0}, {"value": 12.5, "documento": "rótulo legado"}):
        before = deepcopy(row)
        assert contexto_documental(row) == {}
        assert row == before


def test_mistura_perfis_nao_empresta_identidade_documental():
    with pytest.MonkeyPatch.context() as patch:
        fg, _ = galicia.coletor(patch)
    with pytest.MonkeyPatch.context() as patch:
        fs, _ = supervielle.coletor(patch)
    pg = deepcopy(_grupos(galicia.row_ttm(fg))[0][1][0])
    ps = deepcopy(_grupos(supervielle.row_ttm(fs))[0][1][0])
    assert contexto_documental(pg) and contexto_documental(ps)
    with pytest.raises(ValueError):
        contexto_composicao([pg, ps])
