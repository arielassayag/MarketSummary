"""DADOS SIMULADOS: arquivos novos em tmp; nenhum insumo histórico ou coleta externa."""

import io
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from cdp.data import make_synthetic_market
from cdp.data.ri_captura.configuracao import carregar_contexto_ri
from cdp.data.ri_captura.observado import sha
from cdp.universe import universe_from_frame

CAPTURE = datetime(2026, 10, 7, 10, 50, 46, 408768, UTC)
BOUND = CAPTURE + timedelta(seconds=2)
ENTITY = "EMISSOR EXEMPLO S.A. DADOS SIMULADOS"


def pdf_bytes(pages):
    writer = PdfWriter()
    for lines in pages:
        page = writer.add_blank_page(width=1200, height=1000)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        body = [b"BT /F1 10 Tf 10 970 Td 14 TL"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            body.append(("(" + escaped + ") Tj T*").encode("cp1252"))
        body.append(b"ET")
        stream.set_data(b"\n".join(body))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def fixture(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    def write(name, value):
        file = path / name
        raw = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        file.write_bytes(raw)
        return file, sha(raw)

    md = make_synthetic_market(as_of=date(2026, 10, 7))
    lines = md.universe.lines
    chosen = []
    for country in ("BR", "MX", "CL"):
        chosen.append(lines[(lines.country == country) & lines.primary_line].index[0])
    frame = lines.loc[chosen].copy()
    prior_iid = frame.loc[chosen[1], "issuer_id"]
    frame.loc[chosen[1], "issuer_id"] = "MX_AMX"
    frame.loc[chosen[1], "yahoo_ticker"] = "AMX"
    frame.loc[chosen[1], "exchange"] = "NYSE"
    frame.loc[chosen[1], "issuer_name"] = ENTITY
    frame.loc[chosen[1], "currency"] = "MXN"
    master_path, master_sha = write("master.csv", frame.to_csv(index=False).encode())
    universe = universe_from_frame(frame, source_sha256=master_sha)
    ren = {chosen[1]: "AMX"}
    kwargs = {"universe": universe}
    for name in ("close", "adj_close", "volume"):
        kwargs[name] = getattr(md, name)[chosen].rename(columns=ren)
    for name in ("fundamentals", "short_interest", "lending"):
        kwargs[name] = getattr(md, name).rename(index=ren)
    md = replace(md, **kwargs)
    observation = {
        "schema": "cdp.observacao_local_curada/v1",
        "master_path": str(master_path),
        "master_sha256": master_sha,
        "inicio_utc": (BOUND - timedelta(microseconds=1)).isoformat(),
        "fim_utc": BOUND.isoformat(),
        "aviso": "DADOS SIMULADOS",
    }
    obs_path, obs_sha = write("master-observacao.json", observation)
    master_root = {
        "schema": "cdp.ri.master_confiado_privado/v2",
        "origem_confianca": "DADOS SIMULADOS: autoridade gerada previamente ao candidato",
        "master_path": str(master_path),
        "master_sha256": master_sha,
        "observacao_path": str(obs_path),
        "observacao_sha256": obs_sha,
    }
    master_root_path, master_root_sha = write("master-root.json", master_root)
    reg_path, reg_sha = write(
        "registro.json",
        {"cik": "0000001234", "name": ENTITY, "tickers": ["AMX"], "exchanges": ["NYSE"]},
    )
    url = "https://data.sec.gov/submissions/CIK0000001234.json"
    reg_receipt = {
        "schema": "cdp.captura_publica_http/v1",
        "retrodatada": False,
        "fontes": [
            {
                "path": str(reg_path),
                "sha256": reg_sha,
                "status_http": 200,
                "aceita_como_documento": True,
                "url_solicitada": url,
                "url_final": url,
                "inicio_utc": (CAPTURE + timedelta(seconds=1, microseconds=-1)).isoformat(),
                "fim_utc": (CAPTURE + timedelta(seconds=1)).isoformat(),
            }
        ],
    }
    receipt_path, receipt_sha = write("registro-captura.json", reg_receipt)
    identity_path, identity_sha = write(
        "identity-root.json",
        {
            "schema": "cdp.ri.identidade_custodia/v2",
            "origem_confianca": "DADOS SIMULADOS: nenhum registro real",
            "master_anchor_sha256": master_root_sha,
            "registro": {
                "raw_path": str(reg_path),
                "raw_sha256": reg_sha,
                "receipt_path": str(receipt_path),
                "receipt_sha256": receipt_sha,
                "url": url,
                "namespace": "sec.submissions",
            },
        },
    )
    meta = [
        ENTITY + " Consolidado",
        "Cantidades monetarias expresadas en Unidades",
        "Periodo cubierto por los estados financieros: 2026-01-01 al 2026-06-30",
        "Descripción de la moneda de presentación: MXN",
        "Consolidado: Si",
        "Grado de redondeo utilizado en los estados financieros: MILES DE PESOS",
        "Clave de cotización: AMX",
        "Nombre de la entidad que informa u otras formas de identificación: " + ENTITY,
        "Descripción de la moneda de presentación: MXN",
    ]
    table = [
        ENTITY + " Consolidado",
        "Cantidades monetarias expresadas en Unidades",
        "Concepto Cierre Periodo Actual MXN 2026-06-30 Cierre Año Anterior MXN 2025-12-31",
        "Controladores 30,000 20,000",
        "Minoritarios 10,000 5,000",
        "Total 40,000 25,000",
    ]
    pdfurl = "https://cdn.exemplo.test/relatorio.pdf"
    entries = {}
    captures = {
        "origem": ("https://ri.exemplo.test/relatorios", b"DADOS SIMULADOS cdn.exemplo.test", None),
        "lista": (
            "https://ri.exemplo.test/feed",
            json.dumps(
                {
                    "GetContentAssetListResult": [
                        {
                            "Title": "2T2026 DADOS SIMULADOS",
                            "FilePath": pdfurl,
                            "FileType": "PDF",
                            "ContentAssetDate": "07/21/2026 00:00:00",
                        }
                    ]
                }
            ).encode(),
            None,
        ),
        "pdf": (pdfurl, pdf_bytes([meta, table]), "application/pdf"),
    }
    for name, (url, raw, contenttype) in captures.items():
        bruto, bsha = write(name + ".raw", raw)
        rec = {
            "status": 200,
            "url": url,
            "sha256": bsha,
            "coleta_inicio": (CAPTURE - timedelta(microseconds=1)).isoformat(),
            "coleta_fim": CAPTURE.isoformat(),
        }
        if contenttype:
            rec["content_type"] = contenttype
        recpath, rsha = write(name + "-recibo.json", rec)
        entries[name] = {
            "bruto": str(bruto),
            "recibo": str(recpath),
            "sha256_bruto": bsha,
            "sha256_recibo": rsha,
            "url": url,
            "tipo": "pdf" if name == "pdf" else name,
        }
    custody_path, custody_sha = write(
        "custodia.json",
        {
            "schema": "cdp.ri.custodia_privada/v1",
            "origem_confianca": "DADOS SIMULADOS: sem coleta externa",
            "entradas": entries,
        },
    )
    cfg = {
        "schema": "cdp.ri.configuracao_externa/v1",
        "origem": "DADOS SIMULADOS",
        "master": {"path": master_root_path.name, "sha256": master_root_sha},
        "identidade": {"path": identity_path.name, "sha256": identity_sha},
        "custodia": {"path": custody_path.name, "sha256": custody_sha},
        "ticker": "AMX",
        "exchange": "NYSE",
        "documento": {
            "issuer_id": "MX_AMX",
            "entity": ENTITY,
            "currency": "MXN",
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
            "pages_context": [1, 2],
            "page_metadata": 1,
            "page_table": 2,
            "page_count": 2,
            "columns": [
                {"label": "Cierre Periodo Actual", "end": "2026-06-30"},
                {"label": "Cierre Año Anterior", "end": "2025-12-31"},
            ],
            "items": [
                {"name": "patrimonio_controladores", "label": "Controladores"},
                {"name": "participacao_minoritarios", "label": "Minoritarios"},
                {"name": "patrimonio_liquido", "label": "Total"},
            ],
            "identity": [
                "patrimonio_liquido",
                ["patrimonio_controladores", "participacao_minoritarios"],
            ],
            "listing_title": "2T2026 DADOS SIMULADOS",
            "expected_scale": "1",
        },
    }
    cfgpath, cfgsha = write("contexto.json", cfg)
    context = carregar_contexto_ri(cfgpath, sha256_esperado=cfgsha)
    return md, context, prior_iid
