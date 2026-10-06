"""Portal público do CDP (GitHub Pages) — ``cdp site construir|conferir|estaticos``.

Monta, a partir do repositório (livro, relatórios e configuração já gravados pelo executor), um
site estático completo em ``--saida`` (nunca grava em outro lugar):

- ``index.html`` — o painel de gestão (casca do template + ``data.json`` sem os cortes de tamanho
  do artifact), embrulhado num documento completo: ``lang="pt-BR"``, SEO, Open Graph, política de
  segurança de conteúdo, dados estruturados (schema.org ``WebSite`` + ``Dataset``), aviso legal
  e o bloco "Transparência e auditoria";
- ``dados/`` — dados abertos para auditoria: cópias fiéis dos arquivos do livro, dos relatórios e
  da configuração (nunca números recalculados; sem resultados da carteira-sombra; nada anterior
  à data de início do mandato), catálogo ``dados/index.html`` e ``dados/datapackage.json``
  (Frictionless Data Package v2, com tamanho e SHA-256 de cada arquivo);
- ``404.html``, ``robots.txt``, ``sitemap.xml``, ícones e imagem de compartilhamento (``site/``);
- ``manifest.json`` (versão do repositório de origem, instante, SHA-256 de cada arquivo) e
  ``SHA256SUMS`` (``sha256sum -c``).

Determinístico por versão do repositório: ``--agora`` padrão = instante do commit ``HEAD``.
Recusa montar com o livro aguardando a abertura na data de início e com ``cdp verify`` falhando.
``--demo`` monta a demonstração offline (DADOS SIMULADOS, fora dos buscadores).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import shutil
import sys
import tempfile
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from . import SIMULATED_DATA_NOTICE

SITE_PADRAO = Path("configs/cdp/site.yaml")
ESTATICOS = Path("site")
FUSO = ZoneInfo("America/Sao_Paulo")
MAX_ARQUIVO = 25 * 1024 * 1024
MAX_SITE = 900 * 1024 * 1024
GRANDE = 10**9
PROIBIDOS = re.compile(r"(^|/)(\.env.*|.*\.pem|.*\.key|id_rsa.*|credentials.*|.*secret.*|"
                       r"\.git(/.*)?|\.cdp(/.*)?)$", re.I)
_REF_RE = re.compile(r'(?:href|src)="([^"]+)"')
_HEAD_RE = re.compile(r"\s*(<title>.*?</title>|<(?:meta|link|base)\b[^>]*>|<style\b.*?</style>)",
                      re.S | re.I)
_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: Pastas de relatórios derivadas da carteira (nada anterior à data de início é publicado).
RELATORIOS_DA_CARTEIRA = ("daily", "weekly", "risk", "semanal")
#: Caminhos cujas mudanças em ``main`` remontam o portal — os mesmos do filtro ``on.push.paths``
#: de ``.github/workflows/cdp-site.yml`` (teste confere) e da checagem ``PORTAL_DEFASADO`` de
#: ``cdp estado``.
CAMINHOS_DO_PORTAL = ("book", "reports", "data", "configs/cdp", "src/cdp", "site",
                      "docs/cdp/marca", "pyproject.toml", "uv.lock",
                      ".github/workflows/cdp-site.yml")
#: Nota de calendário que o motor de backtest grava em ``metrics.json`` (``notes``), por regra
#: de rebalanceamento: o portal só publica backtests da metodologia em vigor.
MARCA_CALENDARIO = {"last": "Calendário: rebalanceamento no último pregão da semana na NYSE",
                    "first": "Calendário: rebalanceamento no 1º pregão da semana da B3"}
EXCLUIR_NOMES = frozenset({"attempts.json", ".gitkeep", ".DS_Store"})
FORMATOS = {
    ".csv": ("csv", "text/csv", "Planilha (CSV)"),
    ".json": ("json", "application/json", "Dados estruturados (JSON)"),
    ".jsonl": ("jsonl", "application/jsonl", "Registro sequencial (JSONL)"),
    ".md": ("md", "text/markdown", "Texto (Markdown)"),
    ".html": ("html", "text/html", "Página (HTML)"),
    ".yaml": ("yaml", "application/yaml", "Configuração (YAML)"),
    ".yml": ("yaml", "application/yaml", "Configuração (YAML)"),
    ".parquet": ("parquet", "application/vnd.apache.parquet", "Tabela colunar (Parquet)"),
    ".txt": ("txt", "text/plain", "Texto"),
    ".gz": ("gz", "application/gzip", "Arquivo compactado (gzip)"),
    ".pdf": ("pdf", "application/pdf", "Documento (PDF)"),
}
FONTES_PUBLICAS = (
    ("CVM — dados abertos (DFP, ITR, FRE, IPE)", "https://dados.cvm.gov.br"),
    ("SEC EDGAR (filings e XBRL)", "https://www.sec.gov/edgar"),
    ("B3 — dados públicos", "https://www.b3.com.br"),
    ("Banco Central do Brasil (SGS)", "https://www.bcb.gov.br"),
    ("Banxico e INEGI", "https://www.banxico.org.mx"),
    ("FRED (Federal Reserve Bank of St. Louis)", "https://fred.stlouisfed.org"),
    ("Damodaran Online (NYU Stern)", "https://pages.stern.nyu.edu/~adamodar/"),
    ("Yahoo Finance (cotações e consenso público)", "https://finance.yahoo.com"),
)


class ErroSite(RuntimeError):
    """Montagem recusada (guarda) ou saída inválida. ``codigo`` é a saída da CLI: 3 = livro
    aguardando a abertura na data de início (nada a publicar ainda; o workflow só pula), 1 =
    recusa que exige atenção (integridade, saída inválida)."""

    def __init__(self, mensagem: str, codigo: int = 1) -> None:
        super().__init__(mensagem)
        self.codigo = codigo


AGUARDANDO_ABERTURA = 3


# ==========================================================================================
# Configuração
# ==========================================================================================


def carregar_site(raiz: Path | str = ".") -> dict[str, Any]:
    padrao = {"titulo": "CDP — Cabra da Peste", "titulo_curto": "CDP — Cabra da Peste",
              "descricao": "Carteira simulada long/short de ações da América Latina.",
              "base_url": "https://arielassayag.github.io/MarketSummary",
              "repositorio": "arielassayag/MarketSummary", "indexar": True,
              "aviso_legal": "Carteira simulada. Não é oferta nem recomendação de investimento.",
              "licenca": {"codigo": None, "conteudo": None},
              "downloads": {"risco_ultimas": 20},
              "og": {"imagem": "site/og.png", "alt": "CDP — Cabra da Peste"}}
    path = Path(raiz) / SITE_PADRAO
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        raw = {}
    cfg = {**padrao, **{k: v for k, v in raw.items() if v is not None}}
    for k in ("descricao", "aviso_legal", "titulo"):
        cfg[k] = " ".join(str(cfg[k]).split())
    cfg["base_url"] = str(cfg["base_url"]).rstrip("/")
    return cfg


# ==========================================================================================
# Utilidades
# ==========================================================================================


def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _gravar(path: Path, texto: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(texto, bytes):
        path.write_bytes(texto)
    else:
        path.write_text(texto, encoding="utf-8", newline="\n")


def _tamanho(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB".replace(".", ",")
    return f"{n / 1024 / 1024:.1f} MB".replace(".", ",")


def _git(args: list[str], raiz: Path) -> str:
    from .executor import git

    r = git(args, raiz)
    return r.stdout.strip() if r.returncode == 0 else ""


def _instante_do_commit(raiz: Path) -> datetime | None:
    v = _git(["show", "-s", "--format=%cI", "HEAD"], raiz)
    try:
        return datetime.fromisoformat(v) if v else None
    except ValueError:
        return None


def _base_path(base_url: str) -> str:
    resto = base_url.split("://", 1)[-1]
    caminho = resto.partition("/")[2].strip("/")
    return "/" + caminho + "/" if caminho else "/"


# ==========================================================================================
# Dados do painel (perfil sem cortes)
# ==========================================================================================


def limites_site() -> Any:
    """Limites do nível 0 do artifact com todas as contagens e textos liberados (o Pages não
    tem o teto de 260 KB): só os resultados da carteira-sombra ficam de fora."""
    from .workflow.painel_publicacao import NIVEIS

    base = NIVEIS[0]
    mudancas: dict[str, Any] = {}
    for f in fields(base):
        v = getattr(base, f.name)
        if isinstance(v, bool):
            mudancas[f.name] = True
        elif isinstance(v, int):
            mudancas[f.name] = GRANDE
    if "posicoes_sombra" in mudancas:
        mudancas["posicoes_sombra"] = 0
    return replace(base, **mudancas)


def backtests_vigentes(rt: Any) -> tuple[list[str], list[str]]:
    """``(vigentes, fora)``: pastas de ``reports/backtest/`` da metodologia em vigor (as notas
    de calendário de todos os ``metrics.json`` da pasta seguem a regra de rebalanceamento atual
    de ``configs/cdp/fund.yaml``) e as demais (calibrações de metodologia substituída ou sem
    nota de calendário — falha fechada: ficam fora do portal, só no repositório)."""
    from .backtest.engine import rebalance_rule

    raiz = Path(rt.reports_root) / "backtest"
    if not raiz.is_dir():
        return [], []
    regra = rebalance_rule(rt.cfg)[0]
    marca = MARCA_CALENDARIO[regra]
    outras = [m for r, m in MARCA_CALENDARIO.items() if r != regra]
    vigentes, fora = [], []
    for pasta in sorted(p for p in raiz.iterdir() if p.is_dir()):
        notas_cal: list[str] = []
        for m in sorted(pasta.rglob("metrics.json")):
            try:
                raw = json.loads(m.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            notas = raw.get("notes") if isinstance(raw, dict) else None
            notas_cal += [str(n) for n in notas or [] if str(n).startswith("Calendário:")]
        ok = (bool(notas_cal) and all(n.startswith(marca) for n in notas_cal)
              and not any(n.startswith(o) for n in notas_cal for o in outras))
        (vigentes if ok else fora).append(pasta.name)
    return vigentes, fora


def dados_do_painel(rt: Any, agora: datetime, reports_dir: str = "dados/relatorios"
                    ) -> dict[str, Any]:
    """``data.json`` do portal: o painel completo com os limites do artifact liberados (trilha
    e monitor de risco inteiros) e só os backtests da metodologia em vigor."""
    from .workflow.painel import page_sha256, painel_data
    from .workflow.painel_publicacao import publicacao

    vigentes, fora = backtests_vigentes(rt)
    with tempfile.TemporaryDirectory(prefix="cdp_site_bt_") as tmp:
        bt_root: Path | None = None
        if fora:  # só as pastas vigentes, numa cópia (os ids relativos não mudam)
            bt_root = Path(tmp) / "backtest"
            bt_root.mkdir()
            for nome in vigentes:
                shutil.copytree(Path(rt.reports_root) / "backtest" / nome, bt_root / nome)
        full = painel_data(rt, now=agora, profile="completo", max_daily_reports=GRANDE,
                           full_weeks=GRANDE, full_research_weeks=GRANDE, max_risk_runs=GRANDE,
                           max_risk_full_runs=GRANDE, audit_tail=GRANDE, backtest_root=bt_root)
    return publicacao(full, reports_dir=reports_dir, niveis=(limites_site(),),
                      page_sha256=page_sha256())


# ==========================================================================================
# Dados abertos (dados/)
# ==========================================================================================


@dataclass
class Arquivo:
    destino: str          # caminho no site (dados/...)
    origem: str | None    # caminho no repositório (para o link fixado na versão)
    grupo: str
    descricao: str
    bytes_: int = 0
    sha256: str = ""


GRUPOS = (
    ("carteira", "Carteira em vigor", "A carteira decidida mais recente, com ordens, tese e "
                                      "decisão."),
    ("livro", "Livro do fundo", "Decisões semanais, propostas otimizadas, pesquisa estruturada e "
                                "teses de investimento, semana a semana."),
    ("registro", "Registro diário", "Valor da cota, retorno, risco e atribuição de cada pregão, "
                                    "em registros encadeados."),
    ("cobertura", "Cobertura de ações e ETFs", "Modelos abertos de valuation e preços-alvo de 12 "
                                               "meses, com insumos e fontes públicas."),
    ("relatorios", "Relatórios", "Relatórios diários, semanais e da decisão, com os fatos usados."),
    ("risco", "Monitor de risco", "Leituras intradiárias e de fechamento do monitor de risco."),
    ("metodologia", "Pesquisa de metodologia", "Backtests e calibração do processo."),
    ("configuracao", "Mandato e parâmetros", "Limites do mandato e parâmetros dos modelos."),
    ("auditoria", "Trilha de auditoria", "Eventos encadeados e resultado da verificação de "
                                         "integridade desta publicação."),
)
_NOMES_GRUPO = {g: (t, d) for g, t, d in GRUPOS}


def _descricao(rel: str) -> str:
    """Descrição pt-BR de um arquivo do livro ou dos relatórios (por padrão do caminho)."""
    nome = rel.rsplit("/", 1)[-1]
    regras = (
        (r"positions_v\d+\.csv$", "Carteira decidida: posições, lados e pesos"),
        (r"trades_v\d+\.csv$", "Ordens da montagem (execução no leilão de fechamento)"),
        (r"decision_v\d+\.json$", "Decisão do gestor autônomo e controles de risco aplicados"),
        (r"proposal_v\d+\.json$", "Proposta otimizada: formulação, restrições e risco ex-ante"),
        (r"memo_v\d+\.md$", "Memorando da decisão"),
        (r"booked\.json$", "Carteira registrada no livro"),
        (r"config_decisao\.json$", "Mandato vigente na decisão"),
        (r"inputs/pm_decision\.json$", "Juízos do gestor (postura, convicções e exclusões)"),
        (r"research_pack[^/]*\.json$", "Pesquisa estruturada da semana (juízos com fontes "
                                       "públicas)"),
        (r"briefing/news\.jsonl$|live/news\.jsonl$", "Notícias públicas coletadas (dados não "
                                                     "confiáveis, só contexto)"),
        (r"briefing/", "Material preparado pelo código para a pesquisa"),
        (r"(tese|carteira_atual)/tese\.md$", "Tese de investimento da carteira"),
        (r"(tese|carteira_atual)/tese_publicada\.json$", "Tese de investimento publicada "
                                                         "(registro)"),
        (r"tese/tese\.json$", "Tese de investimento (texto validado)"),
        (r"tese/(fatos\.md|factbook\.json)$", "Fatos numéricos da tese (calculados pelo código)"),
        (r"tese/analise\.json$", "Análise da carteira que fundamenta a tese"),
        (r"\.schema\.json$", "Esquema de validação"),
        (r"track_record\.csv$", "Registro diário do fundo: valor da cota, retorno e risco"),
        (r"track_record/records/", "Registro diário encadeado"),
        (r"audit_log\.jsonl$", "Trilha de auditoria encadeada (todos os eventos)"),
        (r"genese\.json$", "Abertura do livro na data de início do mandato"),
        (r"KILL_SWITCH$", "Kill switch ligado (motivo e responsável)"),
        (r"cobertura/.*modelos\.csv$", "Resumo dos modelos: preço-alvo, potencial e rating"),
        (r"cobertura/.*etfs\.csv$", "Resumo dos ETFs: valor justo pela carteira subjacente"),
        (r"cobertura/.*/modelos/", "Modelo aberto do emissor: insumos, fórmulas e passos"),
        (r"cobertura/.*/etfs/", "Modelo aberto do ETF"),
        (r"cobertura/.*placar", "Placar dos preços-alvo (acompanhamento)"),
        (r"cobertura/.*contexto", "Contexto macro e de custo de capital"),
        (r"cobertura/.*insumos", "Insumos públicos do modelo (com fonte e data)"),
        (r"cobertura/notas/", "Nota de pesquisa do emissor"),
        (r"cobertura/.*(manifest|selo)", "Manifesto e selo do retrato da cobertura"),
        (r"cobertura/", "Cobertura de ações e ETFs"),
        (r"relatorios/daily/.*relatorio\.(md|html)$", "Relatório diário"),
        (r"relatorios/daily/.*comentario\.json$", "Comentário do dia (texto validado)"),
        (r"relatorios/daily/.*(facts\.md|factbook\.json)$", "Fatos do dia (calculados pelo "
                                                            "código)"),
        (r"relatorios/semanal/.*relatorio\.(md|html)$", "Relatório semanal de resultado"),
        (r"relatorios/semanal/", "Relatório semanal de resultado (fatos e comentário)"),
        (r"relatorios/weekly/", "Relatório da decisão semanal"),
        (r"relatorios/risk/", "Leitura do monitor de risco"),
        (r"relatorios/backtest/.*CALIBRACAO", "Calibração do processo (pesquisa de metodologia)"),
        (r"relatorios/backtest/.*metrics\.json$", "Métricas do backtest"),
        (r"relatorios/backtest/", "Série do backtest (pesquisa de metodologia)"),
        (r"configuracao/fund\.yaml$", "Mandato do fundo: limites, custos e calendário"),
        (r"configuracao/valuation\.yaml$", "Parâmetros dos modelos de valuation"),
        (r"configuracao/", "Parâmetros dos modelos de cobertura"),
    )
    for padrao, desc in regras:
        if re.search(padrao, rel):
            return desc
    return nome


def _sombra(rel: str) -> bool:
    partes = rel.lower().split("/")
    return any("shadow" in p or "sombra" in p or "challenger" in p for p in partes)


def _anterior(partes: tuple[str, ...], inicio: date) -> bool:
    for p in partes:
        if _DATA_RE.match(p) and date.fromisoformat(p) < inicio:
            return True
    return False


def _arquivos_de(raiz: Path) -> Iterable[Path]:
    if not raiz.is_dir():
        return []
    return sorted(p for p in raiz.rglob("*") if p.is_file())


def _rel_repo(p: Path, raiz_repo: Path) -> str | None:
    try:
        return p.resolve().relative_to(raiz_repo.resolve()).as_posix()
    except ValueError:
        return None


def coletar_dados(rt: Any, raiz_repo: Path, *, risco_ultimas: int = 20,
                  desde_o_inicio: bool = True) -> list[tuple[Path, Arquivo]]:
    """``[(origem no disco, Arquivo)]`` publicáveis (cópias fiéis; ver docstring do módulo).
    ``desde_o_inicio``: nada com data anterior a ``fund.inception_date`` (desligado só na
    demonstração, cujo histórico sintético é anterior)."""
    inicio = rt.cfg.fund.inception_date if desde_o_inicio else date.min
    book, reports = Path(rt.book_root), Path(rt.reports_root)
    out: list[tuple[Path, Arquivo]] = []

    def add(p: Path, destino: str, grupo: str) -> None:
        out.append((p, Arquivo(destino=destino, origem=_rel_repo(p, raiz_repo), grupo=grupo,
                               descricao=_descricao(destino))))

    semanas_decididas: list[str] = []
    for p in _arquivos_de(book):
        rel = p.relative_to(book).as_posix()
        partes = tuple(rel.split("/"))
        if p.name in EXCLUIR_NOMES or p.name.startswith(".") or _sombra(rel):
            continue
        if partes[0] == "cobertura":
            add(p, f"dados/livro/{rel}", "cobertura")
            continue
        if _anterior(partes, inicio):
            continue
        if partes[0].startswith("track_record"):
            add(p, f"dados/livro/{rel}", "registro")
        elif _DATA_RE.match(partes[0]):
            add(p, f"dados/livro/{rel}", "livro")
            if re.fullmatch(r"decision_v\d+\.json", p.name) and len(partes) == 2:
                semanas_decididas.append(partes[0])
        else:
            add(p, f"dados/livro/{rel}", "auditoria")
    datas_risco = sorted({p.relative_to(reports).parts[1] for p in _arquivos_de(reports / "risk")
                          if len(p.relative_to(reports).parts) > 2})[-risco_ultimas:]
    bt_vigentes = set(backtests_vigentes(rt)[0])
    for p in _arquivos_de(reports):
        rel = p.relative_to(reports).as_posix()
        partes = tuple(rel.split("/"))
        if p.name in EXCLUIR_NOMES or p.name.startswith(".") or _sombra(rel):
            continue
        if partes[0] in RELATORIOS_DA_CARTEIRA and _anterior(partes, inicio):
            continue
        if partes[0] == "risk":
            if len(partes) < 3 or partes[1] not in datas_risco:
                continue
            grupo = "risco"
        elif partes[0] == "backtest":
            if len(partes) < 3 or partes[1] not in bt_vigentes:
                continue  # metodologia substituída (ou sem nota de calendário): só no repositório
            grupo = "metodologia"
        else:
            grupo = "relatorios"
        add(p, f"dados/relatorios/{rel}", grupo)
    cfg_dir = raiz_repo / "configs" / "cdp"
    for nome in ("fund.yaml", "valuation.yaml"):
        if (cfg_dir / nome).is_file():
            add(cfg_dir / nome, f"dados/configuracao/{nome}", "configuracao")
    for p in _arquivos_de(cfg_dir / "cobertura"):
        rel = p.relative_to(cfg_dir / "cobertura").as_posix()
        if not p.name.startswith("."):
            add(p, f"dados/configuracao/cobertura/{rel}", "configuracao")
    if semanas_decididas:
        sem = sorted(semanas_decididas)[-1]
        for p in _arquivos_de(book / sem):
            rel = p.relative_to(book / sem).as_posix()
            if "/" in rel or p.name in EXCLUIR_NOMES or _sombra(rel):
                continue
            if re.fullmatch(r"(positions|trades|decision|proposal|memo)_v\d+\.\w+", p.name):
                add(p, f"dados/carteira_atual/{rel}", "carteira")
        for nome in ("tese.md", "tese_publicada.json"):
            if (book / sem / "tese" / nome).is_file():
                add(book / sem / "tese" / nome, f"dados/carteira_atual/{nome}", "carteira")
    return out


def _esquema_csv(texto: str) -> dict[str, Any] | None:
    try:
        leitor = csv.reader(io.StringIO(texto))
        cab = next(leitor)
    except (StopIteration, csv.Error):
        return None
    tipos: list[set[str]] = [set() for _ in cab]
    for k, linha in enumerate(leitor):
        if k >= 500:
            break
        for i, v in enumerate(linha[:len(cab)]):
            if v == "":
                continue
            if re.fullmatch(r"-?\d+(\.\d+)?([eE][-+]?\d+)?", v):
                tipos[i].add("number")
            elif _DATA_RE.match(v):
                tipos[i].add("date")
            elif v in ("True", "False", "true", "false"):
                tipos[i].add("boolean")
            else:
                tipos[i].add("string")
    campos = []
    for nome, ts in zip(cab, tipos, strict=False):
        tipo = next(iter(ts)) if len(ts) == 1 else "string" if ts else "any"
        campos.append({"name": nome, "type": tipo})
    return {"fields": campos, "missingValues": [""]}


def _nome_recurso(destino: str, usados: set[str]) -> str:
    base = re.sub(r"[^a-z0-9._-]+", "-", destino.removeprefix("dados/").lower()).strip("-.")
    nome, k = base or "arquivo", 2
    while nome in usados:
        nome, k = f"{base}-{k}", k + 1
    usados.add(nome)
    return nome


# ==========================================================================================
# Páginas
# ==========================================================================================

CSS_SITE = """\
:root{color-scheme:light dark;--bg:#f4efe5;--surface:#fffdf8;--surface-2:#efe8db;--ink:#1d1611;
--ink-2:#4a3e33;--muted:#685a4b;--line:#d8ccb8;--accent:#2b4596;--accent-2:#1e3274;--sol:#b9692f;
--sim:#f2c230;--sim-ink:#1d1700;--foot:#1d1611;--foot-ink:#f1e8d6;
--f-display:"Cinzel","Trajan Pro",Georgia,serif;--f-serif:"Alegreya","Iowan Old Style",Georgia,serif;
--f-body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
--f-mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--gutter:clamp(16px,3vw,36px)}
@media (prefers-color-scheme:dark){:root{--bg:#171310;--surface:#211b16;--surface-2:#2b2219;
--ink:#f1e8d6;--ink-2:#d6c9b1;--muted:#b3a58e;--line:#4d4034;--accent:#b3c3f2;--accent-2:#d0dbfa;
--sol:#e08a45;--foot:#0f0c0a}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 var(--f-body)}
a{color:var(--accent);text-underline-offset:2px}a:hover{color:var(--accent-2)}
a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
code,kbd{font-family:var(--f-mono);font-size:.86em}
.wrap{max-width:1180px;margin:0 auto;padding:0 var(--gutter)}
.mast{border-bottom:2px solid var(--ink);background:var(--surface)}
.mast-in{display:flex;flex-wrap:wrap;gap:12px 24px;align-items:center;justify-content:space-between;
padding:18px var(--gutter)}
.marca{display:flex;align-items:center;gap:16px;color:var(--ink);text-decoration:none}
.marca svg{width:38px;height:38px;flex:none}
.marca-img{position:relative;width:118px;aspect-ratio:960/596;flex:none}
.marca-img i{position:absolute;inset:0;-webkit-mask:var(--m) center/contain no-repeat;mask:var(--m) center/contain no-repeat}
.marca-img .t{--m:url(marca/marca_tinta.webp);background:var(--ink)}
.marca-img .s{--m:url(marca/marca_sol.webp);background:var(--sol)}
@media (forced-colors:active){.marca-img i{forced-color-adjust:none;background:CanvasText}}
@media (max-width:640px){.marca-img{width:92px}.marca small{display:none}}
.marca b{font:700 1.15rem/1.1 var(--f-display);letter-spacing:.06em}
.marca small{display:block;font:.8rem/1.3 var(--f-body);color:var(--muted);letter-spacing:.02em}
.nav{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.92rem}
.regua{height:14px;margin:0;border:0;background:
radial-gradient(circle at 50% 50%,var(--sol) 0 3px,transparent 3.5px) center/14px 14px no-repeat,
linear-gradient(var(--ink),var(--ink)) center/100% 1px no-repeat}
.hero{padding:44px 0 20px}
.hero h1{font:700 clamp(1.7rem,4vw,2.6rem)/1.15 var(--f-display);letter-spacing:.04em;margin:0 0 10px}
.hero p{font:1.12rem/1.55 var(--f-serif);color:var(--ink-2);max-width:62rem;margin:0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:26px 0 8px}
.kpi{background:var(--surface);border:1px solid var(--line);border-top:3px solid var(--ink);padding:14px 16px}
.kpi span{display:block;font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.kpi b{display:block;font:600 1.15rem/1.3 var(--f-body);margin-top:4px;overflow-wrap:anywhere}
section.bloco{margin:34px 0}
section.bloco>h2{font:700 1.25rem/1.2 var(--f-display);letter-spacing:.05em;margin:0 0 6px}
section.bloco>p{color:var(--ink-2);margin:0 0 14px;max-width:64rem}
ol.passos{counter-reset:p;list-style:none;padding:0;margin:0;display:grid;gap:12px;
grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
ol.passos li{counter-increment:p;background:var(--surface);border:1px solid var(--line);padding:16px 16px 14px 56px;position:relative}
ol.passos li::before{content:counter(p);position:absolute;left:14px;top:14px;width:30px;height:30px;
border-radius:50%;background:var(--ink);color:var(--bg);font:700 .95rem/30px var(--f-display);text-align:center}
ol.passos b{display:block;margin-bottom:4px}
pre{background:var(--surface-2);border:1px solid var(--line);padding:10px 12px;overflow-x:auto;
margin:8px 0 0;font:.8rem/1.55 var(--f-mono);white-space:pre;max-width:100%}
ol.passos li{min-width:0}
details.grupo{background:var(--surface);border:1px solid var(--line);margin:0 0 12px}
details.grupo>summary{cursor:pointer;padding:14px 16px;display:flex;flex-wrap:wrap;gap:4px 14px;
align-items:baseline;list-style:none}
details.grupo>summary::-webkit-details-marker{display:none}
details.grupo>summary::before{content:"\\25B8";color:var(--sol);transition:transform .15s}
details.grupo[open]>summary::before{transform:rotate(90deg)}
details.grupo>summary h3{font:700 1.02rem/1.3 var(--f-display);letter-spacing:.05em;margin:0}
details.grupo>summary small{color:var(--muted)}
.tabela{overflow-x:auto;border-top:1px solid var(--line)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.74rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;background:var(--surface-2)}
td.arq a{font-family:var(--f-mono);font-size:.82rem;overflow-wrap:anywhere}
td.num{white-space:nowrap;font-variant-numeric:tabular-nums}
td code{color:var(--ink-2)}
.fontes{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px 18px;padding:0;list-style:none}
.aviso{border-left:4px solid var(--sol);background:var(--surface);padding:12px 16px;color:var(--ink-2);font:.95rem/1.55 var(--f-serif)}
.sim{background:var(--sim);color:var(--sim-ink);font-weight:700;letter-spacing:.04em;padding:8px var(--gutter);text-align:center}
.foot{background:var(--foot);color:var(--foot-ink);margin-top:48px;padding:28px 0 36px;font-size:.88rem}
.foot a{color:var(--foot-ink)}
.foot p{margin:6px 0;max-width:72rem}
.erro{min-height:70vh;display:grid;place-items:center;text-align:center;padding:40px var(--gutter)}
.erro h1{font:700 clamp(1.6rem,5vw,2.4rem)/1.2 var(--f-display);letter-spacing:.05em;margin:16px 0 8px}
.erro p{font:1.1rem/1.5 var(--f-serif);color:var(--ink-2)}
.erro svg{width:64px;height:64px}
@media (max-width:640px){
 table,thead,tbody,tr,th,td{display:block}thead{display:none}
 tr{border-bottom:1px solid var(--line);padding:8px 0}td{border:0;padding:3px 16px}
 td[data-r]::before{content:attr(data-r) ": ";color:var(--muted);font-size:.74rem;text-transform:uppercase;letter-spacing:.05em}
}
@media print{.nav,.sim{display:none}details.grupo{break-inside:avoid}a{color:inherit}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

ESTRELA = ("M50 0 53.6 41.2 71.2 28.8 58.8 46.4 100 50 58.8 53.6 71.2 71.2 53.6 58.8 50 100 "
           "46.4 58.8 28.8 71.2 41.2 53.6 0 50 41.2 46.4 28.8 28.8 46.4 41.2Z")
FAVICON_SVG = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
               "<rect width='100' height='100' rx='18' fill='#1d1611'/>"
               f"<path d='{ESTRELA}' fill='#e08a45' transform='translate(14 14) scale(.72)'/>"
               "</svg>\n")
FONTES_GOOGLE = ("https://fonts.googleapis.com/css2?family=Alegreya:ital,wght@0,400..800;1,400"
                 "&family=Cinzel:wght@600..700&family=IBM+Plex+Mono:wght@400;500"
                 "&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&display=swap")


def _csp(base_url: str) -> str:
    partes = ["default-src 'self'", "script-src 'self' https://cdnjs.cloudflare.com",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "font-src 'self' https://fonts.gstatic.com data:", "img-src 'self' data: blob:",
              "connect-src 'self'", "base-uri 'self'", "form-action 'none'",
              "object-src 'none'"]
    if base_url.startswith("https://"):
        partes.append("upgrade-insecure-requests")
    return "; ".join(partes)


def _marca_svg(cor: str = "currentColor", sol: str = "var(--sol)") -> str:
    return (f'<svg viewBox="0 0 100 100" aria-hidden="true" focusable="false">'
            f'<rect width="100" height="100" rx="18" style="fill:{cor}"/>'
            f'<path d="{ESTRELA}" style="fill:{sol}" transform="translate(14 14) scale(.72)"/>'
            "</svg>")


def _cabeca_comum(cfg: Mapping[str, Any], *, titulo: str, descricao: str, canonico: str,
                  indexar: bool, raiz_rel: str, tem_og: bool) -> list[str]:
    robots = "index, follow, max-image-preview:large" if indexar else "noindex, nofollow"
    out = ['<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           f"<title>{esc(titulo)}</title>",
           f'<meta name="description" content="{esc(descricao)}">',
           f'<meta name="robots" content="{robots}">',
           f'<link rel="canonical" href="{esc(canonico)}">',
           f'<meta http-equiv="Content-Security-Policy" content="{_csp(cfg["base_url"])}">',
           '<meta name="referrer" content="strict-origin-when-cross-origin">',
           '<meta name="color-scheme" content="light dark">',
           '<meta name="theme-color" content="#f4efe5" media="(prefers-color-scheme: light)">',
           '<meta name="theme-color" content="#171310" media="(prefers-color-scheme: dark)">',
           '<meta property="og:type" content="website">',
           '<meta property="og:locale" content="pt_BR">',
           f'<meta property="og:site_name" content="{esc(cfg["titulo_curto"])}">',
           f'<meta property="og:title" content="{esc(titulo)}">',
           f'<meta property="og:description" content="{esc(descricao)}">',
           f'<meta property="og:url" content="{esc(canonico)}">',
           '<meta name="twitter:card" content="summary_large_image">',
           f'<link rel="icon" href="{raiz_rel}favicon.svg" type="image/svg+xml">',
           f'<link rel="apple-touch-icon" href="{raiz_rel}apple-touch-icon.png">']
    if tem_og:
        out += [f'<meta property="og:image" content="{esc(cfg["base_url"])}/og.png">',
                '<meta property="og:image:type" content="image/png">',
                '<meta property="og:image:width" content="1200">',
                '<meta property="og:image:height" content="630">',
                f'<meta property="og:image:alt" content="{esc(cfg["og"].get("alt", ""))}">']
    return out


def _jsonld(obj: Any) -> str:
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
            + "</script>")


def _separar_fragmento(frag: str) -> tuple[list[str], str]:
    cab, i = [], 0
    while m := _HEAD_RE.match(frag, i):
        tag = m.group(1)
        if not re.match(r"<(title|meta\s+charset|link\s+rel=\"icon\")", tag, re.I):
            cab.append(tag)
        i = m.end()
    return cab, frag[i:]


def _rodape_painel(cfg: Mapping[str, Any], commit: str | None, agora: datetime) -> str:
    repo = cfg["repositorio"]
    ver = (commit or "")[:10]
    codigo = (f'<a href="https://github.com/{esc(repo)}/tree/{esc(commit)}">Código e metodologia'
              f'</a> — código aberto na versão do repositório <code>{esc(ver)}</code>'
              if commit else
              f'<a href="https://github.com/{esc(repo)}">Código e metodologia</a> — código aberto')
    return f"""<section class="site-auditoria" aria-labelledby="site-auditoria-t">
<style>
.site-auditoria{{background:var(--surface-2,#efe8db);color:var(--ink,#1d1611);border-top:1px solid var(--line,#d8ccb8);margin-top:40px;padding:28px 0 30px}}
.site-auditoria h2{{font:700 1.1rem/1.2 var(--font-display,Georgia,serif);letter-spacing:.05em;margin:0 0 8px}}
.site-auditoria p{{margin:6px 0;max-width:72rem;color:var(--ink-2,#4a3e33)}}
.site-auditoria ul{{margin:10px 0;padding-left:1.1rem}}
.site-auditoria li{{margin:4px 0}}
.site-auditoria a{{color:var(--accent,#2b4596)}}
.site-auditoria .site-aviso{{font:.95rem/1.55 var(--font-serif,Georgia,serif);border-left:3px solid var(--sol,#b9692f);padding-left:12px;margin-top:14px}}
.site-auditoria .site-meta{{font-size:.82rem;color:var(--muted,#685a4b)}}
</style>
<div class="wrap">
<h2 id="site-auditoria-t">Transparência e auditoria</h2>
<p>Todos os números deste portal são calculados por código aberto a partir de dados públicos e
podem ser conferidos por qualquer pessoa, arquivo por arquivo.</p>
<ul>
<li><a href="dados/">Dados abertos e auditoria</a> — livro, relatórios, modelos, mandato e trilha de auditoria, com código de verificação (SHA-256) de cada arquivo</li>
<li>{codigo}</li>
<li><a href="manifest.json">Manifesto da publicação</a> e <a href="SHA256SUMS">somas de verificação</a></li>
</ul>
<p class="site-aviso">{esc(cfg["aviso_legal"])}</p>
<p class="site-meta">Publicado em {agora.astimezone(FUSO):%d/%m/%Y %H:%M} (Brasília){" · versão do repositório " + esc(ver) if ver else ""}</p>
</div>
</section>
"""


def pagina_inicial(fragmento: str, cfg: Mapping[str, Any], *, indexar: bool, demo: bool,
                   commit: str | None, agora: datetime, meta: Mapping[str, Any],
                   tem_og: bool) -> str:
    titulo = cfg["titulo"]
    descricao = cfg["descricao"]
    if demo:
        titulo = f"{SIMULATED_DATA_NOTICE} — {titulo}"
        descricao = f"{SIMULATED_DATA_NOTICE}: demonstração com mercado sintético. {descricao}"
    base = cfg["base_url"]
    cab = _cabeca_comum(cfg, titulo=titulo, descricao=descricao, canonico=base + "/",
                        indexar=indexar, raiz_rel="", tem_og=tem_og)
    dataset: dict[str, Any] = {
        "@type": "Dataset", "name": f"{cfg['titulo_curto']} — dados abertos",
        "description": descricao, "url": f"{base}/dados/", "inLanguage": "pt-BR",
        "isAccessibleForFree": True, "dateModified": agora.astimezone(UTC).isoformat(),
        "creator": {"@type": "Organization", "name": cfg["titulo_curto"]},
        "keywords": ["carteira simulada", "long/short", "ações", "América Latina",
                     "dados abertos", "auditoria"],
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": f"{base}/data.json"},
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": f"{base}/dados/datapackage.json"}]}
    lic = (cfg.get("licenca") or {}).get("conteudo")
    if lic:
        dataset["license"] = lic
    cab.append(_jsonld({"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "name": cfg["titulo_curto"], "url": f"{base}/",
         "inLanguage": "pt-BR", "description": descricao}, dataset]}))
    extra, corpo = _separar_fragmento(fragmento)
    corpo = corpo.strip()
    rodape = _rodape_painel(cfg, commit, agora)
    marca_rodape = '<footer class="foot" id="foot">'
    corpo = (corpo.replace(marca_rodape, rodape + marca_rodape, 1) if marca_rodape in corpo
             else corpo + "\n" + rodape)
    sim = (f'<div class="site-sim" role="note" style="background:#f2c230;color:#1d1700;'
           f'font-weight:700;text-align:center;padding:8px 16px;letter-spacing:.03em">'
           f"{SIMULATED_DATA_NOTICE} — demonstração com mercado sintético; não é a carteira do "
           "fundo.</div>\n" if demo else "")
    noscript = ('<noscript><p style="padding:16px;max-width:60rem;margin:0 auto">O painel precisa '
                'de JavaScript. Os arquivos do fundo estão em <a href="dados/">Dados abertos e '
                'auditoria</a>.</p></noscript>\n')
    return ("<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n" + "\n".join(cab) + "\n"
            + "\n".join(extra) + "\n</head>\n<body>\n" + sim + noscript + corpo
            + "\n</body>\n</html>\n")


def _pagina(cfg: Mapping[str, Any], *, titulo: str, descricao: str, canonico: str,
            indexar: bool, raiz_rel: str, corpo: str, demo: bool, tem_og: bool) -> str:
    cab = _cabeca_comum(cfg, titulo=titulo, descricao=descricao, canonico=canonico,
                        indexar=indexar, raiz_rel=raiz_rel, tem_og=tem_og)
    cab += ['<link rel="preconnect" href="https://fonts.googleapis.com">',
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
            f'<link rel="stylesheet" href="{esc(FONTES_GOOGLE)}">',
            f'<link rel="stylesheet" href="{raiz_rel}site.css">']
    sim = (f'<div class="sim" role="note">{SIMULATED_DATA_NOTICE} — demonstração com mercado '
           "sintético; não é a carteira do fundo.</div>\n" if demo else "")
    mast = (f'<header class="mast"><div class="mast-in" style="max-width:1180px;margin:0 auto">'
            f'<a class="marca" href="{raiz_rel or "./"}" aria-label="CDP Asset Management — '
            f'Cabra da Peste"><span class="marca-img" role="img" aria-hidden="true"><i class="t">'
            f'</i><i class="s"></i></span>'
            f'<span><b>CABRA DA PESTE</b><small>Carteira simulada long/short · ações da América '
            f'Latina · USD</small></span></a>'
            f'<nav class="nav" aria-label="Portal"><a href="{raiz_rel or "./"}">Painel</a>'
            f'<a href="{raiz_rel}dados/">Dados abertos</a>'
            f'<a href="https://github.com/{esc(cfg["repositorio"])}">Código</a></nav>'
            "</div></header>\n")
    return ("<!doctype html>\n<html lang=\"pt-BR\">\n<head>\n" + "\n".join(cab)
            + "\n</head>\n<body>\n" + sim + mast + corpo + "\n</body>\n</html>\n")


def pagina_404(cfg: Mapping[str, Any], *, demo: bool) -> str:
    base_path = _base_path(cfg["base_url"])
    titulo = "Página não encontrada · " + cfg["titulo_curto"]
    if demo:
        titulo = f"{SIMULATED_DATA_NOTICE} — {titulo}"
    corpo = f"""<main class="erro"><div>
{_marca_svg("var(--ink)")}
<h1>Página não encontrada</h1>
<p>O endereço pode ter mudado com a última publicação do portal.</p>
<p><a href="{esc(base_path)}">Voltar ao painel</a> · <a href="{esc(base_path)}dados/">Dados abertos e auditoria</a></p>
</div></main>"""
    # 404 é servida em qualquer caminho: só endereços absolutos a partir da base.
    return _pagina(cfg, titulo=titulo, descricao=cfg["descricao"],
                   canonico=cfg["base_url"] + "/404.html", indexar=False, raiz_rel=base_path,
                   corpo=corpo, demo=demo, tem_og=False)


def texto_integridade(verificacao: Mapping[str, Any], n_eventos: int | None) -> str:
    """Integridade em linguagem de investidor (a mesma frase do painel)."""
    res = verificacao.get("resultado")
    if res == "ÍNTEGRO":
        if n_eventos:
            return (f"Registro íntegro — {n_eventos} evento{'s' if n_eventos != 1 else ''} "
                    f"conferido{'s' if n_eventos != 1 else ''}")
        return "Registro íntegro"
    if res == "FALHA DE INTEGRIDADE":
        return "Falha de integridade no registro"
    return "Integridade não verificada nesta publicação"


def pagina_dados(cfg: Mapping[str, Any], arquivos: list[Arquivo], *, commit: str | None,
                 agora: datetime, demo: bool, indexar: bool, verificacao: Mapping[str, Any],
                 tem_og: bool, n_eventos: int | None = None) -> str:
    repo = cfg["repositorio"]
    ver = (commit or "")[:10]
    total = sum(a.bytes_ for a in arquivos)
    ref = commit or "main"
    por_grupo: dict[str, list[Arquivo]] = {}
    for a in arquivos:
        por_grupo.setdefault(a.grupo, []).append(a)
    blocos = []
    for chave, titulo, desc in GRUPOS:
        itens = por_grupo.get(chave) or []
        if not itens:
            continue
        linhas = []
        for a in sorted(itens, key=lambda x: x.destino):
            ext = Path(a.destino).suffix.lower()
            fmt = FORMATOS.get(ext, (ext.lstrip("."), "application/octet-stream",
                                     ext.lstrip(".").upper() or "Arquivo"))[2]
            origem = (f' · <a href="https://github.com/{esc(repo)}/blob/{esc(ref)}/'
                      f'{esc(a.origem)}">origem</a>' if a.origem else "")
            rel = a.destino.removeprefix("dados/")
            linhas.append(
                f'<tr><td class="arq" data-r="Arquivo"><a href="{esc(rel)}">{esc(rel)}</a></td>'
                f'<td data-r="Descrição">{esc(a.descricao)}{origem}</td>'
                f'<td data-r="Formato">{esc(fmt)}</td>'
                f'<td class="num" data-r="Tamanho">{_tamanho(a.bytes_)}</td>'
                f'<td data-r="Verificação"><code title="SHA-256: {a.sha256}">'
                f"{a.sha256[:16]}…</code></td></tr>")
        aberto = " open" if chave in ("carteira", "registro", "auditoria") else ""
        blocos.append(
            f'<details class="grupo"{aberto}><summary><h3>{esc(titulo)}</h3>'
            f"<small>{len(itens)} arquivo{'s' if len(itens) != 1 else ''} · "
            f"{_tamanho(sum(a.bytes_ for a in itens))}</small><small>{esc(desc)}</small>"
            '</summary><div class="tabela"><table><thead><tr><th>Arquivo</th><th>Descrição</th>'
            "<th>Formato</th><th>Tamanho</th><th>Código de verificação (SHA-256)</th></tr>"
            "</thead><tbody>" + "".join(linhas) + "</tbody></table></div></details>")
    if not any(por_grupo.get(g) for g in ("carteira", "livro", "registro")):
        blocos.insert(0, '<p class="aviso">Ainda não há arquivos do fundo publicados nesta '
                         "versão: a carteira, as decisões e o registro diário aparecem aqui a "
                         "partir da data de início do mandato.</p>")
    fontes = "".join(f'<li><a href="{esc(u)}">{esc(n)}</a></li>' for n, u in FONTES_PUBLICAS)
    resultado = esc(texto_integridade(verificacao, n_eventos))
    guia = f"https://github.com/{esc(repo)}/blob/{esc(ref)}/docs/cdp"
    corpo = f"""<main class="wrap">
<section class="hero">
<h1>Dados abertos e auditoria</h1>
<p>Cada número do portal vem de código aberto aplicado a dados públicos. Aqui estão os arquivos
que o sustentam — carteira, decisões, teses, registro diário, modelos de cobertura, relatórios,
mandato e a trilha de auditoria encadeada —, cada um com o seu código de verificação.</p>
<div class="kpis">
<div class="kpi"><span>Versão do repositório</span><b>{esc(ver or "—")}</b></div>
<div class="kpi"><span>Publicado em</span><b>{agora.astimezone(FUSO):%d/%m/%Y %H:%M}</b></div>
<div class="kpi"><span>Arquivos</span><b>{len(arquivos)} · {_tamanho(total)}</b></div>
<div class="kpi"><span>Trilha de auditoria</span><b>{resultado}</b></div>
</div>
</section>
<hr class="regua">
<section class="bloco" aria-labelledby="como">
<h2 id="como">Como conferir</h2>
<p>Qualquer pessoa pode refazer o caminho: obter a mesma versão, conferir cada arquivo e
recalcular os números com o código aberto.</p>
<ol class="passos">
<li><b>Obtenha a mesma versão</b>Os arquivos abaixo vêm da versão {esc(ver or "atual")} do
<a href="https://github.com/{esc(repo)}/tree/{esc(ref)}">repositório público</a>.</li>
<li><b>Confira os códigos de verificação</b>Cada arquivo traz o seu código (SHA-256); a lista
completa está nas <a href="../SHA256SUMS">somas de verificação</a> da publicação.</li>
<li><b>Recalcule com o código</b>A verificação refaz a trilha de auditoria encadeada e os
registros diários a partir dos arquivos.</li>
<li><b>Reproduza com qualquer assistente de IA</b>Passo a passo, com os comandos, no
<a href="{guia}/SITE.md#conferir-uma-publicação">guia de conferência</a>, em
<a href="{guia}/REPRODUZIR.md">Reproduzir</a> e, para operar a sua própria cópia, em
<a href="{guia}/REPLICAR.md">Replicar</a>.</li>
</ol>
</section>
<section class="bloco" aria-labelledby="arquivos">
<h2 id="arquivos">Arquivos</h2>
<p>Para programas e auditores: <a href="datapackage.json">catálogo dos arquivos</a> (padrão
aberto de pacotes de dados), <a href="../manifest.json">manifesto da publicação</a> e
<a href="../SHA256SUMS">somas de verificação</a>.</p>
{"".join(blocos)}
</section>
<section class="bloco" aria-labelledby="fontes">
<h2 id="fontes">Fontes públicas</h2>
<p>Os modelos usam somente fontes públicas; cada insumo traz fonte, data de publicação e data de
coleta. Os arquivos públicos coletados ficam arquivados no repositório
(<a href="https://github.com/{esc(repo)}/tree/{esc(ref)}/data">data/</a>).</p>
<ul class="fontes">{fontes}</ul>
</section>
<p class="aviso">{esc(cfg["aviso_legal"])}</p>
</main>
<footer class="foot"><div class="wrap">
<p>{esc(cfg["titulo_curto"])} · <a href="../">Painel</a> · <a href="https://github.com/{esc(repo)}">Repositório público</a></p>
<p>Publicado em {agora.astimezone(FUSO):%d/%m/%Y %H:%M} (Brasília){" · versão do repositório " + esc(ver) if ver else ""}</p>
</div></footer>"""
    titulo = "Dados abertos e auditoria · " + cfg["titulo_curto"]
    desc = ("Arquivos do fundo para auditoria: carteira, decisões, teses, registro diário, "
            "modelos de cobertura, relatórios e trilha encadeada, com SHA-256.")
    if demo:
        titulo = f"{SIMULATED_DATA_NOTICE} — {titulo}"
        desc = f"{SIMULATED_DATA_NOTICE}: {desc}"
    return _pagina(cfg, titulo=titulo, descricao=desc, canonico=cfg["base_url"] + "/dados/",
                   indexar=indexar, raiz_rel="../", corpo=corpo, demo=demo, tem_og=tem_og)


# ==========================================================================================
# Montagem
# ==========================================================================================


@dataclass
class Opcoes:
    saida: Path
    raiz: Path = Path(".")
    base_url: str | None = None
    agora: datetime | None = None
    commit: str | None = None
    demo: bool = False
    demo_dias: int = 6
    noindex: bool = False
    verificar: bool = True


def _preparar_saida(saida: Path, raiz: Path) -> None:
    saida = saida.resolve()
    proibidas = [raiz.resolve() / d for d in ("book", "data", "reports", "artifacts", "src",
                                              "configs", "docs", ".git")]
    if saida == raiz.resolve() or any(saida == p or p in saida.parents for p in proibidas):
        raise ErroSite(f"saída proibida: {saida} (use uma pasta própria, ex.: _site)")
    if saida.exists():
        if any(saida.iterdir()) and not (saida / "manifest.json").is_file():
            raise ErroSite(f"{saida} não está vazia e não é um site montado antes: escolha outra")
        shutil.rmtree(saida)
    saida.mkdir(parents=True)


def construir(rt: Any, op: Opcoes) -> dict[str, Any]:
    """Monta o site em ``op.saida`` (ver docstring do módulo). Devolve o resumo."""
    from .workflow.painel import page_assets, render_page
    from .workflow.painel_publicacao import dump_publicacao

    raiz = Path(op.raiz)
    cfg = carregar_site(raiz)
    if op.base_url:
        cfg["base_url"] = op.base_url.rstrip("/")
    commit = op.commit or _git(["rev-parse", "HEAD"], raiz) or None
    agora = op.agora or _instante_do_commit(raiz) or datetime.now(UTC)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=FUSO)
    tmp: tempfile.TemporaryDirectory[str] | None = None
    try:
        if op.demo:
            from .config import load_config
            from .workflow.demo import run_demo
            from .workflow.runtime import Runtime

            tmp = tempfile.TemporaryDirectory(prefix="cdp_site_demo_")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                run_demo(Path(tmp.name), days=op.demo_dias)
            rt = Runtime(load_config(), Path(tmp.name) / "book", Path(tmp.name) / "market",
                         Path(tmp.name) / "reports", teses_root=None)
        else:
            from .workflow.reinicio import situacao

            sit = situacao(rt)
            if sit.get("pendente"):
                raise ErroSite("livro aguardando a abertura na data de início do mandato: o "
                               f"portal não é montado antes disso ({sit.get('motivo')})",
                               AGUARDANDO_ABERTURA)
        verificacao: dict[str, Any] = {"resultado": "não verificada", "mensagens": []}
        if op.verificar:
            ok, msgs = rt.verify_all()
            verificacao = {"resultado": "ÍNTEGRO" if ok else "FALHA DE INTEGRIDADE",
                           "mensagens": msgs}
            if not ok and not op.demo:
                raise ErroSite("cdp verify falhou: o portal não publica um livro com a trilha "
                               "quebrada (" + "; ".join(msgs[:3]) + ")")
        saida = Path(op.saida)
        _preparar_saida(saida, raiz)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dados = dados_do_painel(rt, agora)
        meta = dados.get("meta") or {}
        demo = op.demo or bool(meta.get("is_synthetic"))
        indexar = bool(cfg.get("indexar", True)) and not op.noindex and not demo
        # 1) painel: dados, estilo e script versionados, página completa
        _gravar(saida / "data.json", dump_publicacao(dados))
        for nome, texto in page_assets().items():
            _gravar(saida / nome, texto)
        estaticos = raiz / ESTATICOS
        if estaticos.is_dir():
            for p in sorted(estaticos.iterdir()):
                if p.is_file() and not p.name.startswith("."):
                    shutil.copyfile(p, saida / p.name)
        if not (saida / "favicon.svg").exists():
            _gravar(saida / "favicon.svg", FAVICON_SVG)
        for nome in ("marca_tinta.webp", "marca_sol.webp"):
            origem_marca = raiz / "docs" / "cdp" / "marca" / nome
            if origem_marca.is_file():
                (saida / "marca").mkdir(exist_ok=True)
                shutil.copyfile(origem_marca, saida / "marca" / nome)
        tem_og = (saida / "og.png").is_file()
        _gravar(saida / "site.css", CSS_SITE)
        _gravar(saida / "index.html", pagina_inicial(
            render_page(), cfg, indexar=indexar, demo=demo, commit=commit, agora=agora,
            meta=meta, tem_og=tem_og))
        # 2) dados abertos
        pares = coletar_dados(rt, raiz, risco_ultimas=int((cfg.get("downloads") or {})
                                                           .get("risco_ultimas", 20)),
                              desde_o_inicio=not op.demo)
        arquivos: list[Arquivo] = []
        for origem, a in pares:
            if origem.stat().st_size > MAX_ARQUIVO:
                continue  # grande demais para o Pages: fica só no repositório
            destino = saida / a.destino
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origem, destino)
            a.bytes_ = destino.stat().st_size
            a.sha256 = sha256_arquivo(destino)
            arquivos.append(a)
        auditoria = {"versao_do_repositorio": commit, "publicado_em": agora.isoformat(),
                     "verificacao": verificacao, "arquivos": len(arquivos),
                     "dados_simulados": demo}
        texto_aud = json.dumps(auditoria, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        _gravar(saida / "dados/auditoria/verificacao.json", texto_aud)
        arquivos.append(Arquivo("dados/auditoria/verificacao.json", None, "auditoria",
                                "Resultado da verificação de integridade desta publicação",
                                len(texto_aud.encode()), sha256_bytes(texto_aud.encode())))
        arquivos.sort(key=lambda a: a.destino)
        _gravar(saida / "dados/datapackage.json", datapackage(
            cfg, arquivos, saida, commit=commit, agora=agora, demo=demo))
        _gravar(saida / "dados/index.html", pagina_dados(
            cfg, arquivos, commit=commit, agora=agora, demo=demo, indexar=indexar,
            verificacao=verificacao, tem_og=tem_og,
            n_eventos=(dados.get("audit") or {}).get("n_events")))
        # 3) 404, robots, sitemap
        _gravar(saida / "404.html", pagina_404(cfg, demo=demo))
        base = cfg["base_url"]
        regra = "Allow: /" if indexar else "Disallow: /"
        _gravar(saida / "robots.txt", f"User-agent: *\n{regra}\nSitemap: {base}/sitemap.xml\n")
        urls = [f"{base}/", f"{base}/dados/"] + [
            f"{base}/{a.destino}" for a in arquivos if a.destino.endswith("/relatorio.html")]
        lastmod = agora.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        sm = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        sm += [f"  <url><loc>{esc(u)}</loc><lastmod>{lastmod}</lastmod></url>" for u in urls]
        sm.append("</urlset>")
        _gravar(saida / "sitemap.xml", "\n".join(sm) + "\n")
        # 4) manifesto e somas
        from .workflow.painel import page_sha256

        todos = sorted(p for p in saida.rglob("*") if p.is_file())
        mapa = {p.relative_to(saida).as_posix(): {"bytes": p.stat().st_size,
                                                  "sha256": sha256_arquivo(p)} for p in todos}
        manifest = {"site": cfg["titulo_curto"], "versao": 1, "source_commit": commit,
                    "agora": agora.isoformat(), "base_url": base,
                    "perfil": "demo" if op.demo else "site", "dados_simulados": demo,
                    "indexado": indexar, "data_hash": meta.get("data_hash"),
                    "pagina_sha256": page_sha256(), "verificacao": verificacao["resultado"],
                    "arquivos": mapa}
        _gravar(saida / "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        somas = dict(mapa)
        somas["manifest.json"] = {"sha256": sha256_arquivo(saida / "manifest.json")}
        _gravar(saida / "SHA256SUMS", "".join(f"{v['sha256']}  {k}\n"
                                              for k, v in sorted(somas.items())))
        total = sum(p.stat().st_size for p in saida.rglob("*") if p.is_file())
        return {"saida": saida.as_posix(), "arquivos": len(mapa) + 2, "bytes": total,
                "source_commit": commit, "agora": agora.isoformat(), "dados_simulados": demo,
                "indexado": indexar, "verificacao": verificacao["resultado"],
                "downloads": len(arquivos), "data_json_bytes": (saida / "data.json").stat().st_size}
    finally:
        if tmp is not None:
            tmp.cleanup()


def datapackage(cfg: Mapping[str, Any], arquivos: list[Arquivo], saida: Path, *,
                commit: str | None, agora: datetime, demo: bool) -> str:
    usados: set[str] = set()
    recursos = []
    for a in arquivos:
        ext = Path(a.destino).suffix.lower()
        fmt, mt, _ = FORMATOS.get(ext, (ext.lstrip(".") or "bin", "application/octet-stream", ""))
        r: dict[str, Any] = {"name": _nome_recurso(a.destino, usados),
                             "path": a.destino.removeprefix("dados/"), "format": fmt,
                             "mediatype": mt, "bytes": a.bytes_, "hash": f"sha256:{a.sha256}",
                             "description": a.descricao, "grupo": a.grupo}
        if a.origem:
            r["sources"] = [{"title": "Repositório público",
                             "path": f"https://github.com/{cfg['repositorio']}/blob/"
                                     f"{commit or 'main'}/{a.origem}"}]
        if ext == ".csv":
            try:
                esquema = _esquema_csv((saida / a.destino).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                esquema = None
            if esquema:
                r["schema"] = esquema
        recursos.append(r)
    titulo = f"{cfg['titulo_curto']} — dados abertos"
    desc = ("Arquivos do fundo simulado (paper trading com preços reais) para auditoria: "
            "cópias fiéis do livro, dos relatórios e da configuração do repositório público.")
    palavras = ["carteira simulada", "long/short", "América Latina", "dados abertos"]
    if demo:
        titulo = f"{SIMULATED_DATA_NOTICE} — {titulo}"
        desc = f"{SIMULATED_DATA_NOTICE}: demonstração com mercado sintético. {desc}"
        palavras.insert(0, SIMULATED_DATA_NOTICE)
    pkg: dict[str, Any] = {
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
        "name": "cdp-cabra-da-peste", "title": titulo, "description": desc,
        "version": (commit or "")[:12] or None, "created": agora.astimezone(UTC).isoformat(),
        "homepage": cfg["base_url"] + "/", "keywords": palavras,
        "sources": [{"title": "Repositório público",
                     "path": f"https://github.com/{cfg['repositorio']}"
                             + (f"/tree/{commit}" if commit else "")}]
        + [{"title": n, "path": u} for n, u in FONTES_PUBLICAS],
        "resources": recursos,
    }
    lic = cfg.get("licenca") or {}
    if lic.get("conteudo"):
        pkg["licenses"] = [{"name": lic["conteudo"]}]
    return json.dumps({k: v for k, v in pkg.items() if v is not None}, ensure_ascii=False,
                      indent=1, sort_keys=False) + "\n"


# ==========================================================================================
# Conferência
# ==========================================================================================


def _refs_locais(path: Path, saida: Path) -> list[str]:
    texto = path.read_text(encoding="utf-8")
    texto = re.sub(r"<script\b(?![^>]*\bsrc=)[^>]*>.*?</script>", "", texto, flags=re.S | re.I)
    texto = re.sub(r"<pre\b.*?</pre>", "", texto, flags=re.S | re.I)
    faltas = []
    base_path = None
    for ref in _REF_RE.findall(texto):
        ref = html.unescape(ref)
        if re.match(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", ref, re.I):
            continue
        alvo = ref.split("#", 1)[0].split("?", 1)[0]
        if not alvo:
            continue
        if alvo.startswith("/"):
            if base_path is None:
                man = json.loads((saida / "manifest.json").read_text(encoding="utf-8")) \
                    if (saida / "manifest.json").is_file() else {}
                base_path = _base_path(str(man.get("base_url") or ""))
            if not alvo.startswith(base_path):
                faltas.append(ref)
                continue
            destino = saida / alvo[len(base_path):]
        else:
            destino = (path.parent / alvo).resolve()
            if saida.resolve() not in (destino, *destino.parents):
                faltas.append(ref)
                continue
        if destino.is_dir():
            destino = destino / "index.html"
        if not destino.exists():
            faltas.append(ref)
    return faltas


def conferir(saida: Path | str) -> list[str]:
    """Problemas do site montado (lista vazia = pronto para publicar)."""
    saida = Path(saida)
    out: list[str] = []
    obrigatorios = ("index.html", "data.json", "404.html", "robots.txt", "sitemap.xml",
                    "manifest.json", "SHA256SUMS", "favicon.svg", "site.css",
                    "dados/index.html", "dados/datapackage.json")
    for nome in obrigatorios:
        if not (saida / nome).is_file():
            out.append(f"arquivo obrigatório ausente: {nome}")
    essenciais = ("index.html", "manifest.json", "SHA256SUMS", "dados/datapackage.json",
                  "404.html", "dados/index.html")
    if any(not (saida / n).is_file() for n in essenciais):
        return out
    total = 0
    for p in sorted(saida.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(saida).as_posix()
        tam = p.stat().st_size
        total += tam
        if tam > MAX_ARQUIVO:
            out.append(f"arquivo acima de 25 MiB: {rel}")
        if PROIBIDOS.search(rel):
            out.append(f"nome proibido (segredo?): {rel}")
    if total > MAX_SITE:
        out.append(f"site com {total} bytes (acima de 900 MB)")
    man = json.loads((saida / "manifest.json").read_text(encoding="utf-8"))
    listados = man.get("arquivos") or {}
    presentes = {p.relative_to(saida).as_posix() for p in saida.rglob("*") if p.is_file()}
    for rel in sorted(presentes - set(listados) - {"manifest.json", "SHA256SUMS"}):
        out.append(f"arquivo fora do manifesto: {rel}")
    for rel, info in sorted(listados.items()):
        p = saida / rel
        if not p.is_file():
            out.append(f"manifesto cita arquivo ausente: {rel}")
        elif p.stat().st_size != info.get("bytes") or sha256_arquivo(p) != info.get("sha256"):
            out.append(f"arquivo difere do manifesto: {rel}")
    for linha in (saida / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        h, _, rel = linha.partition("  ")
        if not (saida / rel).is_file() or sha256_arquivo(saida / rel) != h:
            out.append(f"SHA256SUMS não confere: {rel}")
    pkg = json.loads((saida / "dados/datapackage.json").read_text(encoding="utf-8"))
    for r in pkg.get("resources") or []:
        p = saida / "dados" / r["path"]
        if ".." in Path(r["path"]).parts or not p.is_file():
            out.append(f"datapackage cita arquivo ausente: {r['path']}")
        elif p.stat().st_size != r.get("bytes") or f"sha256:{sha256_arquivo(p)}" != r.get("hash"):
            out.append(f"datapackage difere do arquivo: {r['path']}")
    for pagina in sorted(saida.rglob("*.html")):
        rel = pagina.relative_to(saida).as_posix()
        if rel.startswith("dados/relatorios/"):
            continue  # relatórios copiados como estão (podem citar caminhos do repositório)
        for ref in _refs_locais(pagina, saida):
            out.append(f"{rel}: link local quebrado: {ref}")
    idx = (saida / "index.html").read_text(encoding="utf-8")
    for agulha in ('<html lang="pt-BR">', 'rel="canonical"', "Content-Security-Policy",
                   'type="application/ld+json"', 'name="viewport"'):
        if agulha not in idx:
            out.append(f"index.html sem {agulha}")
    m = re.search(r'<script type="application/ld\+json">(.*?)</script>', idx, re.S)
    if m:
        try:
            json.loads(m.group(1).replace("<\\/", "</"))
        except ValueError:
            out.append("index.html: dados estruturados (schema.org) inválidos")
    og = re.search(r'property="og:image" content="([^"]+)"', idx)
    if og and not og.group(1).startswith(("https://", "http://")):
        out.append("og:image precisa ser endereço absoluto")
    simulado = bool(man.get("dados_simulados"))
    for nome in ("index.html", "404.html", "dados/index.html"):
        txt = (saida / nome).read_text(encoding="utf-8")
        if simulado and SIMULATED_DATA_NOTICE not in txt:
            out.append(f"{nome}: dados simulados sem o aviso {SIMULATED_DATA_NOTICE}")
        if simulado and "noindex" not in txt:
            out.append(f"{nome}: dados simulados precisam ficar fora dos buscadores (noindex)")
    if not simulado:
        if 'class="site-sim"' in idx:
            out.append("index.html: faixa de dados simulados numa publicação real")
        if "site-aviso" not in idx:
            out.append("index.html sem o aviso legal")
    return out


# ==========================================================================================
# Estáticos de marca (site/): ícones e imagem de compartilhamento — Playwright (grupo dev)
# ==========================================================================================

_OG_HTML = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Alegreya:ital,wght@0,400..800;1,400&family=Cinzel:wght@600..700&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>
html,body{margin:0;width:1200px;height:630px;overflow:hidden}
body{background:#f4efe5;color:#1d1611;font-family:"IBM Plex Sans",sans-serif;position:relative}
.borda{position:absolute;inset:26px;border:2px solid #1d1611}
.borda::after{content:"";position:absolute;inset:6px;border:1px solid #1d1611}
.marca{position:absolute;left:70px;top:92px;width:520px;aspect-ratio:960/596}
.marca i{position:absolute;inset:0;-webkit-mask:var(--m) center/contain no-repeat;mask:var(--m) center/contain no-repeat}
.tinta{background:#1d1611}.sol{background:#b9692f}
.txt{position:absolute;left:650px;right:70px;top:110px}
h1{font:700 54px/1.05 "Cinzel",serif;letter-spacing:.04em;margin:0 0 18px}
p{font:400 27px/1.35 "Alegreya",serif;margin:0 0 14px;color:#4a3e33}
.selo{position:absolute;left:650px;bottom:84px;display:flex;gap:12px;align-items:center;font:600 18px/1 "IBM Plex Sans";letter-spacing:.08em;text-transform:uppercase}
.selo span{border:2px solid #1d1611;padding:9px 14px}
.selo .sol{background:#b9692f;color:#fff;border-color:#b9692f}
.rodape{position:absolute;left:70px;bottom:70px;font:400 20px/1.3 "Alegreya",serif;color:#685a4b}
</style></head><body><div class="borda"></div>
<div class="marca"><i class="tinta" style="--m:url('@@TINTA@@')"></i><i class="sol" style="--m:url('@@SOL@@')"></i></div>
<div class="txt"><h1>Cabra da Peste</h1>
<p>Carteira simulada long/short de ações da América Latina, neutra em mercado, em dólares.</p>
<p>Decisões, risco e modelos abertos, com dados públicos e trilha auditável.</p></div>
<div class="selo"><span>Dados públicos</span><span class="sol">Não é oferta</span></div>
<div class="rodape">Paper trading com preços reais · portal aberto</div>
</body></html>"""

_ICONE_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;width:180px;height:180px;background:#1d1611}
svg{display:block;width:180px;height:180px}</style></head><body>
<svg viewBox="0 0 100 100"><rect width="100" height="100" fill="#1d1611"/>
<path d="@@PATH@@" fill="#e08a45" transform="translate(16 16) scale(.68)"/></svg></body></html>"""


def gerar_estaticos(raiz: Path | str, saida: Path | str | None = None) -> dict[str, Any]:
    """Regera ``site/og.png`` (1200×630), ``site/apple-touch-icon.png`` e ``site/favicon.svg``
    a partir das máscaras da marca (``docs/cdp/marca``). Requer Playwright (grupo dev)."""
    import base64

    from playwright.sync_api import sync_playwright

    raiz = Path(raiz)
    pasta = Path(saida) if saida else raiz / ESTATICOS
    pasta.mkdir(parents=True, exist_ok=True)
    marca = raiz / "docs" / "cdp" / "marca"

    def uri(nome: str) -> str:
        return "data:image/webp;base64," + base64.b64encode((marca / nome).read_bytes()).decode()

    og = (_OG_HTML.replace("@@TINTA@@", uri("marca_tinta.webp"))
          .replace("@@SOL@@", uri("marca_sol.webp")))
    icone = _ICONE_HTML.replace("@@PATH@@", ESTRELA)
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pg = nav.new_page(viewport={"width": 1200, "height": 630})
        pg.set_content(og, wait_until="networkidle")
        pg.screenshot(path=str(pasta / "og.png"))
        pg = nav.new_page(viewport={"width": 180, "height": 180})
        pg.set_content(icone)
        pg.screenshot(path=str(pasta / "apple-touch-icon.png"))
        nav.close()
    (pasta / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    return {"pasta": pasta.as_posix(), "arquivos": ["og.png", "apple-touch-icon.png",
                                                     "favicon.svg"]}


# ==========================================================================================
# CLI
# ==========================================================================================


def _aware(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=FUSO)


def cmd_site(args: argparse.Namespace) -> int:
    if args.action == "conferir":
        problemas = conferir(Path(args.saida))
        print("OK" if not problemas else "FALHOU")
        for p in problemas:
            print(f"- {p}")
        return 0 if not problemas else 1
    if args.action == "estaticos":
        print(json.dumps(gerar_estaticos(Path(args.raiz), args.saida), ensure_ascii=False,
                         indent=2))
        return 0
    from .workflow.runtime import Runtime

    rt = Runtime.from_args(args)
    op = Opcoes(saida=Path(args.saida), raiz=Path(args.raiz), base_url=args.base_url,
                agora=args.agora, commit=args.commit, demo=args.demo, noindex=args.noindex,
                verificar=not args.sem_verificar)
    try:
        out = construir(rt, op)
    except ErroSite as exc:
        print(f"Recusado: {exc}", file=sys.stderr)
        return exc.codigo
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


def registrar(sub: argparse._SubParsersAction) -> None:
    s = sub.add_parser("site", help="portal público (GitHub Pages): montar e conferir")
    ssub = s.add_subparsers(dest="action", required=True)
    c = ssub.add_parser("construir", help="monta o site estático em --saida (só lê o livro)")
    c.add_argument("--saida", default="_site", help="pasta de saída (padrão: _site)")
    c.add_argument("--raiz", default=".", help="raiz do repositório (configuração e estáticos)")
    c.add_argument("--base-url", default=None, help="URL pública (padrão: configs/cdp/site.yaml)")
    c.add_argument("--agora", type=_aware, default=None,
                   help="instante da publicação (padrão: o do commit HEAD)")
    c.add_argument("--commit", default=None, help="versão do repositório (padrão: HEAD)")
    c.add_argument("--demo", action="store_true",
                   help="demonstração offline (DADOS SIMULADOS, fora dos buscadores)")
    c.add_argument("--noindex", action="store_true", help="fora dos buscadores")
    c.add_argument("--sem-verificar", action="store_true", help="não roda cdp verify")
    c.set_defaults(func=cmd_site)
    c = ssub.add_parser("conferir", help="confere o site montado (links, manifesto, avisos)")
    c.add_argument("--saida", default="_site")
    c.set_defaults(func=cmd_site)
    c = ssub.add_parser("estaticos", help="regera ícones e imagem de compartilhamento (site/; "
                                          "requer Playwright)")
    c.add_argument("--raiz", default=".")
    c.add_argument("--saida", default=None)
    c.set_defaults(func=cmd_site)


__all__ = ["ErroSite", "Opcoes", "carregar_site", "coletar_dados", "conferir", "construir",
           "dados_do_painel", "gerar_estaticos", "limites_site", "registrar"]
