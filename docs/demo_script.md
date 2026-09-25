# Roteiro de Demonstração (5 Minutos) — Fechamento (AI Notes #8)

Este roteiro orienta uma demonstração guiada da aplicação local em aproximadamente 5 minutos, cobrindo os quatro pilares do projeto:
1. O mapa do processo (atual vs redesenhado)
2. Uma execução normal determinística
3. Uma interrupção por dado corrompido (bloqueio preventivo)
4. Uma revisão humana lado a lado com aprovação e exportação vinculada a hash

---

## Minuto 1: O Ponto de Partida e o Redesenho do Processo

1. **Abra a aplicação no navegador:**
   ```bash
   uv run streamlit run app.py --server.address 127.0.0.1
   ```
2. **Navegue para a aba "1. Processo":**
   - Destaque o lema: *"Antes de automatizar, entenda e redesenhe o trabalho"*.
   - Alterne entre o **Processo Atual** e o **Processo Redesenhado**.
   - Mostre o diagrama de dependências (DAG) e explique as cores:
     - Vermelho: etapas eliminadas (abertura manual de planilhas, colagem em e-mail).
     - Azul claro: etapas transferidas integralmente para código (validação de tipos, cálculo de retornos, FactBook).
     - Laranja: IA com escopo delimitado (redação estruturada com placeholders).
     - Verde: etapas sob responsabilidade humana (interpretação qualitativa, revisão e aprovação).

---

## Minuto 2: Execução do Fluxo Normal com Dados Sintéticos

1. **Navegue para a aba "2. Executar":**
   - Verifique que o **Cenário Normal** está selecionado.
   - Mostre a data de referência (`18/09/2026`), o horário de corte (`18:00:00-03:00`) e o fuso horário oficial (`America/Sao_Paulo`).
   - Mantenha o modo **DemoProvider (Determinístico e Offline)** selecionado.
2. **Clique em "▶ Executar Pipeline de Fechamento":**
   - Observe a rápida execução (menos de 1 segundo).
   - Acompanhe o avanço das etapas até o estado `IN_REVIEW`.
   - Note o resumo quantitativo:
     - IBOV: `+1,00%`
     - USD/BRL: `-0,64%` (queda do dólar frente ao real)
     - Carteira Long-Only: `+1,14%`
     - Spread vs IBOV: `+13,7 bps`
   - Abra o expansor **"Exclusões Documentadas"** e mostre que a notícia das 18h45 foi automaticamente excluída por ter sido publicada após o horário de corte.

---

## Minuto 3: Teste de Bloqueio Preventivo (Cenário Corrompido)

1. **Ainda na aba "2. Executar", selecione:**
   - **Cenário de Entrada:** `Cenário Corrompido (Teste de Bloqueio por Inconsistência)`.
2. **Clique novamente em "▶ Executar Pipeline de Fechamento":**
   - Observe que o sistema não tenta adivinhar dados nem renormaliza pesos silenciosamente.
   - O estado transita imediatamente para `BLOCKED`.
   - Leia a mensagem explícita de erro na tela:
     - `A soma dos pesos da carteira é 1.1500 (esperado 1.0000). Não é permitida renormalização silenciosa.`
     - `Ativo da carteira 'PETR4' não possui cotação correspondente em quotes.csv.`
   - Mostre que a geração de texto foi cancelada e nenhuma exportação foi permitida.

---

## Minuto 4: Revisão Humana Lado a Lado

1. **Retorne ao "Cenário Normal" e execute novamente** para restaurar o estado `IN_REVIEW`.
2. **Navegue para a aba "3. Revisar":**
   - Apresente a divisão da tela no desktop:
     - **Lado Esquerdo:** O comentário estruturado gerado com substituição determinística dos placeholders.
     - **Lado Direito:** O Painel de Evidências contendo o FactBook (fatos calculados com fórmulas) e as notícias elegíveis.
   - Demonstre a disciplina de governança:
     - Aponte para a caixa de status: *"Aguardando aprovação humana formal. A aplicação não se autoaprova"*.
     - Mostre que o botão de exportação está desabilitado.

---

## Minuto 5: Edição, Aprovação Vinculada a Hash e Exportação

1. **Demonstre o controle de versão:**
   - No editor de texto do comentário, faça um pequeno ajuste (ex: adicione uma observação no parágrafo 2).
   - Clique em **"💾 Salvar Edição"**.
   - Note que o número da revisão avançou para `#2` e um novo hash de texto foi calculado.
2. **Formalize a aprovação:**
   - Digite o nome do aprovador (ex: `Ariel Assayag`).
   - Clique em **"✔ Aprovar Comentário Formalmente"**.
   - Observe a transição para `APPROVED` e a geração do **Approval Hash (SHA-256)**, que vincula criptograficamente o texto, os fatos e os arquivos de entrada.
3. **Execute a exportação final:**
   - Clique em **"📦 Exportar Artefatos"**.
   - Mostre os três arquivos gerados na pasta `outputs/<run_id>/`:
     - `comentario.md` (Markdown com cabeçalho de dados simulados)
     - `comentario.html` (HTML estilizado com paleta institucional e escape seguro)
     - `bundle.json` (JSON contendo o texto, fatos, verificações e trilha de auditoria)
4. **Encerramento:**
   - Conclua destacando como o processo tornou o trabalho transparente, auditável e seguro.
