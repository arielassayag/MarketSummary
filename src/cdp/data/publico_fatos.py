"""Motor point-in-time comum (CVM, SEC, Yahoo): fatos brutos → linhas canônicas A/Q/TTM.

Entrada: fatos com ``FATO_COLUNAS`` (:mod:`.publico_cvm`) mais ``fonte`` e ``sha256`` (do arquivo
bruto de origem). Em ``as_of``:

1. só fatos com ``received_date <= as_of`` (data de publicação: CVM ``DT_RECEB``; SEC ``filed``);
2. **moeda vigente**: por entidade, só a moeda de apresentação do documento mais recente
   publicado até ``as_of`` (quem muda de moeda — ARS → USD, MXN → USD — nunca tem séries que
   misturam moedas; períodos só disponíveis na moeda antiga ficam ausentes e a troca é
   registrada em ``attrs['moeda_trocada']``);
3. por (entidade, item, início, fim), a publicação mais recente (data, depois versão);
4. **fluxos** — ``A``: valor de 12 meses (350–380 dias) do período; ``Q``: trimestre discreto
   (3 meses reportado; senão diferença de acumulados do mesmo exercício; Q4 = anual − 9M);
   ``TTM``: anual quando o período fecha o exercício, senão soma de 4 trimestres discretos.
   ``consolidado`` de ``Q``/``TTM`` derivados = todos os documentos usados consolidados (base
   mista registrada em ``nota``);
5. **saldos** (CVM/SEC) — só em datas-base de períodos (fins de mês com fluxo do emissor):
   ``Q`` em toda data-base; ``A`` só no fim de exercício (data com fluxo de 12 meses). Saldos
   em datas avulsas (abertura IFRS 16, entidade antes de reorganização, data de capa) não
   viram período.

Com semântica explícita, ``data_publicacao`` de Q/TTM derivados é a máxima dos componentes
efetivamente usados, cujas datas, valores, coeficientes e fontes são preservados em ``nota``.
Sem metadado semântico, mantém-se a publicação histórica do documento de ``period_end``.
Derivados calculados por código: ``ebitda = ebit + d_a``,
``fcf = cfo − capex``, ``divida_liquida = divida_bruta − caixa − aplicacoes_cp`` (aplicações
ausentes ⇒ só caixa, com nota). Componente ausente ⇒ derivado ausente (nunca zero).
"""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .fundamentals_pit import _QUARTER_DAYS as _QUARTER_DIAS
from .fundamentals_pit import _match_end, _months_back, _quarter_value, _ttm_value

FLUXOS = frozenset({
    "receita", "lucro_bruto", "ebit", "ebitda", "d_a", "resultado_financeiro", "lucro_antes_ir",
    "ir_csll", "lucro_liquido", "lucro_liquido_controladores", "cfo", "capex", "fcf",
    "d_a_dfc", "adicoes_direito_uso", "depreciacao_direito_uso",
    "variacao_capital_giro_operacional", "juros_pagos_operacionais",
    "dividendos_pagos", "arrendamentos_pagos", "recompras", "margem_financeira", "receita_servicos", "despesa_pdd",
})

SAIDA_COLUNAS = [
    "entidade", "demonstrativo", "freq", "period_end", "item", "value", "currency", "escala",
    "consolidado", "fonte", "url", "documento", "data_publicacao", "sha256", "pit_estimado",
    "nota",
]

_ANUAL = (350, 380)
METADADOS_OBSERVADOS = ('disponivel_desde', 'disponibilidade_tipo',
                       'data_recebimento_documento', 'received_date')


def _observado(m) -> bool:
    return str(m.get('disponibilidade_tipo')) == 'recepcao_observada'


def _publicacao_componentes(ms):
    if any(_observado(m) for m in ms) and any(pd.isna(m.get('data_publicacao')) for m in ms):
        return None
    return max(m['data_publicacao'] for m in ms)


