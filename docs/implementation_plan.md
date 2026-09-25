# Plano de Implementação — Fechamento (AI Notes #8)

Este documento registra o plano de arquitetura, implementação, testes e validação do projeto **Fechamento — AI Notes #8**.

## 1. Escopo e Objetivos
Implementação de uma aplicação local, didática e funcional para redesenhar o processo de elaboração de um comentário de fechamento do mercado brasileiro, materializando os princípios de **capacidade, confiabilidade e autorização**.

O fluxo funcional é:
`Carregar dados → validar → calcular → organizar evidências → redigir → conferir → revisar → aprovar → exportar.`

## 2. Estrutura de Arquivos
- `src/fechamento/`: Domínio, ingestão, métricas, evidências, provedores, validação, fluxo e persistência.
- `data/demo/`: Cenários sintéticos (normal e corrompido para teste de bloqueio).
- `tests/`: Suíte automatizada cobrindo contratos, cálculos, segurança, fluxo e interface.
- `docs/`: Documentação de processos (atual e redesenhado), evidências empíricas e roteiro de demo.
- `app.py`: Interface Streamlit com 4 abas (Processo, Executar, Revisar, Evidências).

## 3. Critérios de Conclusão
- Execução determinística 100% offline via CLI e Web.
- Testes automatizados passando (`pytest`).
- Bloqueio gracioso e transparente diante de dados inválidos.
- Interface funcional permitindo inspeção lado a lado, edição e aprovação vinculada a hash.
- Exportação segura em Markdown, HTML e JSON após aprovação.
