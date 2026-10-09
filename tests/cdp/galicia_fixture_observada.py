"""Transporte offline: bytes primários reais; novos recibos DADOS SIMULADOS."""

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from cdp.cobertura.disponibilidade_demonstrativos import RegistroParticipantes
from cdp.cobertura.temporal import construir
from cdp.data import publico, publico_galicia
from cdp.data.publico_arquivo import RegistroArquivo
from cdp.universe import Universe

PDFS = Path(__file__).resolve().parent / "fixtures/galicia"
DIA = date(2026, 10, 8)
JUNHO = datetime(2026, 10, 9, 0, 10, 0, 123456, tzinfo=UTC)
ANUAL = datetime(2026, 10, 9, 0, 11, 0, 123456, tzinfo=UTC)
CORTE = datetime(2026, 10, 9, 0, 12, tzinfo=UTC)


def registro(papel, recebido=None, precisao="microseconds"):
    pin = publico_galicia.PINS[papel]
    return RegistroArquivo(
        f"RI/demonstrativos/AR_GALICIA/{pin['documento']}",
        "RI",
        pin["url"],
        "DADOS_SIMULADOS/" + pin["documento"],
        pin["sha256"],
        pin["bytes"],
        recebido or (JUNHO if papel == "junho" else ANUAL),
        precisao,
    )


def documento():
    return next(
        d
        for d in publico.ri_pdf.documentos_ri("AR_GALICIA", DIA)
        if d.get("extrator") == publico_galicia.EXTRATOR_ID
    )


def corpos():
    return {
        role: (PDFS / pin["documento"]).read_bytes() for role, pin in publico_galicia.PINS.items()
    }


def fatos():
    data = corpos()
    return publico_galicia.fatos_pdf_observado(
        data["junho"], registro("junho"), data["anual"], registro("anual"), documento()
    )


def universo():
    lines = pd.DataFrame(
        [
            dict(
                issuer_id="AR_GALICIA",
                line_type="LOCAL",
                country="AR",
                currency="ARS",
                market="BYMA",
                primary_line=True,
                adr_ratio=1.0,
            )
        ],
        index=["GGAL.BA"],
    )
    issuers = pd.DataFrame(
        [
            dict(
                issuer_name="Grupo Financiero Galicia S.A.",
                country="AR",
                gics_sector="Financials",
                primary_ticker="GGAL.BA",
                local_currency="ARS",
            )
        ],
        index=["AR_GALICIA"],
    )
    return Universe(lines, issuers, "DADOS SIMULADOS UNIVERSE - sem preços")


class ArquivoMemoria:
    """Apenas transporte/RegistroArquivo; nunca substitui parser/seletor/consumidor."""

    offline = True

    def __init__(self, *, corte=CORTE, dados=None, registros=None, ausente=None):
        self.falhas = []
        self.conhecimento_ate = corte
        self.dados = corpos() if dados is None else dados
        self.registros = (
            {r: registro(r) for r in ("junho", "anual")} if registros is None else registros
        )
        self.ausente = ausente
        self.pedidos = []

    def chaves(self, prefixo=""):
        return []

    def buscar(self, *_args, **_kwargs):
        return None

    def obter(self, chave, fonte, url, baixar, **kwargs):
        self.pedidos.append((chave, fonte, url))
        for role, reg in self.registros.items():
            if chave == registro(role).chave:
                if role == self.ausente:
                    return None
                body = self.dados[role]
                # Como Arquivo.obter real: a validação é sempre a callable ordinária recebida.
                kwargs["validar"](body)
                return reg, body
        return None  # Fontes não recebidas não viram dados/zeros, nem chamam rede.


def coletor(monkeypatch, *, arquivo=None, corte=CORTE, ativo=True):
    arq = arquivo or ArquivoMemoria(corte=corte)
    monkeypatch.setattr(publico, "_arquivo", lambda *_args: arq)

    def sem_rede(*_args, **_kwargs):
        raise AssertionError("rede proibida; transporte offline DADOS SIMULADOS")

    out = publico.demonstrativos(
        ["AR_GALICIA"],
        DIA,
        offline=True,
        universe=universo(),
        complementar_yahoo=False,
        selecionar_ri_observado=ativo,
        conhecimento_ate=corte if ativo else None,
        http_get=sem_rede,
    )
    return out, arq


def row_ttm(frame):
    return frame[
        frame.item.eq("lucro_liquido_controladores")
        & frame.freq.eq("TTM")
        & frame.period_end.eq(pd.Timestamp("2026-06-30"))
    ].iloc[0]


def pacote(row, corte=CORTE, *, fonte=None):
    pac = dict(
        issuer_id="AR_GALICIA",
        as_of=DIA.isoformat(),
        corte_temporal=construir(DIA, corte),
        **{"t.lucro_liquido_controladores": float(row.value)},
    )
    reg = RegistroParticipantes("AR_GALICIA")
    reg.registrar(row, "t.lucro_liquido_controladores", fonte=fonte)
    reg.finalizar(pac)
    return pac


__all__ = [
    "replace",
    "DIA",
    "JUNHO",
    "ANUAL",
    "CORTE",
    "registro",
    "documento",
    "corpos",
    "fatos",
    "universo",
    "ArquivoMemoria",
    "coletor",
    "row_ttm",
    "pacote",
]
