"""Contrato da CLI e das interfaces congeladas no W0 (DESIGN §2.3 e §3.6).

- Cada comando novo está registrado com os argumentos finais (datas validadas, IIDs seguros para
  caminhos, flags) e argumentos obrigatórios ausentes são recusados pelo parser.
- Enquanto o handler do comando é um stub, o comando responde "em implementação" com código 2
  (o teste decide por handler: deixa de exigir isso quando o dono substitui AQUELE stub, mesmo
  que outros comandos do mesmo módulo ainda sejam stubs).
- As interfaces entre workstreams têm as assinaturas do contrato; os stubs levantam
  ``NotImplementedError`` (nunca devolvem um valor inventado).
- Só dados públicos (DESIGN §15.3): nenhum canal de dados proprietário nos contratos, no esquema
  publicado para a mente nem na CLI. As opções ``--mind`` vêm de ``contracts.HARNESS_MINDS``.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from datetime import date
from pathlib import Path

import pytest

from cdp.__main__ import build_parser, main

D = "2026-10-09"

# (argv, "módulo:handler" dono, atributos esperados no Namespace)
COMMANDS = [
    (["cobertura", "run", "--date", D], "cdp.cobertura.cli:cmd_run",
     {"cmd": "cobertura", "action": "run", "date": date(2026, 10, 9), "emissores": None,
      "offline": False}),
    (["cobertura", "run", "--date", D, "--emissores", "BR_VALE,ETF_EWZ,SIM001", "--offline"],
     "cdp.cobertura.cli:cmd_run",
     {"emissores": ("BR_VALE", "ETF_EWZ", "SIM001"), "offline": True}),
    (["cobertura", "verify"], "cdp.cobertura.cli:cmd_verify",
     {"cmd": "cobertura", "action": "verify"}),
    (["nota", "agenda"], "cdp.workflow.notas:cmd_agenda",
     {"cmd": "nota", "action": "agenda", "date": None}),
    (["nota", "agenda", "--date", D], "cdp.workflow.notas:cmd_agenda",
     {"date": date(2026, 10, 9)}),
    (["nota", "prepare", "--issuer", "BR_VALE"], "cdp.workflow.notas:cmd_prepare",
     {"action": "prepare", "issuer": "BR_VALE", "date": None}),
    (["nota", "prepare", "--issuer", "BR_VALE", "--date", D], "cdp.workflow.notas:cmd_prepare",
     {"date": date(2026, 10, 9)}),
    (["nota", "publish", "--issuer", "BR_VALE", "--date", D], "cdp.workflow.notas:cmd_publish",
     {"action": "publish", "issuer": "BR_VALE", "date": date(2026, 10, 9)}),
    (["validate-nota", "--issuer", "BR_VALE", "--date", D], "cdp.workflow.notas:cmd_validate",
     {"cmd": "validate-nota", "issuer": "BR_VALE", "date": date(2026, 10, 9)}),
    (["weekly", "close-report", "--date", D], "cdp.workflow.relatorio_semanal:cmd_close_report",
     {"cmd": "weekly", "action": "close-report", "date": date(2026, 10, 9), "publish": False}),
    (["weekly", "close-report", "--date", D, "--publish"],
     "cdp.workflow.relatorio_semanal:cmd_close_report", {"publish": True}),
    (["validate-weekly-report", "--date", D], "cdp.workflow.relatorio_semanal:cmd_validate",
     {"cmd": "validate-weekly-report", "date": date(2026, 10, 9)}),
    (["reinicio"], "cdp.workflow.reinicio:cmd_reinicio", {"cmd": "reinicio", "executar": False}),
    (["reinicio", "--executar"], "cdp.workflow.reinicio:cmd_reinicio",
     {"cmd": "reinicio", "executar": True}),
]

INVALID = [
    ["cobertura", "run"],                                       # --date obrigatório
    ["cobertura", "run", "--date", "2026-13-01"],               # data inválida
    ["cobertura", "run", "--date", D, "--emissores", "BR_VALE,,BR_ITAU"],
    ["cobertura", "run", "--date", D, "--emissores", "BR_VALE,BR_VALE"],
    ["cobertura", "run", "--date", D, "--emissores", "../etc"],
    ["cobertura"],
    ["nota", "prepare"],                                        # --issuer obrigatório
    ["nota", "prepare", "--issuer", "br_vale"],                 # IID minúsculo
    ["nota", "prepare", "--issuer", "BR/VALE"],
    ["nota", "publish", "--issuer", "BR_VALE"],                 # --date obrigatório
    ["validate-nota", "--issuer", "BR_VALE"],
    ["weekly", "close-report"],
    ["validate-weekly-report"],
    ["reinicio", "--executar", "sim"],                          # flag sem valor
    ["reinicio", "--dry-run"],                                  # simulação é o padrão
]


def _handler(owner: str):
    module, name = owner.split(":")
    return getattr(importlib.import_module(module), name)


def _is_stub(handler) -> bool:
    """Stub = o handler ainda responde pela função ``_em_implementacao`` do módulo dono."""
    return "_em_implementacao" in inspect.getsource(handler)


@pytest.mark.parametrize(("argv", "module", "expected"), COMMANDS)
def test_new_commands_parse_with_final_arguments(argv, module, expected):
    args = build_parser().parse_args(argv)
    for key, value in expected.items():
        assert getattr(args, key) == value, (argv, key)
    assert callable(args.func)


@pytest.mark.parametrize("argv", INVALID)
def test_new_commands_reject_bad_arguments(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(argv)
    assert exc.value.code == 2
    capsys.readouterr()


def _subparsers(p: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    act = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    return dict(act.choices)


def _all_parsers(p: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    yield path, p
    for a in p._actions:
        if isinstance(a, argparse._SubParsersAction):
            for name, sp in a.choices.items():
                yield from _all_parsers(sp, (*path, name))


def test_new_commands_listed_in_the_parser():
    sub = _subparsers(build_parser())
    assert {"cobertura", "nota", "validate-nota", "validate-weekly-report", "reinicio"} <= set(sub)
    assert set(_subparsers(sub["weekly"])) == {"prepare", "preview", "decide", "close-report"}
    assert set(_subparsers(sub["cobertura"])) == {"run", "verify"}
    assert set(_subparsers(sub["nota"])) == {"agenda", "prepare", "publish"}


@pytest.mark.parametrize(("argv", "owner", "expected"), COMMANDS)
def test_stub_commands_exit_2_until_implemented(argv, owner, expected, tmp_path, capsys):
    if not _is_stub(_handler(owner)):
        pytest.skip(f"{owner} já implementado pelo dono (testes próprios)")
    base = ["--book", str(tmp_path / "book"), "--market", str(tmp_path / "market"),
            "--reports", str(tmp_path / "reports")]
    rc = main(base + argv)
    err = capsys.readouterr().err
    assert rc == 2 and "em implementação" in err, (argv, err)
    assert not (tmp_path / "book").exists()  # stub não grava nada


@pytest.mark.parametrize(("argv", "owner", "expected"), COMMANDS)
def test_cli_dispatches_to_the_owner_handler(argv, owner, expected, monkeypatch):
    """O handler registrado chama a função do módulo dono (resolvida na hora da chamada), então
    o dono entrega um comando por vez sem tocar na CLI."""
    module, name = owner.split(":")
    seen = []
    monkeypatch.setattr(importlib.import_module(module), name,
                        lambda args: seen.append(args) or 0)
    args = build_parser().parse_args(argv)
    assert args.func(args) == 0 and seen == [args]


def _em_implementacao(comando: str) -> int:  # mesmo nome do stub dos módulos donos
    print(f"cdp {comando}: em implementação.", file=sys.stderr)
    return 2


def test_stub_detection_is_per_handler(monkeypatch, tmp_path, capsys):
    """Num módulo com um comando entregue e outro ainda stub, só o stub é exigido (independe do
    andamento real do dono: os dois handlers são simulados)."""
    from cdp.cobertura import cli

    def entregue(args: argparse.Namespace) -> int:
        return 0

    def pendente(args: argparse.Namespace) -> int:
        return _em_implementacao("cobertura verify")

    monkeypatch.setattr(cli, "cmd_run", entregue)
    monkeypatch.setattr(cli, "cmd_verify", pendente)
    assert not _is_stub(_handler("cdp.cobertura.cli:cmd_run"))
    assert _is_stub(_handler("cdp.cobertura.cli:cmd_verify"))
    assert main(["--book", str(tmp_path / "book"), "cobertura", "run", "--date", D]) == 0
    assert main(["--book", str(tmp_path / "book"), "cobertura", "verify"]) == 2
    assert "em implementação" in capsys.readouterr().err


# ----------------------------------------------------------------------------- dados públicos


def test_no_proprietary_data_channel_in_contracts_or_cli():
    """DESIGN §15.3: nenhum membro de evidência, esquema publicado para a mente, comando ou
    opção da CLI cita o canal proprietário removido."""
    from cdp.contracts import EvidenceKind, EvidenceRef, ResearchPack

    banned = "quartr"
    assert {k.value for k in EvidenceKind} == {"fact", "news", "source"}
    assert EvidenceRef.model_fields["ref_id"].description == "fact_id, news_id ou URL"
    for model in (ResearchPack, EvidenceRef):
        assert banned not in json.dumps(model.model_json_schema(), ensure_ascii=False).lower()
    for path, parser in _all_parsers(build_parser()):
        assert banned not in " ".join(path).lower()
        assert banned not in parser.format_help().lower(), path
    root = Path(__file__).resolve().parents[2]
    assert ".cdp_cache" not in (root / ".gitignore").read_text(encoding="utf-8")


def test_mind_choices_come_from_harness_minds():
    from cdp.contracts import HARNESS_MINDS, ResearchPack

    found = []
    for path, parser in _all_parsers(build_parser()):
        for a in parser._actions:
            if "--mind" in a.option_strings:
                found.append(path)
                assert tuple(a.choices) == HARNESS_MINDS, path
    assert sorted(found) == [("daily",), ("validate",), ("weekly", "decide"),
                             ("weekly", "prepare"), ("weekly", "preview")]
    desc = ResearchPack.model_fields["mind"].description
    assert all(m in desc for m in HARNESS_MINDS)


# ----------------------------------------------------------------------------- interfaces §2.3


def _params(fn) -> list[tuple[str, str]]:
    return [(p.name, p.kind.name) for p in inspect.signature(fn).parameters.values()]


def test_execucao_contract():
    from cdp.portfolio import execucao as ex

    assert [f.name for f in ex.JanelaExecucao.__dataclass_fields__.values()] == [
        "sessao", "abertos", "fechamentos", "corte_moc", "prazo_decisao",
        "fechamento_antecipado", "multiplicador_capacidade"]
    assert ex.JanelaExecucao.__dataclass_params__.frozen
    pk = "POSITIONAL_OR_KEYWORD"
    assert _params(ex.janela_execucao) == [("sessao", pk), ("cfg", pk)]
    assert _params(ex.capacidade_fechamento_usd) == [
        ("lines", pk), ("md", pk), ("janela", pk), ("cfg", pk), ("lado", "KEYWORD_ONLY")]
    assert _params(ex.emissores_congelados) == [("sides", pk), ("atual", pk), ("janela", pk),
                                                ("cfg", pk)]
    assert _params(ex.fechamentos_necessarios) == [("nocional_usd", pk), ("capacidade_usd", pk)]


def test_idio_and_cobertura_contracts():
    from cdp.cobertura import fatos, livro, sinal
    from cdp.risk import idio

    pk = "POSITIONAL_OR_KEYWORD"
    assert _params(idio.serie_idio) == [("records", pk), ("md", pk), ("cfg", pk)]
    assert _params(idio.decomposicao_decisao) == [("proposal", pk)]
    assert idio.CHAVE_RISCO == "risco"
    assert idio.GRUPOS_IDIO == ("mercado", "pais", "setor", "estilo", "macro", "especifico")
    assert _params(livro.ultimo_snapshot) == [("root", pk), ("ate", pk)]
    assert _params(fatos.factbook_emissor) == [("snap", pk), ("issuer_id", pk), ("md", pk)]
    assert _params(sinal.valuation_gap) == [("snap", pk)]
    snap = livro.SnapshotCobertura(as_of=date(2026, 10, 9), pasta=Path("x"))
    assert snap.manifest == {} and snap.is_synthetic is False


def test_stub_interfaces_raise_not_implemented():
    """Um stub nunca devolve um número inventado: ou o dono implementou, ou falha alto."""
    from cdp.cobertura import fatos, livro, sinal
    from cdp.portfolio import execucao as ex
    from cdp.risk import idio

    calls = [
        (ex, "janela_execucao", (date(2026, 10, 9), None), {}),
        (ex, "capacidade_fechamento_usd", (None, None, None, None), {"lado": "long"}),
        (ex, "emissores_congelados", (None, None, None, None), {}),
        (ex, "fechamentos_necessarios", (1.0, 0.0), {}),
        (idio, "serie_idio", ((), None, None), {}),
        (idio, "decomposicao_decisao", (None,), {}),
        (livro, "ultimo_snapshot", (Path("x"), date(2026, 10, 9)), {}),
        (fatos, "factbook_emissor", (None, "BR_VALE", None), {}),
        (sinal, "valuation_gap", (None,), {}),
    ]
    for module, name, args, kwargs in calls:
        fn = getattr(module, name)
        src = inspect.getsource(fn)
        if "NotImplementedError" not in src:
            continue  # implementado pelo dono
        with pytest.raises(NotImplementedError, match="em implementação"):
            fn(*args, **kwargs)


def test_painel_artifact_check_moved_and_reexported():
    import cdp.__main__ as cli
    from cdp.workflow import painel_artifact

    assert cli.painel_artifact_check is painel_artifact.painel_artifact_check
    assert "painel_artifact_check" not in {
        name for name, obj in vars(cli).items()
        if inspect.isfunction(obj) and obj.__module__ == "cdp.__main__"}
