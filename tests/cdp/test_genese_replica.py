"""Abertura de réplica em repositórios locais sintéticos; nenhum livro oficial é usado."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cdp import executor as ex
from cdp.__main__ import build_parser, main
from cdp.audit import GENESIS_HASH
from cdp.config import load_config
from cdp.hashing import sha256_obj
from cdp.workflow import genese as g
from cdp.workflow.book import GENESIS_EVENT, Book
from cdp.workflow.reinicio import plano as plano_legado
from cdp.workflow.reinicio import situacao
from cdp.workflow.runtime import Runtime

ROOT = Path(__file__).resolve().parents[2]
SRC_CDP = Path(g.__file__).resolve().parents[1]
NOW = datetime(2026, 10, 9, 10, 0, tzinfo=UTC)  # relógio lógico de teste, não recepção histórica
EXECUCAO = "execucao-sintetica-genese"
TRAVA = "trava-sintetica-genese"
ENV = {"CDP_EXECUTOR": "local-pc", "CDP_HARNESS": "codex"}


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return p.stdout.strip()


def tree(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and ".git" not in p.relative_to(root).parts}


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    root = tmp_path_factory.mktemp("genese-fonte")
    repo = root / "repo"
    repo.mkdir()
    shutil.copytree(SRC_CDP, repo / "src/cdp", copy_function=shutil.copy2,
                    ignore=shutil.ignore_patterns("__pycache__"))
    (repo / "configs/cdp").mkdir(parents=True)
    for name in ("fund.yaml", "rotinas.yaml", "executor.yaml"):
        shutil.copy2(ROOT / "configs/cdp" / name, repo / "configs/cdp" / name)
    (repo / ".gitignore").write_text("book/\n.cdp/\n.cdp_genese.tmp/\n")
    lock = {"versao": 1, "estado": "ocupada", "id": TRAVA, "tarefa": "cdp-diario",
            "executor": "local-pc", "harness": "codex", "inicio": NOW.isoformat(),
            "renovada": NOW.isoformat(), "expira": "2026-10-09T11:00:00+00:00"}
    (repo / "trava.json").write_text(json.dumps(lock) + "\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Teste de réplica")
    git(repo, "config", "user.email", "teste@example.invalid")
    git(repo, "config", "gc.auto", "0")
    git(repo, "config", "maintenance.auto", "false")
    git(repo, "add", "src", "configs", ".gitignore", "trava.json")
    git(repo, "commit", "-qm", "DADOS SIMULADOS: fonte e mandato da réplica de teste")
    git(repo, "branch", "cdp-trava")
    origin = root / "origin.git"
    subprocess.run(["git", "clone", "--quiet", "--bare", "--no-hardlinks", str(repo), str(origin)], cwd=root,
                   check=True)
    git(repo, "remote", "add", "origin", str(origin))
    return repo, origin, lock


@pytest.fixture
def replica(template, tmp_path):
    fonte, origin, lock = template
    root = tmp_path / "replica"
    shutil.copytree(fonte, root, copy_function=shutil.copy2)
    cfg = load_config(root / "configs/cdp/fund.yaml")
    rt = Runtime(cfg, root / "book", root / "market", root / "reports", clock=lambda: NOW)
    head = git(root, "rev-parse", "HEAD")
    reg = {"tarefa": "cdp-diario", "inicio": NOW.isoformat(), "head": head, "trava": TRAVA,
           "ensaio": False, "sem_trava": False, "mente": "codex", "instantaneo": {}}
    # Fixture explicitamente sintética do contrato de registro. Não chamamos gate.
    ex.registrar_execucao(root, EXECUCAO, reg)
    return root, rt, reg, dict(lock)


def abrir(rt, **kw):
    return g.executar(rt, execucao=EXECUCAO, trava=TRAVA, env=ENV, **kw)


def assert_recusa_literal(root, rt, **kw):
    before = tree(root)
    code, out = g.executar(rt, execucao=kw.pop("execucao", EXECUCAO),
                           trava=kw.pop("trava", TRAVA), env=kw.pop("env", ENV))
    assert code == 1 and not out["executado"]
    assert tree(root) == before and not (root / g.STAGING_NAME).exists()
    return out


def test_plano_vazio_nao_cria_diretorio_ou_arquivo(tmp_path):
    cfg = load_config(ROOT / "configs/cdp/fund.yaml")
    rt = Runtime(cfg, tmp_path / "ainda-inexistente/book", tmp_path / "market", tmp_path / "reports")
    before = tree(tmp_path)
    assert g.plano(rt)["estado"] == "vazio"
    assert tree(tmp_path) == before and not rt.book_root.parent.exists()
    # O caminho legado mantém sua semântica, sem nova rotina automática.
    assert plano_legado(rt).estado == "nada"
    assert situacao(rt) == {"pendente": False, "motivo": None}


@pytest.mark.parametrize("diretorio_vazio", [False, True])
def test_api_real_promove_so_genese_e_evento_com_trava_nativa_local(replica, diretorio_vazio):
    root, rt, reg, lock = replica
    if diretorio_vazio:
        rt.book_root.mkdir()
    cfg_hash = load_config(root / "configs/cdp/fund.yaml").config_hash()
    head = git(root, "rev-parse", "HEAD")
    code, out = abrir(rt)
    assert code == 0 and out["executado"] and out["estado"] == "iniciado"
    assert sorted(p.name for p in rt.book_root.iterdir()) == ["audit_log.jsonl", "genese.json"]
    payload = json.loads((rt.book_root / "genese.json").read_text())
    assert payload == {"inception_date": "2026-10-09", "config_hash": cfg_hash,
                       "codigo": head, "ancora_sha256": None}
    book = Book(rt.book_root, config=rt.cfg)
    event, = book.audit.events()
    assert (event.event_type, event.seq, event.prev_hash) == (GENESIS_EVENT, 0, GENESIS_HASH)
    assert event.payload_hash == sha256_obj(payload) and event.ts == NOW
    assert book.verify_integrity() == (True, [])
    assert out["autoridade"]["trava"] == TRAVA
    assert not (root / g.STAGING_NAME).exists()
    assert not rt.market_root.exists() and not rt.reports_root.exists()


def test_repeticao_integra_preserva_bytes_timestamps_e_ancora_original(replica):
    root, rt, _, _ = replica
    assert abrir(rt)[0] == 0
    before = tree(root)
    metas = {p.name: p.stat().st_mtime_ns for p in rt.book_root.iterdir()}
    # Ler uma gênese não requer nova trava; sem gravação e sem adotar configuração nova.
    code, out = g.executar(rt, env={})
    assert code == 0 and not out["executado"]
    assert tree(root) == before and metas == {p.name: p.stat().st_mtime_ns
                                             for p in rt.book_root.iterdir()}


def test_livro_nativo_recusa_chave_anterior_ao_inicio(replica):
    _, rt, _, _ = replica
    assert abrir(rt)[0] == 0
    with pytest.raises(ValueError, match="anterior"):
        Book(rt.book_root, config=rt.cfg).check_key(date(2026, 10, 2))
    Book(rt.book_root, config=rt.cfg).check_key(date(2026, 10, 9))


@pytest.mark.parametrize("arquivo", ["audit_log.jsonl", "herdado.json", ".gitkeep",
                                    "2026-10-02/booked.json", "2026-10-09/proposal_v1.json"])
def test_nao_adota_nem_remove_livro_sem_genese(replica, arquivo):
    root, rt, _, _ = replica
    path = rt.book_root / arquivo
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("DADOS SIMULADOS: não remover\n")
    out = assert_recusa_literal(root, rt)
    assert out["estado"] == "conflito"


def test_kill_switch_permanece_ativo(replica):
    root, rt, _, _ = replica
    rt.book_root.mkdir()
    (rt.book_root / "KILL_SWITCH").write_text("não desligar\n")
    out = assert_recusa_literal(root, rt)
    assert "kill switch" in out["motivo"]


@pytest.mark.parametrize("env", [{}, {"CDP_EXECUTOR": "claude-cloud"},
                                  {"CDP_EXECUTOR": "codex"}, {**ENV, "CDP_ENSAIO": "1"}])
def test_identidade_invalida_outro_executor_e_ensaio_nao_gravam(replica, env):
    root, rt, _, _ = replica
    assert_recusa_literal(root, rt, env=env)


@pytest.mark.parametrize(("execucao", "trava"), [(None, TRAVA), (EXECUCAO, None),
                                                 ("../emprestada", TRAVA), (EXECUCAO, "../trava")])
def test_exige_ids_proprios_sem_escape_de_caminho(replica, execucao, trava):
    root, rt, _, _ = replica
    assert_recusa_literal(root, rt, execucao=execucao, trava=trava)


@pytest.mark.parametrize("alteracao", [{"ensaio": True}, {"sem_trava": True},
                                      {"head": "0" * 40}, {"trava": "outra"},
                                      {"tarefa": "cdp-status"}, {"tarefa": "cdp-risco-1330"},
                                      {"tarefa": "cdp-cobertura"}])
def test_execucao_precisa_ser_exclusiva_mesmo_head_trava_e_escopo(replica, alteracao):
    root, rt, reg, _ = replica
    ex.registrar_execucao(root, EXECUCAO, {**reg, **alteracao})
    assert_recusa_literal(root, rt)


@pytest.mark.parametrize("alteracao", [{"id": "outra"}, {"executor": "claude-cloud"},
                                      {"tarefa": "cdp-semanal"}, {"harness": "gemini"},
                                      {"estado": "livre"}, {"expira": NOW.isoformat()},
                                      {"expira": "2026-10-09T11:00:00"},
                                      {"expira": "inválido"}])
def test_trava_incompativel_vencida_ou_sem_fuso_nao_grava(replica, monkeypatch, alteracao):
    root, rt, _, lock = replica
    # Controle do corpo do transporte, declarado; o positivo usa trava_ler real/local.
    monkeypatch.setattr(ex, "trava_ler", lambda *a: ({**lock, **alteracao}, "ponta", None))
    assert_recusa_literal(root, rt)


def test_remoto_da_trava_indisponivel_nao_grava(replica, monkeypatch):
    root, rt, _, _ = replica
    monkeypatch.setattr(ex, "trava_ler", lambda *a: (None, None, "falha de transporte simulada"))
    assert_recusa_literal(root, rt)


@pytest.mark.parametrize("remote", [None, {"executor": "claude-cloud"}])
def test_designacao_remota_indisponivel_ou_trocada_nao_grava(replica, monkeypatch, remote):
    root, rt, _, _ = replica
    monkeypatch.setattr(ex, "executor_remoto", lambda *a, **kw: remote)
    assert_recusa_literal(root, rt)


@pytest.mark.parametrize("tipo", ["branch", "commit_local"])
def test_so_main_sincronizado_pode_abrir_replica(replica, tipo):
    root, rt, reg, _ = replica
    if tipo == "branch":
        git(root, "checkout", "-qb", "codex/teste-genese")
    else:
        git(root, "commit", "--allow-empty", "-qm", "DADOS SIMULADOS: commit ainda não publicado")
        ex.registrar_execucao(root, EXECUCAO, {**reg, "head": git(root, "rev-parse", "HEAD")})
    assert_recusa_literal(root, rt)


@pytest.mark.parametrize("tipo", ["runtime", "arquivo", "codigo"])
def test_mandato_e_codigo_do_clone_precisam_estar_registrados(replica, tipo):
    root, rt, _, _ = replica
    if tipo == "runtime":
        rt.cfg = rt.cfg.with_overrides({"fund": {"inception_date": date(2026, 10, 16)}})
    elif tipo == "arquivo":
        with (root / "configs/cdp/fund.yaml").open("a") as f:
            f.write("\n# alteração não registrada\n")
    else:
        with (root / "src/cdp/workflow/genese.py").open("a") as f:
            f.write("\n# alteração não registrada\n")
    assert_recusa_literal(root, rt)


def test_area_interrompida_preexistente_nao_e_limpa(replica):
    root, rt, _, _ = replica
    temp = root / g.STAGING_NAME
    temp.mkdir()
    (temp / "preservar.json").write_text("{}\n")
    before = tree(root)
    code, out = abrir(rt)
    assert code == 1 and "interrompida" in out["motivo"] and tree(root) == before


@pytest.mark.parametrize("alvo", ["book", "genese", "audit"])
def test_links_nao_emprestam_livro_ou_trilha(replica, alvo):
    root, rt, _, _ = replica
    if alvo == "book":
        other = root / "terceiro"
        other.mkdir()
        rt.book_root.symlink_to(other, target_is_directory=True)
    else:
        assert abrir(rt)[0] == 0
        name = "genese.json" if alvo == "genese" else "audit_log.jsonl"
        actual = rt.book_root / name
        other = root / "terceiro.json"
        shutil.copy2(actual, other)
        actual.unlink()
        actual.symlink_to(other)
    assert_recusa_literal(root, rt)


@pytest.mark.parametrize("tipo", ["payload", "evento", "sem_evento", "duplicada", "data"])
def test_genese_parcial_divergente_ou_adulterada_nao_e_reparada(replica, tipo):
    root, rt, _, _ = replica
    assert abrir(rt)[0] == 0
    path = rt.book_root / "genese.json"
    audit = rt.book_root / "audit_log.jsonl"
    payload = json.loads(path.read_text())
    if tipo == "payload":
        payload["config_hash"] = "0" * 64
        path.write_text(json.dumps(payload))
    elif tipo == "evento":
        ev = json.loads(audit.read_text())
        ev["summary"] = "adulteração simulada"
        audit.write_text(json.dumps(ev) + "\n")
    elif tipo == "sem_evento":
        audit.unlink()
    elif tipo == "duplicada":
        Book(rt.book_root).audit.append(GENESIS_EVENT, "CDP", payload, ts=NOW)
    else:
        payload["inception_date"] = "2026-10-16"
        path.write_text(json.dumps(payload))
    assert_recusa_literal(root, rt)


@pytest.mark.parametrize("momento", ["audit", "verificacao", "rename", "interrupcao"])
def test_falha_pre_promocao_preserva_destino_vazio(replica, monkeypatch, momento):
    root, rt, _, _ = replica
    rt.book_root.mkdir()
    before = tree(root)
    if momento == "audit":
        monkeypatch.setattr(g.AuditLog, "append", lambda *a, **kw: (_ for _ in ()).throw(OSError("teste")))
    elif momento == "verificacao":
        monkeypatch.setattr(Book, "verify_integrity", lambda *a: (False, ["falha simulada"]))
    else:
        error = KeyboardInterrupt if momento == "interrupcao" else OSError
        monkeypatch.setattr(g.os, "rename", lambda *a: (_ for _ in ()).throw(error("teste")))
    if momento == "interrupcao":
        with pytest.raises(KeyboardInterrupt):
            abrir(rt)
    else:
        assert abrir(rt)[0] == 1
    assert tree(root) == before and not (root / g.STAGING_NAME).exists()


def test_destino_alterado_durante_preparo_e_preservado(replica, monkeypatch):
    root, rt, _, _ = replica
    original = g._autoridade
    calls = []

    def concurrent(*args):
        out = original(*args)
        calls.append(True)
        if len(calls) == 2:
            rt.book_root.mkdir()
            (rt.book_root / "nao-remover.json").write_text("concorrência simulada\n")
        return out

    monkeypatch.setattr(g, "_autoridade", concurrent)
    assert abrir(rt)[0] == 1
    assert (rt.book_root / "nao-remover.json").read_text() == "concorrência simulada\n"
    assert not (rt.book_root / "genese.json").exists()
    assert not (root / g.STAGING_NAME).exists()


def test_race_no_instante_da_promocao_nao_substitui_conteudo(replica, monkeypatch):
    root, rt, _, _ = replica
    original = g.os.rename

    def rename_com_concorrente(src, dst):
        rt.book_root.mkdir()
        (rt.book_root / "concorrente.txt").write_text("preservar\n")
        return original(src, dst)  # sistema de arquivos recusa diretório destino não vazio

    monkeypatch.setattr(g.os, "rename", rename_com_concorrente)
    assert abrir(rt)[0] == 1
    assert sorted(p.name for p in rt.book_root.iterdir()) == ["concorrente.txt"]
    assert (rt.book_root / "concorrente.txt").read_text() == "preservar\n"
    assert not (root / g.STAGING_NAME).exists()


def test_trava_perdida_durante_preparo_nao_promove_genese(replica, monkeypatch):
    root, rt, _, lock = replica
    calls = []

    def transporte(*args):
        calls.append(True)
        return (lock if len(calls) == 1 else {"estado": "livre"}), "ponta", None

    monkeypatch.setattr(ex, "trava_ler", transporte)
    assert abrir(rt)[0] == 1
    assert not rt.book_root.exists() and not (root / g.STAGING_NAME).exists()


def test_cli_plano_apenas_le_e_execucao_sem_ids_recusa(replica, monkeypatch, capsys):
    root, rt, _, _ = replica
    monkeypatch.chdir(root)
    argv = ["--config", str(root / "configs/cdp/fund.yaml"), "--book", str(rt.book_root),
            "--market", str(rt.market_root), "--reports", str(rt.reports_root), "genese"]
    before = tree(root)
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["estado"] == "vazio"
    assert main([*argv, "--executar"]) == 1
    assert not json.loads(capsys.readouterr().out)["executado"]
    assert tree(root) == before


def test_cli_explicita_abre_somente_clone_sintetico_com_ids_validos(replica, monkeypatch, capsys):
    root, rt, _, _ = replica
    monkeypatch.chdir(root)
    monkeypatch.setenv("CDP_EXECUTOR", "local-pc")
    monkeypatch.setenv("CDP_HARNESS", "codex")
    monkeypatch.delenv("CDP_ENSAIO", raising=False)
    monkeypatch.setattr(Runtime, "now", lambda self: NOW)
    argv = ["--config", str(root / "configs/cdp/fund.yaml"), "--book", str(rt.book_root),
            "--market", str(rt.market_root), "--reports", str(rt.reports_root), "genese",
            "--executar", "--execucao", EXECUCAO, "--trava", TRAVA]
    assert main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["executado"] and out["genese"]["codigo"] == git(root, "rev-parse", "HEAD")
    assert Book(rt.book_root).verify_integrity() == (True, [])


def test_documentacao_candidata_cita_cli_real_sem_abertura_automatica():
    doc = (ROOT / "docs/cdp/REPLICAR.md").read_text()
    assert "a CLI ainda não tem um comando" not in doc
    assert "Sem pendência exclusiva" in doc and "não cria um gate nem uma nova rotina" in doc
    for argv in (["genese"], ["genese", "--executar", "--execucao", EXECUCAO, "--trava", TRAVA]):
        args = build_parser().parse_args(argv)
        assert args.cmd == "genese" and args.func.__name__ == "cmd_genese"
