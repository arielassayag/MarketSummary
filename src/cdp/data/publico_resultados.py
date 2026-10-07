"""Fatos RI e eventos de resultado: bytes primários → catálogo autenticável.

O catálogo de estrutura não contém valores financeiros. Páginas, títulos, colunas,
rótulos e provas são conferidos antes da extração. A disponibilidade sem prova de
publicação é a primeira captura destes mesmos bytes, nunca a assinatura do auditor.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader

from .publico_arquivo import Arquivo, data_local
from .publico_ri import _NUMERO, _n, _valor

CATALOGO = Path(__file__).resolve().parents[3] / "configs/cdp/resultado_evidencias.json"
SCHEMA = "cdp.resultado_evidencias/v1"
EXTRATOR = "ri_pdf_resultados/1"


def texto_json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def hash_obj(v: Any) -> str:
    return hashlib.sha256(texto_json(v).encode()).hexdigest()


def instante(v: str | datetime) -> datetime:
    d = v if isinstance(v, datetime) else datetime.fromisoformat(v)
    if d.tzinfo is None:
        raise ValueError("resultado: instante de conhecimento exige fuso explícito")
    return d.astimezone(UTC)


def extrair(
    conteudo: bytes, doc: Mapping[str, Any], first_capture: datetime, conhecimento_ate: datetime
) -> dict[str, Any]:
    """Extrai sem rede; hash, entidade/base/unidade/períodos e provas são obrigatórios."""
    sha = hashlib.sha256(conteudo).hexdigest()
    if sha != doc["sha256"]:
        raise ValueError("resultado RI: SHA do bruto diverge do catálogo")
    captura, corte = instante(first_capture), instante(conhecimento_ate)
    pdf = PdfReader(io.BytesIO(conteudo), strict=True)
    if pdf.is_encrypted:
        raise ValueError("resultado RI: PDF criptografado")
    paginas: dict[int, str] = {}

    def pagina(n: int) -> str:
        if not 1 <= n <= len(pdf.pages):
            raise ValueError("resultado RI: página ausente")
        if n not in paginas:
            paginas[n] = _n(pdf.pages[n - 1].extract_text() or "")
        return paginas[n]

    disponibilidade = captura
    pub = doc.get("publicacao")
    if pub:
        if _n(pub["texto"]) not in pagina(int(pub["pagina"])):
            raise ValueError("resultado RI: prova de publicação ausente")
        # Data declarada não prova hora: só no fim do dia civil da fonte.
        disponibilidade = instante(pub["disponivel_desde"])
    if disponibilidade > corte:
        return {"documentos": [], "fatos": [], "provas": []}
    documento = {
        "documento_id": sha,
        "sha256": sha,
        "url": doc["url"],
        "first_capture": captura.isoformat(),
        "disponivel_desde": disponibilidade.isoformat(),
        "publicacao_prova": pub,
        "extrator": EXTRATOR,
    }
    fatos, provas = [], []
    for prova in doc.get("provas", []):
        t = pagina(prova["pagina"])
        for ancora in prova["ancoras"]:
            if _n(ancora) not in t:
                raise ValueError("resultado RI: prova textual ausente: " + ancora)
        dado = {
            "documento_id": sha,
            "pagina": prova["pagina"],
            "ancoras": prova["ancoras"],
            "papel": prova["papel"],
            "disponivel_desde": disponibilidade.isoformat(),
        }
        if "data_regex" in prova:
            m = re.search(prova["data_regex"], t)
            if not m:
                raise ValueError("resultado RI: data do evento ausente")
            meses = {
                "enero": 1,
                "febrero": 2,
                "marzo": 3,
                "abril": 4,
                "mayo": 5,
                "junio": 6,
                "julio": 7,
                "agosto": 8,
                "septiembre": 9,
                "octubre": 10,
                "noviembre": 11,
                "diciembre": 12,
            }
            dado["data_economica"] = datetime(int(m[3]), meses[m[2]], int(m[1])).date().isoformat()
        dado["prova_id"] = hash_obj({k: v for k, v in dado.items() if k != "disponivel_desde"})
        provas.append(dado)
    for tabela in doc.get("tabelas", []):
        t = pagina(tabela["pagina"])
        for a in tabela["ancoras"]:
            if _n(a) not in t:
                raise ValueError("resultado RI: título/base/unidade/cabeçalho divergente: " + a)
        cab = _n(tabela["cabecalho"])
        if t.count(cab) != 1:
            raise ValueError("resultado RI: cabeçalho ausente ou ambíguo")
        corpo = t.split(cab, 1)[1].replace("$ ", "$")
        if tabela.get("fim_tabela"):
            corpo = corpo.split(_n(tabela["fim_tabela"]), 1)[0]
        ncols = len(tabela["colunas"])
        for regra in tabela["itens"]:
            celulas = []
            for rotulo in regra["rotulos"]:
                matches = re.findall(
                    re.escape(_n(rotulo))
                    + r"\s+"
                    + r"\s+".join(["(" + _NUMERO + ")"] * ncols)
                    + r"(?=\s|$)",
                    corpo.split(_n(regra["fim_busca"]), 1)[0] if regra.get("fim_busca") else corpo,
                )
                if len(matches) != 1:
                    raise ValueError("resultado RI: linha ausente/duplicada: " + rotulo)
                # re.findall retorna string com um único grupo, tupla com dois ou mais.
                capturados = (matches[0],) if ncols == 1 else matches[0]
                celulas.append([_valor(x.replace("$", "")) for x in capturados])
            for j, col in enumerate(tabela["colunas"]):
                inicio = datetime.fromisoformat(col["inicio"]).date()
                fim = datetime.fromisoformat(col["fim"]).date()
                dias = (fim - inicio).days + 1
                lo, hi = {"A": (350, 380), "TTM": (350, 380), "H1": (160, 200), "Q": (60, 105)}[
                    col["freq"]
                ]
                if not lo <= dias <= hi:
                    raise ValueError("resultado RI: duração incompatível com a frequência")
                valores = [c[j] for c in celulas]
                v = None if any(x is None for x in valores) else sum(valores, Decimal(0))
                contexto = {
                    "issuer_id": doc["issuer_id"],
                    "item": regra["item"],
                    "inicio": col["inicio"],
                    "fim": col["fim"],
                    "freq": col["freq"],
                    "moeda": tabela["moeda"],
                    "base": "consolidado",
                    "documento_id": sha,
                    "pagina": tabela["pagina"],
                    "rotulos": regra["rotulos"],
                    "coluna": j,
                    "escala": str(tabela["escala"]),
                    "coeficiente_fonte": str(regra.get("coeficiente", 1)),
                    "conceito": regra.get("conceito", regra["item"]),
                    "versao": int(doc.get("versao", 1)),
                }
                fato = {
                    **contexto,
                    "fato_id": hash_obj(contexto),
                    "valor_bruto": None if v is None else str(v),
                    "valor": None
                    if v is None
                    else str(
                        v
                        * Decimal(str(tabela["escala"]))
                        * Decimal(str(regra.get("coeficiente", 1)))
                    ),
                    "disponivel_desde": disponibilidade.isoformat(),
                    "url": doc["url"],
                }
                if datetime.fromisoformat(col["fim"]).date() > corte.date():
                    raise ValueError("resultado RI: competência futura")
                fatos.append(fato)
    return {"documentos": [documento], "fatos": fatos, "provas": provas}


def construir(
    partes: Sequence[Mapping[str, Any]], estrutura: Mapping[str, Any], conhecimento_ate: datetime
) -> dict[str, Any]:
    """Catálogo versionado, binds primários e TTM anual+H1−H1; divergências são recusadas."""
    cat = {
        "schema": SCHEMA,
        "extrator": EXTRATOR,
        "estrutura_sha256": hash_obj(estrutura),
        "conhecimento_ate": instante(conhecimento_ate).isoformat(),
        "documentos": [],
        "fatos": [],
        "provas": [],
        "eventos": [],
        "bindings": [],
        "escopo": "alienações de controle explicitamente documentadas; cobertura parcial",
        "resultado_recorrente_certificado": False,
    }
    for campo in ("documentos", "fatos", "provas"):
        vistos = {}
        chave = {"documentos": "documento_id", "fatos": "fato_id", "provas": "prova_id"}[campo]
        for parte in partes:
            for x in parte[campo]:
                anterior = vistos.get(x[chave])
                if anterior:
                    variaveis = {"first_capture", "disponivel_desde", "url", "urls", "arquivo"}
                    if {k: v for k, v in anterior.items() if k not in variaveis} != {
                        k: v for k, v in x.items() if k not in variaveis
                    }:
                        raise ValueError("resultado: fato/prova conflitante")
                    unidos = dict(anterior)
                    unidos["disponivel_desde"] = min(
                        anterior["disponivel_desde"], x["disponivel_desde"]
                    )
                    if "first_capture" in x:
                        unidos["first_capture"] = min(anterior["first_capture"], x["first_capture"])
                    urls = sorted(
                        set(
                            [
                                u
                                for u in [
                                    anterior.get("url"),
                                    x.get("url"),
                                    *anterior.get("urls", []),
                                    *x.get("urls", []),
                                ]
                                if u
                            ]
                        )
                    )
                    if urls:
                        unidos["urls"] = urls
                        unidos["url"] = urls[0]
                    vistos[x[chave]] = unidos
                else:
                    vistos[x[chave]] = x
        cat[campo] = sorted(vistos.values(), key=lambda x: x[chave])
    for ponte in estrutura.get("pontes_subtotal", []):
        fs = [f for f in cat["fatos"] if f["documento_id"] == ponte["documento_id"]]
        for total in [f for f in fs if f["item"] == ponte["total"]]:
            soma = Decimal(0)
            for item, coef in ponte["componentes"].items():
                linhas = [
                    f
                    for f in fs
                    if f["item"] == item
                    and f["inicio"] == total["inicio"]
                    and f["fim"] == total["fim"]
                    and f["moeda"] == total["moeda"]
                    and f["base"] == total["base"]
                    and f["valor"] is not None
                ]
                if len(linhas) != 1:
                    raise ValueError("resultado: componente do subtotal ausente/ambíguo")
                soma += Decimal(linhas[0]["valor"]) * Decimal(str(coef))
            if total["valor"] is None or soma != Decimal(total["valor"]):
                raise ValueError("resultado: identidade do subtotal primário divergente")
    for cfg in estrutura.get("eventos", []):
        selecao = cfg["medida_periodo"]
        medidas = [
            f
            for f in cat["fatos"]
            if f["issuer_id"] == cfg["issuer_id"]
            and f["item"] == cfg["medida_item"]
            and f["documento_id"] in cfg["medida_documentos"]
            and all(f[k] == selecao[k] for k in ("inicio", "fim", "freq"))
            and f["valor"] is not None
        ]
        provas = [p for p in cat["provas"] if p["documento_id"] in cfg["documentos_prova"]]
        if not medidas or set(cfg["papeis_prova"]) - {p["papel"] for p in provas}:
            continue
        versao = max(int(f.get("versao", 1)) for f in medidas)
        medidas = [f for f in medidas if int(f.get("versao", 1)) == versao]
        if len(medidas) != 1:
            raise ValueError("resultado: versões da medida conflitantes")
        m = medidas[0]
        provas_medida = [p for p in provas if p["documento_id"] == m["documento_id"]]
        if set(cfg["papeis_prova"]) <= {p["papel"] for p in provas_medida}:
            provas = provas_medida
        datas = {p["data_economica"] for p in provas if p.get("data_economica")}
        if len(datas) != 1:
            raise ValueError("resultado: data econômica do evento ausente/conflitante")
        data_economica = next(iter(datas))
        if not m["inicio"] <= data_economica <= m["fim"]:
            raise ValueError("resultado: evento fora da competência da medida primária")
        evento = {
            "evento_id": hash_obj({"tipo": cfg["tipo"], "identidade": cfg["identidade"]}),
            "issuer_id": cfg["issuer_id"],
            "tipo": cfg["tipo"],
            "identidade": cfg["identidade"],
            "reconhecimento_inicio": data_economica,
            "reconhecimento_fim": m["fim"],
            "medida_fato_id": m["fato_id"],
            "contribuicao_pre_imposto": m["valor"],
            "moeda": m["moeda"],
            "base": m["base"],
            "disponivel_desde": max(
                [m["disponivel_desde"], *[p["disponivel_desde"] for p in provas]]
            ),
            "provas": [p["prova_id"] for p in provas],
            "imposto_evento": None,
            "lucro_liquido_ajustado": None,
            "eps_ajustado": None,
            "mudanca_perimetro": True,
            "cfo_ajuste_adicional": "0",
        }
        cat["eventos"].append(evento)
        ebs = [
            f
            for f in cat["fatos"]
            if f["issuer_id"] == cfg["issuer_id"]
            and f["item"] == "ebit"
            and f["documento_id"] == m["documento_id"]
            and f["inicio"] == m["inicio"]
            and f["fim"] == m["fim"]
        ]
        for eb in ebs:
            cat["bindings"].append(
                {
                    "evento_id": evento["evento_id"],
                    "fato_ebit_id": eb["fato_id"],
                    "medida_fato_id": m["fato_id"],
                    "coeficiente": "1",
                    "provas": evento["provas"],
                }
            )
    # Derivação só entre fatos semestrais e anual de contexto idêntico, nunca saldo de balanço.
    grupos = {}
    for f in cat["fatos"]:
        k = (f["issuer_id"], f["item"], f["freq"], f["inicio"], f["fim"], f["moeda"], f["base"])
        grupos.setdefault(k, []).append(f)
    primarios = []
    for fs in grupos.values():
        versao = max(int(f.get("versao", 1)) for f in fs)
        ativos = [f for f in fs if int(f.get("versao", 1)) == versao]
        if len(ativos) != 1:
            raise ValueError("resultado: republicação conflitante sem versão distinta")
        primarios += ativos
    for atual in primarios:
        if atual["freq"] != "H1" or atual["valor"] is None:
            continue
        pares = [
            f
            for f in primarios
            if f["item"] == atual["item"]
            and f["issuer_id"] == atual["issuer_id"]
            and f["moeda"] == atual["moeda"]
            and f["base"] == atual["base"]
            and f["valor"] is not None
        ]
        a = [
            f
            for f in pares
            if f["freq"] == "A"
            and pd.Timestamp(f["fim"]) + pd.Timedelta(days=1) == pd.Timestamp(atual["inicio"])
        ]
        if len(a) != 1:
            continue
        yp = [
            f
            for f in pares
            if f["freq"] == "H1"
            and f["inicio"] == a[0]["inicio"]
            and pd.Timestamp(f["fim"]) + pd.DateOffset(years=1) == pd.Timestamp(atual["fim"])
            and pd.Timestamp(f["inicio"]) + pd.DateOffset(years=1) == pd.Timestamp(atual["inicio"])
        ]
        if len(yp) != 1:
            continue
        componentes = [
            {"fato_id": f["fato_id"], "coeficiente": str(c)}
            for f, c in ((a[0], 1), (atual, 1), (yp[0], -1))
        ]
        v = Decimal(a[0]["valor"]) + Decimal(atual["valor"]) - Decimal(yp[0]["valor"])
        inicio = (pd.Timestamp(yp[0]["fim"]) + pd.Timedelta(days=1)).date().isoformat()
        dias = (pd.Timestamp(atual["fim"]) - pd.Timestamp(inicio)).days + 1
        if not 350 <= dias <= 380:
            continue
        publicados = [f for f in pares if f["freq"] == "TTM" and f["fim"] == atual["fim"]]
        if publicados and any(
            Decimal(f["valor"]) != v or f["inicio"] != inicio for f in publicados
        ):
            raise ValueError("resultado: TTM derivado diverge do TTM reportado")
        f = {
            **atual,
            "freq": "TTM",
            "inicio": inicio,
            "valor": str(v),
            "valor_bruto": None,
            "componentes": componentes,
            "disponivel_desde": max(
                f["disponivel_desde"] for f in (a[0], atual, yp[0], *publicados)
            ),
            "documento_id": None,
            "pagina": None,
            "rotulos": [],
            "conceito": atual["conceito"],
            "ttm_reportado_fato_ids": [p["fato_id"] for p in publicados],
        }
        f["fato_id"] = hash_obj(
            {"componentes": componentes, "inicio": inicio, "fim": f["fim"], "item": f["item"]}
        )
        cat["fatos"].append(f)
    cat["catalogo_sha256"] = hash_obj(cat)
    return cat


def tabela_fatos(cat: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    fatos = {f["fato_id"]: f for f in cat["fatos"]}
    documentos = {d["documento_id"]: d for d in cat["documentos"]}

    def coleta(f, caminho=()):
        if f["fato_id"] in caminho:
            raise ValueError("resultado: componentes cíclicos")
        dependencias = [c["fato_id"] for c in f.get("componentes", [])]
        dependencias += f.get("ttm_reportado_fato_ids", [])
        if dependencias:
            return max(coleta(fatos[i], (*caminho, f["fato_id"])) for i in dependencias)
        return documentos[f["documento_id"]]["first_capture"]

    derivados = {
        (f["issuer_id"], f["item"], f["fim"]) for f in cat["fatos"] if f.get("componentes")
    }
    revisoes = {}
    for f in cat["fatos"]:
        k = (f["issuer_id"], f["item"], f["freq"], f["fim"])
        revisoes[k] = max(revisoes.get(k, 0), int(f.get("versao", 1)))
    for f in cat["fatos"]:
        if int(f.get("versao", 1)) != revisoes[(f["issuer_id"], f["item"], f["freq"], f["fim"])]:
            continue
        if (
            f["valor"] is None
            or f["freq"] == "H1"
            or f["item"]
            in {"ganho_alienacao_controle", "outros_ingressos", "despesas_operacionais"}
        ):
            continue
        if (
            f["freq"] == "TTM"
            and not f.get("componentes")
            and (f["issuer_id"], f["item"], f["fim"]) in derivados
        ):
            continue
        rows.append(
            {
                "issuer_id": f["issuer_id"],
                "demonstrativo": "DFC" if f["item"] in {"cfo", "capex", "d_a_dfc"} else "DRE",
                "freq": f["freq"],
                "period_start": f["inicio"],
                "period_end": f["fim"],
                "item": f["item"],
                "value": float(Decimal(f["valor"])),
                "currency": f["moeda"],
                "escala": 1,
                "consolidado": True,
                "fonte": "RI",
                "url": f["url"],
                "documento": "fato primário RI " + f["fato_id"],
                "data_publicacao": data_local(instante(f["disponivel_desde"])),
                "data_coleta": coleta(f),
                "sha256": f["documento_id"] or cat["catalogo_sha256"],
                "pit_estimado": False,
                "fato_resultado_id": f["fato_id"],
                "disponivel_desde": f["disponivel_desde"],
                "nota": "RI: catálogo de fatos e componentes autenticados "
                + cat["catalogo_sha256"],
            }
        )
    return pd.DataFrame(rows)


def coletar_resultados(
    issuer_ids: Sequence[str],
    *,
    arquivo: Arquivo,
    conhecimento_ate: datetime | None = None,
    http_get: Callable | None = None,
    estrutura: Mapping[str, Any] | None = None,
    exigir_captura: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    estrutura = dict(estrutura) if estrutura is not None else json.loads(CATALOGO.read_text())
    if estrutura.get("schema") != SCHEMA:
        raise ValueError("resultado: schema do catálogo estrutural desconhecido")
    estrutura_arquivo_sha256 = (
        hashlib.sha256(CATALOGO.read_bytes()).hexdigest()
        if estrutura == json.loads(CATALOGO.read_text())
        else None
    )
    capturas = []
    for doc in estrutura["documentos"]:
        if doc["issuer_id"] not in issuer_ids:
            continue
        chave = f"RI/resultados/{doc['issuer_id']}/{doc['sha256']}.pdf"

        def baixar(d=doc):
            if http_get is not None:
                r = http_get(d["url"])
                return r if isinstance(r, bytes) else r.content
            import requests

            r = requests.get(d["url"], timeout=45)
            r.raise_for_status()
            return r.content

        got = arquivo.obter(
            chave,
            "RI",
            doc["url"],
            baixar,
            ate=data_local(conhecimento_ate or datetime.now(UTC)),
            max_idade_dias=3650,
            validar=lambda b, d=doc: extrair(b, d, datetime.now(UTC), datetime.now(UTC)),
        )
        if got is None:
            continue
        mesma = [r.limite_captura if exigir_captura else r.data_coleta
                 for r in arquivo.registros() if r.sha256 == got[0].sha256]
        capturas.append((got[1], doc, min(mesma)))
    corte = instante(conhecimento_ate or datetime.now(UTC))
    partes = [extrair(b, d, c, corte) for b, d, c in capturas
              if not exigir_captura or instante(c) <= corte]
    for parte in partes:
        for d in parte["documentos"]:
            registros = [r for r in arquivo.registros() if r.sha256 == d["sha256"]]
            registro = min(registros, key=lambda r: (r.limite_captura if exigir_captura else r.data_coleta,
                                                     r.chave)) if registros else None
            d["arquivo"] = registro.como_dict() if registro else None
            if registro is not None and not exigir_captura:
                # Contrato .7: o envelope histórico sempre exportava segundos e
                # não tinha marcador, inclusive se ler um índice externo preciso.
                d["arquivo"].pop("precisao_temporal", None)
                d["arquivo"]["data_coleta"] = registro.data_coleta.astimezone(UTC).isoformat(timespec="seconds")
    cat = construir(partes, estrutura, corte)
    cat.pop("catalogo_sha256")
    cat["estrutura_json"] = texto_json(estrutura)
    cat["estrutura_arquivo_sha256"] = estrutura_arquivo_sha256
    cat["catalogo_sha256"] = hash_obj(cat)
    if arquivo.falhas:
        cat.pop("catalogo_sha256")
        cat["falhas_coleta"] = list(arquivo.falhas)
        cat["catalogo_sha256"] = hash_obj(cat)
    return tabela_fatos(cat), cat
