# Daqui Para Frente: O Redesenho do Trabalho no AI Notes #8

> *“É essa mudança que quero explorar nos próximos AI Notes.*
> 
> *Até aqui, falamos de várias peças separadas: como funcionam os modelos, como organizar uma Skill, como produzir apresentações, como avaliar respostas e como escrever pedidos melhores. Agora vamos juntar tudo isso.*
> 
> *A ideia é pegar um processo real e redesenhá-lo de ponta a ponta usando as ferramentas que temos hoje.*
> 
> *Vamos continuar usando o comentário de fechamento do mercado como exemplo, mas o mesmo raciocínio vale para uma conciliação, um relatório para clientes, uma análise recorrente, uma triagem de documentos ou praticamente qualquer processo operacional que tenha informação entrando de um lado e uma entrega saindo do outro.*
> 
> *E o primeiro passo vai ser entender como o trabalho realmente acontece hoje.*
> 
> *Quais etapas existem? Quais precisam continuar existindo? O que pode virar uma regra objetiva? Onde realmente precisamos de um modelo? Onde uma pessoa precisa continuar no processo?”*

---

## 1. A Construção sobre as Edições Anteriores

No **AI Notes #7** (`market-close-eval`), estabelecemos uma distinção conceitual fundamental: **capacidade, confiabilidade e autorização**. Demonstramos empiricamente que um LLM conseguir redigir um comentário não significa que ele calculou os números corretamente, nem que tinha autorização para publicar uma análise sem supervisão.

No **AI Notes #8**, damos o passo lógico seguinte: **antes de automatizar, entenda e redesenhe o trabalho**.

Não tentamos substituir cada clique manual por uma chamada desgovernada a um agente. Em vez disso, analisamos o processo de ponta a ponta e respondemos às 5 perguntas essenciais que todo profissional deve se fazer antes de introduzir IA em sua rotina.

---

## 2. As Cinco Perguntas Fundamentais do Redesenho

### Pergunta 1: Quais etapas existem hoje?
No processo tradicional, um analista realiza cerca de 10 passos manuais:
1. Abrir planilhas de preços e sistemas de mercado;
2. Conferir visualmente se as datas e cotações correspondem ao pregão atual;
3. Calcular variações percentuais e contribuições no Excel;
4. Identificar os destaques de alta e baixa;
5. Ler portais de notícias em busca de explicações para as oscilações;
6. Cruzar mentalmente as notícias com os números calculados;
7. Redigir o rascunho corrido em um editor de texto;
8. Revisar números e ortografia;
9. Copiar e colar o texto no sistema de e-mail ou canal de distribuição;
10. Arquivar uma cópia em disco compartilhado.

### Pergunta 2: Quais etapas precisam continuar existindo?
Precisamos que os dados sejam validados, que as contas sejam exatas, que haja uma narrativa clara e que alguém assuma a responsabilidade formal pela entrega. 
Por outro lado, etapas como **abrir arquivos manualmente** e **copiar/colar entre janelas** são puro atrito mecânico e **desaparecem** completamente no novo desenho.

### Pergunta 3: O que pode virar uma regra objetiva em código?
**Tudo o que for determinístico e quantitativo.**
Modelos de linguagem não são calculadoras confiáveis. No projeto Fechamento, o LLM é estritamente proibido de calcular.
- A conferência de integridade dos arquivos virou código com hashes SHA-256;
- O cálculo de retornos, atribuição setorial e contribuições em bps ($w_i \times R_i \times 10.000$) virou funções puras em Python;
- A reconciliação matemática virou um portão automatizado (diferença máxima de 0.05 bps);
- O catálogo de números virou o `FactBook` — a única fonte da verdade quantitativa do sistema.

### Pergunta 4: Onde realmente precisamos de um modelo de IA?
**Apenas na redação preliminar da narrativa.**
O LLM atua como um redator com escopo delimitado: ele recebe o `FactBook` e as notícias elegíveis, e deve estruturar os parágrafos usando placeholders determinísticos como `{{fact:ibov.return_pct}}` e `{{news:id}}`.
O modelo não acessa a internet, não executa comandos no computador e não inventa dados fora do que lhe foi fornecido. Se tentar criar um número financeiro por conta própria, o validador em código rejeita o rascunho antes que qualquer pessoa perca tempo lendo.

### Pergunta 5: Onde uma pessoa precisa continuar no processo?
**Na interpretação qualitativa, na governança e na autorização final.**
Uma notícia ter sido publicada no mesmo dia do pregão não prova que ela causou o movimento da ação. Essa sustentação semântica e a responsabilidade institucional continuam sendo exclusivas do revisor humano.
A aplicação não se autoaprova: o revisor inspeciona o texto lado a lado com o `FactBook` e as notícias, edita o que julgar necessário e clica em **Aprovar**. Essa aprovação gera um **Approval Hash (SHA-256)** que vincula criptograficamente o texto, os fatos e os arquivos de entrada. Se qualquer caractere for alterado após a aprovação, o selo é invalidado e a exportação é bloqueada.

---

## 3. A Generalização para Outros Processos

O comentário de fechamento de mercado é apenas o exemplo mais visível. O mesmo raciocínio aplica-se a:
- **Conciliação Contábil:** Código valida os lançamentos e calcula as diferenças; a IA resume as pendências atípicas; o contador sênior aprova os ajustes.
- **Relatório de Performance para Clientes:** Código consolida rentabilidade e riscos; a IA redige os comentários de contexto macroeconômico com placeholders; o gestor de portfólio assina.
- **Triagem de Documentos e Contratos:** Código extrai metadados e confere assinaturas; a IA identifica cláusulas divergentes da minuta padrão; o advogado decide se aceita a exceção.

Essa é a transição de *brincar com chatbots* para **construir sistemas de trabalho confiáveis**.
