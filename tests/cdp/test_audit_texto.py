"""DADOS SIMULADOS: reutilização de prova nunca substitui leitura física."""
import hashlib
import json
import os

import pytest

from cdp.audit import AuditLog
from cdp.leitura_arquivos import ReceptorArquivos, ativar_receptor
from cdp.workflow.leitura_contratos import TentativaDeEfeitoLeitura


def test_repeated_audit_detects_same_size_and_mtime_tampering(tmp_path):
    log=AuditLog(tmp_path/'audit.jsonl')
    log.append('TESTE','teste',{},'DADOS SIMULADOS A')
    assert log.verify_chain()[0]
    stat=log.path.stat()
    original=log.path.read_text()
    log.path.write_text(original.replace('SIMULADOS A','SIMULADOS B'))
    os.utime(log.path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    assert not log.verify_chain()[0]
    log.path.write_text(original)
    assert log.verify_chain()[0]
    log.append('TESTE','teste',{},'DADOS SIMULADOS B')
    assert log.verify_chain()[0]
    rows=log.path.read_text().splitlines()
    log.path.write_text(rows[-1]+'\n')
    assert not log.verify_chain()[0]


def test_warm_proof_does_not_bypass_nominal_receiver(tmp_path):
    root=tmp_path.resolve()
    log=AuditLog(root/'audit.jsonl')
    log.append('TESTE','teste',{},'DADOS SIMULADOS')
    assert log.verify_chain()[0]
    receiver=ReceptorArquivos({'book':root},{'audit':('book','audit.jsonl',
        hashlib.sha256(log.path.read_bytes()).hexdigest())})
    with ativar_receptor(receiver):
        assert AuditLog(log.path,somente_leitura=True).verify_chain()[0]
    log.append('TESTE','teste',{},'DADOS SIMULADOS NOVOS')
    with ativar_receptor(receiver),pytest.raises(TentativaDeEfeitoLeitura):
        AuditLog(log.path,somente_leitura=True).verify_chain()


def test_missing_empty_lines_and_invalid_json_keep_contract(tmp_path):
    log=AuditLog(tmp_path/'audit.jsonl')
    assert log.verify_chain()[0]
    log.path.write_text('\n  \n')
    assert log.verify_chain()[0]
    log.append('TESTE','teste',{},'DADOS SIMULADOS')
    assert log.verify_chain()[0]
    log.path.write_text(json.dumps({'broken':'DADOS SIMULADOS'}))
    with pytest.raises(ValueError):
        log.verify_chain()


def test_invalid_late_json_is_parsed_before_earlier_chain_failure(tmp_path):
    log=AuditLog(tmp_path/'audit.jsonl')
    log.append('TESTE','teste',{},'DADOS SIMULADOS A')
    raw=log.path.read_text().replace('SIMULADOS A','SIMULADOS B')
    log.path.write_text(raw+'{"invalido": true}\n')
    with pytest.raises(ValueError):
        log.verify_chain()
