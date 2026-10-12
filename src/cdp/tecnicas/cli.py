"""CLI de técnicas; não carrega o runtime operacional do CDP."""
import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="cdp-tecnicas", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("listar", help="lista os três kernels disponíveis")
    exemplo = sub.add_parser("exemplo", help="confere os corpos do exemplo simulado")
    exemplo.add_argument("nome", choices=["latam_simulado_v1"])
    adaptadores = sub.add_parser("adaptadores", help="gera ou confere adaptadores em destino explícito")
    adaptadores.add_argument("--saida", required=True)
    adaptadores.add_argument("--verificar", action="store_true")
    args = parser.parse_args()
    if args.comando == "adaptadores":
        from pathlib import Path

        from .adaptadores import conferir_adaptadores, gravar_adaptadores

        try:
            destino = Path(args.saida)
            if args.verificar:
                diferentes = conferir_adaptadores(destino)
                print(json.dumps({"ok": not diferentes, "diferentes": diferentes}, ensure_ascii=False))
                return 1 if diferentes else 0
            escritos = gravar_adaptadores(destino)
        except (OSError, ValueError) as exc:
            print(f"Adaptadores recusados: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"gravados": escritos}, ensure_ascii=False))
        return 0
    if args.comando == "listar":
        print(json.dumps({"tecnicas": ["calcular_ke", "avaliar_pb_justificado", "estimar_preenchimento"]}, ensure_ascii=False))
        return 0
    from .recursos import carregar_exemplo

    try:
        entradas = carregar_exemplo(args.nome)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Configuração recusada: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"papel": entradas.origem.papel, "aviso": entradas.origem.aviso,
                      "nome": entradas.origem.nome, "sha256": dict(entradas.arquivos.sha256)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
