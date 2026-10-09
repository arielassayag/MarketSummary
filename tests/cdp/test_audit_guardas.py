"""DADOS SIMULADOS: guardas recusam efeitos reais e deixam de contar depois do contexto."""
import importlib
import socket
import subprocess
import sys

import pytest


@pytest.fixture(params=[('test_eps_fronteira_receita_v3', 'guarda', RuntimeError),
                        ('test_eps_fronteira_receita_nao_autor', 'sem_efeitos', AssertionError),
                        ('test_cvm_comparativos_revisor', 'guarded', RuntimeError)])
def papel(request):
    module, name, error = request.param
    return getattr(importlib.import_module(module), name), error


def proibidos(state):
    if 'forbidden' in state:
        return len(state['forbidden'])
    return sum(state[k] for k in ('write', 'network', 'process', 'mutation'))


def test_leitura_real_contada_sem_efeito(papel, tmp_path):
    guard, _ = papel
    path = tmp_path / 'dados_simulados.txt'
    path.write_text('DADOS SIMULADOS: controle de leitura')
    with guard() as state:
        assert path.read_text() == 'DADOS SIMULADOS: controle de leitura'
    assert state['reads'] == 1 and proibidos(state) == 0
    assert state['active'] is False


@pytest.mark.parametrize('effect', ['write', 'socket', 'process', 'mutation'])
def test_recusa_antes_do_efeito_observavel(papel, tmp_path, effect):
    guard, error = papel
    marker = tmp_path / 'efeito_dados_simulados'
    sock = socket.socket() if effect == 'socket' else None
    context = guard()
    state = context.__enter__()
    try:
        with pytest.raises(error, match='Guarda API|Efeito vedado'):
            if effect == 'write':
                marker.write_text('DADOS SIMULADOS: escrita deve ser recusada')
            elif effect == 'socket':
                sock.connect(('127.0.0.1', 9))
            elif effect == 'process':
                subprocess.run([sys.executable, '-B', '-c',
                    'import sys; from pathlib import Path; Path(sys.argv[1]).write_text("DADOS SIMULADOS: processo")',
                    str(marker)], check=True)
            else:
                marker.mkdir()
    finally:
        with pytest.raises(AssertionError):  # assertiva final original conserva evidência de tentativa
            context.__exit__(None, None, None)
        if sock is not None:
            sock.close()
    assert not marker.exists() and state['active'] is False
    assert proibidos(state) == 1
    if 'forbidden' not in state:
        category = 'network' if effect == 'socket' else effect
        assert state[category] == 1


def test_nesting_leitura_e_fim_do_contexto_interno(papel, tmp_path):
    guard, _ = papel
    path = tmp_path / 'dados_simulados.txt'
    path.write_text('DADOS SIMULADOS')
    with guard() as outer:
        with guard() as inner:
            assert path.read_text() == 'DADOS SIMULADOS'
        assert path.read_text() == 'DADOS SIMULADOS'
    assert outer['reads'] == 2 and inner['reads'] == 1
    assert proibidos(outer) == proibidos(inner) == 0
    assert not outer['active'] and not inner['active']


def test_nesting_recusa_preserva_ordem_e_nao_cria_arquivo(papel, tmp_path):
    guard, error = papel
    marker = tmp_path / 'efeito_dados_simulados'
    outer_context, inner_context = guard(), guard()
    outer, inner = outer_context.__enter__(), inner_context.__enter__()
    with pytest.raises(error, match='Guarda API|Efeito vedado'):
        marker.write_text('DADOS SIMULADOS')
    inner_context.__exit__(None, None, None)
    with pytest.raises(AssertionError):
        outer_context.__exit__(None, None, None)
    assert proibidos(outer) == 1 and proibidos(inner) == 0
    assert not marker.exists() and not outer['active'] and not inner['active']


def test_depois_contexto_efeito_proprio_nao_e_bloqueado_nem_contado(papel, tmp_path):
    guard, _ = papel
    path = tmp_path / 'dados_simulados.txt'
    path.write_text('DADOS SIMULADOS')
    with guard() as state:
        assert path.read_text() == 'DADOS SIMULADOS'
    previous = state.copy()
    path.write_text('DADOS SIMULADOS: escrita própria após contexto')
    assert path.read_text().endswith('após contexto')
    assert state == previous and state['active'] is False


def test_reentradas_preservam_leitura_recusa_e_nao_acumulam_registro(papel, tmp_path, monkeypatch):
    guard, error = papel
    path = tmp_path / 'dados_simulados.txt'
    path.write_text('DADOS SIMULADOS')
    native, registrations = sys.addaudithook, []

    def observe(callback):
        registrations.append(callback)
        return native(callback)

    monkeypatch.setattr(sys, 'addaudithook', observe)
    previous = []
    for _ in range(8):
        with guard() as state:
            assert path.read_text() == 'DADOS SIMULADOS'
        previous.append((state, state.copy()))
    context = guard()
    state = context.__enter__()
    with pytest.raises(error, match='Guarda API|Efeito vedado'):
        path.write_text('DADOS SIMULADOS: deve permanecer original')
    with pytest.raises(AssertionError):
        context.__exit__(None, None, None)
    assert path.read_text() == 'DADOS SIMULADOS'
    assert all(state == saved for state, saved in previous)
    assert len(registrations) <= 1
