"""Transporte das nove leituras nativas; contexto recebido e entrada STDIO própria."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .operacional_schemas import contratos_ferramentas, texto_json, validar_ingresso, validar_saida


def emitir_json_recebido(payload: dict, ferramenta: str | None = None):
    """Emite JSON da folha; também permite qualificar corpos recebidos sem delegate."""
    from mcp.types import CallToolResult, TextContent

    data = validar_saida(payload, ferramenta)
    text = texto_json(data)
    result = CallToolResult(content=[TextContent(type="text", text=text)],
                            structured_content=data, is_error=data["status"] != "disponivel")
    transported = validar_saida(result.structured_content, ferramenta)
    if texto_json(transported) != text or result.content[0].text != text:
        raise ValueError("SDK alterou o corpo recebido")
    return result


def catalogo_ferramentas():
    """Catálogo de produção reutilizável na qualificação de protocolo."""
    from mcp.types import ListToolsResult, Tool, ToolAnnotations

    return ListToolsResult(tools=[
        Tool(name=name, description="Consulta nativa de leitura com contexto recebido; sem autoridade operacional.",
             input_schema=ingress, output_schema=output,
             annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
        for name, ingress, output in contratos_ferramentas()
    ])


def ingresso_chamada(params) -> dict:
    """Fronteira de protocolo anterior ao delegate, reutilizável sem leitor."""
    from mcp import MCPError

    try:
        return validar_ingresso(params.name, params.arguments)
    except Exception:
        raise MCPError(-32602, "Ingresso recusado pelo contrato estrito") from None


def build_server(leitor):
    """Exige o leitor canônico; construir servidor não escolhe fontes nem executa consulta."""
    from mcp import MCPError
    from mcp.server import Server

    from .. import __version__
    from ..workflow.leitura import LeitorOperacional
    from ..workflow.leitura_serializacao import serializar_resposta

    if type(leitor) is not LeitorOperacional:
        raise TypeError("LeitorOperacional canônico exigido")
    specs = contratos_ferramentas()
    names = frozenset(name for name, _, _ in specs)

    async def listar(ctx, params):
        return catalogo_ferramentas()

    async def chamar(ctx, params):
        if type(params.name) is not str or params.name not in names:
            raise MCPError(-32602, "Ferramenta fora da lista fechada")
        arguments = ingresso_chamada(params)
        try:
            response = leitor.consultar(params.name, arguments)
            payload = serializar_resposta(response)
            return emitir_json_recebido(payload, params.name)
        except Exception:
            raise MCPError(-32603, "Resposta de leitura recusada") from None

    return Server("cdp-operacional-leitura", version=__version__, on_list_tools=listar,
                  on_call_tool=chamar)


def _contexto_absoluto(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("Contexto exige path absoluto")
    return path


def main(argv: list[str] | None = None) -> int:
    """Host fornece contexto; não instala SDK, usa cwd ou registra entrypoint."""
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(prog="cdp-mcp-operacional", allow_abbrev=False,
                                     description="Nove consultas de leitura; contexto recebido obrigatório.")
    parser.add_argument("--contexto", required=True, type=_contexto_absoluto)
    args = parser.parse_args(argv)
    try:
        from mcp.server.stdio import stdio_server
    except ModuleNotFoundError as exc:
        if exc.name is None or not (exc.name == "mcp" or exc.name.startswith("mcp.")):
            raise
        print("MCP indisponível: instale o extra mcp do pacote CDP.", file=sys.stderr)
        return 2

    import anyio

    from ..workflow.leitura import LeitorOperacional, receber_contexto_leitura
    from ..workflow.leitura_contratos import ContextoLeituraInvalido

    try:
        context = receber_contexto_leitura(args.contexto)
        server = build_server(LeitorOperacional(context))
    except (ContextoLeituraInvalido, OSError, ValueError, TypeError):
        print("Contexto de leitura ausente ou inválido; servidor não iniciado.", file=sys.stderr)
        return 2

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
