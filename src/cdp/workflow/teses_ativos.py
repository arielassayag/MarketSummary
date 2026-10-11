"""Dossiês estáticos de ações e ETFs, a partir da cobertura conferida e de notas publicadas.

Não calcula valuation nem publica notas. A narrativa quantitativa identifica sua origem;
a opinião qualitativa só vem de uma nota ligada à trilha, com data própria. A ausência
de pesquisa específica nunca se transforma em uma tese fundamentalista concluída.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from .painel_publicacao import expandir

SCHEMA = "cdp.analise-ativo/v1"
_IID = re.compile(r"[A-Za-z0-9_-]{1,64}")

# Perguntas de diligência por método econômico: não são afirmações sobre uma empresa.
_DILIGENCIA = {
    "Bancos": (
        "A rentabilidade do patrimônio pode superar o custo de capital sem depender de crédito de maior risco?",
        "Margem financeira, custo de crédito, inadimplência, capital regulatório e qualidade do lucro.",
        "Deterioração persistente do crédito, reconhecimento inadequado de perdas ou crescimento que consuma capital sem retorno.",
    ),
    "Seguradoras": (
        "O resultado de subscrição e a política de reservas sustentam o retorno do capital?",
        "Sinistralidade, despesas, reservas, solvência e contribuição do resultado financeiro.",
        "Reservas insuficientes, piora da subscrição ou dependência de ganhos financeiros não recorrentes.",
    ),
    "Utilidades reguladas": (
        "A remuneração regulatória e a execução dos investimentos compensam o custo do capital e do financiamento?",
        "Revisões tarifárias, base regulatória, eficiência operacional, dívida e desembolsos de investimento.",
        "Retorno regulado insuficiente, atraso de obras, custos não recuperáveis ou financiamento incompatível com o caixa.",
    ),
    "Concessões": (
        "O caixa econômico da concessão remunera o capital após investimentos e obrigações contratuais?",
        "Volumes, tarifas, prazo contratual, manutenção, investimentos obrigatórios e financiamento.",
        "Demanda abaixo da premissa, investimento subestimado, mudança contratual adversa ou dívida sem cobertura pelo caixa.",
    ),
    "Commodities": (
        "A geração de caixa permanece defensável em preços e margens normalizados ao longo do ciclo?",
        "Preços realizados, volumes, custo unitário, câmbio, reinvestimento e estrutura de capital.",
        "Custos estruturalmente maiores, deterioração de ativos ou valuation dependente de margens de pico.",
    ),
    "Imobiliário": (
        "Os ativos e seus fluxos líquidos sustentam o valor atribuído ao patrimônio?",
        "Ocupação, receita recorrente, revisões de contratos, despesas, investimento e alavancagem.",
        "Queda persistente da renda, vacância crescente ou valor dos ativos sem respaldo em transações e caixa.",
    ),
    "Holdings": (
        "O valor econômico das participações chega ao acionista após dívida, custos e governança da holding?",
        "Valor e liquidez das participações, dívida por nível, despesas, partes relacionadas e alocação de capital.",
        "Dupla contagem de ativos, dívida omitida ou decisões de capital que destruam valor para o minoritário.",
    ),
}
_PADRAO = (
    "O crescimento e a rentabilidade geram caixa para o acionista após reinvestimento e financiamento?",
    "Receitas, preços, volumes, margens, conversão de lucro em caixa, capital investido e dívida.",
    "Crescimento sem geração de caixa, perda de posição competitiva ou retorno incremental inferior ao custo do capital.",
)


def caminho(iid: str) -> str:
    """Endereço estável, sem interpolação de caminhos arbitrários."""
    if not isinstance(iid, str) or not _IID.fullmatch(iid):
        raise ValueError("Identificador inválido para página de ativo")
    return f"ativos/{iid.lower()}/"


def _s(value: Any) -> str:
    return html.escape(str(value if value is not None else "Não disponível"), quote=True)


def _url(value: Any) -> str | None:
    if not isinstance(value, str) or any(ord(c) <= 32 for c in value):
        return None
    try:
        u = urlsplit(value)
        return value if u.scheme == "https" and u.hostname and not u.username and not u.password else None
    except ValueError:
        return None


def _paragrafo(texto: Any) -> str:
    return "".join(f"<p>{_s(t)}</p>" for t in str(texto or "Não disponível.").split("\n") if t.strip())


def _lista(itens: list[Any]) -> str:
    return "<ul>" + "".join(f"<li>{_s(i)}</li>" for i in itens) + "</ul>" if itens else "<p>Não disponível neste recorte.</p>"


def _tabela(colunas: list[tuple[str, str]], linhas: list[Mapping[str, Any]]) -> str:
    if not linhas:
        return "<p>Não disponível neste recorte.</p>"
    cab = "".join(f'<th scope="col">{_s(t)}</th>' for _, t in colunas)
    body = "".join("<tr>" + "".join(f"<td>{_s(r.get(k))}</td>" for k, _ in colunas) + "</tr>" for r in linhas)
    return f'<div class="analise-tabela" tabindex="0" role="region" aria-label="{_s("Tabela: " + ", ".join(t for _, t in colunas))}"><table><thead><tr>{cab}</tr></thead><tbody>{body}</tbody></table></div>'


def carregar_notas(rt: Any, ate: str) -> dict[str, dict[str, Any]]:
    """Somente notas publicadas íntegras; nunca rascunhos ou datas posteriores ao corte."""
    from .notas import load_published, nota_dir, published_notes, verify_notes

    if verify_notes(rt):
        return {}
    out = {}
    for iid, d in published_notes(rt.book_root):
        if d.isoformat() > ate:
            continue
        doc = load_published(rt.book_root, iid, d)
        if not doc or doc.get("issuer_id") != iid or doc.get("data") != d.isoformat():
            continue
        p = nota_dir(rt.book_root, iid, d) / "nota_publicada.json"
        out[iid] = {"documento": doc, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    "caminho": f"cobertura/notas/{iid}/{d.isoformat()}/nota_publicada.json"}
    return out


def documentos(arquivos: Mapping[str, str], notas: Mapping[str, dict[str, Any]], *,
               corte_pesquisa: str | None = None) -> list[dict[str, Any]]:
    """Um dossiê por linha, com números já formatados e identidade dos insumos."""
    principal = expandir(json.loads(arquivos["cobertura.json"]))
    meta = principal["meta"]
    if meta.get("estado") != "publicado":
        return []
    corte = corte_pesquisa or meta["as_of"]
    try:
        if date.fromisoformat(corte) < date.fromisoformat(meta["as_of"]):
            raise ValueError("Corte de pesquisa anterior ao retrato quantitativo")
    except (TypeError, ValueError) as exc:
        raise ValueError("Corte de pesquisa inválido ou anterior ao retrato quantitativo") from exc
    modelos, origens = {}, {}
    for info in (meta.get("files") or {}).get("modelos", []):
        nome = info["file"]
        raw = arquivos[nome]
        fragmento = expandir(json.loads(raw))
        for iid, m in fragmento["modelos"].items():
            if iid in modelos:
                raise ValueError("Modelo duplicado no dossiê: " + iid)
            modelos[iid] = m
            origens[iid] = {"arquivo": nome, "sha256": hashlib.sha256(raw.encode()).hexdigest()}
    out, enderecos = [], set()
    for u in principal["universe"]:
        iid = u["iid"]
        rota = caminho(iid)
        if rota in enderecos or iid not in modelos:
            raise ValueError("Dossiê duplicado ou sem modelo: " + iid)
        enderecos.add(rota)
        n = notas.get(iid)
        if n and (n["documento"].get("issuer_id") != iid or n["documento"].get("data", "") > corte):
            raise ValueError("Nota incompatível com o ativo ou com o corte de pesquisa")
        out.append({"schema": SCHEMA, "ativo": u, "modelo": modelos[iid], "nota": n,
                    "corte_cobertura": meta["as_of"], "corte_pesquisa": corte,
                    "dados_simulados": bool(meta["is_synthetic"]),
                    "aviso": meta.get("aviso_cvm"), "origem_modelo": origens[iid], "endereco": rota,
                    "estado_pesquisa": "nota_publicada" if n and n["documento"].get("autoria") == "mente"
                    else "analise_quantitativa_preliminar"})
    return out


def _evidencias(itens: list[dict[str, Any]]) -> str:
    descricoes = [str(x.get("fonte") or x.get("fato") or "") for x in itens]
    return f'<p class="analise-fonte">Evidências: {_s(" · ".join(descricoes))}</p>' if descricoes else ""


def _nota_secoes(r: Mapping[str, Any], *, etf: bool = False) -> list[tuple[str, str, str]]:
    from ..research.notas import COMPLEMENTOS_TESE

    pilares = "".join(f'<h3>{_s(p["titulo"])}</h3>{_paragrafo(p["texto"])}{_evidencias(p.get("evidencias") or [])}' for p in r.get("pilares_tese") or [])
    vetores = "".join(f'<h3>{_s(v["vetor"])}</h3>{_paragrafo(v["texto"])}{_evidencias(v.get("evidencias") or [])}' for v in r.get("vetores") or [])
    riscos = "".join(f'<h3>{_s(x["texto"])}</h3><p>Probabilidade: {_s(x["probabilidade"])} · Impacto: {_s(x["impacto"])}</p>{_evidencias(x.get("evidencias") or [])}' for x in r.get("riscos") or [])
    catalisadores = "".join(f'<h3>{_s(c["descricao"])}</h3><p>Data: {_s(c.get("data") or "Não confirmada")} · Direção: {_s(c["direcao"])}</p>{_evidencias(c.get("evidencias") or [])}' for c in r.get("catalisadores") or [])
    cenarios = "".join(f'<h3>{_s(t)}</h3>{_paragrafo((r.get("cenarios") or {}).get(k))}' for k, t in (("pessimista", "Pessimista"), ("base", "Base"), ("otimista", "Otimista")))
    out = [
        ("negocio", "Produto e exposição econômica" if etf else "Negócio e economia da empresa", _paragrafo(r.get("negocio"))),
        ("tese", "Tese e evidências", pilares),
        ("vetores", "Vetores de valor", vetores),
        ("valuation-narrativa", "Leitura qualitativa do valuation", _paragrafo(r.get("comentario_valuation"))),
        ("cenarios-narrativa", "Cenários da narrativa", cenarios),
        ("resultado", "Resultados e expectativas da gestão", _paragrafo(r.get("ultimo_resultado")) + f'<p>Guidance: {_s(r.get("guidance"))} · Tom da gestão: {_s(r.get("tom_gestao"))}</p>'),
        ("catalisadores", "Catalisadores", catalisadores or "<p>Não há catalisador datado confirmado na nota.</p>"),
        ("riscos", "Riscos da tese", riscos),
        ("governanca", "Governança e alocação de capital", _paragrafo(r.get("governanca"))),
        ("revisao", "O que muda a visão", _lista(r.get("gatilhos_revisao") or []) + (_paragrafo(r["o_que_mudou"]) if r.get("o_que_mudou") else "")),
        ("lacunas-narrativa", "Lacunas da pesquisa qualitativa", _lista(r.get("lacunas_de_dados") or [])),
    ]
    if etf:
        out = [(k, t, b) if k != "resultado" else
               (k, "Prestação de contas do produto", _paragrafo(
                   r.get("ultimo_resultado") or "Prestação de contas do fundo não analisada nesta nota."))
               for k, t, b in out]
    for campo, titulo in COMPLEMENTOS_TESE.items():
        if r.get(campo):
            body = "".join(f'<h3>{_s(p["titulo"])}</h3>{_paragrafo(p["texto"])}{_evidencias(p.get("evidencias") or [])}' for p in r[campo])
            out.append((campo.replace("_", "-"), titulo, body))
    return out


def _memoria(m: Mapping[str, Any]) -> str:
    partes = []
    for passo in m.get("passos") or []:
        partes.append(f'<h3>{_s(passo["t"])}</h3>')
        partes.append(_paragrafo(passo.get("s") or passo.get("f") or passo.get("r")))
        if passo.get("r") and passo["r"] != passo.get("s"):
            partes.append(_paragrafo("Resultado: " + str(passo["r"])))
        if passo.get("p"):
            partes.append(_paragrafo(passo["p"]))
        fontes_passo = [f'<a href="#fonte-{i}">M{i + 1}</a>' for i in passo.get("fo") or []
                        if type(i) is int and 0 <= i < len(m.get("fontes") or [])]
        if fontes_passo:
            partes.append('<p class="analise-fonte">Fontes do modelo: ' + " · ".join(fontes_passo) + '</p>')
    for metodo in m.get("metodos") or []:
        if metodo.get("projecao") and metodo.get("colunas"):
            partes.append(f'<h3>Projeção: {_s(metodo["t"])}</h3>')
            colunas = [("ano", "Ano"), *((c["k"], c["t"]) for c in metodo["colunas"])]
            partes.append(_tabela(colunas, metodo["projecao"]))
        if metodo.get("terminal"):
            partes.append(_paragrafo(f'Participação do valor terminal em {metodo["t"]}: {metodo["terminal"]}.'))
    if not partes:
        return "<p>Memória detalhada não disponível neste recorte.</p>"
    return '<details><summary>Abrir fórmulas, resultados intermediários e projeções</summary>' + "".join(partes) + '</details>'


def secoes(doc: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    """Narrativa existente e análise do modelo permanecem em seus próprios cortes."""
    u, m = doc["ativo"], doc["modelo"]
    n = doc.get("nota")
    r = (n["documento"].get("rendered") or {}) if n else {}
    out = _nota_secoes(r, etf=u.get("tipo") == "etf") if r else []
    if u["tipo"] == "etf":
        pergunta = "A exposição ao índice oferece retorno suficiente após custos e riscos da carteira subjacente?"
        indicadores = "Composição efetiva, concentração, taxa de administração, liquidez, spread, prêmio ou desconto ao patrimônio e aderência ao índice."
        invalida = "Mudança material da composição, piora da liquidez ou custos que consumam o retorno esperado."
        contexto = f'{u["nome"]} é analisado pela exposição declarada ao índice {m.get("indice") or "não disponível"}. A visão {u["rating"]} é relativa ao ILF no modelo; não representa uma recomendação individual ou uma avaliação completa do produto.'
    else:
        pergunta, indicadores, invalida = _DILIGENCIA.get(m.get("arquetipo"), _PADRAO)
        contexto = f'{u["nome"]} integra o setor {u["setor_nome"]}, com classificação econômica {u["arquetipo_nome"]} e país {u["pais_nome"]}. Essas classificações orientam a seleção dos métodos; não demonstram vantagem competitiva ou qualidade da gestão.'
    if not r:
        out += [("negocio", "Negócio e enquadramento econômico", _paragrafo(contexto)),
                ("tese", "Questão central da tese", _paragrafo(pergunta) + _paragrafo("Hipótese de diligência a testar. A evidência disponível abaixo sustenta a leitura do modelo, mas ainda não estabelece uma tese qualitativa específica do ativo."))]
    visao = f'O sinal do modelo no retrato de {doc["corte_cobertura"]} é {u["rating"]}.'
    if u["citavel"]:
        visao += f' O preço de referência é {u["preco_texto"]}, o preço-alvo é {u["alvo_texto"]} e o potencial indicado é {u["upside_texto"]}. O retorno esperado com proventos é {u["etr_texto"]}.'
    else:
        visao += " Os portões de qualidade impedem apresentar preço-alvo ou potencial como conclusão citável."
    visao += " O sinal quantitativo não dimensiona posições e pode diferir da narrativa publicada em outra data."
    out += [("visao-modelo", "Visão do modelo e debate de investimento", _paragrafo(visao) + _paragrafo(m.get("rating_motivo") or u.get("motivo")) + _paragrafo("A percepção do mercado e uma divergência fundamentada frente ao consenso precisam de pesquisa própria. O consenso público, quando disponível, não comprova o que está precificado.")),
            ("valuation", "Valuation e premissas", _tabela([("t", "Indicador"), ("v", "Valor no retrato")], m.get("cabecalho") or []) + _tabela([("t", "Método"), ("peso", "Peso"), ("v", "Resultado do método"), ("motivo", "Fundamentação")], m.get("metodos") or []) + _paragrafo("Os valores e as premissas são do modelo aberto. Valores por método são memória de cálculo, inclusive quando o alvo agregado não é citável; não são uma promessa de retorno.")),
            ("monitoramento", "Indicadores, contraponto e critérios de revisão", _paragrafo("Agenda de diligência: " + indicadores) + _paragrafo("Sinais que podem invalidar uma hipótese favorável: " + invalida) + _paragrafo("Confirmar a materialidade desses sinais com documentos do emissor. Eventos sem data confirmada permanecem sem data; não se presume um catalisador futuro."))]
    if m.get("cenarios"):
        out.append(("cenarios-modelo", "Cenários calculados pelo modelo", _tabela([("t", "Cenário"), ("v", "Preço"), ("p", "Probabilidade")], m["cenarios"].get("linhas") or [])))
    if u["tipo"] == "etf":
        out += [("exposicao", "Carteira subjacente e exposição", _tabela([("t", "Indicador"), ("v", "Valor")], m.get("agregados") or []) + _tabela([("nome", "Componente"), ("peso", "Peso")], [{"nome": p.get("nome") or p.get("t"), "peso": p.get("peso_texto") or p.get("peso") or p.get("w")} for p in m.get("posicoes") or []]) + _paragrafo("A composição é a recebida no retrato. Cobertura parcial das posições, preços defasados e exposição cambial limitam a leitura do retorno agregado.")),
                ("diligencia-etf", "Diligência do ETF", _paragrafo("O erro de acompanhamento frente ao ILF compara exposições regionais; não mede a aderência ao índice contratual do ETF. Spread, prêmio ou desconto ao patrimônio, empréstimo de ativos, replicação e regras de rebalanceamento exigem documentos próprios do administrador. Sem esses insumos, a diligência do produto permanece aberta."))]
    out += [("memoria-calculo", "Memória de cálculo do modelo aberto", _memoria(m)),
            ("qualidade", "Qualidade dos dados e condições da análise", _tabela([("t", "Condição"), ("s", "Estado"), ("d", "Detalhe")], m.get("portoes") or []) + _lista(m.get("avisos") or []) + _tabela([("t", "Lacuna"), ("m", "Consequência")], m.get("lacunas") or [])),
            ("insumos", "Resultados, insumos e custo de capital", _tabela([("t", "Insumo"), ("v", "Valor"), ("per", "Período"), ("pub", "Publicação")], m.get("insumos") or []) + _tabela([("t", "Parâmetro"), ("v", "Valor")], m.get("custo_capital") or []))]
    return out


def fontes(doc: Mapping[str, Any]) -> str:
    m = doc["modelo"]
    rows = list(m.get("fontes") or [])
    if doc.get("nota"):
        r = doc["nota"]["documento"].get("rendered") or {}
        rows += [{"doc": f.get("titulo"), "fonte": f.get("instituicao"), "url": f.get("url"), "pub": f.get("publicado_em"), "consulta": f.get("consultado_em"), "id": f.get("id")} for f in r.get("fontes") or []]
    itens = []
    for i, f in enumerate(rows):
        titulo = _s(f.get("doc") or f.get("fonte"))
        url = _url(f.get("url"))
        link = f'<a href="{_s(url)}" rel="noopener noreferrer">{titulo}</a>' if url else titulo
        identificador = f'<b>{_s(f.get("id") or f"M{i + 1}")}</b> · '
        consulta = f' · consulta {_s(f["consulta"])}' if f.get("consulta") else ""
        itens.append(f'<li id="fonte-{i}">{identificador}{link} · {_s(f.get("fonte"))} · publicação {_s(f.get("pub"))}{consulta}</li>')
    return "<ol>" + "".join(itens) + "</ol>" if itens else "<p>Sem fonte pública identificada neste recorte.</p>"


def corpo(doc: Mapping[str, Any]) -> str:
    u = doc["ativo"]
    n = doc.get("nota")
    if doc["estado_pesquisa"] == "nota_publicada":
        r = n["documento"]["rendered"]
        estado = "Narrativa publicada da gestão"
        resumo = r["resumo"]
        sub = f'Visão qualitativa {r.get("stance_pt") or "não disponível"} · nota de {r["data"]} · dados até {r.get("dados_ate") or "não informado"}. Não é uma nova recomendação ou uma atualização dessa nota.'
    else:
        estado = "Análise quantitativa preliminar"
        resumo = "Leitura dos modelos e agenda de investigação. A tese qualitativa específica do ativo ainda depende de pesquisa e publicação de uma nota."
        sub = "O relatório completo do modelo está disponível; a ausência de narrativa publicada não equivale a uma opinião neutra."
    ss = secoes(doc)
    toc = "".join(f'<li><a href="#{_s(k)}">{_s(t)}</a></li>' for k, t, _ in ss) + '<li><a href="#fontes">Fontes e rastreabilidade</a></li>'
    conteudo = "".join(f'<section id="{_s(k)}"><h2>{_s(t)}</h2>{b}</section>' for k, t, b in ss)
    origem = doc["origem_modelo"]["arquivo"]
    return f'''<a class="analise-pular" href="#analise">Ir para a análise</a>
<main class="analise-shell" id="analise">
<p class="analise-voltar"><a href="../">Todas as teses e análises</a> · <a href="../../cases/?ativo={_s(u['iid'])}">Case e comparáveis</a> · <a href="../../risco/">Risco da carteira</a></p>
<header class="analise-capa"><p class="analise-kicker">Tese e análise de investimento · {_s(u['ticker'])}</p>
<h1>{_s(u['nome'])}</h1><p>{_s(u['pais_nome'])} · {_s(u['setor_nome'])} · {_s(u['arquetipo_nome'])}</p>
<p class="analise-estado">{_s(estado)}</p>{_paragrafo(resumo)}<p class="analise-fonte">{_s(sub)}</p>
<p>Retrato quantitativo: {_s(doc['corte_cobertura'])} · preço de {_s(u.get('preco_data'))} · sinal do modelo: {_s(u['rating'])}</p>
<p class="analise-fonte">Pesquisa disponível até {_s(doc.get('corte_pesquisa', doc['corte_cobertura']))}. Narrativa e modelo conservam suas próprias datas; a pesquisa não recalcula o retrato quantitativo.</p>
<nav class="analise-acoes" aria-label="Documento"><a href="analise.md" download>Baixar documento</a><a href="analise.json" download>Dados da análise</a><button type="button" id="analise-imprimir">Imprimir ou salvar PDF</button></nav></header>
<div class="analise-layout"><aside><nav aria-label="Conteúdo da tese"><h2>Nesta análise</h2><ol>{toc}</ol></nav></aside><article>{conteudo}
<section id="fontes"><h2>Fontes e rastreabilidade</h2>{fontes(doc)}
<p>Fontes do modelo e da narrativa conservam suas próprias datas. Data de recebimento, publicação e período financeiro são conceitos distintos.</p>
<p><a href="../../{_s(origem)}">Modelo aberto deste retrato</a> · <a href="../../dados/">Dados abertos e auditoria</a></p>
<details><summary>Identidade dos documentos</summary><p>SHA-256 do fragmento do modelo: <code>{_s(doc['origem_modelo']['sha256'])}</code></p>{'<p>SHA-256 da nota: <code>' + _s(n['sha256']) + '</code></p>' if n else ''}</details>
<p class="analise-fonte">{_s(doc.get('aviso'))} Carteira simulada; pesquisa baseada em dados públicos.</p></section>
</article></div></main>'''


def markdown(doc: Mapping[str, Any]) -> str:
    """Documento portátil com o mesmo conteúdo textual, sem interpretação HTML externa."""
    from html.parser import HTMLParser

    class Texto(HTMLParser):
        def __init__(self):
            super().__init__()
            self.partes = []
            self.ignorar = 0
            self.href = None
            self.cabecalho = False
            self.colunas = 0

        def handle_starttag(self, tag, attrs):
            if tag in {"nav", "aside", "button"}:
                self.ignorar += 1
            if self.ignorar:
                return
            if tag in {"h1", "h2", "h3"}:
                self.partes.append("\n\n" + {"h1": "# ", "h2": "## ", "h3": "### "}[tag])
            elif tag == "li":
                self.partes.append("\n- ")
            elif tag == "table":
                self.partes.append("\n\n")
            elif tag == "tr":
                self.partes.append("| ")
                self.colunas = 0
            elif tag == "th":
                self.cabecalho = True
            elif tag == "a":
                self.href = _url(dict(attrs).get("href"))
                if self.href:
                    self.partes.append("[")

        def handle_data(self, data):
            if not self.ignorar:
                self.partes.append(re.sub(r"([\\`*_\[\]<>|])", r"\\\1", data))

        def handle_endtag(self, tag):
            if tag in {"nav", "aside", "button"}:
                self.ignorar -= 1
                return
            if self.ignorar:
                return
            if tag == "a" and self.href:
                self.partes.append("](" + self.href + ")")
                self.href = None
            if tag == "tr":
                self.partes.append("\n")
                if self.cabecalho:
                    self.partes.append("|" + " --- |" * self.colunas + "\n")
                    self.cabecalho = False
            elif tag in {"p", "h1", "h2", "h3", "li", "section", "header", "table"}:
                self.partes.append("\n\n")
            elif tag in {"td", "th"}:
                self.colunas += 1
                self.partes.append(" | ")

    parser = Texto()
    parser.feed(corpo(doc))
    aviso = "DADOS SIMULADOS\n\n" if doc["dados_simulados"] else ""
    return aviso + re.sub(r"\n{3,}", "\n\n", "".join(parser.partes)).strip() + "\n"


def indice(docs: list[dict[str, Any]]) -> str:
    cards = []
    for d in docs:
        u = d["ativo"]
        estado = "Narrativa publicada" if d["estado_pesquisa"] == "nota_publicada" else "Análise preliminar"
        cards.append(f'<li class="analise-card" data-busca="{_s(u["nome"] + " " + u["ticker"] + " " + u["pais_nome"])}"><a href="{_s(d["endereco"].removeprefix("ativos/"))}"><span>{_s(u["ticker"])} · {_s(u["pais_nome"])}</span><h2>{_s(u["nome"])}</h2><p>{_s(u["setor_nome"])} · {_s(u["rating"])}</p><p>{_s(estado)}</p><b>Ler tese e análise →</b></a></li>')
    n_notas = sum(d["estado_pesquisa"] == "nota_publicada" for d in docs)
    progresso = f'<p>{len(docs)} ativos com página · {n_notas} narrativas publicadas · {len(docs) - n_notas} análises preliminares.</p>'
    return '<main class="analise-shell"><header class="analise-capa"><p class="analise-kicker">Pesquisa por ativo</p><h1>Teses e análises de investimento</h1><p>Uma página dedicada a cada empresa e ETF sob cobertura. Narrativas publicadas e análises preliminares têm estados distintos, fontes e datas visíveis.</p>' + progresso + '</header><label class="analise-busca">Buscar por empresa, ticker ou país<input type="search" id="analise-busca" placeholder="Empresa, ticker ou país"></label><ul class="analise-cards">' + ''.join(cards) + '</ul>' + ("<p>A cobertura está indisponível ou em conferência; nenhuma tese é exibida como válida.</p>" if not docs else "") + '</main>'


CSS = """.analise-shell{max-width:1180px;margin:0 auto;padding:32px 28px 64px;color:var(--ink,#211b16);overflow-wrap:anywhere}
.analise-capa{max-width:900px;padding:24px 0 32px;border-bottom:2px solid #ad8b50}.analise-capa h1{font:600 clamp(2.2rem,5vw,3.8rem)/1.1 Alegreya,Georgia,serif;margin:8px 0 20px}.analise-capa p{line-height:1.65}.analise-kicker{text-transform:uppercase;letter-spacing:.12em;font-size:.75rem}.analise-estado{display:inline-block;border:1px solid #97723a;border-radius:4px;padding:6px 12px;font-weight:600}.analise-layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:48px;margin-top:32px}.analise-layout aside nav{position:sticky;top:20px}.analise-layout aside h2{font-size:1rem}.analise-layout aside ol{padding-left:18px;line-height:1.8;font-size:.9rem}.analise-layout article{min-width:0;max-width:820px}.analise-layout section{padding:8px 0 32px;border-bottom:1px solid #b5a58a;scroll-margin-top:24px}.analise-layout h2{font:600 1.8rem/1.2 Alegreya,Georgia,serif}.analise-layout h3{font-size:1.1rem;margin-top:24px}.analise-layout p,.analise-layout li{line-height:1.75}.analise-fonte{font-size:.86rem;color:var(--muted,#6b6051)}.analise-tabela{overflow-x:auto;margin:20px 0}.analise-tabela table{display:table;border-collapse:collapse;width:100%;font-size:.9rem;min-width:380px}.analise-tabela thead{display:table-header-group}.analise-tabela tbody{display:table-row-group}.analise-tabela tr{display:table-row}.analise-tabela th{white-space:nowrap;overflow-wrap:normal}.analise-tabela td{min-width:110px;overflow-wrap:break-word}.analise-tabela th,.analise-tabela td{display:table-cell;padding:12px;text-align:left;vertical-align:top;border-bottom:1px solid #b5a58a}.analise-acoes{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.analise-acoes a,.analise-acoes button{font:inherit;color:inherit;border:1px solid #97723a;border-radius:4px;padding:8px 12px;background:transparent;cursor:pointer}.analise-shell code{overflow-wrap:anywhere;font-size:.8rem}.analise-pular{position:absolute;left:-9999px}.analise-pular:focus{position:static;padding:12px}.analise-busca{display:block;margin:28px 0;font-weight:600}.analise-busca input{display:block;margin-top:10px;width:min(100%,500px);font:inherit;padding:12px;border:1px solid #97723a;border-radius:4px;background:transparent;color:inherit}.analise-cards{padding:0;list-style:none;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.analise-card{border:1px solid #b5a58a;border-radius:6px}.analise-card a{display:block;padding:24px;color:inherit;text-decoration:none;height:100%}.analise-card a:hover,.analise-card a:focus-visible{outline:2px solid #97723a;outline-offset:3px}.analise-card h2{font:600 1.55rem/1.2 Alegreya,Georgia,serif}.analise-card span{font-size:.8rem}.analise-card[hidden]{display:none}
@media(max-width:800px){.analise-shell{padding:24px 18px}.analise-layout{display:block}.analise-layout aside nav{position:static}.analise-layout aside{margin-bottom:28px}.analise-cards{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:480px){.analise-cards{grid-template-columns:1fr}.analise-acoes{display:block}.analise-acoes a,.analise-acoes button{display:inline-block;margin:4px}}
@media print{.mast,.analise-layout aside,.analise-acoes,.analise-voltar,.analise-busca{display:none!important}.analise-shell{max-width:none;padding:0}.analise-layout{display:block}.analise-layout article{max-width:none}.analise-layout section{break-inside:auto}.analise-capa{max-width:none}.analise-tabela{overflow:visible}h2,h3{break-after:avoid}a{color:inherit}.analise-card{break-inside:avoid}}
"""

JS = """'use strict';
var pesquisa=document.getElementById('analise-busca');
if(pesquisa)pesquisa.addEventListener('input',function(){var q=pesquisa.value.toLocaleLowerCase('pt-BR');document.querySelectorAll('[data-busca]').forEach(function(c){c.hidden=c.dataset.busca.toLocaleLowerCase('pt-BR').indexOf(q)<0;});});
var imprimir=document.getElementById('analise-imprimir');
if(imprimir)imprimir.addEventListener('click',function(){window.print();});
"""
