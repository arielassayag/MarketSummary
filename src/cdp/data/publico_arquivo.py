"""Arquivo de fontes públicas: cada arquivo bruto baixado fica guardado com SHA-256 e índice.

Layout (``<raiz>`` = ``data/`` na rotina; diretório temporário ou sintético em testes/demo)::

    <raiz>/publico/indice.jsonl                         # uma linha por coleta (append-only)
    <raiz>/publico/<FONTE>/<sub>/<AAAA-MM-DD>/<nome>    # bytes exatamente como recebidos
                                                        # (data da coleta em São Paulo)

A ``chave`` lógica de um arquivo é ``<FONTE>/<sub>/<nome>`` (ex.: ``CVM/DFP/dfp_cia_aberta_2025.zip``,
``SEC/companyfacts/CIK0000917851.json``, ``YAHOO/consenso/ALSEA.MX.json``). Cada coleta grava
uma linha no índice com ``chave``, ``fonte``, ``url``, ``caminho``, ``sha256``, ``bytes`` e
``data_coleta`` (UTC). Conteúdo idêntico ao da última versão da mesma chave não é regravado: a
nova linha do índice aponta para o mesmo caminho.

Regras:

- **Point-in-time**: a leitura em ``ate`` usa a coleta mais recente com ``data_coleta <= ate``
  (nada coletado depois da data de referência entra).
- **Integridade**: toda leitura recalcula o SHA-256 e falha (:class:`ArquivoAdulterado`) se o
  arquivo não confere com o índice; linha ilegível no meio do índice também. Só o último
  registro sem quebra de linha final (gravação interrompida) é ignorado (e removido antes
  da próxima gravação), com registro em ``falhas``.
- **Offline**: nenhuma rede; só o que está no arquivo (ou nada — ausência nunca vira zero).
- **Online**: reaproveita uma coleta recente (``max_idade_dias``) e, se não houver, baixa,
  arquiva e devolve. Falha de rede com versão arquivada ⇒ usa a versão arquivada (registrado).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DEFAULT_RAIZ = Path("data")
PASTA_ARQUIVO = "publico"
INDICE = "indice.jsonl"

FONTES = ("CVM", "SEC", "YAHOO", "BCB", "FRED", "B3", "ISHARES", "GLOBALX", "DAMODARAN",
          "BANXICO", "SIMULADO")

_CHAVE_RE = re.compile(r"^[A-Z][A-Z0-9]*(/[A-Za-z0-9_.=\-]+)+$")


class ArquivoAdulterado(RuntimeError):
    """O arquivo em disco não confere com o SHA-256 registrado no índice."""


class FonteIndisponivel(RuntimeError):
    """Sem rede (ou modo offline) e sem versão arquivada para a chave pedida."""


@dataclass(frozen=True)
class RegistroArquivo:
    """Uma coleta registrada no índice do arquivo público."""

    chave: str
    fonte: str
    url: str | None
    caminho: str            # relativo a ``<raiz>/publico`` (posix)
    sha256: str
    bytes: int
    data_coleta: datetime   # UTC

    def como_dict(self) -> dict:
        return {"chave": self.chave, "fonte": self.fonte, "url": self.url,
                "caminho": self.caminho, "sha256": self.sha256, "bytes": self.bytes,
                "data_coleta": self.data_coleta.astimezone(UTC).isoformat(timespec="seconds")}

    @staticmethod
    def de_dict(d: dict) -> RegistroArquivo:
        dc = datetime.fromisoformat(str(d["data_coleta"]))
        if dc.tzinfo is None:
            dc = dc.replace(tzinfo=UTC)
        return RegistroArquivo(chave=str(d["chave"]), fonte=str(d["fonte"]),
                               url=d.get("url") or None, caminho=str(d["caminho"]),
                               sha256=str(d["sha256"]), bytes=int(d.get("bytes", 0)),
                               data_coleta=dc)


FUSO = ZoneInfo("America/Sao_Paulo")


def data_local(dt: datetime) -> date:
    """Data civil em São Paulo (referência de todas as datas do fundo)."""
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(FUSO).date()


def sha256_de(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def agora_utc() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


_SEGREDO_RE = re.compile(r"(?i)((?:token|apikey|api_key|key|access_token)=)[^&\s'\"]+")


def ocultar_segredos(texto: str) -> str:
    """Remove valores de parâmetros sensíveis (``token=…``) de mensagens e endereços."""
    return _SEGREDO_RE.sub(r"\1<oculto>", str(texto))


class Arquivo:
    """Arquivo de fontes públicas sob ``<raiz>/publico`` (seguro para threads)."""

    def __init__(self, raiz: str | Path | None = None, *, offline: bool = False,
                 agora: Callable[[], datetime] = agora_utc) -> None:
        self.raiz = Path(raiz) if raiz is not None else DEFAULT_RAIZ
        self.base = self.raiz / PASTA_ARQUIVO
        self.offline = bool(offline)
        self._agora = agora
        self._lock = threading.RLock()
        self._indice: dict[str, list[RegistroArquivo]] | None = None
        self.falhas: list[str] = []

    # ------------------------------------------------------------------ índice
    @property
    def caminho_indice(self) -> Path:
        return self.base / INDICE

    def _carregar(self) -> dict[str, list[RegistroArquivo]]:
        with self._lock:
            if self._indice is not None:
                return self._indice
            idx: dict[str, list[RegistroArquivo]] = {}
            if self.caminho_indice.exists():
                texto = self.caminho_indice.read_text(encoding="utf-8")
                linhas = texto.split("\n")
                # ``split`` deixa por último o que vem depois do último "\n": vazio num índice
                # íntegro; um fragmento quando a gravação foi interrompida (registro incompleto)
                cauda = linhas.pop()
                if cauda.strip():
                    self.falhas.append(
                        f"{INDICE}: último registro incompleto ignorado (gravação interrompida)")
                for n, linha in enumerate(linhas, start=1):
                    if not linha.strip():
                        continue
                    try:
                        reg = RegistroArquivo.de_dict(json.loads(linha))
                    except (ValueError, KeyError, TypeError) as exc:
                        raise ArquivoAdulterado(
                            f"{self.caminho_indice}: linha {n} ilegível ({exc}).") from exc
                    idx.setdefault(reg.chave, []).append(reg)
            for regs in idx.values():
                regs.sort(key=lambda r: (r.data_coleta, r.caminho))
            self._indice = idx
            return idx

    def registros(self, chave: str | None = None) -> list[RegistroArquivo]:
        idx = self._carregar()
        if chave is not None:
            return list(idx.get(chave, []))
        return [r for k in sorted(idx) for r in idx[k]]

    def chaves(self, prefixo: str = "") -> list[str]:
        return sorted(k for k in self._carregar() if k.startswith(prefixo))

    def buscar(self, chave: str, ate: date | datetime | None = None) -> RegistroArquivo | None:
        """Coleta mais recente da ``chave`` com ``data_coleta <= ate`` (sem ``ate``: a última)."""
        regs = self._carregar().get(chave, [])
        if ate is not None:
            if isinstance(ate, datetime):
                lim = ate if ate.tzinfo else ate.replace(tzinfo=UTC)
                regs = [r for r in regs if r.data_coleta <= lim]
            else:
                regs = [r for r in regs if data_local(r.data_coleta) <= ate]
        return regs[-1] if regs else None

    def por_sha(self, sha256: str) -> RegistroArquivo | None:
        """Registro (mais antigo) de um conteúdo pelo SHA-256 — reprodução exata de um run."""
        for reg in self.registros():
            if reg.sha256 == sha256:
                return reg
        return None

    # ------------------------------------------------------------------ leitura/escrita
    def ler(self, reg: RegistroArquivo) -> bytes:
        p = self.base / reg.caminho
        if not p.exists():
            raise ArquivoAdulterado(f"Arquivo do índice ausente em disco: {reg.caminho}")
        data = p.read_bytes()
        if sha256_de(data) != reg.sha256:
            raise ArquivoAdulterado(
                f"SHA-256 de {reg.caminho} não confere com o índice (arquivo alterado).")
        return data

    def gravar(self, chave: str, fonte: str, url: str | None, conteudo: bytes, *,
               data_coleta: datetime | None = None) -> RegistroArquivo:
        """Arquiva ``conteudo`` sob a ``chave`` (bytes intocados) e registra no índice."""
        if not _CHAVE_RE.match(chave) or ".." in chave.split("/"):
            raise ValueError(f"Chave de arquivo inválida: {chave!r}")
        if fonte not in FONTES:
            raise ValueError(f"Fonte desconhecida: {fonte!r}")
        if self.offline:
            raise FonteIndisponivel("Arquivo aberto em modo offline: gravação não permitida.")
        dc = (data_coleta or self._agora()).astimezone(UTC).replace(microsecond=0)
        sha = sha256_de(conteudo)
        pasta, nome = chave.rsplit("/", 1)
        dia = data_local(dc).isoformat()  # pasta pela data de São Paulo (a da rotina)
        with self._lock:
            ultimo = self.buscar(chave)
            if ultimo is not None and ultimo.sha256 == sha and (self.base / ultimo.caminho).exists():
                caminho = ultimo.caminho
            else:
                caminho = f"{pasta}/{dia}/{nome}"
                destino = self.base / caminho
                if destino.exists() and sha256_de(destino.read_bytes()) != sha:
                    caminho = f"{pasta}/{dia}/{sha[:12]}_{nome}"
                    destino = self.base / caminho
                destino.parent.mkdir(parents=True, exist_ok=True)
                tmp = destino.with_name(destino.name + ".part")
                tmp.write_bytes(conteudo)
                tmp.replace(destino)
            reg = RegistroArquivo(chave=chave, fonte=fonte, url=url, caminho=caminho,
                                  sha256=sha, bytes=len(conteudo), data_coleta=dc)
            self.base.mkdir(parents=True, exist_ok=True)
            self._anexar_indice(json.dumps(reg.como_dict(), ensure_ascii=False,
                                           sort_keys=True) + "\n")
            idx = self._carregar()
            idx.setdefault(chave, []).append(reg)
            idx[chave].sort(key=lambda r: (r.data_coleta, r.caminho))
        return reg

    def _anexar_indice(self, linha: str) -> None:
        """Acrescenta uma linha ao índice (``flush`` + ``fsync``). Um registro incompleto no fim
        do arquivo (gravação interrompida, sem ``\\n`` final) é removido antes: nunca foi um
        registro válido, e anexar depois dele corromperia a linha seguinte."""
        p = self.caminho_indice
        tamanho = p.stat().st_size if p.exists() else 0
        if tamanho > 0:
            with open(p, "r+b") as fh:
                fh.seek(tamanho - 1)
                if fh.read(1) != b"\n":
                    # procura a última quebra de linha de trás para frente (em blocos)
                    corte, pos = 0, tamanho
                    while pos > 0:
                        ini = max(0, pos - 65536)
                        fh.seek(ini)
                        k = fh.read(pos - ini).rfind(b"\n")
                        if k >= 0:
                            corte = ini + k + 1
                            break
                        pos = ini
                    fh.truncate(corte)
                    fh.flush()
                    os.fsync(fh.fileno())
                    self.falhas.append(
                        f"{INDICE}: registro incompleto removido do fim do índice antes de anexar")
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(linha)
            fh.flush()
            os.fsync(fh.fileno())

    def obter(self, chave: str, fonte: str, url: str | None, baixar: Callable[[], bytes | None],
              *, ate: date, max_idade_dias: float = 0.0, instantaneo: bool = False,
              validar: Callable[[bytes], None] | None = None,
              ) -> tuple[RegistroArquivo, bytes] | None:
        """Conteúdo da ``chave`` em ``ate``: arquivado (offline/recente) ou baixado agora.

        Datas comparadas no fuso de São Paulo (a rotina noturna das 22h BRT já é o dia
        seguinte em UTC).

        - Fontes com data própria (demonstrações, taxas, proventos): coleta ``<= ate``; sem
          ela, a mais recente (o conteúdo é filtrado depois pela data de publicação).
        - ``instantaneo=True`` (retratos sem data própria: consenso, carteira de ETF, free float
          do Yahoo): só coleta ``<= ate``; com ``ate`` anterior a hoje (São Paulo) nunca baixa —
          o retrato baixado hoje teria ``data_coleta`` posterior a ``ate`` e nenhuma releitura em
          ``ate`` o veria (irreprodutível); sem coleta até ``ate`` ⇒ ``None`` (registrado).
        - offline: nunca baixa.
        - online: coleta com idade ``<= max_idade_dias`` é reaproveitada; senão ``baixar()``
          (``None`` = recurso inexistente, ex.: 404) e arquivamento. O conteúdo passa por
          ``validar`` ANTES de ser arquivado (resposta inválida nunca entra). Falha de rede com
          versão arquivada ⇒ versão arquivada (falha registrada em ``falhas``).
        """
        exato = self.buscar(chave, ate)
        ultimo = None if instantaneo else self.buscar(chave)
        agora = self._agora()
        hoje = data_local(agora)
        if self.offline or (instantaneo and ate < hoje):
            arquivado = exato or ultimo
            if arquivado is None and instantaneo and not self.offline:
                with self._lock:
                    self.falhas.append(f"{chave}: retrato não coletado até {ate.isoformat()} "
                                       "(coleta posterior não é usada)")
            return (arquivado, self.ler(arquivado)) if arquivado is not None else None
        if exato is not None and max_idade_dias > 0 and ate < hoje and \
                (ate - data_local(exato.data_coleta)).days <= max_idade_dias:
            return exato, self.ler(exato)  # referência passada: a coleta daquela data
        arquivado = exato or ultimo
        if arquivado is not None and max_idade_dias > 0:
            idade = (agora - arquivado.data_coleta).total_seconds() / 86400.0
            if idade <= max_idade_dias:
                return arquivado, self.ler(arquivado)
        try:
            conteudo = baixar()
            if conteudo is None:
                return (arquivado, self.ler(arquivado)) if arquivado is not None else None
            if validar is not None:
                validar(conteudo)
        except Exception as exc:  # rede, HTTP, conteúdo inválido
            msg = f"{chave}: falha na coleta ({type(exc).__name__}: {ocultar_segredos(str(exc))[:200]})"
            logger.warning(msg)
            with self._lock:
                self.falhas.append(msg)
            if arquivado is not None:
                return arquivado, self.ler(arquivado)
            return None
        reg = self.gravar(chave, fonte, url, conteudo)
        return reg, conteudo


__all__ = [
    "ArquivoAdulterado", "Arquivo", "DEFAULT_RAIZ", "FONTES", "FonteIndisponivel",
    "PASTA_ARQUIVO", "RegistroArquivo", "agora_utc", "data_local", "ocultar_segredos",
    "sha256_de",
]
