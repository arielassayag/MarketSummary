"""Camada privada de identidade; mantém v1 como extrator estrutural imutável."""
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal

from .identidade_legada import Bind, IdentityVault, bind, canonical
from .observado import Document, ReceiptVault, Result, sha
from .observado import extract as structural_extract


@dataclass(frozen=True)
class BoundResult:
    schema: str
    binding: Bind | None
    binding_sha256: str | None
    result: Result


def encode(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [encode(v) for v in value]
    return value


def extract(vault: ReceiptVault, doc: Document, *, identity: IdentityVault, ticker: str, exchange: str, cutoff: datetime) -> BoundResult:
    binding, available = bind(vault, doc, identity, ticker=ticker, exchange=exchange, cutoff=cutoff)
    if binding is None:
        return BoundResult('cdp.ri.captura_identidade_privada/v2', None, None,
            Result('ausente', (), ('identidade_dependencia_posterior_ao_corte',), None, None, available,
                   vault.manifest_sha256, None))
    result = structural_extract(vault, doc, cutoff=cutoff)
    # Toda medida depende também do bind de identidade, não apenas dos bytes do PDF.
    result = replace(result, available_since=available,
                     facts=tuple(replace(f, disponivel_desde=available) for f in result.facts))
    binding_hash = sha(canonical(encode(asdict(binding))))
    return BoundResult('cdp.ri.captura_identidade_privada/v2', binding, binding_hash, result)


def export(result: BoundResult):
    envelope = encode(asdict(result))
    for fact in envelope['result']['facts']:
        fact['identity_binding_sha256'] = result.binding_sha256
    return envelope


def verify_export(envelope, vault, doc, *, identity, ticker, exchange, cutoff):
    expected = export(extract(vault, doc, identity=identity, ticker=ticker, exchange=exchange, cutoff=cutoff))
    if envelope != expected:
        raise ValueError('identidade/fatos diferentes da reextração sob roots/corte')
    return True
