"""Modo ensaio suportado: relógio do cenário e substituto de dados de mercado.

Ensaiar as rotinas nas datas de um cenário (ex.: a semana da carteira inaugural antes dela) exige
dois recursos, ambos **só com ``CDP_ENSAIO=1``** (fora do ensaio a CLI recusa as variáveis):

- ``CDP_AGORA`` — instante do cenário (ISO; sem fuso = Brasília). O relógio de toda a CLI
  (rotinas, gate, agenda, fechamento, cobertura, notas, semanal, trilha) parte dele e anda junto
  com o tempo real, como um relógio de máquina acertado para o cenário.
- ``CDP_ENSAIO_SUBSTITUTO=1`` — substituto de dados **rotulado**: para pregões ainda
  inexistentes, a base de mercado recebe a última barra real disponível de cada série com a data
  pedida (preços, câmbio, índices, aluguel e juros). Cada lote substituído é anunciado na saída
  de erro com o rótulo ``[ensaio] SUBSTITUTO``; o retorno desses dias é nulo por construção.

Com ``CDP_ENSAIO=1``, ``cdp publicar`` faz o commit local (com o trailer ``CDP-Ensaio: sim``) e
nunca o push; a rotina seguinte encontra o livro em dia. Um clone com commits de ensaio nunca
publica (``cdp publicar`` recusa o push fora do ensaio).
"""

from __future__ import annotations

import datetime as _dtmod
import importlib
import os
import pkgutil
import sys
import time as _time
from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

VAR_AGORA = "CDP_AGORA"
VAR_SUBSTITUTO = "CDP_ENSAIO_SUBSTITUTO"
ROTULO = "[ensaio] SUBSTITUTO"
_BRT = ZoneInfo("America/Sao_Paulo")
_REAL_DT = _dtmod.datetime
_REAL_DATE = _dtmod.date
_estado: dict[str, Any] = {}


class ErroEnsaio(ValueError):
    """Variável de ensaio fora do ensaio (ou inválida)."""


def em_ensaio(env: Mapping[str, str] | None = None) -> bool:
    return (os.environ if env is None else env).get("CDP_ENSAIO") == "1"


def instante_do_cenario(texto: str) -> _dtmod.datetime:
    try:
        t = _REAL_DT.fromisoformat(texto.strip())
    except ValueError as exc:
        raise ErroEnsaio(f"{VAR_AGORA} inválido ({texto!r}): use ISO, ex. 2026-10-09T11:07") \
            from exc
    return t.replace(tzinfo=_BRT) if t.tzinfo is None else t


def _agora_utc() -> _dtmod.datetime:
    base, inicio = _estado["agora"], _estado["inicio_real"]
    return (base + _dtmod.timedelta(seconds=_time.time() - inicio)).astimezone(_dtmod.UTC)


class _Proxy(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, cls._real)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, cls._real)

    def __call__(cls, *a, **k):
        return cls._real(*a, **k)

    def __getattr__(cls, name):
        return getattr(cls._real, name)

    def __or__(cls, other):
        return cls._real | other

    def __ror__(cls, other):
        return other | cls._real

    def __repr__(cls):
        return repr(cls._real)


class RelogioDatetime(metaclass=_Proxy):
    """``datetime`` com ``now``/``today``/``utcnow`` no relógio do cenário."""

    _real = _REAL_DT

    @classmethod
    def now(cls, tz=None):
        u = _agora_utc()
        if tz is None:
            return u.astimezone(_BRT).replace(tzinfo=None)
        return u.astimezone(tz)

    @classmethod
    def utcnow(cls):
        return _agora_utc().replace(tzinfo=None)

    @classmethod
    def today(cls):
        return cls.now()


class RelogioDate(metaclass=_Proxy):
    """``date`` com ``today`` no relógio do cenário (data de Brasília)."""

    _real = _REAL_DATE

    @classmethod
    def today(cls):
        return _agora_utc().astimezone(_BRT).date()


def _importar_modulos() -> None:
    import cdp

    for m in pkgutil.walk_packages(cdp.__path__, "cdp."):
        if m.name.startswith("cdp.ui"):
            continue
        try:
            importlib.import_module(m.name)
        except Exception:  # noqa: BLE001 - módulos opcionais (extras não instalados)
            pass


def _trocar_relogio() -> None:
    for nome, mod in list(sys.modules.items()):
        if mod is None or not (nome == "cdp" or nome.startswith("cdp.")):
            continue
        if getattr(mod, "datetime", None) is _REAL_DT:
            mod.datetime = RelogioDatetime
        if getattr(mod, "date", None) is _REAL_DATE:
            mod.date = RelogioDate


