"""Demonstrações de RI em PDF, com catálogo de estrutura e hash dos bytes oficiais.

O catálogo descreve páginas físicas (base 1), títulos, colunas, períodos e rótulos;
nunca valores. Uma estrutura diferente exige revisão explícita do catálogo. Traços,
linhas incompletas e duplicatas divergentes permanecem ausentes, nunca viram zero.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

from .publico_cvm import FATO_COLUNAS, FATO_DIMENSOES

CATALOGO_RI = Path(__file__).resolve().parents[3] / "configs/cdp/ri_demonstrativos.json"
COLUNAS = FATO_COLUNAS + ["nota", "pit_estimado"]
COLUNAS_DIMENSOES = FATO_DIMENSOES  # Somente fatos documentalmente tipados.
COLUNAS_OBSERVADAS = ["disponibilidade_tipo", "disponivel_desde",
                     "data_recebimento_documento", "data_publicacao_primaria"]
_NUMERO = r"(?:\$?\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\)?|[-—])"
_MESES_ES = dict(zip(("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                     "agosto", "septiembre", "octubre", "noviembre", "diciembre"),
                    range(1, 13), strict=True))
_MESES_EN = dict(zip(("JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY",
                      "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"),
                     range(1, 13), strict=True))


def _periodos_ingles(normal: str, demonstrativo: str) -> list[tuple[str | None, str]]:
    """Datas e grão vêm da declaração literal, não só do ano em Notes."""
    if demonstrativo == "BP":
        m = re.search(r"AS OF ([A-Z]+) (\d+), (\d+) AND ([A-Z]+) (\d+), (\d+)", normal)
        if m:
            return [(None, date(int(m[3]), _MESES_EN[m[1]], int(m[2])).isoformat()),
                    (None, date(int(m[6]), _MESES_EN[m[4]], int(m[5])).isoformat())]
        m = re.search(r"AS OF ([A-Z]+) (\d+), (\d+), (\d+) AND (\d+)", normal)
        if m:
            return [(None, date(int(y), _MESES_EN[m[1]], int(m[2])).isoformat())
                    for y in m.groups()[2:]]
    else:
        m = re.search(r"FOR THE (SIX AND THREE|THREE|SIX|NINE)-MONTH PERIODS ENDED "
                      r"([A-Z]+) (\d+), (\d+) AND (\d+)", normal)
        if m:
            duracoes = {"SIX AND THREE": [6, 3], "THREE": [3], "SIX": [6], "NINE": [9]}[m[1]]
            out = []
            for meses in duracoes:
                for ano in (m[4], m[5]):
                    fim = pd.Timestamp(date(int(ano), _MESES_EN[m[2]], int(m[3])))
                    inicio = fim.replace(day=1) - pd.DateOffset(months=meses-1)
                    out.append((inicio.date().isoformat(), fim.date().isoformat()))
            return out
        m = re.search(r"FOR THE YEARS ENDED ([A-Z]+) (\d+), (\d+), (\d+) AND (\d+)", normal)
        if m:
            out = []
            for ano in m.groups()[2:]:
                fim = pd.Timestamp(date(int(ano), _MESES_EN[m[1]], int(m[2])))
                inicio = fim.replace(day=1) - pd.DateOffset(months=11)
                out.append((inicio.date().isoformat(), fim.date().isoformat()))
            return out
    raise ValueError("RI PDF: declaração de períodos/grão não reconhecida")


def _n(texto: str) -> str:
    return " ".join(texto.split())


def documentos_ri(issuer_id: str, as_of: date) -> list[dict]:
    if not CATALOGO_RI.exists():
        return []
    catalogo = json.loads(CATALOGO_RI.read_text(encoding="utf-8"))
    if catalogo.get("schema") != "cdp.ri_demonstrativos/v1":
        raise ValueError("catálogo RI: schema desconhecido")
    documentos = []
    for d in catalogo["documentos"]:
        if d["issuer_id"] != issuer_id:
            continue
        if d.get("disponibilidade_tipo") == "recepcao_observada":
            # Descoberta por competência; elegibilidade só depois da recepção real.
            fins = [date.fromisoformat(c["fim"]) for t in d["tabelas"] for c in t["colunas"]]
            if fins and max(fins) <= as_of:
                documentos.append(d)
        elif date.fromisoformat(d["data_publicacao"]) <= as_of:
            documentos.append(d)
    return documentos


def _valor(celula: str) -> Decimal | None:
    if celula in {"-", "—"}:
        return None
    v = celula.replace("$", "").replace(",", "")
    if v.startswith("(") and v.endswith(")"):
        v = "-" + v[1:-1]
    return Decimal(v)


def fatos_pdf_ri(conteudo: bytes, documento: dict, *, as_of: date,
                 recebido_em: datetime | None = None) -> pd.DataFrame:
    """Confere o documento inteiro antes de ler as tabelas catalogadas.

    ``data_publicacao`` deve aparecer no próprio PDF em uma página com a entidade;
    ela não é inferida do nome do arquivo. Publicação/período futuro é recusado.
    A ordem integral das colunas deve coincidir com o cabeçalho do PDF.
    """
    if hashlib.sha256(conteudo).hexdigest() != documento["sha256"]:
        raise ValueError("RI PDF: hash diferente do catálogo")
    observado = documento.get("disponibilidade_tipo") == "recepcao_observada"
    publicacao = None if observado else date.fromisoformat(documento["data_publicacao"])
    if observado and documento.get("data_publicacao") is not None:
        raise ValueError("RI observado: publicação desconhecida não recebe uma data presumida")
    if recebido_em is not None and recebido_em.tzinfo is None:
        raise ValueError("RI observado: recebimento exige fuso explícito")
    if publicacao is not None and publicacao > as_of:
        raise ValueError("RI PDF: publicação posterior à data-base")
    pdf = PdfReader(io.BytesIO(conteudo), strict=True)
    if pdf.is_encrypted:
        raise ValueError("RI PDF: arquivo criptografado")
    textos = {}

    def pagina(numero: int) -> str:
        if numero < 1 or numero > len(pdf.pages):
            raise ValueError("RI PDF: página física inexistente")
        if numero not in textos:
            textos[numero] = (pdf.pages[numero - 1].extract_text(extraction_mode="layout")
                              if observado else pdf.pages[numero - 1].extract_text()) or ""
        return textos[numero]

    if not observado:
        prova = documento["publicacao_no_documento"]
        texto_prova = _n(pagina(prova["pagina"]))
        data_extenso = re.fullmatch(r"(\d{1,2}) de ([a-z]+) de (\d{3}\s*\d)",
                                   _n(prova["texto"]).lower())
        if not data_extenso or data_extenso.group(2) not in _MESES_ES:
            raise ValueError("RI PDF: data de publicação por extenso não reconhecida")
        data_no_pdf = date(int(data_extenso.group(3).replace(" ", "")),
                           _MESES_ES[data_extenso.group(2)], int(data_extenso.group(1)))
        if data_no_pdf != publicacao:
            raise ValueError("RI PDF: data do catálogo difere da data no documento")
        if (_n(prova["texto"]) not in texto_prova
                or _n(documento["entidade_documento"]) not in texto_prova):
            raise ValueError("RI PDF: entidade/data de publicação não conferem")
    saida = []
    for tabela in documento["tabelas"]:
        texto = pagina(tabela["pagina"])
        normal = _n(texto)
        if observado and _n(documento["entidade_documento"]) not in normal:
            raise ValueError("RI PDF: identidade da entidade não confere")
        if observado and tabela.get("tipo") != "capital":
            unidade = re.search(r"Amounts expressed in (millions|thousands) of "
                                r"(United States dollars|Argentine pesos)", normal)
            if unidade is None:
                raise ValueError("RI PDF: declaração monetária não reconhecida")
            moeda_no_pdf = {"United States dollars": "USD", "Argentine pesos": "ARS"}[unidade[2]]
            escala_no_pdf = {"millions": Decimal(1000000), "thousands": Decimal(1000)}[unidade[1]]
            if (tabela.get("moeda") != moeda_no_pdf
                    or Decimal(str(tabela["escala"])) != escala_no_pdf):
                raise ValueError("RI PDF: moeda/escala do descritor diferem da declaração literal")
        if any(_n(a) not in normal for a in tabela["ancoras"]):
            raise ValueError("RI PDF: contexto, moeda ou escala não conferem")
        if (tabela.get("tipo") != "capital"
                and "consolidad" not in _n(tabela["ancoras"][0]).lower()
                and not (observado and "consolidated" in _n(tabela["ancoras"][0]).lower())):
            raise ValueError("RI PDF: demonstração sem contexto consolidado")
        cabecalho = _n(tabela["cabecalho_colunas"])
        if cabecalho not in normal:
            raise ValueError("RI PDF: ordem/identidade das colunas não conferem")
        colunas = tabela["colunas"]
        if observado and tabela.get("tipo") != "capital":
            periodos_catalogo = [(c.get("inicio"), c["fim"]) for c in colunas]
            if periodos_catalogo != _periodos_ingles(normal, tabela["demonstrativo"]):
                raise ValueError("RI PDF: intervalos/grão do descritor diferem da declaração literal")
        posicao = 0
        for coluna in colunas:
            fim = date.fromisoformat(coluna["fim"])
            inicio = date.fromisoformat(coluna["inicio"]) if coluna.get("inicio") else None
            if ((publicacao is not None and fim > publicacao)
                    or fim > as_of or (inicio and inicio > fim)):
                raise ValueError("RI PDF: período futuro/invertido")
            posicao_rotulo = cabecalho.find(_n(coluna["rotulo"]), posicao)
            if posicao_rotulo < 0:
                raise ValueError("RI PDF: período sem rótulo no cabeçalho")
            posicao = posicao_rotulo + len(_n(coluna["rotulo"]))
        # O primeiro cabeçalho de colunas delimita o corpo; rótulos da introdução,
        # índices ou textos narrativos anteriores não são linhas financeiras.
        corpo = normal.split(cabecalho, 1)[1]
        if observado and tabela.get("inicio_tabela"):
            inicio_tabela = _n(tabela["inicio_tabela"])
            if inicio_tabela not in corpo:
                raise ValueError("RI PDF: início do bloco financeiro ausente")
            corpo = corpo.split(inicio_tabela, 1)[1]
        if tabela.get("fim_tabela"):
            fim_tabela = _n(tabela["fim_tabela"])
            if fim_tabela not in corpo:
                raise ValueError("RI PDF: delimitação final da tabela ausente")
            corpo = corpo.split(fim_tabela, 1)[0]
        linhas = [_n(linha) for linha in texto.splitlines() if _n(linha) and _n(linha) in corpo]
        for item, regra in tabela["itens"].items():
            encontrados = []
            for rotulo in regra["rotulos"]:
                vetores = set()
                for linha in linhas:
                    m = re.fullmatch(re.escape(_n(rotulo)) + r"\s+(" + _NUMERO
                                     + r"(?:\s+" + _NUMERO + r")*)", linha)
                    if m:
                        celulas = re.findall(_NUMERO, m.group(1))
                        if len(celulas) != len(colunas):
                            raise ValueError("RI PDF: quantidade de colunas da linha não confere")
                        vetores.add(tuple(_valor(v) for v in celulas))
                # Subtotais com texto adicional não são substitutos do rótulo exato.
                if len(vetores) != 1:
                    encontrados = []
                    break
                encontrados.append(next(iter(vetores)))
            if not encontrados:
                continue
            for idx, coluna in enumerate(colunas):
                valores = [v[idx] for v in encontrados]
                if any(v is None for v in valores):
                    continue
                valor = sum(valores) * Decimal(str(tabela["escala"]))
                if regra.get("sinal") == "modulo":
                    valor = abs(valor)
                elif regra.get("sinal") == "despesa":
                    valor = -abs(valor)
                elif regra.get("sinal", "original") != "original":
                    raise ValueError("RI PDF: transformação de sinal desconhecida")
                inicio = pd.Timestamp(coluna["inicio"]) if coluna.get("inicio") else pd.NaT
                fim = pd.Timestamp(coluna["fim"])
                dias = (fim - inicio).days + 1 if pd.notna(inicio) else 0
                registro = {
                    "entidade": "RI:" + documento["issuer_id"],
                    "demonstrativo": tabela["demonstrativo"], "item": item,
                    "period_start": inicio, "period_end": fim, "value": float(valor),
                    "currency": tabela.get("moeda"),
                    "received_date": (pd.Timestamp(recebido_em.astimezone(UTC))
                                      if observado and recebido_em is not None else pd.Timestamp(publicacao)),
                    "version": 1, "documento": documento["documento"],
                    "url": documento["url"] + f"#page={tabela['pagina']}",
                    "consolidado": True, "anual": 350 <= dias <= 380,
                    "pit_estimado": False,
                    "nota": f"RI PDF; página física {tabela['pagina']}; coluna {idx + 1} "
                            f"({coluna['rotulo']}); rótulos: " + " + ".join(regra["rotulos"])
                            + (f"; escala {tabela['escala']}; recepção observada; publicação primária desconhecida; "
                               "descritor vinculado ao SHA-256" if observado else
                               f"; escala {tabela['escala']}; publicação conferida na página {prova['pagina']}; "
                               "catálogo vinculado ao SHA-256"),
                }
                if observado:
                    registro.update({"disponibilidade_tipo": "recepcao_observada",
                                     "disponivel_desde": recebido_em,
                                     "data_recebimento_documento": None,
                                     "data_publicacao_primaria": None})
                saida.append(registro)
    return pd.DataFrame(saida, columns=COLUNAS + (COLUNAS_OBSERVADAS if observado else []))


__all__ = ["documentos_ri", "fatos_pdf_ri"]
