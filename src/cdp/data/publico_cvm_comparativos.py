"""Ledger opcional de células CVM reportadas; não é entrada financeira ou seleção PIT.

Mantém os lexemas e ambos os exercícios. Contexto externo prova apenas ligação a
bytes/localizadores; não certifica política financeira, homogeneidade ou perímetro.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import re
import zipfile
from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlsplit

import pandas as pd
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .publico_arquivo import RegistroArquivo
from .security_master import CVM_DOC_BASE_URL, normalize_text

COLUNAS_EXERCICIOS = [
    "entidade",
    "demonstrativo",
    "item_reportado",
    "period_start",
    "period_end",
    "referencia_documento",
    "version_literal",
    "ordem_exercicio",
    "consolidado",
    "moeda_literal",
    "escala_literal",
    "valor_reportado",
    "id_doc",
    "url_filing",
    "data_recebimento_documento",
    "source_sha256",
    "source_url",
    "recibo_origem",
    "localizador",
    "raw",
    "indice_documento",
    "contexto_politica",
    "disponivel_desde",
    "data_publicacao_primaria",
    "conflito_reportado",
    "fontes_em_conflito",
]
_TABELAS = ("DRE", "BPA", "BPP", "DFC_MD", "DFC_MI", "DVA")
_FLUXOS = {"DRE", "DFC_MD", "DFC_MI", "DVA"}


@dataclass(frozen=True)
class ContextoPoliticaCVM:
    """Ligação documental explícita, sem rótulo declaratório de política financeira.

    Cada célula tem source_sha256, membro, linha_csv_1_based e raw integral. O PDF
    é uma fonte separada, com páginas/âncoras observadas. Para RI, conteudo é PDF
    direto; para CVM, é o HTML recebido que incorpora o PDF, com recibo do HTML.
    """

    registro: RegistroArquivo
    conteudo: bytes
    ancoras: tuple[tuple[int, str], ...]
    celulas: tuple[dict, ...]


def _agora() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Recepção/corte exige datetime com fuso explícito")
    return value.astimezone(UTC)


def _registro(conteudo: bytes, registro: RegistroArquivo, fonte: str, corte: datetime) -> datetime:
    if not isinstance(conteudo, bytes):
        raise ValueError("Corpo de origem exige bytes")
    if not isinstance(registro, RegistroArquivo) or registro.fonte != fonte:
        raise ValueError("Registro de origem incompatível")
    _utc(registro.data_coleta)  # consciência temporal antes de normalizar precisão
    limite = _utc(registro.limite_captura)
    if registro.bytes != len(conteudo) or registro.sha256 != hashlib.sha256(conteudo).hexdigest():
        raise ValueError("Bytes/SHA não conferem com o registro de origem")
    if not registro.url or not registro.url.startswith("https://"):
        raise ValueError("Origem exige URL pública HTTPS registrada")
    if limite > min(_utc(corte), _utc(_agora())):
        raise ValueError("Recepção observada posterior ao corte ou relógio atual")
    return limite


def _civil(value: str | None, *, opcional: bool = False) -> str | None:
    if not value and opcional:
        return None
    try:
        parsed = date.fromisoformat(value or "")
    except (TypeError, ValueError) as exc:
        raise ValueError("Data civil CVM inválida") from exc
    if parsed.isoformat() != value:
        raise ValueError("Data civil CVM deve ser ISO literal")
    return value


def _linhas(body: bytes):
    reader = csv.DictReader(io.StringIO(body.decode("latin-1")), delimiter=";")
    for row in reader:
        if None in row:
            raise ValueError("Linha CVM com campos excedentes")
        yield reader.line_num, {key: value if value != "" else None for key, value in row.items()}


def _numero(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Lexema monetário CVM inválido") from exc
    if not result.is_finite():
        raise ValueError("Lexema monetário CVM não finito")
    return result


def _parametros_cvm(url: str, path: str, keys: set[str], *, schemes=("https",)) -> dict:
    if not isinstance(url, str) or not url.isascii() or any(c.isspace() for c in url):
        raise ValueError("URL documental CVM inválida")
    parsed = urlsplit(url)
    if (
        parsed.scheme not in schemes
        or parsed.netloc != "www.rad.cvm.gov.br"
        or parsed.path != path
        or parsed.fragment
    ):
        raise ValueError("Rota documental CVM incompatível")
    raw_pairs = [field.partition("=") for field in parsed.query.split("&")]
    raw_params = {name: value for name, _, value in raw_pairs}
    if (
        any(not separator for _, separator, _ in raw_pairs)
        or len(raw_params) != len(raw_pairs)
        or set(raw_params) != keys
        or not all(raw_params.values())
    ):
        raise ValueError("Parâmetros documentais CVM exigem nomes literais únicos e completos")
    try:
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise ValueError("Parâmetros documentais CVM inválidos") from exc
    params = dict(pairs)
    if len(params) != len(pairs) or set(params) != keys or not all(params.values()):
        raise ValueError("Parâmetros documentais CVM duplicados, ausentes ou desconhecidos")
    identity_keys = keys - {"Hash", "RelatorioRevisaoEspecial"}
    if any(raw_params[name] != params[name] for name in identity_keys):
        raise ValueError("Identidade documental CVM exige lexemas brutos literais")
    if not re.fullmatch(r"[1-9][0-9]*", params["NumeroSequencialDocumento"]):
        raise ValueError("NSD CVM exige inteiro ASCII positivo literal")
    return params


class _PDFIncorporado(HTMLParser):
    """Lê somente o input literal; nenhum script ou recurso externo é executado."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag != "input" or not any(
            key in {"id", "name"} and value == "hdnConteudoArquivo" for key, value in attrs
        ):
            return
        data = dict(attrs)
        if (
            len(data) != len(attrs)
            or data.get("type") != "hidden"
            or data.get("id") != "hdnConteudoArquivo"
            or data.get("name") != "hdnConteudoArquivo"
            or not data.get("value")
        ):
            raise ValueError("Input PDF CVM incompleto ou ambíguo")
        self.values.append(data["value"])


