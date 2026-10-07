"""PROTÓTIPO PRIVADO: cenários de atribuição, distintos de medições primárias.

Não escreve livro/modelo/ETF, não muda gates e não certifica publicação ou PIT.
Autoridades vêm das referências externas seladas; cenários aceitam apenas etapa.
"""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from ..data import publico_resultados as R
from ..data.ri_captura.adapter import texto
from ..data.ri_captura.configuracao import carregar_contexto_ri
from ..data.ri_captura.observado import instant, sha
from ..data.ri_captura.transporte import reabrir_insumos_ri
from ..data.snapshot import load_snapshot
from .contexto import montar_contexto
from .insumos import ESTOQUES, FLUXOS, preparar, taxa_publica
from .modelo import Avaliador
from .motor import _tp_do_avaliador, tp_deterministico
from .parametros import carregar_parametros
from .ponte import GRUPOS, ORDEM, ponte
from .resultado import ativo as resultado_ativo
from .resultado import visao

SCHEMA = "cdp.atribuicao_endpoint_derivada/v2"
# Metadados acompanham valores; não mudam a conta nem a ordem da atribuição.
DEPENDENCIAS = {
    "estimativas": ("item_patrimonio", "item_lucro", "dps_anual", "fim_exercicio_consenso", "periodos_fluxos",
                    "moedas_fluxos", "bases_fluxos", "historico_fontes", "historico_periodos",
                    "historico_moedas", "historico_bases", "resultado_ebitda_base"),
    "estrutura_capital": ("contagem",),
    "cambio": (), "preco": (), "rolagem": (),
}
ARQUIVOS_ECONOMICOS = frozenset(("valuation.yaml", "cobertura/arquetipos.csv",
    "cobertura/betas_setor.csv", "cobertura/unidades.csv", "cobertura/sotp.yaml", "cobertura/etfs.yaml"))
CATALOGOS_DOCUMENTAIS = frozenset(("resultado_evidencias.json",))


def _mapa(value):
    return value if isinstance(value, dict) else {}


