"""Oito controles novos de tipo owners; entradas artificiais DADOS SIMULADOS.

Importação normal dos módulos físicos completos. Sentinelas apenas negam
fronteiras de efeito e política; não fornecem dados ou cálculos substitutos.
"""

import json
import os
import re
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime
from inspect import signature
from pathlib import Path

import pytest

from cdp.cobertura import fontes, ri_observada, temporal
from cdp.data import publico

_CONTAGENS: ContextVar[dict[str, int] | None] = ContextVar("owners_efeitos", default=None)
_MENSAGEM = "patrimonio_owners_observado exige bool explícito"


def _auditar_efeitos(evento, _args):
    contagens = _CONTAGENS.get()
    if contagens is None:
        return
    if evento == "open" or evento.startswith(("socket.", "subprocess.", "os.exec")):
        contagens["auditoria_efeitos"] += 1
        raise AssertionError(f"Efeito proibido no controle de flag: {evento}")
    if evento in {"os.system", "os.remove", "os.rename", "os.mkdir", "os.rmdir"}:
        contagens["auditoria_efeitos"] += 1
        raise AssertionError(f"Escrita proibida no controle de flag: {evento}")


sys.addaudithook(_auditar_efeitos)


@contextmanager
def _negar_efeitos(contagens):
    token = _CONTAGENS.set(contagens)
    try:
        yield
    finally:
        _CONTAGENS.reset(token)


class _BoolObservavel:
    def __init__(self, contagens):
        self.contagens = contagens

    def __bool__(self):
        self.contagens["bool_hook"] += 1
        raise AssertionError("Truthiness proibida: objeto DADOS SIMULADOS")

    @property
    def __class__(self):
        self.contagens["class_hook"] += 1
        raise AssertionError("Getter __class__ proibido: objeto DADOS SIMULADOS")


def _fronteira_negada(contagens, nome):
    def negar(*_args, **_kwargs):
        contagens[nome] += 1
        raise AssertionError(f"Fronteira proibida no controle de flag: {nome}")

    return negar


@pytest.mark.parametrize(
    ("api", "entrada"),
    [
        pytest.param("publico", "int", id="OWNFLAG_PUBLICO_INT"),
        pytest.param("publico", "text", id="OWNFLAG_PUBLICO_TEXT"),
        pytest.param("publico", "null", id="OWNFLAG_PUBLICO_NULL"),
        pytest.param("publico", "bool_hook", id="OWNFLAG_PUBLICO_BOOL_HOOK"),
        pytest.param("coleta", "int", id="OWNFLAG_COLETA_INT"),
        pytest.param("coleta", "text", id="OWNFLAG_COLETA_TEXT"),
        pytest.param("coleta", "null", id="OWNFLAG_COLETA_NULL"),
        pytest.param("coleta", "bool_hook", id="OWNFLAG_COLETA_BOOL_HOOK"),
    ],
)
def test_flag_owners_exige_bool_antes_de_efeitos(api, entrada, monkeypatch, record_property):
    origem = Path(os.environ.get("CDP_OWNERS_TEST_IMPORT_ROOT", Path(__file__).resolve().parents[2]))
    for modulo in (publico, fontes, ri_observada, temporal):
        assert Path(modulo.__file__).resolve().is_relative_to((origem / "src").resolve())
    for funcao in (publico.demonstrativos, fontes.coletar):
        assert signature(funcao).parameters["patrimonio_owners_observado"].default is False

    contagens = dict.fromkeys(
        ["arquivo", "coleta", "disponibilidade", "ri", "temporal", "bool_hook",
         "class_hook", "auditoria_efeitos"],
        0,
    )
    for modulo, atributo, nome in [
        (publico, "_arquivo", "arquivo"),
        (fontes, "_coletar", "coleta"),
        (fontes, "disponibilidade_observada", "disponibilidade"),
        (ri_observada, "ativo", "ri"),
        (temporal, "ativo", "temporal"),
    ]:
        monkeypatch.setattr(modulo, atributo, _fronteira_negada(contagens, nome))
    valor = {"int": 1, "text": "false", "null": None}.get(entrada)
    if entrada == "bool_hook":
        valor = _BoolObservavel(contagens)

    try:
        with _negar_efeitos(contagens), pytest.raises(ValueError, match=f"^{re.escape(_MENSAGEM)}$"):
            if api == "publico":
                publico.demonstrativos(
                    [], date(2026, 10, 10), offline=True, selecionar_ri_observado=True,
                    conhecimento_ate=datetime(2026, 10, 10, 10, 0, tzinfo=UTC),
                    patrimonio_owners_observado=valor,
                )
            else:
                fontes.coletar(None, date(2026, 10, 10), [], [], [], offline=True,
                               patrimonio_owners_observado=valor)
    finally:
        record_property("origem_importacao", str(origem.resolve()))
        record_property("efeitos_e_fronteiras", json.dumps(contagens, sort_keys=True))
    assert all(contagem == 0 for contagem in contagens.values())
