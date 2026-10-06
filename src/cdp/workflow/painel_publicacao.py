"""Perfil ``publicacao`` do painel do CDP: o retrato publicado no artifact (``data.json``).

Quem publica o artifact precisa ler TODO o arquivo publicado antes (leitura em partes de até 2.000
linhas; linhas acima de 2.000 caracteres são cortadas na leitura). O perfil ``completo``
(:func:`cdp.workflow.painel.painel_data`) passa de 1,7 MB numa linha só; este módulo deriva dele,
em código puro e determinístico, um JSON compacto que cabe nesse orçamento:

- JSON indentado com chaves ordenadas (:func:`dump_publicacao`: objeto ou lista pequenos numa
  linha só e listas de escalares agrupadas em linhas de até :data:`WRAP_CHARS` caracteres), com no
  máximo :data:`DATA_MAX_BYTES` bytes e nenhuma linha acima de :data:`DATA_MAX_LINE` caracteres;
- investimento, não TI: o perfil publicado não traz hashes/SHA-256, marcas de verificação contra
  a trilha, eventos da trilha, alertas da verificação de integridade, agenda das rotinas, nomes
  da mente (a oração inteira sai dos textos), linhas de proveniência, o rótulo "Caminho:" do
  racional, ledger de chamadas de IA, tentativas/fallbacks, caminhos de arquivos nem
  apontamentos de leitura (tudo fica no livro e na cópia local completa); ficam os campos de protocolo de ``meta`` (versão, perfil,
  ``data_hash``, ``page_sha256``, ``publication``, ``truncations``, ``config_hash``...);
- números nunca são alterados nem arredondados: itens inteiros saem ou ficam; agregados novos
  (meses consolidados do track record) são calculados aqui, em código; ausente continua ``null``;
- textos longos são cortados com "…" e o objeto que os contém ganha ``"_truncado": true``; tudo o
  que foi cortado ou omitido fica em ``meta.truncations`` (campo, regra, quantidade);
- três formas SEM perda reduzem o tamanho e o comprimento das linhas — a página e
  :func:`expandir` as desfazem antes de usar os dados:
  ``{"_colunas": {...}, "_n": N}`` (tabela em colunas; ``"a.b"`` = campo ``b`` do objeto ``a``;
  ``_faltam`` lista as linhas em que a coluna não existe), ``{"_rep": {"v": [...], "n": [...]}}``
  (coluna de escalares em corridas: ``v[k]`` repetido ``n[k]`` vezes), ``{"_partes": [...]}``
  (texto longo em partes concatenadas sem separador) e ``{"_igual": "<chave irmã>", ...}`` (o
  mesmo conteúdo da chave irmã, com os campos dados — ex.: o período do mês igual ao desde o
  início no primeiro mês);
- se o retrato não couber, :data:`NIVEIS` aplica cortes progressivos (menos semanas completas,
  menos pregões em linhas diárias, menos comentários...) até caber; o nível usado fica em
  ``meta.publication.nivel``. A tese da carteira da semana vigente é o conteúdo mais valioso:
  só os níveis finais encurtam (nível 5) e depois omitem (nível 7) os textos por nome.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any

from ..contracts import HARNESS_MINDS

PROFILES = ("publicacao", "completo")
#: Orçamento do ``data.json`` publicado (bytes UTF-8 e caracteres por linha).
DATA_MAX_BYTES = 260_000
DATA_MAX_LINE = 1_500
#: Leiaute do ``data.json``: objeto/lista cujo JSON compacto cabe em ``INLINE_CHARS`` fica numa
#: linha só; listas de escalares maiores vão em linhas de até ``WRAP_CHARS`` caracteres.
INLINE_CHARS = 300
WRAP_CHARS = 1_000
#: Orçamento do ``index.html`` (só é relido/publicado quando o template muda).
PAGE_MAX_BYTES = 260_000
PAGE_MAX_LINE = 2_000
#: Texto (já escapado em JSON) acima disto vira ``{"_partes": [...]}`` com partes deste tamanho.
SPLIT_AT = 1_200
PART_CHARS = 1_000
MIN_COLUMNAR_ROWS = 3
ELLIPSIS = "…"
TRUNC_FLAG = "_truncado"
_DATED_NOTE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_CHOSEN_RE = re.compile(r"[Vv]ariante\s+\**([A-Za-z0-9_-]+)\**\s+(?:foi\s+)?escolhida")
_DATE_IN_PATH_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class Limites:
    """Limites de um nível de compactação (sempre em itens ou caracteres de texto; números nunca
    são alterados). O nível 0 segue as regras do artifact; os seguintes cortam mais."""

    semanas_completas: int = 2
    #: A semana completa anterior à mais recente traz o detalhe da proposta (todas as colunas das
    #: posições, gates aprovados, risco ex-ante, notas do otimizador) e a pesquisa resumida
    #: (macro, tabela de notas, visões); sem ele, posições enxutas, só os gates reprovados e a
    #: postura macro (os textos da decisão do PM continuam).
    semana_anterior_detalhe: bool = True
    semanas_resumo: int = 26
    pregoes: int = 90
    comentarios: int = 10
    comentario_chars: int = 4_000
    #: Pesquisa (notas por emissor e notas macro): já no nível 0 abre espaço para a tese da
    #: carteira, que traz a leitura da gestão para cada nome e o contexto de mercado.
    notas_completas: bool = True
    tese_chars: int = 450
    itens_nota: int = 3
    urls_nota: int = 2
    resumo_macro_chars: int = 800
    itens_macro: int = 3
    item_macro_chars: int = 150
    texto_curto: int = 200
    #: Racional das visões agregadas da pesquisa (0 = omitido) e visões de emissores fora da
    #: carteira da semana.
    visao_chars: int = 200
    visoes_fora_carteira: bool = False
    #: Texto ``details`` dos gates de compliance APROVADOS (os reprovados sempre trazem o texto).
    detalhes_aprovadas: bool = True
    notas_backtest: int = 8
    nota_backtest_chars: int = 300
    #: Execuções de backtest publicadas além da escolhida (as mais recentes, pela ordem do id) e
    #: notas de calibração (as mais recentes): as demais só entram na contagem.
    backtests_execucoes: int = 6
    backtests_documentos: int = 12
    posicoes_sombra: int = 20
    notas_otimizador: int = 8
    #: Hedge cambial sugerido (NDFs) da semana mais recente.
    hedge_cambial: bool = True
    execucoes_risco: int = 10
    atribuicao_extremos: int = 8
    noticias: int = 20
    indice_relatorios: int | None = None
    posicoes_detalhe: bool = True
    #: Textos da mente na decisão (leitura do PM, visões, exclusões, diários): ``None`` = íntegros.
    texto_pm_chars: int | None = None
    #: Períodos da atribuição publicados (``None`` = todos).
    periodos: tuple[str, ...] | None = None
    #: Monitor de risco: Markdown da última execução e posições do intradiário.
    monitor_markdown: bool = True
    monitor_posicoes: bool = True
    #: Últimos recursos: tabela de notas, visões agregadas da pesquisa, verificações de
    #: compliance não triviais (aprovadas perto do limite e informativas; sem elas, só as
    #: reprovadas) e o diário da decisão.
    tabela_notas: bool = True
    visoes_pesquisa: bool = True
    compliance_relevantes: bool = True
    diario_decisao: bool = True
    #: Tese da carteira da semana vigente (o conteúdo mais valioso; só os níveis finais cortam):
    #: textos por nome (por que, risco, gatilho) — ``None`` = íntegros, ``0`` = omitidos (ficam
    #: os números) — e textos das seções e dos temas (``None`` = íntegros).
    tese_carteira_nome_chars: int | None = None
    tese_carteira_secao_chars: int | None = None


def _nivel(base: Limites, **changes: Any) -> Limites:
    return replace(base, **changes)


#: Mínimo do histórico diário mantido até o nível 6 (pregões em linhas e comentários do dia).
PREGOES_MINIMOS = 60
COMENTARIOS_MINIMOS = 5


# Ordem dos cortes: primeiro o que a página quase não mostra ou o que se repete (detalhe dos
# gates aprovados, racionais das visões agregadas, detalhe da semana anterior, execuções antigas
# de backtest), depois os textos longos da pesquisa e as tabelas de apoio, a
# partir do nível 5 os textos da tese da carteira e, só nos últimos níveis, o histórico diário: até
# o nível 6 ficam ao menos ``PREGOES_MINIMOS`` pregões em linhas diárias e
# ``COMENTARIOS_MINIMOS`` comentários do dia.
_N1 = _nivel(Limites(), detalhes_aprovadas=False, visao_chars=0,
             semana_anterior_detalhe=False, notas_otimizador=4, noticias=10)
_N2 = _nivel(_N1, semanas_completas=1, resumo_macro_chars=600,
             item_macro_chars=140, tese_chars=400, itens_nota=2, urls_nota=1,
             texto_curto=160, semanas_resumo=12, indice_relatorios=120, backtests_execucoes=3,
             backtests_documentos=6, notas_backtest=4, atribuicao_extremos=6,
             execucoes_risco=5, periodos=("itd", "mtd", "semana", "dia"))
_N3 = _nivel(_N2, notas_completas=False, visoes_pesquisa=False, resumo_macro_chars=300,
             itens_macro=0, hedge_cambial=False, compliance_relevantes=False,
             posicoes_detalhe=False, texto_pm_chars=800, periodos=("itd", "semana", "dia"),
             atribuicao_extremos=5, pregoes=75, comentarios=7, semanas_resumo=8,
             indice_relatorios=90, monitor_markdown=False, posicoes_sombra=10,
             backtests_execucoes=2)
_N4 = _nivel(_N3, tabela_notas=False, diario_decisao=False, texto_pm_chars=500, comentarios=6,
             comentario_chars=3_500, pregoes=66, periodos=("itd", "dia"), semanas_resumo=6,
             indice_relatorios=60, backtests_execucoes=1, backtests_documentos=3,
             monitor_posicoes=False, notas_otimizador=2)
# A partir do nível 5, depois dos textos da pesquisa e do PM, a tese da carteira encurta.
_N5 = _nivel(_N4, texto_pm_chars=300, comentarios=COMENTARIOS_MINIMOS, comentario_chars=3_000,
             pregoes=PREGOES_MINIMOS, semanas_resumo=4, indice_relatorios=40, posicoes_sombra=5,
             execucoes_risco=3, resumo_macro_chars=150, tese_carteira_nome_chars=200)
_N6 = _nivel(_N5, texto_pm_chars=200, comentario_chars=2_000, semanas_resumo=2,
             indice_relatorios=20, execucoes_risco=2, backtests_execucoes=0,
             backtests_documentos=1, notas_backtest=2, atribuicao_extremos=4, urls_nota=0,
             tese_carteira_nome_chars=140)
# Emergência (só se nada acima couber): menos histórico diário e menos comentários; a tese
# perde os textos por nome (ficam os números) e as seções encurtam.
_N7 = _nivel(_N6, pregoes=40, comentarios=3, comentario_chars=1_500, texto_pm_chars=150,
             indice_relatorios=10, tese_carteira_nome_chars=0, tese_carteira_secao_chars=1_200)
_N8 = _nivel(_N7, pregoes=21, comentarios=2, comentario_chars=1_000, semanas_resumo=0,
             indice_relatorios=0, execucoes_risco=1, noticias=0, atribuicao_extremos=3,
             posicoes_sombra=0, tese_carteira_secao_chars=700)

#: Níveis progressivos, do mais fiel ao mais compacto: o primeiro que cabe no orçamento é o
#: publicado (``meta.publication.nivel``); os cortes de cada um ficam em ``meta.truncations``.
NIVEIS: tuple[Limites, ...] = (Limites(), _N1, _N2, _N3, _N4, _N5, _N6, _N7, _N8)


# ==========================================================
# Serialização e medidas
# ==========================================================

def _compacto(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _leiaute(x: Any, depth: int) -> str:
    """JSON de ``x`` indentado (1 espaço por nível): objeto ou lista cujo JSON compacto cabe em
    :data:`INLINE_CHARS` vai numa linha só; lista de escalares maior, em linhas de até
    :data:`WRAP_CHARS` caracteres (um escalar mais longo fica sozinho na linha)."""
    if not isinstance(x, (dict, list)) or not x:
        return _compacto(x)
    flat = _compacto(x)
    if len(flat) <= INLINE_CHARS:
        return flat
    pad, end = " " * (depth + 1), " " * depth
    if isinstance(x, list):
        if not any(isinstance(v, (dict, list)) for v in x):
            lines: list[str] = []
            cur = ""
            for v in x:
                s = _compacto(v)
                if cur and len(cur) + 1 + len(s) > WRAP_CHARS:
                    lines.append(cur + ",")
                    cur = s
                else:
                    cur = f"{cur},{s}" if cur else s
            lines.append(cur)
            return "[\n" + "\n".join(pad + ln for ln in lines) + "\n" + end + "]"
        return ("[\n" + ",\n".join(pad + _leiaute(v, depth + 1) for v in x) + "\n" + end
                + "]")
    items = [f"{pad}{_compacto(str(k))}: {_leiaute(x[k], depth + 1)}" for k in sorted(x)]
    return "{\n" + ",\n".join(items) + "\n" + end + "}"


def dump_publicacao(data: Any) -> str:
    """O texto exato do ``data.json`` publicado: JSON indentado, chaves ordenadas, UTF-8, sem
    NaN; objetos e listas pequenos numa linha e listas de escalares agrupadas (:func:`_leiaute`).
    """
    return _leiaute(data, 0) + "\n"


def max_line(text: str) -> int:
    """Maior linha (em caracteres) de um texto."""
    return max((len(x) for x in text.splitlines()), default=0)


def cabe(text: str, max_bytes: int = DATA_MAX_BYTES, max_len: int = DATA_MAX_LINE) -> bool:
    return len(text.encode("utf-8")) <= max_bytes and max_line(text) <= max_len


# ==========================================================
# Formas sem perda: colunas e partes
# ==========================================================

def _flat(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Uma linha achatada em um nível (``{"a": {"b": 1}}`` → ``{"a.b": 1}``); ``None`` se alguma
    chave tiver ponto (a coluna ficaria ambígua)."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if "." in k:
            return None
        if (isinstance(v, dict) and v and not ({"_colunas", "_partes", "_rep"} & set(v))
                and all("." not in kk for kk in v)):
            for kk, vv in v.items():
                out[f"{k}.{kk}"] = vv
        else:
            out[k] = v
    return out


def _runs(values: Sequence[Any]) -> dict[str, Any] | None:
    """Coluna de escalares em corridas: ``{"_rep": {"v": [...], "n": [...]}}`` = ``v[k]``
    repetido ``n[k]`` vezes (sem perda; ``None`` se a coluna tiver objetos ou listas)."""
    if not values or not all(v is None or isinstance(v, (str, int, float, bool)) for v in values):
        return None
    vs: list[Any] = []
    ns: list[int] = []
    last = None
    for v in values:
        key = json.dumps(v, ensure_ascii=False)  # distingue 1, 1.0, True e -0.0
        if vs and key == last:
            ns[-1] += 1
        else:
            vs.append(v)
            ns.append(1)
            last = key
    return {"_rep": {"v": vs, "n": ns}}


def _unruns(values: Any) -> list[Any]:
    if isinstance(values, dict) and isinstance(values.get("_rep"), dict):
        rep = values["_rep"]
        return [v for v, n in zip(rep.get("v") or [], rep.get("n") or [], strict=True)
                for _ in range(n)]
    return list(values or [])


def _columnar(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    flats = [_flat(r) for r in rows]
    if any(f is None for f in flats):
        return None
    cols = sorted(set().union(*flats))  # type: ignore[arg-type]
    columns: dict[str, Any] = {}
    for c in cols:
        values = [f.get(c) for f in flats]  # type: ignore[union-attr]
        runs = _runs(values)
        columns[c] = runs if runs is not None and _size(runs) < _size(values) else values
    out: dict[str, Any] = {"_colunas": columns, "_n": len(rows)}
    faltam = {c: idx for c in cols
              if (idx := [i for i, f in enumerate(flats) if c not in f])}  # type: ignore[operator]
    if faltam:
        out["_faltam"] = faltam
    return out


def _size(x: Any) -> int:
    return len(json.dumps(x, ensure_ascii=False, sort_keys=True, indent=1))


def _pack(x: Any) -> Any:
    """Listas de objetos viram colunas quando isso encurta o JSON (de baixo para cima)."""
    if isinstance(x, dict):
        return {k: _pack(v) for k, v in x.items()}
    if isinstance(x, list):
        items = [_pack(v) for v in x]
        if len(items) >= MIN_COLUMNAR_ROWS and all(isinstance(v, dict) for v in items):
            col = _columnar(items)
            if col is not None and _size(col) < _size(items):
                return col
        return items
    return x


def _esc_len(s: str) -> int:
    return len(json.dumps(s, ensure_ascii=False)) - 2


def _hard_split(text: str, limit: int) -> list[str]:
    out, cur, n = [], [], 0
    for ch in text:
        cl = _esc_len(ch)
        if cur and n + cl > limit:
            out.append("".join(cur))
            cur, n = [], 0
        cur.append(ch)
        n += cl
    if cur:
        out.append("".join(cur))
    return out


def partes(text: str, limit: int = PART_CHARS) -> list[str]:
    """Texto em partes (quebras de linha preferidas) cujo JSON escapado tem até ``limit``
    caracteres; ``"".join(partes(t)) == t``."""
    out: list[str] = []
    cur, n = "", 0
    for piece in re.split(r"(?<=\n)", text):
        if not piece:
            continue
        pl = _esc_len(piece)
        if pl > limit:
            if cur:
                out.append(cur)
                cur, n = "", 0
            out.extend(_hard_split(piece, limit))
            continue
        if cur and n + pl > limit:
            out.append(cur)
            cur, n = "", 0
        cur += piece
        n += pl
    if cur:
        out.append(cur)
    return out


def _split(x: Any) -> Any:
    if isinstance(x, str):
        return {"_partes": partes(x)} if _esc_len(x) > SPLIT_AT else x
    if isinstance(x, dict):
        return {k: _split(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_split(v) for v in x]
    return x


def expandir(x: Any) -> Any:
    """Desfaz as formas sem perda (``_colunas``/``_rep``/``_partes``/``_igual``): o mesmo que a
    página faz ao carregar."""
    if isinstance(x, list):
        return [expandir(v) for v in x]
    if not isinstance(x, dict):
        return x
    if isinstance(x.get("_partes"), list) and set(x) == {"_partes"}:
        return "".join(x["_partes"])
    if isinstance(x.get("_colunas"), dict) and isinstance(x.get("_n"), int):
        n, faltam = x["_n"], x.get("_faltam") or {}
        rows: list[dict[str, Any]] = [{} for _ in range(n)]
        for col, packed in x["_colunas"].items():
            values = _unruns(packed)
            skip = set(faltam.get(col) or [])
            a, _, b = col.partition(".")
            for i in range(n):
                if i in skip:
                    continue
                v = expandir(values[i])
                if b:
                    if not isinstance(rows[i].get(a), dict):
                        rows[i][a] = {}
                    rows[i][a][b] = v
                else:
                    rows[i][a] = v
        return rows
    out = {k: expandir(v) for k, v in x.items()}
    for k, v in out.items():  # {"_igual": "<chave irmã>", ...}: o irmão com estes campos
        ref = v.get("_igual") if isinstance(v, dict) else None
        if isinstance(ref, str) and isinstance(out.get(ref), dict) and "_igual" not in out[ref]:
            out[k] = {**out[ref], **{kk: vv for kk, vv in v.items() if kk != "_igual"}}
    return out


# ==========================================================
# Cortes (sempre registrados)
# ==========================================================

class _Cortes:
    def __init__(self) -> None:
        self._n: dict[tuple[str, str], int] = {}

    def add(self, campo: str, regra: str, n: int = 1) -> None:
        if n > 0:
            key = (campo, regra)
            self._n[key] = self._n.get(key, 0) + n

    def lista(self) -> list[dict[str, Any]]:
        return [{"campo": c, "regra": r, "n": n} for (c, r), n in sorted(self._n.items())]


def _cut_text(text: Any, limit: int) -> tuple[Any, bool]:
    if not isinstance(text, str) or len(text) <= limit:
        return text, False
    return text[: max(limit - 1, 0)].rstrip() + ELLIPSIS, True


def _cut_field(obj: Any, key: str, limit: int, cortes: _Cortes, campo: str) -> None:
    if not isinstance(obj, dict):
        return
    v, cut = _cut_text(obj.get(key), limit)
    if cut:
        obj[key] = v
        obj[TRUNC_FLAG] = True
        cortes.add(f"{campo}.{key}", f"texto ≤ {limit} caracteres")


def _cut_list(obj: Any, key: str, n: int, cortes: _Cortes, campo: str, *,
              item_chars: int | None = None, item_key: str | None = None) -> None:
    """Lista ≤ ``n`` itens; itens de texto (ou ``item[item_key]``) ≤ ``item_chars``."""
    if not isinstance(obj, dict) or not isinstance(obj.get(key), list):
        return
    items = obj[key]
    if len(items) > n:
        cortes.add(f"{campo}.{key}", f"lista ≤ {n} itens", len(items) - n)
        items = items[:n]
        obj[TRUNC_FLAG] = True
    if item_chars is not None:
        out, hits = [], 0
        for it in items:
            if item_key is None:
                t, cut = _cut_text(it, item_chars)
            elif isinstance(it, dict):
                it = dict(it)
                t0, cut = _cut_text(it.get(item_key), item_chars)
                if cut:
                    it[item_key] = t0
                    it[TRUNC_FLAG] = True
                t = it
            else:
                t, cut = it, False
            hits += cut
            out.append(t)
        if hits:
            obj[TRUNC_FLAG] = True
            cortes.add(f"{campo}.{key}[]" + (f".{item_key}" if item_key else ""),
                       f"texto ≤ {item_chars} caracteres", hits)
        items = out
    obj[key] = items


def _drop(obj: Any, key: str, cortes: _Cortes, campo: str,
          regra: str = "omitido na publicação") -> None:
    if not isinstance(obj, dict) or key not in obj:
        return
    if obj[key] not in (None, [], {}, ""):
        cortes.add(f"{campo}.{key}", regra)
    obj.pop(key)


def _pick(obj: Mapping[str, Any] | None, keys: Iterable[str]) -> dict[str, Any]:
    src = obj or {}
    return {k: src[k] for k in keys if k in src}


# ==========================================================
# Track record e dia mais recente
# ==========================================================

#: Colunas das linhas diárias publicadas (as que os gráficos e tabelas da página usam).
TRACK_ROW_KEYS = ("date", "nav_end", "pnl", "ret", "pnl_components", "n_alerts", "live_book_week")
TRACK_RISK_KEYS = ("ex_ante_vol", "realized_vol_21d", "drawdown")


def _num(x: Any) -> float | None:
    from .painel import _num as num

    return num(x)


def _compound(values: Iterable[Any]) -> float | None:
    from .painel import _compound as comp

    return comp(values)


def _rollup(older: Sequence[Mapping[str, Any]], compare: Sequence[Mapping[str, Any]]
            ) -> list[dict[str, Any]]:
    """Pregões antigos agregados por mês (em código): NAV no fim do mês, retorno composto do mês,
    média da vol ex-ante dos dias com valor, drawdown no fim do mês e a comparação com a sombra
    no último dia do mês. Dia sem retorno ⇒ retorno do mês ``None`` (nunca zero)."""
    months: dict[str, list[Mapping[str, Any]]] = {}
    for r in older:
        months.setdefault(str(r.get("date"))[:7], []).append(r)
    cmp_by_date = {str(c.get("date")): c for c in compare}
    out = []
    for month in sorted(months):
        rs = months[month]
        last = rs[-1]
        vols = [v for r in rs if (v := _num((r.get("risk") or {}).get("ex_ante_vol"))) is not None]
        pnls = [_num(r.get("pnl")) for r in rs]
        c = next((cmp_by_date[str(r.get("date"))] for r in reversed(rs)
                  if str(r.get("date")) in cmp_by_date), None)
        out.append({
            "month": month, "first_date": rs[0].get("date"), "date": last.get("date"),
            "n_days": len(rs), "nav_start": rs[0].get("nav_start"), "nav_end": last.get("nav_end"),
            "ret": _compound(r.get("ret") for r in rs),
            "pnl": sum(p for p in pnls if p is not None) if all(p is not None for p in pnls)
            else None,
            "ex_ante_vol_avg": sum(vols) / len(vols) if vols else None, "n_vol": len(vols),
            "drawdown": (last.get("risk") or {}).get("drawdown"),
            "nav_shadow": c.get("nav_shadow") if c else None,
            "cum_value_added": c.get("cum_value_added") if c else None,
        })
    return out


def _trim_attribution(attr: Any, lim: Limites, cortes: _Cortes, campo: str,
                      keep_names: set[str] | None = None) -> Any:
    """Por emissor e por fator: os ``n`` maiores e os ``n`` menores (a página só mostra esses),
    mais ``keep_names`` (emissores da carteira vigente, no período desde o início)."""
    if not isinstance(attr, dict):
        return attr
    n = lim.atribuicao_extremos
    out = dict(attr)
    for g in ("issuer", "factor"):
        rows = out.get(g)
        if not isinstance(rows, list) or len(rows) <= 2 * n:
            continue
        keep = set(range(n)) | set(range(len(rows) - n, len(rows)))
        if keep_names and g == "issuer":
            keep |= {i for i, r in enumerate(rows) if r.get("name") in keep_names}
        out[g] = [r for i, r in enumerate(rows) if i in keep]
        cortes.add(f"{campo}.{g}", f"só os {n} maiores e os {n} menores"
                   + (" e os emissores da carteira vigente" if keep_names and g == "issuer"
                      else ""), len(rows) - len(out[g]))
    return out


def _track(tr: Mapping[str, Any], lim: Limites, cortes: _Cortes, book: set[str]
           ) -> dict[str, Any]:
    out = dict(tr)
    recs = list(tr.get("records") or [])
    n = max(lim.pregoes, 0)
    kept, older = (recs[-n:], recs[:-n]) if n else ([], recs)
    rows, dropped = [], set()
    for r in kept:
        row = _pick(r, TRACK_ROW_KEYS)
        row["risk"] = _pick(r.get("risk"), TRACK_RISK_KEYS)
        dropped |= set(r) - set(TRACK_ROW_KEYS) - {"risk"}
        dropped |= {f"risk.{k}" for k in (r.get("risk") or {}) if k not in TRACK_RISK_KEYS}
        rows.append(row)
    # Campos de TI (hashes do encadeamento) saem sem ser nomeados: a publicação não os cita.
    shown = sorted(k for k in dropped if not _IT_KEY_RE.search(k.rsplit(".", 1)[-1]))
    if dropped:
        cortes.add("track_record.records[]",
                   "campos omitidos: " + ", ".join(shown) if shown else "campos de TI omitidos",
                   len(kept))
    out["records"] = rows
    kept_dates = {str(r.get("date")) for r in kept}
    cmp = list(tr.get("compare") or [])
    out["compare"] = [c for c in cmp if str(c.get("date")) in kept_dates]
    out["rollup"] = _rollup(older, [c for c in cmp if str(c.get("date")) not in kept_dates])
    if older:
        cortes.add("track_record.records", f"pregões além dos {n} mais recentes agregados por "
                   "mês em track_record.rollup", len(older))
    out["rows_limit"] = n
    shadow = dict(tr.get("shadow") or {})
    if shadow.get("records"):
        cortes.add("track_record.shadow.records",
                   "omitido (a comparação diária está em track_record.compare)",
                   len(shadow["records"]))
    shadow.pop("records", None)
    out["shadow"] = shadow
    periods: dict[str, Any] = {}
    seen: dict[str, str] = {}
    for key, p in (tr.get("periods") or {}).items():
        if lim.periodos is not None and key not in lim.periodos:
            if p:
                cortes.add(f"track_record.periods.{key}", "omitido (períodos publicados: "
                           + ", ".join(lim.periodos) + ")")
            continue
        if isinstance(p, dict):
            # Período idêntico a um anterior (ex.: mês = desde o início no 1º mês do fundo):
            # forma sem perda {"_igual": "<período>", "label": ...}.
            sig = json.dumps({k: v for k, v in p.items() if k != "label"}, sort_keys=True,
                             ensure_ascii=False, default=str)
            if sig in seen:
                periods[key] = {"_igual": seen[sig], "label": p.get("label")}
                continue
            seen[sig] = key
            p = dict(p)
            p["attribution"] = _trim_attribution(p.get("attribution"), lim, cortes,
                                                 f"track_record.periods.{key}.attribution",
                                                 book if key == "itd" else None)
        periods[key] = p
    out["periods"] = periods
    return out


def _latest(ld: Mapping[str, Any] | None, lim: Limites, cortes: _Cortes) -> Any:
    if not isinstance(ld, dict):
        return ld
    out = dict(ld)
    out["attribution"] = _trim_attribution(ld.get("attribution"), lim, cortes,
                                           "latest_day.attribution")
    risk = dict(ld.get("risk") or {})
    _drop(risk, "exposures", cortes, "latest_day.risk",
          "omitido (idêntico a risk.daily.exposures)")
    out["risk"] = risk
    _drop(out, "shadow", cortes, "latest_day",
          "omitido (a comparação diária está em track_record.compare)")
    if not lim.posicoes_detalhe and out.get("positions"):
        out["positions"] = [{k: v for k, v in p.items() if k not in LD_DETAIL_ONLY}
                            for p in out["positions"]]
        cortes.add("latest_day.positions[]", "campos de detalhe omitidos: "
                   + ", ".join(LD_DETAIL_ONLY), len(out["positions"]))
    return out


#: Campos das posições do dia que só aparecem no detalhe expandido da linha.
LD_DETAIL_ONLY = ("adtv_usd", "currency", "line_type", "price_local", "price_usd", "repriced",
                  "shares")
#: Colunas das posições-alvo que a página não exibe (recalculadas ou só de auditoria).
UNUSED_POSITION_KEYS = ("days_to_liquidate_recorded", "liq_participation")
#: Colunas das posições-alvo usadas fora da semana-fonte da tabela de posições.
SLIM_POSITION_KEYS = ("issuer_id", "name", "execution_ticker", "side", "weight", "country",
                      "sector", "alpha_annual", "risk_contribution")


# ==========================================================
# Semanas
# ==========================================================

#: Semana resumida: decisão, postura, caminho, nº de longs/shorts, vol, gross, net e beta.
SUMMARY_WEEK_KEYS = ("week", "stage", "state", "executed", "path_taken")
SUMMARY_DECISION_KEYS = ("decision", "mode", "conviction", "approver", "decided_at_local",
                         "deadline_local", "on_time", "acknowledged_soft_checks")
SUMMARY_PM_KEYS = ("risk_posture", "posture_label", "regime", "regime_label")
SUMMARY_PROPOSAL_KEYS = ("n_long", "n_short", "ex_ante_vol", "gross", "net", "beta")
SUMMARY_PERF_KEYS = ("n_days", "ret", "value_added")
#: Pesquisa publicada: sem fornecedor/mente (``provider``, ``author``), snapshot nem hashes.
RESEARCH_HEAD_KEYS = ("source", "is_synthetic", "counts")
NOTE_KEYS = ("issuer_id", "role", "stance", "confidence", "horizon_weeks", "thesis",
             "key_risks", "catalysts", "squeeze", "n_evidence", "created_at")
TABLE_NOTE_KEYS = ("issuer_id", "role", "stance", "confidence", "horizon_weeks")
MACRO_KEYS = ("scope", "stance", "regime", "summary", "key_events", "risks",
              "portfolio_implications", "n_evidence", "created_at")
VIEW_KEYS = ("issuer_id", "source", "score", "confidence", "no_short", "no_long",
             "max_abs_weight", "rationale")
REPORT_KEYS = ("available", "has_html", "chars")
#: Campos de TI da semana (ledger de IA, tentativas/fallbacks, manifesto do briefing, entradas,
#: versões de proposta e decisão com hashes, apontamentos): ficam no livro e na cópia local.
WEEK_IT_KEYS = ("ai_calls", "attempts", "briefing", "inputs", "issues", "input_issues",
                "proposals", "decisions")
#: Tese fora da semana em foco: só a manchete.
THESIS_SLIM_KEYS = ("available", "week", "published_at", "authorship", "is_synthetic", "title",
                    "summary_md")
#: Textos por nome das posições da tese (o resto da linha são números e rótulos curtos).
THESIS_NAME_TEXTS = ("why_md", "risk_md", "trigger_md")


def _urls(evidence: Any, n: int) -> list[dict[str, Any]]:
    return [{"kind": e.get("kind"), "url": e.get("url")}
            for e in (evidence or []) if isinstance(e, dict) and e.get("url")][:max(n, 0)]


def _note_pub(n: Mapping[str, Any], lim: Limites, cortes: _Cortes) -> dict[str, Any]:
    campo = "weeks[].research.notes[]"
    out = _pick(n, NOTE_KEYS)
    _cut_field(out, "thesis", lim.tese_chars, cortes, campo)
    _cut_list(out, "key_risks", lim.itens_nota, cortes, campo, item_chars=lim.texto_curto)
    _cut_list(out, "catalysts", lim.itens_nota, cortes, campo, item_chars=lim.texto_curto,
              item_key="description")
    if isinstance(out.get("squeeze"), dict):
        sq = dict(out["squeeze"])
        _cut_field(sq, "rationale", lim.texto_curto, cortes, f"{campo}.squeeze")
        out["squeeze"] = sq
    out["evidence"] = _urls(n.get("evidence"), lim.urls_nota)
    for key in ("bull_points", "bear_points"):
        if n.get(key):
            cortes.add(f"{campo}.{key}", "omitido na publicação")
    return out


def _macro_pub(m: Mapping[str, Any], lim: Limites, cortes: _Cortes) -> dict[str, Any]:
    campo = "weeks[].research.macro[]"
    out = _pick(m, MACRO_KEYS)
    _cut_field(out, "summary", lim.resumo_macro_chars, cortes, campo)
    _cut_list(out, "key_events", lim.itens_macro, cortes, campo,
              item_chars=lim.item_macro_chars, item_key="description")
    for key in ("risks", "portfolio_implications"):
        _cut_list(out, key, lim.itens_macro, cortes, campo, item_chars=lim.item_macro_chars)
    out["evidence"] = _urls(m.get("evidence"), lim.urls_nota)
    return out


#: Postura macro que fica na pesquisa da semana anterior enxuta.
MACRO_SLIM_KEYS = ("scope", "stance", "regime", "n_evidence")


def _research_slim(r: Mapping[str, Any], cortes: _Cortes) -> dict[str, Any]:
    """Pesquisa da semana anterior (sem detalhe): contagens e a postura macro."""
    out = _pick(r, RESEARCH_HEAD_KEYS)
    out["macro"] = [_pick(m, MACRO_SLIM_KEYS) for m in (r.get("macro") or [])]
    n_notes, n_views = len(r.get("notes") or []), len(r.get("views") or [])
    out.update({"notes": [], "notes_table": [], "views": [], "resumo": True,
                "notes_detail": False})
    cortes.add("weeks[].research", "semana anterior enxuta: contagens e a postura macro "
               "(escopo, stance, regime); notas, visões e textos ficam no livro",
               1 + n_notes + n_views)
    return out


def _research_pub(r: Any, w: Mapping[str, Any], lim: Limites, cortes: _Cortes, *,
                  full_notes: bool = True, detail: bool = True) -> Any:
    """Notas macro resumidas; notas por emissor quase completas só na semana da carteira vigente
    (``full_notes``) e só para os emissores dessa carteira COM visão do PM; as demais numa tabela
    (papel, stance, confiança, horizonte, veredito de squeeze). ``detail=False``: semana anterior
    enxuta (:func:`_research_slim`)."""
    if not isinstance(r, dict):
        return r
    if not detail:
        return _research_slim(r, cortes)
    out = _pick(r, RESEARCH_HEAD_KEYS)
    out["macro"] = [_macro_pub(m, lim, cortes) for m in (r.get("macro") or [])]
    if "notes" not in r:
        out["notes_detail"] = r.get("notes_detail", False)
        return out
    book = {p.get("issuer_id") for p in ((w.get("proposal") or {}).get("positions") or [])}
    pm = w.get("pm_decision") or {}
    pm_ids = ({v.get("issuer_id") for v in (pm.get("views") or [])}
              if pm.get("valid") is not False else set())
    full_ids = (book & pm_ids) if lim.notas_completas and full_notes else set()
    notes = list(r.get("notes") or [])
    out["notes"] = [_note_pub(n, lim, cortes) for n in notes if n.get("issuer_id") in full_ids]
    table = []
    for n in notes:
        if n.get("issuer_id") in full_ids:
            continue
        row = _pick(n, TABLE_NOTE_KEYS)
        row["squeeze_verdict"] = (n.get("squeeze") or {}).get("verdict")
        table.append(row)
    if table and not lim.tabela_notas:
        cortes.add("weeks[].research.notes[]", "omitido (ficam as contagens)", len(table))
        table = []
    elif table:
        cortes.add("weeks[].research.notes[]", "só a linha da tabela (emissor fora da carteira "
                   "vigente ou sem visão do PM): research.notes_table", len(table))
    out["notes_table"] = table
    out["notes_detail"] = bool(r.get("notes_detail", True))
    out["notes_selection"] = ("emissores da carteira vigente com visão do PM"
                              if lim.notas_completas and full_notes else "nenhuma (só a tabela)")
    views, outside = [], 0
    for v in r.get("views") or []:
        if v.get("issuer_id") not in book and not lim.visoes_fora_carteira:
            outside += 1
            continue
        x = _pick(v, VIEW_KEYS)
        if v.get("issuer_id") in book and lim.visao_chars > 0:
            _cut_field(x, "rationale", lim.visao_chars, cortes, "weeks[].research.views[]")
        elif x.get("rationale"):
            x["rationale"] = None
            cortes.add("weeks[].research.views[].rationale",
                       "omitido (emissor fora da carteira da semana)" if lim.visao_chars > 0
                       else "omitido")
        if v.get("note_ids"):
            cortes.add("weeks[].research.views[].note_ids", "omitido na publicação")
        views.append(x)
    if outside:
        cortes.add("weeks[].research.views", "só as visões de emissores da carteira da semana",
                   outside)
    if not lim.visoes_pesquisa and views:
        cortes.add("weeks[].research.views", "omitido (ficam as contagens)", len(views))
        views = []
    out["views"] = views
    if "news" in r:
        out["news"] = list(r.get("news") or [])
        _cut_list(out, "news", lim.noticias, cortes, "weeks[].research", item_chars=200,
                  item_key="title")
        out.pop(TRUNC_FLAG, None)
    return out


def _shadow_pub(s: Any, w: Mapping[str, Any], lim: Limites, cortes: _Cortes) -> Any:
    if not isinstance(s, dict):
        return s
    out = dict(s)
    _drop(out, "risk", cortes, "weeks[].shadow",
          "omitido (a comparação CDP × sombra está em weeks[].shadow.comparison)")
    cmp = dict(out.get("comparison") or {})
    _cut_list(cmp, "weight_diffs", lim.posicoes_sombra, cortes, "weeks[].shadow.comparison")
    cmp.pop(TRUNC_FLAG, None)
    out["comparison"] = cmp
    cdp: dict[str, float] = {}
    for p in (w.get("proposal") or {}).get("positions") or []:
        cdp[p.get("issuer_id")] = cdp.get(p.get("issuer_id"), 0.0) + float(p.get("weight") or 0.0)
    sh: dict[str, float] = {}
    for p in out.get("positions") or []:
        sh[p.get("issuer_id")] = sh.get(p.get("issuer_id"), 0.0) + float(p.get("weight") or 0.0)
    positions = sorted(out.get("positions") or [], key=lambda p: (
        -abs(cdp.get(p.get("issuer_id"), 0.0) - sh.get(p.get("issuer_id"), 0.0)),
        str(p.get("issuer_id"))))
    if len(positions) > lim.posicoes_sombra:
        cortes.add("weeks[].shadow.positions",
                   f"só as {lim.posicoes_sombra} maiores diferenças de peso vs. o CDP",
                   len(positions) - lim.posicoes_sombra)
    out["positions"] = positions[:lim.posicoes_sombra]
    return out


def _report_pub(rep: Any, cortes: _Cortes) -> Any:
    """Relatório semanal: disponibilidade e tamanho (o Markdown, o caminho e o SHA-256 ficam
    em ``reports/``; a página mostra as seções estruturadas)."""
    if not isinstance(rep, dict):
        return rep
    out = _pick(rep, REPORT_KEYS)
    if rep.get("markdown"):
        cortes.add("weeks[].report.markdown", "omitido (fica em reports/weekly; a página mostra "
                   "as seções estruturadas)")
    return out


#: Verificação aprovada "perto do limite": |valor| / |limite| entre esta razão e o seu inverso
#: (teto quase tomado ou piso quase rompido).
PERTO_DO_LIMITE = 0.85
#: Verificações técnicas (validade dos pesos, origem e defasagem dos dados) que a página não
#: exibe: publicadas sem o texto ``details`` (que fala de snapshot e hash, não de investimento).
CHECKS_TECNICOS = frozenset({"WEIGHTS_VALID", "SYNTHETIC_DATA", "DATA_STALENESS"})


def compliance_relevante(c: Mapping[str, Any]) -> bool:
    """Verificação que não é um simples "aprovado com folga": reprovada, informativa (INFO) ou
    aprovada perto do limite (:data:`PERTO_DO_LIMITE`)."""
    if c.get("passed") is False or c.get("severity") == "INFO":
        return True
    v, lim = _num(c.get("value")), _num(c.get("limit"))
    if v is None or not lim:
        return False
    ratio = abs(v) / abs(lim)
    return PERTO_DO_LIMITE <= ratio <= 1.0 / PERTO_DO_LIMITE


def _compliance_pub(comp: Mapping[str, Any], lim: Limites, cortes: _Cortes, *,
                    detail: bool) -> dict[str, Any]:
    """Gates de compliance: as contagens sempre; as verificações não triviais
    (:func:`compliance_relevante`) com ``compliance_relevantes`` e ``detail``, senão só as
    reprovadas; ``details`` das aprovadas só com ``detalhes_aprovadas``; as verificações
    técnicas (:data:`CHECKS_TECNICOS`) nunca trazem ``details``."""
    out = dict(comp)
    campo = "weeks[].proposal.compliance.checks"
    keep = compliance_relevante if lim.compliance_relevantes and detail else (
        lambda c: c.get("passed") is False)
    checks, n_out = [], 0
    for c in comp.get("checks") or []:
        if not keep(c):
            n_out += 1
            continue
        c = dict(c)
        if str(c.get("check_id") or "").split(":")[0] in CHECKS_TECNICOS:
            _drop(c, "details", cortes, f"{campo}[]", "omitido (verificação técnica de dados, "
                  "não exibida)")
        if c.get("passed") is not False and not lim.detalhes_aprovadas and c.get("details"):
            c.pop("details")
            cortes.add(f"{campo}[].details", "omitido nos gates aprovados (os reprovados trazem o "
                       "texto)")
            out["details_aprovadas_omitidos"] = True
        _cut_field(c, "details", lim.texto_curto, cortes, f"{campo}[]")
        checks.append(c)
    if n_out:
        cortes.add(campo, "só as verificações não triviais (reprovadas, informativas e perto do "
                   "limite)" if keep is compliance_relevante else
                   "só as verificações reprovadas", n_out)
        out["n_omitidas"] = n_out
    if "checks" in comp:
        out["checks"] = checks
    return out


def _week_full(w: Mapping[str, Any], lim: Limites, cortes: _Cortes, *, latest: bool,
               live_week: Any, positions_source: bool, full_notes: bool = True,
               detail: bool = True) -> dict[str, Any]:
    """Semana em detalhe. ``positions_source``: a tabela de posições da página usa as
    posições-alvo desta semana (sem registro diário); nas demais, só as colunas exibidas.
    ``full_notes``: semana da carteira vigente (notas completas por emissor e a tese completa).
    ``detail=False``: semana anterior enxuta (proposta sem gates aprovados, risco nem notas do
    otimizador; pesquisa só com a postura macro) — os textos da decisão do PM continuam."""
    out = dict(w)
    week = str(w.get("week"))
    for key in WEEK_IT_KEYS:
        _drop(out, key, cortes, "weeks[]", "omitido na publicação (TI: fica no livro e na cópia "
              "local)")
    out["shadow"] = _shadow_pub(w.get("shadow"), w, lim, cortes)
    out["research"] = _research_pub(w.get("research"), w, lim, cortes, full_notes=full_notes,
                                    detail=detail)
    if not detail:
        out["detail_publicacao"] = "enxuta"
    prop = out.get("proposal")
    if isinstance(prop, dict):
        prop = dict(prop)
        if prop.get("positions"):
            unused = [k for k in UNUSED_POSITION_KEYS if any(k in p for p in prop["positions"])]
            if unused:
                prop["positions"] = [{k: v for k, v in p.items() if k not in UNUSED_POSITION_KEYS}
                                     for p in prop["positions"]]
                cortes.add("weeks[].proposal.positions[]", "omitidos (não exibidos): "
                           + ", ".join(unused), len(prop["positions"]))
        if not positions_source and prop.get("positions"):
            extra = sorted({k for p in prop["positions"] for k in p} - set(SLIM_POSITION_KEYS))
            prop["positions"] = [_pick(p, SLIM_POSITION_KEYS) for p in prop["positions"]]
            if extra:
                cortes.add("weeks[].proposal.positions[]", "só as colunas exibidas (a tabela de "
                           "posições usa a marcação diária): omitidos " + ", ".join(extra),
                           len(prop["positions"]))
        _drop(prop, "trades", cortes, "weeks[].proposal",
              "omitido (boleta de ordens; giro e custo em weeks[].proposal.summary)")
        if not (lim.hedge_cambial and latest):
            _drop(prop, "fx_hedges", cortes, "weeks[].proposal",
                  "omitido (só a semana mais recente traz o hedge)")
        if isinstance(prop.get("optimizer"), dict):
            opt = dict(prop["optimizer"])
            _cut_list(opt, "notes", lim.notas_otimizador if detail else 0, cortes,
                      "weeks[].proposal.optimizer", item_chars=lim.texto_curto)
            opt.pop(TRUNC_FLAG, None)
            prop["optimizer"] = opt
        if isinstance(prop.get("compliance"), dict):
            prop["compliance"] = _compliance_pub(prop["compliance"], lim, cortes, detail=detail)
        if week == str(live_week):
            _drop(prop, "risk", cortes, "weeks[].proposal",
                  "omitido na semana vigente (idêntico a risk.ex_ante)")
        elif not detail:
            _drop(prop, "risk", cortes, "weeks[].proposal",
                  "omitido na semana anterior enxuta (não exibido; fica no livro)")
        out["proposal"] = prop
    out["decision"] = _decision_pub(w.get("decision"), cortes)
    if lim.texto_pm_chars is not None:
        out["pm_decision"] = _cut_pm(w.get("pm_decision"), lim.texto_pm_chars, cortes)
        out["decision"] = _cut_decision(out["decision"], lim.texto_pm_chars, cortes)
    if not lim.diario_decisao and isinstance(out.get("decision"), dict) \
            and out["decision"].get("journal"):
        out["decision"] = {**out["decision"], "journal": None, "journal_omitted": True}
        cortes.add("weeks[].decision.journal", "omitido (fica no livro)")
    out["report"] = _report_pub(w.get("report"), cortes)
    if out.get("memo_markdown"):
        _cut_field(out, "memo_markdown", lim.comentario_chars, cortes, "weeks[]")
    if "thesis" in out:
        out["thesis"] = _thesis_pub(w.get("thesis"), lim, cortes, focus=full_notes)
    return out


def _thesis_pub(t: Any, lim: Limites, cortes: _Cortes, *, focus: bool) -> Any:
    """Tese da carteira: completa na semana em foco (a da carteira vigente); nas demais semanas
    completas, só a manchete (título, resumo, autoria). Na semana em foco, só os níveis finais
    cortam: textos por nome encurtados (``tese_carteira_nome_chars`` > 0) ou omitidos (0) e
    textos das seções e dos temas encurtados (``tese_carteira_secao_chars``)."""
    if not isinstance(t, dict) or not t.get("available"):
        return t
    campo = "weeks[].thesis"
    if not focus:
        out = _pick(t, THESIS_SLIM_KEYS)
        out["resumo"] = True
        cortes.add(campo, "semana fora de foco: só título, resumo e autoria (a tese completa vai "
                   "só na semana da carteira vigente; fica no livro)")
        return out
    out = dict(t)
    n = lim.tese_carteira_nome_chars
    if n is not None and isinstance(out.get("positions"), list):
        rows, dropped = [], 0
        for p in out["positions"]:
            if isinstance(p, dict):
                p = dict(p)
                if n <= 0:
                    hits = [k for k in THESIS_NAME_TEXTS if p.get(k)]
                    dropped += len(hits)
                    for k in THESIS_NAME_TEXTS:
                        p.pop(k, None)
                else:
                    for k in THESIS_NAME_TEXTS:
                        _cut_field(p, k, n, cortes, f"{campo}.positions[]")
            rows.append(p)
        out["positions"] = rows
        if dropped:
            out[TRUNC_FLAG] = True
            cortes.add(f"{campo}.positions[]", "textos por nome omitidos (ficam os números)",
                       dropped)
    s = lim.tese_carteira_secao_chars
    if s is not None:
        for key, items, text_keys in (("sections", out.get("sections"), ("md",)),
                                      ("themes", out.get("themes"), ("md", "risks_md"))):
            if isinstance(items, list):
                new = []
                for it in items:
                    it = dict(it) if isinstance(it, dict) else it
                    for k in text_keys:
                        _cut_field(it, k, s, cortes, f"{campo}.{key}[]")
                    new.append(it)
                out[key] = new
    return out


PM_TEXT_KEYS = ("market_view", "what_changed", "evaluation_last_week")
PM_LIST_TEXT = (("views", "rationale"), ("exclusions", "reason"), ("position_journal", "thesis"),
                ("position_journal", "invalidation_criteria"), ("position_journal", "premortem"))
JOURNAL_TEXT_KEYS = ("situation", "alternatives_considered", "sizing_rationale",
                     "ai_vs_quant_vs_pm", "premortem", "mental_state")


def _cut_pm(pm: Any, limit: int, cortes: _Cortes) -> Any:
    """Último recurso: textos da leitura do PM cortados em ``limit`` caracteres."""
    if not isinstance(pm, dict):
        return pm
    out = dict(pm)
    for key in PM_TEXT_KEYS:
        _cut_field(out, key, limit, cortes, "weeks[].pm_decision")
    for lst, key in PM_LIST_TEXT:
        if isinstance(out.get(lst), list):
            items = []
            for it in out[lst]:
                it = dict(it) if isinstance(it, dict) else it
                _cut_field(it, key, limit, cortes, f"weeks[].pm_decision.{lst}[]")
                items.append(it)
            out[lst] = items
    return out


#: Rótulo do processo que gerou a carteira, acrescentado ao fim do racional da decisão
#: ("... Caminho: cdp."): processo interno, não vai ao perfil publicado.
_CAMINHO_RE = re.compile(r"[ \t]*\bCaminho:[ \t]*[\w-]+\.?\s*$")


def _decision_pub(dec: Any, cortes: _Cortes) -> Any:
    """Decisão publicada: sem ``co_sign_reasons`` (ciência automática dos limites de alerta,
    registro do processo) e sem o rótulo do processo ("Caminho: cdp.") no fim do racional."""
    if not isinstance(dec, dict):
        return dec
    out = dict(dec)
    _drop(out, "co_sign_reasons", cortes, "weeks[].decision",
          "omitido (registro do processo; os limites de alerta reconhecidos ficam em "
          "acknowledged_soft_checks)")
    text = out.get("rationale")
    if isinstance(text, str) and _CAMINHO_RE.search(text):
        out["rationale"] = _CAMINHO_RE.sub("", text) or None
    return out


def _cut_decision(dec: Any, limit: int, cortes: _Cortes) -> Any:
    if not isinstance(dec, dict):
        return dec
    out = dict(dec)
    _cut_field(out, "rationale", limit, cortes, "weeks[].decision")
    if isinstance(out.get("journal"), dict):
        j = dict(out["journal"])
        for key in JOURNAL_TEXT_KEYS:
            _cut_field(j, key, limit, cortes, "weeks[].decision.journal")
        out["journal"] = j
    return out


def _week_summary(w: Mapping[str, Any]) -> dict[str, Any]:
    """Semana antiga em uma linha da tabela de semanas (sem textos nem tese)."""
    out = _pick(w, SUMMARY_WEEK_KEYS)
    out["detail"] = "resumo"
    dec, pm, prop = w.get("decision"), w.get("pm_decision"), w.get("proposal")
    out["decision"] = _pick(dec, SUMMARY_DECISION_KEYS) if isinstance(dec, dict) else None
    out["pm_decision"] = _pick(pm, SUMMARY_PM_KEYS) if isinstance(pm, dict) else None
    out["proposal"] = ({"summary": _pick(prop.get("summary"), SUMMARY_PROPOSAL_KEYS),
                        "positions": []} if isinstance(prop, dict) else None)
    perf = w.get("performance")
    out["performance"] = _pick(perf, SUMMARY_PERF_KEYS) if isinstance(perf, dict) else None
    rep = w.get("report")
    out["report"] = ({"available": True} if isinstance(rep, dict) and rep.get("available")
                     else None)
    return out


def _weeks(weeks: Sequence[Mapping[str, Any]], lim: Limites, cortes: _Cortes, live_week: Any,
           has_daily_positions: bool) -> list[dict[str, Any]]:
    full = [str(w.get("week")) for w in weeks if w.get("detail") == "completo"]
    full_set = set(full[-lim.semanas_completas:]) if lim.semanas_completas > 0 else set()
    live = str(live_week) if live_week else None
    if full_set and live in full:
        full_set.add(live)  # a semana da carteira vigente nunca sai do detalhe
    latest = str(weeks[-1].get("week")) if weeks else None
    # Semana "em foco": a da carteira vigente (a página tira dela as notas, visões e gates);
    # sem carteira vigente em detalhe, a mais recente. Ela e a mais recente ficam em detalhe; as
    # demais semanas completas ficam enxutas quando ``semana_anterior_detalhe`` é falso.
    focus = live if live in full_set else latest
    older = [w for w in weeks if str(w.get("week")) not in full_set]
    keep_old = {str(w.get("week")) for w in older[-lim.semanas_resumo:]} if lim.semanas_resumo > 0 \
        else set()
    if len(older) > len(keep_old):
        cortes.add("weeks[]", f"só as {lim.semanas_resumo} semanas resumidas mais recentes "
                   "(as anteriores ficam no livro)", len(older) - len(keep_old))
    out = []
    for w in weeks:
        wk = str(w.get("week"))
        if wk not in full_set and wk not in keep_old:
            continue
        if wk in full_set:
            source = not has_daily_positions and (wk == str(live_week) if live_week
                                                  else wk == latest)
            detail = lim.semana_anterior_detalhe or wk in (focus, latest)
            out.append(_week_full(w, lim, cortes, latest=wk == latest, live_week=live_week,
                                  positions_source=source, full_notes=wk == focus,
                                  detail=detail))
        else:
            cortes.add("weeks[]", f"semana resumida (só as {lim.semanas_completas} mais recentes "
                       "em detalhe): decisão, postura, caminho e resumo da carteira")
            out.append(_week_summary(w))
    return out


# ==========================================================
# Relatórios, monitor, backtests e auditoria
# ==========================================================

DAILY_KEYS = ("date", "published", "has_html", "nav_end", "ret")
#: Comentário do dia publicado: texto, origem e se é da mente (sem o nome da mente).
COMMENTARY_KEYS = ("markdown", "source", "ai")
#: Linha de proveniência do comentário ("_Autoria: mente X [IA] (comentario.json validado)..._"):
#: processo e arquivos internos; a origem publicada fica em ``source``/``ai``.
_AUTORIA_RE = re.compile(r"^_[ \t]*Autoria:[^\n]*_[ \t]*(?:\n|$)", re.MULTILINE)


def _sem_autoria(md: Any) -> Any:
    """Markdown sem a linha de proveniência (:data:`_AUTORIA_RE`)."""
    if not isinstance(md, str) or not _AUTORIA_RE.search(md):
        return md
    out = re.sub(r"\n{3,}", "\n\n", _AUTORIA_RE.sub("", md))
    return out.rstrip() + ("\n" if md.endswith("\n") else "")


def report_path(reports_dir: str, kind: Any, day: Any) -> str:
    """Caminho do Markdown de um relatório (o mesmo que a página monta a partir do índice)."""
    return f"{reports_dir}/{kind}/{day}/relatorio.md"


def _reports(daily: Sequence[Mapping[str, Any]], index: Sequence[Mapping[str, Any]],
             lim: Limites, cortes: _Cortes
             ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Os ``comentarios`` relatórios diários mais recentes com o comentário do dia (Markdown
    cortado em ``comentario_chars``); de todos os relatórios, tipo e data em ``reports_index``
    (o Markdown completo fica em ``reports/``)."""
    out = []
    for i, r in enumerate(daily):
        if r.get("report_markdown"):
            cortes.add("daily_reports[].report_markdown",
                       "omitido (fica em reports/daily; o comentário do dia vai em commentary)")
        if i >= lim.comentarios:
            cortes.add("daily_reports[]", f"só os {lim.comentarios} mais recentes (os demais "
                       "em reports_index)")
            continue
        x = _pick(r, DAILY_KEYS)
        c = r.get("commentary")
        if isinstance(c, dict):
            c = _pick(c, COMMENTARY_KEYS)
            if "markdown" in c:
                c["markdown"] = _sem_autoria(c["markdown"])
            _cut_field(c, "markdown", lim.comentario_chars, cortes, "daily_reports[].commentary")
        x["commentary"] = c
        out.append(x)
    # Índice: tipo e data; o caminho é sempre
    # ``<meta.publication.reports_dir>/<kind>/<date>/relatorio.md`` (``has_md``) e a página o
    # monta (:func:`report_path`), sem repeti-lo em cada linha.
    idx = [_pick(r, ("kind", "date", "has_md")) for r in index]
    if lim.indice_relatorios is not None and len(idx) > lim.indice_relatorios:
        idx = sorted(idx, key=lambda r: (str(r.get("date")), str(r.get("kind"))),
                     reverse=True)[:lim.indice_relatorios]
        cortes.add("reports_index", f"só os {lim.indice_relatorios} relatórios mais recentes",
                   len(index) - lim.indice_relatorios)
    return out, idx


