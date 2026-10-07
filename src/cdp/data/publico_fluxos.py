"""Componentes de reinvestimento em tabelas HTML oficiais de demonstrações financeiras.

Complemento ao XBRL, sem valores curados por companhia: lê a coluna consolidada de direitos
de uso quando abertura, encerramento, adições e depreciação estão explícitos no mesmo quadro.
Datas são as impressas no quadro; moeda e escala vêm do cabeçalho imediatamente anterior.
Não interpreta a variação de um saldo como aquisição, nem pagamentos de principal como capex.
O chamador fornece a identidade e a data de publicação verificadas no índice da SEC ou do RI.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from html.parser import HTMLParser
from typing import Any

from .publico_cvm import FATO_COLUNAS

_MESES = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
          "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
          "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
          "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def _normal(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


class _Tabelas(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, Any]] = []
        self.tabelas: list[dict[str, Any]] = []
        self.texto = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.stack.append({"linhas": [], "linha": [], "celula": None, "antes": self.texto[-3000:]})
        elif self.stack:
            t = self.stack[-1]
            if tag == "tr":
                t["linha"] = []
            elif tag in ("td", "th"):
                t["celula"] = []

    def handle_data(self, data: str) -> None:
        self.texto += " " + data
        self.texto = self.texto[-6000:]
        if self.stack and self.stack[-1]["celula"] is not None:
            self.stack[-1]["celula"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return
        t = self.stack[-1]
        if tag in ("td", "th") and t["celula"] is not None:
            t["linha"].append(re.sub(r"\s+", " ", " ".join(t["celula"])).strip())
            t["celula"] = None
        elif tag == "tr":
            t["linhas"].append(t["linha"])
            t["linha"] = []
        elif tag == "table":
            self.tabelas.append(self.stack.pop())


def _data(s: str) -> date | None:
    t = _normal(s)
    if m := re.search(r"([a-z]+)\s+(\d{1,2}),?\s+(\d{4})", t):
        mes = _MESES.get(m[1])
        if mes is not None:
            try:
                return date(int(m[3]), mes, int(m[2]))
            except ValueError:
                return None
    if m := re.search(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", t):
        mes = _MESES.get(m[2])
        if mes is not None:
            try:
                return date(int(m[3]), mes, int(m[1]))
            except ValueError:
                return None
    return None


def _numero(s: str) -> float | None:
    # Sem convenção explicitamente publicada, traço e célula vazia são ausências. Só o
    # algarismo zero certifica zero nesta versão. Aceita formato inglês com vírgula de milhar.
    s = re.sub(r"\s+", "", s)
    if not re.fullmatch(r"\(?-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?|\(?-?\d+(?:\.\d+)?\)?", s):
        return None
    negativo = s.startswith("(") and s.endswith(")")
    return float(s.strip("()").replace(",", "")) * (-1 if negativo else 1)


def _moeda_escala(s: str) -> tuple[str, float] | None:
    t = _normal(s)
    matches = list(re.finditer(r"(?:millions? of|milhoes de)\s+(reais|u\.?s\.? dollars|us dollars|dolares)", t))
    if matches:
        m = matches[-1]
        return ("BRL" if m[1] == "reais" else "USD"), 1e6
    return None  # sem escala/idioma explícitos não há valor canônico


def fatos_fluxos_html(conteudo: bytes, entidade: str, *, documento: str, url: str,
                     data_publicacao: date, data_referencia: date) -> list[dict[str, Any]]:
    """Fatos canônicos suplementares; publicação e referência vêm do índice oficial arquivado.

    Não aceita quadro só individual, coluna ambígua, duração negativa ou quadro de período
    posterior à referência do documento. O hash dos bytes é acrescentado pela camada pública.
    """
    parser = _Tabelas()
    parser.feed(conteudo.decode("utf-8", errors="replace"))
    candidatos: list[dict[str, Any]] = []
    for n, t in enumerate(parser.tabelas):
        me = _moeda_escala(t["antes"])
        if me is None:
            continue
        moeda, escala = me
        coluna = None
        n_colunas = None
        inicio = None
        vals: dict[str, float] = {}
        ambiguos: set[str] = set()
        consolidado = False
        for r in t["linhas"]:
            norm = [_normal(c) for c in r]
            if "consolidated" in norm or "consolidado" in norm:
                bases = [c for c in norm if c in ("consolidated", "consolidado", "parent company", "controladora")]
                consolidado = bool(bases and bases[0] in ("consolidated", "consolidado"))
            # O cabeçalho imediatamente acima precisa declarar a primeira base consolidada.
            cols_rou = [i for i, c in enumerate(norm) if re.fullmatch(r"right.of.use assets|ativos? (?:de )?direito de uso", c)]
            if cols_rou:
                coluna = cols_rou[0] if len(cols_rou) == 1 and consolidado else None
                n_colunas = len(r)
                inicio, vals = None, {}
                ambiguos = set()
                continue
            if coluna is None or n_colunas is None or len(r) != n_colunas or not r:
                continue
            if re.match(r"balance (?:at|on)|saldo (?:em|no|a)", norm[0]):
                d = _data(r[0])
                if d is None:
                    continue
                if inicio is not None and vals and d > inicio and d <= data_referencia:
                    for item, value in vals.items():
                        if item in ambiguos:
                            continue
                        candidatos.append({"entidade": entidade, "demonstrativo": "NOTAS", "item": item,
                            "account": f"tabela_{n}:direitos_de_uso:{item}", "description": r[0],
                            "value": value * escala, "currency": moeda, "period_start": inicio + timedelta(days=1),
                            "period_end": d, "received_date": data_publicacao, "consolidado": True, "version": 1,
                            "documento": documento, "url": url,
                            "nota": (f"tabela HTML {n}, coluna {coluna + 1} de direitos de uso, {item}; "
                                     f"abertura {inicio.isoformat()} e encerramento {d.isoformat()}; "
                                     "quadro consolidado, moeda e escala explícitas")})
                inicio, vals, ambiguos = d, {}, set()
                continue
            item = None
            if norm[0] in ("additions", "adicoes"):
                item = "adicoes_direito_uso"
            elif norm[0] in ("depreciation, amortization and depletion", "depreciation, amortisation and depletion",
                              "depreciation", "depreciacao", "depreciacao, amortizacao e deplecao"):
                item = "depreciacao_direito_uso"
            if item is not None:
                v = _numero(r[coluna])
                if v is not None and (v >= 0 if item == "adicoes_direito_uso" else v <= 0):
                    if item in vals and vals[item] != abs(v):
                        ambiguos.add(item)
                    vals[item] = abs(v)
    # Duplicações coincidentes são iguais; divergências para o mesmo período invalidam o item.
    grupos: dict[tuple, list[dict[str, Any]]] = {}
    for r in candidatos:
        grupos.setdefault((r["item"], r["period_start"], r["period_end"], r["currency"]), []).append(r)
    return [dict((k, r[k]) for k in [*FATO_COLUNAS, "documento", "url", "nota"] if k in r)
            for g in grupos.values() if len({r["value"] for r in g}) == 1 for r in g[:1]]
