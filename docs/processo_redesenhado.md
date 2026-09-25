# Redesenho do Processo — Fechamento (AI Notes #8)

> **Antes de automatizar, entenda e redesenhe o trabalho.**
> O objetivo central deste redesenho é tornar visível como a rotina é reconstruída: quais etapas desaparecem, quais viram regras determinísticas em código, quais dependem de interpretação e onde uma pessoa continua indispensável e responsável.

---

## 1. Princípios do Redesenho

1. **Cálculos exclusivamente em código**: Modelos de linguagem (LLMs) são péssimos computadores aritméticos. Todo cálculo de retorno, soma de pesos, contribuição ponderada em bps e spread relativo é executado por funções puras em Python com tolerâncias explícitas. O LLM é estritamente proibido de calcular.
2. **FactBook como fonte única da verdade**: Toda informação quantitativa é organizada em um catálogo estável de fatos imutáveis (`FactBook`). O texto gerado utiliza placeholders determinísticos `{{fact:id}}` que são substituídos por código. Se um número financeiro aparecer no texto fora de um placeholder, o rascunho é rejeitado.
3. **Filtro temporal e causalidade disciplinada**: Notícias publicadas após o horário de corte do pregão são automaticamente excluídas do pacote de evidências com registro documentado. Notícia pré-corte vinculada a ativo não implica causalidade comprovada: a sustentação semântica é de responsabilidade da revisão humana.
4. **Governança de versão vinculada a Hash**: A aprovação do revisor vincula os hashes SHA-256 do texto, do FactBook, das evidências e da configuração. Se qualquer vírgula do texto ou dado for modificado após a aprovação, o selo de aprovação é invalidado e a exportação é bloqueada.
5. **Sem Autoaprovação**: A máquina não aprova o próprio trabalho. A aprovação humana é um portão explícito e auditável.

---

## 2. Mapa do Processo Redesenhado

```
[1. Carregar & Validar] (Código) ──▶ [2. Calcular Métricas] (Código) ──▶ [3. FactBook & Notícias] (Código)
                                                                                  │
[6. Revisão Humana] ◀── [5. Conferir Rascunho] (Código) ◀── [4. Redigir c/ Placeholders] (IA/Demo)
        │
[7. Aprovação vinculada a Hash] (Humano) ──▶ [8. Exportação Segura] (Código)
```

---

## 3. Matriz de Mudanças: O que mudou e por quê?

| Etapa Redenhada | O que foi feito? | Problema que resolve | Risco que permanece |
| :--- | :--- | :--- | :--- |
| **1. Carregar & Validar** | Substituiu abertura manual e checagem visual de datas por leitura automática de CSV/JSON com validação de tipos, preços positivos e manifesto de integridade. | Elimina erro humano de usar planilha antiga ou corrompida. | Arquivo de entrada fornecido pelo usuário pode conter erros conceituais na origem. |
| **2. Calcular Métricas** | Substituiu fórmulas de Excel por funções matemáticas puras com reconciliação estrita (soma das contribuições = retorno da carteira). | Elimina erros de `#DIV/0!`, fórmulas quebradas e confusão entre retorno e contribuição. | Hipótese simplificadora de carteira fixa diária sem trades intradiários. |
| **3. FactBook & Notícias** | Centralizou todos os números calculados em um catálogo imutável e filtrou notícias após o horário de corte. | Impede citação de fatos extemporâneos e padroniza as referências. | Notícia dentro do horário de corte pode ainda assim conter boatos de mercado. |
| **4. Redigir c/ Placeholders** | Substituiu redação livre por geração estruturada com placeholders `{{fact:id}}` e `{{news:id}}`. | Impede alucinação de números financeiros pelo modelo de linguagem. | O modelo pode construir uma frase com estilo pobre ou interpretação superficial. |
| **5. Conferir Rascunho** | Validação automatizada que confere se todos os placeholders existem e se nenhum número financeiro foi inventado fora do sistema. | Garante 100% de integridade factual antes de o texto chegar aos olhos do revisor. | Validação sintática não atesta se o tom editorial é o mais adequado. |
| **6. Revisão Humana** | Substituiu conferência mecânica de números por avaliação semântica lado a lado com as evidências. | Libera o revisor de tarefas de calculadora e concentra seu foco no julgamento qualitativo. | Revisor pode aprovar por distração sem ler atentamente as notícias. |
| **7. Aprovação vinculada a Hash** | Registro formal de aprovação vinculado aos hashes criptográficos do texto e dos dados. | Garante que nenhuma edição posterior seja publicada sem nova revisão. | Chave de aprovação é didática e local, não substituindo controle de acesso corporativo. |
| **8. Exportação Segura** | Geração automatizada de Markdown, HTML e JSON com bloqueio estrito contra versões não aprovadas. | Elimina etapa manual de copiar/colar e assegura preservação do aviso de dados simulados. | Falha de infraestrutura local de disco na máquina do usuário. |

---

## 4. Por que não apenas colocar um agente com ferramentas?

Um agente autônomo comum que recebesse ferramentas para abrir arquivos, calcular no terminal, redigir e enviar o e-mail diretamente violaria o princípio da **autorização e da confiabilidade**. Ao executar cálculos por conta própria, o LLM comete erros aritméticos frequentes. Ao receber ferramentas de escrita, ele pode publicar rascunhos sem conferência humana.

No redesenho, o código controla o fluxo, a matemática e as restrições; o LLM opera estritamente como um gerador de texto delimitado; e o humano é o único responsável pela aprovação.
