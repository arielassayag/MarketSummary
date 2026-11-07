#!/usr/bin/env python3
"""Reconta evidências por linhas e verifica os artefatos sem importar o recuperador."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from functools import cache
from hashlib import sha256
from pathlib import Path

_MODOS = ('direta', 'memoria', 'guiada')
_TIPOS = ('evidencia', 'estado_atual', 'fora_escopo')
_REF = ('caminho', 'inicio', 'fim', 'sha256')


def hash_(bruto):
    return sha256(bruto).hexdigest()


def _chaves_unicas(pares):
    objeto = {}
    for chave, valor in pares:
        if chave in objeto:
            raise ValueError(f'chave JSON duplicada: {chave}')
        objeto[chave] = valor
    return objeto


def ler_json(p):
    return json.loads(p.read_bytes(), object_pairs_hook=_chaves_unicas)


def fonte_git(revisao, caminho):
    return subprocess.check_output(['git', 'show', f'{revisao}:{caminho}'])


def _recortar(linhas, caminho, inicio, fim):
    src = linhas(caminho)
    assert type(inicio) is int and type(fim) is int
    assert 1 <= inicio <= fim <= len(src) and fim - inicio + 1 <= 14
    texto = '\n'.join(src[inicio - 1:fim]).encode()
    assert len(texto) <= 1800
    return texto


def _conferir_guiada(pacote, resposta, medicao, linhas, fontes, explorar):
    assert {'lacre', 'ids'} <= resposta.keys()
    if explorar:
        assert resposta.keys() <= {'lacre', 'ids', 'intencao', 'recortes'}
        lista = pacote['fontes_permitidas']
        assert isinstance(lista, list) and all(isinstance(p, str) for p in lista)
        assert len(lista) == len(set(lista)) and set(lista) <= fontes.keys()
        permitidas = set(lista)
        rota = pacote['rota_sugerida']
        assert rota in _TIPOS and (permitidas or rota == 'fora_escopo')
    else:
        assert resposta.keys() == {'lacre', 'ids'}
        assert not {'fontes_permitidas', 'rota_sugerida'} & pacote.keys()
        permitidas = set(fontes)
        rota = None

    assert all(type(p['id']) is int for p in pacote['candidatas'])
    candidatas = {p['id']: {k: p[k] for k in _REF} for p in pacote['candidatas']}
    assert list(candidatas) == list(range(1, len(pacote['candidatas']) + 1))
    ids, recortes = resposta['ids'], resposta.get('recortes', [])
    assert isinstance(ids, list) and all(type(i) is int and i in candidatas for i in ids)
    assert isinstance(recortes, list) and len(ids) + len(recortes) <= pacote['limite']
    assert len(ids) == len(set(ids))
    intencao = resposta.get('intencao')
    assert intencao is None or intencao in _TIPOS
    assert not recortes or intencao == 'evidencia'
    assert intencao not in ('evidencia', 'estado_atual') or permitidas

    iniciais = [candidatas[i] for i in ids]
    for r in recortes:
        assert r.keys() == {'caminho', 'inicio', 'fim'}
        assert r['caminho'] in permitidas
        texto = _recortar(linhas, r['caminho'], r['inicio'], r['fim'])
        assert texto.strip()
        iniciais.append({**r, 'sha256': hash_(texto)})
    assert len({tuple(p[k] for k in _REF) for p in iniciais}) == len(iniciais)

    passagens = medicao['passagens']
    assert all(p['caminho'] in permitidas for p in passagens)
    assert len({tuple(p[k] for k in _REF) for p in passagens}) == len(passagens)
    assert passagens[:len(iniciais)] == iniciais
    if recortes:
        assert passagens == iniciais
    else:
        assert all(p in candidatas.values() for p in passagens[len(iniciais):])
    if intencao in ('estado_atual', 'fora_escopo'):
        assert not ids and not recortes and not passagens and not medicao['retornou_notas']
    if explorar:
        efetiva = intencao or rota
        assert medicao['encaminhou'] is (efetiva == 'estado_atual')
        if efetiva in ('estado_atual', 'fora_escopo'):
            assert not passagens and not medicao['retornou_notas']


def _atingidos(passagens, gabarito):
    return [any(p['caminho'] == f and p['inicio'] <= a <= b <= p['fim']
                for p in passagens for f, a, b in grupo) for grupo in gabarito]


def main():
    if not __debug__:
        raise RuntimeError('a auditoria requer verificações Python ativas')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ensaio', type=Path, required=True)
    parser.add_argument('--respostas', type=Path, required=True)
    parser.add_argument('corpora', nargs='+', type=Path)
    args = parser.parse_args()
    path_manifesto = args.ensaio / 'privado/manifesto.json'
    manifesto = ler_json(path_manifesto)
    resultado = ler_json(args.ensaio / 'privado/resultado.json')
    respostas = ler_json(args.respostas)
    assert hash_(path_manifesto.read_bytes()) == resultado['sha256_manifesto']
    assert hash_(args.respostas.read_bytes()) == resultado['sha256_respostas']
    assert manifesto['revisao'] == resultado['revisao']
    assert manifesto['revisao_fontes'] == resultado['revisao_fontes']
    assert manifesto['fontes'] == resultado['fontes']
    assert manifesto['limite_passagens'] == resultado['limite_passagens'] == 5
    assert manifesto['orcamento_bytes'] == resultado['orcamento_bytes'] == 4500
    explorar = manifesto.get('explorar_fontes', False)
    assert type(explorar) is bool and resultado.get('explorar_fontes', False) is explorar
    for caminho, digest in manifesto['fontes'].items():
        assert (hash_(fonte_git(manifesto['revisao'], caminho))
                == hash_(fonte_git(manifesto['revisao_fontes'], caminho)) == digest)

    @cache
    def linhas(caminho):
        return fonte_git(resultado['revisao'], caminho).decode().splitlines()

    casos = {}
    for p in args.corpora:
        assert hash_(p.read_bytes()) == resultado['corpora'][p.stem] == manifesto['corpora'][p.stem]
        for c in ler_json(p)['casos']:
            assert c['id'] not in casos
            casos[c['id']] = c
    mapa = {p['id']: p for p in manifesto['pacotes']}
    assert len(mapa) == len(manifesto['pacotes']) == len(casos) == len(resultado['casos']) == len(respostas)
    assert mapa.keys() == casos.keys() == {c['id'] for c in resultado['casos']}
    assert respostas.keys() == {c['opaco'] for c in resultado['casos']}
    assert resultado['modos'].keys() == set(_MODOS)
    resumido = {modo: Counter() for modo in _MODOS}
    opcoes = []
    for medido in resultado['casos']:
        c = casos[medido['id']]
        opaco = mapa[c['id']]['opaco']
        assert medido['opaco'] == opaco and medido['tipo'] == c['tipo']
        path_pacote = args.ensaio / 'pacotes' / f'{opaco}.json'
        pacote = ler_json(path_pacote)
        assert hash_(path_pacote.read_bytes()) == mapa[c['id']]['sha256_pacote']
        assert pacote['lacre'] == mapa[c['id']]['lacre'] == respostas[opaco]['lacre']
        assert pacote['escopo'] == c['escopo'] and pacote['consulta'] == c['consulta']
        assert pacote['revisao'] == resultado['revisao'] and pacote['data'] == resultado['data']
        assert pacote['limite'] == 5 and pacote['orcamento_bytes'] == 4500
        if c['tipo'] == 'evidencia':
            opcoes.append(len(pacote['candidatas']))
        gabarito = []
        for grupo in c['grupos']:
            evs = []
            for ev in grupo:
                literal = ev['trecho'].splitlines()
                src = linhas(ev['caminho'])
                assert hash_(ev['trecho'].encode()) == ev['sha256']
                (inicio,) = [i+1 for i in range(len(src)) if src[i:i+len(literal)] == literal]
                evs.append((ev['caminho'], inicio, inicio + len(literal) - 1))
            gabarito.append(evs)
        assert medido['modos'].keys() == set(_MODOS)
        for modo, medicao in medido['modos'].items():
            passagens = medicao['passagens']
            assert len(passagens) <= 5
            assert type(medicao['encaminhou']) is bool and type(medicao['retornou_notas']) is bool
            if modo == 'guiada':
                _conferir_guiada(pacote, respostas[opaco], medicao, linhas,
                                  manifesto['fontes'], explorar)
            total = 0
            prefixo = []
            for p in passagens:
                assert p.keys() == set(_REF) and p['caminho'] in manifesto['fontes']
                texto = _recortar(linhas, p['caminho'], p['inicio'], p['fim'])
                assert hash_(texto) == p['sha256']
                total += len(texto) + bool(total)
                if total <= 4500:
                    prefixo.append(p)
            assert total == medicao['bytes_evidencia']
            if modo == 'guiada':
                assert total <= 4500
            cenario = resumido[modo]
            cenario[c['tipo']] += 1
            assert medicao['grupos_atingidos'] == _atingidos(passagens, gabarito)
            assert medicao['abstencao'] is (None if gabarito else not (passagens or medicao['retornou_notas']))
            if c['tipo'] == 'evidencia':
                for limite in (1, 3, 5):
                    assert medicao[f'completo_{limite}'] is all(_atingidos(passagens[:limite], gabarito))
                hits = _atingidos(prefixo, gabarito)
                assert all(hits) == medicao['completo_4500b']
                cenario['completo_4500b'] += all(hits)
                cenario['falsas_orientacoes_estaticas'] += bool(medicao['encaminhou'])
            elif c['tipo'] == 'estado_atual':
                cenario['estado_encaminhado_sem_contexto'] += bool(medicao['encaminhou']) and not (
                    passagens or medicao['retornou_notas'])
            else:
                cenario['fora_abstencao'] += not (
                    passagens or medicao['retornou_notas'] or medicao['encaminhou'])
    for modo, contagem in resumido.items():
        resumo = resultado['modos'][modo]
        for medida in ('completo_4500b', 'falsas_orientacoes_estaticas',
                       'estado_encaminhado_sem_contexto', 'fora_abstencao'):
            assert resumo[medida] == contagem[medida]
        assert resumo['n_evidencia'] == contagem['evidencia']
        assert resumo['estado_n'] == contagem['estado_atual']
        assert resumo['fora_n'] == contagem['fora_escopo']
    guiada = resumido['guiada']
    integral = (guiada['evidencia'] == guiada['completo_4500b']
                and not guiada['falsas_orientacoes_estaticas']
                and guiada['estado_atual'] == guiada['estado_encaminhado_sem_contexto']
                and guiada['fora_escopo'] == guiada['fora_abstencao'])
    assert resultado['integral'] is integral
    print(json.dumps({'revisao': resultado['revisao'], 'casos': len(casos),
                      'candidatas_media': sum(opcoes) / len(opcoes) if opcoes else None, 'modos': resumido},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
