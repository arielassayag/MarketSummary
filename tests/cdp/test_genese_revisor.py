"""DADOS SIMULADOS: perda de autoridade após preparo, em Git local privado."""
from datetime import timedelta

import pytest
from test_genese_replica import ENV, EXECUCAO, TRAVA
from test_genese_replica import replica as replica
from test_genese_replica import template as template

from cdp import executor as ex
from cdp.workflow import genese as g
from cdp.workflow.book import Book
from cdp.workflow.runtime import Runtime


def apos_preparo(monkeypatch, alterar):
    original = Book.verify_integrity
    calls = []

    def verificar(book):
        out = original(book)
        assert out == (True, [])
        calls.append(True)
        assert len(calls) == 1
        alterar()
        return out

    monkeypatch.setattr(Book, 'verify_integrity', verificar)
    return calls


def recusa_sem_promocao(root, rt):
    code, out = g.executar(rt, execucao=EXECUCAO, trava=TRAVA, env=ENV)
    assert code == 1 and not out['executado']
    assert not rt.book_root.exists() and not (root / g.STAGING_NAME).exists()
    return out


@pytest.mark.parametrize('camada', ['mandato', 'execucao'])
def test_releitura_recusa_mandato_ou_registro_alterado_apos_preparo(replica, monkeypatch, camada):
    root, rt, reg, _ = replica
    cfg = root / 'configs/cdp/fund.yaml'
    texto = cfg.read_text()

    def alterar():
        if camada == 'mandato':
            cfg.write_text(texto + '\n# DADOS SIMULADOS: mudança após preparo\n')
        else:
            ex.registrar_execucao(root, EXECUCAO, {**reg, 'tarefa': 'cdp-status'})

    calls = apos_preparo(monkeypatch, alterar)
    recusa_sem_promocao(root, rt)
    assert len(calls) == 1
    if camada == 'mandato':
        assert cfg.read_text().endswith('# DADOS SIMULADOS: mudança após preparo\n')
    else:
        assert ex.ler_execucao(root, EXECUCAO)['tarefa'] == 'cdp-status'


def test_kill_switch_torna_se_ativo_apos_preparo_e_nao_e_desligado(replica, monkeypatch):
    root, rt, _, _ = replica
    active = [False]
    monkeypatch.setattr(Runtime, 'kill_switch_active', lambda self: active[0])
    calls = apos_preparo(monkeypatch, lambda: active.__setitem__(0, True))
    recusa_sem_promocao(root, rt)
    assert len(calls) == 1 and active[0] is True


def test_trava_expira_apos_preparo_e_nao_promove(replica, monkeypatch):
    root, rt, _, _ = replica
    clock = rt.now()

    def avancar():
        rt.clock = lambda: clock + timedelta(hours=2)

    calls = apos_preparo(monkeypatch, avancar)
    recusa_sem_promocao(root, rt)
    assert len(calls) == 1 and rt.now() == clock + timedelta(hours=2)
