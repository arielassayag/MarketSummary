"""Disponibilidade prospectiva dos participantes; não certifica publicação/PIT."""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC

import pandas as pd

from .temporal import validar as validar_corte

VERSAO = "cdp.disponibilidade_participantes/v3"
GRAO = ("issuer_id", "origem", "item", "freq", "period_end", "uso")
FREQUENCIAS = {"A", "Q", "TTM", "YTD", "H1", "9M", "FRE", "SNAPSHOT", "D"}
IDENTIDADE = (*GRAO, "period_start", "entidade", "identidade_declarada", "contexto",
              "tipo_grao", "grupo", "posicao", "valor", "coeficiente", "currency", "consolidado")


def _texto(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if not pd.api.types.is_scalar(value):
        return None
    if pd.isna(value):
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _grupos(row):
    """Campo explícito prevalece totalmente; na sua ausência conserva todas as notas."""
    raw = row.get("componentes_fluxo")
    ausente = (raw is None or raw is pd.NA or raw is pd.NaT
               or (pd.api.types.is_scalar(raw) and pd.isna(raw)))
    if not ausente:
        return [("campo", json.loads(raw) if isinstance(raw, str) else raw)]
    restante = str(row.get("nota", ""))
    grupos = []
    while "componentes_fluxo=" in restante:
        restante = restante.split("componentes_fluxo=", 1)[1]
        grupo, tamanho = json.JSONDecoder().raw_decode(restante)
        grupos.append(("nota", grupo))
        # Não procura marcadores dentro de strings do próprio JSON já consumido.
        restante = restante[tamanho:]
    return grupos


def participante(row, uso, *, issuer_id=None, origem="demonstrativos", fonte=None):
    """Conserva a disponibilidade da linha escolhida e de cada componente explícito."""
    out = {"uso": uso, "issuer_id": _texto(issuer_id or row.get("issuer_id")), "origem": origem,
           "item": _texto(row.get("item")), "freq": _texto(row.get("freq")),
           "period_end": _texto(row.get("period_end")),
           "disponivel_desde": _texto(row.get("disponivel_desde")),
           "fonte": deepcopy(fonte) if fonte is not None else {
               k: _texto(row.get(k)) for k in ("fonte", "url", "documento", "sha256", "data_publicacao")}}
    # Contexto do consumidor não substitui identidade explicitamente declarada na entrada.
    out["identidade_declarada"] = {k: _texto(row.get(k)) for k in ("issuer_id", "origem")
                                  if _texto(row.get(k)) is not None}
    if _texto(row.get("entidade")) is not None:
        out["entidade"] = _texto(row.get("entidade"))
    if "period_start" in row and _texto(row.get("period_start")) is not None:
        out["period_start"] = _texto(row.get("period_start"))
    try:
        grupos = _grupos(row)
        if not grupos:
            return out  # Um fluxo reportado não exige trimestres inventados.
        out["componentes"] = []
        out["grupos_componentes"] = []
        contexto = {k: out[k] for k in ("issuer_id", "origem", "entidade") if k in out}
        for grupo, (onde, componentes) in enumerate(grupos):
            if not isinstance(componentes, list) or not componentes:
                raise ValueError("componentes ausentes")
            indices = []
            for posicao, componente in enumerate(componentes):
                if not isinstance(componente, Mapping) or not isinstance(componente.get("fonte"), Mapping):
                    raise ValueError("componente incompleto")
                index = len(out["componentes"])
                member = deepcopy(dict(componente))
                for key in ("item", "freq", "period_start", "period_end", "issuer_id", "origem", "entidade"):
                    if key in member:
                        member[key] = _texto(member[key])
                member.update({"uso": f"{uso}/componente:{index}", "grupo": grupo, "posicao": posicao,
                    "contexto": deepcopy(contexto),
                    "tipo_grao": "intervalo" if "period_start" in componente else "periodico",
                    "disponivel_desde": _texto(componente.get("disponivel_desde")
                        if "disponivel_desde" in componente else componente["fonte"].get("disponivel_desde"))})
                out["componentes"].append(member)
                indices.append(index)
            out["grupos_componentes"].append({"origem": onde, "indices": indices})
    except (TypeError, ValueError):
        out["componentes_incompletos"] = True
    return out


def _identidade(member):
    return {k: deepcopy(member[k]) for k in IDENTIDADE if k in member}


def _chave(member):
    return tuple(member.get(k) for k in GRAO)


def _valor(pac, destino):
    if destino.startswith("historico."):
        _, item, ano = destino.split(".")
        return (pac.get("historico") or {}).get(item, {}).get(ano)
    if destino.startswith("serie_acoes."):
        dia = destino.removeprefix("serie_acoes.")
        return next((v for d, v in pac.get("serie_acoes", []) if d == dia), None)
    return pac.get(destino)


def _destinos_financeiros(pac):
    usados = {k for k, v in pac.items() if k.startswith("t.") and v is not None}
    usados.update(f"historico.{item}.{ano}" for item, anos in (pac.get("historico") or {}).items()
                  for ano, v in anos.items() if v is not None)
    usados.update(f"serie_acoes.{d}" for d, v in pac.get("serie_acoes", []) if v is not None)
    usados.update(k for k in ("unidades", "receita_ano_anterior") if pac.get(k) is not None)
    return usados


class RegistroParticipantes:
    """Registro no ponto de uso; vínculo de completude, nunca autoridade documental/PIT."""

    def __init__(self, issuer_id):
        self.issuer_id = issuer_id
        self.rows = []
        self.esperados = []
        self.vinculos = {}

    def registrar(self, row, uso, destino=None, *, origem="demonstrativos", fonte=None):
        if row is None:
            return
        member = participante(row, uso, issuer_id=self.issuer_id, origem=origem, fonte=fonte)
        self.rows.append(member)
        self.esperados.append({**_identidade(member), "componentes": [
            _identidade(c) for c in member.get("componentes", [])],
            "grupos_componentes": deepcopy(member.get("grupos_componentes", []))})
        self.vinculos.setdefault(destino or uso, []).append(uso)

    def finalizar(self, pac):
        pac["disponibilidade_demonstrativos"] = deepcopy(self.rows)
        pac["manifesto_disponibilidade"] = {"versao": VERSAO, "issuer_id": self.issuer_id,
            "participantes_esperados": deepcopy(self.esperados),
            "vinculos": {destino: {"usos": sorted(usos), "valor": deepcopy(_valor(pac, destino))}
                         for destino, usos in sorted(self.vinculos.items())}}


def _periodo(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("período ausente")
    periodo = pd.Timestamp(value)
    if pd.isna(periodo) or periodo.tzinfo is not None or periodo != periodo.normalize():
        raise ValueError("período financeiro inválido")
    return periodo


def _declaracao_incompativel(declarada, contexto):
    for key in ("issuer_id", "origem", "entidade"):
        if key in declarada:
            value = declarada[key]
            if not isinstance(value, str) or not value.strip():
                return True
            if key in contexto and value != contexto[key]:
                return True
    return False


def _conferir_componentes(row):
    componentes = row.get("componentes", [])
    grupos = row.get("grupos_componentes", [])
    if not isinstance(componentes, list) or not isinstance(grupos, list):
        return "componentes ou grupos incompletos"
    contexto = {k: row[k] for k in ("issuer_id", "origem", "entidade") if k in row}
    vistos = []
    for grupo, declaracao in enumerate(grupos):
        if not isinstance(declaracao, Mapping) or declaracao.get("origem") not in {"campo", "nota"}:
            return "grupo de componentes incompleto"
        indices = declaracao.get("indices")
        if not isinstance(indices, list) or not indices:
            return "grupo de componentes vazio"
        operacoes = set()
        for posicao, index in enumerate(indices):
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(componentes):
                return "índice de componente inválido"
            member = componentes[index]
            if not isinstance(member, Mapping) or not isinstance(member.get("fonte"), Mapping):
                return "proveniência de componente incompleta"
            if member.get("contexto") != contexto or _declaracao_incompativel(member, contexto):
                return "identidade declarada de componente incompatível com o contexto"
            if member.get("grupo") != grupo or member.get("posicao") != posicao \
                    or member.get("uso") != f"{row['uso']}/componente:{index}":
                return "ordem ou vínculo de componente incompatível"
            if not isinstance(member.get("item"), str) or not member["item"].strip():
                return "componente sem item"
            tipo = member.get("tipo_grao")
            if tipo not in {"intervalo", "periodico"}:
                return "grão de componente inválido"
            if (tipo == "periodico" or "freq" in member) and member.get("freq") not in FREQUENCIAS:
                return "frequência de componente inválida"
            try:
                fim = _periodo(member.get("period_end"))
                if fim > _periodo(row["period_end"]):
                    return "componente posterior ao período do participante"
                if tipo == "intervalo" and _periodo(member.get("period_start")) > fim:
                    return "intervalo de componente inválido"
            except (ValueError, TypeError, OverflowError):
                return "período de componente inválido"
            campos = ("valor", "coeficiente", "currency", "consolidado")
            if tipo == "intervalo" and any(k not in member for k in campos):
                return "semântica de componente intervalar incompleta"
            for key in ("valor", "coeficiente"):
                if key in member:
                    value = member[key]
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                        return "valor ou coeficiente de componente inválido"
            if "currency" in member:
                moeda = member["currency"]
                if not isinstance(moeda, str) or len(moeda) != 3 or not moeda.isalpha() or not moeda.isupper():
                    return "moeda de componente inválida"
            if "consolidado" in member and not isinstance(member["consolidado"], bool):
                return "base de componente inválida"
            # YTD pode reutilizar o intervalo com sinais opostos; usos/grupos são distintos.
            operacao = tuple(member.get(k) for k in ("item", "freq", "period_start", "period_end", "coeficiente"))
            if operacao in operacoes:
                return "operação duplicada na mesma composição"
            operacoes.add(operacao)
            vistos.append(index)
    if vistos != list(range(len(componentes))):
        return "grupos não cobrem os componentes na ordem declarada"
    return None


def _conferir_manifesto(pac, rows):
    manifesto = pac.get("manifesto_disponibilidade")
    if not isinstance(manifesto, Mapping) or manifesto.get("versao") != VERSAO:
        return "manifesto de participantes ausente ou versão inválida"
    if not pac.get("issuer_id") or manifesto.get("issuer_id") != pac.get("issuer_id"):
        return "identidade do manifesto incompatível com o emissor"
    esperados = manifesto.get("participantes_esperados")
    vinculos = manifesto.get("vinculos")
    if not isinstance(esperados, list) or not isinstance(vinculos, Mapping):
        return "manifesto de participantes incompleto"
    vistos = []
    for row in rows:
        if not isinstance(row, Mapping):
            return "participante incompleto"
        componentes = row.get("componentes", [])
        if not isinstance(componentes, list):
            return "componentes incompletos"
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in GRAO):
            return "participante sem identidade/grão/uso"
        if row["issuer_id"] != pac["issuer_id"] or not isinstance(row.get("fonte"), Mapping):
            return "proveniência ou identidade do participante incompatível"
        if row["freq"] not in FREQUENCIAS or row["origem"] not in {"demonstrativos", "oficial", "mercado"}:
            return "frequência ou origem de participante inválida"
        declarada = row.get("identidade_declarada")
        if not isinstance(declarada, Mapping) or _declaracao_incompativel(declarada, row):
            return "identidade declarada de participante incompatível com o contexto"
        try:
            periodo = _periodo(row["period_end"])
            if periodo.date().isoformat() > pac["as_of"]:
                return "período financeiro posterior à data do modelo"
            if "period_start" in row and _periodo(row["period_start"]) > periodo:
                return "intervalo do participante inválido"
        except (ValueError, TypeError, OverflowError):
            return "período financeiro inválido"
        problema = _conferir_componentes(row)
        if problema:
            return problema
        vistos.append({**_identidade(row), "componentes": [_identidade(c) for c in componentes],
                       "grupos_componentes": deepcopy(row.get("grupos_componentes", []))})
    if vistos != esperados or len({_chave(r) for r in rows}) != len(rows):
        return "participantes divergentes do manifesto (omissão, alteração ou duplicata)"
    usos = [r["uso"] for r in rows]
    if len(set(usos)) != len(usos):
        return "usos duplicados"
    usados_vinculados = []
    for destino, vinculo in vinculos.items():
        if not isinstance(destino, str) or not isinstance(vinculo, Mapping):
            return "vínculo de uso inválido"
        membros = vinculo.get("usos")
        if not isinstance(membros, list) or not membros or any(u not in usos for u in membros):
            return "uso financeiro sem participante"
        if vinculo.get("valor") != _valor(pac, destino):
            return "vínculo financeiro alterado"
        usados_vinculados.extend(membros)
    if sorted(usados_vinculados) != sorted(usos) or not _destinos_financeiros(pac) <= set(vinculos):
        return "manifesto não cobre os usos financeiros do pacote"
    if pac.get("unidades") is not None:
        fontes = (pac.get("contagem") or {}).get("fontes_participantes")
        if not isinstance(fontes, list) or not fontes:
            return "contagem sem fontes participantes"
        contagem_usos = set(vinculos["unidades"]["usos"])
        for origem in fontes:
            if not any(r["uso"] in contagem_usos and r["origem"] == origem for r in rows):
                return "fonte efetiva da contagem omitida"
    return None


def conferir(pac):
    """Todos os participantes têm instante explícito <= corte; nenhum max omite NA."""
    try:
        if not isinstance(pac.get("as_of"), str):
            raise ValueError("data do modelo ausente")
        corte = validar_corte(pac.get("corte_temporal"), as_of=pac.get("as_of"))
        limite = pd.Timestamp(corte["conhecimento_ate"]).tz_convert(UTC)
    except (TypeError, ValueError, KeyError):
        return False, "disponibilidade observada: corte temporal ausente ou inválido"
    rows = pac.get("disponibilidade_demonstrativos")
    if not isinstance(rows, list) or not rows:
        return False, "disponibilidade observada: participantes financeiros ausentes"
    if not any(isinstance(r, Mapping) and r.get("origem") == "demonstrativos" for r in rows):
        return False, "disponibilidade observada: demonstrativos participantes ausentes"
    try:
        problema = _conferir_manifesto(pac, rows)
    except (TypeError, ValueError, KeyError, AttributeError):
        problema = "manifesto ou vínculo financeiro malformado"
    if problema:
        return False, "disponibilidade observada não comprovada: " + problema
    falhas = []
    total = 0
    for row in rows:
        if not isinstance(row, Mapping):
            falhas.append("participante incompleto")
            continue
        if row.get("componentes_incompletos"):
            falhas.append(f"{row.get('uso')}: componentes incompletos")
        componentes = row.get("componentes", [])
        if not isinstance(componentes, list):
            falhas.append(f"{row.get('uso')}: componentes incompletos")
            componentes = []
        for member in [row, *componentes]:
            total += 1
            if not isinstance(member, Mapping):
                falhas.append("componente incompleto")
                continue
            uso = member.get("uso", "participante")
            try:
                stamp = pd.Timestamp(member.get("disponivel_desde"))
                if pd.isna(stamp) or stamp.tzinfo is None or stamp.utcoffset() is None:
                    falhas.append(f"{uso}: disponibilidade ausente ou sem fuso")
                elif stamp.tz_convert(UTC) > limite:
                    falhas.append(f"{uso}: disponibilidade posterior ao corte")
                fonte = member.get("fonte", {})
                if "disponivel_desde" in fonte:
                    fonte_stamp = pd.Timestamp(fonte["disponivel_desde"])
                    if pd.isna(fonte_stamp) or fonte_stamp.tzinfo is None or fonte_stamp.utcoffset() is None:
                        falhas.append(f"{uso}: disponibilidade na fonte ausente ou sem fuso")
                    elif fonte_stamp.tz_convert(UTC) > limite:
                        falhas.append(f"{uso}: disponibilidade na fonte posterior ao corte")
                    elif pd.notna(stamp) and stamp.tzinfo is not None and stamp.utcoffset() is not None \
                            and stamp.tz_convert(UTC) != fonte_stamp.tz_convert(UTC):
                        falhas.append(f"{uso}: recibo do participante diverge da fonte")
            except (ValueError, TypeError, OverflowError):
                falhas.append(f"{uso}: disponibilidade inválida")
    if falhas:
        detalhe = "; ".join(falhas[:3])
        resto = f"; mais {len(falhas) - 3} falha(s)" if len(falhas) > 3 else ""
        return False, f"disponibilidade observada não comprovada ({len(falhas)} falha(s)): {detalhe}{resto}"
    return True, (f"{total} participantes disponíveis até o corte UTC {corte['conhecimento_ate']}; "
                  "elegibilidade prospectiva; publicação primária/PIT histórico não certificados")