#: Série cuja última barra real está a mais que isso (dias corridos) da barra mais recente do
#: lote não é estendida (ativo suspenso ou deslistado continua sem preço, como na base real).
JANELA_SERIE_DIAS = 7


def _redatar(df, fim, *, por_serie: bool = True, janela_dias: int | None = None):
    """Acrescenta, até ``fim`` (dias úteis), cópias da última barra real de cada série.

    ``por_serie``: cada série parte da SUA última barra (ex.: EUA até 05/10 e Brasil até 06/10
    no mesmo lote); ``janela_dias``: só séries com barra real a até essa distância da mais
    recente do lote."""
    import pandas as pd

    if df is None or len(df) == 0 or "date" not in df.columns:
        return df
    datas = pd.to_datetime(df["date"])
    alvo = pd.Timestamp(fim)
    chave = next((c for c in ("ticker", "currency", "symbol", "series") if c in df.columns), None)
    base_df = df if por_serie else df[datas == datas.max()]
    if por_serie and janela_dias is not None and chave is not None:
        ultimas = datas.groupby(df[chave]).transform("max")
        base_df = df[ultimas >= datas.max() - pd.Timedelta(days=janela_dias)]
    grupos = [(None, base_df)] if chave is None else list(base_df.groupby(chave, sort=False))
    partes, n = [df], 0
    for _k, g in grupos:
        dg = pd.to_datetime(g["date"])
        ultima = dg.max()
        if alvo <= ultima:
            continue
        base = g[dg == ultima]
        for t in pd.bdate_range(ultima + pd.Timedelta(days=1), alvo):
            novo = base.copy()
            novo["date"] = t if pd.api.types.is_datetime64_any_dtype(df["date"]) else t.date()
            partes.append(novo)
            n += 1
    if n == 0:
        return df
    print(f"{ROTULO}: {n} barra(s) até {alvo.date()} = cópia da última barra real de cada série "
          "(dados de ensaio, nunca publicados)", file=sys.stderr)
    return pd.concat(partes, ignore_index=True)


def _ligar_substituto() -> None:
    import dataclasses

    from .data import store as st

    if getattr(st.MarketStore, "_cdp_ensaio_substituto", False):
        return
    orig_init = st.MarketStore.__init__

    def init(self, *a, **k):
        orig_init(self, *a, **k)
        f = self.fetchers

        def precos(tickers, start, end, *aa, **kk):
            # Por série: um lote em que os EUA terminam um pregão antes do Brasil não pode
            # deixar as linhas dos EUA sem a barra do cenário ("dados não prontos").
            df, faltando = f.prices(tickers, start, end, *aa, **kk)
            return _redatar(df, end, por_serie=True, janela_dias=JANELA_SERIE_DIAS), faltando

        def simples(fn):
            def g(x, start, end, *aa, **kk):
                return _redatar(fn(x, start, end, *aa, **kk), end)
            return g

        def juros(start, end, *aa, **kk):
            return _redatar(f.rates(start, end, *aa, **kk), end)

        self.fetchers = dataclasses.replace(
            f, prices=precos, fx=simples(f.fx), benchmarks=simples(f.benchmarks),
            lending=simples(f.lending), rates=juros)

    st.MarketStore.__init__ = init
    st.MarketStore._cdp_ensaio_substituto = True


def ativar(env: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    """Liga o relógio do cenário e/ou o substituto de dados (só em ensaio). ``None`` = nada a
    ligar. Variáveis de ensaio fora do ensaio ⇒ :class:`ErroEnsaio`."""
    env = os.environ if env is None else env
    agora_txt = (env.get(VAR_AGORA) or "").strip()
    substituto = env.get(VAR_SUBSTITUTO) == "1"
    if not agora_txt and not substituto:
        return None
    if not em_ensaio(env):
        raise ErroEnsaio(f"{VAR_AGORA} e {VAR_SUBSTITUTO} só valem em ensaio (CDP_ENSAIO=1): "
                         "fora dele, o relógio e os dados são sempre os reais.")
    info: dict[str, Any] = {"ensaio": True}
    if agora_txt:
        if "agora" not in _estado:
            _estado.update({"agora": instante_do_cenario(agora_txt),
                            "inicio_real": _time.time()})
            _importar_modulos()
            _trocar_relogio()
        info["relogio"] = _agora_utc().astimezone(_BRT).isoformat(timespec="seconds")
    if substituto:
        _ligar_substituto()
        info["substituto_de_dados"] = True
    print(f"[ensaio] relógio do cenário: {info.get('relogio', 'real')}; substituto de dados: "
          f"{'ligado' if substituto else 'desligado'}", file=sys.stderr)
    return info