def _pdf_cvm(conteudo: bytes, url: str) -> tuple[bytes, dict]:
    params = _parametros_cvm(
        url,
        "/ENET/frmExibirArquivoFRE.aspx",
        {"NumeroSequencialDocumento", "CodigoGrupo", "CodigoQuadro", "Tipo",
         "RelatorioRevisaoEspecial", "CodTipoDocumento", "Hash"},
    )
    if (
        params["CodigoGrupo"] != "412"
        or params["CodigoQuadro"] != "0"
        or params["Tipo"] != "PDF"
        or params["CodTipoDocumento"] != "4"
    ):
        raise ValueError("Perfil de notas DFP CVM incompatível")
    parser = _PDFIncorporado()
    try:
        parser.feed(conteudo.decode("utf-8"))
        parser.close()
        if len(parser.values) != 1:
            raise ValueError("HTML CVM exige exatamente um input PDF")
        pdf = base64.b64decode(parser.values[0], validate=True)
        if base64.b64encode(pdf).decode("ascii") != parser.values[0]:
            raise ValueError("Base64 PDF CVM não canônica")
    except (UnicodeError, binascii.Error) as exc:
        raise ValueError("HTML/Base64 PDF CVM inválido") from exc
    if not pdf.startswith(b"%PDF-") or not pdf.rstrip().endswith(b"%%EOF"):
        raise ValueError("Corpo derivado CVM não é PDF completo")
    return pdf, {
        "resposta_HTTP_sha256": hashlib.sha256(conteudo).hexdigest(),
        "resposta_HTTP_bytes": len(conteudo),
        "numero_sequencial_documento": params["NumeroSequencialDocumento"],
        "derivacao": {
            "localizador": "input#hdnConteudoArquivo[name=hdnConteudoArquivo].value",
            "metodo": "HTMLParser; Base64 estrita canônica; sem alteração dos bytes PDF",
            "document_bytes": len(pdf),
            "parametros_url": params,
        },
    }


def _documento_politica(contexto: ContextoPoliticaCVM, corte: datetime) -> dict:
    if (
        not isinstance(contexto, ContextoPoliticaCVM)
        or not contexto.ancoras
        or not contexto.celulas
    ):
        raise ValueError("Contexto documental parcial")
    if not isinstance(contexto.registro, RegistroArquivo) or contexto.registro.fonte not in {"RI", "CVM"}:
        raise ValueError("Registro de contexto documental incompatível")
    limite = _registro(contexto.conteudo, contexto.registro, contexto.registro.fonte, corte)
    body, derivation = contexto.conteudo, {}
    if contexto.registro.fonte == "CVM":
        body, derivation = _pdf_cvm(body, contexto.registro.url)
    try:
        pdf = PdfReader(io.BytesIO(body), strict=True)
        if pdf.is_encrypted:
            raise ValueError("PDF criptografado não é contexto público legível")
        anchors = []
        for pagina, ancora in contexto.ancoras:
            if (
                isinstance(pagina, bool)
                or not isinstance(pagina, int)
                or not 1 <= pagina <= len(pdf.pages)
            ):
                raise ValueError("Página física PDF inválida")
            if not isinstance(ancora, str) or not ancora.strip():
                raise ValueError("Âncora documental ausente")
            text = " ".join((pdf.pages[pagina - 1].extract_text() or "").split())
            normalized = " ".join(ancora.split())
            if normalized not in text:
                raise ValueError("Âncora não encontrada no corpo PDF")
            anchors.append(
                {"pagina_fisica_1_based": pagina, "ancora": ancora, "texto_pagina_extraido": text}
            )
    except (KeyError, TypeError, IndexError, PdfReadError) as exc:
        raise ValueError("Contexto PDF inválido") from exc
    return {
        "document_sha256": hashlib.sha256(body).hexdigest(),
        "url": contexto.registro.url,
        "recibo": contexto.registro.como_dict(),
        "disponivel_desde": limite.isoformat(),
        "ancoras": anchors,
        "alcance": "ligação documental; não aprovação financeira",
        "perimetro_economico_constante": None,
        "publicacao_primaria_UTC": None,
        **derivation,
    }


