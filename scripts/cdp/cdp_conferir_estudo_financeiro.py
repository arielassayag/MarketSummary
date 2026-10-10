"""Relê corpos fornecidos; confere recortes públicos, sem CDP, rede ou escrita."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

from pypdf import PdfReader

NUM = re.compile(r"\(?-?\d{1,3}(?:\.\d{3})*\)?|—")
NUM_DVA = re.compile(r"\(?\d{1,3}(?:\.\d{3})+\)?|—")


def exigir(ok, mensagem):
    if not ok:
        raise ValueError(mensagem)


def local(tag):
    return tag.rsplit("}", 1)[-1]


def money(token):
    if token == "—":
        return None
    return str(Decimal(token.replace(".", "").replace("(", "-").replace(")", "")) * 1000)


def utc(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    exigir(dt.utcoffset() == timedelta(0), "Recepção deve declarar UTC explícito")
    return dt


def meta(path):
    stat = path.lstat()
    exigir(path.is_file() and not path.is_symlink(), "Forneça arquivo regular: " + str(path))
    body = path.read_bytes()
    return body, {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body),
                  "mtime_ns": stat.st_mtime_ns, "inode": stat.st_ino,
                  "mode": stat.st_mode, "nlink": stat.st_nlink}


def fontes(e, paths):
    bodies, pins = {}, {}
    for sid, path in paths.items():
        exigir(sid in e["fontes"], "SourceID desconhecido: " + sid)
        f = e["fontes"][sid]
        u = urlsplit(f["url"])
        exigir(u.scheme == "https" and u.hostname in ("www.sec.gov", "dados.cvm.gov.br", "api.mziq.com")
               and not u.username and not u.password, "URL primária inesperada")
        body, pin = meta(path)
        exigir(pin["sha256"] == f["sha256"] and pin["bytes"] == f["bytes"], "Bytes divergem: " + sid)
        exigir(bool(f["recibos"]), "Recibo ausente: " + sid)
        for r in f["recibos"]:
            exigir(r["url"] == f["url"] and r["sha256"] == pin["sha256"] and r["bytes"] == pin["bytes"],
                   "Recibo diverge do corpo: " + sid)
            utc(r["recebido_utc"])
            exigir(r["status_http"] in (None, 200), "Recibo negativo não é corpo financeiro: " + sid)
        if f["tipo"] == "PDF":
            exigir(body.startswith(b"%PDF-") and all(r["status_http"] == 200 for r in f["recibos"]),
                   "PDF não autenticado pelo recibo declarado: " + sid)
        if f["filing_data_civil"] is not None:
            datetime.strptime(f["filing_data_civil"], "%Y-%m-%d")
        bodies[sid], pins[sid] = body, pin
    return bodies, pins


def xml_recorte(body, expected):
    exigir(b"<!DOCTYPE" not in body.upper() and b"<!ENTITY" not in body.upper(), "XML com declaração externa recusado")
    root = ET.fromstring(body)
    contexts, units = {}, {}
    for n in root:
        if local(n.tag) == "context":
            contexts[n.get("id")] = {"id": n.get("id"),
                "entidade": next((x.text for x in n.iter() if local(x.tag) == "identifier"), None),
                "inicio": next((x.text for x in n.iter() if local(x.tag) == "startDate"), None),
                "fim": next((x.text for x in n.iter() if local(x.tag) in ("endDate", "instant")), None),
                "dimensoes": [{"eixo": x.get("dimension"), "membro": x.text} for x in n.iter()
                               if local(x.tag) in ("explicitMember", "typedMember")]}
        elif local(n.tag) == "unit":
            units[n.get("id")] = {"id": n.get("id"), "medidas": [x.text for x in n.iter() if local(x.tag) == "measure"],
                                  "divisao": any(local(x.tag) == "divide" for x in n.iter())}
    facts = []
    for f in expected:
        n = root[f["ordinal_filho_xbrl_0base"]]
        exigir(n.tag == f["tag_xml"] and dict(n.attrib) == f["atributos_literais"]
               and (n.text or "").strip() == f["valor_literal"], "Lexema/ordinal XML divergente")
        c, u = contexts[n.get("contextRef")], units[n.get("unitRef")]
        exigir(c == f["contexto"] and u == f["unidade_xml"], "Contexto/unidade XML divergente")
        exigir(c["entidade"] == "0001659939" and not c["dimensoes"] and u["medidas"] == ["iso4217:USD"]
               and not u["divisao"] and f["escala_multiplicativa"] == "1", "Grão XML inesperado")
        facts.append({"grupo": f["grupo_documental"], "contexto": c, "unidade": u,
                      "ordinal_0base": f["ordinal_filho_xbrl_0base"], "valor_USD": str(Decimal(n.text)),
                      "decimals_precisao": n.get("decimals")})
    residuals = {}
    for year in ("2023", "2024", "2025"):
        vals = {r["grupo"]: Decimal(r["valor_USD"]) for r in facts if r["contexto"]["fim"] == year + "-12-31"}
        residuals[year] = str(vals["PL_total"] - vals["owners"] - vals["NCI"])
        exigir(Decimal(residuals[year]) == 0, "Identidade patrimonial divergente")
    return {"ocorrencias": facts, "residuos_PL_total_owners_NCI": residuals,
            "NI_e_fluxo_anual_distinto_de_PL": True, "divida_consolidada_nao_certificada": True}


def entidade_cvm(e, issuer, physical_rows):
    """CNPJ vem do CSV; issuer é vínculo curatorial explicitamente versionado."""
    mapping = e["mapeamento_issuer_CVM"]
    exigir(mapping["natureza"] == "declaracao_curatorial_versionada" and bool(mapping["versao"]),
           "Mapeamento curatorial sem natureza/versão")
    declared = mapping["vinculos"].get(issuer)
    exigir(declared is not None and physical_rows, "Issuer curatorial desconhecido ou sem linhas físicas")
    identities = {(r["CNPJ_CIA"], r["DENOM_CIA"]) for r in physical_rows}
    exigir(len(identities) == 1, "Entidades físicas diferentes na composição")
    cnpj, name = next(iter(identities))
    exigir((cnpj, name) == (declared["CNPJ_CIA"], declared["DENOM_CIA"]),
           "Issuer declarado diverge do CNPJ/denominação físicos")
    return {"CNPJ_documental": cnpj, "DENOM_documental": name,
            "issuer_id_curatorial": issuer, "mapeamento_versao": mapping["versao"],
            "mapeamento_e_declaracao_versionada_nao_prova_PIT": True}


def grao_composicao_cvm(e, c, rows):
    """Reconstrói intervalo/frequência pelos períodos físicos e coeficientes."""
    all_ids = [rid for t in c["termos"] for rid in t["linhas"]]
    exigir(all_ids and len(all_ids) == len(set(all_ids)), "Composição vazia ou participante repetido")
    physical = [rows[rid] for rid in all_ids]
    entity = entidade_cvm(e, c["issuer_id"], physical)
    exigir(c["moeda"] == "BRL" and all(r["MOEDA"] == "REAL" and r["ESCALA_MOEDA"] == "MIL" for r in physical),
           "Moeda/escala declaradas incompatíveis com participantes físicos")
    groups = {r["GRUPO_DFP"] for r in physical}
    exigir(len(groups) == 1 and next(iter(groups)).startswith("DF Consolidado - "),
           "Demonstração/consolidação diferentes na composição")
    group = next(iter(groups))
    terms = []
    for t in c["termos"]:
        exigir(bool(t["linhas"]), "Termo sem participantes")
        grain_fields = ("DT_INI_EXERC", "DT_FIM_EXERC", "DT_REFER", "VERSAO", "ORDEM_EXERC")
        grains = {tuple(rows[rid].get(k) for k in grain_fields) for rid in t["linhas"]}
        exigir(len(grains) == 1, "Grão físico diferente dentro de um termo")
        start, end, reference, version, order = next(iter(grains))
        end_date = date.fromisoformat(end)
        exigir(reference == end and order == "ÚLTIMO" and bool(version),
               "Composição exige coluna original ÚLTIMO e referência física do período")
        origins = set()
        for rid in t["linhas"]:
            locator = e["CVM_linhas"][rid]
            member = locator["membro"]
            kind = "ITR" if member.startswith("itr_cia_aberta_") else "DFP" if member.startswith("dfp_cia_aberta_") else None
            exigir(kind is not None and "_con_" in member and member.endswith("_" + end[:4] + ".csv"),
                   "Membro físico incompatível com período/consolidação")
            source = e["fontes"][locator["SourceID"]]
            exigir(source["tipo"] == "ZIP" and urlsplit(source["url"]).path.rsplit("/", 1)[-1]
                   == kind.lower() + "_cia_aberta_" + end[:4] + ".zip", "Fonte/ano incompatível com membro físico")
            origins.add(kind)
        exigir(len(origins) == 1, "Origens documentais diferentes no termo")
        terms.append({"inicio": date.fromisoformat(start) if start else None, "fim": end_date,
                      "coeficiente": Decimal(t["coeficiente"]), "origem": next(iter(origins)),
                      "versao": version, "ordem": order})
    if all(t["inicio"] is None for t in terms):
        exigir(group == "DF Consolidado - Balanço Patrimonial Passivo" and len(terms) == 1
               and terms[0]["coeficiente"] == 1 and c["usar_modulo_nas_partes"] is False,
               "Composição de estoque incompatível com grão físico")
        derived_start, derived_end, kind, frequency = None, terms[0]["fim"].isoformat(), "estoque", "pontual"
    else:
        exigir(all(t["inicio"] is not None for t in terms) and len(terms) == 3
               and group in ("DF Consolidado - Demonstração do Fluxo de Caixa (Método Indireto)",
                             "DF Consolidado - Demonstração de Valor Adicionado")
               and c["usar_modulo_nas_partes"] is True, "Composição TTM incompatível com grão físico")
        end = max(t["fim"] for t in terms)
        exigir(end.month != 12 or end.day != 31, "Este recorte TTM exige acumulado intermediário explícito")
        previous_accumulated_end = end.replace(year=end.year - 1)
        expected = {
            (date(end.year, 1, 1), end): (Decimal(1), "ITR"),
            (date(end.year - 1, 1, 1), date(end.year - 1, 12, 31)): (Decimal(1), "DFP"),
            (date(end.year - 1, 1, 1), previous_accumulated_end): (Decimal(-1), "ITR"),
        }
        observed = {(t["inicio"], t["fim"]): (t["coeficiente"], t["origem"]) for t in terms}
        exigir(len(observed) == 3 and observed == expected,
               "Períodos/origens/coeficientes físicos não formam exercício + acumulado − acumulado anterior")
        derived_start = (previous_accumulated_end + timedelta(days=1)).isoformat()
        derived_end, kind, frequency = end.isoformat(), "TTM", "TTM"
    exigir((c["inicio"], c["fim"], c["tipo"], c["frequencia"]) == (derived_start, derived_end, kind, frequency),
           "Intervalo/tipo/frequência declarados divergem da composição física")
    return {**entity, "inicio_derivado": derived_start, "fim_derivado": derived_end,
            "tipo_derivado": kind, "frequencia_derivada": frequency, "demonstracao_fisica": group,
            "moeda_documental": "REAL", "escala_documental": "MIL", "moeda_saida": "BRL",
            "termos_fisicos": [{k: v.isoformat() if isinstance(v, date) else str(v) if isinstance(v, Decimal) else v
                               for k, v in t.items()} for t in terms],
            "item_permanece_rotulo_curatorial_nao_classificacao_economica_certificada": True}


def cvm_recorte(e, bodies):
    values, rows = {}, {}
    for sid, body in bodies.items():
        if e["fontes"][sid]["tipo"] != "ZIP":
            continue
        wanted = {rid: r for rid, r in e["CVM_linhas"].items() if r["SourceID"] == sid}
        with ZipFile(io.BytesIO(body)) as z:
            for member in sorted({r["membro"] for r in wanted.values()}):
                subset = {r["linha_csv_1base"]: (rid, r) for rid, r in wanted.items() if r["membro"] == member}
                raw = z.read(member)
                exigir(all(hashlib.sha256(raw).hexdigest() == r["membro_sha256"] for _, r in subset.values()),
                       "Membro ZIP divergente")
                for line, row in enumerate(csv.DictReader(io.StringIO(raw.decode("iso-8859-1")), delimiter=";"), 2):
                    if line not in subset:
                        continue
                    rid, expected = subset[line]
                    exigir(row == expected["campos"], "Linha/versão/ordem CVM divergente: " + rid)
                    exigir(row["MOEDA"] == "REAL" and row["ESCALA_MOEDA"] == "MIL"
                           and row["GRUPO_DFP"].startswith("DF Consolidado"), "Grão CVM inesperado")
                    values[rid] = Decimal(row["VL_CONTA"]) * 1000
                    rows[rid] = row
        exigir(set(wanted) <= set(values), "Linha CVM ausente no corpo")
    accounts = []
    for c in e["contas_CVM"]:
        ids = [rid for t in c["termos"] for rid in t["linhas"]]
        if not all(rid in values for rid in ids):
            continue
        grain = grao_composicao_cvm(e, c, rows)
        total = sum((Decimal(t["coeficiente"]) * sum(
            (abs(values[rid]) if c["usar_modulo_nas_partes"] else values[rid] for rid in t["linhas"]), Decimal(0))
            for t in c["termos"]), Decimal(0))
        exigir(total == Decimal(c["valor_codigo_arquivado"]), "Composição CVM divergente")
        accounts.append({"issuer_id": grain["issuer_id_curatorial"], "item": c["item"], "tipo": grain["tipo_derivado"],
                         "inicio": grain["inicio_derivado"], "fim": grain["fim_derivado"],
                         "frequencia": grain["frequencia_derivada"], "valor_BRL": str(total),
                         "escopo_declarado": c["escopo"], "grao_conferido": grain})
    giro = []
    for c in e["giro_Jun2026_controles"]:
        if all(rid in values for rid in [c["agregado"], *c["filhos"]]):
            physical = [rows[rid] for rid in [c["agregado"], *c["filhos"]]]
            entity = entidade_cvm(e, c["issuer_id"], physical)
            grains = {tuple(r.get(k) for k in ("DT_INI_EXERC", "DT_FIM_EXERC", "DT_REFER", "VERSAO", "ORDEM_EXERC", "GRUPO_DFP", "MOEDA", "ESCALA_MOEDA")) for r in physical}
            exigir(len(grains) == 1, "Grão físico diferente na identidade do agregado")
            residual = values[c["agregado"]] - sum((values[rid] for rid in c["filhos"]), Decimal(0))
            exigir(residual == 0, "Identidade do agregado divergente")
            giro.append({"issuer_id": entity["issuer_id_curatorial"], "entidade_documental": entity,
                         "residuo": str(residual), "operacional_certificado": False})
    return {"linhas": rows, "contas": accounts, "giro": giro}, values


def pdf_recorte(e, bodies):
    readers = {sid: PdfReader(io.BytesIO(body)) for sid, body in bodies.items() if e["fontes"][sid]["tipo"] == "PDF"}
    cells, locators = {}, []
    for r in e["PDF_linhas"]:
        if r["SourceID"] not in readers:
            continue
        text = readers[r["SourceID"]].pages[r["pagina_fisica_1base"] - 1].extract_text()
        exigir("Reais" in text and "consolidado" in text.casefold(), "Moeda/consolidação PDF ausente")
        if r["tipo"] == "DVA_DFC":
            if r["ultimo_consolidado"]:
                text = text.rsplit("Consolidado", 1)[1]
            flat = " ".join(text.split())
            tail = flat.split(r["rotulo"], 1)[1]
            tokens = NUM_DVA.findall(tail)[:len(r["colunas"])]
        else:
            flat = " ".join(text.split())
            opening = "Saldo em 01 de janeiro de " + r["inicio_exercicio"][:4]
            if r["qualificador"] == "passivo":
                section = flat[flat.index(opening):]
            else:
                cost, amort = flat.split("Valor de custo:", 1)[1].split("Amortização", 1)
                section = amort if r["qualificador"] == "amortização" else cost
                section = section[section.index(opening):]
            exigir(r["trecho_compactado"] in section, "Localizador/qualificador PDF divergente: " + r["id"])
            tokens = NUM.findall(r["trecho_compactado"][len(r["rotulo"]):])
        vals = [money(t) for t in tokens]
        exigir(tokens == r["tokens_arquivados"] and vals == r["valores_BRL_arquivados"], "Células PDF divergentes")
        cells[r["id"]] = vals
        locators.append({"id": r["id"], "SourceID": r["SourceID"], "pagina_fisica_1base": r["pagina_fisica_1base"],
                         "qualificador": r["qualificador"], "tokens": tokens, "colunas": r["colunas"], "valores_BRL": vals})
    rou = []
    for t in e["ROU_termos"]:
        ids = t["linhas_PDF"]
        if ids["adicoes_custo_ROU"] not in cells:
            continue
        add = Decimal(cells[ids["adicoes_custo_ROU"]][-1])
        passive = Decimal(cells[ids["adicoes_passivo_arrendamento"]][-1])
        reaj = Decimal(cells[ids["reajuste_custo_ROU"]][-1])
        supplement = Decimal(t["suplemento_nao_caixa_reportado_BRL"])
        page = readers[t["SourceID"]].pages[t["pagina_suplemento"] - 1].extract_text()
        lexeme = format(int(supplement / 1000), ",").replace(",", ".")
        exigir(lexeme in page, "Lexema do suplemento ausente; ele não é adição pura")
        exigir(add == passive and add + reaj == supplement, "Conciliação ROU divergente")
        rou.append({"periodo": t["periodo"], "adicoes_custo_BRL": str(add), "residuo_custo_passivo": str(add-passive),
                    "residuo_custo_reajuste_suplemento": str(add+reaj-supplement), "adotado_FCFF": False})
    conditional = None
    if len(rou) == len(e["ROU_termos"]):
        val = {t["periodo"]: Decimal(t["adicoes_custo_BRL"]) for t in rou}
        conditional = str(val["6M2026"] + val["A2025"] - val["6M2025"])
        exigir(conditional == e["ROU_composicao_condicional"]["composicao_documental_condicional_BRL"], "Composição ROU diverge")
        ids26 = next(t for t in e["ROU_termos"] if t["periodo"] == "6M2026")["linhas_PDF"]
        ids25 = next(t for t in e["ROU_termos"] if t["periodo"] == "A2025")["linhas_PDF"]
        exigir(cells[ids26["saldo_inicial_custo"]][-1] == cells[ids25["saldo_final_custo"]][-1], "Continuidade de custo diverge")
    return {"linhas": locators, "ROU": rou, "composicao_documental_condicional_BRL": conditional}, cells


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidencias", type=Path, required=True)
    parser.add_argument("--corpo", action="append", required=True, metavar="SourceID=ARQUIVO")
    args = parser.parse_args()
    paths = {}
    for spec in args.corpo:
        sid, sep, path = spec.partition("=")
        exigir(sep and sid and path and sid not in paths, "SourceID=ARQUIVO único exigido")
        paths[sid] = Path(path)
    state = {"leituras": 0, "escritas": 0, "rede": 0, "processos": 0, "vedados": []}

    def guard(event, values):
        kind = None
        if event == "open":
            _, mode, flags = values[:3]
            if (isinstance(mode, str) and any(c in mode for c in "wa+x")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                kind = "escritas"
            else:
                state["leituras"] += 1
        elif event.startswith("socket."):
            kind = "rede"
        elif event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.posix_spawnp"}:
            kind = "processos"
        elif event in {"os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.utime", "os.link", "os.symlink"}:
            kind = "escritas"
        if kind:
            state[kind] += 1
            state["vedados"].append(event)
            raise RuntimeError("Efeito vedado no leitor: " + event)

    sys.addaudithook(guard)
    raw, evidence_pin = meta(args.evidencias)
    e = json.loads(raw)
    exigir(e["schema"] == "cdp-estudo-documental-publico-v1", "Schema desconhecido")
    utc(e["corte_historico_UTC"])
    with localcontext() as ctx:
        ctx.prec = 80
        bodies, before = fontes(e, paths)
        xml = xml_recorte(bodies["ENEL_XML2025"], e["enel_XML_ocorrencias_delimitadas"]) if "ENEL_XML2025" in bodies else None
        cvm, values = cvm_recorte(e, bodies)
        pdf, cells = pdf_recorte(e, bodies)
        dva = {}
        needed = ("original_DVA", "original_DFC_DA", "original_DFC_perda", "despesas_DA", "atual_DVA", "atual_DVA_perda_separada")
        if all(k in cells for k in needed):
            v = {k: abs(Decimal(cells[k][1 if k == "despesas_DA" else 3 if k.startswith("atual") else 2])) for k in needed}
            dva = {"DVA_original_menos_DFC_DA_menos_perda": str(v["original_DVA"] - v["original_DFC_DA"] - v["original_DFC_perda"]),
                   "despesas_por_natureza_menos_DFC_DA": str(v["despesas_DA"] - v["original_DFC_DA"]),
                   "DVA_comparativo_reapresentado_menos_DFC_original_DA": str(v["atual_DVA"] - v["original_DFC_DA"]),
                   "perda_DVA_comparativo_menos_perda_DFC_original": str(v["atual_DVA_perda_separada"] - v["original_DFC_perda"])}
            for cell, description in (("original_DVA", "Depreciação, Amortização e Exaustão"),
                                      ("original_DFC_DA", "Depreciação e amortização"),
                                      ("original_DFC_perda", "Perda por redução ao valor recuperável")):
                refs = [rid for rid in e["DVA_CVM_originais_e_comparativos"] if rid in values and
                        e["CVM_linhas"][rid]["campos"]["DT_REFER"] == "2025-06-30" and
                        e["CVM_linhas"][rid]["campos"]["ORDEM_EXERC"] == "ÚLTIMO" and
                        e["CVM_linhas"][rid]["campos"]["DS_CONTA"] == description]
                exigir(len(refs) <= 1, "Grão CVM ambíguo no confronto DVA")
                if refs:
                    dva[cell + "_PDF_menos_CVM"] = str(v[cell] - abs(values[refs[0]]))
            exigir(all(Decimal(r) == 0 for r in dva.values()), "Confronto DVA/DFC divergente")
    after = {sid: meta(path)[1] for sid, path in paths.items()}
    exigir(before == after and evidence_pin == meta(args.evidencias)[1], "Entrada mudou durante leitura")
    result = {"fontes_conferidas": sorted(bodies), "fontes_nao_fornecidas": sorted(set(e["fontes"]) - set(bodies)),
              "EVIDENCIAS_sha256": evidence_pin["sha256"], "entradas_meta6_antes": before, "entradas_meta6_depois": after,
              "Enel_XML": xml, "CVM": cvm, "PDF": pdf, "residuos_DVA": dva, "guarda": state,
              "HTTP_novo": False, "recibos_sao_declaracoes_historicas_publicadas": True,
              "sem_modelo_produtor_gates_cache": True, "nao_certifica_PIT_P0_FCFF_ou_financeiros_completos": True}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
