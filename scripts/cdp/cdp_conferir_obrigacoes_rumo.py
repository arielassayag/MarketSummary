"""Confere PDFs fornecidos e emite apoio documental Rumo em stdout; sem CDP."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

CONTEXTO = {
    "publicacao_historica": "7f0d368c1a5bba0c1bbe948aea38dda232e34852",
    "gerador_historico": "af6eb0c93d7c14efaa49bd658c0a502f4e9aedb9",
    "retrato": "2026-10-09",
    "corte_UTC": "2026-10-09T14:19:57.833570+00:00",
    "replay07_nao_e_prova09": True,
    "natureza": "apoio_documental_sem_aceite_economico_ou_PIT",
}
FONTES = {
    "RUMO_PDF_2T26": {
        "sha256": "ba0083fabddc262ccf391e14123d00910b8965d628b2d6718bfab7fd5a741a35",
        "arquivo_URL": "e563721f-ed1f-b028-f29b-edc251818619",
        "datas": ["2026-06-30", "2025-12-31"],
        "a": 90, "b": 92, "lease": 67, "deposit": 91,
        "paginas": [35, 39, 67, 68, 80, 81, 90, 91, 92],
    },
    "RUMO_PDF_4T25": {
        "sha256": "ed34eb3cd60505dd2b1024afd613cd9a06a36c075d472c4a66c1b7f28952e982",
        "arquivo_URL": "6ee246be-abc2-a58f-13f4-39dbf47c8cf0",
        "datas": ["2025-12-31", "2024-12-31"],
        "a": 119, "b": 120, "lease": 75, "deposit": 120,
        "paginas": [33, 74, 75, 99, 100, 101, 119, 120, 121],
    },
    "RUMO_PDF_2T25": {
        "sha256": "16bd36189133e78b96e1eac9148999d2c4fef6c62261b0b4e63963004c9fe882",
        "arquivo_URL": "e466510f-2d3d-e096-40b5-b5e0886006d9",
        "datas": ["2025-06-30", "2024-12-31"],
        "a": 79, "b": 81, "lease": 56, "deposit": 80,
        "paginas": [30, 56, 57, 69, 70, 79, 80, 81, 82],
    },
}
RAIZ_URL = "https://api.mziq.com/mzfilemanager/v2/d/003f6029-d45a-44ac-9c9e-869fe5df83fc/"
DINHEIRO = r"(?:\([0-9][0-9.]*\)|[0-9][0-9.]*|—)"
DUAS = re.compile(rf"(?P<a>{DINHEIRO})\s+(?P<b>{DINHEIRO})\s*$")
DECLARACOES_SHA = "cf5ffab14120e682d7b090da8e44a073a575569f9ad351ffb2b699e9541d7718"


def exigir(condicao, mensagem):
    if not condicao:
        raise ValueError(mensagem)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def utc(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    exigir(result.utcoffset() == timedelta(0), "Instante deve ter UTC explícito")
    return result


def metadados(path):
    st = path.lstat()
    exigir(path.is_file() and not path.is_symlink(), "Forneça arquivo regular, sem symlink")
    body = path.read_bytes()
    return body, {"sha256": sha(body), "bytes": len(body), "mtime_ns": st.st_mtime_ns,
                  "inode": st.st_ino, "mode": st.st_mode, "nlink": st.st_nlink}


def objeto(pairs):
    result = {}
    for key, value in pairs:
        exigir(key not in result, "Chave JSON duplicada: " + key)
        result[key] = value
    return result


def invalido(value):
    raise ValueError("Constante JSON não finita: " + value)


def ler_json(body):
    return json.loads(body, object_pairs_hook=objeto, parse_constant=invalido)


def selo_curatorial(index, expected):
    declared = {"fontes_declaradas": index["fontes"], "proveniencia": index["proveniencia_fechada"],
                "revisao_ROOT": index["revisao_documental_recebida_ROOT_SHA"],
                "ANTT": index["ANTT_descoberta_e_negativa"],
                "participante": expected["participante_historico_recebido"],
                "claims": expected["claims"], "flags": expected["flags"]}
    return sha(json.dumps(declared, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode())


class Guarda:
    """Defesa Python em leitura; não é sandbox de chamadas nativas de bibliotecas."""

    def __init__(self):
        self.negados = []

    def audit(self, event, args):
        negar = False
        if event == "open":
            _, mode, flags = args
            negar = isinstance(mode, str) and any(c in mode for c in "wax+")
            negar |= isinstance(flags, int) and bool(flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
        negar |= event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn", "os.posix_spawn"))
        negar |= event in {"os.system", "os.fork", "os.remove", "os.rename", "os.rmdir", "os.mkdir",
                           "os.link", "os.symlink", "os.chmod", "os.chown", "os.utime", "os.truncate"}
        negar |= event == "import" and (args[0] == "cdp" or args[0].startswith("cdp."))
        if negar:
            self.negados.append(event)
            raise RuntimeError("Efeito negado: " + event)


def valor(lexema):
    if lexema == "—":
        return None
    exigir(re.fullmatch(DINHEIRO, lexema) is not None, "Lexema monetário inválido")
    return str(Decimal(lexema.replace(".", "").replace("(", "-").replace(")", "")) * 1000)


def secao(text, start, end=None):
    exigir(text.count(start) == 1 and (end is None or text.count(end) == 1),
           "Âncora de seção ausente ou ambígua: " + start)
    tail = text.split(start, 1)[1]
    return tail.split(end, 1)[0] if end else tail


def extrair_rubricas(sid, spec, texts):
    rows = []

    def linha(page, selected, label, category, subtotal=False):
        text = texts[str(page)]
        candidates = [line for line in selected.splitlines()
                      if (DUAS.fullmatch(line.strip()) if subtotal else line.strip().startswith(label))]
        exigir(len(candidates) == 1, "Rubrica física ausente ou ambígua: " + label)
        raw = candidates[0]
        match = DUAS.search(raw)
        exigir(match is not None, "Duas colunas monetárias obrigatórias")
        ordinals = [i for i, line in enumerate(text.splitlines(), 1) if line == raw]
        exigir(len(ordinals) == 1, "Ordinal de linha ambíguo")
        row = {"source_id": sid, "pdf_sha256": spec["sha256"], "pagina_fisica_1base": page,
               "linha_texto_1base": ordinals[0], "linha_literal": raw, "rubrica": label,
               "categoria_documental": category, "moeda": "BRL", "escala": "MIL",
               "base": "grupo/controladas na nota do consolidado", "label": "fact_source_reported",
               "celulas": [{"data_coluna": day, "lexema": match.group(key),
                            "valor_BRL": valor(match.group(key)),
                            "ausente_nao_e_zero": match.group(key) == "—"}
                           for day, key in zip(spec["datas"], ("a", "b"), strict=True)]}
        rows.append(row)

    a_text, b_text = texts[str(spec["a"])], texts[str(spec["b"])]
    for day in spec["datas"]:
        header = day[8:10] + "/" + day[5:7] + "/" + day[:4]
        exigir(header in a_text and header in b_text, "Data física das colunas ausente")
    a = secao(a_text, "a) Arrendamentos e concessões em litígio e parcelados")
    lit = secao(a, "Arrendamento e concessão em litígio:", "Arrendamentos parcelados:")
    par = secao(a, "Arrendamentos parcelados:", "Concessões e outorgas:")
    grant = secao(a, "Concessões e outorgas:", "Total")
    b = secao(b_text, "b) Arrendamentos e outorgas enquadrados no IFRS16 (Nota 5.6)",
              None if sid == "RUMO_PDF_4T25" else "c) Compromissos de investimento")
    leases, grants = secao(b, "Arrendamentos:", "Outorgas:"), secao(b, "Outorgas:", "Total")
    for selected, label, category, subtotal, page in [
        (lit, "Rumo Malha Oeste S.A.", "a_litigio", False, spec["a"]),
        (par, "Rumo Malha Paulista S.A.", "a_parcelados", False, spec["a"]),
        (grant, "Subtotal concessões e outorgas", "a_outorgas", True, spec["a"]),
        (a, "Total", "a_total", False, spec["a"]),
        (leases, "Subtotal arrendamentos IFRS16", "b_IFRS16", True, spec["b"]),
        (grants, "Subtotal outorgas IFRS16", "b_IFRS16", True, spec["b"]),
        (b, "Total", "b_total_subconjunto_5_6", False, spec["b"]),
    ]:
        linha(page, selected, label, category, subtotal)
    for label in ("Rumo Malha Sul S.A.", "Rumo Malha Paulista S.A.", "Rumo Malha Central S.A."):
        linha(spec["a"], grant, label, "a_outorgas_detalhe")
    for label in ("Rumo Malha Sul S.A.", "Rumo Malha Paulista S.A.", "Rumo Malha Oeste S.A."):
        linha(spec["b"], leases, label, "b_arrendamentos_detalhe")
    for label in ("Rumo Malha Paulista S.A. (renovação)", "Rumo Malha Central S.A."):
        linha(spec["b"], grants, label, "b_outorgas_detalhe")
    dep = secao(texts[str(spec["deposit"])],
                "Os depósitos judiciais associados aos litígios de arrendamento e concessão",
                "b) Arrendamentos e outorgas enquadrados" if sid == "RUMO_PDF_4T25" else None)
    linha(spec["deposit"], dep, "Rumo Malha Oeste S.A.", "deposito_judicial_nao_compensado_sem_contrato")
    return rows


def conferir(index, expected, bodies):
    from pypdf import PdfReader

    exigir(index["contexto"] == expected["contexto"] == CONTEXTO, "Contexto histórico divergente")
    exigir(index["identificacao"] == {
        "issuer_id": "BR_RUMO", "entidade": "Rumo S.A.", "cnpj": "02.387.241/0001-60",
        "natureza_CNPJ": "herdado_CVM_sem_nova_conferencia_primaria",
        "natureza_issuer": "mapeamento_curatorial_versionado", "versao": "rumo-obrigacoes-v1",
        "moeda": "BRL", "escala": "MIL", "base": "grupo/controladas na nota do consolidado",
        "tipo_periodo": "estoques_pontuais_com_comparativos_nativos_nao_TTM",
    }, "Identificação/grão curatorial divergente; CNPJ não é nova prova documental")
    exigir(set(index["fontes"]) == set(FONTES) == set(bodies), "Três PDFs exatos obrigatórios")
    rows, texts_all, sources = [], {}, []
    for sid, spec in FONTES.items():
        source, body = index["fontes"][sid], bodies[sid]
        url = RAIZ_URL + spec["arquivo_URL"] + "?origin=2"
        exigir(source["source_id"] == sid and source["sha256"] == sha(body) == spec["sha256"]
               and source["bytes"] == len(body) and body.startswith(b"%PDF-"), "SHA/bytes/PDF divergentes: " + sid)
        exigir(source["url"] == source["url_final"] == url, "URL primária divergente: " + sid)
        exigir(source["datas_colunas"] == spec["datas"] and source["paginas_fisicas"] == spec["paginas"],
               "Contexto temporal/colunas/páginas divergente: " + sid)
        receipt = source["recibo_projecao"]
        exigir(receipt["url_observada"] == receipt["url_final"] == url
               and receipt["sha256"] == sha(body) and receipt["bytes"] == len(body)
               and receipt["status"] == 200, "Recibo declarado não corresponde ao PDF")
        start, received = utc(receipt["inicio_utc"]), utc(receipt["recebido_utc"])
        exigir(start <= received and received > utc(CONTEXTO["corte_UTC"])
               and source["publicado_instante_UTC"] is None, "Recepção/publicação/corte divergente")
        reader = PdfReader(io.BytesIO(body))
        exigir(len(reader.pages) == source["n_paginas"], "Quantidade de páginas divergente")
        texts = {str(p): reader.pages[p - 1].extract_text() or "" for p in spec["paginas"]}
        for page, text in texts.items():
            exigir("milhares de reais" in text.lower()
                   and sha(text.encode()) == expected["paginas_SHA"][sid][page], "Página/escala/extrator divergente")
        exigir("Arrendamentos consolidado" in texts[str(spec["lease"])], "Base consolidada ausente")
        rows.extend(extrair_rubricas(sid, spec, texts))
        texts_all[sid] = texts
        sources.append({"source_id": sid, "sha256": sha(body), "recebido_UTC": received.isoformat(),
                        "publicacao_exata": None, "recepcao_posterior_corte09": True})
    exigir(rows == expected["rubricas"], "Rubricas/colunas/lexemas/grão divergem das linhas físicas")
    exigir(len(rows) == 48 and sum(len(r["celulas"]) for r in rows) == 96, "Recorte de rubricas incompleto")
    claims = expected["claims"]
    exigir([c["id"] for c in claims] == [f"P{i:02d}" for i in range(1, 15)], "Claims incompletos ou duplicados")
    for claim in claims:
        text = texts_all[claim["source_id"]][str(claim["pagina_fisica_1base"])]
        exigir(claim["pdf_sha256"] == FONTES[claim["source_id"]]["sha256"]
               and sha(text.encode()) == claim["pagina_texto_sha256"]
               and claim["ancora_literal"] in text.splitlines()[claim["linha_inicio_1base"] - 1], "Âncora física de claim divergente")
        exigir(claim["label"] == ("issuer_management_claim" if claim["id"] == "P09" else "fact_source_reported"),
               "Relato do emissor/classificação de evidência divergente")
    flags = expected["flags"]
    exigir([f["id"] for f in flags] == [f"Q{i:02d}" for i in range(1, 9)]
           and all(f["material"] is True for f in flags), "Flags materiais ausentes")
    exigir(selo_curatorial(index, expected) == DECLARACOES_SHA,
           "Declarações/recibos projetados/participante histórico diferem da versão curatorial; pin não é prova primária")
    stock_text = texts_all["RUMO_PDF_2T26"]["67"]
    matches = [line for line in stock_text.splitlines() if line.startswith("Saldo em 30 de junho de 2026")]
    exigir(len(matches) == 1, "Estoque pontual 5.6 ausente ou ambíguo")
    stock = matches[0]
    base = expected["base_herdada_5_6"]
    exigir(stock == base["linha_literal"] and base["data"] == "2026-06-30"
           and base["moeda"] == "BRL" and base["escala"] == "MIL" and base["pagina"] == 67
           and base["source_id"] == "RUMO_PDF_2T26", "Base herdada 5.6/contexto divergente")
    amounts = [valor(x) for x in stock.split()[-4:]]
    exigir(amounts == base["valores_BRL"], "Quatro células da linha de apoio 5.6 divergem")
    financial, concession, other, total56 = [Decimal(x) for x in amounts]
    current = [r for r in rows if r["source_id"] == "RUMO_PDF_2T26"]

    def cell(category, rubric=None):
        found = [r for r in current if r["categoria_documental"] == category
                 and (rubric is None or r["rubrica"] == rubric)]
        exigir(len(found) == 1, "Componente da abertura ausente ou ambíguo")
        return Decimal(found[0]["celulas"][0]["valor_BRL"])

    blease = cell("b_IFRS16", "Subtotal arrendamentos IFRS16")
    bgrant = cell("b_IFRS16", "Subtotal outorgas IFRS16")
    leaves = [
        ("Financeiro — nota 5.6", financial, "5.6/p67"),
        ("Operacionais — outros — nota 5.6", other, "5.6/p67"),
        ("Arrendamentos IFRS16 — abertura b", blease, "5.15(b)/p92"),
        ("Outorgas IFRS16 — abertura b", bgrant, "5.15(b)/p92"),
        ("Arrendamento/concessão em litígio — Malha Oeste", cell("a_litigio"), "5.15(a)/p90"),
        ("Arrendamentos parcelados — Malha Paulista", cell("a_parcelados"), "5.15(a)/p90"),
        ("Concessões/outorgas — conta a", cell("a_outorgas"), "5.15(a)/p90"),
    ]
    total = sum((x[1] for x in leaves), Decimal(0))
    checks = [
        {"id": "b_total_mesma_coluna_concessoes_fisica_5_6", "residuo_BRL": str(cell("b_total_subconjunto_5_6") - concession)},
        {"id": "b_subtotais_total_b_fisico", "residuo_BRL": str(blease + bgrant - cell("b_total_subconjunto_5_6"))},
        {"id": "abertura_mesmo_perimetro_total5_6_mais_a", "residuo_BRL": str(total - total56 - cell("a_total"))},
    ]
    exigir(checks == expected["controles_documentais"]
           and all(Decimal(c["residuo_BRL"]) == 0 for c in checks), "Controle documental divergente")
    unknown = [{"source_id": r["source_id"], "pagina": r["pagina_fisica_1base"],
                "rubrica": r["rubrica"], "data": c["data_coluna"], "valor": None}
               for r in rows for c in r["celulas"] if c["valor_BRL"] is None]
    exigir(unknown == [{"source_id": "RUMO_PDF_2T26", "pagina": 92,
                       "rubrica": "Rumo Malha Oeste S.A.", "data": "2026-06-30", "valor": None}], "Travessão desconhecido divergente")
    return {"contexto": CONTEXTO, "fontes_conferidas": sources, "rubricas": rows, "claims": claims,
            "flags": flags, "controles_documentais": checks, "travessao_desconhecido": unknown,
            "abertura": [{"rubrica": name, "valor_BRL": str(v), "localizador": loc} for name, v, loc in leaves],
            "total_abertura_BRL": str(total), "participante_historico_recebido": expected["participante_historico_recebido"],
            "rubricas_48_celulas_96": True, "linha_apoio_5_6_relocalizada_sem_novo_caso": True,
            "instrumento_ANTT_autenticado": False, "casos_financeiros_novos": 0,
            "FCFF_EV_PIT_P0_aceitos": False, "limite": "Âncoras, rótulos e três controles documentais não provam contrato econômico, disponibilidade histórica ou comportamento do produtor atual."}


def quadro(result, index):
    def fmt(value):
        return f"{int(Decimal(value)):,}".replace(",", ".")

    lines = ["# Rumo — abertura documental de obrigações", "",
             "Publicação histórica 7f0d368c; gerador af6eb0c; retrato 09/10/2026; corte 14:19:57.833570Z. A reprodução 07 não comprova o retrato 09. Apoio documental, sem execução ou adoção financeira.", "",
             "Estoque 30/06/2026; BRL; escala original MIL; grupo/controladas na nota consolidada. CNPJ herdado da CVM, sem nova verificação primária. A abertura b já está na coluna concessões de 5.6 e não constitui dívida adicional.", "",
             "| Rubrica | BRL | PDF 2T26 — página física |", "|---|---:|---|" ]
    lines.extend(f"| {r['rubrica']} | {fmt(r['valor_BRL'])} | {r['localizador']} |" for r in result["abertura"])
    lines.extend([f"| Total derivado em código | {fmt(result['total_abertura_BRL'])} | 5.6 + 5.15(a) |", "",
                  "Participante histórico recebido `t.arrendamentos`, arredondado pelo modelo: "
                  + fmt(result["participante_historico_recebido"]["valor_BRL_declarado"]) + " BRL. Essa base é preservada, separada do bruto das notas; o leitor não recertifica o modelo ou seu arredondamento.", "",
                  f"O leitor confere {len(result['rubricas'])} rubricas/{sum(len(r['celulas']) for r in result['rubricas'])} células, {len(result['claims'])} âncoras e {len(result['flags'])} flags materiais. Relocaliza a linha de apoio 5.6 já recebida. Os três controles documentais herdados mantêm resíduo zero; nenhum novo caso de modelo ou repetição dos 8 fluxos/4 saldos/6 ROU ties é reivindicado.", "",
                  "Malha Oeste na abertura IFRS16 de 30/06/2026: travessão preservado como desconhecido (`null`/`None`), sem inferir baixa, quitação ou zero. Originais e comparativos nativos permanecem separados no ledger.", "",
                  "D&A Rumo legado contém impairment na DVA original 6M25; o montante CVM permanece reportado, com classificação econômica incorreta no legado. D&A DFC, remensuração, impairment e concessões continuam separados; este quadro não os repara.", "",
                  "| Fonte | Coluna original / comparativa | Recepção original UTC | Publicação exata |", "|---|---|---|---|"])
    for sid, source in index["fontes"].items():
        lines.append(f"| [{sid}]({source['url']}) | {' / '.join(source['datas_colunas'])} | {source['recibo_projecao']['recebido_utc']} | Desconhecida |")
    lines.extend(["", "Os três recibos são posteriores ao corte 09. Referência contábil, aprovação, publicação e recepção não são intercambiáveis; o SHA do corpo vincula o arquivo fornecido, sem autenticação independente de um recibo HTTP passado.", "",
                  "A única recepção urllib do instrumento ANTT retornou 403. A descoberta web de 23 páginas é um meio distinto, sem PDF local autenticado nesta evidência. Não confirma cláusulas, implementação, encontro de contas, crédito, baixa ou exclusão do consolidado.", "",
                  "Fontes, SHAs, recibos projetados e localizadores: [SOURCE_INDEX.json](SOURCE_INDEX.json) e [EVIDENCIAS.json](EVIDENCIAS.json). Alcance econômico/jurídico: [LIMITES.md](LIMITES.md).", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fontes", type=Path, required=True, help="SOURCE_INDEX.json público")
    parser.add_argument("--evidencias", type=Path, required=True, help="EVIDENCIAS.json público")
    parser.add_argument("--pdf-2t26", type=Path, required=True)
    parser.add_argument("--pdf-4t25", type=Path, required=True)
    parser.add_argument("--pdf-2t25", type=Path, required=True)
    parser.add_argument("--formato", choices=("json", "quadro"), default="json")
    args = parser.parse_args()
    try:
        exigir(sys.dont_write_bytecode, "Execute Python com -B")
        exigir(not any(n == "cdp" or n.startswith("cdp.") for n in sys.modules), "CDP importado: fronteira recusada")
        guard = Guarda()
        sys.addaudithook(guard.audit)
        files = [args.fontes, args.evidencias, args.pdf_2t26, args.pdf_4t25, args.pdf_2t25]
        received = {p: metadados(p) for p in files}
        index, expected = ler_json(received[args.fontes][0]), ler_json(received[args.evidencias][0])
        bodies = {sid: received[path][0] for sid, path in zip(FONTES, files[2:], strict=True)}
        with localcontext() as ctx:
            ctx.prec = 80
            result = conferir(index, expected, bodies)
        exigir(all(metadados(p)[1] == received[p][1] for p in files), "Entradas alteradas durante leitura")
        exigir(not guard.negados, "Efeito vedado observado")
        print(quadro(result, index) if args.formato == "quadro" else
              json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), end="" if args.formato == "quadro" else "\n")
    except (ValueError, KeyError, TypeError, IndexError, OSError, RuntimeError) as exc:
        parser.exit(2, "Conferência recusada: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