def _max_recebimento_observado(values):
    """Agrega somente um domínio temporal; nunca transforma uma data civil em UTC."""
    if any(pd.isna(v) for v in values):
        return None
    stamps = [pd.Timestamp(v) for v in values]
    domains = {"instante" if t.tzinfo is not None else
               "civil" if t == t.normalize() else "sem_fuso" for t in stamps}
    if len(domains) != 1:
        return None
    return max(zip(values, stamps, strict=True), key=lambda pair: pair[1])[0]


def _disponibilidade_com_fuso(value):
    try:
        t = pd.Timestamp(value)
        return pd.notna(t) and t.tzinfo is not None
    except (ValueError, TypeError):
        return False


def _max_disponibilidade_observada(values):
    """Disponibilidade agregada exige instantes com fuso conhecido em todos os componentes."""
    if any(pd.isna(v) for v in values):
        return None
    stamps = [pd.Timestamp(v) for v in values]
    if any(t.tzinfo is None for t in stamps):
        return None
    return max(zip(values, stamps, strict=True), key=lambda pair: pair[1])[0]


def _observacao_componentes(ms):
    if not any(_observado(m) for m in ms):
        return {}
    out = {'disponibilidade_tipo': 'recepcao_observada'}
    for key in ('disponivel_desde', 'data_recebimento_documento', 'received_date'):
        values = [m.get(key) for m in ms]
        out[key] = (_max_recebimento_observado(values) if key == 'received_date' else
                    _max_disponibilidade_observada(values) if key == 'disponivel_desde' else
                    None if any(pd.isna(v) for v in values) else max(values))
    return out


def _fonte_componente(m):
    pub = m['data_publicacao']
    out = {k: m[k] for k in ('fonte', 'url', 'documento', 'sha256')}
    out['data_publicacao'] = None if pd.isna(pub) else pd.Timestamp(pub).date().isoformat()
    if _observado(m):
        out.update({k: (None if pd.isna(m.get(k)) else str(m[k])) for k in METADADOS_OBSERVADOS})
    return out


def _agora_observado():
    return datetime.now(UTC)


def _corte_observado(as_of, conhecimento_ate):
    if isinstance(as_of, datetime):
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError('seleção observada exige datetime com fuso explícito')
        cut = as_of.astimezone(UTC)
        civil = cut.astimezone(ZoneInfo('America/Sao_Paulo')).date()
    else:
        civil = as_of
        cut = datetime.combine(civil + timedelta(days=1), time(),
                               ZoneInfo('America/Sao_Paulo')).astimezone(UTC) - timedelta(microseconds=1)
    if conhecimento_ate is not None:
        if conhecimento_ate.tzinfo is None or conhecimento_ate.utcoffset() is None:
            raise ValueError('corte observado exige fuso explícito')
        cut = min(cut, conhecimento_ate.astimezone(UTC))
    return civil, min(cut, _agora_observado())


def _texto(v) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
        return None
    return str(v) or None


def _semantica(v) -> str | None:
    texto = _texto(v)
    return (texto.strip() or None) if texto is not None else None


def _meta(row) -> dict:
    semantica = _semantica(getattr(row, "semantica_fluxo", None))
    rubrica = _texto(getattr(row, "rubrica_reportada", None))
    nota = _texto(getattr(row, "nota", None))
    if semantica and semantica != "receita_dre":
        nota = _juntar(nota, f"semantica_fluxo={semantica}; rubrica reportada: {rubrica}")
    out = {
        "demonstrativo": row.demonstrativo, "currency": row.currency,
        "consolidado": bool(row.consolidado), "fonte": row.fonte, "url": row.url,
        "documento": row.documento, "data_publicacao": row.received_date, "sha256": row.sha256,
        "pit_estimado": bool(getattr(row, "pit_estimado", False)),
        "nota": nota, "semantica_fluxo": semantica, "rubrica_reportada": rubrica,
    }
    if str(getattr(row, 'disponibilidade_tipo', None)) == 'recepcao_observada':
        out['data_publicacao'] = getattr(row, 'data_publicacao_primaria', None)
        out.update({k: getattr(row, k, None) for k in METADADOS_OBSERVADOS})
        out['received_date'] = getattr(row, 'received_date_original', row.received_date)
    return out


