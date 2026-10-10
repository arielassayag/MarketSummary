"""Servidor STDIO de três técnicas e exemplo; nenhuma rota operacional."""
from __future__ import annotations

import hashlib
import json
import math
from importlib.resources import files

from mcp import MCPError
from mcp.server import Server, ServerRequestContext
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListResourcesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
    ToolAnnotations,
)
from pydantic import ValidationError

from .. import __version__
from ..tecnicas import avaliar_pb_justificado, calcular_ke, estimar_preenchimento
from .schemas import (
    MEMBROS,
    ArrayPB,
    AusentePB,
    Catalogo,
    EntradaKE,
    EntradaPB,
    EntradaPreenchimento,
    Erro,
    ManifestoExemplo,
    NumeroObservado,
    RecursoExemplo,
    SaidaDesconhecida,
    SaidaKE,
    SaidaPB,
    SaidaPreenchimento,
    SucessoKE,
    SucessoPB,
    SucessoPreenchimento,
    TecnicaCatalogo,
    forma_pb,
)

CATALOGO_URI = "cdp://tecnicas/catalogo"
EXEMPLO_URI = "cdp://exemplos/latam_simulado_v1/"
RECURSOS = {EXEMPLO_URI + n: n for n in ("manifesto", *MEMBROS)}


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _observado(value) -> NumeroObservado:
    value = float(value)
    state = ("nan" if math.isnan(value) else "mais_infinito" if value > 0
             else "menos_infinito") if not math.isfinite(value) else "finito"
    return NumeroObservado(valor=value if math.isfinite(value) else None, estado=state)


def _ke(args: EntradaKE) -> SucessoKE:
    return SucessoKE(custo=_observado(calcular_ke(**args.model_dump())))


def _pb(args: EntradaPB) -> SucessoPB:
    import numpy as np

    def native(operand):
        if isinstance(operand, ArrayPB):
            return np.asarray([np.nan if isinstance(v, AusentePB) else v for v in operand.valores],
                              dtype=float).reshape(operand.forma)
        return np.nan if isinstance(operand, AusentePB) else operand.valor

    result = avaliar_pb_justificado(*(native(x) for x in (args.roe, args.ke, args.g)),
                                    estrito=args.estrito)
    if list(result.shape) != forma_pb((args.roe, args.ke, args.g)):
        raise ValueError("Delegate retornou forma divergente")
    cells = [_observado(v) for v in result.reshape(-1)]
    return SucessoPB(forma=list(result.shape), valores=[c.valor for c in cells],
                     estados=[c.estado for c in cells], estrito=args.estrito)


def _preenchimento(args: EntradaPreenchimento) -> SucessoPreenchimento:
    return SucessoPreenchimento(acoes=estimar_preenchimento(**args.model_dump()))


# Cada entrada associa nominalmente um contrato e um delegate; nada vem de getattr/CLI.
TECNICAS = {
    "calcular_ke": (EntradaKE, SaidaKE, _ke, "taxa decimal; base USD"),
    "avaliar_pb_justificado": (EntradaPB, SaidaPB, _pb, "múltiplo adimensional x"),
    "estimar_preenchimento": (EntradaPreenchimento, SaidaPreenchimento, _preenchimento,
                             "ações inteiras assinadas; capacidade e preço em USD"),
}


def _resposta(model) -> CallToolResult:
    # Validar também o objeto final; um model construído fora da validação não escapa.
    data = type(model).model_validate(model.model_dump(mode="python"), strict=True).model_dump(
        mode="json")
    return CallToolResult(content=[TextContent(type="text", text=_json(data))],
                          structured_content=data, is_error=data["resultado"]["tipo"] == "erro")


