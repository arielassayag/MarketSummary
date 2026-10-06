# Guia de estilo do CDP — Cabra da Peste

Versão `cdp-estilo-2026-10-06.1`. Vale para todo texto que chega ao investidor: tese de
investimento, decisão do PM e pesquisa da semana, notas de pesquisa por emissor, comentário
diário de resultado, relatório semanal, alertas e textos do portal escritos por código. O mesmo
texto está no código (`cdp.research.prompts.ESTILO_REGRAS`) e é anexado às regras de cada passo
da mente — tese, PM, comentário diário, nota por emissor e o pacote de `cdp mente pacote` —; o
teste `tests/cdp/test_style_guide.py` confere que as duas versões coincidem.

## Regras

1. Leitor: investidor qualificado e experiente. Escreva como a carta de uma gestora ou o
   relatório de research de primeira linha: português do Brasil, registro institucional, frases
   diretas, voz ativa, um parágrafo por ideia.
2. Vocabulário técnico preciso e sem didatismo: vol ex-ante, beta, risco fatorial e
   idiossincrático, IC, upside até o preço-alvo, EV/EBITDA, ke, prêmio de risco-país (CRP),
   carry, duration. Não defina conceitos básicos nem explique o óbvio.
3. Sem tom promocional: nada de superlativos, adjetivos de venda (excelente, imperdível,
   explosivo), promessas de retorno ou recomendações a terceiros.
4. Sem coloquialismos, gírias, interjeições, exclamações, perguntas retóricas ou emojis.
5. Sem jargão de tecnologia e sem bastidores: não mencione arquivos, formatos de dados, hashes,
   commits, scripts, rotinas, ferramentas nem nomes de assistentes de IA; descreva o processo em
   termos de investimento (modelo quantitativo, comitê, trilha de auditoria).
6. Separe fato de julgamento: fato só com {{fact:<id>}} ou fonte pública citada; julgamento com
   convicção explícita e incerteza em termos ordinais (alta, média, baixa), sem previsões
   pontuais que o código não calculou.
7. Cite fontes primárias públicas (CVM, SEC, B3, relações com investidores, bancos centrais,
   institutos de estatística) pela instituição e pela data; as URLs vão só nos campos de fonte ou
   evidência, nunca no texto.
8. Descreva a carteira, os modelos e a metodologia somente na forma vigente, sem histórico de
   versões do processo.
9. Empresas pelo nome (Petrobras, Vale), nunca pelo identificador interno; tickers só quando for
   preciso distinguir linhas. Datas como 2026-10-25, 25/10/2026 ou 25 de outubro; trimestres como
   3T26.

## Vocabulário

| Prefira | Evite |
|---|---|
| vol ex-ante, volatilidade realizada de curto prazo (a janela vem no fato citado) | "o quanto a carteira balança" |
| risco idiossincrático / específico, risco fatorial | "risco da empresa", "risco do mercado" |
| beta da carteira ao mercado LatAm | "sensibilidade geral" |
| upside até o preço-alvo, retorno total esperado | "potencial de valorização garantido" |
| prêmio de risco-país (CRP), custo de capital próprio (ke) | "taxa de risco" |
| carteira de projetos, carteira de lançamentos | "pipeline" |
| trilha de auditoria, registro íntegro | "hash", "log", "commit" |
| modelo quantitativo, comitê de investimento | "o algoritmo", "o robô", o nome do assistente |
| guidance elevado, mantido, reduzido ou retirado | "a empresa prometeu" |
| convicção alta, média ou baixa | "temos certeza", "com certeza" |

## O que o validador rejeita

Os validadores das saídas da mente recusam números fora de `{{fact:<id>}}` (inclusive por
extenso; algarismos só dentro de fatos, datas, anos, trimestres e nomes de formulários como 20-F
e 6-K nas notas), fatos inexistentes, links, URLs, HTML e emojis no texto. Em todo texto que chega
ao investidor — decisão do PM (`validate`), tese (`validate-tese`), nota por emissor
(`validate-nota`), comentário diário (`validate-daily`) e comentário semanal
(`validate-weekly-report`) — recusam também, pelo guia de estilo (`guardrails.style_problems`,
aplicado em `pm_agent.text_problems`):

- jargão de tecnologia e nomes de assistentes (por exemplo: JSON, hash, commit, pipeline,
  script, prompt, Python, e os nomes dos assistentes de IA);
- registro coloquial ("galera", "tipo assim", "pra", "tá", "né", "kkk");
- tom promocional ("imperdível", "incrível", "sensacional", "espetacular", "explosivo",
  "foguete", "retorno garantido", "oportunidade única");
- ponto de exclamação.

Na decisão do PM, o texto fora do guia é substituído por um texto neutro e o apontamento fica
registrado; nos demais, a validação falha e, esgotadas as tentativas, o código publica o texto
automático. As notas do pacote de pesquisa da semana (insumo interno do PM, não publicado como
texto ao investidor) seguem as regras de números, fatos, evidências e marcação, sem o filtro de
vocabulário.

Os textos escritos pelo código para o investidor seguem as mesmas regras e são varridos pelo
teste do guia de estilo. A única exceção é a linha de autoria do relatório diário ("Autoria:
mente … [IA]"), que identifica a mente para a auditoria e o aplicativo interno; o portal a omite.

## Exemplos

Fora do guia:

> A ação está barata demais! Esperamos uma alta explosiva com o novo pipeline de projetos e o
> modelo (que roda em Python) aponta 35% de upside.

Conforme o guia:

> O modelo aberto aponta preço-alvo de {{fact:val.BR_VALE.preco_alvo}}, potencial de
> {{fact:val.BR_VALE.upside}} sobre o fechamento de referência, com ke de
> {{fact:val.BR_VALE.ke}}. A carteira de projetos de minério de alto teor sustenta a geração de
> caixa no cenário base; o principal risco é a sensibilidade ao preço do minério, de magnitude
> alta e direção incerta (formulário de referência, CVM, 2026-05-29).
