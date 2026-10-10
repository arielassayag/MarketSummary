"""Corpos de configuração explícitos; nenhum fallback ou autoridade de executor."""
from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Literal

import pandas as pd
import yaml

from ..cobertura.parametros import ParametrosCobertura, _parametros_de_textos
from ..config import FundConfig, config_from_text
from ..universe import Universe, universe_from_frame

EXEMPLO = "latam_simulado_v1"
COBERTURA = ("arquetipos.csv", "betas_setor.csv", "unidades.csv", "sotp.yaml", "etfs.yaml")
MEMBROS = ("fund.yaml", "valuation.yaml", "universo.csv", "nomes.yaml",
           *(f"cobertura/{n}" for n in COBERTURA))
CATALOGOS = frozenset({"resultado_evidencias.json", "sec_classes_acoes.json",
                       "sec_fluxos_html.json", "sec_ri_xbrl.json", "ri_demonstrativos.json"})


@dataclass(frozen=True)
class OrigemConfiguracao:
    papel: Literal["EXEMPLO", "CONFIG_DECLARADA"]
    nome: str
    aviso: str


@dataclass(frozen=True)
class ArquivosTecnicas:
    corpos: Mapping[str, bytes]
    sha256: Mapping[str, str]


@dataclass(frozen=True)
class EntradasTecnicas:
    origem: OrigemConfiguracao
    arquivos: ArquivosTecnicas
    fund: FundConfig
    valuation: ParametrosCobertura
    universo: Universe


def _texto(raw: bytes) -> str:
    # Mesma normalização universal de nova linha de Path.read_text.
    return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _parse(corpos: dict[str, bytes], origem: OrigemConfiguracao) -> EntradasTecnicas:
    if not set(MEMBROS) <= set(corpos) or set(corpos) - set(MEMBROS) - CATALOGOS:
        raise ValueError("Membros de configuração ausentes ou desconhecidos")
    hashes = {n: hashlib.sha256(b).hexdigest() for n, b in corpos.items()}
    fund = config_from_text(_texto(corpos["fund.yaml"]))
    textos = {n: _texto(corpos[n]) for n in ("valuation.yaml", *(f"cobertura/{n}" for n in COBERTURA))}
    val = yaml.safe_load(textos["valuation.yaml"]) or {}
    if val.get("projecao", {}).get("normalizacao_resultado_metodo") == "eventos_evidenciados":
        if "resultado_evidencias.json" not in corpos:
            raise FileNotFoundError("Catálogo declarado resultado_evidencias.json ausente")
        textos["resultado_evidencias.json"] = _texto(corpos["resultado_evidencias.json"])
    elif "resultado_evidencias.json" in corpos:
        # Catálogo declarado permanece nos corpos brutos; o hash nativo segue o
        # mesmo readset do parser original quando o método não o consome.
        json.loads(_texto(corpos["resultado_evidencias.json"]))
    params = _parametros_de_textos(textos)
    for n in set(corpos) & CATALOGOS:
        json.loads(_texto(corpos[n]))
    names = yaml.safe_load(_texto(corpos["nomes.yaml"]))
    if not isinstance(names, dict) or set(names) != {"nomes"} or not isinstance(names["nomes"], dict):
        raise ValueError("Mapa de nomes declarado inválido")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in names["nomes"].items()):
        raise ValueError("Nomes devem ser textos explícitos")
    frame = pd.read_csv(io.BytesIO(corpos["universo.csv"]), dtype={"adr_ratio": "string"},
                        keep_default_na=False, na_values=[""])
    universe = universe_from_frame(frame, hashes["universo.csv"], nomes=names["nomes"])
    arquivo = ArquivosTecnicas(MappingProxyType(dict(corpos)), MappingProxyType(hashes))
    return EntradasTecnicas(origem, arquivo, fund, params, universe)


def carregar_exemplo(nome: Literal["latam_simulado_v1"]) -> EntradasTecnicas:
    """Recebe o exemplo nomeado pelo recurso de pacote, inclusive em wheel instalado."""
    if nome != EXEMPLO:
        raise ValueError("Exemplo desconhecido")
    base = files("cdp").joinpath("recursos", "exemplos", nome)
    manifest = json.loads(base.joinpath("manifesto.json").read_bytes())
    if (not isinstance(manifest, dict) or set(manifest) != {"schema", "papel", "nome", "aviso", "membros"}
            or manifest["schema"] != "cdp.tecnicas.exemplo/v1" or manifest["papel"] != "EXEMPLO"
            or manifest["nome"] != nome or manifest["aviso"] != "DADOS SIMULADOS"
            or not isinstance(manifest["membros"], dict) or set(manifest["membros"]) != set(MEMBROS)):
        raise ValueError("Manifesto do exemplo inválido")
    corpos = {}
    for n in MEMBROS:
        raw = base.joinpath(*n.split("/")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["membros"][n]:
            raise ValueError(f"Integridade divergente do exemplo: {n}")
        corpos[n] = raw
    expected = {n.split("/")[0] for n in MEMBROS} | {"manifesto.json"}
    if {p.name for p in base.iterdir()} != expected or {p.name for p in base.joinpath("cobertura").iterdir()} != set(COBERTURA):
        raise ValueError("Membro extra no exemplo")
    result = _parse(corpos, OrigemConfiguracao("EXEMPLO", nome, "DADOS SIMULADOS"))
    if result.fund.execution is not None or "DADOS SIMULADOS" not in result.fund.fund.track_record_type:
        raise ValueError("Exemplo não pode carregar execução ou ocultar dados simulados")
    return result


def carregar_arquivos_locais(*, fund: Path, valuation: Path, cobertura: Path,
                            universo: Path, nomes: Path,
                            catalogos: Mapping[str, Path]) -> EntradasTecnicas:
    """Lê exclusivamente os caminhos declarados, sem default ou busca de clone."""
    if set(catalogos) - CATALOGOS:
        raise ValueError("Catálogo desconhecido")
    paths = {"fund.yaml": fund, "valuation.yaml": valuation, "universo.csv": universo, "nomes.yaml": nomes,
             **{f"cobertura/{n}": Path(cobertura) / n for n in COBERTURA}, **catalogos}
    if cobertura == "" or any(p is None or p == "" for p in paths.values()):
        raise ValueError("Caminho explícito vazio/ausente")
    # Esses bytes são configuração declarada, não recibo de documento financeiro.
    corpos = {n: Path(p).read_bytes() for n, p in paths.items()}
    return _parse(corpos, OrigemConfiguracao("CONFIG_DECLARADA", "arquivos locais declarados",
                                           "Configuração declarada; não comprova dados financeiros ou autoridade"))
