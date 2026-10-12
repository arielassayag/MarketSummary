"""Fronteira JSON estrita do transporte; contratos pertencem à folha nativa."""
from __future__ import annotations

import json
import math

NOMES = (
    "consultar_estado", "consultar_agenda", "verificar_integridade", "ler_fatos",
    "validar_documento", "ler_carteira", "decompor_risco_operacional",
    "ler_modelo_cobertura", "ler_pacote_mente",
)
MAX_BYTES = 8 * 1024 * 1024
MAX_NOS = 500_000
MAX_PROFUNDIDADE = 128


def _json_exato(value) -> None:
    """Recusa objetos e subclasses antes de acessar seus métodos/propriedades."""
    pending = [(value, 0)]
    visited = 0
    while pending:
        item, depth = pending.pop()
        visited += 1
        if depth > MAX_PROFUNDIDADE or visited > MAX_NOS:
            raise ValueError("JSON excede o limite de transporte")
        kind = type(item)
        if kind is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("Chave JSON precisa ser texto exato")
                pending.append((child, depth + 1))
        elif kind is list:
            pending.extend((child, depth + 1) for child in item)
        elif kind is float:
            if not math.isfinite(item):
                raise ValueError("Número JSON não finito recusado")
        elif kind not in (str, int, bool, type(None)):
            raise ValueError("Tipo fora dos primitivos JSON exatos")


def texto_json(value) -> str:
    """Codifica somente primitivos recebidos; não converte objetos financeiros."""
    _json_exato(value)
    text = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("JSON excede o limite de bytes do transporte")
    return text


def _contratos():
    from ..workflow.leitura_contratos import FerramentaLeitura, schema_ingresso, schema_saida

    values = tuple(item.value for item in FerramentaLeitura)
    if (len(values) != len(NOMES) or any(type(value) is not str for value in values)
            or set(values) != set(NOMES) or len(FerramentaLeitura.__members__) != len(NOMES)):
        raise ValueError("Catálogo nativo diverge das nove ferramentas")
    return schema_ingresso, schema_saida


def _schema_fechado(schema: dict) -> None:
    _json_exato(schema)
    pending = [schema]
    while pending:
        item = pending.pop()
        if type(item) is dict:
            if item.get("type") == "object" and item.get("additionalProperties") is not False:
                branches = item.get("oneOf")
                closed_union = (
                    "additionalProperties" not in item and type(branches) is list and bool(branches)
                    and all(type(branch) is dict and branch.get("type") == "object"
                            and branch.get("additionalProperties") is False for branch in branches)
                )
                if not closed_union:
                    raise ValueError("Schema nativo admite propriedades abertas")
            for key in ("$ref", "$dynamicRef", "$recursiveRef"):
                if key in item and (type(item[key]) is not str or not item[key].startswith("#")):
                    raise ValueError("Schema exige referência externa")
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)


def _validador_estrito(schema: dict):
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
    from jsonschema.validators import extend
    from referencing import Registry

    # JSON Schema considera 1.0 um integer; o ingresso exige int literal.
    types = Draft202012Validator.TYPE_CHECKER.redefine_many({
        "integer": lambda checker, value: type(value) is int,
        "number": lambda checker, value: type(value) in (int, float),
        "boolean": lambda checker, value: type(value) is bool,
        "object": lambda checker, value: type(value) is dict,
        "array": lambda checker, value: type(value) is list,
        "string": lambda checker, value: type(value) is str,
        "null": lambda checker, value: value is None,
    })

    def const(validator, expected, value, node):
        if type(value) is not type(expected) or value != expected:
            yield ValidationError("Literal diverge do contrato estrito")

    def enum(validator, expected, value, node):
        if not any(type(value) is type(item) and value == item for item in expected):
            yield ValidationError("Enum diverge do contrato estrito")

    strict = extend(Draft202012Validator, {"const": const, "enum": enum}, type_checker=types)
    # evolve() pode trocar a extensão pelo Draft padrão ao resolver um $schema.
    # Só a cópia de compilação remove esse metadado; o schema publicado é preservado.
    compiled = json.loads(texto_json(schema))
    pending = [compiled]
    while pending:
        item = pending.pop()
        if type(item) is dict:
            item.pop("$schema", None)
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)
    return strict(compiled, registry=Registry())


def contratos_ferramentas() -> tuple[tuple[str, dict, dict], ...]:
    """Recebe os schemas compartilhados; nenhuma cópia de ValorNativo vive aqui."""
    from jsonschema import Draft202012Validator

    schema_ingresso, schema_saida = _contratos()
    output = schema_saida()
    _schema_fechado(output)
    Draft202012Validator.check_schema(output)
    catalog = []
    for name in NOMES:
        native_ingress = schema_ingresso(name)
        _schema_fechado(native_ingress)
        if native_ingress.get("type", "object") != "object":
            raise ValueError("Ingresso nativo não é um objeto de chamada")
        # MCP exige type: object na raiz do inputSchema, inclusive com oneOf.
        # A cópia de protocolo só explicita a fronteira dict já exigida abaixo.
        ingress = json.loads(texto_json(native_ingress))
        ingress.setdefault("type", "object")
        _schema_fechado(ingress)
        Draft202012Validator.check_schema(ingress)
        catalog.append((name, ingress, output))
    return tuple(catalog)


def validar_ingresso(ferramenta: str, argumentos: dict) -> dict:
    """Valida sem coerção, antes de qualquer consulta nativa."""
    if type(ferramenta) is not str or ferramenta not in NOMES:
        raise ValueError("Ferramenta fora da lista fechada")
    if type(argumentos) is not dict:
        raise ValueError("Objeto JSON exato exigido")
    texto_json(argumentos)
    schema_ingresso, _ = _contratos()
    schema = schema_ingresso(ferramenta)
    _schema_fechado(schema)
    _validador_estrito(schema).validate(argumentos)
    return argumentos


def validar_saida(payload: dict, ferramenta: str | None = None) -> dict:
    """Confronta contrato/bytes/hash nativos sem reconstrução ou novo selo."""
    from ..workflow.leitura_serializacao import (
        bytes_resultado,
        hash_resultado,
        validar_json_resposta,
    )

    if type(payload) is not dict:
        raise ValueError("Resposta JSON exata exigida")
    texto_json(payload)
    _, schema_saida = _contratos()
    schema = schema_saida()
    _schema_fechado(schema)
    _validador_estrito(schema).validate(payload)
    received = validar_json_resposta(payload)
    _json_exato(received)
    if type(received) is not dict or texto_json(received) != texto_json(payload):
        raise ValueError("Validação nativa alterou a resposta recebida")
    if ferramenta is not None and received["ferramenta"] != ferramenta:
        raise ValueError("Ferramenta da resposta diverge da chamada")
    if received["status"] == "disponivel":
        original = bytes_resultado(payload["resultado"])
        if original != bytes_resultado(received["resultado"]):
            raise ValueError("Bytes do resultado foram alterados")
        if hash_resultado(received["resultado"]) != received["resultado_sha256"]:
            raise ValueError("Hash de transporte diverge do resultado recebido")
    elif received["resultado"] is not None or received["resultado_sha256"] is not None:
        raise ValueError("Recusa/indisponibilidade não admite resultado")
    return received
