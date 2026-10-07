"""Parâmetros versionados da cobertura (``configs/cdp/valuation.yaml`` + ``configs/cdp/cobertura/``).

Os arquivos são lidos como estão (sem preenchimento silencioso) e o sha256 de cada um entra no
manifesto do snapshot. Insumos datados (Damodaran, alíquotas, inflação) carregam a fonte pública
citada no próprio YAML; regras de política (pesos dos métodos, limiares de rating, portões de
qualidade) são parte do modelo e ficam versionadas aqui.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..hashing import sha256_obj, sha256_text

DEFAULT_VALUATION = Path("configs/cdp/valuation.yaml")
DEFAULT_COBERTURA_DIR = Path("configs/cdp/cobertura")

ARQUETIPOS = ("banco", "seguradora", "utilidade_regulada", "concessao", "commodity",
              "corporativo", "imobiliario", "holding")
METODOS = ("rim", "rim_real", "pb_justificado", "ddm", "ddm_real", "fcff", "fcff_real",
           "fcff_vida_finita", "fcff_normalizado", "multiplo_justificado", "regressao_pb_roe",
           "regressao_pl", "regressao_ev_receita", "soma_partes")
NOME_METODO = {
    "rim": "Lucro residual (GLS)",
    "rim_real": "Lucro residual em termos reais",
    "pb_justificado": "P/VPA justificado (Gordon)",
    "ddm": "Dividendos descontados (dois estágios)",
    "ddm_real": "Dividendos descontados em termos reais",
    "fcff": "Fluxo de caixa livre da firma (três estágios)",
    "fcff_real": "Fluxo de caixa livre da firma em termos reais",
    "fcff_vida_finita": "Fluxo de caixa livre até o fim da concessão",
    "fcff_normalizado": "Fluxo de caixa livre com margem ao longo do ciclo",
    "multiplo_justificado": "P/L justificado pelos fundamentos",
    "regressao_pb_roe": "P/VPA de regressão transversal (ROE, crescimento, β, payout)",
    "regressao_pl": "P/L de regressão transversal (crescimento, payout, β)",
    "regressao_ev_receita": "EV/Receita de regressão transversal (margem, crescimento, alavancagem)",
    "soma_partes": "Soma das partes com desconto histórico da holding",
}
MOEDA_PAIS = {"USD": "US", "BRL": "BR", "MXN": "MX", "CLP": "CL", "COP": "CO", "PEN": "PE",
              "ARS": "AR", "UYU": "UY"}


@dataclass(frozen=True)
class Arquetipo:
    issuer_id: str
    arquetipo: str
    industria_damodaran: str
    moeda_demonstrativos: str | None
    lambda_: float
    linha_valuation: str | None
    fim_concessao: int | None
    nota: str
    fim_concessao_fonte: str = ""


@dataclass(frozen=True)
class BetaSetor:
    industria: str
    beta_u_global: float
    beta_u_em: float
    financeira: bool
    data_ref: str
    url: str


@dataclass(frozen=True)
class ParametrosCobertura:
    """Tudo o que o motor usa além dos dados públicos. ``arquivos``: ``{caminho: sha256}``."""

    valuation: dict[str, Any]
    arquetipos: dict[str, Arquetipo]
    betas: dict[str, BetaSetor]
    unidades: dict[str, dict[str, Any]]
    sotp: dict[str, Any]
    etfs: dict[str, Any]
    arquivos: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------ atalhos
    @property
    def versao(self) -> str:
        return str(self.valuation.get("versao", ""))

    @property
    def cc(self) -> dict[str, Any]:
        return self.valuation["custo_capital"]

    def sec(self, nome: str) -> dict[str, Any]:
        return self.valuation[nome]

    def fonte(self, chave: str) -> dict[str, Any]:
        """Proveniência de um insumo datado da configuração. Para fontes externas (Damodaran, FRED) o
        valor é transcrito em ``valuation.yaml``: o ``sha256`` fica vazio (a planilha não é arquivada no
        snapshot; o hash da configuração não é o do documento) e o documento diz de onde conferir."""
        f = dict(self.valuation.get("fontes", {}).get(chave, {}))
        externa = chave.startswith(("damodaran", "fred"))
        doc = f.get("documento")
        if externa and doc:
            doc = (f"{doc} — valor transcrito na configuração pública da cobertura (valuation.yaml, "
                   "nos dados abertos); conferir no endereço da fonte")
        return {"fonte": "DAMODARAN" if chave.startswith("damodaran") else (
            "FRED" if chave.startswith("fred") else "CONFIG"),
            "url": f.get("url"), "documento": doc,
            "data_publicacao": f.get("data_publicacao"), "data_coleta": None,
            "sha256": None if externa else self.arquivos.get("valuation.yaml")}

    def fonte_config(self, descricao: str) -> dict[str, Any]:
        return {"fonte": "CONFIG", "url": None, "documento": f"configs/cdp/valuation.yaml — {descricao}",
                "data_publicacao": None, "data_coleta": None,
                "sha256": self.arquivos.get("valuation.yaml")}

    def pesos(self, arquetipo: str) -> dict[str, float]:
        return {str(k): float(v) for k, v in self.valuation["pesos_metodos"][arquetipo].items()}

    def hash(self) -> str:
        return sha256_obj(self.arquivos)


def _read_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def _opt_str(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _validar(val: dict[str, Any], arqs: dict[str, Arquetipo], betas: dict[str, BetaSetor]) -> None:
    faltam = [k for k in ("custo_capital", "perpetuidade", "fade_phi", "pesos_metodos", "projecao",
                          "persistencia_roe", "multiplo_h", "multiplos", "minoritarios", "soma_partes",
                          "cenarios", "sensibilidade", "rating", "qualidade", "etf", "alpha") if k not in val]
    if faltam:
        raise ValueError(f"valuation.yaml sem seções: {faltam}")
    unidade_metodo = val.get("consenso", {}).get("unidade_metodo")
    if unidade_metodo not in (None, "declaracao_fonte"):
        raise ValueError(f"Método de unidade do consenso desconhecido: {unidade_metodo!r}")
    reinvestimento_metodo = val["projecao"].get("reinvestimento_metodo")
    if reinvestimento_metodo not in (None, "capitalizacao_arrendamentos"):
        raise ValueError(f"Método de reinvestimento desconhecido: {reinvestimento_metodo!r}")
    reinvestimento_regime = val["projecao"].get("reinvestimento_regime")
    if reinvestimento_regime not in (None, "recente", "suavizado"):
        raise ValueError(f"Regime de reinvestimento desconhecido: {reinvestimento_regime!r}")
    for arq, pesos in val["pesos_metodos"].items():
        if arq not in ARQUETIPOS:
            raise ValueError(f"Arquétipo desconhecido em pesos_metodos: {arq}")
        ruins = [m for m in pesos if m not in METODOS]
        if ruins:
            raise ValueError(f"Métodos desconhecidos para {arq}: {ruins}")
        if abs(sum(float(v) for v in pesos.values()) - 1.0) > 1e-9:
            raise ValueError(f"Pesos de {arq} não somam 1.")
    for a in arqs.values():
        if a.arquetipo not in ARQUETIPOS:
            raise ValueError(f"{a.issuer_id}: arquétipo inválido {a.arquetipo!r}")
        if a.industria_damodaran not in betas:
            raise ValueError(f"{a.issuer_id}: indústria {a.industria_damodaran!r} fora de betas_setor.csv")


def carregar_parametros(valuation: Path | str | None = None,
                        pasta: Path | str | None = None) -> ParametrosCobertura:
    """Lê e valida os parâmetros; o sha256 do texto de cada arquivo vai em ``arquivos``."""
    vpath = Path(valuation) if valuation else DEFAULT_VALUATION
    pdir = Path(pasta) if pasta else (vpath.parent / "cobertura" if valuation else DEFAULT_COBERTURA_DIR)
    textos: dict[str, str] = {"valuation.yaml": vpath.read_text(encoding="utf-8")}
    for nome in ("arquetipos.csv", "betas_setor.csv", "unidades.csv", "sotp.yaml", "etfs.yaml"):
        p = pdir / nome
        textos[f"cobertura/{nome}"] = p.read_text(encoding="utf-8") if p.exists() else ""
    arquivos = {k: sha256_text(v) for k, v in sorted(textos.items())}
    val = yaml.safe_load(textos["valuation.yaml"]) or {}

    betas: dict[str, BetaSetor] = {}
    for r in _read_csv(textos["cobertura/betas_setor.csv"]):
        betas[r["industria_damodaran"]] = BetaSetor(
            industria=r["industria_damodaran"], beta_u_global=float(r["beta_u_global"]),
            beta_u_em=float(r["beta_u_em"]), financeira=r["financeira"].strip().lower() == "true",
            data_ref=r["data_ref"], url=r["url"])
    arqs: dict[str, Arquetipo] = {}
    for r in _read_csv(textos["cobertura/arquetipos.csv"]):
        fim = _opt_str(r.get("fim_concessao"))
        arqs[r["issuer_id"]] = Arquetipo(
            issuer_id=r["issuer_id"], arquetipo=r["arquetipo"],
            industria_damodaran=r["industria_damodaran"],
            moeda_demonstrativos=_opt_str(r.get("moeda_demonstrativos")),
            lambda_=float(r.get("lambda") or 1.0),
            linha_valuation=_opt_str(r.get("linha_valuation")),
            fim_concessao=int(float(fim)) if fim else None, nota=(r.get("nota") or "").strip(),
            fim_concessao_fonte=(r.get("fim_concessao_fonte") or "").strip())
    unidades = {r["ticker"]: {"acoes_por_unidade": float(r["acoes_por_unidade"]),
                              "conferido": r.get("conferido", "").strip().lower() == "true",
                              "url": _opt_str(r.get("url")), "nota": (r.get("nota") or "").strip()}
                for r in _read_csv(textos["cobertura/unidades.csv"])}
    sotp = yaml.safe_load(textos["cobertura/sotp.yaml"]) or {}
    etfs = yaml.safe_load(textos["cobertura/etfs.yaml"]) or {}
    _validar(val, arqs, betas)
    return ParametrosCobertura(valuation=val, arquetipos=arqs, betas=betas, unidades=unidades,
                               sotp=sotp, etfs=etfs, arquivos=arquivos)


def arquetipo_padrao(issuer_id: str, setor_gics: str) -> Arquetipo:
    """Arquétipo de reserva para emissores fora do arquivo curado (ex.: universo sintético)."""
    if setor_gics == "Financials":
        arq, ind = "banco", "Banks (Regional)"
    elif setor_gics == "Utilities":
        arq, ind = "utilidade_regulada", "Utility (General)"
    elif setor_gics == "Real Estate":
        arq, ind = "imobiliario", "Real Estate (Development)"
    elif setor_gics in ("Energy",):
        arq, ind = "commodity", "Oil/Gas (Integrated)"
    elif setor_gics in ("Materials",):
        arq, ind = "commodity", "Metals & Mining"
    else:
        arq, ind = "corporativo", "Total Market"
    return Arquetipo(issuer_id=issuer_id, arquetipo=arq, industria_damodaran=ind,
                     moeda_demonstrativos=None, lambda_=1.0, linha_valuation=None,
                     fim_concessao=None, nota="arquétipo pelo setor GICS (emissor fora do arquivo curado)")


__all__ = ["ARQUETIPOS", "Arquetipo", "BetaSetor", "DEFAULT_COBERTURA_DIR", "DEFAULT_VALUATION",
           "METODOS", "MOEDA_PAIS", "NOME_METODO", "ParametrosCobertura", "arquetipo_padrao",
           "carregar_parametros"]
