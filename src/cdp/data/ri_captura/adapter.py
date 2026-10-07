"""Adapter privado de saldos observados; autoridades vêm do fornecedor externo."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .custodia import ReceiptVault
from .extracao import export, extract, verify_export
from .extracao_identidade import encode
from .identidade import IdentityVault, MasterAuthority
from .identidade_legada import canonical
from .observado import Document, instant, sha

SCHEMA = "cdp.ri.adapter_privado/v2"
COLUNAS = ("issuer_id", "item", "freq", "period_end", "value", "currency", "escala",
           "consolidado", "fonte", "demonstrativo", "documento", "url", "sha256",
           "data_publicacao", "received_date", "data_coleta", "disponivel_desde",
           "quantum", "lexema", "coluna", "locator", "fato_id", "identity_binding_sha256",
           "base", "pit_estimado")


@dataclass(frozen=True, slots=True)
class ContextoRI:
    """Não se reconstrói este objeto a partir do catálogo/tabela/pacote candidato."""
    vault: ReceiptVault
    identity: IdentityVault
    document: Document
    ticker: str
    exchange: str


def texto(value):
    # Ausência não finita do legado vira null somente na representação do pacote.
    # O transporte de quadros mantém a distinção por tipo; bruto nunca é alterado.
    def clean(v):
        if v is pd.NA or v is pd.NaT or isinstance(v, float) and not math.isfinite(v):
            return None
        if isinstance(v, dict):
            return {str(k): clean(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [clean(x) for x in v]
        if hasattr(v, "item"):
            return clean(v.item())
        return encode(v)
    return canonical(clean(value)).decode("utf-8")


def autenticar(contexto, md):
    if type(contexto) is not ContextoRI:
        raise ValueError("RI: fornecedor externo de autoridades ausente")
    if (type(contexto.vault) is not ReceiptVault or type(contexto.identity) is not IdentityVault
            or type(contexto.identity.master) is not MasterAuthority or type(contexto.document) is not Document):
        raise ValueError("RI: autoridades exatas congeladas são obrigatórias")
    contexto.vault.authenticate()
    contexto.identity.authenticate()
    master = contexto.identity.master
    master.authenticate()
    line, _ = master.read_line(contexto.ticker, contexto.exchange)
    if not md.universe.source_sha256 or md.universe.source_sha256 != master.master_sha256:
        raise ValueError("RI: Universe não corresponde ao master externo")
    if contexto.ticker not in md.universe.lines.index:
        raise ValueError("RI: linha ausente no Universe")
    market_line = md.universe.lines.loc[contexto.ticker]
    if (str(market_line["issuer_id"]) != line["issuer_id"]
            or str(market_line["exchange"]) != line["exchange"]
            or line["issuer_id"] != contexto.document.issuer_id):
        raise ValueError("RI: IID/ticker/bolsa divergentes do master")
    return contexto


def _tabela(envelope, doc):
    rows = []
    if (doc.issuer_id != "MX_AMX" or doc.currency != "MXN"
            or tuple(c.label for c in doc.columns) != ("Cierre Periodo Actual", "Cierre Año Anterior")
            or {i.name for i in doc.items} != {"patrimonio_controladores", "participacao_minoritarios", "patrimonio_liquido"}):
        raise ValueError("RI: recorte privado fechado em AMX e duas colunas patrimoniais")
    # Convenção de saldo autenticada; não constitui duração de fluxo.
    frequencies = {"Cierre Periodo Actual": "Q", "Cierre Año Anterior": "A"}
    columns = {c.end.isoformat(): (c.label, frequencies.get(c.label)) for c in doc.columns}
    for fact in envelope["result"]["facts"]:
        if fact["base"] != "consolidado":
            raise ValueError("RI: base não consolidada fora do recorte AMX")
        label, freq = columns[fact["period_end"]]
        if freq is None:
            raise ValueError("RI: semântica da coluna não normalizável neste recorte")
        rows.append({"issuer_id": fact["issuer_id"], "item": fact["item"], "freq": freq,
                     "period_end": fact["period_end"], "value": fact["value"],
                     "currency": fact["currency"], "escala": "1", "consolidado": fact["base"] == "consolidado",
                     "fonte": "RI_OBSERVADA", "demonstrativo": "SALDO_OBSERVADO",
                     "documento": doc.listing_title, "url": fact["url"], "sha256": fact["pdf_sha256"],
                     "data_publicacao": None, "received_date": None, "data_coleta": fact["data_coleta"],
                     "disponivel_desde": fact["disponivel_desde"], "quantum": fact["rounding_quantum"],
                     "lexema": fact["raw"], "coluna": label, "locator": fact["locator"],
                     "fato_id": sha(canonical(fact)), "identity_binding_sha256": fact["identity_binding_sha256"],
                     "base": fact["base"], "pit_estimado": False})
    return pd.DataFrame(rows, columns=COLUNAS)


def coletar_observados(md, contexto, conhecimento_ate: datetime):
    contexto = autenticar(contexto, md)
    cutoff = instant(conhecimento_ate)
    result = extract(contexto.vault, contexto.document, identity=contexto.identity,
                     ticker=contexto.ticker, exchange=contexto.exchange, cutoff=cutoff)
    envelope = export(result)
    verify_export(envelope, contexto.vault, contexto.document, identity=contexto.identity,
                  ticker=contexto.ticker, exchange=contexto.exchange, cutoff=cutoff)
    table = _tabela(envelope, contexto.document)
    catalog = {"schema": SCHEMA, "conhecimento_ate": cutoff.isoformat(),
               "universe_sha256": md.universe.source_sha256,
               "master_anchor_sha256": contexto.identity.master.anchor_sha256,
               "identity_custody_sha256": contexto.identity.config_sha256,
               "custody_manifest_sha256": contexto.vault.manifest_sha256,
               "envelope": envelope}
    catalog["catalogo_sha256"] = sha(canonical(catalog))
    evidence = pd.DataFrame([{"schema": SCHEMA, "conhecimento_ate": cutoff.isoformat(),
                              "catalogo_sha256": catalog["catalogo_sha256"], "catalogo_json": texto(catalog)}])
    return table, evidence


def validar_tabelas(md, observados, evidencias, contexto, conhecimento_ate):
    from ...cobertura.fontes import csv_canonico
    expected, expected_evidence = coletar_observados(md, contexto, conhecimento_ate)
    if (csv_canonico(observados) != csv_canonico(expected)
            or csv_canonico(evidencias) != csv_canonico(expected_evidence)):
        raise ValueError("RI: tabelas/catálogo diferem da reextração externa no mesmo corte")
    catalog = json.loads(expected_evidence.iloc[0]["catalogo_json"])
    return expected, catalog


def _celula(x):
    if x is None or x is pd.NA or x is pd.NaT or isinstance(x, float) and math.isnan(x):
        return {"tipo": "ausente"}
    if isinstance(x, pd.Timestamp):
        return {"tipo": "timestamp", "valor": x.isoformat()}
    if isinstance(x, datetime):
        return {"tipo": "datetime", "valor": x.isoformat()}
    if isinstance(x, date):
        return {"tipo": "date", "valor": x.isoformat()}
    if hasattr(x, "item"):
        x = x.item()
    return {"tipo": "literal", "valor": x}


def _quadro(df):
    return {"colunas": list(df.columns), "tipos": [str(t) for t in df.dtypes],
            "linhas": [[_celula(x) for x in row] for row in df.itertuples(index=False, name=None)]}


def _ler_quadro(value):
    def decode(cell):
        if cell["tipo"] == "ausente":
            return None
        if cell["tipo"] == "timestamp":
            return pd.Timestamp(cell["valor"])
        if cell["tipo"] == "datetime":
            return datetime.fromisoformat(cell["valor"])
        if cell["tipo"] == "date":
            return date.fromisoformat(cell["valor"])
        if cell["tipo"] != "literal":
            raise ValueError("RI: tipo de célula desconhecido")
        return cell["valor"]
    df = pd.DataFrame([[decode(c) for c in row] for row in value["linhas"]], columns=value["colunas"])
    for column, dtype in zip(value["colunas"], value["tipos"], strict=True):
        df[column] = df[column].astype(dtype)
    return df


def gravar_pacote_privado(saida, pacote, md, dados, params):
    """Transporte privado exato; CSV de conferência não substitui tipos/precisão dos brutos."""
    from ...cobertura.fontes import csv_canonico
    from ...cobertura.ri_observada import validar_pacote
    validar_pacote(pacote, md, dados, params)
    path = Path(saida).resolve()
    private_root = Path(__file__).resolve().parents[5]
    path.relative_to(private_root / "saidas")  # nunca book/data/reports/artifacts ou a própria fonte
    path.mkdir(parents=True, exist_ok=False)
    tables = dados.tabelas()
    exact = {name: _quadro(df) for name, df in tables.items()}
    files = {"tabelas.json": texto(exact), "pacote.json": texto(pacote)}
    for name, df in tables.items():
        files[f"{name}.csv"] = csv_canonico(df)
    for name, body in files.items():
        (path / name).write_text(body, encoding="utf-8")
    manifest = {"schema": "cdp.ri.pacote_privado_transporte/v2", "origem": dados.origem,
                "arquivos": {name: sha(body.encode()) for name, body in files.items()},
                "fornecedor_externo_obrigatorio": True,
                "escopo": "pacote/reabertura; não aprova modelos ou operação"}
    (path / "manifest.json").write_text(texto(manifest), encoding="utf-8")
    return manifest


def reabrir_pacote_privado(saida, *, md, params, contexto):
    from ...cobertura.fontes import DadosPublicos
    from ...cobertura.ri_observada import validar_pacote
    autenticar(contexto, md)
    path = Path(saida)
    manifest = json.loads((path / "manifest.json").read_text())
    if manifest.get("schema") != "cdp.ri.pacote_privado_transporte/v2":
        raise ValueError("RI: schema de transporte desconhecido")
    for name, digest in manifest["arquivos"].items():
        if Path(name).name != name or sha((path / name).read_bytes()) != digest:
            raise ValueError("RI: arquivo de transporte não confere")
    tables = {name: _ler_quadro(value) for name, value in json.loads((path / "tabelas.json").read_text()).items()}
    kwargs = {name: tables[name] for name in ("demonstrativos", "consenso", "dividendos", "eventos", "taxas", "free_float")}
    kwargs.update(origem=manifest["origem"], ri_contexto=contexto, ri_observados=tables["ri_observados"],
                  ri_evidencias=tables["ri_evidencias"], corte_temporal=tables["corte_temporal"].iloc[0].to_dict())
    if "alertas_fonte" in tables:
        kwargs["alertas"] = tables["alertas_fonte"]
    for name in ("capital_oficial", "resultado_evidencias"):
        if name in tables:
            kwargs[name] = tables[name]
    # ETFs estão fora do recorte; recusa em vez de perder silenciosamente um quadro.
    if any(name.startswith("etf_") for name in tables):
        raise ValueError("RI: transporte deste recorte não inclui ETFs")
    dados = DadosPublicos(**kwargs)
    pacote = json.loads((path / "pacote.json").read_text())
    validar_pacote(pacote, md, dados, params)
    return dados, pacote
