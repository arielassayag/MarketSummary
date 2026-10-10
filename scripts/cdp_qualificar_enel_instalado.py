"""Consumo instalado por import normal; -I impede PYTHONPATH e o clone no sys.path."""
import hashlib
import json
import os
import socket
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def write_json(path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, sort_keys=True, indent=2)
        output.write("\n")


def main():
    if len(sys.argv) < 3:
        raise ValueError("Fase e AREA absoluta explícita são obrigatórias")
    label, raw_area = sys.argv[1:3]
    if (not label or label in (".", "..") or "/" in label or "\\" in label
            or "\0" in label or Path(label).is_absolute() or len(Path(label).parts) != 1):
        raise ValueError("Fase deve ser um componente único")
    if not Path(raw_area).is_absolute():
        raise ValueError("AREA deve ser absoluta e explícita")
    area = Path(raw_area).resolve()
    prefix = Path(sys.prefix).resolve()
    if not area.is_dir() or area == Path("/") or sys.prefix == sys.base_prefix or not prefix.is_relative_to(area):
        raise ValueError("Prefixo instalado fora da AREA explícita")
    work = area / "execucao" / label
    if not work.resolve().is_relative_to(area):
        raise ValueError("Fase resolvida fora da AREA explícita")
    probe_destination = None
    if label in ("LITERAL", "INVALIDO"):
        if len(sys.argv) != 4 or not Path(sys.argv[3]).is_absolute():
            raise ValueError("Destino absoluto explícito do catálogo é obrigatório")
        probe_destination = Path(sys.argv[3])
        if not probe_destination.resolve().is_relative_to(prefix):
            raise ValueError("Catálogo de controle fora do prefixo instalado")
    os.environ["ENEL_INSTALACAO_AREA"] = str(area)
    os.environ.pop("PYTHONPATH", None)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    guards = {"network": [], "writers": [], "solver": [], "filesystem": []}

    def deny(kind):
        def handler(*args, **kwargs):
            guards[kind].append("tentativa")
            raise AssertionError("Operação proibida na integração instalada: " + kind)
        return handler

    socket.socket.connect = deny("network")
    socket.socket.connect_ex = deny("network")
    socket.create_connection = deny("network")
    import urllib.request

    import requests

    urllib.request.urlopen = deny("network")
    requests.sessions.Session.request = deny("network")
    import cvxpy
    import scipy.optimize

    cvxpy.Problem.solve = deny("solver")
    for name in ("minimize", "linprog", "milp", "least_squares", "differential_evolution"):
        setattr(scipy.optimize, name, deny("solver"))
    from cdp.data.publico_arquivo import Arquivo
    from cdp.workflow.book import Book
    from cdp.workflow.track_record import TrackRecord

    Arquivo.gravar = deny("writers")
    TrackRecord.append = deny("writers")
    for name in ("save_research_pack", "save_proposal", "save_decision", "save_booked", "registrar_efetivacao_recusada"):
        setattr(Book, name, deny("writers"))

    def resolved_path(raw, dir_fd=None):
        def descriptor_path(fd):
            for root in ("/proc/self/fd", "/dev/fd"):
                try:
                    return Path(os.readlink(f"{root}/{fd}")).resolve()
                except OSError:
                    continue
            raise AssertionError("Descritor sem caminho verificável")

        if isinstance(raw, int):
            return descriptor_path(raw)
        path = Path(os.fsdecode(raw))
        if not path.is_absolute():
            base = descriptor_path(dir_fd) if dir_fd not in (None, -1) else Path.cwd()
            path = base / path
        return path.resolve()

    def require_private(event, raw, dir_fd=None):
        try:
            path = resolved_path(raw, dir_fd)
            if path.is_relative_to(area):
                return path
        except (OSError, ValueError, AssertionError) as error:
            guards["filesystem"].append({"evento": event, "caminho": str(raw), "erro": str(error)})
            raise AssertionError("Caminho de mutação não verificável") from error
        guards["filesystem"].append({"evento": event, "caminho": str(raw), "resolvido": str(path)})
        raise AssertionError("Mutação fora da área privada")

    def audit(event, args):
        if event == "open":
            path, mode, flags = args
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
            if writing and str(path) != "/dev/null":
                if not isinstance(path, int) and not Path(os.fsdecode(path)).is_absolute():
                    guards["filesystem"].append({"evento": event, "caminho": os.fsdecode(path),
                                                 "motivo": "nome relativo sem dir_fd autenticável no evento"})
                    raise AssertionError("Open relativo sem diretório autenticado")
                require_private(event, path)
        elif event in ("os.rename", "os.link"):
            require_private(event, args[0], args[2])
            require_private(event, args[1], args[3])
        elif event == "os.symlink":
            destination = require_private(event, args[1], args[2])
            source = Path(os.fsdecode(args[0]))
            require_private(event, source if source.is_absolute() else destination.parent / source)
        elif event in ("os.mkdir", "os.chmod"):
            require_private(event, args[0], args[2])
        elif event in ("os.remove", "os.rmdir"):
            require_private(event, args[0], args[1])
        elif event in ("os.chown", "os.utime"):
            require_private(event, args[0], args[3])
        elif event in ("os.chdir", "os.truncate"):
            require_private(event, args[0])
        elif event in ("shutil.copyfile", "shutil.copymode", "shutil.copystat"):
            require_private(event, args[1])

    sys.addaudithook(audit)
    if label in ("LITERAL", "INVALIDO"):
        from cdp.data import publico_sec as sec

        assert sec.CATALOGO_CLASSES == probe_destination
        if label == "LITERAL":
            assert sec.ciks_classes_sec()
        else:
            try:
                sec.ciks_classes_sec()
            except ValueError:
                pass
            else:
                raise AssertionError("Catálogo presente inválido recebeu fallback")
        assert not any(guards.values())
        print(json.dumps({"catalogo_presente_preferido": True, "guard_attempts": 0}))
        return
    target = REPO
    work.mkdir(parents=True, exist_ok=True)
    os.chdir(work)
    os.environ["TMPDIR"] = str(work)
    os.environ["ENEL_INSTALACAO_SAIDA"] = str(work)
    os.environ["ENEL_INSTALACAO_PROBE"] = str(Path(__file__).resolve())
    import tempfile

    tempfile.tempdir = str(work)
    import pytest

    with (work / "pytest.log").open("x", encoding="utf-8") as log:
        prior_out, prior_err = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = log
        try:
            result = pytest.main([str(target / "scripts/enelchile/test_instalacao_offline.py"), "-q", "-p", "no:cacheprovider",
                                  "-c", str(REPO / "pyproject.toml"), f"--basetemp={work / 'pytest'}",
                                  f"--junitxml={work / 'pytest.xml'}"])
        finally:
            sys.stdout, sys.stderr = prior_out, prior_err
    modules = {}
    for name, module in sorted(sys.modules.items()):
        raw = getattr(module, "__file__", None)
        if raw and (name == "cdp" or name.startswith("cdp.") or name.startswith("enelchile_documental")):
            path = Path(raw).resolve()
            assert path.is_relative_to(Path(sys.prefix).resolve()) and "site-packages" in path.parts
            modules[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    write_json(work / "GUARDAS.json", guards)
    write_json(work / "IMPORTS_NORMAIS_INSTALADOS.json", modules)
    assert not any(guards.values())
    print(json.dumps({"exit": int(result), "imports_normais_instalados": len(modules), "guard_attempts": 0}))
    raise SystemExit(result)


if __name__ == "__main__":
    main()