def _monitor(rm: Mapping[str, Any], lim: Limites, cortes: _Cortes) -> dict[str, Any]:
    """Só a execução mais recente completa (JSON e Markdown); as demais, na linha do tempo."""
    out = dict(rm)
    tl = list(rm.get("timeline") or [])
    if len(tl) > lim.execucoes_risco:
        cortes.add("risk_monitor.timeline",
                   f"só as {lim.execucoes_risco} execuções mais recentes",
                   len(tl) - lim.execucoes_risco)
    out["timeline"] = tl[:lim.execucoes_risco]
    latest = rm.get("latest") or {}
    runs = []
    n_files = 0
    for run in rm.get("runs") or []:
        files = run.get("files") or []
        n_files += len(files)
        if run.get("key") != latest.get("run_key"):
            continue
        keep = []
        for f in files:
            if f.get("name") == latest.get("md_file") and not lim.monitor_markdown:
                continue
            if f.get("name") in (latest.get("file"), latest.get("md_file")):
                f = {k: v for k, v in f.items() if k != "summary"}
                intra = (f.get("data") or {}).get("intradiario") if isinstance(
                    f.get("data"), dict) else None
                if not lim.monitor_posicoes and isinstance(intra, dict) and intra.get("posicoes"):
                    f["data"] = {**f["data"], "intradiario": {k: v for k, v in intra.items()
                                                              if k != "posicoes"}}
                    cortes.add("risk_monitor.runs[].files[].data.intradiario.posicoes",
                               "omitido (fica o resumo do intradiário)", len(intra["posicoes"]))
                keep.append(f)
        runs.append({**run, "files": keep})
    kept = sum(len(r["files"]) for r in runs)
    if n_files > kept:
        cortes.add("risk_monitor.runs[].files",
                   "omitido (só a execução mais recente; as demais na linha do tempo)",
                   n_files - kept)
    out["runs"] = runs
    return out


