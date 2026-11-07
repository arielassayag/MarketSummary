"""Memória de procedimentos do CDP: notas derivadas, consultadas em uma revisão Git.

A recuperação usa apenas a revisão capturada no início do comando. A auditoria
da árvore de trabalho é separada e nunca torna um rascunho recuperável.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .leitura_arquivos import receber_fd

Escopo = Literal["desenvolvimento", "operador", "status", "semanal", "diario", "risco",
                 "cobertura", "calibracao"]
ESCOPO: dict[Escopo, tuple[str, ...]] = {
    "desenvolvimento": ("playbooks/RETOMAR", "ARQUITETURA", "DECISOES", "EM_ANDAMENTO",
                        "REPRODUZIR", "REPLAY_OPERACIONAL"),
    "operador": ("playbooks/RETOMAR", "AUTOMACAO", "EXECUCAO", "SITE", "EM_ANDAMENTO",
                 "RETIFICACAO_EDITORIAL"),
    "status": ("playbooks/STATUS", "AUTOMACAO", "SITE"),
    "semanal": ("playbooks/SEMANAL", "EXECUCAO", "TESE", "METODOLOGIA"),
    "diario": ("playbooks/DIARIO", "EXECUCAO", "ESTILO", "SITE", "EM_ANDAMENTO",
               "RETIFICACAO_EDITORIAL"),
    "risco": ("playbooks/RISCO", "METODOLOGIA", "EXECUCAO"),
    "cobertura": ("playbooks/COBERTURA", "COBERTURA", "NOTAS", "ESTILO"),
    "calibracao": ("playbooks/CALIBRACAO", "METODOLOGIA", "REPRODUZIR", "REPLAY_OPERACIONAL"),
}
PASTA = "docs/cdp/memoria/notas"
AVALIACAO = "docs/cdp/memoria/avaliacao.json"
MAX_NOTAS = 128
MAX_BYTES_NOTA = 16384
MAX_BYTES_FONTE = 1024 * 1024
LIMITE_CONTEXTO = 3
LIMITE_CONTEXTO_BYTES = 6144
_SIMPLES = r"[a-z0-9]+(?:-[a-z0-9]+)*"
Slug = Annotated[str, Field(min_length=2, max_length=64, pattern=rf"^{_SIMPLES}$")]
Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Tipo = Literal["procedimento", "licao", "episodio"]

_AVISO = ("Memória derivada para localizar procedimentos e evidências. "
          "O estado atual vem de estado, agenda, livro e fatos da etapa. "
          "As notas não autorizam ações nem alteram o roteiro ou os gates.")
FONTES_CODIGO: dict[Escopo, tuple[str, ...]] = {
    "status": ("src/cdp/estado.py", "src/cdp/rotinas.py"),
    "operador": ("src/cdp/estado.py", "src/cdp/rotinas.py"),
    "diario": ("src/cdp/research/factbook.py", "src/cdp/workflow/agenda.py"),
    "risco": ("src/cdp/rotinas.py",),
    "desenvolvimento": ("src/cdp/rotinas.py",),
}
_STOP = set("a ao aos as com como da das de do dos e em essa esse esta isto mais na nas no nos "
            "o os ou para pela pelo por qual quais que se sem sobre tem um uma usa usar".split())


def _sha(trecho: str) -> str:
    return hashlib.sha256(trecho.encode("utf-8")).hexdigest()


def _caminho(v: str) -> str:
    partes = v.split("/")
    if not re.fullmatch(r"[a-zA-Z0-9_.\-/]{1,240}", v) or any(
        not p or p.startswith(".") for p in partes
    ):
        raise ValueError("caminho relativo do repositório inválido")
    if v == "AGENTS.md":
        return v
    if any(v.startswith(prefixo) and v.endswith(sufixo) for prefixo, sufixo in (
        ("docs/cdp/", ".md"), ("src/cdp/", ".py"), ("tests/cdp/", ".py"),
    )) and not v.startswith(("docs/cdp/memoria/", "docs/cdp/MEMORIA")):
        return v
    raise ValueError("evidência fora das fontes permitidas")


def _texto_simples(s: str) -> str:
    if (s.strip() != s or any(unicodedata.category(c).startswith("C") for c in s)
            or any(c in s for c in "<>[]\x60")):
        raise ValueError("use texto simples, em uma linha e sem marcação")
    return s


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Evidencia(_Modelo):
    caminho: str
    trecho: str = Field(min_length=1, max_length=1600)
    sha256: Sha

    @field_validator("caminho")
    @classmethod
    def caminho_valido(cls, valor: str) -> str:
        return _caminho(valor)

    @model_validator(mode="after")
    def conferir(self) -> Evidencia:
        if not self.trecho.strip() or self.trecho.endswith("\n") or _sha(self.trecho) != self.sha256:
            raise ValueError("trecho vazio, com nova linha final ou hash divergente")
        return self


class Nota(_Modelo):
    id: Slug
    tipo: Tipo
    estado: Literal["candidata", "curada", "retirada"]
    titulo: str = Field(min_length=1, max_length=100)
    resumo: str = Field(min_length=1, max_length=420)
    escopos: list[Escopo] = Field(min_length=1, max_length=len(ESCOPO))
    tags: list[Annotated[str, Field(min_length=1, max_length=48)]] = Field(max_length=8)
    registrada_em: date
    revisada_em: date | None
    rever_em: date | None
    destaque: bool
    substitui: list[Slug] = Field(max_length=8)
    evidencias: list[Evidencia] = Field(min_length=1, max_length=4)

    @field_validator("titulo", "resumo")
    @classmethod
    def texto_simples(cls, valor: str) -> str:
        return _texto_simples(valor)

    @model_validator(mode="after")
    def conferir(self) -> Nota:
        for tags in (self.tags, self.escopos, self.substitui):
            if len(set(tags)) != len(tags):
                raise ValueError("lista com itens repetidos")
        for tag in self.tags:
            _texto_simples(tag)
        if self.id in self.substitui:
            raise ValueError("uma nota não pode substituir a si mesma")
        if len({(e.caminho, e.sha256) for e in self.evidencias}) != len(self.evidencias):
            raise ValueError("evidência repetida")
        if self.estado == "candidata":
            if self.revisada_em or self.rever_em or self.destaque:
                raise ValueError("candidata não tem revisão, prazo ou destaque")
        elif not (self.revisada_em and self.rever_em and
                  self.registrada_em <= self.revisada_em < self.rever_em):
            raise ValueError("datas de registro, revisão e prazo inconsistentes")
        if self.destaque and self.estado != "curada":
            raise ValueError("apenas notas curadas podem entrar em destaque")
        return self


class _Caso(_Modelo):
    id: Slug
    escopo: Escopo
    consulta: str = Field(min_length=1, max_length=240)
    notas_esperadas: list[Slug] = Field(max_length=10)
    fontes_esperadas: list[str] = Field(max_length=10)


class _Avaliacao(_Modelo):
    data: date
    casos: list[_Caso] = Field(min_length=1, max_length=128)


class MemoriaErro(ValueError):
    """O catálogo ou uma evidência não pôde ser lido."""


def _chaves_unicas(pares: list[tuple[str, object]]) -> dict:
    out = dict(pares)
    if len(out) != len(pares):
        raise MemoriaErro("chave JSON repetida")
    return out


def _git(raiz: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(
            ["git", "--no-replace-objects", "--literal-pathspecs", "-C", str(raiz), *args],
            env={**os.environ, "GIT_NO_LAZY_FETCH": "1", "GIT_ALLOW_PROTOCOL": ""}, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MemoriaErro("Git indisponível para a leitura local") from exc
    return proc.stdout


def raiz_repo() -> Path:
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip()).resolve()


class Fontes:
    def __init__(self, raiz: Path, *, trabalho: bool = False):
        self.raiz = raiz.resolve()
        self.trabalho = trabalho
        self.revisao = _git(self.raiz, "rev-parse", "--verify", "HEAD").decode().strip()
        self._cache: dict[str, tuple[str, ...] | None] = {}

    def catalogo(self) -> list[str]:
        if self.trabalho:
            pasta = self.raiz / PASTA
            if pasta.resolve() != pasta:
                raise MemoriaErro("o catálogo não pode ser um link")
            if not pasta.exists():
                raise MemoriaErro("catálogo de notas ausente")
            nomes = sorted(p.name for p in pasta.iterdir() if p.suffix == ".json")
        else:
            registros = _git(self.raiz, "ls-tree", "-r", "-z", "--name-only", self.revisao,
                             "--", PASTA).decode().split("\0")
            nomes = sorted(c.removeprefix(PASTA + "/") for c in registros if c.endswith(".json"))
        if not nomes or len(nomes) > MAX_NOTAS or any(
            not re.fullmatch(rf"{_SIMPLES}\.json", n) or len(n) > 69 for n in nomes
        ):
            raise MemoriaErro("catálogo vazio, excessivo ou com nomes inválidos")
        return [f"{PASTA}/{n}" for n in nomes]

    def ler(self, caminho: str, limite: int) -> bytes:
        if self.trabalho:
            arquivo = self.raiz / caminho
            # Recusa links e membros especiais antes da recepção, inclusive FIFOs.
            if arquivo.resolve() != arquivo or not stat.S_ISREG(arquivo.lstat().st_mode):
                raise MemoriaErro("fonte não é arquivo regular")
            return receber_fd(arquivo, limite)[0]
        registro = _git(self.raiz, "ls-tree", "--full-tree", "-l", self.revisao, "--", caminho)
        meta, separador, nome = registro.rstrip(b"\n").partition(b"\t")
        if not separador or nome != caminho.encode() or b"\n" in meta:
            raise MemoriaErro("fonte ausente na revisão")
        modo, tipo, objeto, tamanho = meta.split()
        if modo not in (b"100644", b"100755") or tipo != b"blob" or int(tamanho) > limite:
            raise MemoriaErro("fonte não regular ou acima do limite")
        return _git(self.raiz, "cat-file", "blob", objeto.decode())

    def linhas(self, caminho: str) -> tuple[str, ...]:
        _caminho(caminho)
        if caminho not in self._cache:
            try:
                self._cache[caminho] = tuple(
                    self.ler(caminho, MAX_BYTES_FONTE).decode("utf-8").splitlines()
                )
            except (ValueError, OSError, RuntimeError):
                self._cache[caminho] = None
        valor = self._cache[caminho]
        if valor is None:
            raise MemoriaErro("fonte ausente, ilegível ou fora dos limites")
        return valor


@dataclass(frozen=True)
class Local:
    caminho: str
    inicio: int
    fim: int
    sha256: str

    def json(self) -> dict:
        return {"caminho": self.caminho, "inicio": self.inicio, "fim": self.fim,
                "sha256": self.sha256}


def _localizar(fontes: Fontes, ev: Evidencia) -> Local:
    linhas = fontes.linhas(ev.caminho)
    trecho = tuple(ev.trecho.split("\n"))
    n = len(trecho)
    pos = [i for i, linha in enumerate(linhas)
           if linha == trecho[0] and linhas[i:i + n] == trecho]
    if len(pos) != 1:
        raise MemoriaErro("trecho ausente ou ambíguo na fonte")
    return Local(ev.caminho, pos[0] + 1, pos[0] + n, ev.sha256)


@dataclass(frozen=True)
class Registro:
    nota: Nota
    locais: tuple[Local, ...]

    def json(self) -> dict:
        return {
            "id": self.nota.id, "tipo": self.nota.tipo, "titulo": self.nota.titulo,
            "resumo": self.nota.resumo, "revisada_em": self.nota.revisada_em.isoformat(),
            "rever_em": self.nota.rever_em.isoformat(),
            "evidencias": [local.json() for local in self.locais],
        }


def _normalizar(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def _tokens(s: str) -> set[str]:
    termos = set(re.findall(r"[a-z0-9]{2,}", _normalizar(s))) - _STOP
    # Normalização leve de plural em português; não exige modelo, dicionário ou rede.
    return {t[:-3] + "ao" if len(t) > 4 and t.endswith("oes") else
            t[:-1] if len(t) > 4 and t[-2:] in ("as", "es", "is", "os", "us") else t
            for t in termos}


def _fonte_atual(consulta: str) -> str | None:
    """Encaminha perguntas diretas de estado; consultas de procedimento continuam na busca."""
    q = _normalizar(consulta).strip()
    if re.match(r"^(como|por que|porque|quando|onde|em que)\b", q):
        return None
    if not re.search(r"\b(agora|hoje|atualmente|ultim[oa]s?)\b|\bestado atual\b", q):
        return None
    if re.search(r"\b(portal|pages)\b", q):
        return "Confira o portal servido e a procedência em docs/cdp/SITE.md."
    if re.search(r"\b(p&l|retorno|resultado|pl|preco|patrimonio)\b", q):
        return "Consulte o relatório oficial da data e os fatos calculados pelo código."
    if re.search(r"\b(cobertura|emissor(?:es)?)\b", q) and re.search(
        r"\b(fila|notas?|emissor(?:es)?)\b", q
    ):
        return "Consulte a agenda de cobertura e a fila da nota no clone de operação."
    if re.search(r"\b(kill switch|executor|rotina|agenda|cotacoes?|carteira|posic(?:ao|oes)|"
                 r"montagem|pendencias?|fechamento|trava|cobertura|risco)\b", q):
        return "Consulte o estado e a agenda no clone de operação."
    return None


class Catalogo:
    def __init__(self, fontes: Fontes, data: date):
        self.fontes, self.data = fontes, data
        self.problemas: list[dict[str, str]] = []
        self.contagens = dict.fromkeys(("candidata", "curada", "retirada", "vencida",
                                       "futura", "substituida", "disponivel"), 0)
        notas: dict[str, Nota] = {}
        registros: dict[str, Registro] = {}
        for caminho in fontes.catalogo():
            id_ = Path(caminho).stem
            try:
                bruto = fontes.ler(caminho, MAX_BYTES_NOTA)
                json.loads(bruto, object_pairs_hook=_chaves_unicas)
                nota = Nota.model_validate_json(bruto)
                if nota.id != id_:
                    raise MemoriaErro("ID diverge do nome do arquivo")
            except ValidationError as exc:
                campos = ", ".join(sorted({str(e["loc"][0]) if e["loc"] else "objeto"
                                           for e in exc.errors(include_input=False)}))
                self._problema(id_, "schema", campos)
                continue
            except (ValueError, OSError, RuntimeError):
                self._problema(id_, "arquivo", "arquivo ilegível ou ID divergente")
                continue
            notas[id_] = nota
            self.contagens[nota.estado] += 1
            if nota.estado == "retirada":
                continue
            locais = []
            for ev in nota.evidencias:
                try:
                    locais.append(_localizar(fontes, ev))
                except MemoriaErro as exc:
                    self._problema(id_, "evidencia", f"{ev.caminho}: {exc}")
            if len(locais) == len(nota.evidencias):
                registros[id_] = Registro(nota, tuple(locais))

        for id_, nota in notas.items():
            for alvo in nota.substitui:
                anterior = notas.get(alvo)
                if (not anterior or nota.registrada_em <= anterior.registrada_em
                        or not set(anterior.escopos).issubset(nota.escopos)):
                    self._problema(id_, "substituicao", f"alvo inexistente, sem precedência ou escopo: {alvo}")
        self.notas = notas
        invalidas = {p["id"] for p in self.problemas}
        # Uma substituição com data de revisão alcançada encerra o uso da versão anterior.
        # Se a evidência da sucessora falhar depois, não ressuscite a versão conhecida como antiga.
        substitu = {alvo for n in notas.values() if n.estado in ("curada", "retirada")
                    and n.revisada_em <= data and n.registrada_em <= data
                    and not any(p["id"] == n.id and p["codigo"] == "substituicao"
                                for p in self.problemas)
                    for alvo in n.substitui}
        self.ativos: list[Registro] = []
        for id_, nota in notas.items():
            if nota.estado != "curada":
                continue
            if id_ in substitu:
                self.contagens["substituida"] += 1
            elif data < nota.revisada_em:
                self.contagens["futura"] += 1
            elif data >= nota.rever_em:
                self.contagens["vencida"] += 1
            elif id_ not in invalidas:
                self.ativos.append(registros[id_])

        resumos: dict[str, list[Registro]] = {}
        for reg in self.ativos:
            resumos.setdefault(" ".join(reg.nota.resumo.lower().split()), []).append(reg)
        duplicatas = {a.nota.id for grupo in resumos.values() for a in grupo for b in grupo
                      if a != b and set(a.nota.escopos).intersection(b.nota.escopos)}
        for id_ in sorted(duplicatas):
            self._problema(id_, "duplicata", "resumo ativo repetido no mesmo escopo")
        self.ativos = [r for r in self.ativos if r.nota.id not in duplicatas]
        self.contagens["disponivel"] = len(self.ativos)
        self._primarias: dict[str, list[tuple[int, set[str]]]] = {}

    def _problema(self, id_: str, codigo: str, detalhe: str) -> None:
        self.problemas.append({"id": id_, "codigo": codigo, "detalhe": detalhe})

    def contexto(self, escopo: Escopo) -> dict:
        destacados = sorted((r for r in self.ativos if escopo in r.nota.escopos and r.nota.destaque),
                             key=lambda r: (len(r.nota.escopos), r.nota.id))
        out = {"revisao": self.fontes.revisao, "data": self.data.isoformat(), "escopo": escopo,
               "aviso": _AVISO, "catalogo_com_ressalvas": bool(self.problemas),
               "fontes": list(_primarias(escopo)[:3]), "notas": []}
        for reg in destacados[:LIMITE_CONTEXTO]:
            out["notas"].append(reg.json())
            if max(len((json.dumps(out, ensure_ascii=False, indent=2) + "\n").encode()),
                   len(render_contexto(out).encode())) > LIMITE_CONTEXTO_BYTES:
                out["notas"].pop()
                break
        return out

    def buscar(self, escopo: Escopo, consulta: str, limite: int) -> dict:
        atual = _fonte_atual(consulta)
        termos = _tokens(consulta)
        notas = []
        if termos and not atual:
            for reg in self.ativos:
                n = reg.nota
                if escopo not in n.escopos:
                    continue
                chave = _tokens(n.titulo + " " + " ".join(n.tags))
                resumo = _tokens(n.resumo)
                comuns = termos & (chave | resumo)
                # Sobreposição mínima evita forçar uma lembrança com coincidência incidental.
                if (len(comuns) >= min(2, len(termos)) and termos & chave
                        and len(comuns) * 3 >= len(termos)):
                    pontos = 3 * len(termos & chave) + len(termos & resumo)
                    notas.append((-pontos, -len(comuns), n.id, reg))
        notas.sort(key=lambda v: v[:3])
        primarias = self.buscar_fontes(escopo, consulta, limite)
        return {"revisao": self.fontes.revisao, "data": self.data.isoformat(), "escopo": escopo,
                "aviso": _AVISO, "catalogo_com_ressalvas": bool(self.problemas),
                "notas": [r.json() for *_, r in notas[:limite]],
                "fontes": primarias, "orientacao_atual": atual}

    def buscar_fontes(self, escopo: Escopo, consulta: str, limite: int) -> list[dict]:
        termos = _tokens(consulta)
        achados = []
        if not termos:
            return []
        for ordem, caminho in enumerate(_primarias(escopo)):
            if caminho not in self._primarias:
                try:
                    linhas = self.fontes.linhas(caminho)
                except MemoriaErro:
                    continue
                janelas = [(i + 1, _tokens(" ".join(linhas[i:i + 6])))
                           for i, linha in enumerate(linhas) if linha.strip()]
                self._primarias[caminho] = janelas
            pontuado = [(len(termos & texto), -len(texto), -num)
                        for num, texto in self._primarias[caminho]]
            pontos, _, linha = max(pontuado, default=(0, 0, 0))
            if pontos >= min(2, len(termos)) and pontos * 3 >= len(termos):
                achados.append((-pontos, ordem, caminho, -linha))
        return [{"caminho": caminho, "inicio": linha}
                for _, _, caminho, linha in sorted(achados)[:limite]]


def _primarias(escopo: Escopo) -> tuple[str, ...]:
    return (tuple(f"docs/cdp/{nome}.md" for nome in ESCOPO[escopo]) + ("AGENTS.md",)
            + FONTES_CODIGO.get(escopo, ()))


def _hoje() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def propor(fontes: Fontes, *, id_: str, escopo: Escopo, caminho: str, inicio: int, fim: int,
           data: date, tipo: Tipo, titulo: str, resumo: str) -> Nota:
    linhas = fontes.linhas(caminho)
    if not 1 <= inicio <= fim <= len(linhas):
        raise MemoriaErro("intervalo de linhas fora da fonte")
    trecho = "\n".join(linhas[inicio - 1:fim])
    ev = Evidencia(caminho=caminho, trecho=trecho, sha256=_sha(trecho))
    _localizar(fontes, ev)
    return Nota(id=id_, tipo=tipo, estado="candidata", titulo=titulo, resumo=resumo,
                escopos=[escopo], tags=[], registrada_em=data, revisada_em=None, rever_em=None,
                destaque=False, substitui=[], evidencias=[ev])


def avaliar(catalogo: Catalogo, casos: list[_Caso], limite: int = 3) -> dict:
    """Compara recuperação de caminhos com o mesmo orçamento nas duas abordagens."""
    resultados = []
    for caso in casos:
        busca = catalogo.buscar(caso.escopo, caso.consulta, limite)
        ids = [n["id"] for n in busca["notas"]]
        direta = [f["caminho"] for f in busca["fontes"]]
        com_memoria = list(dict.fromkeys(
            [e["caminho"] for n in busca["notas"] for e in n["evidencias"]] + direta
        ))[:limite]
        resultados.append({
            "id": caso.id, "notas": ids, "busca_direta": direta, "memoria_e_busca": com_memoria,
            "nota_esperada_recuperada": bool(set(ids) & set(caso.notas_esperadas))
            if caso.notas_esperadas else None,
            "absteve_de_nota": not ids if not caso.fontes_esperadas else None,
            "absteve_em_busca_direta": not ids if caso.fontes_esperadas
            and not caso.notas_esperadas else None,
            "fonte_direta_recuperada": bool(set(direta) & set(caso.fontes_esperadas))
            if caso.fontes_esperadas else None,
            "fonte_com_memoria_recuperada": bool(set(com_memoria) & set(caso.fontes_esperadas))
            if caso.fontes_esperadas else None,
        })
    medidas = {}
    for chave in ("nota_esperada_recuperada", "absteve_de_nota", "absteve_em_busca_direta",
                  "fonte_direta_recuperada", "fonte_com_memoria_recuperada"):
        validos = [r[chave] for r in resultados if r[chave] is not None]
        medidas[chave] = {"acertos": sum(validos), "casos": len(validos)}
    return {"revisao": catalogo.fontes.revisao, "data": catalogo.data.isoformat(),
            "limite": limite, "catalogo_com_ressalvas": bool(catalogo.problemas),
            "medidas": medidas, "casos": resultados}


def render_contexto(contexto: dict, *, nivel: int = 1) -> str:
    topo = "#" * nivel
    escopo = contexto["escopo"]
    linhas = [f"{topo} Memória do CDP — {escopo}", "", contexto["aviso"], "",
              f"Revisão Git: {contexto['revisao']} · referência: {contexto['data']}.", ""]
    if contexto["catalogo_com_ressalvas"]:
        linhas += ["O catálogo tem ressalvas; notas inválidas foram excluídas.", ""]
    if not contexto["notas"]:
        linhas += ["Sem notas destacadas e válidas para este escopo nesta data.", ""]
    for nota in contexto["notas"]:
        fontes = "; ".join(f"{e['caminho']}:{e['inicio']}–{e['fim']} (SHA-256 {e['sha256']})"
                           for e in nota["evidencias"])
        linhas += [f"- **{nota['titulo']}** ({nota['id']}): {nota['resumo']}",
                   f"  Evidência: {fontes}."]
    linhas += ["", "Fontes para consulta: " + ", ".join(contexto["fontes"]) + ".", ""]
    return "\n".join(linhas)


def _relatorio(c: Catalogo) -> dict:
    fila = [{"id": p["id"], "acao": p["codigo"], "detalhe": p["detalhe"]} for p in c.problemas]
    for id_, nota in c.notas.items():
        if nota.estado == "candidata":
            fila.append({"id": id_, "acao": "revisar_candidata",
                         "detalhe": "conferir a alegação nas fontes; aceitar, corrigir ou descartar"})
        if nota.estado == "curada" and c.data >= nota.rever_em:
            fila.append({"id": id_, "acao": "rever_validade",
                         "detalhe": nota.rever_em.isoformat()})
    for i, a in enumerate(c.ativos):
        for b in c.ativos[i + 1:]:
            if not set(a.nota.escopos) & set(b.nota.escopos):
                continue
            ta, tb = _tokens(a.nota.resumo), _tokens(b.nota.resumo)
            if len(ta & tb) >= 5 and len(ta & tb) * 5 >= len(ta | tb) * 4:
                fila.append({"id": a.nota.id, "acao": "comparar_semelhanca", "detalhe": b.nota.id})
    return {"ok": not c.problemas, "base_git": c.fontes.revisao,
            "origem": "árvore de trabalho" if c.fontes.trabalho else "revisão Git",
            "data": c.data.isoformat(), "contagens": c.contagens,
            "problemas": c.problemas, "fila_de_revisao": fila,
            "aviso": "A fila propõe revisões. Nenhuma nota foi gravada, promovida ou descartada."}


def _data(valor: str) -> date:
    try:
        d = date.fromisoformat(valor)
        if d.isoformat() == valor:
            return d
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("use AAAA-MM-DD")


def _intervalo(s: str) -> tuple[int, int]:
    if not re.fullmatch(r"[1-9][0-9]{0,6}:[1-9][0-9]{0,6}", s):
        raise argparse.ArgumentTypeError("use N:M com os números inicial e final, inclusivos")
    return tuple(map(int, s.split(":")))


def _json(obj: object) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _comando(args: argparse.Namespace) -> int:
    try:
        acao = args.acao_memoria
        trabalho = acao == "auditar" and not args.revisao_git
        if trabalho and os.name != "posix":
            raise MemoriaErro("auditoria da árvore de trabalho requer POSIX; use --revisao-git")
        fontes = Fontes(raiz_repo(), trabalho=trabalho)
        if acao == "propor":
            inicio, fim = args.linhas
            nota = propor(fontes, id_=args.id, escopo=args.escopo, caminho=args.evidencia,
                          inicio=inicio, fim=fim, data=args.data or _hoje(), tipo=args.tipo,
                          titulo=args.titulo, resumo=args.resumo)
            print(nota.model_dump_json(indent=2))
            return 0
        if acao == "avaliar":
            bruto = fontes.ler(AVALIACAO, 65536)
            json.loads(bruto, object_pairs_hook=_chaves_unicas)
            corpus = _Avaliacao.model_validate_json(bruto)
            if len({c.id for c in corpus.casos}) != len(corpus.casos):
                raise MemoriaErro("casos repetidos na avaliação")
            for caso in corpus.casos:
                if caso.notas_esperadas and not caso.fontes_esperadas:
                    raise MemoriaErro("caso de recuperação de notas exige fonte esperada")
                for caminho in caso.fontes_esperadas:
                    fontes.linhas(caminho)
            c = Catalogo(fontes, corpus.data)
            rel = avaliar(c, corpus.casos)
            _json(rel)
            return int(bool(c.problemas))
        c = Catalogo(fontes, args.data or _hoje())
        if acao == "contexto":
            out = c.contexto(args.escopo)
            if args.formato == "md":
                print(render_contexto(out), end="")
            else:
                _json(out)
        elif acao == "buscar":
            _json(c.buscar(args.escopo, args.consulta, args.limite))
        else:
            _json(_relatorio(c))
            return int(bool(c.problemas))
        return 0
    except ValidationError:
        print("Memória indisponível: formato de nota ou corpus inválido.", file=sys.stderr)
    except (ValueError, OSError, RuntimeError) as exc:
        detalhe = str(exc) if isinstance(exc, MemoriaErro) else "entrada ou fonte inválida"
        print(f"Memória indisponível: {detalhe}.", file=sys.stderr)
    return 1


def registrar(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("memoria", help="lições e evidências para continuidade entre sessões")
    acoes = p.add_subparsers(dest="acao_memoria", required=True)
    for acao, ajuda in (
        ("contexto", "mostra um índice breve e as notas destacadas de um escopo"),
        ("buscar", "busca notas curadas e fontes primárias do escopo"),
        ("propor", "imprime um rascunho de nota com evidência da revisão Git"),
        ("auditar", "verifica a árvore de trabalho e gera uma fila de consolidação"),
        ("avaliar", "executa a comparação offline do corpus da revisão Git"),
    ):
        s = acoes.add_parser(acao, help=ajuda)
        s.set_defaults(func=_comando)
        if acao != "avaliar":
            s.add_argument("--data", type=_data, help="data de referência (padrão: Brasília)")
        if acao in ("contexto", "buscar", "propor"):
            s.add_argument("--escopo", choices=tuple(ESCOPO), required=True)
        if acao == "auditar":
            s.add_argument("--revisao-git", action="store_true",
                           help="audita o HEAD em vez da árvore de trabalho")
        if acao == "contexto":
            s.add_argument("--formato", choices=("md", "json"), default="md")
        if acao == "buscar":
            s.add_argument("--consulta", required=True, type=_consulta)
            s.add_argument("--limite", type=int, choices=range(1, 11), default=5)
        if acao == "propor":
            s.add_argument("--id", required=True)
            s.add_argument("--evidencia", required=True, help="caminho relativo da fonte")
            s.add_argument("--linhas", type=_intervalo, required=True, help="intervalo inclusivo N:M")
            s.add_argument("--tipo", choices=("procedimento", "licao", "episodio"), default="licao")
            s.add_argument("--titulo", default="Preencher após conferir a evidência")
            s.add_argument("--resumo", default="Descrever a lição e seus limites para revisão.")


def _consulta(valor: str) -> str:
    if 1 <= len(valor) <= 240 and not any(unicodedata.category(c).startswith("C") for c in valor):
        return valor
    raise argparse.ArgumentTypeError("use texto em uma linha de até 240 caracteres")
