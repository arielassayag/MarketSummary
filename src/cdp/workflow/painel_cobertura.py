"""Aba "Cobertura de ativos" do portal: os arquivos de dados publicados e o módulo da página.

A aba mostra a cobertura de ações e ETFs (modelos abertos de valuation e preços-alvo de 12
meses) produzida pela workstream A (:mod:`cdp.cobertura`). Este módulo lê o livro da cobertura
(``book/cobertura/``: snapshots conferidos contra o manifesto, livro encadeado e placar), a base
de mercado (fechamentos) e, se houver, a carteira vigente, e grava ao lado de ``index.html``:

- ``cobertura.json`` (``cdp-cobertura/1``): resumo, tabela do universo (uma linha por
  instrumento, nunca omitida), painel do universo (distribuição do potencial, CDP × consenso,
  mistura de ratings), ETFs, histórico de acertos, revisões recentes e metodologia;
- ``cobertura-precos.json``: fechamentos mais recentes e o potencial a esses preços;
- ``cobertura-hist-<k>.json``: histórico semanal de preço, preço-alvo, consenso e rating de
  cada instrumento (últimas 52 semanas e, antes delas, um ponto por fim de mês);
- ``cobertura-modelo-<k>.json``: o modelo aberto de cada instrumento — memória de cálculo
  completa (cada passo com fórmula, substituição, resultado e fontes), insumos com fonte e data
  de publicação, lacunas, grade de sensibilidade, cenários, ponte do preço-alvo e portões de
  qualidade.

Regras (as mesmas do ``data.json``, :mod:`cdp.workflow.painel_publicacao`):

- a página nunca calcula: todo número exibido chega formatado daqui (campos ``*_texto``) e a
  geometria dos gráficos chega pronta, em coordenadas de 0 a 100 (``x`` da esquerda, ``y`` do
  topo) — o módulo só posiciona elementos;
- cada arquivo tem no máximo :data:`MAX_BYTES` bytes e nenhuma linha acima de
  :data:`MAX_LINHA` caracteres; o leiaute e as formas sem perda (``_colunas``, ``_rep``,
  ``_partes``) são os de :func:`~cdp.workflow.painel_publicacao.dump_publicacao`;
- byte a byte estáveis (sem data de geração): os mesmos insumos produzem os mesmos arquivos;
- ausente continua ``null`` (nunca zero); preço-alvo e retornos de instrumento sem rating
  citável ("Em revisão", "Sem preço-alvo") não são publicados como citáveis;
- sem vocabulário de TI fora de ``meta`` (as chaves de hash saem com
  :func:`~cdp.workflow.painel_publicacao._sem_ti`).

Se ``cobertura.json`` não couber, :data:`NIVEIS` aplica cortes progressivos que nunca removem
linhas do universo, ratings, preços-alvo, potenciais, faixas de cenário nem o resumo do placar;
o nível usado fica em ``meta.publication.nivel`` e os cortes em ``meta.truncations``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .. import SIMULATED_DATA_NOTICE
from ..cobertura.formato import NA, mult, pct, pp, preco
from .painel_publicacao import (
    DATA_MAX_BYTES,
    DATA_MAX_LINE,
    _Cortes,
    _pack,
    _sem_ti,
    _split,
    cabe,
    dump_publicacao,
    expandir,
    max_line,
)

SCHEMA = "cdp-cobertura/1"
SCHEMA_PRECOS = "cdp-cobertura-precos/1"
SCHEMA_HISTORICO = "cdp-cobertura-historico/1"
SCHEMA_MODELO = "cdp-cobertura-modelo/1"
ARQUIVO = "cobertura.json"
ARQUIVO_PRECOS = "cobertura-precos.json"
PREFIXO_HISTORICO = "cobertura-hist-"
PREFIXO_MODELO = "cobertura-modelo-"
#: Todos os arquivos de dados da aba (os fragmentos numerados mudam de quantidade com o universo).
ARQUIVO_RE = re.compile(r"cobertura(?:-precos|-hist-\d+|-modelo-\d+)?\.json")
#: Registro local da última publicação dos arquivos da aba (nome → SHA-256); nunca publicado.
MARCADOR = "COBERTURA_PUBLICADA.json"
#: Fonte do módulo da página (carregado sob demanda pela casca; nunca dentro do script principal).
MODULO = Path(__file__).with_name("painel_cobertura.js")
#: Id do elemento ``<script type="application/json">`` da cópia local (dados embutidos).
ELEMENTO_LOCAL = "cdp-cobertura-dados"
MAX_BYTES = DATA_MAX_BYTES
MAX_LINHA = DATA_MAX_LINE
#: Orçamento de cada fragmento (folga para o cabeçalho ``meta``).
ALVO_FRAGMENTO = 240_000
SEMANAS_SEMANAIS = 52
#: Revisão do preço-alvo marcada no gráfico de preço (as demais aparecem só no degrau e na tabela).
REVISAO_MARCADA = 0.05
#: Janela das "Revisões recentes" (dias antes da data do retrato).
JANELA_REVISOES_DIAS = 28
SEMANAS_JANELA = 104
N_MIN_PLACAR_SEMANAS = 13
N_MIN_GRAFICO_SEMANAS = 4
REPOSITORIO = "arielassayag/MarketSummary"
AVISO_CVM = ("Modelos quantitativos internos da gestão; não constituem relatório de análise nos "
             "termos da Resolução CVM 20/2021.")
AVISO_REAL = "Dados públicos (CVM, SEC EDGAR, Yahoo Finance, Banco Central do Brasil, FRED, Damodaran)."

RATINGS = ("Compra", "Neutro", "Venda", "Em revisão", "Sem preço-alvo")
RATINGS_CITAVEIS = ("Compra", "Neutro", "Venda")
TOM_RATING = {"Compra": "compra", "Neutro": "neutro", "Venda": "venda", "Em revisão": "revisao",
              "Sem preço-alvo": "sem", "Positiva": "compra", "Neutra": "neutro",
              "Negativa": "venda", "Referência": "ref"}
VISOES_ETF = ("Positiva", "Neutra", "Negativa", "Em revisão", "Referência")
ORDEM_INCERTEZA = {"Baixa": 1, "Média": 2, "Alta": 3, "Muito alta": 4}
PAISES = {"AR": "Argentina", "BR": "Brasil", "CL": "Chile", "CO": "Colômbia", "MX": "México",
          "PE": "Peru", "UY": "Uruguai", "PA": "Panamá", "US": "Estados Unidos",
          "LATAM": "Regional", "LA": "Regional"}
SETORES = {"Financials": "Financeiro", "Energy": "Energia", "Materials": "Materiais",
           "Utilities": "Utilidades públicas", "Industrials": "Industriais",
           "Consumer Discretionary": "Consumo discricionário", "Consumer Staples": "Consumo básico",
           "Health Care": "Saúde", "Real Estate": "Imobiliário",
           "Communication Services": "Comunicações", "Information Technology": "Tecnologia",
           "OTHER": "Outros"}
ARQUETIPOS = {"banco": "Bancos", "seguradora": "Seguradoras",
              "utilidade_regulada": "Utilidades reguladas", "concessao": "Concessões",
              "commodity": "Commodities", "corporativo": "Empresas não financeiras",
              "imobiliario": "Imobiliário", "holding": "Holdings"}
FONTES = {"CVM": "CVM (dados abertos)", "SEC": "SEC EDGAR", "YAHOO": "Yahoo Finance",
          "BCB": "Banco Central do Brasil", "FRED": "FRED (Federal Reserve de St. Louis)",
          "B3": "B3", "ISHARES": "iShares (BlackRock)", "GLOBALX": "Global X",
          "DAMODARAN": "Damodaran (NYU Stern)", "RI": "Relações com investidores da companhia",
          "SIMULADO": "Simulado", "CODIGO": "Cálculo da gestão",
          "CONFIG": "Parâmetro da gestão"}
TIPOS_EVENTO = {"INICIACAO": "Iniciação", "REITERACAO": "Reiteração", "REVISAO": "Revisão do alvo",
                "MUDANCA_RATING": "Mudança de rating", "SUSPENSAO": "Suspensão do alvo",
                "RETOMADA": "Retomada do alvo", "ENCERRAMENTO": "Encerramento"}
MOTIVOS_PONTE = {"ROLAGEM": "rolagem do horizonte", "RESULTADO": "resultados e estimativas",
                 "JUROS_MACRO": "juros e parâmetros", "ESTRUTURA_CAPITAL": "estrutura de capital",
                 "CAMBIO": "câmbio", "PRECO": "preço e risco de mercado",
                 "MUDANCA_METODO": "composição dos métodos", "CORRECAO_MODELO": "resíduo da decomposição"}
COMPONENTES_PONTE = (("rolagem", "Rolagem do horizonte"), ("estimativas", "Resultados e estimativas"),
                     ("parametros", "Juros e parâmetros"), ("estrutura_capital", "Estrutura de capital"),
                     ("cambio", "Câmbio"), ("preco", "Preço e risco de mercado"),
                     ("metodos", "Composição dos métodos"), ("residuo", "Resíduo"))
STATUS_PORTAO = {"ok": ("Conferido", "ok"), "aviso": ("Aviso", "warn"),
                 "bloqueio": ("Bloqueio", "crit"), "informativo": ("Informativo", "info"),
                 "nao_aplicavel": ("Não se aplica", "na"), "sem_alvo": ("Sem preço-alvo", "na")}
#: Visões de ETF com preço-alvo citável (o equivalente a Compra, Neutro e Venda das ações; o
#: ETF de referência, o ILF, também tem preço-alvo).
VISOES_CITAVEIS = ("Positiva", "Neutra", "Negativa", "Referência")
#: Folga à direita do gráfico de preço dos instrumentos sem leque: espaço para os fechamentos
#: posteriores ao retrato (desenhados a partir de ``cobertura-precos.json``).
FOLGA_POS_RETRATO_DIAS = 28
#: Colunas da projeção explícita de cada método, na ordem da conta (as demais vêm depois).
COLUNAS_PROJECAO = (("receita", "Receita"), ("crescimento", "Crescimento"),
                    ("nopat", "Lucro operacional após impostos"), ("reinvestimento", "Reinvestimento"),
                    ("fcff", "Fluxo de caixa livre"), ("b_inicio", "Patrimônio no início"), ("roe", "ROE"),
                    ("lucro", "Lucro"), ("lpa", "LPA"), ("dividendos", "Dividendos"),
                    ("patrimonio", "Patrimônio"), ("lucro_residual", "Lucro residual"),
                    ("fator_desconto", "Fator de desconto"), ("vp", "Valor presente"))
CUSTO_CAPITAL = (("rf", "Taxa livre de risco (Tesouro americano de 10 anos)", "%"),
                 ("erp", "Prêmio de risco de mercado (ERP)", "%"),
                 ("crp", "Prêmio de risco do país (CRP)", "%"), ("lam", "Exposição ao risco do país (λ)", "n"),
                 ("beta", "β ajustado", "n"), ("ke_usd", "ke em dólar", "%"),
                 ("pi_local", "Inflação esperada local", "%"), ("pi_us", "Inflação esperada nos EUA", "%"),
                 ("delta_calibracao", "Calibração de nível do país (δ do país)", "p.p."),
                 ("ke", "ke na moeda local", "%"),
                 ("ke_sem_calibracao", "ke na moeda local sem a calibração (sensibilidade)", "%"),
                 ("kd", "Custo da dívida (kd)", "%"),
                 ("imposto", "Alíquota de imposto", "%"), ("peso_divida", "Peso da dívida", "%"),
                 ("wacc", "WACC", "%"), ("g", "Crescimento na perpetuidade (g)", "%"))


# ==========================================================================================
# Entradas
# ==========================================================================================


@dataclass
class Entrada:
    """Tudo o que a aba publica, já lido e conferido (função pura a partir daqui).

    ``linhas``: uma por emissor (a do snapshot mais recente que o cobriu, mascarada);
    ``modelos``: modelo aberto de cada emissor (``iid`` → JSON do snapshot);
    ``etfs``: modelo de cada ETF; ``eventos``: livro encadeado até ``as_of``; ``placar``: o do
    último snapshot; ``fechamentos``: ``{ticker: [(data ISO, fechamento), ...]}`` diários em
    ordem crescente (moeda da linha); ``ultimo_preco``: ``{iid: (data ISO, fechamento)}`` mais
    recente (pode ser posterior ao snapshot); ``adtv_usd``: liquidez média diária em dólar;
    ``carteira``: ``{iid: peso}`` da carteira vigente (``None`` = sem carteira);
    ``configuracao``: ``valuation.yaml`` arquivado no snapshot; ``precos_ate``: data dos preços
    usados no retrato (os fragmentos de histórico e de modelo param nela e por isso não mudam com
    os fechamentos posteriores); ``versao_codigo``: versão do código que produziu o retrato
    (registrada no manifesto); ``versao``: versão do repositório desta publicação (os endereços
    do repositório apontam para ela; sem ela, para o ramo principal)."""

    as_of: date
    is_synthetic: bool
    linhas: list[dict[str, Any]]
    modelos: dict[str, dict[str, Any]]
    etfs: dict[str, dict[str, Any]]
    eventos: list[dict[str, Any]]
    placar: dict[str, Any]
    snapshots: list[str] = field(default_factory=list)
    fechamentos: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    ultimo_preco: dict[str, tuple[str, float]] = field(default_factory=dict)
    adtv_usd: dict[str, float] = field(default_factory=dict)
    carteira: dict[str, float] | None = None
    configuracao: dict[str, Any] = field(default_factory=dict)
    repositorio: str = REPOSITORIO
    page_sha256: str | None = None
    precos_ate: str | None = None
    versao_codigo: str | None = None
    versao: str | None = None


_VERSAO_RE = re.compile(r"[0-9a-f]{7,40}")


def _ref(v: Any) -> str | None:
    """Versão do repositório utilizável num endereço (só hexadecimal de 7 a 40 dígitos)."""
    s = str(v or "").strip().lower()
    return s if _VERSAO_RE.fullmatch(s) else None


def _corte(ent: Entrada) -> str:
    """Último dia dos fechamentos dentro dos fragmentos (a data dos preços do retrato)."""
    a = ent.as_of.isoformat()
    p = str(ent.precos_ate or "")[:10]
    return p if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p) and p <= a else a


def _num(x: Any) -> float | None:
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def carregar(book: Path | str, *, ate: date | None = None, md: Any = None,
             carteira: Mapping[str, float] | None = None, repositorio: str = REPOSITORIO,
             page_sha256: str | None = None, versao: str | None = None) -> Entrada | None:
    """Lê o livro da cobertura (``<book>/cobertura``) até ``ate`` (padrão: o último snapshot).

    ``md`` (``MarketData`` opcional): fechamentos para o histórico de preços, o preço mais
    recente e a liquidez; sem ele, os preços são os registrados nos snapshots. ``carteira``:
    pesos da carteira vigente (``None`` = o fundo ainda não tem carteira). ``versao``: versão do
    repositório desta publicação (endereços fixos do código e dos dados abertos). Devolve
    ``None`` se não houver snapshot; um livro que não confere levanta
    :class:`~cdp.cobertura.livro.LivroErro` (quem publica mostra ``exportar(None,
    estado="em_verificacao")``)."""
    import yaml

    from ..cobertura import livro as L

    book = Path(book)
    datas = L.datas_snapshots(book)
    if ate is not None:
        datas = [d for d in datas if d <= ate]
    if not datas:
        return None
    snap = L.ultimo_snapshot(book, datas[-1])
    if snap is None:
        return None
    estado = snap.estado(mascarar=True)
    snaps = {snap.as_of.isoformat(): snap}
    linhas: list[dict[str, Any]] = []
    modelos: dict[str, dict[str, Any]] = {}
    for iid, row in estado.iterrows():
        d = str(row.get("snapshot") or snap.as_of.isoformat())
        if d not in snaps:
            snaps[d] = L.snapshot(book, date.fromisoformat(d))
        m = snaps[d].modelo(str(iid))
        if m is None:
            continue
        r = {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
             for k, v in row.to_dict().items()}
        r["issuer_id"] = str(iid)
        linhas.append(r)
        modelos[str(iid)] = m
    etfs: dict[str, dict[str, Any]] = {}
    tab_etf = snap.etfs()
    for k in sorted(str(i) for i in tab_etf.index):
        e = snap.etf(k)
        if e is not None:
            etfs[k] = e
    evs = [e for e in L.eventos(book) if date.fromisoformat(e["as_of"]) <= snap.as_of]
    cfg_bytes = snap._bytes("configuracao/valuation.yaml")
    configuracao = yaml.safe_load(cfg_bytes.decode("utf-8")) if cfg_bytes else {}
    man = snap.manifest or {}
    ent = Entrada(as_of=snap.as_of, is_synthetic=bool(snap.is_synthetic), linhas=linhas,
                  modelos=modelos, etfs=etfs, eventos=evs, placar=snap.placar(),
                  snapshots=[d.isoformat() for d in datas], carteira=dict(carteira) if carteira else None,
                  configuracao=configuracao or {}, repositorio=repositorio, page_sha256=page_sha256,
                  precos_ate=str(man.get("prices_as_of") or "") or None,
                  versao_codigo=_ref((man.get("codigo") or {}).get("git")), versao=_ref(versao))
    if md is not None:
        _mercado(ent, md)
    return ent


def _mercado(ent: Entrada, md: Any) -> None:
    """Fechamentos (janela do histórico), preço mais recente e liquidez a partir da base."""
    import pandas as pd

    ini = pd.Timestamp(ent.as_of - timedelta(weeks=SEMANAS_JANELA + 2))
    linhas = {str(m.get("issuer_id")): str(m.get("linha")) for m in ent.modelos.values()}
    linhas.update({k: str(e.get("ticker")) for k, e in ent.etfs.items()})
    for iid, t in sorted(linhas.items()):
        frame = md.close if t in md.close.columns else (md.benchmarks if t in md.benchmarks.columns else None)
        if frame is None:
            continue
        s = frame[t].loc[ini:].dropna()
        s = s[s > 0]
        if s.empty:
            continue
        ent.fechamentos[t] = [(ix.date().isoformat(), float(v)) for ix, v in s.items()]
        ent.ultimo_preco[iid] = (s.index[-1].date().isoformat(), float(s.iloc[-1]))
        if frame is md.close and t in md.volume.columns:
            vol = md.volume[t].loc[ini:].reindex(s.index)
            ccy = str((ent.modelos.get(iid) or {}).get("moeda") or "USD")
            fx = md.fx[ccy].reindex(s.index).ffill() if ccy in md.fx.columns else None
            if fx is not None:
                adtv = (vol * s * fx).dropna().tail(20)
                if len(adtv):
                    ent.adtv_usd[iid] = float(adtv.median())


def carteira_do_painel(painel: Mapping[str, Any] | None) -> dict[str, float] | None:
    """Pesos da carteira vigente a partir do retrato do painel (dia mais recente ou proposta da
    semana vigente); ``None`` se o fundo ainda não tem carteira."""
    if not painel:
        return None
    painel = expandir(dict(painel))
    pos = ((painel.get("latest_day") or {}).get("positions")) or []
    if not pos:
        live = str((painel.get("risk") or {}).get("live_week"))
        for w in painel.get("weeks") or []:
            if str(w.get("week")) == live:
                pos = ((w.get("proposal") or {}).get("positions")) or []
    out = {str(p.get("issuer_id")): float(p.get("weight") or 0.0) for p in pos if p.get("issuer_id")}
    return out or None


# ==========================================================================================
# Formatação e geometria (a página só posiciona)
# ==========================================================================================


def _data(iso: Any) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else NA


MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _mes(iso: str) -> str:
    return f"{MESES[int(iso[5:7]) - 1]}/{iso[2:4]}"


def _c(v: float) -> float:
    """Coordenada de 0 a 100 com duas casas (byte a byte estável)."""
    return round(min(100.0, max(0.0, float(v))) + 0.0, 2)


def _ticks(lo: float, hi: float, n: int = 4) -> tuple[float, float, list[float]]:
    """Escala "redonda" (mesma regra dos gráficos do portal): passo 1, 2, 5 ou 10 × 10^k."""
    if not hi > lo:
        pad = abs(lo) * 0.01 or 0.01
        lo, hi = lo - pad, hi + pad
    raw = (hi - lo) / max(1, n)
    mag = 10 ** math.floor(math.log10(raw))
    e = raw / mag
    step = mag * (10 if e >= 7.5 else 5 if e >= 3.5 else 2 if e >= 1.5 else 1)
    a, b = math.floor(lo / step) * step, math.ceil(hi / step) * step
    ticks, v = [], a
    while v <= b + step * 1e-6 and len(ticks) < 30:
        ticks.append(0.0 if abs(v) < step * 1e-9 else round(v, 10))
        v += step
    return a, b, ticks


def _rotulos(ticks: Sequence[float], maximo: int = 6) -> list[float]:
    """Ticks rotulados: todos ou, quando há muitos, um a cada dois com passo constante e o zero
    entre eles (as linhas de grade continuam todas)."""
    if len(ticks) <= maximo:
        return list(ticks)
    passo = abs(ticks[1] - ticks[0]) if len(ticks) > 1 else 1.0
    if ticks[0] <= 0.0 <= ticks[-1] and passo > 0:
        return [t for t in ticks if round(t / passo) % 2 == 0]
    return [t for i, t in enumerate(ticks) if i % 2 == 0]


def _preco_eixo(t: float, moeda: str, ticks: Sequence[float]) -> str:
    passo = abs(ticks[1] - ticks[0]) if len(ticks) > 1 else 1.0
    return preco(t, moeda, 0 if passo >= 1 else 2)


_ISO_RE = re.compile(r"(^|[^\w/.-])(\d{4})-(\d{2})-(\d{2})(?![\w/-])")


_ARQ_RE = re.compile(r"\(\s*([\w-]+)\.(?:json|csv)(?:\.gz)?(?:\s*,\s*[\w.]+)*\s*\)")
_ARQ_SOLTO_RE = re.compile(r"\b([\w-]+)\.(?:json|csv)(?:\.gz)?\b")
_ARQ_PT = {"contexto": "contexto transversal do retrato", "modelos": "resumo dos modelos do retrato",
           "manifest": "manifesto do retrato", "placar": "placar do retrato"}


def _datas_br(t: Any) -> Any:
    """Texto de exibição: datas ISO soltas → dd/mm/aaaa (fora de endereços e identificadores) e
    referências a arquivos internos do retrato ("contexto.json") em palavras."""
    if not isinstance(t, str):
        return t
    if ".json" in t or ".csv" in t:
        t = _ARQ_RE.sub(lambda m: f"({_ARQ_PT.get(m.group(1), 'registro do retrato')})", t)
        t = _ARQ_SOLTO_RE.sub(lambda m: _ARQ_PT.get(m.group(1), "registro do retrato"), t)
    if "-" not in t:
        return t
    return _ISO_RE.sub(lambda m: f"{m.group(1)}{m.group(4)}/{m.group(3)}/{m.group(2)}", t)


# Texto de exibição em português institucional: o motor da cobertura registra alguns códigos
# internos nas memórias de cálculo (tipo de linha, símbolo do provedor de cotações, chave do
# setor, identificador do emissor, situação do portão). Eles são traduzidos aqui, só na
# publicação; o modelo arquivado no livro continua como foi gravado.
_TIPO_LINHA = {"LOCAL": "ação local", "ADR": "ADR", "US_LISTED": "listada nos EUA"}
_TIPO_LINHA_RE = re.compile(r"\((LOCAL|ADR|US_LISTED)\b")
_SIMBOLO_RE = re.compile(r"\b([A-Z0-9]{1,12})\.(?:SA|MX|SN|BA|CL|LM)\b")
_IID_RE = re.compile(r"\b(?:AR|BR|CL|CO|MX|PE|LA|PA|UY|US|ETF)_[A-Z0-9]+(?:_[A-Z0-9]+)*\b")
_PAIS_COD = "AR|BR|CL|CO|MX|PE|PA|UY|LATAM"
_PAIS_PAR_RE = re.compile(rf"\(({_PAIS_COD})\)")
_PAIS_X_RE = re.compile(rf"\b({_PAIS_COD}) ×")
_SETOR_CHAVES = "|".join(re.escape(k) for k in sorted((k for k in SETORES if k != "OTHER"), key=len, reverse=True))
_SETOR_RE = re.compile(rf"(\bde |\bdo setor |pares: |setor: |\(|× )({_SETOR_CHAVES})\b(?!\s*\((?!América))")
_SETOR_X_RE = re.compile(rf"(?:^|(?<=; ))({_SETOR_CHAVES})(?= ×| \(América|:)|\b({_SETOR_CHAVES})(?= ×| \(America)")
_ARQ_X_RE = re.compile(r"× (" + "|".join(sorted(ARQUETIPOS, key=len, reverse=True)) + r")\b")
_CONTAS = {"aplicacoes_cp": "aplicações de curto prazo", "caixa": "caixa", "arrendamentos": "arrendamentos",
           "divida_bruta": "dívida bruta", "capex": "investimento em imobilizado",
           "d_a": "depreciação e amortização", "carteira_credito": "carteira de crédito", "receita": "receita",
           "lucro_liquido": "lucro líquido", "patrimonio": "patrimônio líquido", "ebit": "lucro operacional",
           "cfo": "caixa operacional", "dividendos": "dividendos", "acoes": "ações em circulação"}
_CONTA_RE = re.compile(r"(?<![\w/.])([a-z]+(?:_[a-z]+)*) ([AQ]) (?=salto|\d)")
_CIENTIFICO_RE = re.compile(r"(?<![\w.,])(\d+(?:\.\d+)?)e([+-]\d+)\b")
_DECIMAL_RE = re.compile(r"(?<![\w.,/-])(\d+)\.(\d{1,2}|\d{4,})(?![\d.])|(?<![\w.,/-])(0)\.(\d+)(?![\d.])")
_STATUS_RE = re.compile(r"\bstatus: ([a-z_]+)")
_STATUS_PT = {"ok": "conferido", "fx_corrigido": "câmbio corrigido na conversão",
              "cambio_indisponivel": "câmbio indisponível"}
_PALAVRAS = (
    (re.compile(r"\s*\(upside\)"), ""),
    (re.compile(r"\bUpside\b"), "Potencial"),
    (re.compile(r"\bupside\b"), "potencial"),
    (re.compile(r"\bETR\b"), "retorno esperado"),
    (re.compile(r"\binsumos point-in-time\b"), "insumos disponíveis na data"),
    (re.compile(r"\bnão point-in-time\b"), "sem histórico datado"),
    (re.compile(r"\bpoint-in-time\b"), "disponível na data"),
    (re.compile(r"\bTP(?= [×÷=(])"), "preço-alvo"),
    (re.compile(r"\bnao_aplicavel\b"), "não se aplica"),
    (re.compile(r"\bsem_alvo\b"), "sem preço-alvo"),
    (re.compile(r"\bunidade ok\(herdada\)"), "unidade conferida, herdada do período anterior"),
    (re.compile(r"\bunidade ok\b"), "unidade conferida"),
    (re.compile(r"\bnan\b"), NA),
    (re.compile(r"\bvs\.?(?= )"), "contra"),
    (re.compile(r"α_rel_estilo\b"), "α relativo sem estilo"),
    (re.compile(r"α_rel\b"), "α relativo"),
    (re.compile(r"\bde calibração A2b?\b"), "de calibração"),
    (re.compile(r"\bBottom-up\b"), "Pelas posições"),
    (re.compile(r"\bbottom-up\b"), "pelas posições"),
    (re.compile(r"\bTop-down\b"), "Pelo índice"),
    (re.compile(r"\btop-down\b"), "pelo índice"),
    (re.compile(r"\bsnapshots\b"), "retratos"),
    (re.compile(r"\bsnapshot\b"), "retrato"),
)


def _numero_br(m: re.Match[str]) -> str:
    from ..cobertura.formato import num

    v = float(f"{m.group(1)}e{m.group(2)}")
    return num(v, 0) if abs(v) >= 1000 else num(v, 2)


def _pt(t: Any, nomes: Mapping[str, str] | None = None) -> Any:
    """Texto de exibição: datas e arquivos internos em palavras (:func:`_datas_br`), tipo de
    linha, ticker da casa no lugar do símbolo do provedor de cotações, setor, país e arquétipo
    pelos nomes do portal, emissores pelo nome, situação dos portões e números em português.
    Nunca aplicado a endereços nem a identificadores."""
    if not isinstance(t, str) or not t:
        return t
    t = _datas_br(t)
    t = _TIPO_LINHA_RE.sub(lambda m: "(" + _TIPO_LINHA[m.group(1)], t)
    if "." in t:
        t = _SIMBOLO_RE.sub(r"\1", t)
    for rx, novo in _PALAVRAS:
        t = rx.sub(novo, t)
    t = _STATUS_RE.sub(lambda m: _STATUS_PT.get(m.group(1), m.group(1).replace("_", " ")), t)
    t = _CONTA_RE.sub(lambda m: f"{_CONTAS.get(m.group(1), m.group(1).replace('_', ' '))} "
                                f"({'anual' if m.group(2) == 'A' else 'trimestral'}) ", t)
    t = _CIENTIFICO_RE.sub(_numero_br, t)
    t = _DECIMAL_RE.sub(lambda m: f"{m.group(1) or m.group(3)},{m.group(2) or m.group(4)}", t)
    t = _SETOR_RE.sub(lambda m: m.group(1) + SETORES[m.group(2)], t)
    t = _SETOR_X_RE.sub(lambda m: SETORES[m.group(1) or m.group(2)], t)
    t = _ARQ_X_RE.sub(lambda m: "× " + ARQUETIPOS[m.group(1)].lower(), t)
    t = _PAIS_PAR_RE.sub(lambda m: f"({PAISES.get(m.group(1), m.group(1))})", t)
    t = _PAIS_X_RE.sub(lambda m: f"{PAISES.get(m.group(1), m.group(1))} ×", t)
    if nomes is not None and "_" in t:
        t = _IID_RE.sub(lambda m: nomes.get(m.group(0), m.group(0)), t)
    return t


def _nome_posicao(bruto: Any) -> str:
    """Nome de uma posição do arquivo de composição do ETF, sem o sufixo do recibo de ações
    ("-Sponsored ADR") e com maiúsculas de nome próprio (siglas curtas preservadas)."""
    s = re.sub(r"\s*-?\s*(?:SPONSORED|SPON|UNSPONSORED|UNSP)?\s*-?\s*ADRS?\b.*$", "", str(bruto or "").strip(),
               flags=re.I).strip(" -")
    if not s:
        return NA
    if any(c.islower() for c in s):
        return s
    fixos = {"SA": "S.A.", "S.A.": "S.A.", "SAB": "S.A.B.", "CV": "C.V.", "DE": "de", "DEL": "del", "Y": "y",
             "INC": "Inc.", "CORP": "Corp.", "LTD": "Ltd.", "PLC": "plc", "CO": "Co.", "NV": "N.V."}
    return " ".join(fixos.get(w) or (w if len(w) <= 3 else w[:1] + w[1:].lower()) for w in s.split())


class _Escala:
    def __init__(self, lo: float, hi: float, invertida: bool = False) -> None:
        self.lo, self.hi, self.inv = lo, hi, invertida

    def __call__(self, v: float) -> float:
        f = (v - self.lo) / (self.hi - self.lo) * 100.0 if self.hi > self.lo else 50.0
        return _c(100.0 - f if self.inv else f)


def _caminho(pts: Sequence[tuple[float, float] | None]) -> str:
    """``M x y L x y …``; ``None`` interrompe a linha."""
    out, pen = [], False
    for p in pts:
        if p is None:
            pen = False
            continue
        out.append(f"{'L' if pen else 'M'}{_n(p[0])} {_n(p[1])}")
        pen = True
    return "".join(out)


def _n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _tom_valor(v: float | None) -> str:
    return "na" if v is None else ("pos" if v > 0 else "neg" if v < 0 else "zero")


def _faixa(v: float | None, limites: Sequence[float] = (0.05, 0.15, 0.30)) -> int:
    """Intensidade divergente (−3…+3) para o mapa de sensibilidade (cor, nunca número)."""
    if v is None:
        return 0
    k = sum(1 for lim in limites if abs(v) >= lim)
    return k if v > 0 else -k


def _ticker(t: Any) -> str:
    return re.sub(r"\.(SA|MX|SN|BA|CL|LM)$", "", str(t or ""), flags=re.I)


def _rating_ev(e: Mapping[str, Any]) -> str:
    return str(e.get("rating") or "")


# ==========================================================================================
# Universo, painel e resumo
# ==========================================================================================


def _eventos_por_iid(ent: Entrada) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for e in ent.eventos:
        out.setdefault(str(e.get("issuer_id")), []).append(e)
    for v in out.values():
        v.sort(key=lambda e: (e["as_of"], e["seq"]))
    return out


def _rating_desde(evs: Sequence[Mapping[str, Any]], rating: str) -> str | None:
    desde = None
    for e in evs:
        if _rating_ev(e) != rating:
            desde = None
        elif desde is None:
            desde = e["as_of"]
    return desde


def _linha_acao(ent: Entrada, r: Mapping[str, Any], evs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    iid = str(r["issuer_id"])
    m = ent.modelos.get(iid) or {}
    res = m.get("resumo") or {}
    tx = res.get("texto") or {}
    moeda = str(r.get("moeda") or m.get("moeda") or "")
    rating = str(r.get("rating") or res.get("rating") or "Sem preço-alvo")
    citavel = rating in RATINGS_CITAVEIS and _num(r.get("preco_alvo")) is not None
    cons = res.get("consenso") or {}
    cons_ok = bool(cons.get("plausivel")) and _num(cons.get("alvo_medio")) is not None
    vs = _num(r.get("diff_consenso")) if citavel else None
    inc = r.get("incerteza") or res.get("incerteza")
    peso = (ent.carteira or {}).get(iid)
    alvo = _num(r.get("preco_alvo")) if citavel else None
    return {
        "iid": iid, "nome": str(r.get("nome") or m.get("nome") or iid), "ticker": _ticker(r.get("linha")),
        "tipo": "acao", "pais": str(r.get("pais") or ""), "pais_nome": PAISES.get(str(r.get("pais")), str(r.get("pais") or NA)),
        "setor": str(r.get("setor") or ""), "setor_nome": SETORES.get(str(r.get("setor")), str(r.get("setor") or NA)),
        "arquetipo_nome": ARQUETIPOS.get(str(r.get("arquetipo")), str(r.get("arquetipo") or NA)),
        "moeda": moeda, "preco": _num(r.get("preco")), "preco_texto": preco(_num(r.get("preco")), moeda),
        "preco_data": r.get("data_preco"),
        "alvo": alvo, "alvo_texto": preco(alvo, moeda) if citavel else rating,
        "upside": _num(r.get("upside")) if citavel else None,
        "upside_texto": pct(_num(r.get("upside")), 1, True) if citavel else NA,
        "etr": _num(r.get("etr")) if citavel else None,
        "etr_texto": pct(_num(r.get("etr")), 1, True) if citavel else NA,
        "ke": _num(r.get("ke")), "ke_texto": pct(_num(r.get("ke")), 1),
        "rating": rating, "rating_tom": TOM_RATING.get(rating, "sem"), "rating_desde": _rating_desde(evs, rating),
        "confianca": r.get("confianca") if r.get("confianca") in ("A", "B", "C") else None,
        "incerteza": inc, "incerteza_ordem": ORDEM_INCERTEZA.get(str(inc)),
        "pessimista_texto": preco(_num(r.get("alvo_pessimista")), moeda) if citavel else NA,
        "otimista_texto": preco(_num(r.get("alvo_otimista")), moeda) if citavel else NA,
        "consenso_texto": preco(_num(cons.get("alvo_medio")), moeda) if cons_ok else NA,
        "consenso_n": int(cons["n_alvo"]) if cons_ok and _num(cons.get("n_alvo")) is not None else None,
        "vs_consenso": vs, "vs_consenso_texto": pct(vs, 1, True) if vs is not None else NA,
        "data_modelo": str(r.get("snapshot") or ent.as_of.isoformat()),
        "vencimento": res.get("vencimento") if citavel else None,
        "citavel": citavel,
        "bloqueios": [x for x in str(r.get("portoes_bloqueio") or "").split(",") if x],
        "n_lacunas": len(m.get("lacunas") or []),
        "carteira": None if peso is None or peso == 0 else ("Long" if peso > 0 else "Short"),
        "carteira_peso_texto": None if peso is None or peso == 0 else pct(peso, 2, True),
        "motivo": _pt(res.get("rating_motivo") if rating in RATINGS_CITAVEIS else (
            res.get("motivo_sem_alvo") or "portão de qualidade em aberto")),
        "_tx": tx,
    }


def _linha_etf(ent: Entrada, k: str, e: Mapping[str, Any], evs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    tx = e.get("texto") or {}
    moeda = str(e.get("moeda") or "USD")
    visao = str(e.get("visao_ilf") or "Em revisão")
    citavel = bool(e.get("tem_alvo")) and visao in VISOES_CITAVEIS
    peso = (ent.carteira or {}).get(k)
    return {
        "iid": k, "nome": str(e.get("nome") or k), "ticker": _ticker(e.get("ticker")), "tipo": "etf",
        "pais": str(e.get("pais") or ""), "pais_nome": PAISES.get(str(e.get("pais")), str(e.get("pais") or NA)),
        "setor": "ETF", "setor_nome": "ETF", "arquetipo_nome": "ETF (carteira subjacente)", "moeda": moeda,
        "preco": _num(e.get("preco")), "preco_texto": tx.get("preco") or preco(_num(e.get("preco")), moeda),
        "preco_data": e.get("data_preco"),
        "alvo": _num(e.get("preco_alvo")) if citavel else None,
        "alvo_texto": (tx.get("preco_alvo") or preco(_num(e.get("preco_alvo")), moeda)) if citavel else visao,
        "upside": _num(e.get("upside")) if citavel else None,
        "upside_texto": pct(_num(e.get("upside")), 1, True) if citavel else NA,
        "etr": _num(e.get("retorno_esperado")) if citavel else None,
        "etr_texto": pct(_num(e.get("retorno_esperado")), 1, True) if citavel else NA,
        "ke": None, "ke_texto": NA, "rating": visao, "rating_tom": TOM_RATING.get(visao, "sem"),
        "rating_desde": _rating_desde(evs, visao), "confianca": None, "incerteza": None,
        "incerteza_ordem": None,
        "pessimista_texto": NA, "otimista_texto": NA, "consenso_texto": NA, "consenso_n": None,
        "vs_consenso": None, "vs_consenso_texto": NA, "data_modelo": ent.as_of.isoformat(),
        "vencimento": None, "citavel": citavel,
        "bloqueios": [p["codigo"] for p in e.get("portoes") or [] if p.get("status") == "bloqueio"],
        "n_lacunas": len(e.get("lacunas") or []),
        "carteira": None if peso is None or peso == 0 else ("Long" if peso > 0 else "Short"),
        "carteira_peso_texto": None if peso is None or peso == 0 else pct(peso, 2, True),
        "motivo": None, "_tx": tx,
    }


def _universo(ent: Entrada) -> list[dict[str, Any]]:
    por = _eventos_por_iid(ent)
    acoes = [_linha_acao(ent, r, por.get(str(r["issuer_id"]), []))
             for r in sorted(ent.linhas, key=lambda r: str(r["issuer_id"]))]
    etfs = [_linha_etf(ent, k, ent.etfs[k], por.get(k, [])) for k in sorted(ent.etfs)]
    return acoes + etfs


def _mediana(vs: Sequence[float]) -> float | None:
    xs = sorted(vs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def _contagens(uni: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    acoes = [u for u in uni if u["tipo"] == "acao"]
    por = {r: sum(1 for u in acoes if u["rating"] == r) for r in RATINGS}
    return {"instruments": len(uni), "stocks": len(acoes), "etfs": len(uni) - len(acoes),
            "with_target": sum(1 for u in acoes if u["citavel"]),
            "without_target": por["Sem preço-alvo"], "under_review": por["Em revisão"],
            "by_rating": por, "in_book": sum(1 for u in uni if u["carteira"])}


def _kpis(ent: Entrada, uni: Sequence[Mapping[str, Any]], cont: Mapping[str, Any],
          precos_em: str | None) -> list[dict[str, Any]]:
    acoes = [u for u in uni if u["tipo"] == "acao"]
    ups = [u["upside"] for u in acoes if u["citavel"] and u["upside"] is not None]
    vs = [u["vs_consenso"] for u in acoes if u["vs_consenso"] is not None]
    por = cont["by_rating"]
    out = [
        {"label": "Instrumentos cobertos", "value": f"{cont['instruments']}",
         "sub": f"{cont['stocks']} ações · {cont['etfs']} ETFs"},
        {"label": "Com preço-alvo", "value": f"{cont['with_target']}",
         "sub": (f"de {cont['stocks']} ações · {por['Em revisão']} em revisão · "
                 f"{por['Sem preço-alvo']} sem preço-alvo")},
        {"label": "Ratings", "value": f"{por['Compra']} · {por['Neutro']} · {por['Venda']}",
         "sub": "Compra · Neutro · Venda", "mix": [
             {"rating": r, "tom": TOM_RATING[r], "n": por[r]} for r in RATINGS if por[r]]},
        {"label": "Potencial mediano", "value": pct(_mediana(ups), 1, True) if ups else NA,
         "sub": f"{len(ups)} ações com preço-alvo, no retrato de {_data(ent.as_of.isoformat())}"},
        {"label": "Diferença mediana ao consenso", "value": pct(_mediana(vs), 1, True) if vs else NA,
         "sub": f"preço-alvo da gestão ÷ consenso público − 1 · {len(vs)} ações"},
    ]
    return out


def _dominio_upside(vs: Sequence[float]) -> tuple[float, float, list[float]]:
    xs = sorted(vs)
    if not xs:
        return -0.5, 0.5, [-0.5, 0.0, 0.5]
    lo = xs[max(0, int(len(xs) * 0.02))]
    hi = xs[min(len(xs) - 1, int(len(xs) * 0.98))]
    lo, hi = min(lo, -0.1), max(hi, 0.1)
    return _ticks(lo, hi, 5)


def _enxame(xs: Sequence[float], raio: float, niveis: int) -> list[int]:
    """Nível vertical de cada ponto (0, +1, −1, +2, …) sem sobrepor vizinhos a menos de ``raio``
    (determinístico: pontos em ordem de x; empate pela ordem de entrada)."""
    ordem = sorted(range(len(xs)), key=lambda i: (xs[i], i))
    ocup: dict[int, list[float]] = {}
    out = [0] * len(xs)
    seq = [0] + [s * k for k in range(1, niveis + 1) for s in (1, -1)]
    for i in ordem:
        for lv in seq:
            if all(abs(xs[i] - x) >= raio for x in ocup.get(lv, [])):
                break
        else:
            lv = min(seq, key=lambda v: len(ocup.get(v, [])))
        ocup.setdefault(lv, []).append(xs[i])
        out[i] = lv
    return out


def _distribuicao(ent: Entrada, uni: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """V5: potencial por país (ou setor); cor = rating; anel = na carteira."""
    pts = [u for u in uni if u["tipo"] == "acao" and u["citavel"] and u["upside"] is not None]
    lo, hi, ticks = _dominio_upside([u["upside"] for u in pts])
    ex = _Escala(lo, hi)
    out: dict[str, Any] = {
        "n": len(pts), "as_of": ent.as_of.isoformat(), "dominio_texto": f"{pct(lo, 0, True)} a {pct(hi, 0, True)}",
        "eixo": [{"x": ex(t), "t": pct(t, 0, True)} for t in _rotulos(ticks, 7)], "zero": ex(0.0),
        "fora": len([u for u in uni if u["tipo"] == "acao" and not u["citavel"]]),
        "leiautes": {},
    }
    for chave, campo, nome in (("pais", "pais", "pais_nome"), ("setor", "setor", "setor_nome")):
        grupos: dict[str, list[Mapping[str, Any]]] = {}
        for u in pts:
            grupos.setdefault(str(u[campo]), []).append(u)
        ordem = sorted(grupos, key=lambda g: (-len(grupos[g]), g))
        linha_px, rotulo_px, centro_px, nivel_px = 52, 15, 33, 6
        altura = max(1, len(ordem)) * linha_px
        linhas, pontos = [], []
        for i, g in enumerate(ordem):
            us = sorted(grupos[g], key=lambda u: u["iid"])
            topo = i * linha_px
            meio = topo + centro_px
            linhas.append({"t": str(us[0][nome]), "n": len(us), "y0": _c(topo / altura * 100),
                           "h": _c(linha_px / altura * 100), "ly": _c((topo + rotulo_px) / altura * 100),
                           "alt": i % 2, "med": pct(_mediana([u["upside"] for u in us]), 1, True)})
            xs = [ex(u["upside"]) for u in us]
            lv = _enxame(xs, 1.1, 2)
            for u, x, k in zip(us, xs, lv, strict=True):
                pontos.append({"i": u["iid"], "x": x, "y": _c((meio + k * nivel_px) / altura * 100),
                               "r": u["rating_tom"], "c": 1 if u["carteira"] else 0,
                               "f": 1 if u["upside"] < lo or u["upside"] > hi else 0})
        out["leiautes"][chave] = {"altura": altura, "linhas": linhas, "pontos": pontos}
    return out


def _dispersao(ent: Entrada, uni: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """V6: potencial da gestão × potencial do consenso público (mesmo preço); tamanho = liquidez."""
    pts = []
    for u in uni:
        if u["tipo"] != "acao" or not u["citavel"] or u["upside"] is None:
            continue
        cons = ((ent.modelos.get(u["iid"]) or {}).get("resumo") or {}).get("consenso") or {}
        cu = _num(cons.get("upside")) if cons.get("plausivel") else None
        if cu is None:
            continue
        pts.append((u, cu))
    if not pts:
        return {"n": 0}
    vals = [u["upside"] for u, _ in pts] + [c for _, c in pts]
    lo, hi, ticks = _dominio_upside(vals)
    ex, ey = _Escala(lo, hi), _Escala(lo, hi, invertida=True)
    rot = _rotulos(ticks, 6)
    adtv = sorted(v for v in (ent.adtv_usd.get(u["iid"]) for u, _ in pts) if v is not None)
    t1 = adtv[len(adtv) // 3] if adtv else None
    t2 = adtv[2 * len(adtv) // 3] if adtv else None

    def tam(iid: str) -> int:
        v = ent.adtv_usd.get(iid)
        if v is None or t1 is None or t2 is None:
            return 1
        return 1 if v < t1 else 2 if v < t2 else 3

    acima = sum(1 for u, c in pts if u["upside"] > c)
    fora = sum(1 for u, c in pts if not (lo <= u["upside"] <= hi and lo <= c <= hi))
    return {
        "n": len(pts), "as_of": ent.as_of.isoformat(), "acima": acima, "abaixo": len(pts) - acima,
        "dominio_texto": f"{pct(lo, 0, True)} a {pct(hi, 0, True)}", "fora": fora,
        "eixo_x": [{"x": ex(t), "t": pct(t, 0, True)} for t in rot],
        "eixo_y": [{"y": ey(t), "t": pct(t, 0, True) if t in rot else ""} for t in ticks],
        "zero_x": ex(0.0), "zero_y": ey(0.0),
        "diagonal": _caminho([(ex(lo), ey(lo)), (ex(hi), ey(hi))]),
        "quadrantes": [{"x": ex(0.0), "y": 0.0, "w": _c(100 - ex(0.0)), "h": ey(0.0)},
                       {"x": 0.0, "y": ey(0.0), "w": ex(0.0), "h": _c(100 - ey(0.0))}],
        "pontos": [{"i": u["iid"], "x": ex(min(max(c, lo), hi)), "y": ey(min(max(u["upside"], lo), hi)),
                    "r": u["rating_tom"], "s": tam(u["iid"]), "c": 1 if u["carteira"] else 0,
                    "f": 0 if lo <= u["upside"] <= hi and lo <= c <= hi else 1, "ct": pct(c, 1, True)}
                   for u, c in sorted(pts, key=lambda p: p[0]["iid"])],
    }


def _mistura(uni: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    acoes = [u for u in uni if u["tipo"] == "acao"]

    def barra(us: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        n = len(us)
        out = []
        for r in RATINGS:
            k = sum(1 for u in us if u["rating"] == r)
            if k:
                out.append({"rating": r, "tom": TOM_RATING[r], "n": k, "w": round(k / n * 100, 2),
                            "t": f"{r}: {k} de {n} ({pct(k / n, 0)})"})
        return out

    paises: dict[str, list[Mapping[str, Any]]] = {}
    for u in acoes:
        paises.setdefault(u["pais_nome"], []).append(u)
    return {"total": barra(acoes), "n": len(acoes),
            "paises": [{"t": p, "n": len(us), "segs": barra(us)}
                       for p, us in sorted(paises.items(), key=lambda kv: (-len(kv[1]), kv[0]))]}


# ==========================================================================================
# ETFs, placar, revisões, metodologia
# ==========================================================================================


def _etf_pub(k: str, e: Mapping[str, Any], n_top: int, nomes: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Cartão do ETF: as maiores posições com o nome da casa (e o vínculo para a ficha) quando a
    posição é coberta; as demais com o nome do arquivo de composição, sem o sufixo do recibo."""
    tx = e.get("texto") or {}
    nomes = nomes or {}
    visao = str(e.get("visao_ilf") or "Em revisão")
    posicoes = sorted((p for p in e.get("posicoes") or [] if _num(p.get("peso")) is not None),
                      key=lambda p: (-float(p["peso"]), str(p.get("nome"))))
    pmax = float(posicoes[0]["peso"]) if posicoes else 1.0
    top = []
    for p in posicoes[:n_top]:
        ptx = p.get("texto") or {}
        # retorno esperado da posição (preço, proventos e câmbio); sem ele, o potencial de preço
        u = _num(p.get("retorno") if p.get("retorno") is not None else p.get("u"))
        iid = str(p.get("issuer_id")) if p.get("issuer_id") else None
        top.append({"t": nomes.get(iid) if iid in nomes else _nome_posicao(p.get("nome") or p.get("ticker_bruto")),
                    "peso": ptx.get("peso") or pct(_num(p.get("peso")), 2),
                    "w": round(float(p["peso"]) / pmax * 100, 2) if pmax > 0 else 0.0,
                    "u": (ptx.get("retorno") if p.get("retorno") is not None else ptx.get("u")) or pct(u, 1, True),
                    "tom": _tom_valor(u),
                    "imp": bool(p.get("imputado")), "i": iid if iid in nomes else None})
    citavel = bool(e.get("tem_alvo")) and visao in VISOES_CITAVEIS
    return {
        "iid": k, "ticker": _ticker(e.get("ticker")), "nome": str(e.get("nome") or k),
        "indice": e.get("indice"), "visao": visao, "tom": TOM_RATING.get(visao, "sem"),
        "preco": tx.get("preco") or NA, "alvo": (tx.get("preco_alvo") or NA) if citavel else visao,
        "upside": (tx.get("upside") or NA) if citavel else NA,
        "retorno": (tx.get("retorno_esperado") or NA) if citavel else NA,
        "bu": tx.get("r_bu") or NA, "td": tx.get("r_td") or NA,
        "cobertura": tx.get("cobertura") or NA, "te_ilf": tx.get("te_ilf") or NA,
        "faixa": tx.get("banda_90") or NA, "custo": tx.get("ter") or NA,
        "metodo": ("combinação do retorno pelas posições (modelos da casa) e pelo índice (Grinold–Kroner)"
                   if e.get("metodo") == "combinado" else str(e.get("metodo") or NA)),
        "n_posicoes": len(posicoes), "top": top,
        "avisos": [_pt(str(a), nomes) for a in e.get("avisos") or []],
    }