#: Curva de patrimônio publicada da execução escolhida (pontos de fim de mês).
NAV_SERIES = ("date", "nav", "drawdown")
BT_RUN_KEYS = ("id", "label", "variant", "description", "overrides", "signal_weights", "metrics",
               "is_synthetic")
BT_SELECTED_KEYS = ("provenance", "n_daily_obs")


def _month_end(series: Mapping[str, Any]) -> dict[str, list[Any]] | None:
    """Pontos de fim de mês (o último ponto semanal de cada mês) de séries alinhadas por data."""
    dates = list(series.get("date") or [])
    if not dates:
        return None
    idx = [i for i, d in enumerate(dates)
           if i == len(dates) - 1 or str(dates[i + 1])[:7] != str(d)[:7]]
    return {k: [list(series[k])[i] for i in idx] for k in NAV_SERIES if k in series}


def _doc_date(path: Any) -> str | None:
    """Data (AAAA-MM-DD) de uma nota de calibração, tirada do caminho (``2026-10-05/...``)."""
    m = _DATE_IN_PATH_RE.search(str(path or ""))
    return m.group(0) if m else None


def chosen_backtest(runs: Sequence[Mapping[str, Any]], documents: Sequence[Mapping[str, Any]],
                    config_hash: str | None) -> tuple[str | None, str | None]:
    """Execução "escolhida/vigente": a da configuração atual (``config_hash``); senão a variante
    declarada escolhida na nota de calibração mais recente ("variante X foi escolhida"); senão a
    última execução (ordem do id). O critério é texto para o investidor: sem caminhos de
    arquivos nem hashes."""
    if not runs:
        return None, None
    same = [r for r in runs if config_hash
            and (r.get("provenance") or {}).get("config_hash") == config_hash]
    if same:
        return str(same[-1].get("id")), "configuração vigente do modelo"
    for doc in sorted(documents, key=lambda d: str(d.get("path")), reverse=True):
        m = _CHOSEN_RE.search(str(doc.get("markdown") or ""))
        if not m:
            continue
        hits = [r for r in runs if str(r.get("variant") or "").lower() == m.group(1).lower()]
        if hits:
            day = _doc_date(doc.get("path"))
            when = (f" de {day[8:10]}/{day[5:7]}/{day[:4]}" if day else "")
            return str(hits[-1].get("id")), f"variante escolhida na calibração{when}"
    return str(runs[-1].get("id")), "execução mais recente"