def _presente(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _periodo_dominio(value):
    """Normaliza só a representação do mesmo grão; não rola ou agrega períodos."""
    if not isinstance(value, str):
        return None
    aliases = {"anual": "A", "12 meses": "TTM", "trimestral": "Q", "semestral": "H1"}
    match = re.fullmatch(r"(A|TTM|Q|H1)\|(\d{4}-\d{2}-\d{2})", value)
    if match is None:
        match = re.fullmatch(r"(anual|12 meses|trimestral|semestral) até (\d{4}-\d{2}-\d{2})", value)
    if match is None:
        return None
    try:
        end = date.fromisoformat(match[2]).isoformat()
    except ValueError:
        return None
    return aliases.get(match[1], match[1]) + "|" + end


def _dominio_item(pacote, item, ano=None):
    """Metadados reextraídos, incluindo estoques fora de bases_fluxos."""
    key = "t." + item
    if ano is None:
        value = pacote.get(key)
        source = _mapa(_mapa(pacote.get("fontes")).get(key))
        row = next((r for r in pacote.get("tabela_insumos", []) if r.get("id") == key), {})
        base = source.get("base_contabil")
        currency = source.get("moeda_fonte")
        period = _periodo_dominio(str(source.get("freq_fonte")) + "|" + str(source.get("fim_fonte")))
        unit = row.get("unidade")
        concept = item
        conflicts = []
        if item == "ebitda" and source.get("fonte") == "CODIGO":
            # A visão literal de resultado deriva EBITDA dos dois fatos primários.
            # Sua fonte CODIGO não repete base/moeda/janela. O domínio deriva dos
            # componentes vinculados; não infere metadata/publicação da captura.
            components = [_dominio_item(pacote, k) for k in ("ebit", "d_a")]
            sources = [_mapa(_mapa(pacote.get("fontes")).get("t." + k)) for k in ("ebit", "d_a")]
            binding = (source.get("fato_ebit_id") == sources[0].get("fato_resultado_id")
                       and source.get("fato_d_a_id") == sources[1].get("fato_resultado_id")
                       and all(s.get("fato_resultado_id") for s in sources)
                       and source.get("valor_modelo") == value
                       and _mapa(pacote.get("resultado_ebitda_base")).get("disponivel") is True)
            left, right = components
            same = all(left.get(k) is not None and left.get(k) == right.get(k)
                       for k in ("base", "moeda_fonte", "unidade_modelo", "periodo"))
            if binding and same and all(c["presente"] and not c["conflitos"] for c in components):
                base, currency, period = (components[0][k] for k in ("base", "moeda_fonte", "periodo"))
                if unit != components[0]["unidade_modelo"]:
                    conflicts.append("EBITDA e seus componentes têm unidades diferentes")
            else:
                conflicts.append("EBITDA derivado sem domínio homogêneo dos componentes vinculados")
        if item in FLUXOS:
            for mapping, expected, name in (("bases_fluxos", base, "base"),
                    ("moedas_fluxos", currency, "moeda"), ("periodos_fluxos", period, "período")):
                declared = _mapa(pacote.get(mapping)).get(item)
                if mapping == "periodos_fluxos":
                    declared = _periodo_dominio(declared)
                if declared != expected:
                    conflicts.append(name + ": mapa e fonte não correspondem")
                if mapping == "bases_fluxos":
                    base = declared
                elif mapping == "moedas_fluxos":
                    currency = declared
                else:
                    period = declared
    else:
        value = _mapa(_mapa(pacote.get("historico")).get(item)).get(ano)
        source = _mapa(_mapa(_mapa(pacote.get("historico_fontes")).get(item)).get(ano))
        base = _mapa(_mapa(pacote.get("historico_bases")).get(item)).get(ano)
        currency = _mapa(_mapa(pacote.get("historico_moedas")).get(item)).get(ano)
        period = _periodo_dominio(_mapa(_mapa(pacote.get("historico_periodos")).get(item)).get(ano))
        concept = source.get("item_fonte")
        # O preparador normaliza histórico de ações como contagem (fator 1), e
        # demais itens como totais na moeda do modelo. Isto descreve essa saída;
        # não preenche unidade/escala desconhecida de uma fonte primária.
        unit = ("acoes" if item.startswith("acoes_") and item in ESTOQUES else
                "total:" + pacote["moeda"] if item in (*FLUXOS, *ESTOQUES) and pacote.get("moeda") else None)
        conflicts = []
        for expected, declared, name in ((base, source.get("base_contabil"), "base"),
                (currency, source.get("moeda_fonte"), "moeda"),
                (period, _periodo_dominio(str(source.get("freq_fonte")) + "|" + str(source.get("fim_fonte"))), "período")):
            if declared != expected:
                conflicts.append(name + ": mapa histórico e fonte não correspondem")
        if _presente(value) and source.get("valor_modelo") != value:
            conflicts.append("valor histórico não corresponde à proveniência")
    return {"presente": _presente(value), "base": base, "moeda_fonte": currency,
            "unidade_modelo": unit, "periodo": period, "conceito": concept,
            "conflitos": conflicts}


def _dominio_economico(anterior, novo):
    """Abstém intermediários sem domínio comparável; endpoints ficam intactos.

    Não implementa transformação documental entre bases, unidades ou janelas.
    Estoque e fluxo mantêm seus grãos próprios; Q de estoque não precisa ser TTM.
    """
    pairs = []
    items = sorted({k[2:] for p in (anterior, novo) for k in p if k.startswith("t.")})
    for item in items:
        pairs.append(("t." + item, _dominio_item(anterior, item), _dominio_item(novo, item)))
    history = sorted(set(_mapa(anterior.get("historico"))) | set(_mapa(novo.get("historico"))))
    for item in history:
        years = sorted(set(_mapa(_mapa(anterior.get("historico")).get(item))) |
                       set(_mapa(_mapa(novo.get("historico")).get(item))))
        for year in years:
            pairs.append(("historico." + item + "." + year,
                          _dominio_item(anterior, item, year), _dominio_item(novo, item, year)))
    reasons, records = [], {}
    for selector in ("item_patrimonio", "item_lucro"):
        if anterior.get(selector) != novo.get(selector):
            reasons.append(selector + ": conceito selecionado muda sem transformação documental; intermediário não definido")
    for name, old, new in pairs:
        if not old["presente"] and not new["presente"]:
            continue  # ausente continua ausente, nunca zero
        records[name] = {"anterior": old, "novo": new}
        if old["presente"] != new["presente"]:
            reasons.append(name + ": componente ausente em um endpoint; domínio não demonstrado")
        for side, record in (("anterior", old), ("novo", new)):
            if not record["presente"]:
                continue
            reasons.extend(name + ": " + side + ": " + x for x in record["conflitos"])
            for dimension in ("base", "moeda_fonte", "unidade_modelo", "periodo", "conceito"):
                value = record[dimension]
                if dimension == "base":
                    valid = value in ("consolidado", "individual")
                elif dimension == "moeda_fonte":
                    valid = isinstance(value, str) and re.fullmatch(r"[A-Z]{3}", value) is not None
                else:
                    valid = isinstance(value, str) and bool(value)
                if not valid:
                    reasons.append(name + ": " + side + ": " + dimension + " desconhecido; domínio não demonstrado")
        if old["presente"] and new["presente"]:
            for dimension in ("base", "moeda_fonte", "unidade_modelo", "periodo", "conceito"):
                if old[dimension] != new[dimension]:
                    reasons.append(name + ": " + dimension + " muda sem transformação documental; intermediário não definido")
    # Um par igualmente misto não é domínio homogêneo. Contagens não são totais
    # monetários; estoques preservam sua própria data, sem exigir duração TTM.
    for side in ("anterior", "novo"):
        layers = {}
        for name, pair in records.items():
            record = pair[side]
            if not record["presente"] or not str(record["unidade_modelo"]).startswith("total:"):
                continue
            layer = "corrente" if name.startswith("t.") else "historico." + name.rsplit(".", 1)[1]
            layers.setdefault(layer, []).append(record)
        for layer, rows in layers.items():
            for dimension in ("base", "moeda_fonte", "unidade_modelo"):
                known = {r[dimension] for r in rows if r[dimension] is not None}
                if len(known) > 1:
                    reasons.append(side + ": " + layer + ": " + dimension + " heterogêneo; sem transformação documental")
    return list(dict.fromkeys(reasons)), records


def _dependencias_obrigatorias(spec):
    """Fechamento de caminhos, além do transporte: não confiar em inventário incompleto."""
    refs = {Path(spec[k]).resolve() for k in ("valuation", "ri_config", "resultado_catalogo")}
    refs |= {Path(v["path"]).resolve() for v in spec["resultado_documentos"].values()}
    for key in ("mercado", "transporte", "cobertura"):
        refs |= {p.resolve() for p in Path(spec[key]).rglob('*') if p.is_file()}
    cfgpath = Path(spec["ri_config"])
    cfg = json.loads(cfgpath.read_bytes())
    for name in ("master", "identidade", "custodia"):
        path = Path(cfg[name]["path"])
        if not path.is_absolute():
            path = cfgpath.parent / path
        refs.add(path.resolve())
        body = json.loads(path.read_bytes())
        if name == "master":
            refs |= {Path(body[k]).resolve() for k in ("master_path", "observacao_path")}
        elif name == "identidade":
            refs |= {Path(body["registro"][k]).resolve() for k in ("raw_path", "receipt_path")}
        else:
            refs |= {Path(v[k]).resolve() for v in body["entradas"].values() for k in ("bruto", "recibo")}
    # Cache refere-se a este programa congelado; alteração de algoritmo invalida a key.
    refs |= {p.resolve() for p in Path(__file__).resolve().parents[2].rglob('*.py')}
    return refs


def reextrair_resultado(spec, cut):
    """Refaz desde PDFs, não de um catálogo derivado que alegue seu próprio hash."""
    path = Path(spec["resultado_catalogo"])
    estrutura = json.loads(path.read_bytes())
    if (estrutura.get("schema") != R.SCHEMA or set(estrutura) !=
            {"schema", "documentos", "eventos", "pontes_subtotal"}):
        raise ValueError("atribuição: catálogo documental fora do domínio explícito")
    def keys(value, allowed, required=()):
        if (type(value) is not dict or set(value) - set(allowed)
                or not set(required) <= set(value)):
            raise ValueError("atribuição: campo documental desconhecido/ausente no contrato tipado")
    for doc in estrutura["documentos"]:
        keys(doc, ("issuer_id", "url", "sha256", "versao", "provas", "publicacao", "tabelas"),
             ("issuer_id", "url", "sha256", "tabelas"))
        if "publicacao" in doc:
            keys(doc["publicacao"], ("pagina", "texto", "disponivel_desde", "tipo"),
                 ("pagina", "texto", "disponivel_desde"))
        for proof in doc.get("provas", []):
            keys(proof, ("pagina", "papel", "ancoras", "data_regex"), ("pagina", "papel", "ancoras"))
        for table in doc["tabelas"]:
            keys(table, ("pagina", "ancoras", "cabecalho", "colunas", "moeda", "escala", "itens", "fim_tabela"),
                 ("pagina", "ancoras", "cabecalho", "colunas", "moeda", "escala", "itens"))
            for col in table["colunas"]:
                keys(col, ("inicio", "fim", "freq"), ("inicio", "fim", "freq"))
            for item in table["itens"]:
                keys(item, ("item", "rotulos", "coeficiente", "conceito", "fim_busca"), ("item", "rotulos"))
    for event in estrutura["eventos"]:
        keys(event, ("issuer_id", "tipo", "identidade", "medida_item", "documentos_prova", "papeis_prova",
                     "medida_documentos", "medida_periodo"),
             ("issuer_id", "tipo", "identidade", "medida_item", "documentos_prova", "papeis_prova",
              "medida_documentos", "medida_periodo"))
        keys(event["identidade"], ("entidade", "objeto", "contraparte", "contrato"),
             ("entidade", "objeto", "contraparte", "contrato"))
        keys(event["medida_periodo"], ("inicio", "fim", "freq"), ("inicio", "fim", "freq"))
    for subtotal in estrutura["pontes_subtotal"]:
        keys(subtotal, ("documento_id", "total", "componentes"), ("documento_id", "total", "componentes"))
    partes = []
    for doc in estrutura["documentos"]:
        ref = spec["resultado_documentos"][doc["sha256"]]
        raw = Path(ref["path"]).read_bytes()
        partes.append(R.extrair(raw, doc, instant(ref["captura"]), cut))
    cat = R.construir(partes, estrutura, cut)
    cat["estrutura_json"] = R.texto_json(estrutura)
    cat["estrutura_arquivo_sha256"] = sha(path.read_bytes())
    cat.pop("catalogo_sha256")
    cat["catalogo_sha256"] = R.hash_obj(cat)
    return cat


class Etapa(StrEnum):
    BASE = "base"
    ROLAGEM = "rolagem"
    ESTIMATIVAS = "estimativas"
    PARAMETROS = "parametros"
    ESTRUTURA_CAPITAL = "estrutura_capital"
    CAMBIO = "cambio"
    PRECO = "preco"
    METODOS = "metodos"


@dataclass(frozen=True, slots=True)
class FonteEndpoint:
    """Descriptor/digest previamente confiados fora do candidato ou da saída financeira."""
    arquivo: Path
    sha256_esperado: str
    _retrato: RetratoPonte | None = field(default=None, init=False, repr=False, compare=False)

    def reextrair(self) -> RetratoPonte:
        if type(self) is not FonteEndpoint:
            raise ValueError("atribuição: tipo de fonte externa inválido")
        raw = self.arquivo.read_bytes()
        if sha(raw) != self.sha256_esperado:
            raise ValueError("atribuição: referência externa mudou")
        s = json.loads(raw)
        if s.get("schema") != "cdp.fonte_endpoint_confiada_privada/v1":
            raise ValueError("atribuição: schema externo inválido")
        if not _dependencias_obrigatorias(s) <= {Path(p).resolve() for p in s["dependencias"]}:
            raise ValueError("atribuição: fechamento de dependências externo incompleto")
        for path, h in s["dependencias"].items():
            if sha(Path(path).read_bytes()) != h:
                raise ValueError("atribuição: dependência externa mudou: " + path)
        # Derivação integral inicial imutável. Revalidar todos os backing bytes a
        # cada acesso prova que o cálculo continua sendo função das mesmas fontes;
        # não há cache recebido de candidato, metadado ou transporte.
        if self._retrato is not None:
            if sha(self.arquivo.read_bytes()) != self.sha256_esperado:
                raise ValueError("atribuição: referência externa mudou durante validação de cache")
            return self._retrato
        cut = instant(s["conhecimento_ate"])
        md = load_snapshot(Path(s["mercado"]), verify=True)
        params = carregar_parametros(s["valuation"], s["cobertura"])
        if params.hash() != s["parametros_sha256"]:
            raise ValueError("atribuição: parâmetros do endpoint divergem da âncora externa")
        ctxri = carregar_contexto_ri(s["ri_config"], sha256_esperado=s["ri_config_sha256"])
        fornecedor = reabrir_insumos_ri(s["transporte"], sha256_esperado=s["transporte_sha256"],
            md=md, contexto=ctxri, params=params, conhecimento_ate=cut)
        if set(params.arquivos) != ARQUIVOS_ECONOMICOS | CATALOGOS_DOCUMENTAIS:
            raise ValueError("atribuição: conjunto de parâmetros fora do domínio explícito")
        cat = reextrair_resultado(s, cut)
        cats = fornecedor.dados.resultado_evidencias["catalogo_json"].tolist()
        if cats != [R.texto_json(cat)]:
            raise ValueError("atribuição: catálogo derivado não corresponde à extração dos PDFs externos")
        primary = R.tabela_fatos(cat).set_index("fato_resultado_id")
        dem = fornecedor.dados.demonstrativos
        actual = dem.loc[dem["fato_resultado_id"].notna()].set_index("fato_resultado_id")
        if set(primary.index) != set(actual.index):
            raise ValueError("atribuição: inventário dos fatos do endpoint difere dos PDFs")
        for fid, row in primary.iterrows():
            observed = actual.loc[fid]
            for key in ("issuer_id", "item", "value", "currency", "freq", "consolidado", "sha256",
                        "period_start", "period_end", "data_coleta", "disponivel_desde"):
                if observed[key] != row[key]:
                    raise ValueError("atribuição: fato do endpoint difere dos bytes primários")
        data = date.fromisoformat(fornecedor.dados.corte_temporal["data_modelo"])
        pacotes = preparar(md, fornecedor.dados, params,
                           sorted(str(i) for i in md.universe.issuers.index), data)
        if resultado_ativo(params):
            pacotes = {iid: visao(p, params) for iid, p in pacotes.items()}
        rf, rf_data, rf_fonte = taxa_publica(fornecedor.dados, md, str(params.cc["rf_usd_serie"]), data)
        ctx = montar_contexto(pacotes, params, rf, rf_fonte,
                             ri_fornecedor=fornecedor, conhecimento_ate=cut)
        iid = s["issuer_id"]
        if iid not in pacotes:
            raise ValueError("atribuição: identidade ausente no endpoint")
        tp = tp_deterministico(pacotes[iid], ctx, params, rf, rf_fonte,
                              ri_fornecedor=fornecedor, conhecimento_ate=cut)
        # Catálogo estrutural contém bytes documentais, não uma regra de valuation.
        # Cada catálogo está autenticado integralmente acima. Só os parâmetros de cálculo
        # e os cinco arquivos de cobertura precisam coincidir entre vintages.
        econ = sha(texto({"valuation": params.valuation,
                          "arquivos": {k: h for k, h in params.arquivos.items()
                                       if k in ARQUIVOS_ECONOMICOS}}).encode())
        result = RetratoPonte(self, iid, cut.isoformat(), texto(pacotes[iid]), texto(ctx),
                             texto({"valor": rf, "data": rf_data, "fonte": rf_fonte}),
                             params.hash(), econ, tp)
        # Autenticação posterior: nenhuma troca durante extração/avaliação é aceita.
        if sha(self.arquivo.read_bytes()) != self.sha256_esperado:
            raise ValueError("atribuição: fonte mudou durante extração")
        for path, h in s["dependencias"].items():
            if sha(Path(path).read_bytes()) != h:
                raise ValueError("atribuição: dependência mudou durante extração")
        object.__setattr__(self, "_retrato", result)
        return result

    def parametros(self):
        raw = self.arquivo.read_bytes()
        if sha(raw) != self.sha256_esperado:
            raise ValueError("atribuição: parâmetros sem âncora externa")
        s = json.loads(raw)
        p = carregar_parametros(s["valuation"], s["cobertura"])
        if p.hash() != s["parametros_sha256"]:
            raise ValueError("atribuição: parâmetros alterados")
        return p


@dataclass(frozen=True, slots=True)
class RetratoPonte:
    fonte: FonteEndpoint
    issuer_id: str
    conhecimento_ate: str
    pacote_json: str
    contexto_json: str
    rf_json: str
    parametros_sha256: str
    configuracao_economica_sha256: str
    tp_recalculado: float | None


@dataclass(frozen=True, slots=True)
class CenarioDerivado:
    """Receita autorizada; não aceita pacote, medição ou assinatura interna como autoridade."""
    sessao: SessaoAtribuicao
    etapa: Etapa


@dataclass(frozen=True, slots=True)
class AvaliacaoCenario:
    etapa: str
    valor: float | None
    razoes: tuple[str, ...]
    pacote_numerico_json: str
    contexto_numerico_json: str
    proveniencia_json: str
    natureza: str = "contrafactual de atribuição; não é medição primária"


def _projetar(p, c):
    # Estes traços são origens emprestadas, não certificam o objeto virtual.
    # Conservá-los mantém as mesmas escolhas econômicas do núcleo (PL/NCI e EBIT).
    # A autoridade para o cenário é a sessão reextraída, nunca estes metadados.
    return deepcopy(p), deepcopy(c)


@dataclass(frozen=True, slots=True)
class SessaoAtribuicao:
    anterior: RetratoPonte
    novo: RetratoPonte
    conhecimento_ate: datetime

    def __post_init__(self):
        self._revalidar()

    def _revalidar(self):
        if type(self) is not SessaoAtribuicao:
            raise ValueError("atribuição: tipo de sessão inválido")
        cut = instant(self.conhecimento_ate)
        for r in (self.anterior, self.novo):
            if type(r) is not RetratoPonte or type(r.fonte) is not FonteEndpoint:
                raise ValueError("atribuição: endpoint externo tipado obrigatório")
            if r.fonte.reextrair() != r:
                raise ValueError("atribuição: endpoint não corresponde à reextração integral externa")
            if instant(r.conhecimento_ate) > cut:
                raise ValueError("atribuição: endpoint conhecido após o corte externo da sessão")
        if self.anterior.issuer_id != self.novo.issuer_id:
            raise ValueError("atribuição: identidade incompatível")
        if instant(self.anterior.conhecimento_ate) > instant(self.novo.conhecimento_ate):
            raise ValueError("atribuição: ordem temporal de endpoints inválida")

    def cenario(self, etapa):
        if type(etapa) is not Etapa:
            raise ValueError("atribuição: etapa fora do plano fechado")
        return CenarioDerivado(self, etapa)

    def _materializar(self, etapa):
        old, new = json.loads(self.anterior.pacote_json), json.loads(self.novo.pacote_json)
        a, b = json.loads(self.anterior.contexto_json), json.loads(self.novo.contexto_json)
        rf_a, rf_b = json.loads(self.anterior.rf_json), json.loads(self.novo.rf_json)
        p, c, rf = deepcopy(old), deepcopy(a), deepcopy(rf_a)
        origins = {k: "anterior" for k in p}
        source_origins = {k: "anterior" for k in p.get("fontes", {})}
        table_origins = {r["id"]: "anterior" for r in p.get("tabela_insumos", [])}
        ctx_origin = "anterior"
        if etapa != Etapa.BASE:
            for group in ORDEM:
                if group == "parametros":
                    c, rf, ctx_origin = deepcopy(b), deepcopy(rf_b), "novo"
                elif group == "metodos":
                    p = deepcopy(new)
                    origins = {k: "novo" for k in p}
                    source_origins = {k: "novo" for k in p.get("fontes", {})}
                    table_origins = {r["id"]: "novo" for r in p.get("tabela_insumos", [])}
                else:
                    keys = set(GRUPOS[group]) | set(DEPENDENCIAS[group])
                    if group == "estimativas":
                        keys |= {k for k in set(p) | set(new) if k.startswith("t.")}
                    for k in keys:
                        p[k] = deepcopy(new.get(k))
                        origins[k] = "novo"
                        if k in new.get("fontes", {}) or k in p.get("fontes", {}):
                            p.setdefault("fontes", {})[k] = deepcopy(new.get("fontes", {}).get(k))
                            source_origins[k] = "novo"
                            origins["fontes"] = "derivado_por_campo"
                    rows_new = {r["id"]: r for r in new.get("tabela_insumos", [])}
                    rows = [deepcopy(rows_new[r["id"]]) if r["id"] in keys and r["id"] in rows_new else deepcopy(r)
                            for r in p.get("tabela_insumos", []) if r["id"] not in keys or r["id"] in rows_new]
                    existing = {r["id"] for r in rows}
                    rows += [deepcopy(r) for key, r in rows_new.items() if key in keys and key not in existing]
                    p["tabela_insumos"] = rows
                    origins["tabela_insumos"] = "derivado_por_id"
                    for key in keys:
                        if key in rows_new:
                            table_origins[key] = "novo"
                        else:
                            table_origins.pop(key, None)
                    if group == "estimativas":
                        # Não reaplica evento no cenário: valores/camadas vêm do endpoint.
                        for k in ("ri_observada", "visao_resultado", "resultado_reportado", "resultado_evidencias"):
                            p[k] = deepcopy(new.get(k))
                            origins[k] = "novo"
                if group == etapa.value:
                    break
        reasons = []
        domain_reasons, domain_records = _dominio_economico(old, new)
        for k in ("linha", "moeda", "issuer_id", "acoes_por_linha", "fator_moeda", "fim_exercicio"):
            if old.get(k) != new.get(k):
                reasons.append(k + ": domínio muda entre endpoints; intermediário não definido")
        # Um endpoint final segue reproduzível mesmo se o caminho intermediário não tem domínio.
        if etapa in (Etapa.BASE, Etapa.METODOS):
            reasons = []
        else:
            reasons.extend(domain_reasons)
            if self.anterior.configuracao_economica_sha256 != self.novo.configuracao_economica_sha256:
                reasons.append("regra econômica/tabelas distintas: intermediário fora do domínio fechado")
        proof = {"schema": SCHEMA, "etapa": etapa.value, "ordem": list(ORDEM),
                 "campos": origins, "fontes": source_origins, "tabela_insumos": table_origins, "contexto": ctx_origin,
                 "endpoints_externos": [self.anterior.fonte.sha256_esperado, self.novo.fonte.sha256_esperado],
                 "params_endpoints": [self.anterior.parametros_sha256, self.novo.parametros_sha256],
                 "catalogos_documentais_permitidos": sorted(CATALOGOS_DOCUMENTAIS),
                 "dominio_economico": domain_records,
                 "view_ebit_origem": origins.get("t.ebit"),
                 "view_ebit_endpoint_sha256": ((new if origins.get("t.ebit")=="novo" else old).get("visao_resultado") or {}).get("visao_sha256"),
                 "publicacao_certificada": False, "medicao_primaria": False,
                 "conhecimento_ate": instant(self.conhecimento_ate).isoformat()}
        p, c = _projetar(p, c)
        return p, c, rf, proof, reasons

    def avaliar(self, cenario):
        if type(cenario) is not CenarioDerivado or cenario.sessao is not self or type(cenario.etapa) is not Etapa:
            raise ValueError("atribuição: cenário não pertence à sessão/receita fechada")
        self._revalidar()
        p, c, rf, proof, reasons = self._materializar(cenario.etapa)
        value = None
        if not reasons:
            av = _AvaliadorDerivado(self, cenario.etapa, p, c, rf)
            value = _tp_do_avaliador(av, p)
            if value is None:
                reasons = [str(x.get("motivo")) for x in av.lacunas if x.get("motivo")]
                if not reasons:
                    reasons = ["caso-base sem método/dividendo/preço elegível no núcleo existente"]
        self._revalidar()
        return AvaliacaoCenario(cenario.etapa.value, value, tuple(reasons), texto(p), texto(c), texto(proof))

    def _entrada_da_ponte(self, etapa):
        """Comprova a ordem/chamada recebida da orquestração legada, sem novas contas."""
        old, new = json.loads(self.anterior.pacote_json), json.loads(self.novo.pacote_json)
        p, c, rf = deepcopy(old), json.loads(self.anterior.contexto_json), json.loads(self.anterior.rf_json)["valor"]
        if etapa is not Etapa.BASE:
            for group in ORDEM:
                if group == "parametros":
                    c, rf = json.loads(self.novo.contexto_json), json.loads(self.novo.rf_json)["valor"]
                elif group == "metodos":
                    p = deepcopy(new)
                else:
                    p.update({key: new.get(key) for key in GRUPOS[group]})
                    if group == "estimativas":
                        p.update({key: new.get(key) for key in set(p) | set(new) if key.startswith("t.")})
                if group == etapa.value:
                    break
        return p, c, rf

    def ponte(self):
        """A função de soma/resíduo existente é usada literalmente, sem emitir G7."""
        self._revalidar()
        old, new = json.loads(self.anterior.pacote_json), json.loads(self.novo.pacote_json)
        ca, cb = json.loads(self.anterior.contexto_json), json.loads(self.novo.contexto_json)
        ra, rb = json.loads(self.anterior.rf_json)["valor"], json.loads(self.novo.rf_json)["valor"]
        if self.anterior.tp_recalculado is None or self.novo.tp_recalculado is None:
            return {"componentes": None, "nota": "endpoint sem alvo recalculado; não inventar base/G7",
                    "g7_observado": False, "natureza": SCHEMA}
        stages = iter([Etapa.BASE, *[Etapa(s) for s in ORDEM]])
        records = []
        def callback(p, c, r):
            # Estes mappings são gerados pela ponte fechada, não vêm de candidato externo.
            stage = next(stages)
            if texto((p, c, r)) != texto(self._entrada_da_ponte(stage)):
                raise ValueError("atribuição: orquestração diverge da receita fechada")
            result = self.avaliar(self.cenario(stage))
            records.append(result)
            return result.valor
        out = ponte(self.anterior.tp_recalculado, old, new, ca, cb, ra, rb,
                    self.novo.tp_recalculado, callback)
        out["cenarios"] = [{"etapa": x.etapa, "valor": x.valor, "razoes": list(x.razoes),
                            "proveniencia": json.loads(x.proveniencia_json)} for x in records]
        out.update(natureza=SCHEMA, g7_observado=False, alvo_anterior_publicado=False,
                   nota_escopo="endpoints recalculados; sem referência externa a alvo publicado, nenhum G7 é emitido")
        return out


class _AvaliadorDerivado(Avaliador):
    """Somente TP privado: não passa por API de pacote primário nem exporta modelo."""
    def __init__(self, sessao, etapa, p, c, rf):
        if type(sessao) is not SessaoAtribuicao or type(etapa) is not Etapa:
            raise ValueError("atribuição: núcleo exige sessão tipada")
        sessao._revalidar()
        expected = sessao._materializar(etapa)
        if texto((p, c, rf)) != texto(expected[:3]):
            raise ValueError("atribuição: payload difere da receita rederivada")
        params = (sessao.anterior if etapa is Etapa.BASE else sessao.novo).fonte.parametros()
        self._inicializar_numerico(p, c, params, rf["valor"], rf["fonte"])

    def avaliar(self):
        raise ValueError("atribuição: cenário virtual não é um modelo primário exportável")
