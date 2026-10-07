"""RI privado: captura observada não é publicação. Sem normalizador legado.

O manifesto de confiança é fornecido por uma custódia já conferida; hashes
detectam mudanças posteriores, não autenticam por si o relógio do coletor.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from pypdf import PdfReader

POLICY = "captura_observada"
NUMBER = r"(?:\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\)?|[-—])"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def instant(value: str | datetime) -> datetime:
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("instante sem fuso explícito")
    return value.astimezone(UTC)


def normalize(text: str) -> str:
    return " ".join(text.split())


def money(text: str) -> Decimal | None:
    if text in {"-", "—"}:
        return None
    if not re.fullmatch(NUMBER, text):
        raise ValueError("lexema monetário inválido")
    value = text.replace(",", "")
    return -Decimal(value[1:-1]) if value.startswith("(") else Decimal(value)


def closed_upper_bound(end: date) -> datetime:
    """Limite conservador; não é timestamp fiscal observado.

    Dia seguinte 00:00 UTC +24h cobre qualquer offset datetime de módulo <24h.
    Não deduz fuso fiscal por moeda, país, captura ou publicação.
    """
    if type(end) is not date:
        raise ValueError("fim de competência exige data civil válida")
    return datetime.combine(end + timedelta(days=2), datetime.min.time(), UTC)


@dataclass(frozen=True)
class Capture:
    url: str
    payload: bytes
    receipt_sha256: str
    payload_sha256: str
    started: datetime
    completed: datetime


class ReceiptVault:
    """Só reabre bytes/recibos referidos pelo manifesto externo selado.

    expected_manifest_sha é a âncora fornecida pelo auditor, não um SHA inferido
    de um recibo que o próprio fato acabou de apresentar.
    """
    def __init__(self, manifest_bytes: bytes, expected_manifest_sha: str):
        if sha(manifest_bytes) != expected_manifest_sha:
            raise ValueError("manifesto de custódia diferente da âncora")
        self.manifest_sha256 = expected_manifest_sha
        self.manifest = json.loads(manifest_bytes)
        if self.manifest.get("schema") != "cdp.ri.custodia_privada/v1":
            raise ValueError("schema de custódia desconhecido")
        if not self.manifest.get("origem_confianca"):
            raise ValueError("origem da confiança do recibo ausente")

    def read(self, name: str) -> Capture:
        entry = self.manifest["entradas"][name]
        raw_receipt = Path(entry["recibo"]).read_bytes()
        raw = Path(entry["bruto"]).read_bytes()
        if sha(raw_receipt) != entry["sha256_recibo"] or sha(raw) != entry["sha256_bruto"]:
            raise ValueError("bytes ou recibo diferentes da custódia selada")
        receipt = json.loads(raw_receipt)
        if (receipt.get("status") != 200 or receipt.get("sha256") != sha(raw)
                or receipt.get("url") != entry["url"]):
            raise ValueError("status, URL ou SHA do recibo não vincula os bytes")
        if urlparse(receipt["url"]).scheme != "https":
            raise ValueError("URL pública HTTPS exigida")
        start, end = (instant(receipt[k]) for k in ("coleta_inicio", "coleta_fim"))
        if end < start:
            raise ValueError("captura invertida")
        if entry.get("tipo") == "pdf" and receipt.get("content_type", "").split(";", 1)[0] != "application/pdf":
            raise ValueError("recibo não identifica PDF")
        return Capture(receipt["url"], raw, sha(raw_receipt), sha(raw), start, end)


@dataclass(frozen=True)
class Column:
    label: str
    end: date


@dataclass(frozen=True)
class Item:
    name: str
    label: str


@dataclass(frozen=True)
class Document:
    issuer_id: str
    entity: str
    currency: str
    period_start: date
    period_end: date
    pages_context: tuple[int, ...]
    page_metadata: int
    page_table: int
    page_count: int
    columns: tuple[Column, ...]
    items: tuple[Item, ...]
    identity: tuple[str, tuple[str, ...]]
    listing_title: str
    expected_scale: Decimal = Decimal(1)
    policy: str = POLICY

    def validate(self):
        if self.policy != POLICY:
            raise ValueError("contrato opt-in captura_observada não selecionado")
        if not self.issuer_id or not self.entity or not re.fullmatch("[A-Z]{3}", self.currency):
            raise ValueError("entidade/moeda ausente")
        if type(self.period_start) is not date or type(self.period_end) is not date or self.period_start > self.period_end:
            raise ValueError("competência inválida/invertida")
        if not self.columns or len({x.end for x in self.columns}) != len(self.columns):
            raise ValueError("colunas ausentes/repetidas")
        if any(type(c.end) is not date for c in self.columns):
            raise ValueError("data da coluna inválida")
        if any(c.end > self.period_end for c in self.columns):
            raise ValueError("coluna posterior à competência do documento")
        if len({x.name for x in self.items}) != len(self.items) or len({x.label for x in self.items}) != len(self.items):
            raise ValueError("itens repetidos")
        names = {x.name for x in self.items}
        if self.identity[0] not in names or not set(self.identity[1]) <= names:
            raise ValueError("identidade fora dos itens extraídos")


@dataclass(frozen=True)
class StockFact:
    issuer_id: str
    item: str
    value: Decimal | None
    period_end: date
    currency: str
    base: str
    scale: Decimal
    rounding_quantum: Decimal
    raw: str
    locator: str
    pdf_sha256: str
    receipt_sha256: str
    custody_manifest_sha256: str
    url: str
    data_publicacao: None
    received_date: None
    disponivel_desde: datetime
    data_coleta: datetime
    modo_disponibilidade: str
    fuso_fiscal: None
    limite_conservador_encerramento: datetime


@dataclass(frozen=True)
class Identity:
    period_end: date
    complete: bool
    residual: Decimal | None


@dataclass(frozen=True)
class Result:
    state: str
    facts: tuple[StockFact, ...]
    reasons: tuple[str, ...]
    publication: None
    received_date: None
    available_since: datetime | None
    custody_manifest_sha256: str
    pdf_sha256: str | None
    legacy_eligible: bool = False
    identities: tuple[Identity, ...] = ()


def extract(vault: ReceiptVault, doc: Document, *, cutoff: datetime) -> Result:
    """Seleciona somente com corte explícito e reextrai todos os fatos dos bytes.

    Falta temporal retorna visão vazia; adulteração/estrutura divergente é erro.
    Nunca aceita cifras fornecidas pelo chamador como fatos do PDF.
    """
    cut = instant(cutoff)
    doc.validate()
    origin, listing, pdf = (vault.read(name) for name in ("origem", "lista", "pdf"))
    available = max(x.completed for x in (origin, listing, pdf))
    def missing(reason):
        return Result("ausente", (), (reason,), None, None, available, vault.manifest_sha256, pdf.payload_sha256)
    if available > cut:
        return missing("captura_posterior_ao_corte")
    if closed_upper_bound(doc.period_end) > min(available, cut):
        return missing("competencia_nao_encerrada_sob_limite_conservador")
    if any(closed_upper_bound(c.end) > min(available, cut) for c in doc.columns):
        return missing("coluna_nao_encerrada_sob_limite_conservador")
    # A lista oficial vincula o título/URL; sua data civil não vira publicação.
    if urlparse(origin.url).hostname != urlparse(listing.url).hostname:
        raise ValueError("lista fora da origem oficial selada")
    assets = json.loads(listing.payload)["GetContentAssetListResult"]
    matches = [a for a in assets if a.get("Title") == doc.listing_title and a.get("FilePath") == pdf.url]
    if len(matches) != 1 or matches[0].get("FileType") != "PDF":
        raise ValueError("lista não vincula PDF/título de forma única")
    if urlparse(pdf.url).hostname not in origin.payload.decode("utf-8"):
        raise ValueError("origem não reconhece domínio do documento")
    reader = PdfReader(io.BytesIO(pdf.payload), strict=True)
    if reader.is_encrypted or len(reader.pages) != doc.page_count:
        raise ValueError("PDF criptografado ou quantidade de páginas divergente")
    texts = {}
    def page(n):
        if not 1 <= n <= len(reader.pages):
            raise ValueError("página física inexistente")
        if n not in texts:
            texts[n] = reader.pages[n - 1].extract_text() or ""
        return texts[n]
    context = {n: normalize(page(n)) for n in doc.pages_context}
    if doc.page_metadata not in context or doc.page_table not in context:
        raise ValueError("contexto não inclui metadados/tabela")
    if any(doc.entity + " Consolidado" not in text for text in context.values()):
        raise ValueError("entidade/base não conferem nos bytes")
    meta = context[doc.page_metadata]
    period = f"Periodo cubierto por los estados financieros: {doc.period_start} al {doc.period_end}"
    if period not in meta or f"Descripción de la moneda de presentación: {doc.currency}" not in meta or "Consolidado: Si" not in meta:
        raise ValueError("período, moeda ou base não conferem")
    units = []
    scales = {"Unidades": Decimal(1), "Miles": Decimal(1000), "Millones": Decimal(1000000)}
    for text in context.values():
        found = re.findall(r"Cantidades monetarias expresadas en (Unidades|Miles|Millones)\b", text)
        if len(found) != 1:
            raise ValueError("unidade exibida ausente/ambígua")
        units.append(scales[found[0]])
    if len(set(units)) != 1 or units[0] != doc.expected_scale:
        raise ValueError("escala do catálogo não coincide com unidade exibida")
    # Quantum de arredondamento é separado do multiplicador das células.
    rounding = re.findall(r"Grado de redondeo utilizado en los estados financieros: (MILES DE PESOS|UNIDADES|MILLONES DE PESOS)\b", meta)
    if len(rounding) != 1:
        raise ValueError("arredondamento ausente/ambíguo")
    quantum = {"MILES DE PESOS": Decimal(1000), "UNIDADES": Decimal(1), "MILLONES DE PESOS": Decimal(1000000)}[rounding[0]]
    header = "Concepto " + " ".join(f"{c.label} {doc.currency} {c.end}" for c in doc.columns)
    normal = context[doc.page_table]
    if normal.count(header) != 1:
        raise ValueError("ordem/identidade das colunas divergente")
    body = normal.split(header, 1)[1]
    lines = [normalize(x) for x in page(doc.page_table).splitlines() if normalize(x) and normalize(x) in body]
    vectors = {}
    for item in doc.items:
        rows = []
        for line in lines:
            match = re.fullmatch(re.escape(item.label) + r"\s+(" + NUMBER + r"(?:\s+" + NUMBER + r")*)", line)
            if match:
                cells = tuple(re.findall(NUMBER, match[1]))
                if len(cells) != len(doc.columns):
                    raise ValueError("quantidade de colunas da rubrica divergente")
                rows.append(cells)
        if len(rows) != 1:
            raise ValueError("rubrica ausente/repetida")
        vectors[item.name] = rows[0]
    facts, identities, reasons = [], [], []
    for idx, col in enumerate(doc.columns):
        amounts = {name: money(cells[idx]) for name, cells in vectors.items()}
        total, parts = doc.identity
        complete = all(amounts[n] is not None for n in (total, *parts))
        residual = amounts[total] - sum(amounts[n] for n in parts) if complete else None
        identities.append(Identity(col.end, complete, residual))
        if complete:
            if residual != 0:
                raise ValueError("identidade por coluna não reconciliada")
        else:
            reasons.append(f"identidade_parcial:{col.end}")
        for item in doc.items:
            value = amounts[item.name]
            if value is not None:
                value *= units[0]
                if value % quantum:
                    raise ValueError("valor não respeita arredondamento declarado")
            facts.append(StockFact(doc.issuer_id, item.name, value, col.end, doc.currency, "consolidado", units[0],
                quantum, vectors[item.name][idx], f"página física {doc.page_table}; coluna {idx + 1}; {item.label}",
                pdf.payload_sha256, pdf.receipt_sha256, vault.manifest_sha256, pdf.url, None, None, available,
                pdf.completed, POLICY, None, closed_upper_bound(col.end)))
    return Result("captura_observada_publicacao_desconhecida", tuple(facts), tuple(reasons), None, None, available,
                  vault.manifest_sha256, pdf.payload_sha256, identities=tuple(identities))


def export(result: Result) -> dict:
    def encode(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {k: encode(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [encode(v) for v in value]
        return value
    return encode(asdict(result))


def verify_export(envelope: dict, vault: ReceiptVault, doc: Document, *, cutoff: datetime) -> bool:
    """Reextração obrigatória; nem o hash novo de uma transcrição a autentica."""
    expected = export(extract(vault, doc, cutoff=cutoff))
    if envelope != expected:
        raise ValueError("visão difere da reextração sob o recibo/corte")
    return True