def _ci(xs: Sequence[float]) -> tuple[float, float, float] | None:
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    h = 1.6448536269514722 * sd / math.sqrt(n)
    return m, m - h, m + h


def _semanas_residuais(ent: Entrada) -> list[dict[str, Any]]:
    """Pares de snapshots completos consecutivos: α_rel no início e retorno residual (país ×
    setor) até o seguinte, por emissor com rating citável (o mesmo critério do IC do placar)."""
    from ..cobertura.placar import residualizar

    acoes = [e for e in ent.eventos if not str(e.get("issuer_id", "")).startswith("ETF_")
             and not e.get("parcial")]
    por_data: dict[str, dict[str, dict[str, Any]]] = {}
    for e in acoes:
        por_data.setdefault(e["as_of"], {})[e["issuer_id"]] = e
    datas = sorted(por_data)
    out = []
    for a, b in zip(datas, datas[1:], strict=False):
        ea, eb = por_data[a], por_data[b]
        linhas = []
        for iid in sorted(ea):
            e, f = ea[iid], eb.get(iid)
            ar = _num(e.get("alpha_rel"))
            if f is None or ar is None or e.get("linha") != f.get("linha") or _rating_ev(e) not in RATINGS_CITAVEIS:
                continue
            rt = (f.get("preco_ref") or {}).get("retorno_total_usd") or {}
            if rt.get("desde") == a and _num(rt.get("valor")) is not None:
                ret = float(rt["valor"])
            else:
                p_a = _num((e.get("preco_ref") or {}).get("fechamento"))
                p_b = _num((f.get("preco_ref") or {}).get("fechamento"))
                fs = _num(((f.get("preco_ref") or {}).get("fator_split") or {}).get("valor")) or 1.0
                if not p_a or not p_b:
                    continue
                ret = p_b * fs / p_a - 1
            linhas.append((iid, ar, ret, _rating_ev(e), e.get("pais"), e.get("setor")))
        if len(linhas) < 10:
            continue
        res = list(residualizar([x[2] for x in linhas],
                                [f"{x[4]}|{x[5]}" if x[4] and x[5] else None for x in linhas],
                                [x[4] for x in linhas]))
        out.append({"de": a, "ate": b, "linhas": [(x[0], x[1], r, x[3]) for x, r in zip(linhas, res, strict=True)]})
    return out


