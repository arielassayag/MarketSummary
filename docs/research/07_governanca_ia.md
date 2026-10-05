# Governança e Controles para IA Generativa na Decisão de Investimento (2023–2026) → Requisitos do PM App

> **Documento de pesquisa 07: Fundo LatAm Pure Alpha Long/Short (USD, net neutral, vol-alvo 5% com banda de 3% a 7%)**
> **Data de referência:** segunda-feira, 2026-10-05. Último pregão completo: sexta-feira, 2026-10-02.
> **Escopo:** governança, gestão de risco de modelo e controles para o uso de IA generativa (LLMs e agentes) na decisão de investimento. O documento traduz isso em **requisitos de produto (MUST/SHOULD)** para o app semanal do gestor, mapeados aos módulos do repositório e aos invariantes do `AGENTS.md`.
> **Convenção de evidência:**
> - **[F]** fato verificado em fonte primária (texto do regulador ou do fornecedor, ou o paper) lido nesta sessão.
> - **[S]** fato de fonte secundária (escritório de advocacia, imprensa, blog) não confirmado no texto primário.
> - **[I]** inferência, recomendação ou parâmetro proposto por nós.
>
> **Aviso:** este documento não é parecer jurídico. A aplicabilidade de cada norma depende da estrutura legal do veículo, que pode ser um fundo offshore em USD, um gestor registrado na CVM, um adviser na SEC ou passaporte UE, e deve ser confirmada por advogado.

---

## Sumário executivo

1. **O marco de risco de modelo dos EUA mudou em 2026 e deixou a GenAI de fora.**
   - Em **17/04/2026**, Fed, OCC e FDIC publicaram o **SR 26-2** (OCC Bulletin 2026-13), que **substitui o SR 11-7** (de 04/04/2011) e o SR 21-8.
   - O texto diz que *"Generative AI and agentic AI models are novel and rapidly evolving. As such, they are not within the scope of this guidance"*. Mesmo assim, as práticas de governança da instituição "devem guiar" os controles de ferramentas não cobertas. **[F]**
   - Consequência para nós: os pilares clássicos de MRM continuam valendo para o **modelo de risco, os sinais de alpha e o otimizador**. Esses pilares são inventário, materialidade, *effective challenge*, validação (solidez conceitual, *outcomes analysis*, monitoramento contínuo) e terceiros.
   - Para os **LLMs**, precisamos de um regime próprio, montado a partir de IOSCO, NIST AI 600-1, FINRA, ESMA, ANBIMA e OWASP. **[I]**
2. **Os reguladores de valores mobiliários convergiram em "neutralidade tecnológica + responsabilização humana".**
   - **CVM, Resolução 21, art. 19:** o uso de *"sistemas automatizados ou algoritmos ... não mitiga as responsabilidades do administrador"*, e o **código-fonte deve estar disponível para inspeção da CVM em versão não compilada**. **[F]**
   - **ESMA (30/05/2024):** as decisões *"remain the responsibility of management bodies, irrespective of whether those decisions are taken by people or AI-based tools"*. A ESMA também espera registros do uso de IA, incluindo processos de decisão, fontes de dados, algoritmos e modificações ao longo do tempo. **[F]**
   - **FINRA (Relatório 2026):** espera *logs* de prompts e saídas, além do **registro de qual versão de modelo foi usada e quando**. **[F]/[S]**
3. **A SEC retirou a proposta de *predictive data analytics*, mas mantém a fiscalização pelas regras existentes.**
   - A proposta é de 26/07/2023 e foi retirada em **12/06/2025**, junto com outras 13. **[F]/[S]**
   - O foco continua: as prioridades de exame do FY2026 (17/11/2025) revisam a **acurácia das representações sobre IA** e se há políticas para **supervisionar o uso de IA, inclusive em funções de trading**. **[F]**
   - Houve *AI washing* punido: Delphia (US$ 225 mil) e Global Predictions (US$ 175 mil), em 18/03/2024. **[F]**
   - O chairman Atkins (04/03/2026) disse que a SEC usará as **ferramentas estatutárias existentes**. **[F]**
4. **O EU AI Act é pouco relevante para a decisão de investimento do fundo.**
   - Gestão de carteiras não está no Anexo III (alto risco). O Anexo III, ponto 5, cobra crédito e seguros de pessoas físicas. **[I, com base no texto do Regulamento 2024/1689]**
   - O *Digital Omnibus* adiou as obrigações de alto risco do Anexo III para **02/12/2027** e suavizou o art. 4 (letramento em IA). **[S]**
   - Se houver nexo com a UE, valem as expectativas da ESMA sob a MiFID II. **[F]**
5. **Os controles específicos de LLM com evidência empírica forte formam o núcleo do produto:**
   - **(a)** separação total entre cálculo determinístico e texto. Motivo: no FinanceBench, o GPT-4-Turbo com recuperação **errou ou recusou 81%** das perguntas financeiras. **[F]**
   - **(b)** saídas estruturadas com **IDs de evidência validados em código**.
   - **(c)** verificação de toda afirmação numérica contra o FactBook.
   - **(d)** tratamento de notícias como **conteúdo não confiável**, porque injeção indireta de prompt é viável e trivial (Greshake et al.). **[F]**
   - **(e)** "**LLM só aperta**": a IA pode vetar ou reduzir, nunca ampliar risco.
   - **(f)** pinagem do *snapshot* de modelo e armazenamento da resposta bruta. Motivo: mesmo com modelo pinado e temperatura zero, juízes LLM mudam o veredito em **0,13% a 9,7%** dos itens entre execuções. Além disso, modelos novos da Anthropic **rejeitam `temperature` não padrão**. A reprodutibilidade, portanto, vem de **replay do artefato salvo**, não de reexecução. **[F]**
6. **A evidência sobre *look-ahead* em backtests com LLM é taxativa.**
   - O GPT-4o recupera o nível do S&P 500 com **MAPE de 0,61%** antes do *cutoff*.
   - Instruir o modelo a "ignorar dados após X" não funciona: **98%** de acerto contra **40%** no período realmente fora da amostra (Lopez-Lira, Tang & Zhu). **[F]**
   - A checagem "antes vs. depois do cutoff" também é **não informativa** (Zhang & Stadie, ago/2026). **[F]**
   - **Regra do produto:** nenhuma métrica de valor agregado da IA é aceita fora de janelas **posteriores ao *cutoff*** do modelo exato. A evidência primária passa a ser o **histórico ao vivo/sombra** registrado semanalmente. **[I]**
7. **LLM-as-judge é conselheiro, não oráculo.** Os vieses documentados são:
   - posição: o GPT-4 é consistente em só **65%** das trocas de ordem;
   - autopreferência: +10% para o GPT-4 e +25% para o Claude-v1;
   - falha em aritmética: 14 de 20, caindo para 3 de 20 com resposta de referência;
   - *reward hacking*: a taxa de aprovação subiu de 23,1% para 80,0% sem ganho real de precisão. **[F]**

   Os **gates determinísticos** sempre prevalecem sobre o juiz. **[I]**
8. **Diário de decisão e comitê.** O padrão de mercado é registrar a decisão **antes** do resultado. O registro inclui situação, variáveis, alternativas, probabilidades, estado mental, tese, convicção, catalisadores, critérios de saída e racional de tamanho. As técnicas de apoio são o *pre-mortem* (Klein) e o checklist de vieses (Kahneman, Lovallo & Sibony). O *post-mortem* deve separar processo de resultado. **[F]/[I]**

   O app deve ainda medir o **valor agregado da IA e do gestor**, separando a proposta da IA, a proposta quant e a decisão final. **[I]**
9. **O repositório já cobre parte relevante dos controles:**
   - trilha de auditoria append-only encadeada por hash (`latam_ls.audit`);
   - hashes canônicos (`latam_ls.hashing`);
   - `Decision` com proibição de aprovadores não humanos;
   - `NewsItem.untrusted = True`;
   - `ResearchNote` com `provider/model/prompt_version/input_hash/evidence`;
   - `llm_can_only_tighten`.

   **Lacunas prioritárias [I]:**
   - (i) *ledger* de chamadas LLM com resposta bruta e hash de saída;
   - (ii) registro de prompts e inventário de modelos;
   - (iii) **quatro olhos**, com co-assinatura de risco/compliance independente;
   - (iv) *kill switch* de IA, com degradação para "somente quant";
   - (v) ancoragem externa do hash-cabeça da trilha;
   - (vi) diário de decisão e *post-mortem*;
   - (vii) suíte de avaliação com golden set, injeções e canários;
   - (viii) *gate point-in-time* com `ts_available ≤ T`.

---

## Índice

