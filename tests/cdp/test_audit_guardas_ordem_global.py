"""DADOS SIMULADOS: ordem global e saída por identidade em efeitos reais."""
import importlib
import itertools
import os
import sys

import pytest

PAPEIS = (
    ('test_eps_fronteira_receita_v3', 'guarda', RuntimeError, 'Guarda API EPS: '),
    ('test_eps_fronteira_receita_nao_autor', 'sem_efeitos', AssertionError, 'Efeito vedado na API: '),
    ('test_cvm_comparativos_revisor', 'guarded', RuntimeError, 'Guarda API: '),
)


def papel(index):
    module, name, error, prefix = PAPEIS[index]
    return getattr(importlib.import_module(module), name), error, prefix


def recusas(state):
    if 'forbidden' in state:
        return len(state['forbidden'])
    return sum(state[key] for key in ('write', 'network', 'process', 'mutation'))


def fechar(context, state):
    if recusas(state):
        with pytest.raises(AssertionError):
            context.__exit__(None, None, None)
    else:
        context.__exit__(None, None, None)


@pytest.mark.parametrize('outer_index,inner_index', list(itertools.permutations(range(3), 2)))
@pytest.mark.parametrize('effect', ['write', 'remove'])
def test_ordem_ativacao_global_prevalece_sobre_aquecimento(tmp_path, outer_index, inner_index, effect):
    outer_guard, error, prefix = papel(outer_index)
    inner_guard, _, _ = papel(inner_index)
    path = tmp_path / 'DADOS_SIMULADOS.txt'
    path.write_text('DADOS SIMULADOS: original')
    before = path.stat()
    with inner_guard():
        pass  # aquecimento em ordem oposta à entrada dos contextos ativos
    outer_context, inner_context = outer_guard(), inner_guard()
    outer, inner = outer_context.__enter__(), inner_context.__enter__()
    caught = None
    try:
        try:
            if effect == 'write':
                with open(path, 'w') as stream:
                    stream.write('DADOS SIMULADOS: não deve acontecer')
            else:
                os.remove(path)
        except (RuntimeError, AssertionError) as exc:
            caught = exc
    finally:
        fechar(inner_context, inner)
        fechar(outer_context, outer)
    assert path.read_text() == 'DADOS SIMULADOS: original'
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert type(caught) is error
    category = ('open' if effect == 'write' else 'os.remove') if 'forbidden' in outer else (
        'write' if effect == 'write' else 'mutation')
    assert str(caught) == prefix + category
    assert recusas(outer) == 1 and recusas(inner) == 0
    assert not outer['active'] and not inner['active']


@pytest.mark.parametrize('index', range(3))
def test_saida_nao_lifo_retira_contexto_por_identidade(tmp_path, index):
    guard, error, prefix = papel(index)
    path = tmp_path / 'DADOS_SIMULADOS.txt'
    path.write_text('DADOS SIMULADOS')
    first_context, second_context = guard(), guard()
    first, second = first_context.__enter__(), second_context.__enter__()
    assert first == second and first is not second
    first_context.__exit__(None, None, None)
    assert path.read_text() == 'DADOS SIMULADOS'
    try:
        with pytest.raises(error) as caught:
            os.remove(path)
    finally:
        fechar(second_context, second)
    assert str(caught.value) == prefix + ('os.remove' if 'forbidden' in second else 'mutation')
    assert first['reads'] == 0 and second['reads'] == 1
    assert recusas(first) == 0 and recusas(second) == 1
    assert not first['active'] and not second['active'] and path.exists()
    os.remove(path)  # remoção própria só depois do último contexto
    assert not path.exists() and recusas(second) == 1


@pytest.mark.parametrize('index', range(3))
def test_leitura_cruzada_contada_so_nos_contextos_ativos(tmp_path, index):
    outer_guard, _, _ = papel(index)
    inner_guard, _, _ = papel((index + 1) % 3)
    path = tmp_path / 'DADOS_SIMULADOS.txt'
    path.write_text('DADOS SIMULADOS')
    with outer_guard() as outer:
        with inner_guard() as inner:
            assert path.read_text() == 'DADOS SIMULADOS'
        assert path.read_text() == 'DADOS SIMULADOS'
    assert outer['reads'] == 2 and inner['reads'] == 1
    assert recusas(outer) == recusas(inner) == 0


@pytest.mark.parametrize('index', range(3))
def test_baseexception_cruzada_limpa_ambos_e_preserva_propagacao(tmp_path, index):
    class Sentinela(BaseException):
        pass

    outer_guard, _, _ = papel(index)
    inner_guard, _, _ = papel((index + 1) % 3)
    path = tmp_path / 'DADOS_SIMULADOS.txt'
    path.write_text('DADOS SIMULADOS')
    with pytest.raises(Sentinela, match='DADOS SIMULADOS'):
        with outer_guard() as outer:
            with inner_guard() as inner:
                assert path.read_text() == 'DADOS SIMULADOS'
                raise Sentinela('DADOS SIMULADOS')
    assert not outer['active'] and not inner['active']
    before_outer, before_inner = outer.copy(), inner.copy()
    path.write_text('DADOS SIMULADOS: depois da exceção')
    assert outer == before_outer and inner == before_inner
    with inner_guard() as new_state:
        assert path.read_text().endswith('depois da exceção')
    assert new_state['reads'] == 1 and recusas(new_state) == 0


def test_reentradas_cruzadas_leem_e_recusam_com_um_registro_global(tmp_path, monkeypatch):
    path = tmp_path / 'DADOS_SIMULADOS.txt'
    path.write_text('DADOS SIMULADOS')
    original, registrations = sys.addaudithook, []

    def observar(callback):
        registrations.append(callback)
        return original(callback)

    monkeypatch.setattr(sys, 'addaudithook', observar)
    saved = []
    for index in list(range(3)) * 3:
        guard, _, _ = papel(index)
        with guard() as state:
            assert path.read_text() == 'DADOS SIMULADOS'
        saved.append((state, state.copy()))
    for index in range(3):
        guard, error, _ = papel(index)
        context = guard()
        state = context.__enter__()
        try:
            with pytest.raises(error):
                os.remove(path)
        finally:
            fechar(context, state)
        assert recusas(state) == 1 and path.exists()
    assert all(state == snapshot for state, snapshot in saved)
    assert len(registrations) <= 1
