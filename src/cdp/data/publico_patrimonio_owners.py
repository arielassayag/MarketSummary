"""Estoques owners de dois filings June26; não NI, fluxo, ações ou normalização.

O perfil é finito e seus locadores provêm do ledger documental fechado. Cada
novo RegistroArquivo autentica a recepção do mesmo corpo, sem reutilizar UTC
histórico. IDs de política são exatamente os dos perfis correntes do produto.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext

import pandas as pd

from . import publico_galicia as gal
from . import publico_supervielle as sup
from .publico_contexto_documental import (
    ExtracaoRecusada,
    _envelope,
    contexto_documental,
    dependencia,
)
from .publico_supervielle_documento import validar_contexto

# Gerado por código a partir das quatro células do ledger recebido; valores não
# foram obtidos de modelo, EPS, capital monetário ou narrativa de normalização.
CELULAS_DOCUMENTAIS = {
    "AR_GALICIA": [
        {
            "rubrica": "Shareholders' Equity Attributable to Parent Company's Owners",
            "pagina_pdf": 5,
            "rotulo_coluna": "06.30.26",
            "data_estoque": "2026-06-30",
            "lexema": "9,197,638,149",
            "quantum": "1000",
            "sha256": "ff2b65222f2591c8fd9354d05b50020ee8879528233e4b0cce8a9b5b83921886",
        },
        {
            "rubrica": "Shareholders' Equity Attributable to Parent Company's Owners",
            "pagina_pdf": 5,
            "rotulo_coluna": "12.31.25",
            "data_estoque": "2025-12-31",
            "lexema": "9,074,888,664",
            "quantum": "1000",
            "sha256": "ff2b65222f2591c8fd9354d05b50020ee8879528233e4b0cce8a9b5b83921886",
        },
    ],
    "AR_SUPERVIELLE": [
        {
            "rubrica": "Shareholders' Equity attributable to owners of the parent company",
            "pagina_pdf": 6,
            "rotulo_coluna": "06/30/2026",
            "data_estoque": "2026-06-30",
            "lexema": "1,180,450,429",
            "quantum": "1000",
            "sha256": "320a78c3c35e4c62cb957690435d130897f7e3d0ba0ca1696dbc11a427dc67ee",
        },
        {
            "rubrica": "Shareholders' Equity attributable to owners of the parent company",
            "pagina_pdf": 6,
            "rotulo_coluna": "12/31/2025",
            "data_estoque": "2025-12-31",
            "lexema": "1,176,945,446",
            "quantum": "1000",
            "sha256": "320a78c3c35e4c62cb957690435d130897f7e3d0ba0ca1696dbc11a427dc67ee",
        },
    ],
}


def _require(condition, message):
    if not condition:
        raise ExtracaoRecusada(message)


def _norm(value):
    return re.sub(r"\s+([,.;])", r"\1", " ".join(value.split()))


@dataclass(frozen=True)
class Perfil:
    ISSUER_ID: str
    CONTEXTO_SCHEMA: str
    produto: object
    PAPEIS_DEPENDENCIA = ("junho",)
    SUPORTA_COMPOSICAO = False
    DATA_ESTOQUE_COMPROVADA = True

    @property
    def PINS(self):
        return {"junho": self.produto.PINS["junho"]}

    @property
    def POLITICA(self):
        return self.produto.POLITICA

    @property
    def PODER(self):
        return self.produto.PODER

    @property
    def ANCORA(self):
        return deepcopy(gal._ANCORAS if self.produto is gal else sup._ANCORAS)

    def validar_celula(self, ctx, row, roles, presente):
        _validar_celula(self, ctx, row, roles, presente)


PERFIS = {
    "AR_GALICIA": Perfil("AR_GALICIA", "cdp.galicia.patrimonio_owners/v1", gal),
    "AR_SUPERVIELLE": Perfil("AR_SUPERVIELLE", "cdp.supervielle.patrimonio_owners/v1", sup),
}


def perfil_schema(schema):
    for perfil in PERFIS.values():
        if schema == perfil.CONTEXTO_SCHEMA:
            return perfil
    raise ExtracaoRecusada("Perfil de patrimônio desconhecido")


def _celula(perfil, spec):
    with localcontext() as ctx:
        ctx.prec = 80
        value = Decimal(spec["lexema"].replace(",", "")) * Decimal(spec["quantum"])
    return {
        "papel": "estoque_owners_" + spec["data_estoque"],
        "data_estoque": spec["data_estoque"],
        "period_end": spec["data_estoque"],
        "demonstrativo": "BPA",
        "pagina_pdf": spec["pagina_pdf"],
        "coluna": spec["rotulo_coluna"],
        "indice_coluna_zero": 0 if spec["data_estoque"] == "2026-06-30" else 1,
        "rubrica": spec["rubrica"],
        "lexema": spec["lexema"],
        "escala_ars": "1000",
        "quantum_ars": "1000",
        "valor_decimal_ars": str(value),
        "sha256": perfil.PINS["junho"]["sha256"],
        "owners": True,
        "consolidado": True,
        "currency": "ARS",
        "politica_contabil_id": perfil.POLITICA,
        "poder_aquisitivo_data": perfil.PODER,
    }


def extrair_paginas(perfil, pages):
    """Helper textual causal, sem autenticação/fatos; inputs simulados não burlam SHA."""
    specs = CELULAS_DOCUMENTAIS[perfil.ISSUER_ID]
    page = specs[0]["pagina_pdf"]
    if perfil.produto is gal:
        text = _norm(pages[page])
        for anchor in perfil.ANCORA:
            gal._exige(pages[anchor["pagina_pdf"]], *anchor["trechos"])
        required = [
            "CONSOLIDATED CONDENSED INTERIM STATEMENT OF FINANCIAL POSITION",
            "GRUPO FINANCIERO GALICIA S.A.",
            "June 30, 2026",
            "homogeneous currency",
            "thousand Argentine pesos",
            "Items Notes/ Schedule 06.30.26 12.31.25 Liabilities",
        ]
        limit = "Shareholders' Equity attributable to Non-controlling Interests"
    else:
        # O helper de contexto valida exclusivamente capa/identidade/política,
        # unidade/poder; nenhuma matemática ou ponte NI é chamada.
        validar_contexto(pages, "pages")
        text = _norm(pages["pages"][page - 1])
        required = [
            "CONSOLIDATED CONDENSED INTERIM STATEMENT OF FINANCIAL POSITION",
            "GRUPO SUPERVIELLE S.A.",
            "June 30, 2026 and December 31, 2025",
            "thousands of pesos in homogeneous currency",
            "Notes and Schedules 06/30/2026 12/31/2025 LIABILITIES",
        ]
        limit = "Shareholders' Equity attributable to non-controlling interests"
    _require(
        all(token in text for token in required) and "SEPARATE" not in text,
        "Cabeçalho/grão/unidade/coluna de patrimônio divergente",
    )
    rubric = specs[0]["rubrica"]
    _require(text.count(rubric) == text.count(limit) == 1, "Owners ausente/ambíguo")
    segment = text[text.index(rubric) + len(rubric) : text.index(limit)]
    lexemes = re.findall(r"\d{1,3}(?:,\d{3})+", segment)
    _require(
        lexemes == [s["lexema"] for s in specs], "Colunas/lexemas owners não correspondem ao filing"
    )
    return [
        _celula(perfil, {**s, "lexema": lexeme}) for s, lexeme in zip(specs, lexemes, strict=True)
    ]


def validar_pdf(conteudo, issuer_id):
    _require(
        isinstance(issuer_id, str) and issuer_id in PERFIS, "Emissor de patrimônio desconhecido"
    )
    perfil = PERFIS[issuer_id]
    pages = perfil.produto.validar_pdf_observado(conteudo, "junho")
    return extrair_paginas(perfil, pages)


def validar_catalogo(documento):
    """Vínculo finito ao PDF de estoque; nenhuma dependência anual é inferida."""
    _require(isinstance(documento, Mapping), "Catálogo estruturado exigido")
    issuer = documento.get("issuer_id")
    _require(isinstance(issuer, str) and issuer in PERFIS, "Emissor de patrimônio desconhecido")
    perfil = PERFIS[issuer]
    _require(
        documento.get("extrator") == perfil.produto.EXTRATOR_ID
        and all(documento.get(k) == perfil.PINS["junho"][k] for k in ("documento", "sha256", "url"))
        and documento.get("disponibilidade_tipo") == "recepcao_observada"
        and documento.get("data_publicacao") is None,
        "Catálogo contradiz PDF de estoque owners",
    )


def _validar_celula(perfil, ctx, row, roles, presente):
    _require(roles == ["junho"], "Estoque tem dependência fora do mesmo PDF")
    cell = ctx.get("celula")
    candidates = [_celula(perfil, spec) for spec in CELULAS_DOCUMENTAIS[perfil.ISSUER_ID]]
    _require(cell in candidates, "Célula owners diverge de rubrica/coluna/data/valor do filing")
    _require(
        ctx.get("reportado_no_documento") is True and ctx.get("ponte_especifica") is None,
        "Estoque não é composição ou ponte saldo→fluxo",
    )
    _require(
        ctx.get("ancoras_politica_unidade") == perfil.ANCORA,
        "Política/poder sem contexto do mesmo documento",
    )
    _require(
        ctx.get("normalizado") is False
        and ctx.get("IFRS_integral") is False
        and ctx.get("perimetro_constante_certificado") is False,
        "Estoque não certifica normalização/IFRS/perímetro",
    )
    if perfil.produto is sup:
        _require(
            ctx.get("observacao_visual_fechada") == sup.LEITURA_VISUAL,
            "Evidência visual separada contraditória",
        )
    for node in [row, row.get("fonte")]:
        if not isinstance(node, Mapping) and not isinstance(node, pd.Series):
            continue
        origem = node.get("fonte")
        # Só a linha principal pode conter o Mapping da proveniência.
        # No node dessa fonte, o campo é o identificador, nunca outro
        # contêiner; ausência opcional não recebe origem por inferência.
        estruturada = node is row and isinstance(origem, Mapping)
        if presente(origem) and not estruturada:
            _require(
                isinstance(origem, str)
                and origem == ctx["dependencias"][0]["registro"]["fonte"],
                "Origem nativa contradiz RegistroArquivo do estoque owners",
            )
        par = [presente(node.get(k)) for k in ("politica_contabil_id", "poder_aquisitivo_data")]
        _require(not any(par) or all(par), "Par contábil parcial no estoque/fonte")
        for key, expected in [
            ("item", "patrimonio_controladores"),
            ("currency", "ARS"),
            ("consolidado", True),
            ("demonstrativo", "BPA"),
            ("escala", 1),
            ("anual", False),
            ("issuer_id", perfil.ISSUER_ID),
            ("entidade", "RI:" + perfil.ISSUER_ID),
            ("politica_contabil_id", perfil.POLITICA),
            ("poder_aquisitivo_data", perfil.PODER),
        ]:
            if key in node:
                _require(
                    presente(node[key])
                    and pd.api.types.is_scalar(node[key])
                    and node[key] == expected,
                    "Grão nativo contradiz estoque owners",
                )
        recebido = pd.Timestamp(ctx["dependencias"][0]["registro"]["data_coleta"])
        for key in ("received_date", "data_coleta"):
            if presente(node.get(key)):
                try:
                    stamp = pd.Timestamp(node[key])
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ExtracaoRecusada("Recepção nativa inválida") from exc
                _require(
                    stamp.tzinfo is not None and stamp == recebido,
                    "Recepção nativa contradiz RegistroArquivo",
                )
        if "freq" in node:
            _require(
                isinstance(node["freq"], str) and node["freq"] == "Q",
                "Frequência nativa contradiz coluna de estoque",
            )
        if presente(node.get("documento")):
            from ..cobertura.insumos import documento_proveniencia

            pin = perfil.PINS["junho"]
            label = documento_proveniencia(
                {
                    "documento": pin["documento"],
                    "demonstrativo": "BPA",
                    "freq": "Q",
                    "period_end": cell["period_end"],
                    "consolidado": True,
                }
            )
            _require(
                node["documento"] in (pin["documento"], label),
                "Localizador da fonte contradiz estoque owners",
            )
        if "period_start" in node:
            _require(not presente(node["period_start"]), "Estoque não tem início de fluxo")
        if "period_end" in node:
            try:
                stamp = pd.Timestamp(node["period_end"])
            except (TypeError, ValueError, OverflowError) as exc:
                raise ExtracaoRecusada("Data de estoque inválida") from exc
            _require(
                not pd.isna(stamp)
                and stamp.tzinfo is None
                and stamp == stamp.normalize()
                and stamp.date().isoformat() == cell["period_end"],
                "Data nativa contradiz coluna de estoque",
            )
        for key in ["value", "valor"]:
            if key in node:
                try:
                    _require(
                        presente(node[key])
                        and not isinstance(node[key], bool)
                        and Decimal(str(node[key])) == Decimal(cell["valor_decimal_ars"]),
                        "Valor nativo contradiz célula owners",
                    )
                except (InvalidOperation, TypeError, ValueError) as exc:
                    raise ExtracaoRecusada("Valor nativo contradiz célula owners") from exc


def fatos_pdf_observado(conteudo, registro, issuer_id):
    """Dois estoques no mesmo PDF; registro atual, sem timestamp histórico imposto."""
    from .publico_cvm import FATO_COLUNAS

    cells = validar_pdf(conteudo, issuer_id)
    perfil = PERFIS[issuer_id]
    dep = dependencia(registro, "junho", issuer_id=issuer_id, pins=perfil.PINS)
    rows = []
    for cell in cells:
        ctx = {
            "schema": perfil.CONTEXTO_SCHEMA,
            "tipo": "celula_primaria",
            "celula": cell,
            "dependencias": [dep],
            "reportado_no_documento": True,
            "ponte_especifica": None,
            "ancoras_politica_unidade": perfil.ANCORA,
            "normalizado": False,
            "IFRS_integral": False,
            "perimetro_constante_certificado": False,
            "publicacao_primaria": None,
            "pit_certificado": False,
            "disponivel_desde": dep["limite_captura"],
        }
        if perfil.produto is sup:
            ctx["observacao_visual_fechada"] = deepcopy(sup.LEITURA_VISUAL)
        row = {
            "entidade": "RI:" + issuer_id,
            "demonstrativo": "BPA",
            "item": "patrimonio_controladores",
            "period_start": pd.NaT,
            "period_end": pd.Timestamp(cell["period_end"]),
            "currency": "ARS",
            "value": float(Decimal(cell["valor_decimal_ars"])),
            "consolidado": True,
            "anual": False,
            "received_date": registro.data_coleta,
            "version": 1,
            "documento": perfil.PINS["junho"]["documento"],
            "url": perfil.PINS["junho"]["url"],
            "fonte": "RI",
            "sha256": perfil.PINS["junho"]["sha256"],
            "nota": "Patrimônio owners reportado BCRA; estoque instantâneo, não fluxo ou ações",
            "pit_estimado": False,
            "politica_contabil_id": perfil.POLITICA,
            "poder_aquisitivo_data": perfil.PODER,
            "disponibilidade_tipo": "recepcao_observada",
            "disponivel_desde": dep["limite_captura"],
            "data_recebimento_documento": None,
            "data_publicacao_primaria": None,
            **_envelope(ctx),
        }
        contexto_documental(row)
        rows.append(row)
    columns = FATO_COLUNAS + [key for key in rows[0] if key not in FATO_COLUNAS]
    return pd.DataFrame(rows, columns=columns)
