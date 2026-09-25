"""Especificações factuais dos 20 casos do dataset.

Cada especificação contém apenas fatos verificados em fontes públicas durante a
construção do dataset (2026-08-27). Os fatos quantitativos de índice e câmbio
(IDX-*, FX-*) são calculados pelo engine a partir dos arquivos brutos em
data/raw; os fatos de eventos vêm de matérias de imprensa verificadas, citadas
por URL. Nenhum valor aqui foi inventado.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EventFact:
    fact_id: str
    category: str  # news_domestic | news_global | news_corporate | rates | equity
    subject: str
    statement: str
    source_name: str
    url: str
    tier: int = 3
    published_at: str | None = None
    measure_kind: str = "text_only"
    value: float | None = None
    unit: str = "none"
    direction: str = "na"


@dataclass
class CaseSpec:
    date: str
    slug: str
    regime: str
    events: list[EventFact] = field(default_factory=list)
    # (label, evidence_ids, confidence)
    drivers: list[tuple[str, list[str], str]] = field(default_factory=list)
    # (description, severity)
    forbidden: list[tuple[str, str]] = field(default_factory=list)
    notes: str = ""


YAHOO_URL = "https://finance.yahoo.com/quote/%5EBVSP/history/"
YAHOO_NAME = "Yahoo Finance (série ^BVSP; validar contra a B3)"
BCB_PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)
BCB_PTAX_NAME = "Banco Central do Brasil (PTAX via API Olinda)"


CASE_SPECS: list[CaseSpec] = [
    # ============================== CALMA ==============================
    CaseSpec(
        date="2025-01-24",
        slug="semana_estavel_pos_boj",
        regime="calm",
        events=[
            EventFact(
                "GLO-01", "news_global", "Banco do Japão",
                "O Banco do Japão elevou sua taxa básica de juros em 24/01/2025, em decisão acompanhada pelo mercado global.",
                "Investalk BB", "https://investalk.bb.com.br/noticias/mercado/mercado-agora-24-01",
                published_at="2025-01-24",
            ),
            EventFact(
                "GLO-02", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista caiu pelo 5º dia consecutivo em 24/01/2025, fechando a R$ 5,91, com queda de cerca de 2,4% na semana.",
                "UOL Economia",
                "https://economia.uol.com.br/noticias/redacao/2025/01/24/dolar-abre-em-queda-e-caminha-para-quinto-dia-seguido-de-desvalorizacao.htm",
                published_at="2025-01-24",
            ),
        ],
        drivers=[
            ("Sem catalisador dominante: índice praticamente estável na primeira semana da nova gestão dos EUA", ["IDX-02", "FX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que a decisão do Banco do Japão causou o movimento do Ibovespa no dia", "critical"),
        ],
        notes="Semana encerrou 'no zero a zero' segundo a imprensa. Vigilância de IPCA-15 e primeiros movimentos da nova gestão dos EUA no radar.",
    ),
    CaseSpec(
        date="2025-04-30",
        slug="abril_pre_copom",
        regime="calm",
        events=[
            EventFact(
                "NEWS-01", "news_domestic", "Ibovespa (acumulado de abril)",
                "O Ibovespa acumulou alta de cerca de 3,7% em abril de 2025, mês descrito como o mais volátil do ano, encerrando o dia 30 praticamente estável na véspera do feriado de 1º de maio.",
                "CNN Brasil", "https://www.cnnbrasil.com.br/economia/mercado/mercado-financeiro-ibovespa-dolar-30-abril-2025/",
                published_at="2025-04-30",
            ),
            EventFact(
                "GLO-01", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista subiu 0,78% em 30/04/2025, a R$ 5,67, interrompendo oito quedas consecutivas; no mês, recuou cerca de 0,5%.",
                "Nord Investimentos",
                "https://www.nordinvestimentos.com.br/blog/ibovespa-hoje-bolsa-de-valores-ao-vivo-30-de-abril-de-2025/",
                published_at="2025-04-30",
            ),
        ],
        drivers=[
            ("Dia morno de pré-feriado, sem catalisador dominante; mercado aguardava a decisão do Copom da semana seguinte", ["IDX-02", "FX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que o Ibovespa 'esperava a decisão do Copom' como causa comprovada da estabilidade do dia (é contexto reportado, não causa estabelecida)", "warning"),
        ],
        notes="Caso de calma com contexto mensal. Copom elevaria a Selic em 07/05/2025 (caso separado).",
    ),
    CaseSpec(
        date="2025-08-15",
        slug="sexta_estavel_juros_no_radar",
        regime="calm",
        events=[
            EventFact(
                "CORP-01", "news_corporate", "BRF",
                "BRF disparou em 15/08/2025 após a divulgação de seus resultados trimestrais.",
                "UOL Economia",
                "https://economia.uol.com.br/noticias/redacao/2025/08/15/dolar-bolsa-hoje-15-de-agosto-de-2025.htm",
                published_at="2025-08-15",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Câmbio e juros",
                "O dólar comercial recuou 0,35% em 15/08/2025, vendido a R$ 5,398, em dia em que a bolsa fechou estável com o mercado de olho nos juros.",
                "UOL Economia",
                "https://economia.uol.com.br/noticias/redacao/2025/08/15/dolar-bolsa-hoje-15-de-agosto-de-2025.htm",
                published_at="2025-08-15",
            ),
        ],
        drivers=[
            ("Dia sem catalisador dominante: bolsa estável de olho em juros e câmbio em leve queda", ["IDX-02", "FX-02"], "high"),
            ("Resultado da BRF como destaque corporativo isolado", ["CORP-01"], "medium"),
        ],
        forbidden=[
            ("Afirmar que o resultado da BRF puxou o Ibovespa (a imprensa não estabelece essa causalidade agregada)", "critical"),
        ],
        notes="Semana encerrou com alta de 0,31%.",
    ),
    CaseSpec(
        date="2026-07-21",
        slug="lateral_perde_carona_wall_street",
        regime="calm",
        events=[
            EventFact(
                "GLO-01", "news_global", "Petróleo e Oriente Médio",
                "O petróleo atingiu US$ 91 em 21/07/2026, com a tensão no Oriente Médio no radar dos investidores; tarifas comerciais também pesavam no clima de aversão a risco.",
                "G1", "https://g1.globo.com/economia/noticia/2026/07/21/dolar-ibovespa.ghtml",
                published_at="2026-07-21",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Comportamento do índice",
                "O Ibovespa fechou praticamente estável (-0,03%) em 21/07/2026, perdendo a 'carona' de Wall Street, apesar do desempenho positivo de Vale e Petrobras.",
                "Money Times", "https://www.moneytimes.com.br/ibovespa-21-7-26-apsa/",
                published_at="2026-07-21",
            ),
            EventFact(
                "GLO-02", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista caiu cerca de 0,31% em 21/07/2026, fechando a R$ 5,0731.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/money/mercado/mercado-financeiro-ibovespa-dolar-21-julho-2026/",
                published_at="2026-07-21",
            ),
        ],
        drivers=[
            ("Dia lateral: bolsa perde a correlação com Wall Street; câmbio em leve queda com petróleo em alta", ["IDX-02", "FX-02", "GLO-01"], "medium"),
        ],
        forbidden=[
            ("Afirmar que a alta de Vale e Petrobras 'sustentou o índice' como fato estabelecido (imprensa apenas destaca desempenho positivo)", "warning"),
        ],
        notes="Na semana, o Ibovespa havia recuado 1,8% até o dia.",
    ),
    # ========================= MACRO DOMÉSTICO =========================
    CaseSpec(
        date="2025-01-30",
        slug="copom_selic_13_25",
        regime="domestic_macro",
        events=[
            EventFact(
                "RATE-01", "rates", "Taxa Selic",
                "Em 29/01/2025 o Copom elevou a taxa Selic em 1,00 ponto percentual, para 13,25% ao ano, decisão amplamente esperada pelo mercado.",
                "Investalk BB", "https://investalk.bb.com.br/noticias/mercado/mercado-agora-30-01-25",
                published_at="2025-01-30",
                measure_kind="level", value=13.25, unit="pct", direction="up",
            ),
            EventFact(
                "RATE-02", "rates", "Ajuste da Selic",
                "O ajuste de 29/01/2025 do Copom foi de +100 pontos-base na Selic.",
                "Investalk BB", "https://investalk.bb.com.br/noticias/mercado/mercado-agora-30-01-25",
                published_at="2025-01-30",
                measure_kind="change_bps", value=100.0, unit="bps", direction="up",
            ),
            EventFact(
                "GLO-01", "news_global", "Federal Reserve",
                "No mesmo dia (29/01/2025), o Fed manteve os juros inalterados na faixa de 4,25% a 4,50% ao ano.",
                "Investalk BB", "https://investalk.bb.com.br/noticias/mercado/mercado-agora-30-01-25",
                published_at="2025-01-30",
                measure_kind="level", value=4.375, unit="pct", direction="na",
            ),
            EventFact(
                "EQ-01", "equity", "Vale (VALE3)",
                "As ações da Vale subiram cerca de 5% em 30/01/2025, entre os destaques positivos do dia.",
                "Investalk BB", "https://investalk.bb.com.br/noticias/mercado/mercado-agora-30-01-25",
                published_at="2025-01-30",
                measure_kind="return_pct", value=5.0, unit="pct", direction="up",
            ),
        ],
        drivers=[
            ("Reação positiva pós-decisões de juros no Brasil (Copom +100 bps, esperada) e nos EUA (Fed mantém), com dólar em queda contínua", ["RATE-01", "RATE-02", "GLO-01", "IDX-02"], "high"),
            ("Alta de ~5% da Vale entre os destaques do pregão", ["EQ-01"], "medium"),
        ],
        forbidden=[
            ("Afirmar que a alta do dia foi 'causada' pelo Copom sem sinalizar que a decisão já era esperada e que o Fed também decidiu no mesmo dia", "warning"),
            ("Dizer que a Selic subiu para 14% ou qualquer outro nível diferente de 13,25%", "critical"),
        ],
        notes="Decisão do Copom saiu na noite de 29/01; o pregão de 30/01 é a reação. Dólar à vista caiu 0,23% a R$ 5,85, 9ª queda seguida (imprensa).",
    ),
    CaseSpec(
        date="2025-05-08",
        slug="copom_14_75_recorde",
        regime="domestic_macro",
        events=[
            EventFact(
                "RATE-01", "rates", "Taxa Selic",
                "Em 07/05/2025 o Copom elevou a Selic em 0,50 ponto percentual, para 14,75% ao ano, maior patamar em quase 20 anos.",
                "Banco Central do Brasil", "https://www.bcb.gov.br/detalhenoticia/20655/nota",
                tier=1, published_at="2025-05-07",
                measure_kind="level", value=14.75, unit="pct", direction="up",
            ),
            EventFact(
                "RATE-02", "rates", "Ajuste da Selic",
                "O ajuste de 07/05/2025 foi de +50 pontos-base, sexta alta consecutiva do ciclo.",
                "Banco Central do Brasil", "https://www.bcb.gov.br/detalhenoticia/20655/nota",
                tier=1, published_at="2025-05-07",
                measure_kind="change_bps", value=50.0, unit="bps", direction="up",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Tom do comunicado do Copom",
                "O comunicado do Copom de 07/05/2025 adotou tom menos duro, indicando riscos 'mais equilibrados' e alimentando a leitura de que o ciclo de alta de juros estaria próximo do fim.",
                "Valor Investe",
                "https://valorinveste.globo.com/mercados/renda-variavel/bolsas-e-indices/noticia/2025/05/08/ibovespa-bolsa-valores-fechamento-hoje-quinta-8-maio-2025.ghtml",
                published_at="2025-05-08",
            ),
            EventFact(
                "GLO-01", "news_global", "Acordo comercial EUA-Reino Unido",
                "Na noite de 07/05/2025 foi anunciado um acordo comercial entre EUA e Reino Unido, alimentando otimismo com avanços na agenda comercial americana.",
                "CNN Brasil", "https://www.cnnbrasil.com.br/economia/mercado/mercado-financeiro-ibovespa-dolar-8-maio-2025/",
                published_at="2025-05-08",
            ),
        ],
        drivers=[
            ("Ibovespa em recorde histórico (+2,12%) com tom menos restritivo do Copom e otimismo comercial global; dólar em forte queda", ["NEWS-01", "RATE-01", "RATE-02", "GLO-01", "IDX-02", "FX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que o Copom 'cortou' a Selic ou que a taxa ficou abaixo de 14,75%", "critical"),
            ("Atribuir o recorde da bolsa exclusivamente ao Copom, ignorando o contexto global do acordo EUA-Reino Unido", "warning"),
        ],
        notes="Pregão de reação à decisão da véspera. Dólar à vista fechou perto de R$ 5,67 (-1%), menor nível desde meados de 2024 (imprensa).",
    ),
    CaseSpec(
        date="2025-11-05",
        slug="copom_segura_15_recordes",
        regime="domestic_macro",
        events=[
            EventFact(
                "RATE-01", "rates", "Taxa Selic",
                "O Copom manteve a Selic em 15,00% ao ano na reunião de 05/11/2025, sem sinalizar cortes à frente.",
                "G1", "https://g1.globo.com/economia/noticia/2025/11/05/dolar-ibovespa.ghtml",
                published_at="2025-11-05",
                measure_kind="level", value=15.0, unit="pct", direction="na",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Sequência de recordes",
                "O Ibovespa fechou em recorde pela 8ª sessão consecutiva em 05/11/2025 (153.294 pontos, +1,72%), com a decisão de juros no radar.",
                "G1", "https://g1.globo.com/economia/noticia/2025/11/05/dolar-ibovespa.ghtml",
                published_at="2025-11-05",
            ),
            EventFact(
                "GLO-01", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista recuou para a casa de R$ 5,36-5,38 em 05/11/2025.",
                "Bloomberg Línea",
                "https://www.bloomberglinea.com.br/mercados/ibovespa-sobe-com-investidores-a-espera-da-decisao-do-copom-dolar-cai-a-r-538/",
                published_at="2025-11-05",
            ),
        ],
        drivers=[
            ("Euforia acionária com 8º recorde consecutivo na véspera/ dia da decisão do Copom de manter a Selic em 15%", ["NEWS-01", "RATE-01", "IDX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que o Copom cortou ou sinalizou cortes de juros", "critical"),
            ("Afirmar causalidade entre a manutenção da Selic e a alta do dia (decisão saiu após o fechamento; correlação não é causa)", "critical"),
        ],
        notes="A decisão do Copom é divulgada à noite (após o fechamento); a alta do dia antecede a divulgação formal.",
    ),
    CaseSpec(
        date="2026-07-10",
        slug="ipca_abaixo_esperado",
        regime="domestic_macro",
        events=[
            EventFact(
                "NEWS-01", "news_domestic", "IPCA",
                "Dados de inflação (IPCA) abaixo do esperado alimentaram em 10/07/2026 a alta das ações brasileiras, ao aumentar as expectativas de que o Banco Central possa cortar os juros.",
                "UOL Economia",
                "https://economia.uol.com.br/noticias/redacao/2026/07/10/dolar-bolsa-fechamento-hoje-10-de-julho-de-2026.ghtm",
                published_at="2026-07-10",
            ),
            EventFact(
                "GLO-01", "news_global", "Oriente Médio",
                "Tensões no Oriente Médio movimentaram câmbio e commodities em 10/07/2026.",
                "G1", "https://g1.globo.com/economia/noticia/2026/07/10/dolar-ibovespa.ghtml",
                published_at="2026-07-10",
            ),
        ],
        drivers=[
            ("IPCA abaixo do esperado reacende aposta em cortes de juros; bolsa sobe quase 3% e dólar cai", ["NEWS-01", "IDX-02", "FX-02"], "high"),
            ("Melhora do apetite a risco no exterior como fator de apoio", ["GLO-01"], "medium"),
        ],
        forbidden=[
            ("Apresentar como fato a concretização de corte de juros (era expectativa de mercado, não decisão)", "critical"),
        ],
        notes="Expectativa de corte é inferência de mercado reportada pela imprensa; não é decisão do BCB.",
    ),
    # ============================== GLOBAL ==============================
    CaseSpec(
        date="2025-08-22",
        slug="powell_jackson_hole",
        regime="global_macro",
        events=[
            EventFact(
                "GLO-01", "news_global", "Fed / Jackson Hole",
                "Em 22/08/2025, o presidente do Fed, Jerome Powell, sinalizou em Jackson Hole a possibilidade de corte de juros nos EUA já na próxima reunião, impulsionando bolsas globais.",
                "UOL Economia",
                "https://economia.uol.com.br/noticias/redacao/2025/08/22/dolar-bolsa-hoje-22-de-agosto-de-2025.htm",
                published_at="2025-08-22",
            ),
            EventFact(
                "GLO-02", "news_global", "Wall Street",
                "Com o discurso de Powell, o S&P 500 subiu 1,52% (6.466 pontos) e o Nasdaq avançou 1,88% em 22/08/2025.",
                "UOL Economia",
                "https://economia.uol.com.br/noticias/redacao/2025/08/22/dolar-bolsa-hoje-22-de-agosto-de-2025.htm",
                published_at="2025-08-22",
                measure_kind="return_pct", value=1.52, unit="pct", direction="up",
            ),
            EventFact(
                "GLO-03", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista caiu cerca de 0,95% em 22/08/2025, a R$ 5,42.",
                "Nord Investimentos",
                "https://www.nordinvestimentos.com.br/blog/ibovespa-hoje-bolsa-de-valores-ao-vivo-22-de-agosto-de-2025/",
                published_at="2025-08-22",
            ),
        ],
        drivers=[
            ("Sinalização de cortes de juros pelo Fed (Jackson Hole) impulsiona ativos de risco e emergentes; bolsa +2,57% e câmbio em queda", ["GLO-01", "GLO-02", "IDX-02", "FX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que o Fed já cortou os juros (era sinalização de possibilidade)", "critical"),
        ],
        notes="Agosto/2025 fechou como melhor mês do ano para o Ibovespa (+6,28%).",
    ),
    CaseSpec(
        date="2026-01-21",
        slug="rotacao_emergentes_recorde",
        regime="global_macro",
        events=[
            EventFact(
                "GLO-01", "news_global", "Rotação de capitais",
                "Análises do dia apontaram rotação de capitais para fora dos ativos americanos em direção a mercados emergentes em 21/01/2026, beneficiando Ibovespa e real; bolsas latinas como Colômbia, Peru e Chile também avançaram com força.",
                "G1", "https://g1.globo.com/economia/noticia/2026/01/21/dolar-ibovespa.ghtml",
                published_at="2026-01-21",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Recorde do Ibovespa",
                "O Ibovespa disparou 3,33% em 21/01/2026 e fechou, pela primeira vez na história, acima dos 171 mil pontos (171.817).",
                "G1", "https://g1.globo.com/economia/noticia/2026/01/21/dolar-ibovespa.ghtml",
                published_at="2026-01-21",
            ),
            EventFact(
                "GLO-02", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista recuou 1,10% em 21/01/2026, a R$ 5,3209, menor fechamento desde 04/12/2025, com recuo generalizado da moeda americana no exterior.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/money/mercado/mercado-financeiro-ibovespa-dolar-21-janeiro-2026/",
                published_at="2026-01-21",
            ),
        ],
        drivers=[
            ("Rali de emergentes com rotação para fora dos EUA e dólar global mais fraco; recorde histórico do Ibovespa", ["GLO-01", "GLO-02", "NEWS-01", "IDX-02"], "high"),
        ],
        forbidden=[
            ("Atribuir o rali a fatores domésticos específicos não presentes no pacote", "critical"),
        ],
        notes="'Rotação de capitais' é leitura analítica reportada; em dólar, o Ibovespa equivalia a cerca de 32.291 pontos no dia (Jornal do Comércio).",
    ),
    CaseSpec(
        date="2026-03-03",
        slug="guerra_ira_aversao_global",
        regime="global_macro",
        events=[
            EventFact(
                "GLO-01", "news_global", "Guerra EUA-Irã",
                "A guerra entre Estados Unidos e Irã derrubou bolsas globais em 03/03/2026 por aversão a risco, com receio de interrupções no mercado de energia e de pressão inflacionária global.",
                "Bloomberg Línea",
                "https://www.bloomberglinea.com.br/mercados/ibovespa-cai-33-e-dolar-sobe-a-r-527-diante-de-temor-global-com-guerra-no-ira/",
                published_at="2026-03-03",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Sequência de quedas",
                "Em 03/03/2026 o Ibovespa caiu mais de 3%, no quarto dia consecutivo de perdas.",
                "Valor Investe",
                "https://valorinveste.globo.com/mercados/renda-variavel/bolsas-e-indices/noticia/2026/03/03/ibovespa-hoje-3-de-marco-de-2026.ghtml",
                published_at="2026-03-03",
            ),
            EventFact(
                "GLO-02", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista subiu para cerca de R$ 5,27 em 03/03/2026, impulsionado pelo temor global.",
                "Bloomberg Línea",
                "https://www.bloomberglinea.com.br/mercados/ibovespa-cai-33-e-dolar-sobe-a-r-527-diante-de-temor-global-com-guerra-no-ira/",
                published_at="2026-03-03",
            ),
        ],
        drivers=[
            ("Aversão a risco global com guerra EUA-Irã; bolsa cai ~3,3% e dólar sobe", ["GLO-01", "NEWS-01", "IDX-02", "FX-02"], "high"),
        ],
        forbidden=[
            ("Apresentar estimativas próprias de impacto no petróleo ou na inflação como fatos", "critical"),
        ],
        notes="Quarto pregão consecutivo de perdas. A imprensa também cita medo de inflação global com o conflito.",
    ),
    CaseSpec(
        date="2026-03-23",
        slug="alivio_geopolitico_ira",
        regime="global_macro",
        events=[
            EventFact(
                "GLO-01", "news_global", "Adiamento de ataque dos EUA ao Irã",
                "O presidente Trump adiou um ataque contra o Irã, reduzindo tensões no Oriente Médio e trazendo alívio aos mercados em 23/03/2026.",
                "G1", "https://g1.globo.com/economia/noticia/2026/03/23/dolar-ibovespa.ghtml",
                published_at="2026-03-23",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Maior alta do ano",
                "O Ibovespa subiu 3,24% em 23/03/2026 (181.931,93 pontos), maior alta diária desde 21/01/2026.",
                "G1", "https://g1.globo.com/economia/noticia/2026/03/23/dolar-ibovespa.ghtml",
                published_at="2026-03-23",
            ),
            EventFact(
                "GLO-02", "news_global", "Dólar global",
                "Com o alívio geopolítico, o dólar global mais fraco favoreceu moedas de emergentes; o dólar à vista caiu cerca de 1%, perto de R$ 5,18.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/mercado/mercado-financeiro-ibovespa-dolar-23-marco-2026/",
                published_at="2026-03-23",
            ),
        ],
        drivers=[
            ("Alívio geopolítico (adiamento de ataque ao Irã) impulsiona emergentes; bolsa +3,24% e câmbio em queda", ["GLO-01", "NEWS-01", "GLO-02", "IDX-02", "FX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que o conflito EUA-Irã terminou (houve apenas adiamento reportado)", "critical"),
        ],
        notes="Caso espelho do dia 03/03/2026 (crise x alívio), útil para comparar disciplina causal.",
    ),
    # ============================ CORPORATIVO ============================
    CaseSpec(
        date="2025-02-27",
        slug="petrobras_prejuizo_4t24",
        regime="corporate",
        events=[
            EventFact(
                "CORP-01", "news_corporate", "Petrobras (resultado 4T24)",
                "A Petrobras reportou prejuízo de R$ 17 bilhões no 4T24, balanço descrito como decepcionante, e as ações sofreram forte pressão em 27/02/2025.",
                "Investalk BB", "https://investalk.bb.com.br/noticias/mercado/mercado-agora-27-02",
                published_at="2025-02-27",
            ),
            EventFact(
                "EQ-01", "equity", "Petrobras PN (PETR4)",
                "PETR4 fechou em queda de 3,53%, a R$ 36,61, em 27/02/2025.",
                "Investalk BB", "https://investalk.bb.com.br/noticias/mercado/mercado-agora-27-02",
                published_at="2025-02-27",
                measure_kind="return_pct", value=-3.53, unit="pct", direction="down",
            ),
            EventFact(
                "EQ-02", "equity", "Petrobras ON (PETR3)",
                "PETR3 despencou 5,56%, a R$ 39,24, em 27/02/2025.",
                "Investalk BB", "https://investalk.bb.com.br/noticias/mercado/mercado-agora-27-02",
                published_at="2025-02-27",
                measure_kind="return_pct", value=-5.56, unit="pct", direction="down",
            ),
            EventFact(
                "EQ-03", "equity", "Embraer (EMBR3)",
                "Embraer (EMBR3) teve forte alta em 27/02/2025 e ajudou a compensar a queda da Petrobras no índice.",
                "Investalk BB", "https://investalk.bb.com.br/noticias/mercado/mercado-agora-27-02",
                published_at="2025-02-27",
            ),
        ],
        drivers=[
            ("Balanço negativo da Petrobras pressiona PETR4 (-3,53%) e PETR3 (-5,56%), mas o índice termina estável com compensação de Embraer", ["CORP-01", "EQ-01", "EQ-02", "EQ-03", "IDX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que a Petrobras 'derrubou o Ibovespa' (o índice fechou praticamente estável)", "critical"),
            ("Trocar os retornos de PETR3 e PETR4", "critical"),
        ],
        notes="Bom caso para testar distinção entre movimento de ação individual e desempenho do índice.",
    ),
    CaseSpec(
        date="2026-02-11",
        slug="blue_chips_balancos_recordes",
        regime="corporate",
        events=[
            EventFact(
                "CORP-01", "news_corporate", "Itaú Unibanco",
                "O Itaú Unibanco seguia como destaque positivo da temporada de balanços do 4T25; na semana anterior (06/02/2026) o banco fora um dos principais propulsores da bolsa.",
                "G1", "https://g1.globo.com/economia/noticia/2026/02/11/dolar-ibovespa.ghtml",
                published_at="2026-02-11",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Recorde de fechamento",
                "O Ibovespa subiu 2,03% em 11/02/2026 e fechou acima dos 189 mil pontos (189.699) pela primeira vez, 11º recorde do ano; na máxima do dia superou 190 mil pontos.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/mercado/mercado-financeiro-ibovespa-dolar-11-fevereiro-2026/",
                published_at="2026-02-11",
            ),
            EventFact(
                "NEWS-02", "news_domestic", "Falas de Haddad no câmbio",
                "O dólar caiu 0,18%, a R$ 5,187, em 11/02/2026, em sessão em que declarações do ministro Fernando Haddad pesaram no câmbio.",
                "UOL Economia",
                "https://economia.uol.com.br/noticias/redacao/2026/02/11/fecha-dolar-bolsa-hoje-11-de-fevereiro-de-2026.htm",
                published_at="2026-02-11",
            ),
        ],
        drivers=[
            ("Blue chips (Itaú com momentum pós-balanço, Petrobras e Vale) puxam o 11º recorde do ano", ["CORP-01", "NEWS-01", "IDX-02"], "high"),
            ("Câmbio em queda com falas de Haddad e fluxo estrangeiro forte na B3", ["NEWS-02", "FX-02"], "medium"),
        ],
        forbidden=[
            ("Atribuir a alta exclusivamente a balanços (o dia também teve fluxo externo e falas políticas no câmbio)", "warning"),
        ],
        notes="Janeiro/2026 foi o melhor mês da B3 (+12,6%) puxado por estrangeiro, segundo Itaú BBA (contexto).",
    ),
    CaseSpec(
        date="2026-05-07",
        slug="balancos_1t26_petrobras_bradesco",
        regime="corporate",
        events=[
            EventFact(
                "CORP-01", "news_corporate", "Petrobras e Bradesco",
                "As ações da Petrobras e do Bradesco pesaram contra o Ibovespa em 07/05/2026, em dia de bateria de balanços do 1T26.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/mercado/mercado-financeiro-ibovespa-dolar-7-maio-2026/",
                published_at="2026-05-07",
            ),
            EventFact(
                "GLO-01", "news_global", "Petróleo",
                "O petróleo recuou no exterior em 07/05/2026, pressionando as ações de petróleo.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/mercado/mercado-financeiro-ibovespa-dolar-7-maio-2026/",
                published_at="2026-05-07",
            ),
            EventFact(
                "GLO-02", "news_global", "Conflito EUA-Irã",
                "O mercado acompanhava com cautela o conflito no Oriente Médio entre EUA e Irã em 07/05/2026.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/mercado/mercado-financeiro-ibovespa-dolar-7-maio-2026/",
                published_at="2026-05-07",
            ),
            EventFact(
                "GLO-03", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista subiu 0,05% em 07/05/2026, fechando a R$ 4,9233.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/mercado/mercado-financeiro-ibovespa-dolar-7-maio-2026/",
                published_at="2026-05-07",
            ),
        ],
        drivers=[
            ("Queda de 2,38% com pressão de Petrobras e Bradesco em dia cheio de balanços, recuo do petróleo e cautela com o Oriente Médio", ["CORP-01", "GLO-01", "GLO-02", "IDX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que o Ibovespa caiu 'por causa' apenas dos balanços (houve também recuo do petróleo e aversão global)", "warning"),
        ],
        notes="Maio/2026 terminou com queda de ~7%, pior mês em mais de três anos (contexto).",
    ),
    CaseSpec(
        date="2026-07-22",
        slug="previa_vale_2t26",
        regime="corporate",
        events=[
            EventFact(
                "CORP-01", "news_corporate", "Vale (prévia operacional 2T26)",
                "A Vale subiu 3,96% em 22/07/2026 após divulgar prévia operacional do 2º trimestre com maior produção de minério de ferro para um segundo trimestre.",
                "Bloomberg Línea",
                "https://www.bloomberglinea.com.br/mercados/ibovespa-sobe-24-com-impulso-da-vale-apos-previa-acima-do-esperado/",
                published_at="2026-07-22",
                measure_kind="return_pct", value=3.96, unit="pct", direction="up",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Amplitude do pregão",
                "Em 22/07/2026 o Ibovespa subiu 2,44% (177.548 pontos) e, dos 78 ativos do índice, apenas três caíram.",
                "Valor Investe",
                "https://valorinveste.globo.com/mercados/renda-variavel/bolsas-e-indices/noticia/2026/07/22/dolar-e-ibovespa-hoje-22-de-julho-de-2026.ghtml",
                published_at="2026-07-22",
            ),
            EventFact(
                "GLO-01", "news_global", "Tarifas EUA-Brasil",
                "22/07/2026 marcou o primeiro dia de vigência de novas tarifas dos EUA sobre produtos brasileiros.",
                "Folha de S.Paulo",
                "https://www1.folha.uol.com.br/mercado/2026/07/dolar-abre-em-leve-alta-nesta-quarta-no-primeiro-dia-de-novas-tarifas-dos-eua-sobre-o-brasil.shtml",
                published_at="2026-07-22",
            ),
            EventFact(
                "GLO-02", "news_global", "Petróleo",
                "O petróleo disparou em 22/07/2026, com Petrobras acompanhando o movimento.",
                "Money Times", "https://www.moneytimes.com.br/ibovespa-22-7-26-lils/",
                published_at="2026-07-22",
            ),
        ],
        drivers=[
            ("Prévia operacional da Vale acima do esperado (VALE3 +3,96%) é o principal impulso do dia (+2,44%)", ["CORP-01", "NEWS-01", "IDX-02"], "high"),
            ("Petróleo em disparada apoia Petrobras; novas tarifas dos EUA sobre o Brasil entram em vigor sem derrubar a bolsa", ["GLO-01", "GLO-02"], "medium"),
        ],
        forbidden=[
            ("Afirmar que as tarifas dos EUA causaram a queda da bolsa (a bolsa subiu no primeiro dia de vigência)", "critical"),
            ("Trocar o sinal ou o valor do retorno da Vale", "critical"),
        ],
        notes="Weg também avançou (Bloomberg Línea). Dólar fechou em queda no dia.",
    ),
    # ============================== ESTRESSE ==============================
    CaseSpec(
        date="2025-04-04",
        slug="retaliacao_china_panico",
        regime="stress",
        events=[
            EventFact(
                "GLO-01", "news_global", "Retaliação da China",
                "A China anunciou tarifas adicionais de 34% sobre produtos dos EUA em 04/04/2025, em retaliação ao 'tarifaço' de Donald Trump, acirrando temores de guerra comercial global e recessão mundial.",
                "Valor Investe",
                "https://valorinveste.globo.com/mercados/renda-variavel/bolsas-e-indices/noticia/2025/04/04/china-ibovespa-bolsa-valores-cotacao-fechamento-dolar-hoje-sexta-4-abril-2025.ghtml",
                published_at="2025-04-04",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Pior dia desde dezembro",
                "O Ibovespa caiu cerca de 3% em 04/04/2025 (127.256 pontos), pior dia desde dezembro de 2024, devolvendo os ganhos desde 13 de março.",
                "InfoMoney", "https://www.infomoney.com.br/mercados/ibovespa-hoje-bolsa-de-valores-ao-vivo-04042025/",
                published_at="2025-04-04",
            ),
            EventFact(
                "GLO-02", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista disparou 3,68% em 04/04/2025, a R$ 5,83 — maior alta diária em mais de dois anos.",
                "G1", "https://g1.globo.com/economia/noticia/2025/04/04/dolar-ibovespa.ghtml",
                published_at="2025-04-04",
            ),
            EventFact(
                "GLO-03", "news_global", "Wall Street e América Latina",
                "Wall Street tombou na mesma sessão e ativos da América Latina tiveram a maior queda diária desde a pandemia.",
                "Valor Investe",
                "https://valorinveste.globo.com/mercados/renda-variavel/bolsas-e-indices/noticia/2025/04/04/china-ibovespa-bolsa-valores-cotacao-fechamento-dolar-hoje-sexta-4-abril-2025.ghtml",
                published_at="2025-04-04",
            ),
        ],
        drivers=[
            ("Pânico de guerra comercial com retaliação da China: bolsa ~-3%, dólar à vista +3,68% (maior alta em 2 anos), LatAm no pior dia desde a pandemia", ["GLO-01", "NEWS-01", "GLO-02", "IDX-02", "FX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que a recessão global 'aconteceu' (era temor reportado, não constatação)", "critical"),
            ("Ignorar a magnitude do movimento do dólar ao descrever o dia", "warning"),
        ],
        notes="Dia de extrema volatilidade e sinais contraditórios entre classes de ativos.",
    ),
    CaseSpec(
        date="2025-04-09",
        slug="pausa_tarifas_alivio",
        regime="stress",
        events=[
            EventFact(
                "GLO-01", "news_global", "Pausa de 90 dias nas tarifas",
                "O presidente Trump anunciou pausa de 90 dias nas tarifas mais severas da guerra comercial, exceto para a China, gerando forte alívio nos mercados em 09/04/2025.",
                "InfoMoney", "https://www.infomoney.com.br/mercados/ibovespa-hoje-bolsa-de-valores-ao-vivo-09042025/",
                published_at="2025-04-09",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Primeira alta após quatro quedas",
                "O Ibovespa subiu 3,12% em 09/04/2025 (127.795,93 pontos), primeira alta após quatro quedas consecutivas.",
                "InfoMoney", "https://www.infomoney.com.br/mercados/ibovespa-hoje-bolsa-de-valores-ao-vivo-09042025/",
                published_at="2025-04-09",
            ),
            EventFact(
                "GLO-02", "news_global", "Extremos intradia do dólar",
                "O dólar à vista chegou a R$ 6,095 na máxima do dia antes do anúncio e fechou em queda de 2,53%, a R$ 5,8467.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/mercado/mercado-financeiro-ibovespa-dolar-9-abril-2025/",
                published_at="2025-04-09",
            ),
            EventFact(
                "EQ-01", "equity", "Destaques de varejo",
                "Magazine Luiza e um salto do GPA (PCAR3) estiveram entre os destaques positivos do dia 09/04/2025.",
                "InfoMoney", "https://www.infomoney.com.br/mercados/ibovespa-hoje-bolsa-de-valores-ao-vivo-09042025/",
                published_at="2025-04-09",
            ),
        ],
        drivers=[
            ("Rally de alívio com a pausa tarifária: bolsa +3,12% e dólar de +1,47% na véspera para queda de 2,53%, após máximas acima de R$ 6,09", ["GLO-01", "NEWS-01", "GLO-02", "IDX-02"], "high"),
        ],
        forbidden=[
            ("Afirmar que a guerra comercial terminou (houve apenas pausa de 90 dias, com exceção da China)", "critical"),
            ("Omitir a volatilidade extrema do dólar intradia", "warning"),
        ],
        notes="Caso clássico de sinais contraditórios intradia: dólar a R$ 6,095 antes do anúncio e fechando em forte queda.",
    ),
    CaseSpec(
        date="2025-12-05",
        slug="choque_politico_flavio",
        regime="stress",
        events=[
            EventFact(
                "NEWS-01", "news_domestic", "Cenário eleitoral 2026",
                "Em vez do apoio esperado a Tarcísio de Freitas, veio a sinalização de apoio de Jair Bolsonaro ao senador Flávio Bolsonaro como pré-candidato presidencial em 2026, interpretada como cenário de maior risco pelo mercado em 05/12/2025.",
                "G1", "https://g1.globo.com/economia/noticia/2025/12/05/dolar-ibovespa.ghtml",
                published_at="2025-12-05",
            ),
            EventFact(
                "NEWS-02", "news_domestic", "Pior dia do ano",
                "O Ibovespa caiu 4,31% em 05/12/2025 (157.369 pontos), maior queda diária desde fevereiro de 2021, após bater recordes nos pregões anteriores.",
                "Agência Brasil",
                "https://agenciabrasil.ebc.com.br/economia/noticia/2025-12/bolsa-cai-431-em-dia-tenso-e-reverte-inicio-positivo-de-mes",
                published_at="2025-12-05",
            ),
            EventFact(
                "NEWS-03", "news_domestic", "Pressão sobre estatais",
                "Empresas estatais ou com forte participação do governo no Ibovespa, como Petrobras, bancos públicos e Eletrobras, sofreram quedas acentuadas em 05/12/2025.",
                "UOL Economia",
                "https://economia.uol.com.br/noticias/redacao/2025/12/05/mercado-chega-ao-fim-da-semana-com-dolar-a-r-531-ibovespa-recorde.htm",
                published_at="2025-12-05",
            ),
            EventFact(
                "GLO-01", "news_global", "Dólar à vista (fechamento, imprensa)",
                "O dólar à vista disparou mais de 2% em 05/12/2025, fechando a R$ 5,43, maior valor em quase dois meses.",
                "G1", "https://g1.globo.com/economia/noticia/2025/12/05/dolar-ibovespa.ghtml",
                published_at="2025-12-05",
            ),
        ],
        drivers=[
            ("Choque político-eleitoral: leitura de maior risco com o nome de Flávio Bolsonaro derruba a bolsa 4,31% (pior dia desde 2021) e dispara o dólar", ["NEWS-01", "NEWS-02", "NEWS-03", "IDX-02", "FX-02"], "high"),
            ("Pressão concentrada em estatais e empresas com participação governamental", ["NEWS-03"], "medium"),
        ],
        forbidden=[
            ("Afirmar inelegibilidade como fato jurídico consumado (a imprensa fala em incertezas jurídicas)", "warning"),
            ("Atribuir a queda a fatores externos (o choque foi doméstico)", "critical"),
        ],
        notes="A bolsa havia batido recorde histórico nos pregões anteriores; o dia reverteu o início positivo do mês.",
    ),
    CaseSpec(
        date="2026-06-03",
        slug="sinais_contraditorios_junho",
        regime="stress",
        events=[
            EventFact(
                "GLO-01", "news_global", "Novos ataques no Oriente Médio",
                "Novos ataques no Oriente Médio aumentaram a aversão a risco global em 03/06/2026.",
                "CNN Brasil",
                "https://www.cnnbrasil.com.br/economia/money/mercado/mercado-financeiro-ibovespa-dolar-3-junho-2026/",
                published_at="2026-06-03",
            ),
            EventFact(
                "NEWS-01", "news_domestic", "Maior perda em quase um mês",
                "O Ibovespa teve a maior perda em quase um mês em 03/06/2026 (170,3 mil pontos, -2,22%), com perdas acelerando à tarde num dia de consolidação também em Nova York após sequência de recordes.",
                "UOL Economia",
                "https://economia.uol.com.br/noticias/estadao-conteudo/2026/06/03/ibovespa-tem-maior-perda-em-quase-um-mes-aos-1703-mil-pontos.htm",
                published_at="2026-06-03",
            ),
            EventFact(
                "NEWS-02", "news_domestic", "Fatores domésticos acumulados",
                "Saída de capital estrangeiro, juros altos e preocupação fiscal pressionavam a bolsa brasileira no período, enquanto o dólar subia 2,3% no mês de junho.",
                "Forbes Brasil",
                "https://forbes.com.br/geral/2026/06/ibovespa-fecha-junho-em-queda-pelo-4o-mes-seguido-dolar-sobe-23-no-mes/",
                published_at="2026-06-30",
            ),
        ],
        drivers=[
            ("Dia de sinais contraditórios: aversão global (novos ataques), consolidação pós-recordes de Wall Street e fatores domésticos (fluxo, juros, fiscal) somam-se para a maior perda em quase um mês", ["GLO-01", "NEWS-01", "NEWS-02", "IDX-02"], "medium"),
        ],
        forbidden=[
            ("Apontar uma única causa dominante para o dia (as narrativas reportadas são múltiplas e parcialmente contraditórias)", "critical"),
            ("Usar a variação mensal do dólar (+2,3% no mês) como se fosse variação do dia", "critical"),
        ],
        notes="Quarta queda consecutiva em junho (Money Times). Caso pensado para testar honestidade do modelo diante de narrativas concorrentes.",
    ),
]