def _backtests(bt: Mapping[str, Any], config_hash: str | None, lim: Limites, cortes: _Cortes
               ) -> dict[str, Any]:
    """Execuções de backtest: a escolhida/vigente (curva de fim de mês, resumo do IC e notas) e
    as ``backtests_execucoes`` mais recentes além dela (só métricas); as mais antigas só entram
    na contagem ``n_runs`` (a calibração mensal acrescenta execuções todo mês: sem este teto o
    bloco cresceria sem limite). Notas de calibração: as ``backtests_documentos`` mais recentes,
    só com a data (sem caminho, texto nem SHA-256)."""
    out = dict(bt)
    all_runs = list(bt.get("runs") or [])
    all_docs = list(bt.get("documents") or [])
    chosen, why = chosen_backtest(all_runs, all_docs, config_hash)
    others = [r for r in all_runs if str(r.get("id")) != chosen]
    n_extra = max(lim.backtests_execucoes, 0)
    keep = {str(r.get("id")) for r in others[max(len(others) - n_extra, 0):]} if n_extra else set()
    if chosen:
        keep.add(chosen)
    runs = [r for r in all_runs if str(r.get("id")) in keep]
    if len(all_runs) > len(runs):
        cortes.add("backtests.runs", f"só a execução escolhida e as {n_extra} mais recentes (as "
                   "demais ficam em reports/backtest)", len(all_runs) - len(runs))
    out["n_runs"] = len(all_runs)
    n_docs = max(lim.backtests_documentos, 0)
    docs = sorted(all_docs, key=lambda d: str(d.get("path")))
    docs = docs[max(len(docs) - n_docs, 0):] if n_docs else []
    if len(all_docs) > len(docs):
        cortes.add("backtests.documents", f"só as {n_docs} notas de calibração mais recentes",
                   len(all_docs) - len(docs))
    out["n_documents"] = len(all_docs)
    new_runs = []
    for r in runs:
        x = _pick(r, BT_RUN_KEYS)
        notes = [str(n) for n in (r.get("notes") or [])]
        x["n_notes"] = len(notes)
        if str(r.get("id")) == chosen:
            x["selected"] = True
            x.update(_pick(r, BT_SELECTED_KEYS))
            if isinstance(x.get("provenance"), dict):
                x["provenance"] = {k: v for k, v in x["provenance"].items()
                                   if k != "backtest_config"}
            # Limitações (sem data) antes das semanas com restrições relaxadas (com data).
            x["notes"] = ([n for n in notes if not _DATED_NOTE_RE.match(n)]
                          + [n for n in notes if _DATED_NOTE_RE.match(n)])
            _cut_list(x, "notes", lim.notas_backtest, cortes, "backtests.runs[]",
                      item_chars=lim.nota_backtest_chars)
            if isinstance(r.get("nav_weekly"), dict):
                x["nav_monthly"] = _month_end(r["nav_weekly"])
                cortes.add("backtests.runs[].nav_weekly", "reduzido à curva de patrimônio "
                           "(NAV e drawdown) no último ponto de cada mês: nav_monthly")
            ic = r.get("ic")
            x["ic"] = {"summary": ic.get("summary")} if isinstance(ic, dict) else None
            if isinstance(ic, dict) and ic.get("cumulative"):
                cortes.add("backtests.runs[].ic.cumulative", "omitido (fica o resumo do IC)")
        else:
            for key in ("nav_weekly", "ic", "notes", "provenance"):
                if r.get(key):
                    cortes.add(f"backtests.runs[].{key}",
                               "omitido (as demais execuções só trazem as métricas)")
        if r.get("weekly"):
            cortes.add("backtests.runs[].weekly", "omitido na publicação")
        new_runs.append(x)
    out["runs"] = new_runs
    out["selected"] = {"id": chosen, "criterio": why} if chosen else None
    # Notas de calibração: só a data (o caminho e o Markdown ficam em reports/backtest).
    out["documents"] = [{"date": _doc_date(d.get("path"))} for d in docs]
    if docs:
        cortes.add("backtests.documents[]", "só a data da nota de calibração (caminho e texto "
                   "ficam em reports/backtest)", len(docs))
    return out


