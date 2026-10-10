"""Custódia prospectiva de células Yahoo/mercado; não prova publicação ou PIT.

O contexto vivo nasce no leitor físico nativo. Envelopes JSON são evidência transportada,
nunca substituem os arquivos, a linha do índice ou a recepção própria original.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import sys
import threading
import types
import weakref
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd

SCHEMA = "cdp.recepcao_bancaria/v1"
CAMPOS = ("recepcao_bancaria", "data_publicacao_estimada", "recepcao_fisica_utc")
VERSAO_MANIFESTO = "cdp.disponibilidade_participantes/v4"
IID = "AR_GALICIA"
DOMESTICA, ADR = "GGAL.BA", "GGAL"
_CUSTODIA = weakref.WeakKeyDictionary()


def _estado(ctx):
    if type(ctx) is not ContextoBancario or ctx not in _CUSTODIA:
        raise ValueError("Recepção bancária: contexto não emitido pelo leitor nativo")
    return _CUSTODIA[ctx]


def instante(value):
    """Instante explícito com fuso; data civil não fornece uma hora conhecida."""
    if not isinstance(value, (datetime, str)):
        raise ValueError("Recepção bancária exige corte UTC explícito")
    value = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Recepção bancária exige instante com fuso")
    return value.astimezone(UTC)


def opcao(value):
    if type(value) is not bool:
        raise ValueError("recepcao_bancaria exige bool explícito")
    return value


def data_civil(value):
    from .publico_arquivo import data_local
    return data_local(instante(value)).isoformat()


def texto(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    def pares(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise ValueError("Recepção bancária: chave JSON duplicada")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pares)


def _arquivo(root, relative):
    root = Path(root).absolute()
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or any(p in (".", "..") for p in rel.parts):
        raise ValueError("Recepção bancária: membro fora da raiz física")
    path = root / rel
    def identity(s):
        return (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
    def owned(parent):
        return parent == root or root in parent.parents
    def namespace_identity(parent, value):
        return value if owned(parent) else (value[0], value[1], value[2])
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("Recepção bancária: runtime sem custódia FD/O_NOFOLLOW")
    descriptors, parents = [], []
    try:
        current = Path(path.anchor)
        fd = os.open(current, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        for part in path.parts[1:-1]:
            current /= part
            before = current.lstat()
            if not stat.S_ISDIR(before.st_mode):
                raise ValueError("Recepção bancária: pai/raiz não é diretório físico")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(child)
            if namespace_identity(current, identity(os.fstat(child))) != namespace_identity(current, identity(before)):
                raise ValueError(f"Recepção bancária: pai/raiz mudou durante openat: {current}")
            parents.append((current, child, identity(before)))
            fd = child
        before = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("Recepção bancária: membro não regular ou compartilhado")
        member = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        descriptors.append(member)
        if identity(os.fstat(member)) != identity(before):
            raise ValueError("Recepção bancária: membro mudou entre stat e openat")
        chunks = []
        while chunk := os.read(member, 1024 * 1024):
            chunks.append(chunk)
        raw = b"".join(chunks)
        after = os.fstat(member)
        if identity(before) != identity(after) or identity(path.lstat()) != identity(after) or len(raw) != after.st_size:
            raise ValueError("Recepção bancária: membro mudou durante a leitura por FD")
        namespace = []
        for parent, descriptor, original in parents:
            fd_after, path_after = identity(os.fstat(descriptor)), identity(parent.lstat())
            if (namespace_identity(parent, fd_after) != namespace_identity(parent, original)
                    or namespace_identity(parent, path_after) != namespace_identity(parent, original)):
                raise ValueError(f"Recepção bancária: pai/raiz mudou durante recepção por FD: {parent}")
            row = {"path": str(parent), "dev": original[0], "inode": original[1], "mode": original[2]}
            if owned(parent):
                row.update(bytes=original[3], mtime_ns=original[4], ctime_ns=original[5], nlink=original[6])
            else:
                row["nlink_observado"] = {"antes": original[6], "depois_fd": fd_after[6], "depois_caminho": path_after[6]}
            namespace.append(row)
    except OSError as exc:
        raise ValueError("Recepção bancária: custódia FD recusou membro/pai/raiz") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    receipt = {"root": str(root), "path": rel.as_posix(), "sha256": _sha(raw), "bytes": len(raw),
               "dev": after.st_dev, "inode": after.st_ino, "mode": after.st_mode,
               "mtime_ns": after.st_mtime_ns, "ctime_ns": after.st_ctime_ns, "nlink": after.st_nlink}
    receipt["namespace"] = namespace
    return raw, receipt


def _custodia_recibo(receipt):
    """Só o número observado de links de ancestrais alheios pode variar."""
    out = deepcopy(receipt)
    root = Path(out["root"])
    for row in out["namespace"]:
        parent = Path(row["path"])
        if parent != root and root not in parent.parents:
            row.pop("nlink_observado", None)
    return out


def _valor(value):
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Recepção bancária: célula ausente ou não finita")
    return value


_QUADROS = ("close", "adj_close", "volume", "fx", "fundamentals", "short_interest", "lending", "benchmarks", "rates")


def _vista(md):
    return {"ref": weakref.ref(md), "manifest": md.manifest.model_dump_json(),
            "quadros": {name: getattr(md, name).copy(deep=True) for name in _QUADROS},
            "news": tuple(n.model_dump_json() for n in md.news)}


def _igual_quadro(current, original):
    if type(current) is not pd.DataFrame:
        return False
    try:
        pd.testing.assert_frame_equal(current, original, check_exact=True)
        return (texto(current.attrs) == texto(original.attrs)
                and type(current.index) is type(original.index))
    except (AssertionError, TypeError, ValueError):
        return False


class ContextoBancario:
    """Capability em memória; não pode ser instanciada de um catálogo/DTO."""

    __slots__ = ("__weakref__",)

    def __new__(cls, *args, **kwargs):
        raise TypeError("Contexto bancário nasce exclusivamente no MarketStore.load nativo")

    def __deepcopy__(self, memo):
        return self  # attrs/copias de quadros não duplicam o recibo físico original.

    def _fixar(self, root, relative, expected=None):
        raw, receipt = _arquivo(root, relative)
        if expected is not None and receipt["sha256"] != expected:
            raise ValueError("Recepção bancária: SHA diverge do manifesto/índice original")
        key = (receipt["root"], receipt["path"])
        old = _estado(self)["files"].get(key)
        if old is not None and _custodia_recibo(old) != _custodia_recibo(receipt):
            raise ValueError("Recepção bancária: readset original alterado")
        _estado(self)["files"][key] = receipt if old is None else old
        return raw, deepcopy(_estado(self)["files"][key])

    def revalidar(self):
        for old in tuple(_estado(self)["files"].values()):
            _, current = _arquivo(old["root"], old["path"])
            if _custodia_recibo(current) != _custodia_recibo(old):
                raise ValueError("Recepção bancária: custódia física original alterada")
        return self

    def autenticar(self, md=None, universe=None):
        from ..market import MarketData
        if md is not None and (type(md) is not MarketData or not any(md is x["ref"]() for x in _estado(self)["views"])):
            raise ValueError("Recepção bancária: MarketData não recebido pelo leitor nativo")
        if universe is not None and universe is not _estado(self)["universe"]:
            raise ValueError("Recepção bancária: Universe livre não autentica a linha")
        if (not _igual_quadro(_estado(self)["universe"].lines, _estado(self)["lines"])
                or not _igual_quadro(_estado(self)["universe"].issuers, _estado(self)["issuers"])
                or _estado(self)["universe"].source_sha256 != _estado(self)["universe_sha256"]):
            raise ValueError("Recepção bancária: universo recebido foi adulterado")
        for view in _estado(self)["views"]:
            current = view["ref"]()
            if current is None:
                continue
            if (current.universe is not _estado(self)["universe"]
                    or current.manifest.model_dump_json() != view["manifest"]
                    or tuple(n.model_dump_json() for n in current.news) != view["news"]
                    or any(not _igual_quadro(getattr(current, name), table)
                           for name, table in view["quadros"].items())):
                raise ValueError("Recepção bancária: manifesto/quadros da view nativa adulterados")
        self.revalidar()
        return self

    def readset(self):
        self.revalidar()
        return deepcopy(sorted(_estado(self)["files"].values(), key=lambda x: (x["root"], x["path"])))

    def _registrar(self, body, received, captures):
        caller = sys._getframe(1).f_code
        producers = [c for c in _novo_mercado.__code__.co_consts
                     if type(c) is types.CodeType and c.co_name == "envelope"]
        if caller is not anotar_yahoo.__code__ and caller not in producers:
            raise ValueError("Recepção bancária: recibo exige produtor físico nativo")
        body = {**body, "schema": SCHEMA, "capturas_declaradas": captures,
                "recepcao_fisica_utc": received.isoformat(),
                "disponivel_desde": max(received, *(instante(x) for x in captures)).isoformat(),
                "data_publicacao_primaria": None, "point_in_time": False}
        encoded = texto(body)
        digest = _sha(encoded.encode())
        _estado(self)["envelopes"][digest] = encoded
        return texto({"sha256": digest, "envelope": body})

    def mercado(self, md, ticker, item, *, period_end):
        """Resolve a célula escolhida pelo consumidor, nunca a captura global composta."""
        self.autenticar(md)
        if ticker != ADR:
            return None
        if item == "market_cap":
            key = ("fundamentals", ticker, "market_cap")
            current = md.fundamentals.loc[ticker, "market_cap"]
        elif item == "preco":
            key = ("prices", ticker, date.fromisoformat(str(period_end)[:10]).isoformat())
            current = md.close.loc[pd.Timestamp(period_end), ticker]
        else:
            raise ValueError("Recepção bancária: célula fora do recorte autorizado")
        encoded = _estado(self)["market"].get(key)
        if encoded is None:
            return None  # Ausência não recebe um relógio ou zero.
        self.conferir(encoded)
        envelope = _json(encoded)["envelope"]
        if _valor(current) != envelope["valor_original"]:
            raise ValueError("Recepção bancária: célula do MarketData foi adulterada")
        return encoded

    def conferir(self, encoded, *, conhecimento_ate=None):
        self.autenticar()
        self.revalidar()
        if not isinstance(encoded, str):
            raise ValueError("Recepção bancária: envelope literal ausente")
        wrapped = _json(encoded)
        body = texto(wrapped["envelope"])
        digest = _sha(body.encode())
        if wrapped.get("sha256") != digest or _estado(self)["envelopes"].get(digest) != body:
            raise ValueError("Recepção bancária: envelope não recebido ou alterado")
        if conhecimento_ate is not None and instante(wrapped["envelope"]["disponivel_desde"]) > instante(conhecimento_ate):
            raise ValueError("Recepção bancária: recepção real posterior ao corte")
        return deepcopy(wrapped["envelope"])

    def vincular(self, row, member):
        """Binding do grão original; nunca do destino convertido/calculado."""
        from ..cobertura.disponibilidade_demonstrativos import RegistroParticipantes
        if sys._getframe(1).f_code is not RegistroParticipantes.registrar.__code__:
            raise ValueError("Recepção bancária: binding exige registro nativo")
        encoded = member.get("recepcao_bancaria")
        env = self.conferir(encoded)
        source = member["fonte"]
        if (_valor(row.get("value")) != env["valor_original"] or row.get("currency") != env["currency"]
                or member.get("issuer_id") != IID or member.get("origem") != env["origem"]
                or source.get("fonte") != "YAHOO" or source.get("recepcao_bancaria") != encoded
                or source.get("disponivel_desde") != env["disponivel_desde"]):
            raise ValueError("Recepção bancária: valor/moeda/identidade/fonte divergem do grão original")
        if env["origem"] == "demonstrativos":
            from ..cobertura.insumos import documento_proveniencia
            record = env["registros"][0]["registro"]
            allowed = ("A", "Q") if env["freq_produto"] == "A" else ("Q",)
            raw_document = f"Yahoo Finance {env['table']}: {env['rubrica']}"
            expected = {"url": env["url_fato"], "documento": documento_proveniencia({
                        "documento": raw_document, "demonstrativo": "BP", "freq": member.get("freq"),
                        "period_end": env["period_end"], "consolidado": True}),
                        "sha256": record["sha256"], "data_publicacao": None}
            if (member.get("item") != "acoes_em_circulacao" or member.get("freq") not in allowed
                    or row.get("documento") != raw_document or row.get("demonstrativo") != "BP"
                    or not bool(row.get("consolidado"))
                    or str(member.get("period_end"))[:10] != env["period_end"]
                    or member.get("data_publicacao_estimada") != env["data_publicacao_estimada"]
                    or member.get("entidade") != f"YAHOO:{DOMESTICA}"
                    or member.get("recepcao_fisica_utc") != env["recepcao_fisica_utc"]
                    or source.get("recepcao_fisica_utc") != env["recepcao_fisica_utc"]
                    or source.get("data_estimada") is not True
                    or source.get("data_recebimento_documento") != data_civil(env["recepcao_fisica_utc"])
                    or pd.Timestamp(source.get("received_date")).date().isoformat() != env["data_publicacao_estimada"]
                    or any(source.get(k) != v for k, v in expected.items())
                    or instante(source.get("data_coleta")) != instante(record["data_coleta"])):
                raise ValueError("Recepção bancária: frequência/locator/fonte Yahoo divergem")
        else:
            if member.get("item") not in {"market_cap", "preco"}:
                raise ValueError("Recepção bancária: item mercado fora do recorte autorizado")
            field = "market_cap" if member.get("item") == "market_cap" else "close"
            freq = "SNAPSHOT" if field == "market_cap" else "D"
            period = env["periodo_visao"] if field == "market_cap" else env["period_end"]
            document = "valor de mercado público ÷ fechamento" if field == "market_cap" else "fechamento oficial (base de mercado do fundo)"
            views = [v["ref"]() for v in _estado(self)["views"] if v["ref"]() is not None]
            hashes = {v.manifest.content_hash() for v in views}
            dates = {v.close[ADR].dropna().index[-1].date().isoformat() for v in views if not v.close[ADR].dropna().empty}
            if (env["ticker"] != ADR or env["field"] != field or member.get("freq") != freq
                    or str(member.get("period_end"))[:10] != period
                    or source.get("url") != f"https://finance.yahoo.com/quote/{ADR}"
                    or source.get("documento") != document or source.get("sha256") not in hashes
                    or source.get("data_publicacao") not in dates or source.get("data_coleta") is not None):
                raise ValueError("Recepção bancária: frequência/locator/fonte mercado divergem")
        binding = {"issuer_id": IID, "origem": member["origem"], "uso": member["uso"],
                   "item": member["item"], "freq": member["freq"], "period_end": member["period_end"],
                   "entidade": member.get("entidade"),
                   "valor": env["valor_original"], "currency": env["currency"],
                   "recepcao_bancaria": encoded, "fonte": deepcopy(source)}
        binding["grao_original"] = {k: deepcopy(env[k]) for k in
            ("ticker", "table", "period_end", "field", "rubrica", "ordinal", "freq_produto",
             "registros", "member", "manifest", "source_record") if k in env}
        literal = texto(binding)
        _estado(self)["bindings"][_sha(literal.encode())] = literal
        return {"valor": env["valor_original"], "currency": env["currency"],
                "grao_original": deepcopy(binding["grao_original"]),
                "vinculo_recepcao_bancaria": literal}

    def validar_vinculo(self, member):
        literal = member.get("vinculo_recepcao_bancaria")
        if not isinstance(literal, str) or _estado(self)["bindings"].get(_sha(literal.encode())) != literal:
            raise ValueError("Recepção bancária: binding original não recebido")
        binding = _json(literal)
        if any(member.get(k) != value for k, value in binding.items()):
            raise ValueError("Recepção bancária: grão/fonte/valor/moeda do participante alterados")
        return binding


def autenticar(contexto, md=None, universe=None):
    if type(contexto) is not ContextoBancario:
        raise ValueError("Recepção bancária: contexto físico nativo obrigatório")
    return contexto.autenticar(md, universe)


def _novo_mercado(md, store, base, bt, tabs):
    import pyarrow.parquet as pq

    from ..universe import universe_from_frame
    from .snapshot import (
        DATETIME_DTYPE,
        FILE_FUNDAMENTALS,
        FILE_MANIFEST,
        FILE_PRICES,
        FILE_UNIVERSE,
        _long_to_indexed,
        normalize_prices,
    )
    from .store import MarketStore
    if type(store) is not MarketStore or sys._getframe(1).f_code is not MarketStore.load.__code__:
        raise ValueError("Recepção bancária: origem deve ser MarketStore.load integral nativo")
    ctx = object.__new__(ContextoBancario)
    _CUSTODIA[ctx] = {"files": {}, "envelopes": {}, "market": {}, "yahoo": {}, "bindings": {},
                      "views": [_vista(md)], "universe": md.universe, "lock": threading.RLock()}
    _estado(ctx)["lines"] = md.universe.lines.copy(deep=True)
    _estado(ctx)["issuers"] = md.universe.issuers.copy(deep=True)
    _estado(ctx)["universe_sha256"] = md.universe.source_sha256
    root = store.root.absolute()
    members = [(base, bt.manifest, bt.prices, bt.fundamentals)]
    members += [(t.increment.path, t.increment.manifest, t.prices, t.fundamentals) for t in tabs]
    selected_fund = None
    bars = {}
    for directory, manifest, prices, fundamentals in members:
        prefix = directory.absolute().relative_to(root)
        raw, mr = ctx._fixar(root, prefix / FILE_MANIFEST)
        _json(raw)
        if type(manifest).model_validate_json(raw).model_dump(mode="json") != manifest.model_dump(mode="json"):
            raise ValueError("Recepção bancária: manifesto físico difere do recebido")
        receipts, bodies = {}, {}
        for f in manifest.files:
            bodies[f.path], receipts[f.path] = ctx._fixar(root, prefix / f.path, f.sha256)
        def parquet(name, bodies=bodies):
            frame = pq.read_table(BytesIO(bodies[name])).to_pandas()
            if "date" in frame.columns:
                frame["date"] = pd.to_datetime(frame["date"]).astype(DATETIME_DTYPE)
            return frame
        physical_prices = normalize_prices(parquet(FILE_PRICES))
        if not _igual_quadro(prices, physical_prices):
            raise ValueError("Recepção bancária: preços do leitor divergem dos bytes FD")
        prices = physical_prices
        if fundamentals is not None and FILE_FUNDAMENTALS in bodies:
            physical_fund = _long_to_indexed(parquet(FILE_FUNDAMENTALS))
            if not _igual_quadro(fundamentals, physical_fund):
                raise ValueError("Recepção bancária: fundamentos do leitor divergem dos bytes FD")
            fundamentals = physical_fund
            selected_fund = (fundamentals, manifest, mr, receipts[FILE_FUNDAMENTALS])
        if directory == base:
            universe = universe_from_frame(pd.read_csv(BytesIO(bodies[FILE_UNIVERSE]),
                dtype={"adr_ratio": "string"}, keep_default_na=False, na_values=[""]),
                source_sha256=receipts[FILE_UNIVERSE]["sha256"])
            if (not _igual_quadro(md.universe.lines, universe.lines)
                    or not _igual_quadro(md.universe.issuers, universe.issuers)
                    or md.universe.source_sha256 != universe.source_sha256):
                raise ValueError("Recepção bancária: universo do leitor diverge dos bytes FD")
        for row in prices.itertuples(index=False):
            if str(row.ticker) != ADR:
                continue
            d = pd.Timestamp(row.date).date()
            if d <= md.as_of:
                key = ("prices", str(row.ticker), d.isoformat())
                if key in bars:
                    raise ValueError("Recepção bancária: barra física duplicada")
                bars[key] = (row.close, manifest, mr, receipts[FILE_PRICES])
    # Recepção própria: depois de TODOS os membros integrais e recheck, não _now caller.
    ctx.revalidar()
    received = datetime.now(UTC)

    def envelope(table, ticker, field, period, value, manifest, mr, receipt, currency=None):
        source_id = "yahoo_fundamentals" if field == "market_cap" else "yahoo_prices"
        sources = [s for s in manifest.sources if s.source_id == source_id]
        if len(sources) != 1:
            return None  # Captura por célula indeterminada não vira created_at global.
        try:
            value = _valor(value)
        except ValueError:
            return None
        source = sources[0]
        quote_currency = str(md.universe.lines.loc[ticker, "currency"])
        if field == "market_cap" and currency != quote_currency:
            return None  # Moeda do quadro físico ausente/divergente continua lacuna.
        capture = source.retrieved_at.astimezone(UTC)
        precision = "microseconds" if capture.microsecond else "seconds"
        upper = capture if capture.microsecond else capture + timedelta(seconds=1)
        return ctx._registrar({"origem": "mercado", "ticker": ticker, "table": table,
            "field": field, "period_end": period, "valor_original": value,
            "currency": quote_currency,
            "periodo_visao": md.as_of.isoformat(),
            "manifest": mr, "member": receipt, "source_record": _json(source.model_dump_json()),
            "precisao_captura_declarada": precision,
            "universe_sha256": md.universe.source_sha256,
            "limite": "parquet normalizado; raw marketCap não arquivado" if field == "market_cap"
                      else "barra close original; não adj_close derivado"},
            received, [upper.isoformat()])

    if selected_fund is not None:
        fund, manifest, mr, receipt = selected_fund
        for ticker in fund.index:
            if str(ticker) != ADR:
                continue
            if "market_cap" in fund:
                encoded = envelope("fundamentals", str(ticker), "market_cap", manifest.as_of.isoformat()
                                   if hasattr(manifest, "as_of") else manifest.session_date.isoformat(),
                                   fund.loc[ticker, "market_cap"], manifest, mr, receipt,
                                   currency=fund.loc[ticker, "currency"] if "currency" in fund else None)
                if encoded is not None:
                    _estado(ctx)["market"][("fundamentals", str(ticker), "market_cap")] = encoded
    for key, (value, manifest, mr, receipt) in bars.items():
        encoded = envelope("prices", key[1], "close", key[2], value, manifest, mr, receipt)
        if encoded is not None:
            _estado(ctx)["market"][key] = encoded
    return ctx


def transferir(contexto, parent, child):
    from ..market import MarketData
    if sys._getframe(1).f_code is not MarketData.truncate.__code__:
        raise ValueError("Recepção bancária: transferência exige truncate nativo")
    autenticar(contexto, parent)
    _estado(contexto)["views"].append(_vista(child))
    return contexto


def anotar_yahoo(fatos, *, arquivo, registro, info, ticker, issuer_id, universe, contexto, conhecimento_ate,
                 as_of=None):
    """Recebe e localiza BP Ordinary Shares Number; não calcula nenhum demonstrativo."""
    from .publico_arquivo import Arquivo, RegistroArquivo, data_local
    from .publico_yahoo import DEFASAGEM_DIAS
    ctx = autenticar(contexto, universe=universe)
    cutoff = instante(conhecimento_ate)
    as_of = data_local(cutoff) if as_of is None else as_of
    if type(as_of) is not date:
        raise ValueError("Recepção bancária: seleção Yahoo exige data civil explícita")
    if issuer_id != IID or ticker != DOMESTICA:
        return fatos
    if type(arquivo) is not Arquivo or type(registro) is not RegistroArquivo:
        raise ValueError("Recepção bancária: arquivo/registro nativo obrigatório")
    if info is None or type(info) is not RegistroArquivo:
        return fatos  # Moeda/dependência indisponível não recebe envelope.
    if ticker not in universe.lines.index or str(universe.lines.loc[ticker, "issuer_id"]) != issuer_id:
        raise ValueError("Recepção bancária: ticker/IID divergem do universo físico")
    expected_keys = (f"YAHOO/demonstracoes/{ticker}.json", f"YAHOO/info/{ticker}.json")
    if (registro.chave, info.chave) != expected_keys:
        raise ValueError("Recepção bancária: chave Yahoo/ticker/parte divergente")
    with _estado(ctx)["lock"]:
        raw_index, index_receipt = ctx._fixar(arquivo.base, "indice.jsonl")
        # O leitor nativo ignora a cauda não terminada em newline; o recibo fixa
        # esses bytes também, sem tratá-los como coleta persistida.
        physical = raw_index.decode("utf-8").split("\n")[:-1]
        rows = [(n, _json(line)) for n, line in enumerate(physical, 1) if line.strip()]
        selected = []
        for reg in (registro, info):
            candidates = []
            for position, row in rows:
                if row.get("chave") != reg.chave:
                    continue
                instante(row["data_coleta"])  # não aceita coerção nativa legada de naive para UTC.
                native = RegistroArquivo.de_dict(row)
                if native.limite_captura <= cutoff and data_local(native.data_coleta) <= as_of:
                    candidates.append((position, native))
            candidates.sort(key=lambda x: (x[1].data_coleta, x[1].caminho))
            if not candidates or candidates[-1][1] != reg:
                raise ValueError("Recepção bancária: registro não é a coleta escolhida no índice")
            if sum(candidate == reg for _, candidate in candidates) != 1:
                raise ValueError("Recepção bancária: coleta indistinguível duplicada no índice")
            raw, receipt = ctx._fixar(arquivo.base, reg.caminho, reg.sha256)
            if len(raw) != reg.bytes:
                raise ValueError("Recepção bancária: tamanho do raw diverge do índice")
            selected.append((_json(raw), receipt, candidates[-1][0], reg))
        dem, info_doc = selected[0][0], selected[1][0]
        if dem.get("ticker") != ticker or info_doc.get("ticker") != ticker:
            raise ValueError("Recepção bancária: ticker raw divergente")
        currency = info_doc.get("info", {}).get("financialCurrency")
        if not currency:
            return fatos
        ctx.revalidar()
        cache_key = texto([registro.como_dict(), info.como_dict(), index_receipt])
        received = _estado(ctx)["yahoo"].setdefault(cache_key, datetime.now(UTC))
        out = fatos.copy(deep=True)
        for i, row in out.iterrows():
            if row.get("item") != "acoes_em_circulacao" or row.get("demonstrativo") != "BP":
                continue
            document = str(row.get("documento"))
            table = next((t for t in ("balance_sheet", "quarterly_balance_sheet")
                          if document == f"Yahoo Finance {t}: Ordinary Shares Number"), None)
            if table is None:
                continue
            frame = dem.get("demonstracoes", {}).get(table, {})
            columns, values = frame.get("colunas", []), frame.get("linhas", {}).get("Ordinary Shares Number", [])
            period = pd.Timestamp(row["period_end"]).date().isoformat()
            ordinals = [n for n, c in enumerate(columns) if pd.Timestamp(c).date().isoformat() == period]
            if len(ordinals) != 1 or len(values) != len(columns):
                raise ValueError("Recepção bancária: locator de ações ambíguo/incompleto")
            ordinal = ordinals[0]
            original = _valor(values[ordinal])
            if _valor(row["value"]) != original or row.get("currency") != currency:
                raise ValueError("Recepção bancária: valor/moeda difere do raw selecionado")
            freq = "A" if table == "balance_sheet" else "Q"
            estimate = min(date.fromisoformat(period) + timedelta(days=DEFASAGEM_DIAS[freq]),
                           data_local(registro.data_coleta)).isoformat()
            if (pd.Timestamp(row["received_date"]).date().isoformat() != estimate
                    or row.get("entidade") != f"YAHOO:{ticker}" or row.get("fonte") != "YAHOO"
                    or row.get("sha256") != registro.sha256 or not bool(row.get("pit_estimado"))):
                raise ValueError("Recepção bancária: fato/estimativa não corresponde ao produtor Yahoo")
            body = {"origem": "demonstrativos", "ticker": ticker, "issuer_id": issuer_id,
                "table": table, "rubrica": "Ordinary Shares Number", "ordinal": ordinal,
                "url_fato": f"https://finance.yahoo.com/quote/{ticker}/financials",
                "period_end": period, "valor_original": original, "currency": currency,
                "freq_produto": freq,
                "selecao_as_of": as_of.isoformat(),
                "data_publicacao_estimada": estimate, "pit_estimado": True,
                "indice": index_receipt, "registros": [
                    {"linha": position, "registro": reg.como_dict(), "member": receipt}
                    for _, receipt, position, reg in selected],
                "universe_sha256": universe.source_sha256}
            encoded = ctx._registrar(body, received, [reg.limite_captura.isoformat() for reg in (registro, info)])
            env = _json(encoded)["envelope"]
            out.loc[i, "recepcao_bancaria"] = encoded
            out.loc[i, "data_publicacao_estimada"] = estimate
            out.loc[i, "data_publicacao_primaria"] = None
            out.loc[i, "disponibilidade_tipo"] = "recepcao_observada"
            out.loc[i, "disponivel_desde"] = env["disponivel_desde"]
            out.loc[i, "data_recebimento_documento"] = data_local(received).isoformat()
            out.loc[i, "recepcao_fisica_utc"] = received.isoformat()
        out.attrs["contexto_bancario"] = ctx
        return out


def conferir_participantes(pac, contexto):
    """Autentica somente o recorte v4; outras lacunas continuam sob o gate existente."""
    ctx = autenticar(contexto)
    manifest = pac["manifesto_disponibilidade"]
    if manifest.get("readset_bancario") != ctx.readset():
        raise ValueError("Recepção bancária: readset do manifesto diverge da custódia")
    cutoff = pac["corte_temporal"]["conhecimento_ate"]
    for row in pac["disponibilidade_demonstrativos"]:
        if (row.get("issuer_id") == IID and row.get("origem") == "mercado"
                and row.get("item") not in {"market_cap", "preco"}):
            raise ValueError("Recepção bancária: item mercado fora do recorte autorizado")
        required = row.get("issuer_id") == IID and (
            row.get("origem") == "mercado" and row.get("item") in ("market_cap", "preco")
            or row.get("origem") == "demonstrativos" and row.get("item") == "acoes_em_circulacao"
            and str(row.get("fonte", {}).get("fonte")) == "YAHOO")
        encoded = row.get("recepcao_bancaria")
        source = row.get("fonte")
        marked = ("vinculo_recepcao_bancaria" in row or "grao_original" in row
                  or isinstance(source, Mapping) and "recepcao_bancaria" in source)
        if encoded is None and (required or marked):
            raise ValueError("Recepção bancária: envelope superior ausente em participante do recorte")
        if encoded is None:
            continue
        env = ctx.conferir(encoded, conhecimento_ate=cutoff)
        if env["origem"] == "mercado" and row.get("item") not in {"market_cap", "preco"}:
            raise ValueError("Recepção bancária: item mercado fora do recorte autorizado")
        ctx.validar_vinculo(row)
        if row.get("origem") != env["origem"] or row.get("disponivel_desde") != env["disponivel_desde"]:
            raise ValueError("Recepção bancária: origem/disponibilidade do participante diverge")
        if row["origem"] == "demonstrativos":
            if (row.get("issuer_id") != env["issuer_id"] or row.get("item") != "acoes_em_circulacao"
                    or str(row.get("period_end"))[:10] != env["period_end"]
                    or row.get("data_publicacao_estimada") != env["data_publicacao_estimada"]):
                raise ValueError("Recepção bancária: saldo/estimativa diverge do locator Yahoo")
        else:
            field = "market_cap" if row.get("item") == "market_cap" else "close"
            period = env["periodo_visao"] if field == "market_cap" else env["period_end"]
            if env["ticker"] != ADR or env["field"] != field or str(row.get("period_end"))[:10] != period:
                raise ValueError("Recepção bancária: célula mercado diverge do locator")
        if row.get("fonte", {}).get("recepcao_bancaria") != encoded:
            raise ValueError("Recepção bancária: fonte do participante perdeu o envelope")
    return ctx
