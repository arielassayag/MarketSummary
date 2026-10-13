"""F04: concorrência real entre processos sobre ledger de DADOS SIMULADOS."""

import multiprocessing
from threading import BrokenBarrierError

import pytest

from cdp.audit import AuditLog
from cdp.workflow.leitura_contratos import TentativaDeEfeitoLeitura


def _append_worker(path, start):
    start.wait(timeout=10)
    AuditLog(path).append("TESTE", "fixture", {"aviso": "DADOS SIMULADOS"}, "DADOS SIMULADOS")


def test_f04_tail_and_append_are_serialized_between_processes(tmp_path, monkeypatch):
    context = multiprocessing.get_context("fork")
    start = context.Barrier(2)
    tails = context.Barrier(2)
    native = AuditLog.events

    def interleaved_tail(self):
        events = native(self)
        try:
            tails.wait(timeout=1)
        except BrokenBarrierError:
            pass  # com lock, o segundo processo só lê após o primeiro anexar
        return events

    monkeypatch.setattr(AuditLog, "events", interleaved_tail)
    path = tmp_path / "DADOS_SIMULADOS" / "audit.jsonl"
    workers = [context.Process(target=_append_worker, args=(path, start)) for _ in range(2)]
    try:
        for process in workers:
            process.start()
        for process in workers:
            process.join(timeout=15)
            assert process.exitcode == 0
    finally:
        for process in workers:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
    monkeypatch.setattr(AuditLog, "events", native)
    log = AuditLog(path)
    assert [event.seq for event in log.events()] == [0, 1]
    assert log.verify_chain()[0]


def test_readonly_audit_refuses_before_file_or_lock_creation(tmp_path):
    parent = tmp_path / "nao_criado"
    log = AuditLog(parent / "audit.jsonl", somente_leitura=True)
    with pytest.raises(TentativaDeEfeitoLeitura):
        log.append("TESTE", "fixture", {"aviso": "DADOS SIMULADOS"})
    assert not parent.exists()
