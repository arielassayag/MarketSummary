"""Entrada STDIO opcional; nunca instala dependências por conta própria."""
import sys


def main() -> int:
    sys.dont_write_bytecode = True
    try:
        from mcp.server.stdio import stdio_server
    except ModuleNotFoundError as exc:
        if exc.name is None or not (exc.name == "mcp" or exc.name.startswith("mcp.")):
            raise
        print("MCP indisponível: instale o extra mcp do pacote CDP.", file=sys.stderr)
        return 2

    import anyio

    from .server import build_server

    async def run():
        server = build_server()
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
