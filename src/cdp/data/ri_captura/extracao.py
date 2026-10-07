"""RI privado v4: todas as autoridades originais fixas, antes/depois da extração."""
from dataclasses import replace

from .custodia import ReceiptVault
from .extracao_identidade import export as export_v2
from .extracao_identidade import extract as extract_v2
from .identidade import IdentityVault, MasterAuthority


def _authenticate(vault, identity):
    if type(vault) is not ReceiptVault:
        raise ValueError("RI v4 exige custódia financeira v3 exata e imutável")
    if type(identity) is not IdentityVault or type(identity.master) is not MasterAuthority:
        raise ValueError("RI v4 exige autoridades v4 exatas de identidade/master")
    vault.authenticate()
    identity.master.authenticate()
    identity.authenticate()


def extract(vault, doc, *, identity, ticker, exchange, cutoff):
    _authenticate(vault, identity)
    result = extract_v2(vault, doc, identity=identity, ticker=ticker, exchange=exchange, cutoff=cutoff)
    _authenticate(vault, identity)
    return replace(result, schema="cdp.ri.captura_identidade_privada/v4")


def export(result):
    return export_v2(result)


def verify_export(envelope, vault, doc, *, identity, ticker, exchange, cutoff):
    expected = export(extract(vault, doc, identity=identity, ticker=ticker, exchange=exchange, cutoff=cutoff))
    if envelope != expected:
        raise ValueError("RI v4: fatos/autoridades diferem da reextração sob âncoras/corte fixos")
    return True