#: Trilha de auditoria publicada: só se existe, se a cadeia confere e o nº de eventos.
AUDIT_KEYS = ("exists", "chain_ok", "n_events")
#: Blocos do mandato (``meta.mandate``) que a página lê — limites de risco, liquidez, drawdown,
#: squeeze e short, sinais do alpha e o modelo de risco (aba "Mandato e metodologia"). Os demais
#: (custos, tabela, agenda das rotinas, adoção de IA) ficam em fund.yaml e na cópia local.
MANDATE_KEYS = ("risk", "liquidity", "drawdown", "squeeze", "shorting", "alpha", "risk_model")


def _audit(audit: Mapping[str, Any], cortes: _Cortes) -> dict[str, Any]:
    out = _pick(audit, AUDIT_KEYS)
    if audit.get("events"):
        cortes.add("audit.events", "omitido (TI: a trilha fica no livro e na cópia local)",
                   len(audit["events"]))
    return out


# ==========================================================
# API
# ==========================================================

def _book_issuers(d: Mapping[str, Any]) -> set[str]:
    ld = d.get("latest_day") or {}
    if ld.get("positions"):
        return {str(p.get("issuer_id")) for p in ld["positions"]}
    live = str((d.get("risk") or {}).get("live_week"))
    for w in d.get("weeks") or []:
        if str(w.get("week")) == live:
            return {str(p.get("issuer_id"))
                    for p in ((w.get("proposal") or {}).get("positions") or [])}
    return set()