1. [Aplicabilidade regulatória ao nosso fundo](#1-aplicabilidade-regulatória-ao-nosso-fundo)
2. [Gestão de risco de modelo: do SR 11-7 ao SR 26-2](#2-gestão-de-risco-de-modelo-do-sr-11-7-ao-sr-26-2)
3. [Reguladores e entidades: IOSCO, CFA Institute, FINRA, ESMA, NIST, ANBIMA/APIMEC, OWASP](#3-reguladores-e-entidades)
4. [SEC, CVM e EU AI Act](#4-sec-cvm-e-eu-ai-act)
5. [Controles específicos de LLM](#5-controles-específicos-de-llm)
6. [Humano no circuito, aprovação, auditoria, quatro olhos, pré-trade e *kill switches*](#6-humano-no-circuito-aprovação-auditoria-quatro-olhos-pré-trade-e-kill-switches)
7. [Diário de decisão do PM e comitê de investimentos](#7-diário-de-decisão-do-pm-e-comitê-de-investimentos)
8. [Checklist de requisitos (MUST/SHOULD) mapeado ao app e aos invariantes](#8-checklist-de-requisitos-mustshould)
9. [Tabela de parâmetros](#9-tabela-de-parâmetros)
10. [Fatos vs. inferências, limitações e itens a reverificar](#10-fatos-vs-inferências-limitações-e-itens-a-reverificar)
11. [Fontes](#11-fontes)

---

## 1. Aplicabilidade regulatória ao nosso fundo

| Jurisdição / norma | Status em 05/10/2026 | Como se aplica a nós | Evid. |
|---|---|---|---|
| **CVM Res. 21/2021** (administração de carteiras) | Em vigor desde 01/07/2021 | Aplica-se ao **gestor** se ele for registrado na CVM, inclusive quando gere veículo offshore. Os pontos relevantes são o art. 19 (algoritmos), os arts. 22–26 (controles e risco) e o art. 34 (guarda por 5 anos). | [F] texto / [I] aplicabilidade |
| **CVM Res. 175/2022** (fundos) | Em vigor (consolidada) | Aplica-se diretamente a **fundos brasileiros**. Para um veículo offshore em USD, usamos como *benchmark* de boas práticas: limites, fatores de risco (art. 89), liquidez (art. 92) e estresse (art. 93). | [F]/[I] |
| **CVM Res. 20/2021** + Ofício APIMEC 002/2025 | Ofício de 05/03/2025 | Rege relatórios de analistas. Se o fundo publicar *research*, a IA não pode emitir análise sem supervisão humana, e o analista responde pela veracidade. | [F] |
| **LGPD** (Lei 13.709/2018) | Em vigor | Dados pessoais (cotistas, colaboradores) não devem ir para LLMs de terceiros sem base legal e contrato. | [I] |
| **SEC (Advisers Act)**: Rules 206(4)-7, 204-2, Marketing Rule, Reg S-P | Em vigor; proposta PDA retirada (12/06/2025) | Aplica-se se o gestor for RIA ou ERA nos EUA ou tiver cotistas norte-americanos. Os pontos centrais são políticas escritas, revisão anual, guarda de 5 anos, desempenho hipotético e AI washing. | [F]/[I] |
| **FINRA** (RN 24-09; Relatório 2026) | Orientação | Não se aplica diretamente (somos gestor, não *broker-dealer*), mas é a melhor referência operacional para logs de prompts e saídas e para versionamento de modelo. | [F]/[I] |
| **SR 26-2** (Fed/OCC/FDIC) | 17/04/2026; substitui o SR 11-7 | Não é vinculante para gestores; é o *benchmark* de mercado para MRM. **Exclui GenAI e IA agêntica.** | [F] |
| **PRA SS1/23** (Reino Unido) | Publicada em 17/05/2023; versão em vigor desde 23/04/2026 | É uma referência de MRM que **inclui IA/ML** explicitamente. | [F] |
| **IOSCO** (2021: 6 medidas; 2025: CR/01/2025; 2026: *Supervisory Toolkit*, FR/02/2026) | Toolkit de 25/05/2026 | Orienta os supervisores, CVM inclusive (a CVM integra o grupo de trabalho de IA da IOSCO). Antecipa o que será perguntado em inspeção. | [F]/[S] |
| **ESMA**, *Public Statement* (ESMA35-335435667-5924) | 30/05/2024 | Aplica-se se houver serviço de investimento na UE. É útil como referência de *record keeping*. | [F] |
| **EU AI Act** (Reg. 2024/1689) + *Digital Omnibus* | Em vigor; alto risco do Anexo III adiado para 02/12/2027 | Gestão de carteira **não é alto risco**. Obrigações de GPAI recaem sobre provedores. A relevância para nós é baixa. | [F]/[S]/[I] |
| **NIST AI RMF 1.0 / AI 600-1** | Jul/2024 | Voluntário; serve como taxonomia de riscos de GenAI. | [F] |
| **ANBIMA** (guias de IA de 2024, out/2025 e mar/2026) | Autorregulação (orientativa) | Ciclo de vida, governança, contratação e avaliação de GenAI de terceiros (GAIG). | [F]/[S] |

**Leitura prática [I]:** adotamos o **máximo denominador comum**. Os pilares são:

- responsabilidade humana indelegável (CVM 21, art. 19; ESMA);
- trilha reconstituível com código, prompts, modelos e entradas e saídas (CVM 21, arts. 19 e 34; FINRA; ESMA, §24);
- representações honestas sobre IA (SEC, *AI washing*);
- MRM proporcional para modelos quantitativos (SR 26-2);
- controles próprios de GenAI (NIST AI 600-1, OWASP, IOSCO 2026).

---

## 2. Gestão de risco de modelo: do SR 11-7 ao SR 26-2

### 2.1 O que o SR 26-2 diz (lido no texto primário) [F]

- **Datas e escopo.** SR 26-2 de 17/04/2026, conjunto de Fed, OCC e FDIC. *"Supersedes and replaces SR letter 11-7 ... (issued April 4, 2011) and SR letter 21-8"*. É *"expected to be most relevant to banking organizations with over $30 billion in total assets"*.
- **Natureza.** *"This guidance does not set forth enforceable standards or prescriptive requirements; accordingly, non-compliance with this guidance will not result in supervisory criticism"*. Ações supervisórias, porém, podem decorrer de práticas inseguras.
- **Definição de modelo.** *"A complex quantitative method, system, or approach that applies statistical, economic, or financial theories to process input data into quantitative estimates."* A definição **exclui** *"simple arithmetic calculations ... as well as deterministic rule-based processes and software where there are no statistical, economic, or financial theories underpinning their design or use"*.
- **GenAI fora do escopo.** *"Generative AI and agentic AI models are novel and rapidly evolving. As such, they are not within the scope of this guidance. Nonetheless, a banking organization's risk management and governance practices should guide the determination of appropriate governance and controls for any tools, processes, or systems not covered in this document."* Os princípios **aplicam-se** a modelos estatísticos tradicionais e a *"non-generative, non-agentic AI models"*.
- **Materialidade.** Risco inerente × materialidade, que combina **exposição** e **propósito**. Modelos de alta materialidade *"warrant more comprehensive and rigorous oversight"*. O risco também deve ser avaliado **em agregado**, considerando dependências e premissas e dados comuns.
- ***Effective challenge*.** É a análise crítica feita por especialistas com *"appropriate expertise ... sufficient independence ... organizational standing and influence to effect any change"*.
- **Desenvolvimento e uso.** Exige declaração clara de propósito e testes *out-of-sample* e *out-of-time*. *"Using a model beyond its intended purpose introduces additional uncertainty and risk."*
- **Validação.** Solidez conceitual, *outcomes analysis* (inclusive *back-testing*) e monitoramento contínuo. Uso antes da validação é admitido em urgência, *"placing limits on model use or more closely monitoring its performance"*.
- **Governança.** Papéis claros, conflitos de interesse entre desenvolvimento e validação, inventário de modelos e documentação.
- **Fornecedores.** Os princípios se aplicam mesmo sem acesso a código ou dados, com validação, monitoramento contínuo e análise de resultados.

### 2.2 Implicações para o nosso desenho [I]

| Componente do repo | É "modelo" (SR 26-2)? | Materialidade | Tratamento MRM proposto |
|---|---|---|---|
| Modelo de risco fatorial (`latam_ls.risk`) | **Sim** (estatístico) | **Alta**: define vol ex-ante, beta, neutralidade e o tamanho de todas as posições | Validação independente antes do uso; back-test do previsto vs. realizado (vol e beta) com *bias statistic*; monitoramento semanal |
| Sinais de alpha (`latam_ls.alpha`) | **Sim** | Alta | Testes *out-of-time*; IC realizado vs. assumido (`information_coefficient: 0.04`); decaimento; registro de tentativas |
| Otimizador (`latam_ls.portfolio`) | Sim: aplica teoria financeira (média-variância) | Alta | Testes de viabilidade, sensibilidade a λ, verificação pós-solução das restrições em código separado |
| Modelo de custos e liquidez (impacto raiz quadrada) | Sim | Média | Comparação do custo estimado com o realizado (TCA) após execução |
| Score de *short squeeze* | Sim, heurístico com teoria | Média/Alta (risco de cauda) | *Outcomes analysis* sobre eventos de squeeze; revisão de limiares |
| Motor de compliance pré-trade | **Não**: *"deterministic rule-based"* | — | Fora da definição de modelo, mas sujeito a **testes unitários e controle de mudanças**, como controle interno |
| LLMs de pesquisa (`latam_ls.research`) | **Fora do escopo** (GenAI) | Média: influência limitada por "só aperta" | Regime próprio (§5): inventário, avaliação, logs, pinagem, kill switch, *effective challenge* humano |

Dois pontos de desenho decorrem do SR 26-2:

- **O "modelo" e seus controles são separados.** A verificação de restrições após a otimização deve ser feita por código **independente** do otimizador. É o mesmo princípio do *"deterministic critic"* do OpenPM, que *"guarantees feasibility rather than trusting the LLM"*. **[F] OpenPM; [I] aplicação**
- **Risco agregado.** Alpha, risco e custos compartilham dados de preço e ADTV. Uma falha de dados contamina tudo. Por isso há um **gate de qualidade de dados** antes de qualquer modelo rodar (§6.6).

### 2.3 Referência complementar: PRA SS1/23 [F]

A SS1/23 (publicada em 17/05/2023; versão em vigor desde 23/04/2026) tem cinco princípios:

1. identificação e classificação de modelos;
2. governança;
3. desenvolvimento, implementação e uso;
4. validação independente;
5. mitigantes de risco de modelo.

Ela cobre explicitamente *"the risks associated with the use of artificial intelligence in modelling techniques such as machine learning"*. Usamos a SS1/23 como ponte entre o MRM clássico e a IA. **[F]/[I]**

---

## 3. Reguladores e entidades

### 3.1 IOSCO

**2021: seis medidas** (FR06/2021, reproduzidas no Anexo I do CR/01/2025) **[F]**

1. Alta administração **designada** como responsável por desenvolvimento, testes, implantação, monitoramento e controles de IA/ML. Deve haver governança documentada e um indivíduo sênior que **aprova a implantação inicial e as atualizações substanciais**.
2. Testes e monitoramento **contínuos**, em ambiente **segregado** da produção antes da implantação. O comportamento deve ser verificado em mercado normal e estressado e quanto ao cumprimento de obrigações regulatórias.
3. Habilidades e experiência adequadas. Compliance e risco devem conseguir **entender e desafiar** os algoritmos e fazer *due diligence* de terceiros.
4. Gestão de dependência de **terceiros**, com SLA, indicadores e remédios.
5. Divulgação significativa do uso de IA que afete clientes.
6. Controles de **qualidade de dados** contra vieses, com dados suficientemente amplos.

**2025: CR/01/2025** (mar/2025) **[F]**

- Quatro áreas de risco mais citadas:
  - usos maliciosos;
  - questões de modelo e dados;
  - concentração, terceirização e dependência de terceiros;
  - **interação humano–IA**.
- No ranking de riscos dos respondentes (escala de 1 a 5), lideram cibersegurança (4,26), privacidade (4,11), dados (viés, *drift*, qualidade; 3,94), modelo (explicabilidade; 3,84) e responsabilização (3,83). Alucinações marcaram 3,50 e *herding* 3,28.
- O relatório define **viés de automação**: *"GenAI can produce convincing and seemingly contextually relevant output ... which may lead users to have confidence in AI capabilities, undue trust in its accuracy, and to defer to AI outputs ... a degradation of human skillsets over time"*.
- Uso de IA em asset management observado pelos membros: *robo-advising*/gestão 60% e *investment research* 40%. Citando a Mercer, 90% dos gestores usam ou planejam usar IA na pesquisa. O grupo de trabalho inclui a **CVM**.

**2026: *Supervisory Toolkit for AI Use in Capital Markets*** (FR/02/2026, 25/05/2026) **[S]**

- Cobre o **ciclo de vida completo**, de ML tradicional a **GenAI e IA agêntica**.
- Tem quatro áreas de foco: (i) **governança e gestão de risco**; (ii) **terceiros e terceirização**; (iii) **divulgação**; (iv) **registros e reporte**.
- Traz perguntas práticas para supervisores e indicadores de monitoramento. Uma análise secundária descreve a tipologia de supervisão humana (*human-in-control*, *in-the-loop*, *on-the-loop*, *out-of-the-loop*) e a expectativa de que as firmas demonstrem, **fluxo a fluxo**, qual nível se aplica e o que ocorre quando a acurácia cai abaixo do limiar.
- O PDF primário estava bloqueado (Cloudflare) nesta sessão.

**Implicação [I]:** o app deve declarar, por fluxo, o **nível de autonomia**:

| Fluxo | Nível de autonomia |
|---|---|
| Pesquisa LLM | *Human-in-the-loop* (consultivo) |
| Otimização | Determinística, revisada pelo humano |
| Aprovação e boleta | *Human-in-control* |
| Monitoramento de limites | Automático, com escalonamento |

O app também deve registrar os limiares de acurácia de cada fluxo LLM e a ação de degradação correspondente.

### 3.2 CFA Institute [F]

- ***AI in Asset Management: Tools, Applications, and Frontiers*** (CFA Institute Research Foundation, 18/11/2025). Recomenda *"balance automation with human oversight, while maintaining governance and accountability"* e *"identify where AI adds demonstrable value beyond traditional quantitative methods"*.
- O capítulo 10 (*Ethical AI in Finance*, A. Martirosyan) defende explicabilidade para clientes, conselhos e reguladores, e afirma que *"Human oversight remains critical ... in high-stakes decisions"*. Recomenda também auditorias regulares e governança de dados.
- **[I]** Pelo *Code & Standards* do CFA, o Standard V(A) (diligência e base razoável) e o V(C) (guarda de registros) se aplicam a decisões assistidas por IA: o gestor precisa conseguir **demonstrar a base razoável** de cada decisão. Não verificamos nesta sessão o prazo recomendado pelo CFA para guarda de registros na ausência de regra local (comumente citado como 7 anos).

### 3.3 FINRA [F]/[S]

- **RN 24-09** (27/06/2024): as regras são *"technologically neutral"*. Os sistemas de supervisão devem cobrir *"model risk management, data privacy and integrity, reliability and accuracy"*. As firmas devem *"evaluate Gen AI tools prior to deploying them"*. As regras valem também para IA **embutida em produtos de terceiros**.
- **Relatório de Supervisão 2026** (09/12/2025), seção dedicada a GenAI e agentes:
  - processos formais de revisão e aprovação de casos de uso;
  - testes de privacidade, integridade, confiabilidade e acurácia **antes e depois** de mudanças de modelo;
  - *"prompt and output logs for accountability and troubleshooting"*;
  - *"tracking which model version was used and when"*;
  - revisão humana com checagens regulares de erro e viés.
- Para **agentes**, o relatório pede monitorar acesso e dados, definir onde o humano é obrigatório, *"tracking agent actions and decisions"* e *guardrails* que restrinjam o comportamento.

### 3.4 ESMA, *Public Statement* (30/05/2024) [F]

- Responsabilidade do **órgão de administração** pelas decisões, independentemente de terem sido tomadas por pessoas ou por IA.
- Controle do uso de ferramentas de IA de terceiros pelos funcionários, **com ou sem aprovação** da alta administração. Isso equivale a controlar a *shadow AI*.
- A ESMA cita um estudo de mai/2023 com **~19,5% de respostas alucinadas** no ChatGPT.
- Dados de entrada devem ser *"relevant, sufficient, and representative"*. Pede testes, monitoramento proporcional e **testes de estresse periódicos**, além de treinamento de pessoal sobre riscos, ética e regulação.
- **Registros:** *"records that document the utilisation of AI technologies ... including the decision-making processes, data sources used, algorithms implemented, and any modifications made over time"*.

### 3.5 NIST AI RMF 1.0 e AI 600-1 (*Generative AI Profile*, jul/2024) [F]

O AI 600-1 define 12 riscos. Os relevantes para nós são:

- **Confabulação** (*"confidently stated but erroneous or false content"*);
- **Privacidade de dados**;
- **Configuração humano–IA**, que inclui *"automation bias, over-reliance"*;
- **Integridade da informação**: conteúdo que *"may not distinguish fact from opinion or fiction or acknowledge uncertainties"*;
- **Segurança da informação**;
- **Cadeia de valor e integração de componentes**: integração não transparente de componentes de terceiros e vetting inadequado de fornecedores.

O AI 600-1 mapeia ações para as funções GOVERN, MAP, MEASURE e MANAGE do AI RMF. É a **taxonomia** que usamos no inventário de riscos de IA (requisito GOV-03).

### 3.6 ANBIMA e APIMEC (Brasil)

- **ANBIMA** **[F]/[S]**
  - Guia de boas práticas para uso de sistemas de IA (jul/2024).
  - Guia *"Governança de IA: integrando boas práticas ao longo do ciclo de vida"* (10/10/2025): cobre desenvolvimento, uso, monitoramento e **descomissionamento**, com referência aos princípios da OCDE e ao NIST AI RMF.
  - **GAIG, Guia de Avaliação de IA Generativa** (10/03/2026): metodologia em quatro etapas (risco inerente, questionário de terceiros com *score* de maturidade, risco residual e requisitos de governança) e matriz de taxonomia de riscos.
  - Também há um guia de contratação de sistemas de IA.
- **APIMEC, Ofício 002/2025/SSA** (05/03/2025) **[F]**
  - O analista **responde pela veracidade e integridade** dos relatórios, independentemente do uso de IA.
  - A IA *"não pode ser usada para gerar recomendações ... ou emitir análises sem supervisão humana"* e não é fonte por si só (CVM 20, art. 19, §1º).
  - Toda informação processada por IA deve ser **verificada por humano**.
  - O ofício exige protocolos internos, revisões periódicas e treinamento, e reforça o cumprimento da LGPD.

### 3.7 OWASP Top 10 para Aplicações LLM, versão 2025 [F]

A lista é: LLM01 *Prompt Injection*; LLM02 *Sensitive Information Disclosure*; LLM03 *Supply Chain*; LLM04 *Data and Model Poisoning*; LLM05 *Improper Output Handling*; LLM06 *Excessive Agency*; LLM07 *System Prompt Leakage*; LLM08 *Vector and Embedding Weaknesses*; LLM09 *Misinformation*; LLM10 *Unbounded Consumption*.

Para o nosso app, os mais críticos são:

- **LLM01**: notícias com instruções;
- **LLM05**: saída do LLM tratada como dado e nunca executada;
- **LLM06**: o LLM **não tem ferramentas de escrita**, ordem ou configuração;
- **LLM09**: números e fatos inventados;
- **LLM02**: vazamento do livro e das ordens.

---

## 4. SEC, CVM e EU AI Act

### 4.1 SEC

**Proposta de *predictive data analytics* (PDA)** **[F]/[S]**

- Proposta em **26/07/2023** (Release 2023-140), publicada no Federal Register em 09/08/2023.
- Exigiria que *broker-dealers* e advisers avaliassem conflitos de interesse no uso de tecnologias que *"optimize for, predict, guide, forecast, or direct investment-related behaviors or outcomes"* e os **eliminassem ou neutralizassem**, com políticas e registros.
- **Retirada em 12/06/2025**, junto com outras 13 propostas. Qualquer nova regra exigirá nova proposta.

**O que segue valendo:**

- **Dever fiduciário** e **Rule 206(4)-7**: políticas escritas *"reasonably designed to prevent violation"*, revisão *"no less frequently than annually"* e CCO designado. **[F]**
- **Rule 204-2(e)(1)**: guarda por **5 anos** a partir do fim do exercício, os 2 primeiros em escritório adequado. O inciso (a)(16) exige os papéis que sustentam qualquer cálculo de desempenho divulgado. **[F]**
- ***Marketing Rule*, desempenho hipotético**: em 11/09/2023, **9 advisers** pagaram **US$ 850 mil** por anunciar desempenho hipotético sem políticas que garantam relevância ao público-alvo. Backtests com LLM entram nessa categoria. **[F]**
- ***AI washing*** (18/03/2024): Delphia (**US$ 225 mil**) e Global Predictions (**US$ 175 mil**). O diretor de *enforcement* Grewal disse: *"If you claim to use AI in your investment processes, you need to ensure that your representations are not false or misleading."* **[F]**
- **Prioridades de exame do FY2026** (17/11/2025): *"review for accuracy registrant representations regarding their AI capabilities"* e avaliação de *"policies and procedures to monitor and/or supervise their use of AI technologies, including for tasks related to ... trading functions"*. **[F]**
- **Reg S-P** (emendas de 16/05/2024): programa de resposta a incidentes, notificação *"not later than 30 days"* e supervisão de prestadores de serviço. A conformidade vale 18 meses após a publicação para entidades maiores e 24 meses para menores. **[F]**
- **Sinais de 2026**:
  - Atkins (04/03/2026, FSOC): *"Prescriptive mandates are not the answer to every emerging technology"*; o julgamento humano continua essencial; *"misconduct remains misconduct, regardless of the medium"*. A SEC criou uma *AI Task Force* em ago/2025. **[F]**
  - Brian Daly (diretor da IM, 03/02/2026) se mostrou aberto a *no-action letters* e pilotos. **[F]**
- **Rule 15c3-5 (*market access*)**: aplica-se a *broker-dealers*, não a nós. É, porém, o modelo de controle pré-trade: limites de crédito e capital, rejeição de ordens que *"exceed appropriate price or size parameters"*, checagens regulatórias pré-ordem, controle *"direct and exclusive"*, revisão anual e certificação do CEO. **[F]**

### 4.2 CVM

**Resolução 175 (fundos): deveres do gestor** **[F]**

- **Art. 84**: poderes para os atos necessários à gestão da carteira.
- **Art. 86**: competência para negociar ativos.
- **Art. 88**: ordens com identificação do fundo e da classe; rateio por critérios *"equitativos, preestabelecidos, formalizados e passíveis de verificação"*.
- **Art. 89**: o gestor é responsável pelos limites de composição, concentração **e de concentração em fatores de risco**, e deve avaliar os efeitos de cada operação **antes** de realizá-la. Esta é a base para o **compliance pré-trade com fatores**.
- **Art. 90**: desenquadramento passivo prolongado por **15 dias úteis** exige explicação à CVM.
- **Art. 92**: políticas de liquidez *"consistentes e passíveis de verificação"*.
- **Art. 93**: **testes de estresse periódicos**.
- **Art. 105**: documentação das operações *"atualizada e em perfeita ordem"*; carteira enquadrada.
- **Art. 106**: cuidado e diligência *"que todo homem ativo e probo"*; lealdade.

**Resolução 21 (administração de carteiras)** **[F]**

- **Art. 18**: boa-fé, transparência, diligência e lealdade. O inciso VIII obriga a informar à CVM indícios de violação em até **10 dias úteis**.
- **Art. 19**: *"A prestação de serviço de administração de carteira ... com a utilização de sistemas automatizados ou algoritmos ... **não mitiga as responsabilidades do administrador**. Parágrafo único. O **código-fonte** do sistema automatizado ou o algoritmo deve estar disponível para a inspeção da CVM ... em versão não compilada."*
- **Art. 21**: os integrantes de **comitê de investimento** observam os deveres do art. 18 e as vedações do art. 20.
- **Arts. 22–24**: controles internos efetivos e proporcionais; controle de informação confidencial; **testes periódicos de segurança** dos sistemas; treinamento.
- **Art. 25**: relatório anual de compliance até o último dia útil de abril.
- **Art. 26**: política escrita de risco *"consistente e passível de verificação"*.
  - O diretor de risco envia relatório de exposição **no mínimo mensal** (§2º, II).
  - O gestor ajusta a exposição aos limites (§3º).
  - Os profissionais de risco atuam **com independência** e **não podem atuar na gestão** (§5º). Esta é a base legal para os **quatro olhos com risco independente**.
- **Art. 34**: guarda mínima de **5 anos** de documentos, *"toda a correspondência, interna e externa, todos os papéis de trabalho, relatórios e pareceres"*.

**Leitura do art. 19 para LLMs [I].** O "algoritmo" de um fluxo com LLM inclui o código, os **prompts versionados**, os esquemas de saída, o identificador exato do *snapshot* do modelo, os parâmetros e o pacote de evidências enviado. Como os pesos do modelo de terceiros não são inspecionáveis, a defesa é a **reconstituibilidade**: o app deve permitir reproduzir, para qualquer decisão, o que foi enviado e o que voltou (*replay*), com hashes.

**CVM e IA em 2026 [S].** Há notícias de grupo de trabalho e de uma plataforma de supervisão baseada em IA na própria CVM em 2026. Isso indica supervisão mais intensiva em dados, mas não identificamos norma da CVM específica sobre IA para gestores até esta data.

**PL 2338/2023 (marco legal de IA) [S/I].** Foi aprovado pelo Senado em dez/2024 e seguiu para a Câmara. **Não verificamos o status em 2026.** Deve ser reverificado.

### 4.3 EU AI Act

- **Regulamento (UE) 2024/1689:** entrou em vigor em 01/08/2024. Proibições e letramento (art. 4) valem desde 02/02/2025, e as obrigações de GPAI desde 02/08/2025. **[I: datas do texto do regulamento, não reabertas nesta sessão]**
- ***Digital Omnibus*** **[S]**
  - Acordo político provisório em 06/05/2026, confirmado pelo Conselho em 13/05/2026; em vigor no fim de jul/2026, segundo a Orrick.
  - Alto risco do **Anexo III → 02/12/2027**; Anexo I → 02/08/2028.
  - Marca d'água do art. 50(2) → 02/12/2026; demais transparências em 02/08/2026.
  - **Art. 4** passou de "garantir" letramento para *"support the development of AI literacy"*.
- **Relevância [I]:** o Anexo III, ponto 5, cobre avaliação de crédito de **pessoas físicas** e precificação de seguros de vida e saúde. **Gestão de carteiras e research não são alto risco.** O fundo usaria GPAI como *deployer*, e as obrigações de GPAI recaem sobre os **provedores**. Mantemos letramento em IA e transparência como boas práticas (requisito GOV-06). Se houver distribuição ou serviço na UE, aplicam-se as expectativas da ESMA (§3.4).

---

## 5. Controles específicos de LLM

Cada subseção segue a estrutura **risco → evidência → controle → onde no app**.

### 5.1 Separação entre cálculo determinístico e linguagem

**Risco e evidência:**

- No FinanceBench (150 casos com revisão humana), o **GPT-4-Turbo com *vector store* compartilhado errou ou recusou 81%**: 19% corretas, 13% incorretas, 68% sem resposta.
- Mesmo com o documento no contexto, o melhor desempenho foi **79% corretas, com 17% incorretas**. Os autores alertam para respostas *"hallucinations, out-of-date, logically incorrect, or given with the wrong units"*. **[F]**
- O OpenPM (ago/2026) adota um *"deterministic in-loop risk critic"* porque *"a deterministic projection, not the model, guarantees that the constraints hold"*. **[F]**

**Controles:**

- Invariante 1 do `AGENTS.md`: todo número vem do `FactBook` ou do otimizador.
- O LLM só produz campos **qualitativos ou ordinais**: `stance ∈ [-2,2]`, `confidence ∈ [0,1]`, `no_short`, `no_long`, catalisadores e riscos.
- Esses campos entram no motor quant por uma função **determinística, testada e limitada**: `max_view_tilt_z = 1.5`, `view_information_coefficient = 0.03`.
- **"Só aperta"** (`research.llm_can_only_tighten = True`): o LLM pode **vetar, reduzir limite ou marcar cautela**, mas nunca aumentar peso, limite, gross ou alavancagem.

**No app:**

- `latam_ls.research` produz `ResearchNote` e `View`.
- `latam_ls.portfolio` consome as visões apenas pela função de *tilt*.
- O teste de regressão compara a proposta com e sem a camada LLM e verifica que o risco ex-ante não aumenta acima do teto e que nenhuma posição excede o limite quant.

### 5.2 *Grounding* com IDs de evidência e saídas estruturadas

**Evidência técnica [F]:**

- As *structured outputs* da Anthropic garantem conformidade ao *schema* JSON por *constrained decoding* (*"Always valid ... Type safe"*). Há exceções: **recusa** (`stop_reason: "refusal"`), **corte por `max_tokens`** e diferenças de caixa em *enums*.
- O recurso **não suporta** restrições numéricas (`minimum`/`maximum`) nem de tamanho de *string*. Os **intervalos precisam ser validados em código** (Pydantic).
- A API de *citations* garante que *"citations are guaranteed to contain valid pointers to the provided documents"*, mas é **incompatível com *structured outputs*** (erro 400).

**Controle de desenho [I]:**

- Usar *structured outputs* com `evidence: list[EvidenceRef]`, em que `ref_id` precisa existir no **pacote de evidências** daquela semana: `fact_id` do FactBook, `news_id` do *news pack* ou `filing_id`.
- A **validação de existência** é feita em código. Uma nota com ID inexistente é **rejeitada**, não corrigida.
- Toda tese (`thesis`, `bull_points`, `bear_points`) deve ter **≥ 1 evidência válida**. Afirmações sem evidência são descartadas ou marcadas `unsupported`.
- Como alternativa para trechos literais, fazer duas passagens: *citations* para extrair trechos com ponteiros válidos e depois *structured outputs* sobre os trechos extraídos.
- Guardar o **hash do trecho citado** (`sha256(cited_text)`) para auditoria.

**No app:** `contracts.EvidenceRef` (existe); validador `research.validate_note()` (proposto). A UI mostra, para cada afirmação, o link para o fato ou a notícia de origem.

### 5.3 Verificação de afirmações numéricas

**Controle:**

- O texto gerado pelo LLM **não pode conter números financeiros literais**. Usa *placeholders* `{{fact:ID}}`, resolvidos deterministicamente a partir do FactBook.
- O módulo `fechamento.validation` já implementa `find_unauthorized_numbers()` (regex que ignora tickers, datas e ordinais) e a resolução de *placeholders*. Vamos **reutilizá-lo** no memo semanal do `latam_ls`.
- **Limiar:** **0** números não autorizados. Unidades e sinais são formatados só pelo código (`Fact.formatted`).

**Evidência que motiva [F]:** a ESMA cita 19,5% de respostas alucinadas, e o FinanceBench registra erros de unidade e de direção (*"reporting negative growth when it is actually positive"*).

**No app:** gate `NUMERIC_CLAIMS` no fluxo `IN_REVIEW → APPROVED`. Uma falha **bloqueia** a aprovação e a exportação.

### 5.4 Injeção de prompt vinda de notícias não confiáveis

**Evidência [F]:**

- Greshake et al. (2023) mostram que a recuperação *"blurs the line between data and instructions"* e que *"processing retrieved prompts can act as arbitrary code execution"*.
- As injeções funcionaram *"on the very first attempt"* e persistem na sessão.
- O OWASP classifica o tema como LLM01:2025.

**Controles (em camadas) [I]:**

1. **Sem agência.** O LLM de pesquisa **não tem ferramentas**: não busca na web durante a decisão, não escreve arquivos, não altera configuração nem cria ordens. A coleta de notícias é feita por código antes da chamada (OWASP LLM06).
2. **Separação de canal.** As notícias entram como **dados** delimitados (`<untrusted_news id=...>`), com instrução de sistema para tratá-las como citação, nunca como instrução. São sanitizadas antes: remoção de comentários HTML, caracteres de largura zero, *markdown links* e Base64 longo.
3. **O *schema* não expressa ação.** A saída não tem campos capazes de mudar estado, como "aprovar", "alterar limite" ou "executar". O pior caso de uma injeção é uma **visão enviesada**, limitada pela regra "só aperta" e pela revisão humana.
4. **Detecção.** Heurística de padrões de instrução em notícias (por exemplo, "ignore", "system:", "assistant:"), com um *flag* `suspected_injection` que **remove a notícia do pacote** e registra o evento na trilha.
5. **Testes.** O golden set inclui ao menos 10 notícias com injeções (diretas, ocultas, codificadas, multietapa). O critério é **0% de mudança de estado** e **0% de vazamento de prompt de sistema**.
6. **Invariante 2.** `NewsItem.untrusted: Literal[True]` já existe e precisa ser preservado.

### 5.5 Vazamento de dados e privacidade

**Riscos:**

- vazamento do **livro e das ordens**, que gera risco de *front-running* e de *squeeze* sobre nossos *shorts*;
- MNPI;
- dados pessoais (LGPD; Reg S-P se houver nexo nos EUA);
- *shadow AI* (ESMA).

**Controles [I]:**

- **Minimização.** O LLM recebe só o necessário por emissor: fatos públicos e notícias. **Nunca** recebe o tamanho das posições, preço médio, lista de *shorts* ou ordens pendentes.
- **Contratos.** Usar provedor com retenção zero ou sem treinamento sobre os dados, com DPA. Fazer a avaliação de terceiros com o GAIG da ANBIMA e a medida 4 da IOSCO.
- **Segredos.** Chaves em variáveis de ambiente (já há `.env.example`), nunca no log. A trilha de auditoria guarda **hashes**; as respostas brutas ficam em armazenamento com controle de acesso.
- **MNPI.** Lista restrita aplicada no pré-trade. Notícias de fonte não pública são bloqueadas na ingestão.
- **Incidentes.** Plano de resposta conforme Reg S-P (notificação em ≤ 30 dias, se aplicável) e CVM 21, art. 18, VIII (≤ 10 dias úteis para indícios de violação).

### 5.6 Pinagem de modelo e de versão

**Evidência [F]:**

- A Anthropic dá *"at least 60 days' notice before model retirement for publicly released models"*.
- Exemplo atual: `claude-sonnet-4-5-20250929` foi depreciado em **30/09/2026**, com aposentadoria em **30/11/2026**.
- `temperature`, `top_p` e `top_k` estão **depreciados** a partir do Claude Opus 4.7 e retornam **erro 400** quando recebem valor não padrão.
- *"Pinned and Still Unstable"* (Google, set/2026) mostra que, com modelo pinado e temperatura zero, juízes **mudam o veredito em 0,13% a 9,7% dos itens** entre execuções. Nos itens "apertados", a taxa condicional chega a **~40%**.
- O OpenPM registra que *"MoE serving is not perfectly bit-reproducible even at temperature zero"*.

**Controles [I]:**

- Usar sempre o **ID de snapshot completo** do modelo, nunca um alias móvel. Registrar o ID em `ResearchNote.model`.
- Monitorar a página de depreciações. Ao receber aviso, abrir a **revalidação** (golden set completo) do modelo sucessor. **Proibido** trocar automaticamente.
- **A reprodutibilidade vem do armazenamento, não da reexecução.** Gravar a requisição canônica e a **resposta bruta** com `sha256`. Uma reexecução não serve como evidência de auditoria; a evidência é o **replay** do artefato.
- Uma troca de modelo, de prompt ou de *schema* é uma **mudança de versão** que entra no hash de pesquisa (`research_hash`). A aprovação anterior é invalidada (invariante 3).

### 5.7 Registro de prompts e *ledger* de chamadas

**Evidência [F]:** FINRA 2026 (*"prompt and output logs"*, *"which model version was used and when"*); ESMA, §24; CVM 21, arts. 19 e 34.

**Controle [I]:** cada chamada LLM gera uma entrada no `LLMCallRecord`:

- **Identificação:** `call_id`, `week`, `role` (fundamental, news_sentiment, short_risk, bull_bear_judge, pm), `issuer_id`.
- **Modelo e prompt:** `provider`, `model_snapshot`, `prompt_id`, `prompt_version` (semver) e `prompt_sha256`, `schema_version`.
- **Entrada:** `input_pack_sha256` (FactBook, notícias e filings enviados).
- **Saída:** `request_sha256`, `response_raw_sha256`, `response_path`, `stop_reason`, `parse_ok`, `validation_errors`.
- **Execução:** `latency_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `ts`.
- **Classificação:** `is_synthetic` (provedor demo).

O *ledger* é append-only. Seu hash entra no `research_hash` e, portanto, no `approval_hash`. O **registro de prompts** (`prompts/registry.yaml`, proposto) guarda texto, versão, autor, data, motivo e aprovação de cada mudança. Mudança de prompt passa por **controle de mudança** com quatro olhos e reavaliação no golden set.

### 5.8 Avaliação: golden sets e as ressalvas do LLM-as-judge

**Evidências sobre juízes LLM [F]:**

| Achado | Números |
|---|---|
| Concordância com humanos (Zheng et al., 2023) | GPT-4 vs. especialistas **85%**, contra **81%** entre os próprios humanos (sem empates) |
| Viés de posição | Consistência na troca de ordem: GPT-4 **65%**, GPT-3.5 46,2%, Claude-v1 23,8% |
| Viés de verbosidade (ataque *"repetitive list"*) | Falha: Claude-v1 e GPT-3.5 **91,3%**; GPT-4 8,7% |
| Autopreferência | GPT-4 **+10%** de *win rate* para si; Claude-v1 **+25%** |
| Correção de matemática | Juiz errado em **14/20**; com CoT 6/20; **com resposta de referência 3/20** |
| Não determinismo (2026) | *Flip* por item de **0,13%** (Haiku 4.5) a **5–10%** (Sonnet 4.5); ~40% nos itens apertados. Protocolo: **R ≥ 5 reexecuções** |
| *Reward hacking* (2026) | Aprovação em "alinhamento de raciocínio" de **23,1% → 80,0%** sem ganho de precisão. Agente leu gabarito: **100% reportado vs. 68,1% real** |
| Ordem do esquema | *Rationale* antes do *score*: concordância exata **42,6% → 51,9%** |

**Controles [I]:**

- **Golden set por papel.**
  - Mínimo de **50 casos** por papel LLM no lançamento, com meta de ≥ 200 em 12 meses.
  - ≥ **20%** de casos adversariais: injeção, armadilha numérica, notícia velha, entidade ambígua, notícia de outro emissor homônimo.
  - ≥ **3 canários**: casos impossíveis de passar honestamente. Um *score* perfeito neles indica vazamento.
  - Rótulos feitos por humanos, com dupla revisão nos casos discordantes.
- **Gates determinísticos com veto absoluto:**
  - *schema* válido 100%;
  - IDs de evidência válidos 100%;
  - números não autorizados = 0;
  - sucesso de injeção = 0%;
  - intervalos (`stance`, `confidence`) válidos 100%.
- **Juiz LLM apenas consultivo.**
  - Esquema com *rationale* antes do *score*.
  - Comparação nas **duas ordens**.
  - **R ≥ 5** reexecuções, com intervalo de confiança.
  - Juiz de **família diferente** da do modelo avaliado (evita autopreferência).
  - Resposta de referência para tudo que envolver aritmética.
  - O juiz **nunca** promove um prompt ou modelo sozinho.
- **Holdout congelado e segregado.** Os casos de avaliação não ficam acessíveis ao processo que gera ou otimiza prompts.
- **Métricas de produção.** Taxa de `parse_ok`, taxa de rejeição por evidência inválida, distribuição de `stance` por semana (deriva) e concordância com a decisão final do PM.

### 5.9 *Look-ahead bias* em backtests com LLM

**Evidência [F]:**

- **Glasserman & Lin (set/2023).** Separam *look-ahead* de "efeito distração". Com manchetes anonimizadas, o retorno *in-sample* foi **maior** (+5,89 bps/dia na base raspada; +4,37 na base TR). O conhecimento geral sobre a empresa atrapalha, sobretudo em *large caps*. A anonimização ajuda até fora da amostra.
- **Lopez-Lira, Tang & Zhu (2025).**
  - Antes do *cutoff*, o GPT-4o recupera índices com **MAPE de 0,61%** (S&P 500) e acerta 98,5% do ano das manchetes do WSJ, contra **28,8%** após o *cutoff*.
  - Um *cutoff* fictício por prompt dá **97,6% vs. 98,0%** de acerto, contra **40%** no pós-cutoff real.
  - O mascaramento falha: o modelo reconstrói entidades e datas.
  - Recomendação: avaliar **só após o *cutoff***.
- **Look-Ahead-Bench (jan/2026).** LLMs padrão sofrem **decaimento de alfa de −15 a −22 p.p.** entre o período *in-sample* e o *out-of-sample*. Modelos *point-in-time* ficam estáveis.
- **Zhang & Stadie (ago/2026).** A checagem pré/pós *cutoff* é **não informativa**: 4 de 5 modelos de ponta "falham" mesmo em perguntas resolvidas depois do *cutoff*, por efeito de recência. A medida exige **referência externa**, seja um *cutoff* conhecido ou um controle limpo pareado.
- **OpenPM (ago/2026).** Usa um *gate* por registro, *"enters the state at decision time T only if `ts_available ≤ T`"*, com notícias publicadas mais **30 minutos** de defasagem, certificado de contaminação e checklist de vieses por execução.

**Controles [I]:**

1. **Metadado de *cutoff*.** Cada `model_snapshot` registra o *knowledge cutoff* declarado. Qualquer backtest com LLM em datas **≤ cutoff + 30 dias** recebe o rótulo `CONTAMINATED` e não pode ser usado para afirmar valor agregado, nem internamente nem no marketing (SEC *Marketing Rule*).
2. ***Gate point-in-time*.** Todo dado tem `ts_available`. Preço: fechamento mais defasagem. Notícia: publicação mais ≥ 30 minutos. *Filings*: horário de aceite. Fundamentos: data de divulgação, não fim do trimestre. O snapshot da semana usa apenas `ts_available ≤ sexta 2026-10-02, fechamento`.
3. **Evidência primária = histórico ao vivo/sombra.** Desde a inception, toda segunda-feira registra três propostas: (a) **quant puro**, (b) **quant + IA** e (c) **decisão do PM**. A atribuição semanal mede o valor agregado de cada camada. Antes de **≥ 26 semanas** (cerca de 6 meses) não se afirma valor agregado da IA. **[I]**
4. **Anonimização como diagnóstico.** Rodar periodicamente a mesma nota com o nome do emissor mascarado. Uma divergência grande de `stance` indica distração ou memória e reduz a confiança.
5. **Ledger de tentativas.** Todo backtest e toda variação de prompt são registrados (número de tentativas), para cálculo de *Deflated Sharpe* e PBO (ver docs 01 e 02).

---

## 6. Humano no circuito, aprovação, auditoria, quatro olhos, pré-trade e *kill switches*

### 6.1 Níveis de autonomia por fluxo [I]

| Fluxo semanal (segunda-feira) | Executor | Humano | Nível |
|---|---|---|---|
| Ingestão e snapshot de dados (sexta, fechamento) | Código | Verifica o relatório de qualidade | *on-the-loop* |
| FactBook, risco, alpha, liquidez, squeeze | Código determinístico | Revisa as exceções | *on-the-loop* |
| Pesquisa LLM por emissor | LLM (consultivo) | Lê e aceita ou rejeita cada visão | *in-the-loop* |
| Otimização | Código | Ajusta *overrides* com justificativa | *in-the-loop* |
| Compliance pré-trade | Código (regras) | Risco co-assina os *soft breaches* | *in-the-loop* (quatro olhos) |
| Aprovação da carteira | **Humano (PM)** | — | *in-control* |
| Envio de ordens | Humano/trader | — | *in-control* |
| Monitoramento intra-semana e *kill switch* | Código mais humano | Escalonamento | *on-the-loop* |

### 6.2 Aprovação vinculada a hash (invariante 3) e sem autoaprovação (invariante 4)

**Já existe:**

- `Decision` com `proposal_hash`, `snapshot_hash`, `config_hash`, `research_hash` e `approval_hash`;
- `FORBIDDEN_APPROVERS = {"system","ai","llm","bot","claude",...}`;
- `rationale` com no mínimo 10 caracteres;
- `acknowledged_soft_checks`;
- `conviction` de 1 a 5.

**Ampliar [I]:**

- O `research_hash` passa a incluir o **hash do ledger LLM**, o **hash do registro de prompts** e os **IDs de snapshot** dos modelos.
- O `approval_hash` passa a incluir o **hash do diário de decisão** da semana (tese e critérios de saída), para que a tese aprovada não possa ser reescrita depois.
- **Validação no momento de exportar ou bookar.** O sistema recomputa todos os hashes a partir dos artefatos. Qualquer divergência leva ao estado `BLOCKED` e a um evento de auditoria.

### 6.3 Trilha de auditoria imutável

**Já existe:** `latam_ls.audit.AuditLog`, append-only e encadeado por hash (`prev_hash`, `event_hash`, `verify_chain()`).

**Limitação [I]:** uma cadeia de hash detecta edição parcial, mas **não detecta regravação completa** da cadeia por quem tem acesso de escrita.

**Ampliar:**

- **Ancoragem externa** do hash-cabeça a cada evento de aprovação e diariamente. Opções: commit Git assinado, envio por e-mail ao compliance ou armazenamento WORM (*object lock*).
- O hash-cabeça aparece impresso no memo exportado.
- **Retenção ≥ 5 anos** (CVM 21, art. 34; SEC 204-2), incluindo respostas brutas de LLM, prompts, snapshots, configurações e memos.

### 6.4 Quatro olhos (segregação de funções) [F/I]

**Base:** CVM 21, art. 26, §5º (o risco é independente e não atua na gestão); IOSCO, medida 1 (indivíduo sênior aprova a implantação e mudanças substanciais); SR 26-2 (*effective challenge*).

**Regras do app [I]:**

- O PM **aprova** a carteira. O **Risco/Compliance** (pessoa diferente) **co-assina** obrigatoriamente quando:
  - (a) há qualquer *soft check* reconhecido;
  - (b) um *override* do PM sobre o otimizador passa de **0,50% do NAV** em um nome ou de **5% do NAV** de *turnover* agregado;
  - (c) há um novo *short* com *squeeze* `MEDIUM`;
  - (d) a ex-ante vol fica fora de **[4%, 6%]** (dentro da banda de 3% a 7%, mas longe do alvo);
  - (e) houve mudança de configuração, prompt, modelo ou *schema* desde a última aprovação.
- **Hard limits não admitem *override*.** Só uma mudança formal de configuração, com quatro olhos, os altera, e ela invalida aprovações pendentes.
- Validações: `approver ≠ co_signer`; ambos humanos identificados; o proponente (sistema) nunca aprova.

### 6.5 Compliance pré-trade

**Base:** CVM 175, art. 89 (avaliar efeitos **antes** de operar; fatores de risco); RTS 6 da MiFID II, art. 15 (*price collars*, valor e volume máximos por ordem, limite de mensagens; *override* só temporário, excepcional, verificado pelo risco e autorizado por pessoa designada); Rule 15c3-5 (rejeição pré-ordem). **[F]**

**Checks HARD (bloqueiam a aprovação)**, com valores do `fund.yaml` atual:

| Check | Limite |
|---|---|
| Exposição líquida \|Σw\| | ≤ **1%** do NAV |
| Beta previsto | \|β\| ≤ **0,05** |
| Ex-ante vol | dentro de **[3%, 7%]** (alvo 5%) |
| Peso por nome | long ≤ **4%**; short ≤ **2,5%** |
| Gross | entre **0,5×** e **2,5×** |
| Líquido por país e por setor | ≤ **5%** |
| Estilo | \|exposição líquida\| ≤ **0,15** |
| Dias para liquidar (participação de 20% do ADTV) | long ≤ **3**; short ≤ **2** |
| ADTV mínimo | **US$ 2 mi** |
| Custo de aluguel | ≤ **8% a.a.** |
| *Squeeze* | `HIGH` = veto em *short*; `MEDIUM` = teto de 50% |
| *Short* permitido | apenas em linhas ADR, US-listed ou BR (BTC); cap mínimo de **US$ 500 mi** |
| Lista restrita / MNPI | 0 violações |
| Dados | ausência de dado crítico = bloqueio (nunca zero; invariante 5) |

**Checks SOFT (exigem reconhecimento e co-assinatura):**

- participação de um nome no risco > **8%**;
- risco fatorial > **35%** da variância;
- *turnover* semanal > **60%**;
- vol fora de [4%, 6%].

**Controles de ordem (pós-aprovação, na boleta) [I]:**

- *price collar* de ±**5%** vs. o preço de referência (último fechamento ou VWAP);
- valor máximo por ordem ≤ **1,5% do NAV**;
- volume da ordem ≤ **20%** do ADTV diário (consistente com `participation_rate`);
- *locate* ou aluguel confirmado antes de qualquer *short*.

### 6.6 *Kill switches* (quatro tipos) [I]

1. ***Kill switch* de trading** (análogo ao RTS 6, art. 12 **[F]**, *"cancel immediately, as an emergency measure, any or all of its unexecuted orders"*). Um botão no app gera um evento de auditoria e uma instrução de cancelamento a todos os *brokers*, com identificação da origem de cada ordem.
2. ***Stops* de *drawdown*** (configuração atual):
   - **−3%** a partir do pico → revisão obrigatória da carteira, com co-assinatura de risco;
   - **−5%** → corte de **50% do gross**.
   - É consistente com a prática de plataformas *multi-manager* (−5% → corte de 50%), descrita no documento 01.
3. ***Kill switch* de IA (modo "somente quant").** Desativa a camada LLM, sem permitir decisão "sem pesquisa". É acionado automaticamente quando:
   - um gate determinístico falha em > **5%** das notas da semana;
   - o golden set regride;
   - há injeção suspeita confirmada;
   - o provedor fica indisponível;
   - o modelo pinado é depreciado sem sucessor validado;
   - há anomalia de custo ou latência.

   A proposta segue com `views = []` e o memo exibe a marca "IA DESATIVADA".
4. ***Kill switch* de dados.** Snapshot velho (mais de 1 pregão de defasagem), cobertura de preço < **95%** do universo ou desvio de FX acima do limiar → bloqueio da proposta.

---

## 7. Diário de decisão do PM e comitê de investimentos

### 7.1 Melhores práticas de mercado

- **Diário de decisão** (Farnam Street/Mauboussin, 20/02/2014) **[F]**.
  - Registrar no **momento da decisão**: situação e contexto; enquadramento do problema; variáveis que governam o caso; complicações; **alternativas consideradas e rejeitadas** (e por quê); faixa de resultados possíveis; **resultados esperados com probabilidades**; hora do dia e estado físico e mental.
  - *"The key is looking in this mirror before you act, not after"*, para neutralizar o viés retrospectivo.
- ***Pre-mortem*** (Gary Klein, HBR, set/2007) **[F]**. Supor que a decisão **já fracassou** e listar as causas plausíveis. Isso dá segurança para dissidências. O artigo também cita um ganho de ~30% na identificação de causas via "*prospective hindsight*" **[S, número não verificado nesta sessão]**.
- **Checklist de qualidade de decisão** (Kahneman, Lovallo & Sibony, HBR, jun/2011) **[F: autoria e data; conteúdo I]**. As perguntas cobrem:
  - viés de interesse próprio;
  - heurística afetiva;
  - *groupthink*;
  - saliência;
  - confirmação;
  - disponibilidade;
  - ancoragem;
  - efeito halo;
  - custo afundado;
  - excesso de confiança;
  - negligência de desastre;
  - aversão à perda.
- **CVM 21, art. 21 [F]:** os membros de **comitê de investimento** estão sujeitos aos deveres fiduciários do art. 18. As atas e os papéis de trabalho entram na guarda de 5 anos (art. 34).

### 7.2 Modelo de registro no app (`DecisionJournalEntry`, proposto) [I]

**Por posição nova ou alterada:**

| Campo | Conteúdo / regra |
|---|---|
| `thesis` | 1–3 frases com mecanismo econômico, ligadas às evidências por `EvidenceRef` |
| `variant_perception` | O que o mercado precifica de forma diferente |
| `conviction` | Escala de 1 a 5 (já existe em `Decision`) e **probabilidade explícita** de a tese se confirmar no horizonte |
| `expected_residual_return` | Opcional; vem do motor (alpha), nunca digitado pelo LLM |
| `horizon_weeks` | Padrão de 8 semanas (consistente com `alpha.horizon_weeks`) |
| `catalysts` | Lista com **data esperada** e direção (a estrutura `Catalyst` já existe) |
| `invalidation_criteria` | **Critérios de saída pré-comprometidos**, qualitativos (fato que mata a tese) e quantitativos (ver abaixo) |
| `sizing_rationale` | Por que este tamanho: contribuição ao risco, liquidez, squeeze; texto livre com números vindos do motor |
| `ai_view_vs_decision` | Visão da IA, visão quant e decisão do PM; marca se o PM **divergiu** da IA e por quê |
| `pre_mortem` | Duas ou três causas de fracasso mais plausíveis |
| `bias_checklist` | Respostas sim/não às 12 perguntas, obrigatório em posições ≥ 2% do NAV |
| `dissent` | Registro de opinião contrária de outro membro do comitê, se houver |

**Critérios quantitativos de revisão obrigatória [I]:**

- retorno **residual** acumulado (após fatores) ≤ **−1,5σ** residual do horizonte;
- *squeeze* passa para `HIGH` em um *short*;
- custo de aluguel > **8%**;
- catalisador ultrapassa a data sem ocorrer.

Esses gatilhos geram **alerta** e exigem decisão registrada (manter, reduzir ou zerar). Não executam venda automática.

***Post-mortem* (`PostMortem`, proposto):**

- **Gatilhos:** saída da posição, vencimento do horizonte, acionamento de critério de invalidação, perda acima de 1σ residual e revisão trimestral.
- **Matriz processo × resultado:** "decisão boa/ruim" × "resultado bom/ruim", separando sorte de habilidade.
- **Calibração:** *Brier score* das probabilidades registradas, com curva de calibração trimestral por PM e pela IA.
- **Atribuição por camada:** retorno do quant puro, de quant + IA e da decisão do PM (§5.9, item 3).
- **Lições** que viram mudanças de processo, por meio de controle de mudança.

**Ata do comitê semanal:** participantes, horário, pauta, decisões, votos e dissidências, *soft checks* reconhecidos, *hash* da proposta e *hash* do diário. A ata é um **artefato hasheado** que entra na trilha.

---

## 8. Checklist de requisitos (MUST/SHOULD)

**Legenda dos invariantes do `AGENTS.md`:**

- I1: cálculos só em código.
- I2: *offline-first* e segurança (notícias não confiáveis).
- I3: aprovação vinculada a hash.
- I4: sem autoaprovação.
- I5: dados brutos preservados e ausentes nunca viram zero.
- I6: "DADOS SIMULADOS" explícito.

**Status:** **E** = existe no repo; **P** = parcial; **N** = novo, a implementar.

### 8.1 Governança e MRM

| ID | Requisito | Prior. | Base | Recurso no app / módulo | Invar. | Status |
|---|---|---|---|---|---|---|
| GOV-01 | Inventário de modelos e componentes de IA com dono, propósito, materialidade (alta/média/baixa), data de validação, limitações e status | MUST | SR 26-2; SS1/23; IOSCO M1 | Página "Governança de modelos"; `governance/model_inventory.yaml` | I3 | N |
| GOV-02 | Responsável sênior designado que aprova a implantação e mudanças substanciais de modelo, prompt ou *schema* | MUST | IOSCO M1; CVM 21, arts. 22–23 | Fluxo de controle de mudança com quatro olhos | I4 | N |
| GOV-03 | Registro de riscos de IA pela taxonomia NIST AI 600-1 (confabulação, privacidade, humano–IA, integridade, segurança, cadeia de valor) | SHOULD | NIST AI 600-1 | Documento de risco versionado | — | N |
| GOV-04 | Validação independente dos modelos de risco e alpha antes do uso; *outcomes analysis* semanal (vol e beta previstos vs. realizados) | MUST | SR 26-2, §V | `risk/backtest`; relatório de *bias statistic* | I1 | P |
| GOV-05 | Due diligence de provedores de LLM: retenção de dados, treinamento, SLA, política de depreciação, localização de dados | MUST | IOSCO M4; ESMA, §14; ANBIMA GAIG | Ficha de fornecedor; revisão anual | — | N |
| GOV-06 | Política de uso de IA (inclui *shadow AI*) e treinamento anual do time | SHOULD | ESMA, §§10 e 17–18; CVM 21, art. 24, III; EU AI Act, art. 4 | Documento e registro de treinamento | — | N |
| GOV-07 | Representações externas sobre IA revisadas pelo compliance; nenhuma alegação de valor da IA sem evidência pós-*cutoff* | MUST | SEC *AI washing*; Exam FY2026; *Marketing Rule* | Checklist de marketing; flag `CONTAMINATED` | I6 | N |
| GOV-08 | Revisão anual do programa de compliance e do relatório de controles internos | MUST | Rule 206(4)-7; CVM 21, art. 25 | Exportação anual da trilha e das métricas | — | N |
| GOV-09 | Código-fonte, prompts, *schemas* e configurações versionados e inspecionáveis em forma não compilada | MUST | CVM 21, art. 19 | Repositório Git; registro de prompts | I3 | P |

### 8.2 Controles de LLM

| ID | Requisito | Prior. | Base | Recurso no app / módulo | Invar. | Status |
|---|---|---|---|---|---|---|
| LLM-01 | O LLM nunca calcula retornos, pesos, riscos, rankings ou contribuições; produz só campos qualitativos ou ordinais validados | MUST | FinanceBench; OpenPM | `research` → `View`; testes de contrato | I1 | E/P |
| LLM-02 | "Só aperta": a camada LLM só reduz, veta ou marca cautela; testes de propriedade garantem que não aumenta risco | MUST | ESMA; IOSCO; [I] | `research.llm_can_only_tighten`; teste com e sem IA | I1 | P |
| LLM-03 | Saída estruturada com *schema* versionado; validação Pydantic de intervalos (`stance`, `confidence`) e *enums* | MUST | Docs de *structured outputs* | `ResearchNote` | I1 | E/P |
| LLM-04 | Toda afirmação com ≥ 1 `EvidenceRef` existente no pacote da semana; ID inválido rejeita a nota | MUST | Grounding; ESMA | `research.validate_note()` | I1, I2 | N |
| LLM-05 | 0 números não autorizados no texto; números só via `{{fact:ID}}` | MUST | ESMA (19,5% de alucinação); FinanceBench | Reuso de `fechamento.validation` | I1 | P |
| LLM-06 | Notícias como dados não confiáveis: sanitização, delimitação, detecção de injeção, sem ferramentas para o LLM, *schema* sem campos de ação | MUST | Greshake; OWASP LLM01/05/06 | `NewsItem.untrusted`; `research.sanitize()` | I2 | P |
| LLM-07 | Minimização de dados: o LLM nunca recebe tamanho de posições, *shorts*, ordens nem dados pessoais | MUST | OWASP LLM02; LGPD; Reg S-P | Construtor de *prompt pack* com *allowlist* de campos | I2 | N |
| LLM-08 | Snapshot de modelo pinado (ID completo); proibido alias; troca só após revalidação | MUST | FINRA 2026; aviso de 60 dias da Anthropic | `ResearchNote.model`; inventário | I3 | P |
| LLM-09 | *Ledger* de chamadas LLM com requisição canônica, **resposta bruta**, hashes, modelo, prompt, tokens e custo | MUST | FINRA 2026; ESMA, §24; CVM 21, arts. 19 e 34 | `LLMCallRecord` (novo) | I3 | N |
| LLM-10 | Registro de prompts com versão, hash, autor, motivo e aprovação | MUST | FINRA; IOSCO M1 | `prompts/registry.yaml` | I3, I4 | N |
| LLM-11 | Reprodutibilidade por *replay* do artefato salvo; reexecução não serve como evidência | MUST | *"Pinned and Still Unstable"*; depreciação de `temperature` | Botão "Reproduzir nota" (lê o artefato) | I3 | N |
| LLM-12 | Modo *offline* determinístico (`DemoProvider`) sempre disponível, marcado como simulado | MUST | AGENTS.md | `research.provider = demo` | I2, I6 | E |
| LLM-13 | Orçamento e limite de chamadas, tokens e custo por semana, com alerta | SHOULD | OWASP LLM10 | Config `research.budget` | — | N |
| LLM-14 | Anonimização periódica como diagnóstico de distração e memória (divergência de `stance`) | SHOULD | Glasserman & Lin; Lopez-Lira | Job mensal de diagnóstico | I1 | N |

### 8.3 Avaliação e backtest

| ID | Requisito | Prior. | Base | Recurso no app / módulo | Invar. | Status |
|---|---|---|---|---|---|---|
| EVAL-01 | Golden set por papel (≥ 50 casos, ≥ 20% adversariais, ≥ 3 canários) rodado *offline* no CI | MUST | IOSCO M2; FINRA | `tests/evals/`; `uv run pytest -m evals` | I2 | N |
| EVAL-02 | Gates determinísticos (*schema*, evidência, números, injeção) com veto sobre qualquer juiz LLM | MUST | Wahi 2026; Zheng 2023 | Pipeline de avaliação | I1 | N |
| EVAL-03 | Juiz LLM só consultivo: troca de ordem, R ≥ 5, *rationale* antes do *score*, família diferente, resposta de referência | SHOULD | Zheng 2023; Ayyagari 2026 | Avaliador opcional | — | N |
| EVAL-04 | Holdout congelado, inacessível ao processo de geração e otimização de prompts | MUST | Wahi 2026 (D1) | Diretório segregado; checagem de hash | I5 | N |
| BT-01 | *Gate point-in-time*: todo registro com `ts_available` e uso apenas de `ts_available ≤ T` | MUST | OpenPM | `data.snapshot`; `SourceRecord.point_in_time` | I5 | P |
| BT-02 | Backtests com LLM em janelas ≤ *cutoff* + 30 dias marcados `CONTAMINATED` e excluídos de alegações de desempenho | MUST | Lopez-Lira et al.; Look-Ahead-Bench; *Marketing Rule* | `backtest` + metadado de *cutoff* | I6 | N |
| BT-03 | Registro semanal *shadow* de três trilhas (quant, quant + IA, PM) com atribuição; ≥ 26 semanas antes de afirmar valor da IA | MUST | Zhang & Stadie; [I] | Página "Valor agregado" | I1 | N |
| BT-04 | Ledger de tentativas (backtests, variações de prompt) para *Deflated Sharpe* e PBO | SHOULD | Docs 01 e 02 | `backtest/trials.jsonl` | I3 | N |

### 8.4 Humano no circuito, aprovação e auditoria

| ID | Requisito | Prior. | Base | Recurso no app / módulo | Invar. | Status |
|---|---|---|---|---|---|---|
| HITL-01 | Aprovação humana identificada; aprovadores não humanos proibidos | MUST | CVM 21, art. 19; ESMA | `Decision._human` | I4 | E |
| HITL-02 | Aprovação vinculada aos hashes de snapshot, configuração, pesquisa (ledger LLM, prompts, modelos), proposta e diário | MUST | AGENTS.md; FINRA | `approval_hash` ampliado | I3 | P |
| HITL-03 | Revalidação dos hashes no export e no *booking*; divergência leva a `BLOCKED` | MUST | AGENTS.md | `workflow.verify_integrity()` | I3 | P |
| HITL-04 | Quatro olhos: co-assinatura independente de risco/compliance nos gatilhos do §6.4; `approver ≠ co_signer` | MUST | CVM 21, art. 26, §5º; RTS 6, art. 15(6) | Campo `co_signer` em `Decision` | I4 | N |
| HITL-05 | Nível de autonomia declarado por fluxo, com limiar de acurácia e ação de degradação | SHOULD | IOSCO 2026 | Página "Governança" | — | N |
| HITL-06 | UI que mostra a origem de cada número (FactBook) e de cada afirmação (evidência), deixando claro o que é IA e o que é código | MUST | IOSCO 2025 (viés de automação); NIST (humano–IA) | Cartões com selo "IA" vs. "Calculado" | I1, I6 | N |
| AUD-01 | Trilha append-only encadeada por hash, com `verify_chain()` na abertura do app | MUST | CVM 21, art. 34; SEC 204-2 | `latam_ls.audit` | I3 | E |
| AUD-02 | Ancoragem externa do hash-cabeça a cada aprovação e diariamente (Git assinado, WORM ou e-mail ao compliance) | MUST | [I] | `audit.anchor()` | I3 | N |
| AUD-03 | Retenção ≥ 5 anos de todos os artefatos (respostas brutas, prompts, snapshots, memos, atas) | MUST | CVM 21, art. 34; SEC 204-2 | Política de retenção | I5 | N |
| AUD-04 | Arquivos de entrada nunca alterados; correções geram nova versão com hash | MUST | AGENTS.md | `SnapshotManifest` | I5 | E/P |

### 8.5 Pré-trade, *kill switches* e diário

| ID | Requisito | Prior. | Base | Recurso no app / módulo | Invar. | Status |
|---|---|---|---|---|---|---|
| PTC-01 | Compliance pré-trade determinístico com os checks HARD do §6.5; falha bloqueia a aprovação | MUST | CVM 175, arts. 89 e 105, IV; 15c3-5 | `compliance.run_checks()` → `ComplianceCheck` | I1 | P |
| PTC-02 | Checks SOFT exigem reconhecimento explícito e co-assinatura | MUST | RTS 6, art. 15(6) | `acknowledged_soft_checks` + `co_signer` | I4 | P |
| PTC-03 | Controles de ordem: *price collar*, valor máximo, % do ADTV, *locate* antes do *short* | MUST | RTS 6, art. 15; 15c3-5 | Exportação de boleta com validação | I1 | N |
| PTC-04 | Teste de estresse semanal (cenários históricos e fatoriais) anexado à proposta | MUST | CVM 175, art. 93; ESMA, §21 | `RiskSummary.stress_tests` | I1 | P |
| PTC-05 | Relatório de exposição a risco ao menos mensal para as pessoas designadas | MUST | CVM 21, art. 26, §2º, II | Exportação mensal | I1 | N |
| KS-01 | *Kill switch* de trading: cancelamento imediato de todas as ordens não executadas, com rastreio de origem | MUST | RTS 6, art. 12 | Botão e evento de auditoria | I3 | N |
| KS-02 | *Stops* de *drawdown*: −3% → revisão obrigatória; −5% → corte de 50% do gross | MUST | Config `drawdown`; doc 01 | Monitor diário | I1 | P |
| KS-03 | *Kill switch* de IA com degradação automática para "somente quant" nos gatilhos do §6.6 | MUST | IOSCO; FINRA (agentes) | `research.enabled` + selo "IA DESATIVADA" | I2 | N |
| KS-04 | *Kill switch* de dados: snapshot velho, cobertura baixa ou dado crítico ausente bloqueiam a proposta | MUST | AGENTS.md | `data.quality_gate()` | I5 | N |
| JRN-01 | Diário de decisão por posição (campos do §7.2) obrigatório para aprovar, hasheado na aprovação | MUST | CVM 21, arts. 21 e 34; Mauboussin | `DecisionJournalEntry` | I3 | N |
| JRN-02 | *Pre-mortem* e checklist de vieses obrigatórios em posições ≥ 2% do NAV ou em mudança de sinal | SHOULD | Klein 2007; Kahneman et al. 2011 | Formulário na página de aprovação | — | N |
| JRN-03 | Gatilhos de revisão (−1,5σ residual, *squeeze* `HIGH`, aluguel > 8%, catalisador vencido) geram alerta e exigem decisão registrada | MUST | [I] | Monitor + fila de revisões | I1 | N |
| JRN-04 | *Post-mortem* com matriz processo × resultado, *Brier score* trimestral (PM e IA) e lições virando controle de mudança | SHOULD | Mauboussin; [I] | `PostMortem` + página "Aprendizado" | I1 | N |
| JRN-05 | Ata do comitê semanal hasheada (participantes, votos, dissidências) | SHOULD | CVM 21, art. 21 | Artefato `ic_minutes` | I3 | N |
| SIM-01 | Todo artefato derivado de dados demo ou sintéticos exibe e exporta "DADOS SIMULADOS" | MUST | AGENTS.md | `SIMULATED_DATA_NOTICE` | I6 | E |

**Prioridade de implementação [I]:**

- **Onda 1 (antes da 1ª aprovação real):** LLM-01/03/04/05/06/07/08/09, HITL-01/02/03/04, AUD-01/02, PTC-01/02, KS-03/04, JRN-01, BT-01/02, SIM-01.
- **Onda 2 (até 30 dias):** EVAL-01/02/04, LLM-10/11, BT-03, PTC-03/04, KS-01/02, JRN-03, GOV-01/02/05/07/09.
- **Onda 3 (até 90 dias):** os demais SHOULD.

---

## 9. Tabela de parâmetros

| Parâmetro | Valor | Racional / fonte | Tipo |
|---|---|---|---|
| Retenção de registros | **≥ 5 anos** (2 em acesso imediato) | CVM 21, art. 34; SEC 204-2(e)(1) | [F] |
| Aviso de depreciação de modelo | ≥ **60 dias** (Anthropic) | Docs de depreciação | [F] |
| Prazo interno de revalidação após aviso | ≤ **30 dias** | Metade do aviso mínimo | [I] |
| Troca automática de modelo | **Proibida** | FINRA 2026; IOSCO M1 | [I] |
| Golden set por papel LLM | ≥ **50** casos (meta 200 em 12 meses) | Proporcionalidade; IOSCO M2 | [I] |
| Fração adversarial do golden set | ≥ **20%** | OWASP LLM01; Greshake | [I] |
| Canários por suíte | ≥ **3** | Wahi 2026 | [I] |
| *Schema* válido / evidência válida | **100% / 100%** | Gates determinísticos | [I] |
| Números não autorizados no texto | **0** | AGENTS I1; `fechamento.validation` | [I] |
| Sucesso de injeção | **0%** | OWASP LLM01 | [I] |
| Reexecuções de juiz LLM | **R ≥ 5** | Ayyagari 2026 | [F]/[I] |
| Defasagem de disponibilidade de notícia | ≥ **30 min** após publicação | OpenPM | [F]/[I] |
| Janela contaminada de backtest com LLM | datas ≤ ***cutoff* + 30 dias** | Lopez-Lira et al.; Zhang & Stadie | [I] |
| Histórico mínimo para afirmar valor da IA | ≥ **26 semanas** pós-inception (*shadow*) | Poder estatístico | [I] |
| *Tilt* máximo de visão LLM | \|z\| ≤ **1,5**; IC de visão **0,03** | `alpha.max_view_tilt_z`; `view_information_coefficient` | [I] (config) |
| Vol-alvo / banda | **5%** / **[3%, 7%]**; zona de co-assinatura fora de **[4%, 6%]** | Mandato; [I] | Mandato/[I] |
| Exposição líquida máxima | \|Σw\| ≤ **1%** do NAV | `risk.net_exposure_max_abs` | Config |
| Beta máximo | \|β\| ≤ **0,05** | `risk.beta_max_abs` | Config |
| Peso máximo por nome | long **4%**; short **2,5%** | `risk.max_long_weight` / `max_short_weight` | Config |
| Participação no ADTV | **20%** | `liquidity.participation_rate` | Config |
| Dias para liquidar | long ≤ **3**; short ≤ **2** | `liquidity.*` | Config |
| Aluguel máximo | **8% a.a.** | `shorting.max_borrow_fee` | Config |
| *Drawdown* | **−3%** revisão; **−5%** corte de 50% do gross | `drawdown.*`; doc 01 | Config |
| *Override* que exige quatro olhos | > **0,50% NAV** por nome ou > **5% NAV** de *turnover* | Materialidade | [I] |
| *Price collar* de ordem | ±**5%** vs. referência | RTS 6, art. 15 (análogo) | [I] |
| Valor máximo por ordem | ≤ **1,5% do NAV** | RTS 6, art. 15 (análogo) | [I] |
| Gatilho do *kill switch* de IA | > **5%** das notas com falha em gate na semana | Degradação controlada | [I] |
| Cobertura mínima de preços | ≥ **95%** do universo | Gate de dados | [I] |
| Gatilho de revisão de posição | retorno residual ≤ **−1,5σ** do horizonte | Disciplina de saída | [I] |
| Horizonte padrão da tese | **8 semanas** | `alpha.horizon_weeks` | Config |
| *Pre-mortem* e checklist obrigatórios | posições ≥ **2% NAV** ou mudança de sinal | Proporcionalidade | [I] |
| Relatório de risco às pessoas designadas | ≥ **mensal** (operamos semanal) | CVM 21, art. 26, §2º, II | [F] |
| Desenquadramento passivo | explicação à CVM após **15 dias úteis** | CVM 175, art. 90, §1º | [F] |
| Comunicação de indício de violação | ≤ **10 dias úteis** | CVM 21, art. 18, VIII | [F] |
| Notificação de incidente de dados (EUA) | ≤ **30 dias** | Reg S-P (2024) | [F] |
| Revisão do programa de compliance | ≥ **anual**; relatório até o último dia útil de abril | Rule 206(4)-7; CVM 21, art. 25 | [F] |
| Ancoragem do hash-cabeça | a cada aprovação **e** diária | Ataque de regravação | [I] |

---

## 10. Fatos vs. inferências, limitações e itens a reverificar

**Verificado em fonte primária nesta sessão [F]:**

- SR 26-2: PDF do Fed com escopo, exclusão de GenAI e definição de modelo.
- IOSCO CR/01/2025: PDF com as seis medidas de 2021, o ranking de riscos e o trecho sobre viés de automação.
- CVM Resoluções 21 e 175: textos consolidados com artigos citados.
- ESMA, *Public Statement* de 30/05/2024 (PDF).
- NIST AI 600-1 (PDF).
- Página da OWASP.
- SEC: *press releases* 2023-140, 2023-173, 2024-36 e 2024-58; PDF das prioridades do FY2026; discursos de Atkins (04/03/2026) e Daly (03/02/2026).
- eCFR: Rules 204-2, 206(4)-7 e 15c3-5.
- RTS 6, arts. 12 e 15, via legislation.gov.uk (versão retida no Reino Unido, com texto idêntico ao da UE na origem).
- FINRA RN 24-09.
- Anthropic: docs de depreciações, *structured outputs* e *citations*.
- Papers: Glasserman & Lin; Lopez-Lira, Tang & Zhu; Zheng et al.; FinanceBench; Greshake et al.; Look-Ahead-Bench; OpenPM; Ayyagari (*Pinned and Still Unstable*); Zhang & Stadie; Wahi.
- CFA Institute, *press release* e capítulo 10.
- APIMEC Ofício 002/2025.
- PRA SS1/23 (página).
- Farnam Street (diário de decisão).
- HBR: autoria e data do *pre-mortem* e do checklist.

**Fonte secundária [S]:**

- Conteúdo detalhado do *IOSCO Supervisory Toolkit* (FR/02/2026): o PDF estava bloqueado e usamos o Regulation Tomorrow, o Central Bank of Ireland e o ipushpull. A tipologia de supervisão humana vem do ipushpull.
- Detalhes do Relatório FINRA 2026 (via Debevoise).
- Datas e conteúdo do *Digital Omnibus* (Orrick, Gibson Dunn).
- Data da retirada da proposta PDA (Proskauer, Paul Hastings, Ropes & Gray).
- Guias da ANBIMA (páginas de notícia da ANBIMA).
- Notícias sobre o uso de IA na supervisão da CVM.
- Número de ~30% do *prospective hindsight*.

**Inferência [I]:**

- Todos os parâmetros marcados [I].
- A aplicabilidade das normas ao veículo.
- A leitura do art. 19 da CVM 21 para LLMs.
- O desenho "só aperta", os gatilhos de quatro olhos e os *kill switches*.
- O mínimo de 26 semanas.

**Limitações:**

- Não lemos o texto final do *Digital Omnibus* no Jornal Oficial da UE.
- Não confirmamos o status do PL 2338/2023 em 2026.
- Não lemos o PDF do *toolkit* da IOSCO.
- Não confirmamos o prazo de retenção recomendado pelo CFA.
- O orçamento de buscas web da sessão se esgotou antes de cobrir FIA (boas práticas de controles de trading automatizado), MAS (diretrizes de IA, 2025/2026) e Reg SHO (*locate*). Esses temas ficam para uma rodada futura.

**Reverificar periodicamente (sensível ao tempo):**

1. Eventual RFI ou guia de Fed/OCC/FDIC sobre MRM de GenAI e IA agêntica.
2. Versão final do *IOSCO Toolkit* após a consulta encerrada em 26/06/2026.
3. Datas do *Digital Omnibus*.
4. Agenda da SEC sobre IA: *AI Task Force* e eventual nova proposta.
5. Status do PL 2338/2023 e eventual norma da CVM sobre IA.
6. Tabela de depreciação de modelos do provedor usado (por exemplo, a aposentadoria do `claude-sonnet-4-5-20250929` em 30/11/2026).
7. Atualizações do OWASP LLM Top 10.

---

## 11. Fontes

1. Board of Governors of the Federal Reserve System / OCC / FDIC: **SR 26-2, *Revised Guidance on Model Risk Management***, 17/04/2026. https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm (PDF: https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf)
2. Federal Reserve: **SR 11-7, *Guidance on Model Risk Management***, 04/04/2011 (substituído). https://www.federalreserve.gov/supervisionreg/srletters/sr1107.htm
3. Bank of England / PRA: **SS1/23, *Model risk management principles for banks***, 17/05/2023 (versão em vigor desde 23/04/2026). https://www.bankofengland.co.uk/prudential-regulation/publication/2023/may/model-risk-management-principles-for-banks-ss
4. IOSCO: **CR/01/2025, *Artificial Intelligence in Capital Markets: Use Cases, Risks, and Challenges***, mar/2025 (inclui o Anexo I com as 6 medidas de 2021). https://www.iosco.org/library/pubdocs/pdf/IOSCOPD788.pdf (cópia lida: https://www.hkdca.com/wp-content/uploads/2025/04/ai-in-capital-markets-use-cases-iosco.pdf). Relatório de 2021: FR06/2021, *The use of AI and ML by market intermediaries and asset managers*, set/2021. https://www.iosco.org/library/pubdocs/pdf/IOSCOPD684.pdf
5. IOSCO: **FR/02/2026, *Supervisory Toolkit for AI Use in Capital Markets***, 25/05/2026. https://www.iosco.org/library/pubdocs/pdf/IOSCOPD823.pdf; *press release* IOSCO/MR/13/2026: https://www.iosco.org/news/pdf/IOSCONEWS796.pdf
6. Regulation Tomorrow: *IOSCO Final Report: Supervisory Toolkit for AI Use in Capital Markets*, mai/2026. https://www.regulationtomorrow.com/2026/05/iosco-final-report-supervisory-toolkit-for-ai-use-in-capital-markets/
7. Central Bank of Ireland: *Publication of IOSCO AI Supervisory Toolkit and Industry Practices Review survey*, 2026. https://www.centralbank.ie/regulation/markets-update/iosco/issue-8-2026/central-bank-of-ireland/publication-of-iosco-ai-supervisory-toolkit-and-industry-practices-review-survey
8. ipushpull: *What IOSCO's new AI supervisory toolkit means for regulated trading firms*, 2026. https://ipushpull.com/blog/what-ioscos-new-ai-supervisory-toolkit-means-for-regulated-trading-firms
9. CFA Institute: ***AI in Asset Management: Tools, Applications, and Frontiers***, *press release* de 18/11/2025. https://www.cfainstitute.org/about/press-room/2025/ai-in-asset-management-report-2025
10. CFA Institute Research Foundation: A. Martirosyan, *Chapter 10: Ethical AI in Finance*, 18/11/2025. https://rpc.cfainstitute.org/research/foundation/2025/chapter-10-ethical-ai-in-finance
11. FINRA: **Regulatory Notice 24-09**, *FINRA Reminds Members of Regulatory Obligations When Using Generative AI*, 27/06/2024. https://www.finra.org/rules-guidance/notices/24-09
12. Debevoise Data Blog: *FINRA's 2026 Regulatory Oversight Report: Continued Focus on Generative AI and Emerging Agent-Based Risks*, 11/12/2025. https://www.debevoisedatablog.com/2025/12/11/finras-2026-regulatory-oversight-report-continued-focus-on-generative-ai-and-emerging-agent-based-risks/
13. ESMA: **ESMA35-335435667-5924, *Public Statement on the use of Artificial Intelligence in the provision of retail investment services***, 30/05/2024. https://www.esma.europa.eu/sites/default/files/2024-05/ESMA35-335435667-5924__Public_Statement_on_AI_and_investment_services.pdf
14. NIST: **AI 600-1, *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile***, jul/2024. https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
15. OWASP GenAI Security Project: ***Top 10 for LLM Applications 2025***. https://genai.owasp.org/llm-top-10/
16. SEC: *press release* 2023-140, *SEC Proposes New Requirements to Address Risks to Investors From Conflicts of Interest Associated With the Use of Predictive Data Analytics*, 26/07/2023. https://www.sec.gov/newsroom/press-releases/2023-140
17. Proskauer: *SEC Withdraws Fourteen Rule Proposals*, jun/2025. https://www.proskauer.com/alert/sec-withdraws-fourteen-rule-proposals; Paul Hastings: https://www.paulhastings.com/insights/client-alerts/sec-withdraws-14-pending-rule-proposals; Ropes & Gray: https://www.ropesgray.com/en/insights/alerts/2025/06/sec-clears-unfinished-rulemakings-from-regulatory-agenda
18. SEC: *press release* 2024-36, *SEC Charges Two Investment Advisers with Making False and Misleading Statements About Their Use of Artificial Intelligence*, 18/03/2024. https://www.sec.gov/newsroom/press-releases/2024-36
19. SEC: *press release* 2023-173, *SEC Charges Nine Investment Advisers in Ongoing Sweep Into Marketing Rule Violations*, 11/09/2023. https://www.sec.gov/newsroom/press-releases/2023-173
20. SEC Division of Examinations: ***Fiscal Year 2026 Examination Priorities***, 17/11/2025. https://www.sec.gov/files/2026-exam-priorities.pdf
21. SEC: *press release* 2024-58, *SEC Adopts Rule Amendments to Regulation S-P*, 16/05/2024. https://www.sec.gov/newsroom/press-releases/2024-58
22. SEC: P. Atkins, *Remarks at the FSOC Artificial Intelligence Innovation Series Roundtable*, 04/03/2026. https://www.sec.gov/newsroom/speeches-statements/atkins-remarks-at-financial-stability-oversight-council-artificial-intelligence-innovation-series-roundtable-030426
23. SEC: B. Daly, *Artificial Intelligence and the Future of Investment Management*, 03/02/2026. https://www.sec.gov/newsroom/speeches-statements/daly-020326-artificial-intelligence-future-investment-management
24. eCFR: **17 CFR 275.204-2** (*Books and records*). https://www.ecfr.gov/current/title-17/chapter-II/part-275/section-275.204-2
25. eCFR: **17 CFR 275.206(4)-7** (*Compliance procedures and practices*). https://www.ecfr.gov/current/title-17/chapter-II/part-275/section-275.206(4)-7
26. eCFR: **17 CFR 240.15c3-5** (*Risk management controls for brokers or dealers with market access*). https://www.ecfr.gov/current/title-17/chapter-II/part-240/section-240.15c3-5
27. Regulamento Delegado (UE) **2017/589 (RTS 6)**, arts. 12 (*kill functionality*) e 15 (*pre-trade controls*), de 19/07/2016. https://www.legislation.gov.uk/eur/2017/589/article/12 e https://www.legislation.gov.uk/eur/2017/589/article/15 (original UE: https://eur-lex.europa.eu/eli/reg_del/2017/589/oj)
28. CVM: **Resolução CVM 175** (texto consolidado, Parte Geral), 23/12/2022. https://conteudo.cvm.gov.br/export/sites/cvm/legislacao/resolucoes/anexos/100/resol175consolid_ParteGeral.pdf
29. CVM: **Resolução CVM 21** (texto consolidado), 25/02/2021, em vigor desde 01/07/2021. https://conteudo.cvm.gov.br/export/sites/cvm/legislacao/resolucoes/anexos/001/resol021consolid.pdf
30. APIMEC Brasil: **Ofício nº 002/2025/SSA**, *uso de IA por analistas de valores mobiliários*, 05/03/2025. https://www.apimecbrasil.com.br/noticia/oficio-no-002-2025-ssa-apimecbrasil/
31. ANBIMA: *Guia orientativo, Boas práticas para o uso de sistemas de inteligência artificial nos mercados financeiro e de capitais*, jul/2024. https://www.anbima.com.br/data/files/63/74/15/39/F12C091039E04909EA2BA2A8/Guia_orientativo_boas_praticas_para_o_uso_de_sistemas_de_inteligencia_artificial.pdf
32. ANBIMA: *Inteligência artificial: guia reforça governança em todas as etapas do ciclo de vida da tecnologia*, 10/10/2025. https://www.anbima.com.br/pt_br/noticias/inteligencia-artificial-guia-reforca-governanca-em-todas-as-etapas-do-ciclo-de-vida-da-tecnologia.htm
33. ANBIMA: *Guia para avaliação de IA generativa (GAIG)*, 10/03/2026. https://www.anbima.com.br/pt_br/noticias/guia-para-avaliacao-de-ia-generativa-e-novo-passo-na-agenda-de-inovacao-da-anbima.htm
34. Orrick: *EU AI Act Update: Digital Omnibus Finalizes 8 Compliance Changes*, jul/2026. https://www.orrick.com/en/Insights/2026/07/EU-AI-Act-Update-Digital-Omnibus-Finalizes-8-Compliance-Changes
35. Gibson Dunn: *EU AI Act Omnibus Agreement: Postponed High-Risk Deadlines and Other Key Changes*, mai/2026. https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/
36. Regulamento (UE) **2024/1689** (AI Act), *Jornal Oficial* de 12/07/2024. https://eur-lex.europa.eu/eli/reg/2024/1689/oj
37. Anthropic: ***Model deprecations*** (consultado em 05/10/2026). https://platform.claude.com/docs/en/about-claude/model-deprecations
38. Anthropic: ***Structured outputs*** (consultado em 05/10/2026). https://platform.claude.com/docs/en/build-with-claude/structured-outputs
39. Anthropic: ***Citations*** (consultado em 05/10/2026). https://platform.claude.com/docs/en/build-with-claude/citations
40. P. Islam et al., ***FinanceBench: A New Benchmark for Financial Question Answering***, arXiv:2311.11944, 20/11/2023. https://arxiv.org/abs/2311.11944
41. K. Greshake et al., ***Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection***, arXiv:2302.12173 (v2, 05/05/2023). https://arxiv.org/abs/2302.12173
42. L. Zheng et al., ***Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena***, NeurIPS 2023, arXiv:2306.05685. https://arxiv.org/abs/2306.05685
43. K. C. Ayyagari, ***Pinned and Still Unstable: Within-Judge Verdict Variance and the Noise Floor of LLM-as-Judge Leaderboards***, arXiv:2609.33044, 27/09/2026. https://arxiv.org/abs/2609.33044
44. V. Wahi, ***LLM-as-a-Judge Is Not an Oracle: Why Self-Improving Agents Need Deterministic Guardrails***, arXiv:2609.02246, 02/09/2026. https://arxiv.org/abs/2609.02246
45. P. Glasserman & C. Lin, ***Assessing Look-Ahead Bias in Stock Return Predictions Generated By GPT Sentiment Analysis***, arXiv:2309.17322, 29/09/2023. https://arxiv.org/abs/2309.17322
46. A. Lopez-Lira, Y. Tang & M. Zhu, ***The Memorization Problem: Can We Trust LLMs' Economic Forecasts?***, arXiv:2504.14765 (v2, 16/12/2025). https://arxiv.org/abs/2504.14765
47. M. Benhenda, ***Look-Ahead-Bench: a Standardized Benchmark of Look-ahead Bias in Point-in-Time LLMs for Finance***, arXiv:2601.13770, 20/01/2026. https://arxiv.org/abs/2601.13770
48. Z. Zhang & B. C. Stadie, ***Temporal Leakage in LLM Backtesting: Measurement, Validation, and Adjusted Scores***, arXiv:2608.02985, 04/08/2026. https://arxiv.org/abs/2608.02985
49. X. Cai et al., ***OpenPM: Auditable Point-in-Time Evaluation for LLM Portfolio-Management Agents***, arXiv:2608.09988, 06/08/2026. https://arxiv.org/abs/2608.09988
50. Farnam Street, ***Decision Journal*** (template inspirado em M. Mauboussin), 20/02/2014 (atualizado em 13/02/2025). https://fs.blog/decision-journal/
51. G. Klein, ***Performing a Project Premortem***, Harvard Business Review, set/2007. https://hbr.org/2007/09/performing-a-project-premortem
52. D. Kahneman, D. Lovallo & O. Sibony, ***The Big Idea: Before You Make That Big Decision…***, Harvard Business Review, jun/2011. https://hbr.org/2011/06/the-big-idea-before-you-make-that-big-decision
53. Lei nº 13.709/2018 (**LGPD**). https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm
54. Documentos irmãos deste repositório: `docs/research/01_ia_gestao_industria.md` e `docs/research/02_ia_gestao_academico.md` (padrões de indústria, *drawdown* de plataformas, *Deflated Sharpe*/PBO).