def _vincular(
    rows: list[dict], contextos: Sequence[ContextoPoliticaCVM], corte: datetime, *, doc: str
):
    by_cell = {
        (r["source_sha256"], r["localizador"]["membro"], r["localizador"]["linha_csv_1_based"]): r
        for r in rows
    }
    for contexto in contextos:
        if (
            isinstance(contexto, ContextoPoliticaCVM)
            and isinstance(contexto.registro, RegistroArquivo)
            and contexto.registro.fonte == "CVM"
            and doc != "DFP"
        ):
            raise ValueError("Notas anuais CVM exigem origem documental DFP")
        document = _documento_politica(contexto, corte)
        for cell in contexto.celulas:
            if not isinstance(cell, dict) or set(cell) != {
                "source_sha256",
                "membro",
                "linha_csv_1_based",
                "raw",
            }:
                raise ValueError("Identidade de célula documental incompleta")
            key = (cell["source_sha256"], cell["membro"], cell["linha_csv_1_based"])
            row = by_cell.get(key)
            if row is None or row["raw"] != cell["raw"]:
                raise ValueError("Contexto contradiz origem/grão/lexema da célula CVM")
            if contexto.registro.fonte == "CVM":
                params = _parametros_cvm(
                    row["url_filing"],
                    "/ENETCONSULTA/frmDownloadDocumento.aspx",
                    {"CodigoInstituicao", "NumeroSequencialDocumento"},
                    schemes=("http", "https"),
                )
                nsd = document["numero_sequencial_documento"]
                if (
                    row["id_doc"] != nsd
                    or params["NumeroSequencialDocumento"] != nsd
                    or params["CodigoInstituicao"] != "1"
                ):
                    raise ValueError("Notas CVM não pertencem ao mesmo NSD da célula/filing")
            if row["contexto_politica"] is not None:
                raise ValueError("Mais de um contexto declarado para a mesma célula")
            row["contexto_politica"] = deepcopy({**document, "celula_CVM": cell})
            row["disponivel_desde"] = max(
                datetime.fromisoformat(row["disponivel_desde"]),
                datetime.fromisoformat(document["disponivel_desde"]),
            ).isoformat()


def expor_conflitos(exercicios: Sequence[pd.DataFrame]) -> pd.DataFrame:
    """Conflito de lexemas no mesmo grão literal; não compara bases econômicas.

    Conserva todas as linhas, inclusive duplicatas e valores ausentes. Não escolhe
    versão, ordem, documento ou fonte para consumo financeiro.
    """
    rows = [deepcopy(dict(row)) for frame in exercicios for row in frame.to_dict("records")]
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        key = tuple(
            row[c]
            for c in (
                "entidade",
                "demonstrativo",
                "item_reportado",
                "period_start",
                "period_end",
                "consolidado",
                "moeda_literal",
                "escala_literal",
            )
        )
        groups.setdefault(key, []).append(row)
    for group in groups.values():
        values = {_numero(r["valor_reportado"]) for r in group if r["valor_reportado"] is not None}
        conflict = len(values) > 1
        origins = (
            [
                {
                    "source_sha256": r["source_sha256"],
                    "localizador": r["localizador"],
                    "referencia_documento": r["referencia_documento"],
                    "version_literal": r["version_literal"],
                    "ordem_exercicio": r["ordem_exercicio"],
                    "valor_reportado": r["valor_reportado"],
                }
                for r in group
            ]
            if conflict
            else []
        )
        for row in group:
            row["conflito_reportado"] = conflict
            row["fontes_em_conflito"] = origins
    return pd.DataFrame(rows, columns=COLUNAS_EXERCICIOS, dtype=object)


