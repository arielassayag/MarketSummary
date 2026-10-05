"""Decisão do PM do CDP para a semana de 2026-10-05 (mente: claude-code).

Juízos ordinais apenas; nenhum número é calculado aqui. Evidências: notas do pacote de pesquisa
(note_id) e URLs consultadas pela equipe.
"""
import json, sys
W='2026-10-05'
def nid(iid): return f"cdp-{W}-{iid.lower()}"
views = [
 # (issuer, stance, conviction, rationale)
 ("BR_TENDA", 1, 4, "Quant e pesquisa concordam: execução forte e previsível, projeções do ano elevadas após o 2T26 e desalavancagem em curso; a sensibilidade eleitoral é ambígua e fica neutralizada pelo modelo de risco."),
 ("BR_RIACHUELO", 1, 4, "Quant e pesquisa concordam: virada operacional com melhora de margens e de crédito; o risco de beta doméstico é neutralizado pelas restrições de país, setor e choque eleitoral."),
 ("BR_MOURADUBEUX", 1, 4, "Quant e pesquisa concordam: lucro recorde no 2T26, margens em expansão pelo modelo de condomínio, alavancagem quase nula e recompra em curso; a prévia do 3T26 é o próximo teste."),
 ("AR_CEPU", 1, 3, "Quant e pesquisa convergem em geração de energia com receita dolarizada e balanço líquido; o risco-país argentino é fator e fica neutralizado; convicção moderada pela cauda política."),
 ("BR_PAGUEMENOS", 1, 3, "Quant e pesquisa convergem em ganho de margem e desalavancagem; a cadeia de farmácias tem driver próprio, com o beta de consumo neutralizado pelo modelo."),
 ("BR_ALUPAR", 1, 3, "Quant e pesquisa convergem: transmissão com receita regulada e projetos entrando em operação; a sensibilidade a juros é tratada como fator."),
 ("BR_ISAENERGIA", 1, 3, "Quant e pesquisa convergem em receita regulada previsível e dividendos; tese idiossincrática de baixo risco."),
 ("BR_SBF", 1, 3, "Quant e pesquisa convergem em execução de margens e da marca Nike no Brasil; não há linha alugável, então a visão atua só no lado comprado."),
 ("CL_LATAM", 1, 3, "Quant e pesquisa convergem em capacidade disciplinada, geração de caixa e recompras; o petróleo alto é risco, mas a sensibilidade a commodity fica neutralizada."),
 ("BR_PAGS", 1, 3, "Quant e pesquisa convergem em valuation descontado, geração de caixa e retorno ao acionista; risco competitivo em adquirência acompanhado."),
 ("BR_NATURA", 1, 3, "Quant e pesquisa convergem na simplificação após a reorganização societária e na melhora de margens; execução ainda em teste."),
 ("BR_WEG", 1, 3, "Quant e pesquisa convergem em qualidade, carteira de pedidos de transmissão e baixa alavancagem; nome defensivo diante do evento eleitoral."),
 ("CO_GEOPARK", 1, 3, "Quant e pesquisa convergem em ativos produtores com custo baixo e retorno ao acionista; o fator petróleo é neutralizado à parte."),
 ("BR_AURA", 1, 3, "Quant e pesquisa convergem em crescimento de produção de ouro com custos controlados; a sensibilidade ao ouro é neutralizada pela restrição de commodity."),
 ("BR_PAGUEMENOS", 1, 3, "Repetição evitada"),
 ("BR_BRADSAUDE", 1, 2, "Quant positivo e pesquisa construtiva, mas evidência mais curta; convicção baixa."),
 ("BR_PICPAY", 1, 2, "Quant positivo e pesquisa construtiva sobre crescimento da base e rentabilidade, com histórico curto como companhia listada; convicção baixa."),
 ("PE_BVN", 1, 2, "Quant positivo e pesquisa construtiva em ouro e cobre; risco social no sul do Peru limita a convicção."),
 ("BR_AXIA", 1, 2, "Pesquisa construtiva sobre desalavancagem e dividendos; quant levemente positivo; convicção baixa."),
 ("BR_CURY", -1, 2, "Divergência: quant comprado, mas a pesquisa aponta momento idiossincrático desfavorável frente aos pares e sensibilidade negativa a mudanças na política habitacional; reduzir a aposta."),
 ("CL_SQM", -1, 2, "Divergência: quant comprado, mas a pesquisa aponta lítio em queda e oferta chinesa crescente; reduzir a aposta, sem short por risco de squeeze em commodity."),
 ("BR_MARCOPOLO", -1, 2, "Divergência: quant comprado, mas a pesquisa aponta desaceleração de pedidos e base de comparação difícil; reduzir a aposta."),
 ("BR_BBSEG", -1, 2, "Pesquisa cautelosa sobre a renovação do acordo de distribuição com o controlador; estatal tratada como tema neutro."),
 ("BR_CMIN", -1, 2, "Pesquisa negativa com minério de ferro fraco e oferta nova entrando; sem linha alugável, a visão só reduz a exposição comprada."),
 ("MX_VOLARIS", -1, 3, "Quant e pesquisa concordam em pressão de custos e de demanda no México; sem catalisador iminente que gere squeeze; tamanho limitado pela cautela da sentinela."),
 ("BR_MBRF", -1, 2, "Quant e pesquisa concordam em integração desafiadora e ciclo de proteína desfavorável; convicção baixa."),
 ("CO_TECNOGLASS", -1, 2, "Quant e pesquisa concordam em desaceleração e tarifas nos Estados Unidos; convicção baixa."),
 ("PE_SCCO", -1, 2, "Quant e pesquisa levemente negativos no idiossincrático, com valuation esticado; o fator cobre é neutralizado à parte; cautela de squeeze limita o tamanho."),
 ("BR_BTG", 1, 2, "Divergência: quant vendido, pesquisa positiva em crescimento de receita e captação; neutralizar a aposta vendida."),
 ("BR_SABESP", 1, 2, "Divergência: quant vendido, pesquisa positiva em continuidade regulatória com a reeleição em São Paulo; neutralizar a aposta vendida."),
 ("LA_MELI", 1, 2, "Divergência: quant levemente vendido, pesquisa positiva em crescimento e margens; neutralizar a aposta vendida."),
 ("BR_NU", 1, 3, "Divergência: quant levemente vendido, pesquisa positiva em crescimento e rentabilidade com risco eleitoral baixo; inclinar para o lado comprado."),
 ("PE_CREDICORP", 1, 2, "Divergência: quant levemente vendido, pesquisa positiva em rentabilidade e qualidade de crédito; neutralizar a aposta vendida."),
 ("MX_CEMEX", 1, 2, "Pesquisa positiva em desalavancagem e potencial de acordo comercial; neutralizar a aposta vendida até a definição tarifária."),
 ("LA_MILLICOM", 1, 2, "Divergência: o quant sugeria short relevante, mas a pesquisa é construtiva em geração de caixa e aquisições; neutralizar a aposta vendida."),
 ("BR_VIBRA", 1, 2, "Divergência: quant neutro a vendido, pesquisa positiva em margens de distribuição; neutralizar."),
]
seen=set(); vv=[]
for iid,st,cv,r in views:
    if iid in seen or r=="Repetição evitada": continue
    seen.add(iid)
    vv.append({"issuer_id":iid,"stance":st,"conviction":cv,"horizon_weeks":8,"rationale":r,"evidence_ids":[nid(iid)]})