def _referencia(lit: Mapping[str, Any], chave: str) -> str | None:
    """Faixa de referência de estudos publicados, só quando o placar cita o estudo
    (``{"faixa": [a, b], "fonte": "autores, ano, amostra"}``); faixa sem fonte não é publicada."""
    r = lit.get(chave)
    if not isinstance(r, Mapping) or not r.get("fonte") or len(r.get("faixa") or []) != 2:
        return None
    a, b = r["faixa"]
    return f"referência: {pct(_num(a), 0)}–{pct(_num(b), 0)} ({r['fonte']})"


def _placar(ent: Entrada, max_ic: int) -> dict[str, Any]:
    pl = ent.placar or {}
    n_venc = int(pl.get("n_vencidas") or 0)
    n_prev = int(pl.get("n_previsoes") or 0)
    minimo = int(((ent.configuracao or {}).get("acompanhamento") or {}).get("n_min_exibir") or 20)
    prim = pl.get("primeiro_vencimento")
    lit = pl.get("referencias_literatura") or {}
    venc_t = (f"primeiro vencimento em {_data(prim)}" if prim else None)
    if n_venc:
        sub_mat = f"{n_venc} previsões vencidas de {n_prev}; a taxa é publicada a partir de {minimo} vencidas"
    else:
        sub_mat = f"Nenhuma previsão vencida entre as {n_prev} em aberto; a taxa é publicada a partir de {minimo} vencidas"
    sub_mat += f"; {venc_t}" if venc_t else ""

    def taxa(chave: str, rotulo: str, sub: str) -> dict[str, Any]:
        t = pl.get(chave) or {}
        ref_t = _referencia(lit, chave)
        if not pl.get("exibir_taxas") or t.get("taxa") is None:
            return {"label": rotulo, "value": "Em maturação", "maturacao": True, "sub": sub_mat,
                    "ref": ref_t, "desc": sub}
        ic = t.get("ic90") or [None, None]
        return {"label": rotulo, "value": pct(t.get("taxa"), 0), "maturacao": False,
                "sub": f"N = {t.get('n')} · IC de 90%: {pct(ic[0], 0)}–{pct(ic[1], 0)}", "ref": ref_t,
                "desc": sub}

    tiles = [taxa("tpmet12", "Alvo atingido no vencimento", "preço no vencimento do lado do alvo"),
             taxa("tpmetany", "Alvo tocado até o vencimento", "preço alcançou o alvo em algum ponto")]
    erro = _num(pl.get("erro_abs_mediano"))
    tiles.append({"label": "Erro absoluto mediano", "maturacao": erro is None or not pl.get("exibir_taxas"),
                  "value": pct(erro, 0) if erro is not None and pl.get("exibir_taxas") else "Em maturação",
                  "sub": (f"|preço no vencimento ÷ alvo − 1| · {n_venc} vencidas" if n_venc
                          else "|preço no vencimento ÷ alvo − 1|; " + (venc_t or "sem vencimentos")),
                  "ref": _referencia(lit, "erro_abs"), "desc": None})
    icr = pl.get("ic_resumo") or {}
    semanas = int(icr.get("semanas") or 0)
    madura = semanas >= N_MIN_PLACAR_SEMANAS
    tiles.append({"label": "IC semanal médio", "maturacao": not madura,
                  "value": pct(_num(icr.get("media")), 1, True) if semanas else "Em maturação",
                  "sub": (f"{semanas} semanas · t de Newey–West {_fmt_n(icr.get('t_newey_west'))}"
                          + ("" if madura else f" · em maturação até {N_MIN_PLACAR_SEMANAS} semanas"))
                  if semanas else f"mínimo de {N_MIN_PLACAR_SEMANAS} semanas entre retratos completos",
                  "ref": "correlação de postos entre α relativo e o retorno residual da semana seguinte",
                  "desc": None})
    ics = list(pl.get("ic_semanal") or [])[-max_ic:]
    serie = None
    if len(ics) >= 2:
        vals = [float(x["ic"]) for x in ics]
        lim = max(0.05, max(abs(v) for v in vals))
        lo, hi, ticks = _ticks(-lim, lim, 4)
        ey = _Escala(lo, hi, invertida=True)
        n = len(ics)
        larg = 100.0 / n
        medias = []
        for i in range(n):
            janela = vals[max(0, i - 12): i + 1]
            medias.append(sum(janela) / len(janela))
        serie = {"n": n, "maturacao": n < N_MIN_PLACAR_SEMANAS,
                 "eixo_y": [{"y": ey(t), "t": _fmt_n(t)} for t in ticks], "zero": ey(0.0),
                 "barras": [{"x": _c(i * larg + larg * 0.15), "w": _c(larg * 0.7),
                             "y": min(ey(v), ey(0.0)), "h": _c(abs(ey(v) - ey(0.0))), "tom": _tom_valor(v),
                             "t": f"{_data(x['data'])} → {_data(x['ate'])}: IC {_fmt_n(v)} (N = {x['n']})"}
                            for i, (x, v) in enumerate(zip(ics, vals, strict=True))],
                 "media": _caminho([(_c(i * larg + larg / 2), ey(m)) for i, m in enumerate(medias)]),
                 "eixo_x": [{"x": _c(i * larg + larg / 2), "t": _data(ics[i]["data"])[:5]}
                            for i in sorted({0, n // 2, n - 1})]}
    semanas_res = _semanas_residuais(ent)
    return {"n_previsoes": int(pl.get("n_previsoes") or 0), "n_vencidas": n_venc,
            "primeiro_vencimento": prim, "em_maturacao": bool(pl.get("em_maturacao", True)),
            "tiles": tiles, "ic": serie, "calibracao": _calibracao(semanas_res),
            "carteiras": _carteiras_rating(semanas_res),
            "metodo": _pt(str(pl["metodo"])[:1].upper() + str(pl["metodo"])[1:]) if pl.get("metodo") else None,
            "obsoletos": int(pl.get("obsoletos") or 0)}


def _fmt_n(v: Any, casas: int = 2) -> str:
    x = _num(v)
    if x is None:
        return NA
    from ..cobertura.formato import num

    return num(x, casas, True)


def _calibracao(semanas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """V7: retorno residual médio da semana seguinte por quintil de α relativo (IC de 90%)."""
    n_sem = len(semanas)
    if n_sem < N_MIN_GRAFICO_SEMANAS:
        return {"semanas": n_sem, "exibir": False, "minimo": N_MIN_GRAFICO_SEMANAS}
    grupos: dict[int, list[float]] = {q: [] for q in range(1, 6)}
    for s in semanas:
        ls = sorted(s["linhas"], key=lambda x: (x[1], x[0]))
        n = len(ls)
        for i, x in enumerate(ls):
            grupos[min(5, 1 + i * 5 // n)].append(float(x[2]))
    est = {q: _ci(v) for q, v in grupos.items()}
    vals = [b for e in est.values() if e for b in e]
    if not vals:
        return {"semanas": n_sem, "exibir": False, "minimo": N_MIN_GRAFICO_SEMANAS}
    lim = max(0.002, max(abs(v) for v in vals))
    lo, hi, ticks = _ticks(-lim, lim, 4)
    ey = _Escala(lo, hi, invertida=True)
    pts = []
    for q in range(1, 6):
        e = est[q]
        x = _c((q - 0.5) * 20)
        pts.append({"x": x, "q": f"Q{q}", "n": len(grupos[q]),
                    "y": ey(e[0]) if e else None, "y0": ey(e[2]) if e else None, "y1": ey(e[1]) if e else None,
                    "t": (f"Q{q} ({'menor' if q == 1 else 'maior' if q == 5 else 'intermediário'} α relativo): "
                          f"{pct(e[0], 2, True)} por semana (IC de 90%: {pct(e[1], 2, True)} a {pct(e[2], 2, True)}; "
                          f"N = {len(grupos[q])})") if e else f"Q{q}: sem observações"})
    return {"semanas": n_sem, "exibir": True, "maturacao": n_sem < N_MIN_PLACAR_SEMANAS,
            "eixo_y": [{"y": ey(t), "t": pct(t, 1, True)} for t in ticks], "zero": ey(0.0), "pontos": pts}


def _carteiras_rating(semanas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """V9: retorno residual acumulado (soma simples, sem custos) das carteiras iguais por rating."""
    n_sem = len(semanas)
    if n_sem < N_MIN_GRAFICO_SEMANAS:
        return {"semanas": n_sem, "exibir": False, "minimo": N_MIN_GRAFICO_SEMANAS}
    acc = {"compra": [0.0], "venda": [0.0], "spread": [0.0]}
    datas = [semanas[0]["de"]]
    for s in semanas:
        c = [x[2] for x in s["linhas"] if x[3] == "Compra"]
        v = [x[2] for x in s["linhas"] if x[3] == "Venda"]
        mc = sum(c) / len(c) if c else 0.0
        mv = sum(v) / len(v) if v else 0.0
        acc["compra"].append(acc["compra"][-1] + mc)
        acc["venda"].append(acc["venda"][-1] - mv)
        acc["spread"].append(acc["spread"][-1] + mc - mv)
        datas.append(s["ate"])
    vals = [v for serie in acc.values() for v in serie]
    lo, hi, ticks = _ticks(min(vals + [0.0]), max(vals + [0.0]), 4)
    ey = _Escala(lo, hi, invertida=True)
    n = len(datas)
    xs = [_c(i / (n - 1) * 100) for i in range(n)]
    nomes = {"compra": "Compra", "venda": "Venda (invertida)", "spread": "Compra − Venda"}
    return {"semanas": n_sem, "exibir": True, "maturacao": n_sem < N_MIN_PLACAR_SEMANAS,
            "eixo_y": [{"y": ey(t), "t": pct(t, 1, True)} for t in ticks], "zero": ey(0.0),
            "eixo_x": [{"x": xs[i], "t": _data(datas[i])[:5]} for i in sorted({0, n // 2, n - 1})],
            "series": [{"k": k, "t": nomes[k], "d": _caminho(list(zip(xs, [ey(v) for v in serie], strict=True))),
                        "ultimo": pct(serie[-1], 1, True)} for k, serie in acc.items()]}


def _alvo_anterior(eventos: Sequence[Mapping[str, Any]]) -> dict[int, float | None]:
    """Preço-alvo anterior de cada evento (``seq``): o registrado no evento ou, sem ele (ETFs),
    o do evento anterior do mesmo instrumento."""
    out: dict[int, float | None] = {}
    ult: dict[str, float | None] = {}
    for e in sorted(eventos, key=lambda e: (e["as_of"], e["seq"])):
        iid = str(e.get("issuer_id"))
        reg = e.get("alvo_anterior")
        out[e["seq"]] = _num(reg.get("base")) if isinstance(reg, Mapping) else ult.get(iid)
        ult[iid] = _num((e.get("alvo") or {}).get("base"))
    return out


def _revisoes(ent: Entrada, uni: Sequence[Mapping[str, Any]], n: int) -> dict[str, Any]:
    nomes = {u["iid"]: u["nome"] for u in uni}
    moedas = {u["iid"]: u["moeda"] for u in uni}
    anterior = _alvo_anterior(ent.eventos)
    desde = (ent.as_of - timedelta(days=JANELA_REVISOES_DIAS)).isoformat()
    evs = [e for e in ent.eventos if e.get("tipo") not in ("REITERACAO", "INICIACAO") and e["as_of"] > desde]
    evs.sort(key=lambda e: (e["as_of"], e["seq"]), reverse=True)
    inic = [e for e in ent.eventos if e.get("tipo") == "INICIACAO"]
    out = []
    for e in evs[:n]:
        iid = str(e.get("issuer_id"))
        moeda = str(e.get("moeda") or moedas.get(iid) or "")
        novo = _num((e.get("alvo") or {}).get("base")) if e.get("alvo_citavel", True) else None
        ant = anterior.get(e["seq"])
        out.append({"data": e["as_of"], "data_texto": _data(e["as_of"]), "iid": iid,
                    "nome": nomes.get(iid, iid), "tipo": TIPOS_EVENTO.get(str(e.get("tipo")), str(e.get("tipo"))),
                    "de": preco(ant, moeda) if ant is not None else NA,
                    "para": preco(novo, moeda) if novo is not None else _rating_ev(e) or NA,
                    "var": pct(novo / ant - 1, 1, True) if novo and ant else NA,
                    "rating_de": e.get("rating_anterior"), "rating_para": _rating_ev(e),
                    "motivo": "; ".join(MOTIVOS_PONTE.get(str(m), str(m)) for m in e.get("motivos") or [] if m)
                    or e.get("motivo") or NA})
    return {"itens": out, "n_total": len(evs), "n_iniciacoes": len(inic), "janela_dias": JANELA_REVISOES_DIAS,
            "desde": desde, "inicio": min((e["as_of"] for e in inic), default=None)}


def _linhas_ke(cfg: Mapping[str, Any]) -> list[str]:
    """Custo de capital próprio, montado a partir do ``valuation.yaml`` arquivado no retrato (as
    mesmas regras e limites que o motor aplicou)."""
    cc = cfg.get("custo_capital") or {}
    beta = cc.get("beta") or {}
    blume = beta.get("blume") or [0.67, 0.33]
    lim_b = beta.get("limites")
    cal = cc.get("calibracao_pais") or {}
    imp = cc.get("premio_implicito_pais") or {}
    kappa = _num(imp.get("kappa")) or 0.0
    from ..cobertura.formato import num

    spread = _num(cc.get("spread_default_eua"))
    termos = ["(rf do Tesouro americano de 10 anos − spread de default dos EUA"
              + (f", {pct(spread, 2)}" if spread is not None else "") + ")",
              "β ajustado × ERP", "λ × CRP do país"]
    if cal.get("ativo"):
        termos.append("δ do país")
    if kappa > 0:
        termos.append(f"{num(kappa, 2)} × prêmio implícito pelo mercado no país")
    out = ["ke em dólar = " + " + ".join(termos)]
    b = (f"β ajustado = {num(_num(blume[0]), 2)} × β + {num(_num(blume[1]), 2)}"
         + (f", limitado a [{num(_num(lim_b[0]), 2)}; {num(_num(lim_b[1]), 2)}]" if lim_b and len(lim_b) == 2 else "")
         + " (β desalavancado do setor, realavancado pela estrutura de capital do emissor")
    b += ("; financeiras: mediana dos betas de regressão dos pares)" if beta.get("financeiras") else ")")
    out.append(b)
    lam = _num(cc.get("lambda_padrao"))
    if lam is not None:
        out.append(f"λ = {num(lam, 1)} por padrão; exceções para emissores com receita externa relevante")
    if cal.get("ativo"):
        lim = _num(cal.get("limite"))
        out.append("δ do país: ajuste de nível que faz o emissor mediano do país valer o preço com as premissas "
                   "da casa" + (f", limitado a ±{pp(lim, 1, False)}" if lim is not None else "")
                   + "; corrige o nível dos fluxos do modelo, não é prêmio de risco (a carteira é neutra a país "
                   "e o rating é relativo a país × setor); o ke sem o ajuste fica como sensibilidade")
    out += ["ke na moeda local = (1 + ke em dólar) × (1 + inflação esperada local) ÷ (1 + inflação esperada nos EUA) − 1",
            "α = retorno ponderado pelos cenários − ke; α relativo = α − mediana do α dos pares"]
    return out


def _nota_carteira(cfg: Mapping[str, Any]) -> str:
    """Relação entre o rating da cobertura e a carteira: o rating não dimensiona posições."""
    pr = ((cfg.get("alpha") or {}).get("promocao")) or {}
    try:
        from ..alpha.signals import SIGNALS

        no_alpha = "valuation_gap" in SIGNALS
    except Exception:  # noqa: BLE001 - sem o registro, vale o padrão (fora do alpha)
        no_alpha = False
    from ..cobertura.formato import num

    crit = []
    if pr.get("janela_semanas"):
        crit.append(f"no mínimo {int(pr['janela_semanas'])} semanas")
    if _num(pr.get("ic_min")) is not None:
        crit.append(f"IC médio ≥ {num(_num(pr['ic_min']), 2)}")
    if _num(pr.get("t_nw_min")) is not None:
        crit.append(f"t de Newey–West ≥ {num(_num(pr['t_nw_min']), 1)}")
    base = ("O rating de 12 meses é uma opinião de valuation e não dimensiona posições: a carteira é "
            "construída pelo alpha quantitativo da gestão, com as restrições do mandato. ")
    if no_alpha:
        return base + "O sinal de valuation da cobertura integra o alpha depois de validado pelo IC realizado."
    return base + ("O sinal de valuation da cobertura entra no alpha só depois de validado pelo IC realizado"
                   + (f" ({', '.join(crit)})" if crit else "") + "; até lá, seu peso no alpha é zero.")


def _metodologia(ent: Entrada, uni: Sequence[Mapping[str, Any]], compacta: bool) -> dict[str, Any]:
    cfg = ent.configuracao or {}
    nomes_metodo: dict[str, str] = {}
    for m in ent.modelos.values():
        for d in m.get("metodos") or []:
            if d.get("m") and d.get("nome"):
                nomes_metodo.setdefault(str(d["m"]), str(d["nome"]))
    cont: dict[str, int] = {}
    for m in ent.modelos.values():
        cont[str(m.get("arquetipo"))] = cont.get(str(m.get("arquetipo")), 0) + 1
    arq = []
    for k, pesos in sorted((cfg.get("pesos_metodos") or {}).items(), key=lambda kv: (-cont.get(kv[0], 0), kv[0])):
        arq.append({"t": ARQUETIPOS.get(k, k), "n": cont.get(k, 0),
                    "metodos": [{"t": nomes_metodo.get(mk, mk.replace("_", " ")), "peso": pct(float(w), 0)}
                                for mk, w in sorted(pesos.items(), key=lambda kv: (-float(kv[1]), kv[0]))]})
    cc = cfg.get("custo_capital") or {}
    rcfg = cfg.get("rating") or {}
    lim = rcfg.get("limiar_alpha_rel") or {}
    lim_t = ", ".join(f"{k} {pct(float(v), 0)}" for k, v in lim.items())
    crp = [{"t": PAISES.get(k, k), "v": pct(float(v), 2)} for k, v in sorted((cc.get("crp") or {}).items())
           if k not in ("US",)]
    rating = [
        {"r": "Compra", "tom": "compra",
         "t": (f"α relativo aos pares (país × setor) acima do limiar da classe de incerteza ({lim_t}); "
               f"α ≥ {pct(_num(rcfg.get('guarda_compra_alpha_min')) or 0.0, 0)}, retorno esperado do caso-base ≥ ke "
               f"e potencial positivo; confiança mínima {rcfg.get('confianca_minima', 'B')}.")},
        {"r": "Neutro", "tom": "neutro", "t": "Demais casos com preço-alvo citável."},
        {"r": "Venda", "tom": "venda",
         "t": (f"α relativo abaixo do limiar negativo; α ≤ {pct(_num(rcfg.get('guarda_venda_alpha_max')), 0)} e "
               f"retorno esperado do caso-base ≤ ke {pp(_num(rcfg.get('guarda_venda_etr_menos_ke_max')), 0)}.")},
        {"r": "Em revisão", "tom": "revisao",
         "t": "Portão de qualidade bloqueante em aberto: o modelo segue público para auditoria, mas o preço-alvo não é citado."},
        {"r": "Sem preço-alvo", "tom": "sem", "t": "Insumos insuficientes para qualquer método válido; as lacunas ficam listadas."},
    ]
    ref_codigo = ent.versao_codigo or ent.versao or "main"
    out: dict[str, Any] = {
        "horizonte": f"{int(cfg.get('horizonte_meses') or 12)} meses a partir da data do retrato",
        "versao": cfg.get("versao"),
        "cadencia": ("Retrato completo uma vez por semana, depois do fechamento do último pregão da semana; "
                     "revisões parciais após a divulgação de resultados. O retrato de uma data alimenta só "
                     "a decisão seguinte."),
        "rating": rating,
        "histerese": pp(_num(rcfg.get("histerese")), 0, False) if rcfg.get("histerese") is not None else None,
        "arquetipos": arq,
        "ke": _linhas_ke(cfg),
        "erp": pct(_num(cc.get("erp_contemporaneo")), 2) if cc.get("erp_contemporaneo") is not None else NA,
        "erp_data": _data(cc.get("erp_contemporaneo_data")) if cc.get("erp_contemporaneo_data") else None,
        "crp": crp,
        "referencia_etf": "ILF (iShares Latin America 40): visão de cada ETF frente ao regional",
        "carteira": _nota_carteira(cfg),
        "aviso": AVISO_CVM,
        "links": [
            {"t": "Metodologia da cobertura",
             "u": f"https://github.com/{ent.repositorio}/blob/{ref_codigo}/docs/cdp/COBERTURA.md"},
            {"t": "Como reproduzir os modelos",
             "u": f"https://github.com/{ent.repositorio}/blob/{ref_codigo}/docs/cdp/REPRODUZIR.md"},
            {"t": "Código dos modelos",
             "u": f"https://github.com/{ent.repositorio}/tree/{ref_codigo}/src/cdp/cobertura"},
        ],
        # endereço dos arquivos do livro na versão desta publicação (a ficha junta o caminho de
        # cada arquivo; os fragmentos não mudam quando só a versão do repositório muda)
        "repo_livro": f"https://github.com/{ent.repositorio}/blob/{ent.versao or 'main'}/book/",
    }
    if compacta:
        out.pop("crp")
    return out


# ==========================================================================================
# Preços, histórico (V1) e modelo aberto (V2–V4)
# ==========================================================================================


def _precos(ent: Entrada, uni: Sequence[Mapping[str, Any]],
            geos: Mapping[str, Mapping[str, Any]] | None = None) -> tuple[dict[str, Any], str | None]:
    """``cobertura-precos.json`` (o único arquivo da aba que muda a cada pregão, com
    ``cobertura.json``): último fechamento, potencial a esse preço e, no gráfico de preço da
    ficha, o trecho posterior ao retrato (``g``: caminho do último ponto semanal do retrato aos
    fechamentos semanais seguintes e ao último fechamento, na escala do fragmento)."""
    geos = geos or {}
    corte = _corte(ent)
    linhas = []
    datas = []
    for u in uni:
        ult = ent.ultimo_preco.get(u["iid"])
        if ult is None:
            continue
        d, p = ult
        datas.append(d)
        up = (u["alvo"] / p - 1) if u["citavel"] and u["alvo"] is not None and p else None
        row: dict[str, Any] = {"i": u["iid"], "d": d, "p": round(p, 6), "pt": preco(p, u["moeda"]),
                               "u": None if up is None else round(up, 6),
                               "ut": pct(up, 1, True) if up is not None else NA}
        geo = geos.get(u["iid"])
        if geo and geo.get("ult") and d > corte:
            X, Y = geo["X"], geo["Y"]
            semanas: dict[tuple[int, int], tuple[str, float]] = {}
            for dd, pp_ in ent.fechamentos.get(geo["ticker"], []):
                if corte < dd <= d:
                    iso = date.fromisoformat(dd).isocalendar()
                    semanas[(iso[0], iso[1])] = (dd, pp_)
            semanas[date.fromisoformat(d).isocalendar()[:2]] = (d, p)
            pts = [geo["ult"]] + [(X(dd), Y(pp_)) for dd, pp_ in sorted(semanas.values())]
            row["g"] = {"x": X(d), "y": Y(p), "c": _caminho(pts)}
        linhas.append(row)
    em = max(datas) if datas else None
    return {"meta": {"schema_version": SCHEMA_PRECOS, "as_of": em, "modelos_em": ent.as_of.isoformat(),
                     "is_synthetic": ent.is_synthetic,
                     "data_notice": SIMULATED_DATA_NOTICE if ent.is_synthetic else AVISO_REAL},
            "precos": linhas}, em


def _semanais(serie: Sequence[tuple[str, float]], ate: str) -> list[tuple[str, float, bool]]:
    """Último fechamento de cada semana (até ``ate``): as 52 mais recentes e, antes delas, um
    ponto por fim de mês até completar a janela de 104 semanas (``True`` = ponto mensal)."""
    pts = [(d, p) for d, p in serie if d <= ate]
    if not pts:
        return []
    por_semana: dict[tuple[int, int], tuple[str, float]] = {}
    for d, p in pts:
        iso = date.fromisoformat(d).isocalendar()
        por_semana[(iso[0], iso[1])] = (d, p)
    sem = sorted(por_semana.values())
    ini = (date.fromisoformat(ate) - timedelta(weeks=SEMANAS_JANELA)).isoformat()
    sem = [x for x in sem if x[0] > ini]
    recentes = sem[-SEMANAS_SEMANAIS:]
    antigos = sem[: max(0, len(sem) - SEMANAS_SEMANAIS)]
    por_mes: dict[str, tuple[str, float]] = {}
    for d, p in antigos:
        por_mes[d[:7]] = (d, p)
    return [(d, p, True) for d, p in sorted(por_mes.values())] + [(d, p, False) for d, p in recentes]


def _mais_meses(d: date, meses: int) -> date:
    a, m = divmod(d.month - 1 + meses, 12)
    y, mth = d.year + a, m + 1
    for dia in (d.day, 30, 29, 28):
        try:
            return date(y, mth, dia)
        except ValueError:
            continue
    return date(y, mth, 28)


def _citavel_ev(e: Mapping[str, Any]) -> bool:
    return bool(e.get("alvo_citavel", True)) and _rating_ev(e) in RATINGS_CITAVEIS + VISOES_CITAVEIS


def _historico(ent: Entrada, u: Mapping[str, Any], evs: Sequence[Mapping[str, Any]],
               ticker_linha: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """V1: preço × preço-alvo (degraus), faixa do consenso, ratings ao fundo, eventos e o leque
    dos cenários (ETFs: a faixa de 90%) até o vencimento.

    Só usa os fechamentos até a data dos preços do retrato: o fragmento não muda entre um
    retrato e o seguinte. Devolve também a escala (``geo``) com que :func:`_precos` desenha os
    fechamentos posteriores ao retrato."""
    moeda = u["moeda"]
    corte = _corte(ent)
    pts = _semanais(ent.fechamentos.get(ticker_linha, []), corte)
    evs = [e for e in evs if e.get("tipo") != "ENCERRAMENTO"]
    if not pts and not evs:
        return {"vazio": True}, None
    etf = u["tipo"] == "etf"
    leque = None
    if etf:
        e_m = ent.etfs.get(u["iid"]) or {}
        banda = e_m.get("banda_90") or [None, None]
        p0, base = _num(e_m.get("preco")), _num(e_m.get("preco_alvo"))
        lo_s, hi_s = (_num(banda[0]), _num(banda[1])) if len(banda) == 2 else (None, None)
        venc = _mais_meses(ent.as_of, int((ent.configuracao or {}).get("horizonte_meses") or 12)).isoformat()
    else:
        res = (ent.modelos.get(u["iid"]) or {}).get("resumo") or {}
        p0, base = _num(res.get("preco")), _num(res.get("preco_alvo"))
        lo_s, hi_s = _num(res.get("alvo_pessimista")), _num(res.get("alvo_otimista"))
        venc = res.get("vencimento")
    if venc and u["citavel"] and p0 and lo_s is not None and hi_s is not None:
        leque = (ent.as_of.isoformat(), p0, str(venc), lo_s, base, hi_s)
    folga = (ent.as_of + timedelta(days=FOLGA_POS_RETRATO_DIAS)).isoformat()
    datas = [d for d, _, _ in pts] + [e["as_of"] for e in evs] + ([leque[2]] if leque else []) + [folga]
    d0, d1 = min(datas), max(datas)
    t0 = date.fromisoformat(d0)
    span = max(1, (date.fromisoformat(d1) - t0).days)

    def X(d: str) -> float:
        return _c((date.fromisoformat(d) - t0).days / span * 100)

    vals = [p for _, p, _ in pts]
    degraus: list[tuple[str, float | None, dict[str, Any]]] = []
    for e in evs:
        degraus.append((e["as_of"], _num((e.get("alvo") or {}).get("base")) if _citavel_ev(e) else None, e))
        cons = e.get("consenso") or {}
        for k in ("alvo_alto", "alvo_baixo"):
            if _num(cons.get(k)) is not None:
                vals.append(float(cons[k]))
    vals += [v for _, v, _ in degraus if v is not None]
    if leque:
        vals += [x for x in leque[3:] if x is not None]
    if not vals:
        return {"vazio": True}, None
    lo, hi, ticks = _ticks(min(vals), max(vals), 4)
    Y = _Escala(lo, hi, invertida=True)
    fim_hist = ent.as_of.isoformat()
    alvo_pts: list[tuple[float, float] | None] = []
    cons_sup: list[tuple[float, float]] = []
    cons_inf: list[tuple[float, float]] = []
    faixas = []
    marcas = []
    degrau_visivel = False
    ant_por_seq = _alvo_anterior(evs)
    for i, (d, v, e) in enumerate(degraus):
        prox = degraus[i + 1][0] if i + 1 < len(degraus) else fim_hist
        if v is not None:
            alvo_pts += [(X(d), Y(v)), (X(prox), Y(v))]
            degrau_visivel = degrau_visivel or X(prox) > X(d)
        else:
            alvo_pts.append(None)
        cons = e.get("consenso") or {}
        a, b = _num(cons.get("alvo_alto")), _num(cons.get("alvo_baixo"))
        if a is not None and b is not None:
            cons_sup += [(X(d), Y(a)), (X(prox), Y(a))]
            cons_inf += [(X(d), Y(b)), (X(prox), Y(b))]
        r = _rating_ev(e)
        if X(prox) > X(d):
            tom = TOM_RATING.get(r, "sem")
            if faixas and faixas[-1]["tom"] == tom and faixas[-1]["_fim"] == X(d):
                faixas[-1]["w"] = _c(X(prox) - faixas[-1]["x"])
                faixas[-1]["_fim"] = X(prox)
            else:
                faixas.append({"x": X(d), "w": _c(X(prox) - X(d)), "tom": tom, "t": r, "_fim": X(prox)})
        ant = ant_por_seq.get(e["seq"])
        relevante = e.get("tipo") in ("INICIACAO", "MUDANCA_RATING", "SUSPENSAO", "RETOMADA") or (
            e.get("tipo") == "REVISAO" and v is not None and ant and abs(v / ant - 1) >= REVISAO_MARCADA)
        if relevante:
            linhas_t = [f"{_data(d)} · {TIPOS_EVENTO.get(str(e.get('tipo')), '')}",
                        f"Rating: {(e.get('rating_anterior') + ' → ') if e.get('rating_anterior') and e.get('rating_anterior') != r else ''}{r}"]
            if v is not None:
                linhas_t.append(f"Preço-alvo: {(preco(ant, moeda) + ' → ') if ant is not None else ''}{preco(v, moeda)}")
            mot = "; ".join(MOTIVOS_PONTE.get(str(x), str(x)) for x in e.get("motivos") or [] if x)
            if mot:
                linhas_t.append(f"Motivo: {mot}")
            ref = v if v is not None else _num((e.get("preco_ref") or {}).get("fechamento"))
            if ref is not None:
                marcas.append({"x": X(d), "y": Y(ref), "k": str(e.get("tipo")).lower(), "t": linhas_t})
    area_cons = None
    if cons_sup:
        area_cons = _caminho(cons_sup + cons_inf[::-1]) + "Z"
    preco_pts = [(X(d), Y(p)) for d, p, _ in pts]
    mensais = [x for x in pts if x[2]]
    zona = None
    if mensais and len(mensais) < len(pts):
        zona = {"x": X(pts[0][0]), "w": _c(X(pts[len(mensais)][0]) - X(pts[0][0])), "t": "um ponto por mês"}
    pontos = []
    for i, (d, p, mens) in enumerate(pts):
        x0 = X(pts[i - 1][0]) if i else X(d)
        x1 = X(pts[i + 1][0]) if i + 1 < len(pts) else X(d)
        a0 = _c((x0 + X(d)) / 2) if i else X(d)
        a1 = _c((X(d) + x1) / 2) if i + 1 < len(pts) else _c(X(d) + 0.6)
        alvo_v = next((v for dd, v, _ in reversed(degraus) if dd <= d), None)
        pontos.append({"x": X(d), "a": a0, "w": _c(a1 - a0), "y": Y(p), "d": _data(d), "p": preco(p, moeda),
                       "m": 1 if mens else None, "al": preco(alvo_v, moeda) if alvo_v is not None else None})
    cons_atual = None
    if degraus:
        cu = degraus[-1][2].get("consenso") or {}
        ca, cb = _num(cu.get("alvo_alto")), _num(cu.get("alvo_baixo"))
        if ca is not None and cb is not None:
            cons_atual = {"x": X(degraus[-1][0]), "y": Y(ca), "h": _c(Y(cb) - Y(ca)),
                          "t": f"Consenso público em {_data(degraus[-1][0])}: {preco(cb, moeda)} a {preco(ca, moeda)}"
                               + (f" (média {preco(_num(cu.get('alvo_medio')), moeda)}, {int(_num(cu.get('n_alvo')) or 0)} analistas)"
                                  if _num(cu.get("alvo_medio")) is not None else "")}
    faixas_pub = [{**{k: v for k, v in f.items() if k != "_fim"}, "rot": 1 if f["w"] >= 10 else None}
                  for f in faixas if f["tom"] in ("compra", "venda", "revisao")]
    tons: list[list[str]] = []
    for f in faixas_pub:
        if [f["tom"], f["t"]] not in tons:
            tons.append([f["tom"], f["t"]])
    out: dict[str, Any] = {
        "moeda": moeda, "de": d0, "ate": d1, "n": len(pts), "consenso_atual": cons_atual,
        "etf": etf or None, "tem_alvo": degrau_visivel or None,
        "eixo_y": [{"y": Y(t), "t": _preco_eixo(t, moeda, ticks)} for t in ticks],
        "eixo_x": _eixo_datas(d0, d1, X),
        "preco": _caminho(preco_pts), "alvo": _caminho(alvo_pts), "consenso": area_cons,
        "faixas": faixas_pub, "tons": tons,
        "marcas": marcas, "zona": zona, "pontos": pontos,
        "ultimo": {"x": preco_pts[-1][0], "y": preco_pts[-1][1], "d": _data(pts[-1][0]), "t": preco(pts[-1][1], moeda)}
        if pts else None,
        # linha tracejada na data do retrato (início do leque e dos fechamentos posteriores)
        "retrato": X(ent.as_of.isoformat()),
    }
    if leque:
        d_l, p0, dv, ls, lb, lh = leque
        rot = (("limite superior (90%)", "preço-alvo", "limite inferior (90%)") if etf
               else ("otimista", "base", "pessimista"))
        out["leque"] = {
            "area": _caminho([(X(d_l), Y(p0)), (X(dv), Y(lh)), (X(dv), Y(ls))]) + "Z",
            "base": _caminho([(X(d_l), Y(p0)), (X(dv), Y(lb))]) if lb is not None else None,
            "rotulos": [{"y": Y(lh), "t": f"{rot[0]} {preco(lh, moeda)}"},
                        {"y": Y(lb), "t": f"{rot[1]} {preco(lb, moeda)}"} if lb is not None else None,
                        {"y": Y(ls), "t": f"{rot[2]} {preco(ls, moeda)}"}],
            "x": X(dv), "venc": f"vencimento {_data(dv)}",
        }
        out["leque"]["rotulos"] = [r for r in out["leque"]["rotulos"] if r]
    tabela = []
    anterior = _alvo_anterior(evs)
    for e in reversed(evs):
        v = _num((e.get("alvo") or {}).get("base")) if _citavel_ev(e) else None
        ant = anterior.get(e["seq"])
        tabela.append({"data": _data(e["as_of"]), "tipo": TIPOS_EVENTO.get(str(e.get("tipo")), str(e.get("tipo"))),
                       "rating": _rating_ev(e) or NA, "alvo": preco(v, moeda) if v is not None else NA,
                       "preco": preco(_num((e.get("preco_ref") or {}).get("fechamento")), moeda),
                       "var": pct(v / ant - 1, 1, True) if v and ant else NA,
                       "motivo": "; ".join(MOTIVOS_PONTE.get(str(x), str(x)) for x in e.get("motivos") or [] if x) or NA})
    out["tabela"] = tabela
    geo = {"X": X, "Y": Y, "ult": preco_pts[-1] if preco_pts else None, "ticker": ticker_linha}
    return out, geo


def _eixo_datas(d0: str, d1: str, X: Callable[[str], float]) -> list[dict[str, Any]]:
    """Rótulos de mês espaçados (de 3 em 3 meses quando a janela é longa)."""
    a, b = date.fromisoformat(d0), date.fromisoformat(d1)
    meses = (b.year - a.year) * 12 + b.month - a.month
    passo = 1 if meses <= 6 else 3 if meses <= 30 else 6
    out = []
    y, mth = a.year, a.month
    while True:
        mth += 1
        if mth > 12:
            y, mth = y + 1, 1
        d = date(y, mth, 1)
        if d > b:
            break
        if (mth - 1) % passo == 0:
            out.append({"x": X(d.isoformat()), "t": _mes(d.isoformat())})
    return out


def _fontes_tabela(listas: Iterable[Sequence[Mapping[str, Any]]],
                   nomes: Mapping[str, str] | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    tab: list[dict[str, Any]] = []
    idx: dict[str, int] = {}
    for fs in listas:
        for f in fs or []:
            k = _chave_fonte(f)
            if k in idx:
                continue
            idx[k] = len(tab)
            tab.append({"fonte": FONTES.get(str(f.get("fonte")), str(f.get("fonte") or NA)),
                        "doc": _pt(f.get("documento"), nomes), "url": f.get("url"),
                        "pub": _data(f.get("data_publicacao")) if f.get("data_publicacao") else None,
                        "col": _data(f.get("data_coleta")) if f.get("data_coleta") else None,
                        "est": bool(f.get("data_estimada")) or None})
    return tab, idx


def _chave_fonte(f: Mapping[str, Any]) -> str:
    return "|".join(str(f.get(k)) for k in ("fonte", "url", "documento", "data_publicacao"))


def _football(m: Mapping[str, Any], u: Mapping[str, Any], ent: Entrada, ticker: str) -> dict[str, Any] | None:
    """V2: valor por método, faixa dos cenários, do consenso e das 52 semanas; linha no preço e
    losango no preço-alvo."""
    res = m.get("resumo") or {}
    moeda = u["moeda"]
    p0 = _num(res.get("preco"))
    linhas: list[dict[str, Any]] = []
    vals: list[float] = [] if p0 is None else [p0]
    for d in m.get("metodos") or []:
        v = _num(d.get("valor"))
        w = _num(d.get("peso"))
        if v is None:
            continue
        vals.append(v)
        linhas.append({"r": str(d.get("nome") or d.get("m")), "s": f"peso {pct(w, 0)}" if w else "sem peso",
                       "v": v, "t": preco(v, moeda), "k": "metodo"})
    if u["citavel"]:
        lo_s, hi_s = _num(res.get("alvo_pessimista")), _num(res.get("alvo_otimista"))
        if lo_s is not None and hi_s is not None:
            vals += [lo_s, hi_s]
            linhas.append({"r": "Cenários", "s": "pessimista – otimista", "a": lo_s, "b": hi_s,
                           "v": _num(res.get("preco_alvo")),
                           "t": f"{preco(lo_s, moeda)} – {preco(hi_s, moeda)}", "k": "cenario"})
    cons = res.get("consenso") or {}
    if cons.get("plausivel") and _num(cons.get("alvo_baixo")) is not None and _num(cons.get("alvo_alto")) is not None:
        a, b = float(cons["alvo_baixo"]), float(cons["alvo_alto"])
        vals += [a, b]
        linhas.append({"r": "Consenso público", "s": f"mínimo – máximo · {int(_num(cons.get('n_alvo')) or 0)} analistas",
                       "a": a, "b": b, "v": _num(cons.get("alvo_medio")),
                       "t": f"{preco(a, moeda)} – {preco(b, moeda)}", "k": "consenso"})
    # só até a data dos preços do retrato (o fragmento não muda com os fechamentos seguintes)
    corte = _corte(ent)
    ini52 = (date.fromisoformat(corte) - timedelta(weeks=52)).isoformat()
    serie = [p for d, p in ent.fechamentos.get(ticker, []) if ini52 < d <= corte]
    if serie:
        a, b = min(serie), max(serie)
        vals += [a, b]
        linhas.append({"r": "Últimas 52 semanas", "s": f"mínimo – máximo do fechamento até {_data(corte)}",
                       "a": a, "b": b, "v": serie[-1], "t": f"{preco(a, moeda)} – {preco(b, moeda)}", "k": "faixa52"})
    if len(linhas) < 2 or not vals:
        return None
    lo, hi, ticks = _ticks(min(vals), max(vals), 3)
    X = _Escala(lo, hi)
    for ln in linhas:
        if "a" in ln:
            x0, x1 = X(ln.pop("a")), X(ln.pop("b"))
            ln["x0"], ln["w"] = x0, _c(max(0.6, x1 - x0))
        v = ln.pop("v", None)
        ln["x"] = X(v) if v is not None else None
    alvo = _num(res.get("preco_alvo")) if u["citavel"] else None
    return {"linhas": linhas, "eixo": [{"x": X(t), "t": _preco_eixo(t, moeda, ticks)} for t in ticks],
            "preco": X(p0) if p0 is not None else None, "preco_t": f"preço {preco(p0, moeda)}",
            "alvo": X(alvo) if alvo is not None else None,
            "alvo_t": f"preço-alvo {preco(alvo, moeda)}" if alvo is not None else None}


def _sensibilidade(m: Mapping[str, Any], citavel: bool) -> dict[str, Any] | None:
    s = m.get("sensibilidade")
    if not s or not s.get("preco_alvo_texto"):
        return None
    lin = s.get("ke_texto") or []
    col = s.get("colunas_texto") or []
    ups = s.get("upside") or []
    uts = s.get("upside_texto") or []
    cells = []
    for i, row in enumerate(s.get("preco_alvo_texto") or []):
        # uma linha = {"c": [células]} (nunca lista de listas: a forma em colunas fica sem perda)
        cells.append({"c": [{"t": t, "u": uts[i][j] if i < len(uts) and j < len(uts[i]) else NA,
                             "b": _faixa(_num(ups[i][j]) if i < len(ups) and j < len(ups[i]) else None)}
                            for j, t in enumerate(row)]})
    choques = [_num(c) for c in s.get("choques_colunas") or []]
    base_c = choques.index(0.0) if 0.0 in choques else len(col) // 2
    return {"linhas": "ke", "colunas": str(s.get("colunas") or ""), "rot_linhas": lin, "rot_colunas": col,
            "celulas": cells, "base": [len(lin) // 2, base_c], "citavel": citavel}


def _ponte_pub(m: Mapping[str, Any], moeda: str, nomes: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    """V4: cascata (horizontal) do preço-alvo anterior ao novo, componente a componente."""
    p = m.get("ponte")
    if not p or not p.get("componentes"):
        return None
    comp = p["componentes"]
    a0, a1 = _num(p.get("alvo_anterior")), _num(p.get("alvo_novo"))
    if a0 is None or a1 is None:
        return None
    nivel = a0
    passos: list[tuple[str, float | None, float | None, float | None, str]] = [
        ("Preço-alvo anterior", None, a0, a0, "total")]
    for k, rot in COMPONENTES_PONTE:
        v = _num(comp.get(k))
        if v is None:
            passos.append((rot, None, None, None, "nd"))
            continue
        passos.append((rot, nivel, nivel + v, v, "pos" if v > 0 else "neg" if v < 0 else "zero"))
        nivel += v
    passos.append(("Preço-alvo novo", None, a1, a1, "total"))
    vals = [x for _, a, b, _, _ in passos for x in (a, b) if x is not None]
    lo, hi, ticks = _ticks(min(vals), max(vals), 3)
    X = _Escala(lo, hi)
    barras = []
    for rot, a, b, v, tom in passos:
        if tom == "nd":
            barras.append({"t": rot, "x": None, "w": None, "tom": tom, "v": NA})
            continue
        if tom == "total":  # total: marca no valor (a escala não começa no zero)
            barras.append({"t": rot, "x": X(float(b)), "w": None, "tom": tom, "v": preco(v, moeda)})
            continue
        x0, x1 = sorted((X(float(a)), X(float(b))))
        txt = ("+" if (v or 0) > 0 else "") + preco(v, moeda)
        barras.append({"t": rot, "x": x0, "w": _c(max(0.6, x1 - x0)), "tom": tom, "v": txt})
    return {"barras": barras, "eixo": [{"x": X(t), "t": _preco_eixo(t, moeda, ticks)} for t in ticks],
            "motivo": MOTIVOS_PONTE.get(str(p.get("motivo")), str(p.get("motivo") or NA)),
            "notas": [_pt(str(x), nomes) for x in p.get("notas") or []],
            "residuo": pct(_num(p.get("residuo_relativo")), 2) if p.get("residuo_relativo") is not None else NA}


def _portoes(ps: Sequence[Mapping[str, Any]], nomes: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    out = []
    for p in sorted(ps or [], key=lambda p: (int(re.sub(r"\D", "", str(p.get("codigo"))) or 0), str(p.get("codigo")))):
        st = str(p.get("status") or "")
        rot, tom = STATUS_PORTAO.get(st, (st.replace("_", " ").capitalize() or NA, "na"))
        out.append({"c": p.get("codigo"), "t": _pt(p.get("nome"), nomes), "s": rot, "tom": tom,
                    "d": _pt(p.get("detalhe"), nomes)})
    return out


def _resumo_portoes(ps: Sequence[Mapping[str, Any]]) -> str:
    """``n conferidos · n avisos · n bloqueios`` e, quando houver, os informativos, os que não se
    aplicam e os demais (todos os portões contados)."""
    n = {k: sum(1 for p in ps if p.get("status") == k) for k in ("ok", "aviso", "bloqueio", "informativo",
                                                                  "nao_aplicavel")}
    outros = len(ps) - sum(n.values())
    partes = [f"{n['ok']} conferido{'s' if n['ok'] != 1 else ''}", f"{n['aviso']} aviso{'s' if n['aviso'] != 1 else ''}",
              f"{n['bloqueio']} bloqueio{'s' if n['bloqueio'] != 1 else ''}"]
    if n["informativo"]:
        partes.append(f"{n['informativo']} informativo{'s' if n['informativo'] != 1 else ''}")
    if n["nao_aplicavel"]:
        partes.append(f"{n['nao_aplicavel']} não se aplica{'m' if n['nao_aplicavel'] != 1 else ''}")
    if outros:
        partes.append(f"{outros} outro{'s' if outros != 1 else ''}")
    return " · ".join(partes)


def _texto_unidade(u: Any) -> str | None:
    s = str(u or "")
    if s.startswith("preco:"):
        return f"preço ({s.split(':', 1)[1]})"
    if s.startswith("total:"):
        return f"valor total ({s.split(':', 1)[1]})"
    if s.startswith("fx:"):
        return f"câmbio ({s.split(':', 1)[1]})"
    return {"%": "taxa", "p.p.": "pontos percentuais", "x": "múltiplo", "acoes": "ações", "anos": "anos",
            "dias": "dias", "n": "número", "prob": "probabilidade", "texto": None}.get(s, s or None)


def _modelo_acao(ent: Entrada, u: Mapping[str, Any], nomes: Mapping[str, str]) -> dict[str, Any]:
    m = ent.modelos.get(u["iid"]) or {}
    res = m.get("resumo") or {}
    tx = res.get("texto") or {}
    moeda = u["moeda"]
    cit = u["citavel"]
    passos = m.get("passos") or []
    insumos = m.get("insumos") or []
    fontes, idx = _fontes_tabela([p.get("fontes") or [] for p in passos]
                                 + [[i] for i in insumos if i.get("fonte")], nomes)
    cen = m.get("cenarios") or {}
    cons = res.get("consenso") or {}
    cons_ok = bool(cons.get("plausivel")) and _num(cons.get("alvo_medio")) is not None
    cab = [
        ("Preço no retrato", f"{u['preco_texto']} · {_data(u['preco_data'])}"),
        ("Retorno esperado (caso-base, com proventos)", u["etr_texto"]),
        ("Custo de capital próprio (ke)", u["ke_texto"]),
        ("Retorno ponderado pelos cenários", tx.get("pwr") if cit else NA),
        ("Confiança", f"{u['confianca'] or NA}" + (f" · {_pt(res.get('confianca_motivo'))}" if res.get("confianca_motivo") else "")),
        ("Consenso público", f"{preco(_num(cons.get('alvo_medio')), moeda)} · {int(_num(cons.get('n_alvo')) or 0)} analistas"
         if cons_ok else NA),
        ("P/L projetado · P/VPA", f"{tx.get('pl_fwd') or NA} · {tx.get('pb') or NA}"),
    ]
    cenarios = None
    if cit and cen:
        cenarios = {
            "linhas": [
                {"t": "Pessimista", "v": preco(_num(cen.get("tp_pessimista")), moeda),
                 "p": pct(_num(cen.get("prob_mercado_pessimista")), 1)},
                {"t": "Base", "v": u["alvo_texto"], "p": NA},
                {"t": "Otimista", "v": preco(_num(cen.get("tp_otimista")), moeda),
                 "p": pct(_num(cen.get("prob_mercado_otimista")), 1)},
                {"t": "Mediana da simulação", "v": preco(_num(cen.get("tp_mediana_mc")), moeda), "p": NA},
            ],
            "resumo": [
                ("Retorno ponderado (média da simulação)", pct(_num(cen.get("pwr")), 1, True)),
                ("Percentis 10 · 50 · 90 do retorno", " · ".join(pct(_num(cen.get(k)), 1, True)
                                                              for k in ("ret_p10", "ret_p50", "ret_p90"))),
                ("Probabilidade de superar o ke", pct(_num(cen.get("prob_modelo_supera_ke")), 0)),
                ("Razão de ganho e perda", mult(_num(cen.get("udr")))),
                # média dos retornos simulados até o percentil 10 (um retorno, com sinal)
                ("Retorno médio nos 10% piores sorteios", pct(_num(cen.get("perda_esperada_cauda")), 1, True)),
                ("Sorteios da simulação", f"{int(_num(cen.get('n_sorteios')) or 0):,}".replace(",", ".")),
            ],
        }
    cc = m.get("custo_capital") or {}
    from ..cobertura.formato import num

    custo = [(rot, pct(_num(cc.get(k)), 2) if unid == "%" else pp(_num(cc.get(k)), 2) if unid == "p.p."
              else num(_num(cc.get(k)), 2))
             for k, rot, unid in CUSTO_CAPITAL if k in cc]
    metodos = []
    for d in m.get("metodos") or []:
        proj = []
        chaves: list[str] = []
        for r in d.get("projecao") or []:
            t = r.get("texto") or {}
            chaves += [k for k in t if k not in chaves]
            proj.append({"ano": r.get("ano"), **{k: t.get(k) for k in sorted(t)}})
        metodos.append({"t": d.get("nome") or d.get("m"), "peso": pct(_num(d.get("peso")), 0),
                        "v": preco(_num(d.get("valor")), moeda) if _num(d.get("valor")) is not None else NA,
                        "terminal": pct(_num(d.get("fracao_terminal")), 0) if d.get("fracao_terminal") is not None else None,
                        "motivo": _pt(d.get("motivo"), nomes), "projecao": proj or None,
                        "colunas": _colunas_projecao(chaves) if proj else None})
    pares = m.get("pares") or {}
    out = {
        "iid": u["iid"], "nome": u["nome"], "ticker": u["ticker"], "tipo": "acao",
        "pais": u["pais_nome"], "setor": u["setor_nome"], "arquetipo": u["arquetipo_nome"],
        "industria": m.get("industria"), "moeda": moeda, "as_of": m.get("as_of"),
        "versao": m.get("versao_metodologia"), "rating": u["rating"], "rating_tom": u["rating_tom"],
        "rating_desde": _data(u["rating_desde"]) if u["rating_desde"] else None,
        "rating_motivo": _pt(res.get("rating_motivo"), nomes) if cit else u["motivo"], "citavel": cit,
        "cabecalho": [{"t": a, "v": b} for a, b in cab],
        "linhas_negociadas": [{"t": f"{_ticker(x.get('ticker'))} ({_TIPO_LINHA.get(str(x.get('tipo')), x.get('tipo'))})",
                               "p": x.get("preco_texto"),
                               "a": x.get("preco_alvo_texto") if cit else NA, "u": x.get("upside_texto") if cit else NA,
                               "c": _pt(x.get("conversao"), nomes)} for x in m.get("alvos_linhas") or []],
        "football": _football(m, u, ent, str(m.get("linha"))),
        "sensibilidade": _sensibilidade(m, cit), "ponte": _ponte_pub(m, moeda, nomes),
        "cenarios": cenarios, "custo_capital": [{"t": a, "v": b} for a, b in custo],
        "metodos": metodos,
        "pares": {"grupo": _pt(pares.get("grupo"), nomes), "n": pares.get("n"),
                  "mediana": pct(_num(pares.get("mediana_alpha")), 1, True),
                  "itens": [{"t": nomes.get(str(a[0]), str(a[0])), "v": pct(_num(a[1]), 1, True), "i": str(a[0])}
                            for a in pares.get("alphas") or []]} if pares else None,
        "passos": _passos_pub(passos, idx, nomes),
        "fontes": fontes,
        "insumos": [{"t": _pt(i.get("nome"), nomes), "v": i.get("valor_texto"), "u": _texto_unidade(i.get("unidade")),
                     "per": _pt(i.get("periodo")), "pub": _data(i.get("data_publicacao")) if i.get("data_publicacao") else None,
                     "est": bool(i.get("data_estimada")) or None,
                     "fo": idx.get(_chave_fonte(i)) if i.get("fonte") else None}
                    for i in insumos],
        "lacunas": [_lacuna(x, nomes) for x in m.get("lacunas") or []],
        "avisos": [_pt(str(a), nomes) for a in m.get("avisos") or []],
        "portoes": _portoes(m.get("portoes") or [], nomes), "portoes_resumo": _resumo_portoes(m.get("portoes") or []),
        "diagnosticos": _diagnosticos(m),
        "arquivos": _arquivos_modelo(u, "modelos"),
    }
    return out


def _passos_pub(passos: Sequence[Mapping[str, Any]], idx: Mapping[str, int],
                nomes: Mapping[str, str]) -> list[dict[str, Any]]:
    """Memória de cálculo: título, fórmula, substituição, resultado, premissas e fontes de cada
    passo (o identificador do passo só serve de âncora; a página não o exibe)."""
    return [{"id": p.get("id"), "t": _pt(p.get("titulo"), nomes), "f": _pt(p.get("formula"), nomes) or None,
             "s": _pt(p.get("substituicao"), nomes), "r": _pt(p.get("resultado_texto"), nomes),
             "p": _pt(p.get("premissas"), nomes),
             "fo": [idx[_chave_fonte(f)] for f in p.get("fontes") or []] or None} for p in passos]


def _colunas_projecao(chaves: Sequence[str]) -> list[dict[str, str]]:
    """Colunas da projeção na ordem da conta, com rótulo em português (chaves desconhecidas no
    fim, em ordem alfabética)."""
    rot = dict(COLUNAS_PROJECAO)
    ordem = [k for k, _ in COLUNAS_PROJECAO if k in chaves] + sorted(k for k in chaves if k not in rot)
    return [{"k": k, "t": rot.get(k, k.replace("_", " ").capitalize())} for k in ordem]


def _lacuna(x: Any, nomes: Mapping[str, str] | None = None) -> dict[str, Any]:
    if isinstance(x, Mapping):
        return {"t": _pt(x.get("nome") or x.get("insumo"), nomes), "m": _pt(x.get("motivo"), nomes)}
    return {"t": _pt(str(x), nomes), "m": None}


def _diagnosticos(m: Mapping[str, Any]) -> list[dict[str, Any]]:
    d = m.get("diagnosticos") or {}
    icc = d.get("icc") or {}
    rev = d.get("reverso") or {}
    out = []
    if icc.get("composto") is not None:
        out.append({"t": "Custo de capital implícito no preço (mediana de GLS, MPEG, Gode–Mohanram e Claus–Thomas)",
                    "v": pct(_num(icc.get("composto")), 2)})
        out.append({"t": "Implícito menos ke", "v": pp(_num(icc.get("icc_menos_ke")), 1)})
    if rev.get("roe_implicito") is not None:
        out.append({"t": "ROE implícito no P/VPA (valuation reversa)", "v": pct(_num(rev.get("roe_implicito")), 1)})
        out.append({"t": "ROE sustentável do modelo", "v": pct(_num(rev.get("roe_sustentavel")), 1)})
    fc = m.get("fluxo_caixa_observado") or {}
    if fc.get("fcff_ano1_vs_observado") is not None:
        out.append({"t": "Fluxo de caixa livre do ano 1 ÷ (caixa operacional − investimento) observado",
                    "v": mult(_num(fc.get("fcff_ano1_vs_observado")))})
    return out


def _arquivos_modelo(u: Mapping[str, Any], pasta: str) -> list[dict[str, Any]]:
    """Arquivos abertos do modelo: ``dados`` (caminho no catálogo dos dados abertos do portal) e
    ``rel`` (caminho no livro do repositório; a página junta o endereço da versão publicada,
    ``methodology.repo_livro``, que fica fora dos fragmentos)."""
    d = u["data_modelo"]
    rel = f"cobertura/{d}/{pasta}/{u['iid']}.json"
    tab = f"cobertura/{d}/{pasta}.csv"
    return [{"t": "Modelo completo do emissor (dados abertos)" if pasta == "modelos" else "Modelo completo do ETF (dados abertos)",
             "dados": f"livro/{rel}", "rel": rel},
            {"t": "Resumo dos modelos da data (planilha)", "dados": f"livro/{tab}", "rel": tab}]


def _modelo_etf(ent: Entrada, u: Mapping[str, Any], nomes: Mapping[str, str]) -> dict[str, Any]:
    e = ent.etfs.get(u["iid"]) or {}
    tx = e.get("texto") or {}
    passos = e.get("passos") or []
    fontes, idx = _fontes_tabela([p.get("fontes") or [] for p in passos]
                                 + [[e["fonte_composicao"]] if e.get("fonte_composicao") else []], nomes)
    ag = e.get("agregados") or {}
    pub = _etf_pub(u["iid"], e, 10_000, nomes)
    cit = u["citavel"]
    cab = [("Preço", f"{u['preco_texto']} · {_data(u['preco_data'])}"),
           ("Preço-alvo (12 meses)", u["alvo_texto"]), ("Potencial", u["upside_texto"]),
           ("Retorno esperado", u["etr_texto"]), ("Visão frente ao ILF", u["rating"]),
           ("Retorno pelas posições (modelos da casa)", tx.get("r_bu") or NA),
           ("Retorno pelo índice (Grinold–Kroner)", tx.get("r_td") or NA),
           ("Cobertura pelos modelos da casa", tx.get("cobertura") or NA),
           ("Faixa de 90%", tx.get("banda_90") or NA if cit else NA),
           ("Erro de acompanhamento frente ao ILF", tx.get("te_ilf") or NA), ("Taxa de administração", tx.get("ter") or NA)]
    agreg = [("P/L corrente", mult(_num(ag.get("pl")))), ("P/L justificado", mult(_num(ag.get("pl_justificado")))),
             ("ROE do índice", pct(_num(ag.get("roe_indice")), 1)), ("Crescimento do LPA", pct(_num(ag.get("g_lpa")), 1)),
             ("Payout sustentável", pct(_num(ag.get("payout")), 1)), ("Rendimento de dividendos", pct(_num(ag.get("dy")), 2)),
             ("Cobertura do LPA", pct(_num(ag.get("cobertura_lpa")), 0))] if ag else []
    return {
        "iid": u["iid"], "nome": u["nome"], "ticker": u["ticker"], "tipo": "etf", "pais": u["pais_nome"],
        "setor": "ETF", "arquetipo": e.get("indice") or "ETF", "moeda": u["moeda"], "as_of": e.get("as_of"),
        "rating": u["rating"], "rating_tom": u["rating_tom"], "citavel": cit,
        "rating_desde": _data(u["rating_desde"]) if u["rating_desde"] else None, "rating_motivo": pub["metodo"],
        "cabecalho": [{"t": a, "v": b} for a, b in cab], "agregados": [{"t": a, "v": b} for a, b in agreg],
        "posicoes": pub["top"], "n_posicoes": pub["n_posicoes"],
        "passos": _passos_pub(passos, idx, nomes),
        "fontes": fontes, "insumos": [], "lacunas": [_lacuna(x, nomes) for x in e.get("lacunas") or []],
        "avisos": [_pt(str(a), nomes) for a in e.get("avisos") or []], "portoes": _portoes(e.get("portoes") or [], nomes),
        "portoes_resumo": _resumo_portoes(e.get("portoes") or []),
        "arquivos": _arquivos_modelo(u, "etfs"),
    }


# ==========================================================================================
# Fragmentos, níveis de compactação e exportação
# ==========================================================================================


@dataclass(frozen=True)
class Limites:
    """Cortes de ``cobertura.json`` (nunca removem linhas do universo, ratings, preços-alvo,
    potenciais, faixas de cenário nem o resumo do placar)."""

    revisoes: int = 60
    etf_top: int = 12
    ic_semanas: int = 104
    setor: bool = True
    dispersao: bool = True
    metodologia_completa: bool = True
    motivo: bool = True


NIVEIS: tuple[Limites, ...] = (
    Limites(),
    Limites(revisoes=30, etf_top=10),
    Limites(revisoes=20, etf_top=8, ic_semanas=52, motivo=False),
    Limites(revisoes=10, etf_top=5, ic_semanas=26, motivo=False, metodologia_completa=False),
    Limites(revisoes=5, etf_top=3, ic_semanas=13, motivo=False, metodologia_completa=False, setor=False),
    Limites(revisoes=0, etf_top=0, ic_semanas=13, motivo=False, metodologia_completa=False, setor=False,
            dispersao=False),
)


def _texto(obj: Any) -> str:
    return dump_publicacao(_split(_pack(obj)))


def _carimbo(obj: dict[str, Any]) -> dict[str, Any]:
    from .painel import data_hash

    obj["meta"]["data_hash"] = data_hash(obj)
    return obj


def _fragmentos(itens: Sequence[tuple[str, dict[str, Any]]], prefixo: str, schema: str,
                meta_base: Mapping[str, Any], chave: str) -> list[tuple[str, list[str], dict[str, Any]]]:
    """Empacotamento guloso determinístico (ordem dada; ETFs por último): cada fragmento até
    :data:`ALVO_FRAGMENTO` bytes no leiaute publicado."""
    grupos: list[list[tuple[str, dict[str, Any]]]] = []
    atual: list[tuple[str, dict[str, Any]]] = []
    tam = 0
    for iid, obj in itens:
        t = len(_texto({iid: obj}).encode("utf-8"))
        if atual and tam + t > ALVO_FRAGMENTO:
            grupos.append(atual)
            atual, tam = [], 0
        atual.append((iid, obj))
        tam += t
    if atual:
        grupos.append(atual)
    out = []
    for k, g in enumerate(grupos, start=1):
        nome = f"{prefixo}{k}.json"
        body = {"meta": {**meta_base, "schema_version": schema, "fragmento": k, "iids": [i for i, _ in g]},
                chave: {i: o for i, o in g}}
        out.append((nome, [i for i, _ in g], body))
    return out


def _limpo(x: Any) -> Any:
    """Sem as chaves auxiliares (``_tx``) e sem as chaves de TI."""
    if isinstance(x, dict):
        return {k: _limpo(v) for k, v in x.items() if not k.startswith("_tx")}
    if isinstance(x, list):
        return [_limpo(v) for v in x]
    return x


ESTADOS_SEM_DADOS = ("sem_cobertura", "em_verificacao")


def exportar(ent: Entrada | None, *, niveis: Sequence[Limites] = NIVEIS,
             estado: str = "sem_cobertura") -> dict[str, str]:
    """Os arquivos de dados da aba (nome → texto publicado), byte a byte estáveis.

    Os fragmentos de histórico e de modelo dependem só do retrato (fechamentos até a data dos
    preços do retrato): entre dois retratos, só ``cobertura.json`` e ``cobertura-precos.json``
    mudam com os pregões.

    ``ent = None``: só ``cobertura.json`` com ``estado`` — ``"sem_cobertura"`` (nenhum retrato
    ainda) ou ``"em_verificacao"`` (o livro da cobertura não conferiu; nada é publicado dele). A
    página mostra um aviso institucional em cada caso."""
    if ent is None:
        if estado not in ESTADOS_SEM_DADOS:
            raise ValueError(f"estado sem dados desconhecido: {estado!r}")
        vazio = {"meta": {"schema_version": SCHEMA, "estado": estado, "as_of": None,
                          "is_synthetic": False, "data_notice": None, "files": {}, "truncations": [],
                          "publication": {"nivel": 0, "niveis": len(niveis), "max_bytes": MAX_BYTES,
                                          "max_linha": MAX_LINHA}},
                 "universe": []}
        return {ARQUIVO: _texto(_carimbo(vazio))}
    uni = _universo(ent)
    nomes = {u["iid"]: u["nome"] for u in uni}
    notice = SIMULATED_DATA_NOTICE if ent.is_synthetic else AVISO_REAL
    meta_base = {"as_of": ent.as_of.isoformat(), "is_synthetic": ent.is_synthetic, "data_notice": notice,
                 "simulated_label": SIMULATED_DATA_NOTICE if ent.is_synthetic else None}
    por = _eventos_por_iid(ent)
    # histórico (V1)
    hist_itens = []
    geos: dict[str, dict[str, Any]] = {}
    for u in uni:
        linha = str((ent.modelos.get(u["iid"]) or {}).get("linha") or (ent.etfs.get(u["iid"]) or {}).get("ticker") or "")
        h, geo = _historico(ent, u, por.get(u["iid"], []), linha)
        hist_itens.append((u["iid"], h))
        if geo:
            geos[u["iid"]] = geo
    hist = _fragmentos(hist_itens, PREFIXO_HISTORICO, SCHEMA_HISTORICO, meta_base, "series")
    precos_doc, precos_em = _precos(ent, uni, geos)
    # modelo aberto
    mod_itens = [(u["iid"], _modelo_acao(ent, u, nomes) if u["tipo"] == "acao" else _modelo_etf(ent, u, nomes))
                 for u in uni]
    mods = _fragmentos(mod_itens, PREFIXO_MODELO, SCHEMA_MODELO, meta_base, "modelos")
    arquivos: dict[str, str] = {}
    idx_h = {i: k for k, (_, iids, _) in enumerate(hist, start=1) for i in iids}
    idx_m = {i: k for k, (_, iids, _) in enumerate(mods, start=1) for i in iids}
    files: dict[str, Any] = {"historico": [], "modelos": []}
    for nome, iids, body in hist + mods:
        n_ti = [0]
        body = _sem_ti(_limpo(body), n_ti)
        texto = _texto(_carimbo(body))
        arquivos[nome] = texto
        files["historico" if nome.startswith(PREFIXO_HISTORICO) else "modelos"].append(
            {"file": nome, "n": len(iids), "data_hash": body["meta"]["data_hash"]})
    precos_doc = _sem_ti(precos_doc, [0])
    arquivos[ARQUIVO_PRECOS] = _texto(_carimbo(precos_doc))
    files["precos"] = {"file": ARQUIVO_PRECOS, "data_hash": precos_doc["meta"]["data_hash"]}
    cont = _contagens(uni)
    principal: dict[str, Any] = {}
    texto = ""
    escada = list(niveis) + [n for n in NIVEIS if n not in niveis]
    for nivel, lim in enumerate(escada):
        cortes = _Cortes()
        universo = []
        for u in uni:
            row = {k: v for k, v in u.items() if k != "_tx"}
            row["mk"], row["hk"] = idx_m.get(u["iid"]), idx_h.get(u["iid"])
            if not lim.motivo:
                if row.get("motivo"):
                    cortes.add("universe[].motivo", "omitido (está no modelo aberto)")
                row.pop("motivo", None)
            universo.append(row)
        painel = {"distribuicao": _distribuicao(ent, uni), "mistura": _mistura(uni)}
        if lim.dispersao:
            painel["dispersao"] = _dispersao(ent, uni)
        else:
            cortes.add("aggregates.dispersao", "omitido (gráfico CDP × consenso)")
        if not lim.setor:
            painel["distribuicao"]["leiautes"].pop("setor", None)
            cortes.add("aggregates.distribuicao.setor", "omitido (leiaute por setor)")
        etfs_pub = [_etf_pub(k, ent.etfs[k], lim.etf_top, nomes) for k in sorted(ent.etfs)]
        n_top = sum(max(0, len([p for p in ent.etfs[k].get("posicoes") or []]) - lim.etf_top) for k in ent.etfs)
        cortes.add("etfs[].top", f"lista ≤ {lim.etf_top} posições (as demais no modelo aberto)", n_top)
        rev = _revisoes(ent, uni, lim.revisoes)
        cortes.add("revisions.itens", f"lista ≤ {lim.revisoes} eventos", max(0, rev["n_total"] - lim.revisoes))
        principal = {
            "meta": {
                **meta_base, "schema_version": SCHEMA, "estado": "publicado",
                "prices_as_of": precos_em, "page_sha256": ent.page_sha256,
                "horizon_months": int((ent.configuracao or {}).get("horizonte_meses") or 12),
                "methodology_version": (ent.configuracao or {}).get("versao"),
                "rating_scale": [{"code": r, "label": r, "tone": TOM_RATING[r]} for r in RATINGS],
                "etf_views": [{"code": v, "label": v, "tone": TOM_RATING[v]} for v in VISOES_ETF],
                "counts": cont, "snapshots": ent.snapshots, "has_book": ent.carteira is not None,
                "files": files, "aviso_cvm": AVISO_CVM,
                "publication": {"nivel": nivel, "niveis": len(escada), "limites": asdict(lim),
                                "max_bytes": MAX_BYTES, "max_linha": MAX_LINHA},
                "truncations": cortes.lista(),
            },
            "kpis": _kpis(ent, uni, cont, precos_em),
            "universe": universo,
            "aggregates": painel,
            "etfs": etfs_pub,
            "track_record": _placar(ent, lim.ic_semanas),
            "revisions": rev,
            "methodology": _metodologia(ent, uni, not lim.metodologia_completa),
        }
        if not lim.metodologia_completa:
            cortes.add("methodology.crp", "omitido (está em valuation.yaml)")
            principal["meta"]["truncations"] = cortes.lista()
        principal = _sem_ti(principal, [0])
        texto = _texto(_carimbo(principal))
        if cabe(texto, MAX_BYTES, MAX_LINHA):
            break
    arquivos[ARQUIVO] = texto
    return dict(sorted(arquivos.items()))


def conferir(arquivos: Mapping[str, str]) -> list[str]:
    """Problemas de orçamento (bytes e linha) ou de nome dos arquivos (lista vazia = ok)."""
    out = []
    for nome, texto in sorted(arquivos.items()):
        if not ARQUIVO_RE.fullmatch(nome):
            out.append(f"{nome}: nome fora do padrão da aba")
        b = len(texto.encode("utf-8"))
        if b > MAX_BYTES:
            out.append(f"{nome}: {b} bytes (máximo {MAX_BYTES})")
        ml = max_line(texto)
        if ml > MAX_LINHA:
            out.append(f"{nome}: linha de {ml} caracteres (máximo {MAX_LINHA})")
    return out


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def publicados(out_dir: Path | str) -> dict[str, str]:
    """``{arquivo: SHA-256}`` da última publicação registrada (:data:`MARCADOR`)."""
    try:
        d = json.loads((Path(out_dir) / MARCADOR).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in (d.get("arquivos") or {}).items()} if isinstance(d, dict) else {}


def gravar(out_dir: Path | str, arquivos: Mapping[str, str]) -> dict[str, Any]:
    """Grava os arquivos da aba em ``out_dir`` (só os que mudaram) e remove fragmentos que não
    fazem mais parte da publicação. Devolve o que mudou em relação à última publicação
    registrada (``mudaram``, ``removidos``) — quem publica envia esses e remove os ausentes."""
    from .painel import _write_atomic

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    escritos = []
    for nome, texto in sorted(arquivos.items()):
        p = out / nome
        try:
            atual = p.read_text(encoding="utf-8")
        except OSError:
            atual = None
        if atual != texto:
            _write_atomic(p, texto)
            escritos.append(nome)
    removidos_disco = []
    for p in sorted(out.glob("cobertura*.json")):
        if ARQUIVO_RE.fullmatch(p.name) and p.name not in arquivos:
            p.unlink()
            removidos_disco.append(p.name)
    pub = publicados(out)
    shas = {n: sha256_texto(t) for n, t in arquivos.items()}
    return {"arquivos": [{"path": (out / n).as_posix(), "bytes": len(t.encode("utf-8")), "sha256": shas[n],
                          "max_line": max_line(t)} for n, t in sorted(arquivos.items())],
            "escritos": escritos, "removidos_do_disco": removidos_disco,
            "mudaram": sorted(n for n in arquivos if pub.get(n) != shas[n]),
            "removidos": sorted(n for n in pub if n not in arquivos)}


def marcar_publicado(out_dir: Path | str, arquivos: Mapping[str, str]) -> dict[str, Any]:
    """Registra (:data:`MARCADOR`, só local) os arquivos da aba publicados com sucesso."""
    from .painel import _write_atomic

    shas = {n: sha256_texto(t) for n, t in sorted(arquivos.items())}
    _write_atomic(Path(out_dir) / MARCADOR, json.dumps({"arquivos": shas}, ensure_ascii=False, indent=1,
                                                       sort_keys=True) + "\n")
    return {"marcador": (Path(out_dir) / MARCADOR).as_posix(), "arquivos": len(shas)}


def embutir(arquivos: Mapping[str, str]) -> str:
    """Elemento ``<script type="application/json" id="cdp-cobertura-dados">`` da cópia local:
    ``{arquivo: dados}`` com todos os arquivos da aba (nada fecha o elemento)."""
    from .painel import embed_json

    dados = {n: json.loads(t) for n, t in sorted(arquivos.items())}
    return f'<script type="application/json" id="{ELEMENTO_LOCAL}">{embed_json(dados)}</script>'


def modulo_js() -> str:
    """O módulo da página (``window.CDP_COBERTURA``), como publicado."""
    texto = MODULO.read_text(encoding="utf-8")
    return texto if texto.endswith("\n") else texto + "\n"


def nome_modulo(versao: str) -> str:
    """Nome versionado do módulo: ``painel-<16 hex>-cobertura.js``."""
    return f"painel-{versao[:16]}-cobertura.js"


def resumo(rt: Any) -> dict[str, Any]:
    """Resumo para ``meta.coverage`` do painel (≤ 300 B, sem ler os modelos): se há retrato da
    cobertura, a data e as contagens do selo do último retrato. Um livro que não confere (cadeia
    ou selo) dá ``{"disponivel": False, "estado": "em_verificacao"}`` — a mesma conferência que
    :func:`carregar` faz antes de publicar."""
    from ..cobertura import livro as L

    book = Path(rt.book_root)
    datas = L.datas_snapshots(book)
    if not datas:
        return {"disponivel": False}
    try:
        ok, _ = L.verificar_livro(book)
        ok = ok and L.selado(book)[0]
    except (L.LivroErro, OSError, ValueError):
        ok = False
    if not ok:
        return {"disponivel": False, "estado": "em_verificacao"}
    d = datas[-1]
    try:
        selo = json.loads((L.raiz_cobertura(book) / d.isoformat() / "selo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        selo = {}
    return {"disponivel": True, "as_of": d.isoformat(), "instrumentos": selo.get("n_instrumentos"),
            "com_alvo": selo.get("n_com_alvo"), "dados_simulados": bool(selo.get("is_synthetic"))}


def de_book(book: Path | str, *, md: Any = None, painel: Mapping[str, Any] | None = None,
            ate: date | None = None, repositorio: str = REPOSITORIO,
            page_sha256: str | None = None, versao: str | None = None) -> dict[str, str]:
    """Atalho: lê o livro e exporta (``painel``: retrato do painel, para a carteira vigente)."""
    ent = carregar(book, ate=ate, md=md, carteira=carteira_do_painel(painel), repositorio=repositorio,
                   page_sha256=page_sha256, versao=versao)
    return exportar(ent)


def limites(nivel: int = 0, **changes: Any) -> Limites:
    return replace(NIVEIS[nivel], **changes)


__all__ = ["ARQUIVO", "ARQUIVO_PRECOS", "ARQUIVO_RE", "AVISO_CVM", "ELEMENTO_LOCAL", "ESTADOS_SEM_DADOS", "Entrada", "Limites",
           "MARCADOR", "MAX_BYTES", "MAX_LINHA", "MODULO", "NIVEIS", "PREFIXO_HISTORICO", "PREFIXO_MODELO",
           "SCHEMA", "carregar", "carteira_do_painel", "conferir", "de_book", "embutir", "exportar", "gravar",
           "limites", "marcar_publicado", "modulo_js", "nome_modulo", "publicados", "resumo"]