def conservar_exercicios(
    conteudo: bytes,
    doc: str,
    ano: int,
    cnpjs: Iterable[str] | None,
    registro: RegistroArquivo,
    conhecimento_ate: datetime,
    contextos_politica: Sequence[ContextoPoliticaCVM] = (),
) -> pd.DataFrame:
    """Extrai células ÚLTIMO/PENÚLTIMO com proveniência explícita e nenhum cálculo de produto."""
    doc = str(doc).upper()
    if doc not in {"DFP", "ITR"} or isinstance(ano, bool) or not isinstance(ano, int):
        raise ValueError("Tipo/ano de documento CVM inválido")
    cutoff = _utc(conhecimento_ate)
    available = _registro(conteudo, registro, "CVM", cutoff)
    filename = f"{doc.lower()}_cia_aberta_{ano}"
    if (
        registro.chave != f"CVM/{doc}/{filename}.zip"
        or registro.url != f"{CVM_DOC_BASE_URL}/{doc}/DADOS/{filename}.zip"
    ):
        raise ValueError("Registro/rota CVM não corresponde ao documento/ano")
    wanted = None if cnpjs is None else {str(c).strip() for c in cnpjs}
    rows = []
    with zipfile.ZipFile(io.BytesIO(conteudo)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Membro duplicado no ZIP CVM")
        index = {}
        indices = [n for n in names if n.lower().endswith(f"{filename}.csv")]
        if len(indices) > 1:
            raise ValueError("Índice ambíguo no ZIP CVM")
        if indices:
            for _, row in _linhas(archive.read(indices[0])):
                if wanted is not None and row.get("CNPJ_CIA") not in wanted:
                    continue
                key = (row.get("CNPJ_CIA"), row.get("DT_REFER"), row.get("VERSAO"))
                if key in index and index[key] != row:
                    raise ValueError("Índice CVM contraditório para entidade/referência/versão")
                index[key] = row
        for table in _TABELAS:
            for kind in ("con", "ind"):
                suffix = f"{doc.lower()}_cia_aberta_{table}_{kind}_{ano}.csv".lower()
                members = [n for n in names if n.lower().endswith(suffix)]
                if len(members) > 1:
                    raise ValueError("Demonstração ambígua no ZIP CVM")
                if not members:
                    continue
                name = members[0]
                body = archive.read(name)
                body_sha = hashlib.sha256(body).hexdigest()
                for line, raw in _linhas(body):
                    entity = raw.get("CNPJ_CIA")
                    if wanted is not None and entity not in wanted:
                        continue
                    order = normalize_text(raw.get("ORDEM_EXERC") or "")
                    if order not in {"ultimo", "penultimo"}:
                        continue
                    version = raw.get("VERSAO")
                    if not entity or not version or not version.isdigit() or int(version) < 1:
                        raise ValueError("Identidade/versão CVM ausente ou inválida")
                    reference = _civil(raw.get("DT_REFER"))
                    end = _civil(raw.get("DT_FIM_EXERC"))
                    start = _civil(raw.get("DT_INI_EXERC"), opcional=table not in _FLUXOS)
                    if (
                        reference[:4] != str(ano)
                        or end > reference
                        or (start is not None and start > end)
                    ):
                        raise ValueError("Período/ref CVM incompatível")
                    for required in ("CD_CONTA", "MOEDA", "ESCALA_MOEDA"):
                        if not raw.get(required):
                            raise ValueError("Rubrica/moeda/escala CVM ausente")
                    value = raw.get("VL_CONTA")
                    _numero(value)  # valida lexema, sem converter ausência em zero
                    idx = index.get((entity, reference, version))
                    receipt_civil = _civil(idx.get("DT_RECEB"), opcional=True) if idx else None
                    rows.append(
                        {
                            "entidade": entity,
                            "demonstrativo": table,
                            "item_reportado": raw["CD_CONTA"],
                            "period_start": start,
                            "period_end": end,
                            "referencia_documento": reference,
                            "version_literal": version,
                            "ordem_exercicio": raw["ORDEM_EXERC"],
                            "consolidado": kind == "con",
                            "moeda_literal": raw["MOEDA"],
                            "escala_literal": raw["ESCALA_MOEDA"],
                            "valor_reportado": value,
                            "id_doc": idx.get("ID_DOC") if idx else None,
                            "url_filing": idx.get("LINK_DOC") if idx else None,
                            "data_recebimento_documento": receipt_civil,
                            "source_sha256": registro.sha256,
                            "source_url": registro.url,
                            "recibo_origem": registro.como_dict(),
                            "localizador": {
                                "membro": name,
                                "membro_sha256": body_sha,
                                "linha_csv_1_based": line,
                            },
                            "raw": raw,
                            "indice_documento": idx,
                            "contexto_politica": None,
                            "disponivel_desde": available.isoformat(),
                            "data_publicacao_primaria": None,
                        }
                    )
    _vincular(rows, contextos_politica, cutoff, doc=doc)
    return expor_conflitos([pd.DataFrame(rows, dtype=object)])
