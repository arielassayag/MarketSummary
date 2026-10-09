"""PDFs primários reais; transporte/recepções DADOS SIMULADOS.

Controles não autores do vínculo explícito entre linha consumida e seu contexto.
Não refazem hashes de contexto ou manifestos, não editam documentos/produtor.
"""

from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pandas as pd
import pytest
from supervielle_fixture_observada import (
    ANUAL,
    CORTE,
    JUNHO,
    ArquivoMemoria,
    coletor,
    pacote,
    registro,
    replace,
    row_ttm,
)

from cdp.cobertura.disponibilidade_demonstrativos import _grupos, conferir
from cdp.cobertura.insumos import _prov_linha


@pytest.mark.parametrize("ultimo", ["junho", "anual"])
def test_maximo_dependencias_nao_depende_ordem_de_recepcao(monkeypatch, ultimo):
    posterior = CORTE + timedelta(seconds=17, microseconds=23)
    regs = {"junho": registro("junho"), "anual": registro("anual")}
    regs[ultimo] = replace(regs[ultimo], data_coleta=posterior)
    corte = posterior + timedelta(microseconds=1)
    arq = ArquivoMemoria(corte=corte, registros=regs)
    frame, _ = coletor(monkeypatch, arquivo=arq, corte=corte)
    row = row_ttm(frame)
    assert pd.Timestamp(row.disponivel_desde) == pd.Timestamp(posterior)
    assert conferir(pacote(row, corte))[0]
    assert not conferir(pacote(row, posterior - timedelta(microseconds=1)))[0]
    assert Decimal(str(row.value)) == (
        Decimal("-56766551") + Decimal("-5371246") - Decimal("29405976")
    ) * Decimal("1000")
    assert JUNHO < ANUAL < posterior


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("sha256", "0" * 64),
        ("documento", "OUTRO_DOCUMENTO_DADOS_SIMULADOS.pdf"),
        ("url", "https://invalid.test/OUTRO_DOCUMENTO_DADOS_SIMULADOS.pdf"),
    ],
)
def test_fonte_nativa_explicita_contraditoria_nao_vira_proveniencia_valida(monkeypatch, campo, valor):
    frame, _ = coletor(monkeypatch)
    original = row_ttm(frame)
    assert conferir(pacote(original))[0]
    adulterada = original.copy()
    componentes = deepcopy(_grupos(original)[0][1])
    componentes[0]["fonte"][campo] = valor
    adulterada["componentes_fluxo"] = componentes
    # O contexto continua intocado e aponta aos PDFs primários recebidos.
    # Apenas a fonte do primeiro componente efetivamente consumido contradiz o PDF.
    try:
        _prov_linha(adulterada, detalhar_fluxos=True)
        aceito, _ = conferir(pacote(adulterada))
    except ValueError:
        aceito = False
    assert not aceito


def test_valor_composto_explicito_nao_contradiz_componentes_preservados(monkeypatch):
    frame, _ = coletor(monkeypatch)
    original = row_ttm(frame)
    assert conferir(pacote(original))[0]
    adulterada = original.copy()
    adulterada["value"] = float(Decimal(str(original.value)) + Decimal("1000"))
    try:
        _prov_linha(adulterada, detalhar_fluxos=True)
        aceito, _ = conferir(pacote(adulterada))
    except ValueError:
        aceito = False
    assert not aceito
