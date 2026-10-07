"""Transporte de insumos mistos com tipos e ETFs; reabertura exige autoridades externas."""
from __future__ import annotations

import json
from pathlib import Path

from .adapter import _ler_quadro, _quadro, autenticar, texto, validar_tabelas
from .observado import sha

SCHEMA = "cdp.ri.insumos_mistos/v1"
QUADROS = ("demonstrativos", "consenso", "dividendos", "eventos", "taxas", "free_float",
           "alertas", "capital_oficial", "resultado_evidencias", "ri_observados", "ri_evidencias")


def gravar_insumos_ri(saida, *, raiz_saida, fornecedor, params, conhecimento_ate):
    """Saída nova sob raiz explícita do chamador; nunca contém objetos de autoridade."""
    from ...cobertura.ri_consumo import _corte
    cut = _corte(params, fornecedor, conhecimento_ate)
    dados = fornecedor.dados
    validar_tabelas(fornecedor.md, dados.ri_observados, dados.ri_evidencias,
                    dados.ri_contexto, conhecimento_ate)
    path = Path(saida).resolve()
    root = Path(raiz_saida).resolve()
    path.relative_to(root)
    if path == root:
        raise ValueError("RI: transporte exige subdiretório novo da raiz explícita")
    path.mkdir(parents=True, exist_ok=False)
    quadros = {name: _quadro(getattr(dados, name)) for name in QUADROS}
    etfs = {ticker: None if frame is None else _quadro(frame) for ticker, frame in dados.etfs.items()}
    body = texto({"quadros": quadros, "etfs": etfs, "origem": dados.origem,
                  "raiz": dados.raiz, "corte_temporal": cut})
    (path / "insumos.json").write_text(body, encoding="utf-8")
    manifest = {"schema": SCHEMA, "arquivos": {"insumos.json": sha(body.encode())},
                "fornecedor_externo_obrigatorio": True,
                "escopo": "transporte privado de insumos; nenhuma aprovação PIT/modelo/operação"}
    (path / "manifest.json").write_text(texto(manifest), encoding="utf-8")
    return sha((path / "manifest.json").read_bytes())


def reabrir_insumos_ri(saida, *, sha256_esperado, md, contexto, params, conhecimento_ate):
    from ...cobertura.fontes import DadosPublicos
    from ...cobertura.ri_consumo import FornecedorConsumoRI, _corte
    autenticar(contexto, md)
    path = Path(saida)
    raw = (path / "manifest.json").read_bytes()
    if sha(raw) != sha256_esperado:
        raise ValueError("RI: manifesto difere do digest externo")
    manifest = json.loads(raw)
    if manifest.get("schema") != SCHEMA:
        raise ValueError("RI: schema de transporte desconhecido")
    for name, digest in manifest["arquivos"].items():
        if Path(name).name != name or sha((path / name).read_bytes()) != digest:
            raise ValueError("RI: bytes do transporte não conferem")
    value = json.loads((path / "insumos.json").read_text())
    kwargs = {name: _ler_quadro(value["quadros"][name]) for name in QUADROS}
    kwargs.update(etfs={ticker: None if frame is None else _ler_quadro(frame)
                       for ticker, frame in value["etfs"].items()}, origem=value["origem"],
                  raiz=value["raiz"], corte_temporal=value["corte_temporal"], ri_contexto=contexto)
    dados = DadosPublicos(**kwargs)
    fornecedor = FornecedorConsumoRI(md, dados)
    _corte(params, fornecedor, conhecimento_ate)
    validar_tabelas(md, dados.ri_observados, dados.ri_evidencias, contexto, conhecimento_ate)
    return fornecedor


__all__ = ["gravar_insumos_ri", "reabrir_insumos_ri"]
