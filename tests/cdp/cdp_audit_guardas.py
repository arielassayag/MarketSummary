"""Dispatcher único de testes; políticas originais em ordem de ativação."""
import sys

_ATIVOS = []
_REGISTRADO = False


def _auditar(event, args):
    if not _ATIVOS:
        return
    for _, callback in tuple(_ATIVOS):
        callback(event, args)


def registrar(callback):
    """Ativa a closure original e devolve um token exclusivo do contexto."""
    global _REGISTRADO
    if not _REGISTRADO:
        sys.addaudithook(_auditar)
        _REGISTRADO = True
    token = object()
    _ATIVOS.append((token, callback))
    return token


def remover(token):
    """Retira somente o contexto identificado, inclusive em saída não LIFO."""
    for index, (current, _) in enumerate(_ATIVOS):
        if current is token:
            del _ATIVOS[index]
            return
    raise ValueError('Token de guarda não ativo')