async def _listar(ctx: ServerRequestContext, params: PaginatedRequestParams | None):
    return ListToolsResult(tools=[
        Tool(name=name, description=f"Técnica determinística; {unit}; operandos declarados.",
             input_schema=entrada.model_json_schema(), output_schema=saida.model_json_schema(),
             annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
        for name, (entrada, saida, _fn, unit) in TECNICAS.items()
    ])


async def _chamar(ctx: ServerRequestContext, params: CallToolRequestParams):
    spec = TECNICAS.get(params.name)
    if spec is None:
        return _resposta(SaidaDesconhecida(versao_motor=__version__, resultado=Erro(
            codigo="TECNICA_DESCONHECIDA", mensagem="Técnica fora da lista fechada")))
    entrada, saida, fn, _unit = spec
    try:
        args = entrada.model_validate(params.arguments, strict=True)
    except ValidationError:
        result = Erro(codigo="ENTRADA_INVALIDA", mensagem="Entrada recusada pelo contrato estrito")
    else:
        try:
            result = fn(args)
        except (ValueError, OverflowError):
            result = Erro(codigo="KERNEL_RECUSOU", mensagem="Pré-condição do kernel recusada")
    return _resposta(saida(versao_motor=__version__, resultado=result))


def _catalogo() -> Catalogo:
    def sha(model):
        return hashlib.sha256(_json(model.model_json_schema()).encode()).hexdigest()

    return Catalogo(versao_motor=__version__, aviso=(
        "Operandos declarados; sem identidade, operação ou autoridade financeira"), tecnicas=[
        TecnicaCatalogo(nome=n, unidade=u, input_schema_sha256=sha(e), output_schema_sha256=sha(s))
        for n, (e, s, _fn, u) in TECNICAS.items()
    ])


async def _listar_recursos(ctx: ServerRequestContext, params: PaginatedRequestParams | None):
    return ListResourcesResult(resources=[
        Resource(uri=CATALOGO_URI, name="Catálogo das três técnicas", mime_type="application/json"),
        *(Resource(uri=uri, name=f"EXEMPLO / DADOS SIMULADOS · {name}",
                   mime_type="application/json") for uri, name in RECURSOS.items()),
    ])


def _exemplo(name: str) -> RecursoExemplo:
    from ..tecnicas.recursos import carregar_exemplo

    # Reter o manifesto lido e confrontá-lo com os corpos retornados pelo parser nativo.
    manifest_body = files("cdp").joinpath("recursos", "exemplos", "latam_simulado_v1",
                                       "manifesto.json").read_bytes()
    manifest = ManifestoExemplo.model_validate(json.loads(manifest_body), strict=True)
    example = carregar_exemplo("latam_simulado_v1")
    if manifest.membros != dict(example.arquivos.sha256):
        raise ValueError("Manifesto e corpos recebidos divergem")
    body = manifest_body if name == "manifesto" else example.arquivos.corpos[name]
    mime = "application/json" if name == "manifesto" else (
        "text/csv" if name.endswith(".csv") else "application/yaml")
    return RecursoExemplo(membro="manifesto.json" if name == "manifesto" else name,
                          sha256=hashlib.sha256(body).hexdigest(), tipo_conteudo=mime,
                          conteudo_utf8=body.decode("utf-8"))


async def _ler_recurso(ctx: ServerRequestContext, params: ReadResourceRequestParams):
    uri = params.uri
    if uri != CATALOGO_URI and uri not in RECURSOS:
        raise MCPError(-32602, "Recurso fora da lista fechada")
    try:
        model = _catalogo() if uri == CATALOGO_URI else _exemplo(RECURSOS[uri])
        data = type(model).model_validate(model.model_dump(mode="json"), strict=True)
    except (OSError, ValueError, KeyError):
        raise MCPError(-32602, "Recurso empacotado ausente ou inválido") from None
    return ReadResourceResult(contents=[TextResourceContents(uri=uri, mime_type="application/json",
                                                             text=_json(data.model_dump(mode="json")))])


def build_server() -> Server:
    """Constrói sem iniciar transporte, ler workspace ou obter autoridade."""
    return Server("cdp-tecnicas-leitura", version=__version__, on_list_tools=_listar,
                  on_call_tool=_chamar, on_list_resources=_listar_recursos,
                  on_read_resource=_ler_recurso)