#: Chaves de TI que nunca vão ao perfil publicado, em qualquer ponto fora de ``meta`` (ficam no
#: livro e na cópia local): hashes e SHA-256 de artefatos, marcas de verificação contra a
#: trilha, nome da mente e identificadores de snapshot.
_IT_KEY_RE = re.compile(r"(?:^|_)(?:sha256|hash|hashes|verified)$")
_IT_KEYS = frozenset({"mind", "minds", "snapshot_id"})
#: Nome da mente (ferramenta que roda a IA) citado nos textos gerados ("; mente claude-code
#: [IA]", "Mente: codex"): no perfil publicado a oração inteira sai — a página fala de gestão,
#: não de ferramentas. O ``\b`` antes de "mente" preserva os advérbios ("somente em",
#: "fortemente comprada", "principalmente do", "inteiramente simulado").
#: Todas as mentes de ``HARNESS_MINDS``; soltas no texto, só os nomes de assistentes (``demo``,
#: ``api`` e ``outro`` só saem depois de "mente").
_MIND_NAMES = "(?i:" + "|".join(re.escape(m) for m in sorted(
    (m for m in HARNESS_MINDS if m not in ("api", "demo", "outro")), key=len, reverse=True)) + ")"
_ANY_MIND = "(?i:" + "|".join(re.escape(m) for m in sorted(HARNESS_MINDS, key=len,
                                                           reverse=True)) + ")"
