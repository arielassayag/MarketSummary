"""Confirmação humana fora de banda para desligar o kill switch.

Só um humano desliga o kill switch (invariante 7 do ``AGENTS.md``). Um terminal interativo não
basta: um agente de IA com acesso total à máquina (ex.: Codex em ``danger-full-access``) pode
abrir um pseudoterminal. A confirmação exige, além do motivo digitado de novo, a **senha do
operador** — um segredo que só o humano conhece, guardado fora do repositório como hash
PBKDF2-SHA256 com sal (``~/.config/cdp/operador.json``; ``XDG_CONFIG_HOME`` respeitado). O
arquivo nunca contém a senha, e nenhum agente a recebe: ela é digitada pelo humano no próprio
terminal (``getpass``), nunca passada por argumento, variável de ambiente ou arquivo.

``cdp kill-switch senha`` define a senha (num terminal próprio); trocá-la exige a senha atual.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

ITERACOES = 310_000
ARQUIVO = "operador.json"
TAMANHO_MINIMO = 12


def caminho_segredo() -> Path:
    """Arquivo do hash da senha do operador (fora do repositório)."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "cdp" / ARQUIVO


def configurado() -> bool:
    return caminho_segredo().is_file()


def _derivar(senha: str, sal: bytes, iteracoes: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes).hex()


def conferir(senha: str) -> bool:
    """A senha confere com o hash guardado? (``False`` sem senha configurada)."""
    path = caminho_segredo()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        sal = bytes.fromhex(str(raw["sal"]))
        iteracoes = int(raw.get("iteracoes", ITERACOES))
        esperado = str(raw["hash"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return hmac.compare_digest(_derivar(senha, sal, iteracoes), esperado)


def definir(senha: str) -> Path:
    """Grava o hash da senha (permissão 600). A senha precisa de 12 caracteres ou mais."""
    if len(senha) < TAMANHO_MINIMO:
        raise ValueError(f"a senha do operador precisa de pelo menos {TAMANHO_MINIMO} "
                         "caracteres.")
    path = caminho_segredo()
    path.parent.mkdir(parents=True, exist_ok=True)
    sal = secrets.token_bytes(16)
    dados = {"algoritmo": "pbkdf2_sha256", "iteracoes": ITERACOES, "sal": sal.hex(),
             "hash": _derivar(senha, sal, ITERACOES),
             "definida_em": datetime.now(UTC).isoformat(timespec="seconds")}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def pedir_senha(rotulo: str = "Senha do operador (não é ecoada): ") -> str:
    """Lê a senha do terminal do humano (``getpass``; nunca de argumento ou ambiente)."""
    import getpass

    return getpass.getpass(rotulo)
