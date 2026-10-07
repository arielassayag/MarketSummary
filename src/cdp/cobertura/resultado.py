"""Visão econômica com ponte primária de EBIT, ativada somente por política versionada.

Preserva pacote reportado. Não estima imposto de evento, lucro líquido, EPS, giro
ou ROU. Catálogo/fatos/binds e resultados são autenticados e a visão antecede todo
contexto/custo/modelo. Cobertura parcial não certifica resultado recorrente integral.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal
from typing import Any

from ..data.publico_resultados import SCHEMA, hash_obj, instante
from .formato import r6, valor

METODO = "eventos_evidenciados"
VERSAO = "ponte_ebit/1"
CAMPOS = (
    "t.ebit",
    "t.ebitda",
    "t.d_a",
    "resultado_ebitda_base",
    "historico",
    "fontes",
    "tabela_insumos",
    "periodos_fluxos",
    "moedas_fluxos",
    "bases_fluxos",
    "historico_fontes",
    "historico_periodos",
    "historico_bases",
    "historico_moedas",
    "fator_moeda",
    "resultado_evidencias",
    "issuer_id",
    "moeda",
)


def ativo(params) -> bool:
    metodo = params.sec("projecao").get("normalizacao_resultado_metodo")
    if metodo not in (None, METODO):
        raise ValueError(f"Método de resultado desconhecido: {metodo!r}")
    return metodo == METODO


def _canon(v):
    if isinstance(v, float):
        return r6(v)
    if isinstance(v, Mapping):
        return {str(k): _canon(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_canon(x) for x in v]
    return v


def _campos(params):
    from .temporal import ativo as temporal_ativo
    return (*CAMPOS, "as_of", "corte_temporal") if temporal_ativo(params) else CAMPOS


def _catalogo(p, params):
    texto = p.get("resultado_evidencias")
    if texto is None:
        return None
    c = json.loads(texto)
    if c.get("schema") != SCHEMA or c.get("catalogo_sha256") != hash_obj(
        {k: v for k, v in c.items() if k != "catalogo_sha256"}
    ):
        raise ValueError("resultado: catálogo adulterado ou schema desconhecido")
    origem_hash = c.get("estrutura_arquivo_sha256")
    if origem_hash is not None and origem_hash != params.arquivos.get("resultado_evidencias.json"):
        raise ValueError("resultado: catálogo estrutural diverge da configuração selada")
    if (
        c.get("estrutura_json") is not None
        and hash_obj(json.loads(c["estrutura_json"])) != c["estrutura_sha256"]
    ):
        raise ValueError("resultado: estrutura do catálogo adulterada")
    corte = instante(c["conhecimento_ate"])
    from ..data.publico_arquivo import data_local
    from .temporal import ativo as temporal_ativo
    from .temporal import validar as validar_corte
    if temporal_ativo(params):
        contrato = validar_corte(p.get("corte_temporal"), as_of=p.get("as_of"))
        if p.get("as_of") is None or instante(contrato["conhecimento_ate"]) != corte:
            raise ValueError("resultado: corte do catálogo diverge do conhecimento do pacote")
        if any(instante(d["first_capture"]) > corte for d in c["documentos"]):
            raise ValueError("resultado: primeira captura posterior ao corte do pacote")
    elif p.get("as_of") is not None and data_local(corte).isoformat() > p["as_of"]:
        raise ValueError("resultado: conhecimento posterior à data do pacote")
    for campo in ("documentos", "fatos", "provas", "eventos"):
        if any(instante(f["disponivel_desde"]) > corte for f in c[campo]):
            raise ValueError("resultado: catálogo contém dependência posterior ao corte")
    return c


def _janela(f, e):
    ini, fim = f["inicio"], f["fim"]
    ei, ef = e["reconhecimento_inicio"], e["reconhecimento_fim"]
    if fim < ei or ini > ef:
        return "fora_janela"
    if ini <= ei <= ef <= fim:
        return "incluido_comprovado"
    return "reconhecimento_indeterminado"


def ponte_fato(fato_id: str, cat: Mapping[str, Any], *, issuer_id: str) -> dict[str, Any]:
    fatos = {f["fato_id"]: f for f in cat["fatos"]}
    eventos = {e["evento_id"]: e for e in cat["eventos"] if e["issuer_id"] == issuer_id}
    if len(fatos) != len(cat["fatos"]) or len(eventos) != len(
        [e for e in cat["eventos"] if e["issuer_id"] == issuer_id]
    ):
        raise ValueError("resultado: identidade duplicada no catálogo")
    f = fatos.get(fato_id)
    if f is None or f["item"] != "ebit" or f["issuer_id"] != issuer_id or f["valor"] is None:
        return {
            "status": "vinculo_nao_comprovado",
            "apos_ajustes": None,
            "reportado": None,
            "ajustes": [],
            "motivo": "fato primário de EBIT não vinculado ao insumo",
        }
    aplicados = []
    total = Decimal(0)
    motivos = []

    def contribuicao(fato, evento, trilha):
        estado = _janela(fato, evento)
        if estado == "fora_janela":
            return Decimal(0), [
                {
                    "evento_id": evento["evento_id"],
                    "fato_id": fato["fato_id"],
                    "estado": estado,
                    "coeficiente_evento": "0",
                    "trilha": trilha,
                    "contribuicao": "0",
                }
            ]
        if estado != "incluido_comprovado":
            raise ValueError("reconhecimento_indeterminado")
        if fato.get("componentes"):
            soma = Decimal(0)
            detalhe = []
            for componente in fato["componentes"]:
                cf = fatos.get(componente["fato_id"])
                if (
                    cf is None
                    or cf["moeda"] != fato["moeda"]
                    or cf["base"] != fato["base"]
                    or cf["item"] != "ebit"
                ):
                    raise ValueError("componentes de EBIT incompatíveis/ausentes")
                co = Decimal(componente["coeficiente"])
                v, ds = contribuicao(cf, evento, [*trilha, componente])
                soma += co * v
                detalhe += ds
            if sum(
                Decimal(fatos[c["fato_id"]]["valor"]) * Decimal(c["coeficiente"])
                for c in fato["componentes"]
            ) != Decimal(fato["valor"]):
                raise ValueError("identidade derivada conflitante")
            return soma, detalhe
        binds = [
            b
            for b in cat["bindings"]
            if b["evento_id"] == evento["evento_id"] and b["fato_ebit_id"] == fato["fato_id"]
        ]
        # Duplicação idêntica é erro de catálogo; conflito não escolhe um lado.
        if len(binds) != 1:
            raise ValueError("vinculo_nao_comprovado" if not binds else "vinculo_conflitante")
        b = binds[0]
        medida = fatos.get(b["medida_fato_id"])
        provas = {p["prova_id"] for p in cat["provas"]}
        if (
            medida is None
            or b["medida_fato_id"] != evento["medida_fato_id"]
            or set(b["provas"]) != set(evento["provas"])
            or not set(b["provas"]) <= provas
            or evento["moeda"] != fato["moeda"]
            or evento["base"] != fato["base"]
            or medida["moeda"] != fato["moeda"]
            or medida["base"] != fato["base"]
            or medida["inicio"] != fato["inicio"]
            or medida["fim"] != fato["fim"]
            or medida["valor"] != evento["contribuicao_pre_imposto"]
        ):
            raise ValueError("vinculo_conflitante")
        ganho = Decimal(medida["valor"]) * Decimal(b["coeficiente"])
        return ganho, [
            {
                "evento_id": evento["evento_id"],
                "fato_id": fato["fato_id"],
                "medida_fato_id": medida["fato_id"],
                "estado": estado,
                "coeficiente_evento": b["coeficiente"],
                "contribuicao": str(ganho),
                "trilha": trilha,
                "provas": b["provas"],
            }
        ]

    for e in eventos.values():
        if e["tipo"] != "alienacao_controle":
            motivos.append("natureza do evento fora da política")
            continue
        try:
            v, ds = contribuicao(f, e, [])
            total += v
            aplicados += ds
        except (ValueError, KeyError, TypeError) as exc:
            motivos.append(str(exc))
    ds = [f["disponivel_desde"], *[e["disponivel_desde"] for e in eventos.values()]]
    return {
        "fato_id": fato_id,
        "status": "ausente" if motivos else "apos_ajustes_evidenciados",
        "motivo": "; ".join(motivos) or "ponte pré-imposto de eventos catalogados",
        "reportado": f["valor"],
        "contribuicao_excluida": str(total) if not motivos else None,
        "apos_ajustes": str(Decimal(f["valor"]) - total) if not motivos else None,
        "ajustes": aplicados,
        "recusas": motivos,
        "disponivel_desde": max(ds),
        "resultado_recorrente_certificado": False,
    }


def _fonte_id(fonte):
    return fonte.get("fato_resultado_id") if isinstance(fonte, Mapping) else None


def _aplicar(p, cat):
    eventos = [] if cat is None else [e for e in cat["eventos"] if e["issuer_id"] == p["issuer_id"]]
    diagnosticos = {}
    fator = p.get("fator_moeda")

    def linha(valor_bruto, fonte, periodo, moeda_fonte, base):
        if not eventos:
            return {
                "status": "sem_eventos_catalogados",
                "valor_reportado_modelo": valor_bruto,
                "valor_apos_ajustes_modelo": valor_bruto,
                "ajustes": [],
                "resultado_recorrente_certificado": False,
            }
        fid = _fonte_id(fonte)
        fator_linha = (
            float(fonte["fator_moeda_resultado"])
            if isinstance(fonte, Mapping)
            and fonte.get("fator_moeda_resultado") not in (None, "None")
            else fator
        )
        if fid:
            d = ponte_fato(fid, cat, issuer_id=p["issuer_id"])
            fs = [f for f in cat["fatos"] if f["fato_id"] == fid]
            if (
                fs
                and fator_linha is not None
                and r6(float(Decimal(fs[0]["valor"])) * fator_linha) != valor_bruto
            ):
                raise ValueError(
                    "resultado: fonte primária diverge numericamente do valor modelado"
                )
            from .reinvestimento import _periodo_valido

            per = _periodo_valido(periodo)
            if (
                not fs
                or fs[0]["freq"] not in {"A", "TTM"}
                or per is None
                or per.split("|")[1] != fs[0]["fim"]
                or moeda_fonte != fs[0]["moeda"]
                or base != fs[0]["base"]
            ):
                d.update(
                    {
                        "status": "vinculo_conflitante",
                        "apos_ajustes": None,
                        "motivo": "período/moeda/base do insumo divergem do fato primário",
                    }
                )
            v = (
                None
                if d["apos_ajustes"] is None or fator_linha is None
                else r6(float(Decimal(d["apos_ajustes"])) * fator_linha)
            )
        else:
            # Só a dedução temporal é possível sem bind ao fornecedor; nunca aproximar valores.
            try:
                freq, fim = periodo.split("|")
                if freq not in {"A", "TTM"}:
                    raise ValueError("janela não certificada")
                import pandas as pd

                ini = (
                    (pd.Timestamp(fim) - pd.DateOffset(years=1) + pd.Timedelta(days=1))
                    .date()
                    .isoformat()
                )
                fora = all(
                    _janela({"inicio": ini, "fim": fim}, e) == "fora_janela" for e in eventos
                )
            except (ValueError, TypeError, AttributeError):
                fora = False
            v = valor_bruto if fora else None
            d = {
                "status": "fora_janela" if fora else "vinculo_nao_comprovado",
                "ajustes": [],
                "motivo": "evento fora da janela"
                if fora
                else "fato primário de EBIT não vinculado ao insumo",
            }
        d.update(
            {
                "valor_reportado_modelo": valor_bruto,
                "valor_apos_ajustes_modelo": v,
                "fator_moeda": fator_linha,
                "fonte_reportada": deepcopy(fonte),
            }
        )
        return d

    bruto = p.get("t.ebit")
    fonte = p.get("fontes", {}).get("t.ebit")
    d = linha(
        bruto,
        fonte,
        p.get("periodos_fluxos", {}).get("ebit"),
        p.get("moedas_fluxos", {}).get("ebit"),
        p.get("bases_fluxos", {}).get("ebit"),
    )
    diagnosticos["corrente"] = d
    p["t.ebit"] = d["valor_apos_ajustes_modelo"]
    historico = p.get("historico", {}).get("ebit", {})
    dh = {}
    for ano, v in list(historico.items()):
        fonte_h = p.get("historico_fontes", {}).get("ebit", {}).get(ano)
        hd = linha(
            v,
            fonte_h,
            p.get("historico_periodos", {}).get("ebit", {}).get(ano),
            p.get("historico_moedas", {}).get("ebit", {}).get(ano),
            p.get("historico_bases", {}).get("ebit", {}).get(ano),
        )
        historico[ano] = hd["valor_apos_ajustes_modelo"]
        dh[ano] = hd
        if fonte_h is not None:
            fonte_h.update(
                {
                    "valor_modelo_reportado": fonte_h["valor_modelo"],
                    "valor_modelo": historico[ano],
                    "ponte_ebit": hd,
                }
            )
    diagnosticos["historico"] = dh
    if eventos:
        if fonte is not None:
            fonte.update(
                {
                    "valor_modelo_reportado": bruto,
                    "valor_modelo": p["t.ebit"],
                    "ponte_ebit": deepcopy(d),
                }
            )
        for r in p.get("tabela_insumos", []):
            if r.get("id") == "t.ebit":
                r.update(
                    {
                        "valor_reportado": r["valor"],
                        "valor": p["t.ebit"],
                        "nome": "EBIT após ajustes evidenciados",
                        "ponte_ebit": deepcopy(d),
                        "valor_texto": valor(p["t.ebit"], r["unidade"]),
                    }
                )
        afeta_ebitda = d.get("valor_apos_ajustes_modelo") is None or d.get(
            "contribuicao_excluida"
        ) not in (None, "0")
        if not afeta_ebitda:
            return diagnosticos
        # EBITDA reportado pode já excluir o evento. Só derive com D&A operacional provada
        # da mesma janela/base/moeda; nunca retire o ganho duas vezes do subtotal reportado.
        da_fonte = p.get("fontes", {}).get("t.d_a")
        da_fid = _fonte_id(da_fonte)
        da = next((f for f in cat["fatos"] if f["fato_id"] == da_fid), None)
        eb = next((f for f in cat["fatos"] if f["fato_id"] == _fonte_id(fonte)), None)
        fator_da = (
            float(da_fonte["fator_moeda_resultado"])
            if isinstance(da_fonte, Mapping)
            and da_fonte.get("fator_moeda_resultado") not in (None, "None")
            else fator
        )
        from .reinvestimento import _periodo_valido

        periodo_da = _periodo_valido(p.get("periodos_fluxos", {}).get("d_a"))
        valido_da = (
            da is not None
            and eb is not None
            and da["valor"] is not None
            and Decimal(da["valor"]) >= 0
            and da["conceito"] == "depreciacao_amortizacao_operacional"
            and all(da[k] == eb[k] for k in ("inicio", "fim", "moeda", "base"))
            and periodo_da is not None
            and periodo_da.split("|")[1] == da["fim"]
            and p.get("moedas_fluxos", {}).get("d_a") == da["moeda"]
            and p.get("bases_fluxos", {}).get("d_a") == da["base"]
            and fator_da is not None
            and r6(float(Decimal(da["valor"])) * fator_da) == p.get("t.d_a")
        )
        EBITDA = (
            None
            if p["t.ebit"] is None or not valido_da or p.get("t.d_a") is None
            else r6(p["t.ebit"] + p["t.d_a"])
        )
        p["resultado_ebitda_base"] = {
            "metodo": "EBIT após ajustes + D&A operacional compatível",
            "disponivel": EBITDA is not None,
        }
        p["t.ebitda"] = EBITDA
        f_ebitda = {
            "fonte": "CODIGO",
            "documento": "EBIT após ajustes evidenciados + D&A operacional compatível",
            "fato_ebit_id": _fonte_id(fonte),
            "fato_d_a_id": da_fid,
            "valor_modelo": EBITDA,
            "catalogo_sha256": cat["catalogo_sha256"],
        }
        p.setdefault("fontes", {})["t.ebitda"] = f_ebitda
        for r in p.get("tabela_insumos", []):
            if r.get("id") == "t.ebitda":
                r.update(
                    {
                        "valor_reportado": r["valor"],
                        "valor": EBITDA,
                        "valor_texto": valor(EBITDA, r["unidade"]),
                        "nome": "EBITDA após ajustes evidenciados",
                        **f_ebitda,
                    }
                )
        diagnosticos["ebitda"] = {
            "valor_apos_ajustes_modelo": EBITDA,
            "metodo": "EBIT após ajustes + D&A operacional compatível",
            "d_a_fato_id": da_fid,
            "compativel": bool(valido_da),
        }
        if p["t.ebit"] is None:
            p.setdefault("lacunas", []).append(
                {
                    "insumo": "t.ebit",
                    "nome": "EBIT após ajustes evidenciados",
                    "motivo": d.get("motivo", "ponte não comprovada"),
                }
            )
    return diagnosticos


def visao(pac: Mapping[str, Any], params) -> dict[str, Any]:
    """Cópia idempotente; hash protegido contra edição dos insumos consumidos."""
    if not ativo(params):
        return dict(pac)
    p = deepcopy(dict(pac))
    existente = p.get("visao_resultado")
    if existente:
        esperado = hash_obj(_canon({k: p.get(k) for k in _campos(params)}))
        if (
            existente["insumos_visao_sha256"] != esperado
            or existente["politica"] != METODO
            or existente["versao"] != VERSAO
        ):
            raise ValueError("resultado: visão econômica adulterada/incompatível")
        bruto = p["resultado_reportado"]
        if existente["reportado_sha256"] != hash_obj(_canon(bruto)):
            raise ValueError("resultado: pacote reportado adulterado")
        # Refaz a derivação desde o reportado; não confia num marcador editável.
        novo = deepcopy(p)
        for k in _campos(params):
            if k in bruto:
                novo[k] = deepcopy(bruto[k])
            else:
                novo.pop(k, None)
        novo.pop("visao_resultado", None)
        novo.pop("resultado_reportado", None)
        refeito = visao(novo, params)
        if refeito["visao_resultado"]["visao_sha256"] != existente["visao_sha256"]:
            raise ValueError("resultado: recálculo da visão não confere")
        return p
    cat = _catalogo(p, params)
    bruto = deepcopy({k: p[k] for k in _campos(params) if k in p})
    diagnostico = _aplicar(p, cat)
    assinatura = {
        "politica": METODO,
        "versao": VERSAO,
        "catalogo_sha256": None if cat is None else cat["catalogo_sha256"],
        "conhecimento_ate": None if cat is None else cat["conhecimento_ate"],
        "escopo": "catálogo parcial; não certifica integralmente o resultado recorrente",
        "reportado_sha256": hash_obj(_canon(bruto)),
        "diagnostico": diagnostico,
        "insumos_visao_sha256": hash_obj(_canon({k: p.get(k) for k in _campos(params)})),
    }
    assinatura["visao_sha256"] = hash_obj(_canon(assinatura))
    p["resultado_reportado"] = bruto
    p["visao_resultado"] = assinatura
    return p


def assinar_contexto(ctx, pacotes, params):
    """Sela uma etapa interna de contexto/calibração construída do mesmo conjunto de visões."""
    if not ativo(params):
        return ctx
    esperado = {i: visao(p, params)["visao_resultado"]["visao_sha256"] for i, p in pacotes.items()}
    existente = ctx.get("visoes_resultado")
    if existente is not None and existente != esperado:
        raise ValueError("resultado: conjunto do contexto difere das visões")
    novo = dict(ctx)
    novo["visoes_resultado"] = esperado
    novo.pop("resultado_contexto_sha256", None)
    novo["resultado_contexto_sha256"] = hash_obj(_canon(novo))
    return novo


def validar_contexto(pac, ctx, params):
    if not ativo(params):
        return pac
    p = visao(pac, params)
    if ctx.get("resultado_contexto_sha256") != hash_obj(
        _canon({k: v for k, v in ctx.items() if k != "resultado_contexto_sha256"})
    ):
        raise ValueError("resultado: contexto adulterado")
    if (ctx.get("visoes_resultado") or {}).get(p["issuer_id"]) != p["visao_resultado"][
        "visao_sha256"
    ]:
        raise ValueError("resultado: contexto não corresponde à visão econômica do emissor")
    return p