_MIND_CLAUSE_RE = re.compile(
    rf"(?P<sep>[ \t]*[;,·][ \t]*|[ \t]*)\b[Mm]ente(?::[ \t]*|[ \t]+){_ANY_MIND}\b"
    rf"(?:[ \t]*\[IA\])?(?P<end>[ \t]*[.;,·])?(?P<ws>[ \t]*)")
_MIND_BARE_RE = re.compile(rf"\b{_MIND_NAMES}\b")
_HAS_MIND_RE = re.compile(rf"{_MIND_NAMES}|\b[Mm]ente(?::\s*|\s+){_ANY_MIND}\b")
_URL_ONLY_RE = re.compile(r"^https?://\S+$")


def _sem_oracao_da_mente(m: re.Match[str]) -> str:
    sep, end, ws = m.group("sep"), m.group("end") or "", m.group("ws")
    if sep.strip():  # "A; mente X. B" → "A. B"; "A; mente X; B" → "A; B"; "A · mente X · B"
        return end + ws
    before = m.string[:m.start()].rstrip(" \t")
    if before and before[-1].isalnum():  # no meio da frase: "preparado pela mente X." → "pela IA."
        return f"{sep}IA{end}{ws}"
    return ws if sep else ""  # oração no início do texto ou da frase: sai inteira


