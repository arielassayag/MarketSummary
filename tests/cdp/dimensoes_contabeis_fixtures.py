"""DADOS SIMULADOS; casos finitos, sem gerador de mercado, seed ou coleta."""

from datetime import UTC, date, datetime

import pandas as pd

POLITICA = "BCRA_DADOS_SIMULADOS"
PODER = "2026-06-30"
PAR = {"politica_contabil_id": POLITICA, "poder_aquisitivo_data": PODER}
DIA = date(2026, 10, 8)
CORTE = datetime(2026, 10, 8, 22, tzinfo=UTC)


def fato(inicio, fim, value, *, item="lucro_liquido_controladores", tipado=True, observado=True):
    out = dict(
        entidade="SIMULADO",
        issuer_id="SIMULADO",
        demonstrativo="DRE",
        item=item,
        period_start=inicio,
        period_end=fim,
        value=value,
        currency="ARS",
        received_date="2026-10-08T21:00:00+00:00" if observado else "2026-09-01",
        version=1,
        documento="DADOS SIMULADOS",
        url="https://example.invalid/DADOS_SIMULADOS",
        consolidado=True,
        anual=False,
        fonte="RI",
        sha256="0" * 64,
        pit_estimado=False,
        nota="DADOS SIMULADOS; não é documento ou lucro real",
    )
    if tipado:
        out.update(PAR)
    if observado:
        out.update(
            disponibilidade_tipo="recepcao_observada",
            disponivel_desde="2026-10-08T21:00:00+00:00",
            data_recebimento_documento=None,
            data_publicacao_primaria=None,
        )
    return out


def semestre(**kw):
    return [
        fato("2025-01-01", "2025-06-30", 30.0, **kw),
        fato("2025-01-01", "2025-12-31", 100.0, **kw),
        fato("2026-01-01", "2026-06-30", 60.0, **kw),
    ]


def trimestres(**kw):
    return [
        fato(s, e, v, **kw)
        for s, e, v in [
            ("2025-07-01", "2025-09-30", 5.0),
            ("2025-10-01", "2025-12-31", 6.0),
            ("2026-01-01", "2026-03-31", 7.0),
            ("2026-04-01", "2026-06-30", 8.0),
        ]
    ]


def selecionar(rows):
    from unittest.mock import patch

    from cdp.data import publico_fatos

    with patch.object(publico_fatos, "_agora_observado", lambda: CORTE):
        out = publico_fatos.selecionar_pit(pd.DataFrame(rows), DIA, conhecimento_ate=CORTE)
    if not out.empty:
        out["issuer_id"] = "SIMULADO"
    return out


def coletor(rows):
    """API pública integral, com provider/arquivo SIMULADOS só em memória.

    Não é um extrator Galicia. O parser é a fronteira injetada de fatos simulados;
    selector, QA, refazer derivados e filtro final são os callables normais.
    Nenhum registro de arquivo, bytes financeiros ou captura é gerado em disco.
    """
    import hashlib
    from types import SimpleNamespace
    from unittest.mock import patch

    from cdp.data import publico, publico_fatos

    raw = b"DADOS SIMULADOS - provider contratual, nao e um PDF primario"
    recebido = datetime(2026, 10, 8, 21, tzinfo=UTC)
    reg = SimpleNamespace(
        sha256=hashlib.sha256(raw).hexdigest(), data_coleta=recebido, limite_captura=recebido
    )
    doc = dict(
        documento="DADOS SIMULADOS",
        url="https://example.invalid/DADOS_SIMULADOS",
        disponibilidade_tipo="recepcao_observada",
    )

    class ArquivoMemoria:
        offline = True
        conhecimento_ate = CORTE

        def __init__(self):
            self.falhas = []

        def chaves(self):
            return []

        def obter(self, chave, fonte, url, baixar, **kwargs):
            if not chave.startswith("RI/demonstrativos/") or fonte != "RI" or url != doc["url"]:
                raise AssertionError("fonte fora da fixture finita")
            kwargs["validar"](raw)
            return reg, raw

    def parser(_raw, _doc, **_kwargs):
        out = pd.DataFrame(rows).copy(deep=True)
        out["entidade"] = "RI:SIMULADO"
        return out

    uni = SimpleNamespace(issuers=pd.DataFrame(index=["SIMULADO"]))
    mestre = pd.DataFrame(index=["SIMULADO"], columns=["cnpj", "cik"])
    with (
        patch.object(publico, "_arquivo", lambda *_args: ArquivoMemoria()),
        patch.object(publico, "mestre_publico", lambda *_args, **_kw: mestre),
        patch.object(publico.ri_pdf, "documentos_ri", lambda *_args: [doc]),
        patch.object(publico.ri_pdf, "fatos_pdf_ri", parser),
        patch.object(publico_fatos, "_agora_observado", lambda: CORTE),
    ):
        return publico.demonstrativos(
            ["SIMULADO"],
            DIA,
            offline=True,
            universe=uni,
            complementar_yahoo=False,
            selecionar_ri_observado=True,
            conhecimento_ate=CORTE,
            http_get=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("rede proibida")
            ),
        )