def _moeda_vigente(f: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Mantém, por entidade, só a moeda do documento mais recente (ações não têm moeda)."""
    trocas: dict[str, dict] = {}
    com = f[f["currency"].notna()]
    if com.empty:
        return f, trocas
    manter = pd.Series(True, index=f.index)
    for ent, g in com.groupby("entidade", sort=False):
        moedas = set(g["currency"])
        if len(moedas) <= 1:
            continue
        ult = g[g["received_date"] == g["received_date"].max()]["currency"]
        atual = ult.value_counts().sort_index().idxmax()
        fora = g.index[g["currency"] != atual]
        manter.loc[fora] = False
        desde = g.loc[g["currency"] == atual, "received_date"].min()
        trocas[str(ent)] = {"moeda": atual, "anteriores": sorted(moedas - {atual}),
                            "desde": pd.Timestamp(desde).date().isoformat(),
                            "fatos_descartados": int(len(fora))}
    return f[manter], trocas


def _datas_base(f: pd.DataFrame) -> tuple[dict[str, set], dict[str, set]]:
    """Por entidade: fins de períodos com fluxo (80–380 dias) e fins de exercício (12 meses),
    sempre em fim de mês (datas avulsas — ex.: data de uma reorganização — não são datas-base)."""
    fl = f[f["item"].isin(FLUXOS) & f["period_start"].notna()]
    if fl.empty:
        return {}, {}
    dur = (fl["period_end"] - fl["period_start"]).dt.days + 1
    fl = fl.assign(_dur=dur)
    fl = fl[fl["_dur"].between(80, _ANUAL[1])
            & (fl["period_end"] + pd.Timedelta(days=1)).dt.is_month_start]
    todas = fl.groupby("entidade")["period_end"].agg(lambda x: set(x.dt.date)).to_dict()
    anuais = (fl[fl["_dur"].between(*_ANUAL)].groupby("entidade")["period_end"]
              .agg(lambda x: set(x.dt.date)).to_dict())
    return todas, anuais


def selecionar_pit(fatos: pd.DataFrame, as_of: date, *, conhecimento_ate: datetime | None = None) -> pd.DataFrame:
    """Linhas canônicas (``SAIDA_COLUNAS``) conhecidas em ``as_of`` — sem look-ahead."""
    if fatos is None or fatos.empty:
        return pd.DataFrame(columns=SAIDA_COLUNAS)
    f = fatos.copy()
    if "pit_estimado" not in f.columns:
        f["pit_estimado"] = False
    # fatos de fontes oficiais concatenados com os do Yahoo chegam com NaN aqui (≠ estimado)
    f["pit_estimado"] = f["pit_estimado"].astype("boolean").fillna(False).astype(bool)
    observed = (f['disponibilidade_tipo'].eq('recepcao_observada')
                if 'disponibilidade_tipo' in f else pd.Series(False, index=f.index))
    if observed.any():
        civil, cut = _corte_observado(as_of, conhecimento_ate)
        f['received_date_original'] = f['received_date']
        known_utc = f['received_date'].map(lambda v: pd.notna(v) and pd.Timestamp(v).tzinfo is not None)
        original_received = pd.to_datetime(f['received_date'], utc=True, format='mixed')
        # O instante de disponibilidade conserva hora/fuso; DT_RECEB é civil e separado.
        f['received_date'] = original_received
        empty = pd.Series(None, index=f.index, dtype=object)
        raw_available = f.get('disponivel_desde', empty)
        valid_available = raw_available.map(_disponibilidade_com_fuso)
        available = pd.to_datetime(raw_available.where(valid_available), utc=True, errors='coerce', format='mixed')
        received_civil = pd.to_datetime(f.get('data_recebimento_documento', empty), errors='coerce', format='mixed')
        observed_day = available.dt.tz_convert('America/Sao_Paulo').dt.tz_localize(None).dt.normalize()
        document_day = received_civil.dt.normalize()
        day = document_day.where(received_civil.notna(), observed_day)
        eligible = observed & available.notna() & available.le(pd.Timestamp(cut)) & day.le(pd.Timestamp(civil))
        legacy_day = original_received.dt.tz_localize(None).dt.normalize()
        local_day = original_received.dt.tz_convert('America/Sao_Paulo').dt.tz_localize(None).dt.normalize()
        legacy_day = legacy_day.where(~known_utc, local_day)
        legacy = (~observed & legacy_day.le(pd.Timestamp(civil))
                  & (~known_utc | original_received.le(pd.Timestamp(cut))))
        f = f[eligible | legacy]
    else:
        f["received_date"] = pd.to_datetime(f["received_date"])
    f["period_end"] = pd.to_datetime(f["period_end"])
    f["period_start"] = pd.to_datetime(f["period_start"])
    if not observed.any():
        f = f[f["received_date"] <= pd.Timestamp(as_of)]
    f = f[f["value"].notna()]
    f = f[np.isfinite(f["value"].astype(float))]
    if f.empty:
        return pd.DataFrame(columns=SAIDA_COLUNAS)
    f, trocas = _moeda_vigente(f)
    f = f.sort_values(["entidade", "item", "received_date", "version", "period_end"],
                      kind="stable")
    datas, anuais = _datas_base(f)
    oficiais = set(f.loc[f["fonte"].isin(["CVM", "SEC", "RI"]), "entidade"]) \
        if "fonte" in f.columns else set()
    linhas: list[dict] = []
    incompatibilidades: list[dict] = []
    for (ent, item), g in f.groupby(["entidade", "item"], sort=True):
        if item in FLUXOS:
            linhas.extend(_fluxo(ent, item, g, incompatibilidades))
        elif ent in oficiais:
            linhas.extend(_saldo(ent, item, g, datas.get(ent, set()), anuais.get(ent, set())))
        else:
            linhas.extend(_saldo(ent, item, g, None, None))
    out = pd.DataFrame(linhas)
    if out.empty:
        vazio = pd.DataFrame(columns=SAIDA_COLUNAS)
        vazio.attrs["moeda_trocada"] = trocas
        vazio.attrs["incompatibilidades_fluxos"] = incompatibilidades
        return vazio
    out = pd.concat([out, _derivados(out)], ignore_index=True)
    out["escala"] = 1
    if "nota" not in out.columns:
        out["nota"] = None
    out["value"] = out["value"].astype(float) + 0.0  # -0.0 ⇒ 0.0
    extras = [k for k in METADADOS_OBSERVADOS if k in out] if observed.any() else []
    out = (out[SAIDA_COLUNAS + extras]
           .sort_values(["entidade", "item", "freq", "period_end"], kind="stable")
           .reset_index(drop=True))
    out.attrs["moeda_trocada"] = trocas
    out.attrs["incompatibilidades_fluxos"] = incompatibilidades
    return out


def _base_janela(meta_end: dict[date, dict], fim: date, dias: int) -> tuple[bool, str | None]:
    """``consolidado`` = todos os documentos da janela ``(fim − dias, fim]`` consolidados."""
    ms = [m for e, m in meta_end.items() if fim - pd.Timedelta(days=dias).to_pytimedelta() < e
          <= fim]
    flags = {bool(m["consolidado"]) for m in ms}
    if len(flags) > 1:
        return False, "base mista: componentes individuais e consolidados"
    return (flags.pop() if flags else True), None


def _juntar(*notas: str | None) -> str | None:
    vistas: list[str] = []
    for n in notas:
        if n and n not in vistas:
            vistas.append(n)
    return "; ".join(vistas) or None


def _fluxo(ent: str, item: str, g: pd.DataFrame,
           incompatibilidades: list[dict] | None = None) -> list[dict]:
    """Composição só entre fatos de mesma semântica, quando a fonte a identifica.

    Documentos antigos sem o campo preservam o caminho histórico. Quando aparece uma quebra
    comprovada de conceito, valores reportados ficam nas suas próprias séries e nenhuma
    diferença de acumulados, soma de quatro Q ou identidade anual+H1−H1 cruza a quebra.
    """
    if "semantica_fluxo" not in g:
        return _fluxo_compativel(ent, item, g)
    if g["semantica_fluxo"].map(_semantica).isna().all():
        return _fluxo_compativel(ent, item, g)  # metadado efetivamente ausente: legado
    # Reapresentação é escolhida antes da segregação: não ressuscita uma versão superada.
    atual = g.drop_duplicates(["period_start", "period_end"], keep="last").copy()
    semanticas = atual["semantica_fluxo"].map(_semantica).fillna("nao_informada")
    conhecidas = {"receita_dre", "resultado_liquido_seguros"}
    if semanticas.nunique() == 1 and semanticas.iloc[0] in conhecidas:
        return _fluxo_compativel(ent, item, atual, proveniencia=True)
    out = [r for conceito, grupo in atual.groupby(semanticas, sort=True)
           for r in _fluxo_compativel(ent, item, grupo, derivar=conceito in conhecidas, proveniencia=True)]
    # O consumidor também deriva TTM. O marcador precisa sobreviver no canônico ``nota``
    # de todos os componentes, inclusive a receita antiga, sem depender de attrs opcionais.
    for r in out:
        conceito = r.get("semantica_fluxo") or "nao_informada"
        marcador = f"semantica_fluxo={conceito}"
        if marcador not in (r.get("nota") or ""):
            r["nota"] = _juntar(r.get("nota"), marcador,
                                 f"rubrica reportada: {r.get('rubrica_reportada')}")
    chaves = {(r["freq"], r["period_end"]) for r in out}
    recusadas = [r for r in _fluxo_compativel(ent, item, atual)
                if r["freq"] in ("Q", "TTM") and (r["freq"], r["period_end"]) not in chaves]
    if not recusadas:
        return out
    conceitos = ", ".join(sorted(set(semanticas)))
    datas = ", ".join(sorted({pd.Timestamp(r["period_end"]).date().isoformat() for r in recusadas}))
    motivo = (f"comparabilidade: {item} Q/TTM não composto entre semânticas incompatíveis ou indeterminadas "
              f"({conceitos}); períodos recusados: {datas}; valores reportados preservados")
    if incompatibilidades is not None:
        incompatibilidades.append({"entidade": ent, "item": item, "motivo": motivo})
    # A última base homogênea continua com suas datas e fonte originais; a nota torna a
    # lacuna atual visível até para consumidores que não transportam attrs do DataFrame.
    ttms = [r for r in out if r["freq"] == "TTM"]
    fallback = max((r["period_end"] for r in ttms), default=None)
    for r in out:
        if r["freq"] == "TTM" and r["period_end"] == fallback:
            r["nota"] = _juntar(r.get("nota"), motivo,
                                 "fallback: última base de 12 meses homogênea; não representa o período recusado")
    return out


def _componentes_q(by_end: dict, e: date) -> list[tuple[date, date, float]]:
    """Períodos reais escolhidos pelo mesmo algoritmo de ``_quarter_value``."""
    flows = by_end.get(e, {})
    diretos = [s for s in flows if _QUARTER_DIAS[0] <= (e - s).days + 1 <= _QUARTER_DIAS[1]]
    if diretos:
        return [(min(diretos, key=lambda s: abs((e - s).days + 1 - 91)), e, 1.0)]
    for s in sorted(flows):
        if not _QUARTER_DIAS[1] < (e - s).days + 1 <= _ANUAL[1]:
            continue
        prev = _match_end(by_end, _months_back(e, 3))
        if prev is not None and s in by_end[prev] and math.isfinite(by_end[prev][s]):
            return [(s, e, 1.0), (s, prev, -1.0)]
    return []


def _componentes_ttm(by_end: dict, e: date, how: str) -> list[tuple[date, date, float]]:
    if how == "12m":
        anuais = [s for s in by_end[e] if _ANUAL[0] <= (e - s).days + 1 <= _ANUAL[1]]
        return [(min(anuais, key=lambda s: abs((e - s).days + 1 - 365)), e, 1.0)]
    if how != "4q":
        return []
    partes = []
    for k in range(4):
        fim = e if k == 0 else _match_end(by_end, _months_back(e, 3 * k))
        if fim is None or not (q := _componentes_q(by_end, fim)):
            return []
        partes.extend(q)
    return partes


def _meta_componentes(item: str, by_end: dict, metas: dict,
                      partes: list[tuple[date, date, float]]) -> dict:
    ms = [metas[(s, e)] for s, e, _ in partes]
    m0 = ms[0]
    bases = {m["consolidado"] for m in ms}
    nota_base = "base mista: componentes individuais e consolidados" if len(bases) > 1 else None
    componentes = [{"item": item, "period_start": s.isoformat(), "period_end": e.isoformat(),
                    "valor": by_end[e][s], "coeficiente": coef,
                    "currency": m["currency"], "consolidado": m["consolidado"],
                    "fonte": _fonte_componente(m)}
                   for (s, e, coef), m in zip(partes, ms, strict=True)]
    nota = ("componentes_fluxo=" + json.dumps(componentes, ensure_ascii=False)
            if len(partes) > 1 else None)
    return {**m0, **_observacao_componentes(ms), "data_publicacao": _publicacao_componentes(ms),
            "consolidado": all(m["consolidado"] for m in ms),
            "nota": _juntar(m0.get("nota"), nota_base, nota)}


def _fluxo_compativel(ent: str, item: str, g: pd.DataFrame, *, derivar: bool = True,
                      proveniencia: bool = False) -> list[dict]:
    if 'disponibilidade_tipo' in g and g['disponibilidade_tipo'].eq('recepcao_observada').any():
        proveniencia = True
    g = g.dropna(subset=["period_start", "period_end"])
    by_end: dict[date, dict[date, float]] = {}
    meta_end: dict[date, dict] = {}
    meta_anual: dict[date, dict] = {}
    meta_periodo: dict[tuple[date, date], dict] = {}
    for row in g.itertuples(index=False):
        s, e = row.period_start.date(), row.period_end.date()
        by_end.setdefault(e, {})[s] = float(row.value)
        meta_end[e] = _meta(row)  # ordenado por publicação ⇒ o último é o mais recente
        meta_periodo[(s, e)] = _meta(row)
        dur = (e - s).days + 1
        if _ANUAL[0] <= dur <= _ANUAL[1]:
            meta_anual[e] = _meta(row)
    out = []
    for e in sorted(by_end):
        flows = by_end[e]
        anual = [(abs((e - s).days + 1 - 365), v) for s, v in flows.items()
                 if _ANUAL[0] <= (e - s).days + 1 <= _ANUAL[1]]
        if anual:
            out.append({"entidade": ent, "item": item, "freq": "A",
                        "period_end": pd.Timestamp(e), "value": min(anual)[1],
                        **meta_anual.get(e, meta_end[e])})
        q = _quarter_value(by_end, e)
        direto = any(_QUARTER_DIAS[0] <= (e - s0).days + 1 <= _QUARTER_DIAS[1]
                     for s0 in flows)
        if math.isfinite(q) and (derivar or direto):
            cons, nota_base = _base_janela(meta_end, e, 1 if direto else 100)
            meta_q = {**meta_end[e], "consolidado": cons,
                      "nota": _juntar(meta_end[e].get("nota"), nota_base)}
            if proveniencia:
                meta_q = _meta_componentes(item, by_end, meta_periodo, _componentes_q(by_end, e))
            out.append({"entidade": ent, "item": item, "freq": "Q",
                        "period_end": pd.Timestamp(e), "value": q, **meta_q})
        t, how = _ttm_value(by_end, e)
        if not derivar and how != "12m":
            continue  # conceito indeterminado: preserva somente valores reportados
        componentes = None
        periodos_componentes = []
        if not math.isfinite(t):
            # Um semestre atual e o comparativo, com o exercício imediatamente anterior,
            # determinam 12 meses sem fornecer nenhum trimestre discreto. Exige períodos
            # exatamente alinhados e preserva as três origens na nota.
            for s, atual in flows.items():
                if not 170 <= (e - s).days + 1 <= 195:
                    continue
                s_prev = (pd.Timestamp(s) - pd.DateOffset(years=1)).date()
                e_prev = (pd.Timestamp(e) - pd.DateOffset(years=1)).date()
                fim_anual = (pd.Timestamp(s) - pd.Timedelta(days=1)).date()
                anual_prev = by_end.get(fim_anual, {}).get(s_prev)
                comparativo = by_end.get(e_prev, {}).get(s_prev)
                if anual_prev is None or comparativo is None or not \
                        _ANUAL[0] <= (fim_anual - s_prev).days + 1 <= _ANUAL[1]:
                    continue
                componentes = [meta_periodo[(s, e)], meta_periodo[(s_prev, fim_anual)],
                               meta_periodo[(s_prev, e_prev)]]
                if len({m["consolidado"] for m in componentes}) != 1:
                    componentes = None
                    continue  # base mista não representa nem consolidado nem individual
                t = atual + anual_prev - comparativo
                how = "semestre"
                periodos_componentes = [(s, e, 1.0), (s_prev, fim_anual, 1.0), (s_prev, e_prev, -1.0)]
                break
        if math.isfinite(t):
            meta_ttm = meta_end[e]
            if componentes:
                cons = all(m["consolidado"] for m in componentes)
                origens = " + ".join(f"{m['documento']} (sha256 {m['sha256']}; {m['url']})"
                                     for m in componentes)
                nota_base = "TTM semestral = semestre atual + anual anterior − semestre " \
                            "comparativo; componentes: " + origens
                meta_ttm = {**meta_ttm, "data_publicacao":
                            _publicacao_componentes(componentes)}
            else:
                cons, nota_base = _base_janela(meta_end, e, 1 if how == "12m" else 370)
            meta_ttm = {**meta_ttm, "consolidado": cons,
                        "nota": _juntar(meta_ttm.get("nota"), nota_base)}
            if proveniencia:
                partes = periodos_componentes or _componentes_ttm(by_end, e, how)
                meta_ttm = _meta_componentes(item, by_end, meta_periodo, partes)
            out.append({"entidade": ent, "item": item, "freq": "TTM",
                        "period_end": pd.Timestamp(e), "value": t, **meta_ttm})
    return out


def _saldo(ent: str, item: str, g: pd.DataFrame, datas: set | None,
           anuais_ent: set | None) -> list[dict]:
    """Saldos por data-base. ``datas``/``anuais_ent`` (CVM/SEC): só datas com fluxo do emissor
    viram período ``Q`` e só fins de exercício viram ``A``; ``None`` (Yahoo, colunas já são
    datas de período): ``A`` quando a coluna é anual."""
    out = []
    for e, ge in g.groupby("period_end", sort=True):
        d = pd.Timestamp(e).date()
        if datas is not None and d not in datas:
            continue
        row = list(ge.itertuples(index=False))[-1]
        base = {"entidade": ent, "item": item, "period_end": pd.Timestamp(e),
                "value": float(row.value), **_meta(row)}
        out.append({**base, "freq": "Q"})
        anuais = ge[ge["anual"].astype(bool)]
        if anuais_ent is not None:
            if d not in anuais_ent:
                continue
            ra = list((anuais if not anuais.empty else ge).itertuples(index=False))[-1]
        elif anuais.empty:
            continue
        else:
            ra = list(anuais.itertuples(index=False))[-1]
        out.append({"entidade": ent, "item": item, "period_end": pd.Timestamp(e),
                    "value": float(ra.value), **_meta(ra), "freq": "A"})
    return out


def derivados(df: pd.DataFrame) -> pd.DataFrame:
    """Itens calculados (``ebit`` na falta, ``ebitda``, ``fcf``, ``divida_liquida``) por
    (entidade, freq, period_end) — usado de novo depois do complemento e da conferência."""
    return _derivados(df)


def _derivados(df: pd.DataFrame) -> pd.DataFrame:
    """``ebitda``, ``fcf`` e ``divida_liquida`` por (entidade, freq, period_end)."""
    k = ["entidade", "freq", "period_end"]
    w = df.pivot_table(index=k, columns="item", values="value", aggfunc="first")
    meta_cols = ["demonstrativo", "currency", "consolidado", "fonte", "url", "documento",
                 "data_publicacao", "sha256", "pit_estimado", "nota"]
    meta_cols += [k for k in METADADOS_OBSERVADOS if k in df]
    if "nota" not in df.columns:
        df = df.assign(nota=None)
    meta = df.set_index(k + ["item"])[meta_cols]
    meta = meta[~meta.index.duplicated(keep="last")]
    out = []

    def add(nome: str, comp: list[str], valor: pd.Series, demonstrativo: str, nota: str,
            opcionais: tuple[str, ...] = ()) -> None:
        for idx, v in valor.dropna().items():
            if not math.isfinite(float(v)):
                continue
            ms = [meta.loc[(*idx, c)] for c in comp if (*idx, c) in meta.index]
            ms += [meta.loc[(*idx, c)] for c in opcionais if (*idx, c) in meta.index
                   and pd.notna(w.loc[idx, c] if c in w.columns else np.nan)]
            if not ms:
                continue
            # EBIT reportado usa EBIT+D&A; a identidade alternativa só participa na sua falta.
            if nome == 'ebitda' and any(_observado(m) for m in ms):
                reportado = pd.notna(w.loc[idx, 'ebit'] if 'ebit' in w else np.nan)
                usados = ('ebit', 'd_a') if reportado else ('lucro_antes_ir', 'resultado_financeiro', 'd_a')
                ms = [meta.loc[(*idx, c)] for c in usados if (*idx, c) in meta.index]
            pub = _publicacao_componentes(ms)
            m0 = ms[0]
            notas = [_texto(m["nota"]) for m in ms]
            notas = [n for n in notas if n and not n.startswith("calculado")]
            out.append({"entidade": idx[0], "freq": idx[1], "period_end": idx[2], "item": nome,
                        "value": float(v), "demonstrativo": demonstrativo,
                        "currency": m0["currency"],
                        "consolidado": all(bool(m["consolidado"]) for m in ms),
                        "fonte": m0["fonte"], "url": m0["url"],
                        "documento": m0["documento"], "data_publicacao": pub,
                        "sha256": m0["sha256"],
                        "pit_estimado": any(bool(m["pit_estimado"]) for m in ms),
                        "nota": _juntar(nota, *notas), **_observacao_componentes(ms)})

    def col(c: str) -> pd.Series:
        return w[c] if c in w.columns else pd.Series(np.nan, index=w.index)

    sem_ebit = col("ebit").isna()
    add("ebit", ["lucro_antes_ir", "resultado_financeiro"],
        (col("lucro_antes_ir") - col("resultado_financeiro")).where(sem_ebit), "DRE",
        "calculado: lucro_antes_ir − resultado_financeiro (inclui equivalência patrimonial)")
    ebit_tot = col("ebit").where(~sem_ebit, col("lucro_antes_ir") - col("resultado_financeiro"))
    add("ebitda", ["ebit", "d_a", "lucro_antes_ir", "resultado_financeiro"],
        (ebit_tot + col("d_a")).where(col("ebitda").isna()), "DRE", "calculado: ebit + d_a")
    add("fcf", ["cfo", "capex"], (col("cfo") - col("capex")).where(col("fcf").isna()), "DFC",
        "calculado: cfo − capex")
    liq_com_aplic = col("divida_bruta") - col("caixa") - col("aplicacoes_cp")
    liq_so_caixa = (col("divida_bruta") - col("caixa")).where(col("aplicacoes_cp").isna())
    add("divida_liquida", ["divida_bruta", "caixa", "aplicacoes_cp"], liq_com_aplic, "BP",
        "calculado: divida_bruta − caixa − aplicacoes_cp")
    add("divida_liquida", ["divida_bruta", "caixa"], liq_so_caixa, "BP",
        "calculado: divida_bruta − caixa (aplicações de curto prazo não informadas)")
    return pd.DataFrame(out)


__all__ = ["FLUXOS", "SAIDA_COLUNAS", "derivados", "selecionar_pit"]