def sem_nome_da_mente(text: str) -> str:
    """Texto sem o nome da mente: a oração "; mente claude-code [IA]" / "Mente: codex" sai
    inteira com o seu separador ("Postura defensiva; regime neutro; mente claude-code. Primeira"
    → "Postura defensiva; regime neutro. Primeira"); no meio de uma frase ("preparada pela mente
    demo") vira "IA"; "claude-code"/"codex" soltos viram "IA". Advérbios terminados em "-mente"
    e URL isolada ficam intactos."""
    if _URL_ONLY_RE.match(text) or not _HAS_MIND_RE.search(text):
        return text
    return _MIND_BARE_RE.sub("IA", _MIND_CLAUSE_RE.sub(_sem_oracao_da_mente, text))


def _sem_ti(x: Any, n: list[int]) -> Any:
    """Cópia sem as chaves de TI (:data:`_IT_KEY_RE`, :data:`_IT_KEYS`) e sem o nome da mente
    nos textos; ``n[0]`` conta as chaves removidas com conteúdo."""
    if isinstance(x, dict):
        out: dict[str, Any] = {}
        for k, v in x.items():
            if k in _IT_KEYS or _IT_KEY_RE.search(k):
                n[0] += v not in (None, [], {}, "")
                continue
            out[k] = _sem_ti(v, n)
        return out
    if isinstance(x, list):
        return [_sem_ti(v, n) for v in x]
    if isinstance(x, str):
        return sem_nome_da_mente(x)
    return x


#: Origem dos alertas de verificação dos registros (só do perfil completo, de operação).
ALERTA_INTEGRIDADE = "integridade"


def _status_pub(st: Any, cortes: _Cortes) -> Any:
    """Status sem a agenda das rotinas, com a integridade reduzida ao resultado (``ok``) e sem
    os alertas da verificação dos registros (``source`` = :data:`ALERTA_INTEGRIDADE`)."""
    if not isinstance(st, dict):
        return st
    out = dict(st)
    _drop(out, "agenda", cortes, "status", "omitido (TI: agenda das rotinas)")
    integ = out.get("integrity")
    if isinstance(integ, dict):
        out["integrity"] = {"ok": integ.get("ok")}
        if integ.get("checks"):
            cortes.add("status.integrity.checks", "omitido (TI: fica o resultado em "
                       "status.integrity.ok)", len(integ["checks"]))
    if isinstance(out.get("alerts"), list):
        alerts = [a for a in out["alerts"]
                  if not (isinstance(a, dict) and a.get("source") == ALERTA_INTEGRIDADE)]
        cortes.add("status.alerts", "omitido (TI: verificação dos registros; fica o resultado "
                   "em status.integrity.ok)", len(out["alerts"]) - len(alerts))
        out["alerts"] = alerts
    return out


def _compactar(full: Mapping[str, Any], lim: Limites, nivel: int, reports_dir: str,
               page_sha256: str | None = None) -> dict[str, Any]:
    from .painel import data_hash, referenced_issuers

    d = copy.deepcopy(dict(full))
    cortes = _Cortes()
    live_week = (d.get("risk") or {}).get("live_week")
    d["track_record"] = _track(d.get("track_record") or {}, lim, cortes, _book_issuers(d))
    d["latest_day"] = _latest(d.get("latest_day"), lim, cortes)
    has_daily = bool((full.get("latest_day") or {}).get("positions"))
    d["weeks"] = _weeks(d.get("weeks") or [], lim, cortes, live_week, has_daily)
    d["daily_reports"], d["reports_index"] = _reports(
        d.get("daily_reports") or [], d.get("reports_index") or [], lim, cortes)
    d["risk_monitor"] = _monitor(d.get("risk_monitor") or {}, lim, cortes)
    meta = dict(d.get("meta") or {})
    d["backtests"] = _backtests(d.get("backtests") or {}, meta.get("config_hash"), lim, cortes)
    d["audit"] = _audit(d.get("audit") or {}, cortes)
    d["status"] = _status_pub(d.get("status"), cortes)
    if d.get("issues"):
        cortes.add("issues", "omitido (TI: apontamentos de leitura ficam na cópia local)",
                   len(d["issues"]))
    d["issues"] = []
    n_ti = [0]
    body = _sem_ti({k: v for k, v in d.items() if k != "meta"}, n_ti)
    if n_ti[0]:
        cortes.add("(hashes, verificações, mente, snapshot)", "omitidos na publicação (TI: ficam "
                   "no livro e na cópia local)", n_ti[0])
    d = {**body, "meta": meta}
    meta.pop("data_hash", None)
    _drop(meta, "invariants", cortes, "meta", "omitido (TI: invariantes do sistema)")
    mandate = dict(meta.get("mandate") or {})
    for key in sorted(set(mandate) - set(MANDATE_KEYS)):
        _drop(mandate, key, cortes, "meta.mandate", "omitido (não exibido; está em fund.yaml)")
    meta["mandate"] = mandate
    if isinstance(meta.get("issuer_names"), dict):
        # Só os emissores ainda citados depois dos cortes.
        refs = referenced_issuers(d)
        names = meta["issuer_names"]
        meta["issuer_names"] = {k: v for k, v in names.items() if k in refs}
        cortes.add("meta.issuer_names", "só os emissores citados na publicação",
                   len(names) - len(meta["issuer_names"]))
    meta["profile"] = "publicacao"
    #: Versão da página (SHA-256 do template) para a qual estes dados foram gerados: a página
    #: publicada compara com a sua e avisa "Página desatualizada" quando diferem.
    meta["page_sha256"] = page_sha256
    meta["export_limits"] = {
        "profile": "publicacao", "max_daily_reports": lim.comentarios,
        "full_weeks": lim.semanas_completas, "track_rows": lim.pregoes,
        "max_risk_runs": lim.execucoes_risco,
        "completo": (full.get("meta") or {}).get("export_limits")}
    meta["publication"] = {
        "nivel": nivel, "niveis": len(NIVEIS), "limites": asdict(lim),
        "max_bytes": DATA_MAX_BYTES, "max_linha": DATA_MAX_LINE, "reports_dir": reports_dir,
        "data_hash_completo": (full.get("meta") or {}).get("data_hash"),
        "formato": "JSON indentado (objetos pequenos numa linha, listas de escalares em linhas "
                   "agrupadas); {\"_colunas\": ..., \"_n\": N} = tabela em colunas, "
                   "{\"_rep\": {\"v\": [...], \"n\": [...]}} = coluna em corridas, "
                   "{\"_partes\": [...]} = texto em partes e {\"_igual\": \"x\", ...} = igual "
                   "à chave irmã x com estes campos (a página desfaz as quatro formas)"}
    meta["truncations"] = cortes.lista()
    d["meta"] = meta
    packed = _split(_pack(d))
    packed["meta"]["data_hash"] = data_hash(packed)
    return packed


def publicacao(full: Mapping[str, Any], *, reports_dir: str = "reports",
               niveis: Sequence[Limites] = NIVEIS, page_sha256: str | None = None
               ) -> dict[str, Any]:
    """Retrato publicável derivado do retrato ``completo`` (função pura e determinística).

    Usa o primeiro nível de :data:`NIVEIS` cujo ``data.json`` cabe no orçamento
    (:data:`DATA_MAX_BYTES`, :data:`DATA_MAX_LINE`); se nenhum couber, devolve o mais compacto
    (a CLI então diz ``publicavel: false``). ``page_sha256``: versão da página (SHA-256 do
    template) gravada em ``meta.page_sha256``."""
    if (full.get("meta") or {}).get("profile") == "publicacao":
        raise ValueError("o retrato já está no perfil de publicação")
    out: dict[str, Any] = {}
    for nivel, lim in enumerate(niveis):
        out = _compactar(full, lim, nivel, reports_dir, page_sha256)
        if cabe(dump_publicacao(out)):
            return out
    return out


def compactar(full: Mapping[str, Any], nivel: int = 0, *, reports_dir: str = "reports",
              lim: Limites | None = None, page_sha256: str | None = None) -> dict[str, Any]:
    """Um nível de compactação, sem testar o orçamento (diagnóstico e testes)."""
    return _compactar(full, lim or NIVEIS[nivel], nivel, reports_dir, page_sha256)


def limites(nivel: int = 0, **changes: Any) -> Limites:
    """Os limites de um nível, com ajustes opcionais (testes e diagnósticos)."""
    return replace(NIVEIS[nivel], **changes)


__all__ = ["COMENTARIOS_MINIMOS", "DATA_MAX_BYTES", "DATA_MAX_LINE", "NIVEIS", "PAGE_MAX_BYTES",
           "PAGE_MAX_LINE", "PERTO_DO_LIMITE", "PREGOES_MINIMOS", "PROFILES", "Limites", "cabe",
           "chosen_backtest", "compactar", "compliance_relevante", "dump_publicacao", "expandir",
           "limites", "max_line", "partes", "publicacao", "report_path", "sem_nome_da_mente"]