election_no_short = ["BR_COSAN","BR_INTER","BR_EQUATORIAL","BR_ASSAI","BR_SMARTFIT","BR_XP","BR_LOCALIZA","BR_ECORODOVIAS","BR_BRADESCO","BR_STONE","BR_ENEVA","BR_CVC","BR_PICPAY","BR_PAGS","BR_ALUPAR","BR_NATURA","BR_RIACHUELO","BR_SBF","BR_MOURADUBEUX","BR_PAGUEMENOS","BR_PETROBRAS","BR_ENERGISA","BR_EZTEC"]
excl=[]
for iid in election_no_short:
    excl.append({"issuer_id":iid,"no_long":False,"no_short":True,"reason":"Janela do segundo turno: nome que sobe com vitória da oposição; sem shorts novos até após 2026-10-25 (risco de squeeze e evento binário)."})
for iid in ["BR_COPASA","BR_SANEPAR","BR_CEMIG"]:
    excl.append({"issuer_id":iid,"no_long":False,"no_short":True,"reason":"Estatal com tese de privatização ligada ao resultado do segundo turno em 2026-10-25: evento binário com risco de gap; sem shorts novos até a definição."})
excl.append({"issuer_id":"BR_AFYA","no_long":True,"no_short":True,"reason":"Fusão com a Yduqs com relação de troca fixa assinada em 2026-09-23: o preço segue o da Yduqs e os sinais próprios perdem validade; tratar como arbitragem de fusão, fora do livro direcional."})
excl.append({"issuer_id":"BR_YDUQS","no_long":True,"no_short":True,"reason":"Contraparte da fusão com a Afya: evitar par espúrio entre as duas linhas e risco de decisão do CADE."})
journal=[
 {"issuer_id":"BR_TENDA","thesis":"Execução previsível no segmento econômico com projeções elevadas e desalavancagem.","invalidation_criteria":"Revisão para baixo das projeções do ano, piora relevante de distratos ou mudança desfavorável no programa habitacional.","premortem":"A tese falha se o vencedor do segundo turno reduzir subsídios do programa habitacional ou se a curva de juros abrir com força."},
 {"issuer_id":"BR_RIACHUELO","thesis":"Virada operacional do varejo de moda com margem e crédito em melhora.","invalidation_criteria":"Inadimplência da carteira própria voltando a subir ou margem bruta recuando no 3T26.","premortem":"A tese falha se o consumo de baixa renda desacelerar mais que o esperado após o ciclo eleitoral."},
 {"issuer_id":"BR_MOURADUBEUX","thesis":"Incorporadora de alta rentabilidade com alavancagem quase nula e recompra.","invalidation_criteria":"Prévia do 3T26 com nova queda de vendas e lançamentos sem recuperação de ritmo.","premortem":"A tese falha se a demanda no Nordeste seguir fraca e a recompra não sustentar o papel."},
 {"issuer_id":"AR_CEPU","thesis":"Geradora com receita dolarizada e balanço líquido em ambiente de normalização regulatória.","invalidation_criteria":"Retrocesso regulatório no setor elétrico argentino ou controle cambial mais rígido.","premortem":"A tese falha em um choque de risco-país que arraste todos os ativos argentinos, caso a neutralidade de país não absorva o gap."},
 {"issuer_id":"MX_VOLARIS","thesis":"Pressão de custos e demanda doméstica fraca no México.","invalidation_criteria":"Queda forte do petróleo ou acordo comercial que reacenda a demanda; sinais de aumento do short interest.","premortem":"A tese falha se um acordo tarifário com os Estados Unidos gerar rali generalizado em nomes mexicanos de consumo e viagem."},
 {"issuer_id":"LA_MILLICOM","thesis":"Neutralizar o short sugerido pelo quant diante de pesquisa construtiva.","invalidation_criteria":"Deterioração de geração de caixa ou falha na integração das aquisições.","premortem":"A neutralização custa alpha se o sinal quant estiver certo; o custo é limitado pela convicção baixa."},
]
out={"mind":"claude-code","regime":"neutral","risk_posture":"defensiva","abstain":False,
 "market_view":"Primeira carteira do CDP, montada no primeiro pregão após o primeiro turno brasileiro, com resultado mais favorável à oposição do que indicavam as pesquisas e segundo turno em 2026-10-25. O pano de fundo global é de aperto: Fed subindo juros, juro longo americano nas máximas em décadas e dólar forte. O petróleo está alto, o cobre forte e o minério e o lítio fracos. A postura é defensiva durante a janela eleitoral. O livro é neutro em dólar, beta, país, setor, estilos, estatais, sensibilidade a commodities e choque eleitoral, medido pela reação de hoje. O alpha vem do quant, com inclinações da pesquisa onde há concordância. Em nomes domésticos que sobem com vitória da oposição não há shorts novos. Divergências fortes entre quant e pesquisa reduzem a aposta. A fusão Afya e Yduqs fica fora do livro direcional.",
 "what_changed":"Inception: não há carteira nem visões anteriores. A semana estabelece a metodologia: quant como base, pesquisa como inclinação limitada e vetos de risco, e neutralização explícita do fator eleição.",
 "evaluation_last_week":"Não se aplica: primeira semana do fundo, sem teses anteriores a avaliar.",
 "views":vv,"exclusions":excl,"position_journal":journal}
json.dump(out, open(sys.argv[1],'w'), ensure_ascii=False, indent=2)
print(len(vv),'views', len(excl),'exclusions', len(journal),'journal')
