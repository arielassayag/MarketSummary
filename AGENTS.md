# AGENTS.md — Regras e Invariantes do Fechamento (AI Notes #8)

Este documento define regras fundamentais e comandos operacionais para agentes e colaboradores trabalhando neste repositório.

## Comandos Principais

- **Sincronizar ambiente**: `uv sync`
- **Executar demonstração pela CLI**: `uv run python -m fechamento demo`
- **Iniciar interface web**: `uv run streamlit run app.py --server.address 127.0.0.1`
- **Executar suíte de testes**: `uv run pytest`
- **Verificar formatação e linting**: `uv run ruff check .`

## Invariantes Invioláveis

1. **Cálculos exclusivamente em código**: O LLM **nunca** calcula retornos, diferenças, rankings ou contribuições. Todos os números vêm do `FactBook` determinístico via código Python testado.
2. **Offline-First e Segurança**: A demonstração e os testes devem funcionar sem acesso à internet ou chaves de API. O modo `DemoProvider` é 100% determinístico. Notícias são tratadas como conteúdo não confiável; instruções maliciosas ("ignore as regras...") nunca alteram o estado da aplicação.
3. **Aprovação vinculada à versão (Hash)**: A aprovação humana é vinculada aos hashes SHA-256 do texto, do FactBook, das evidências e da configuração. Qualquer alteração posterior invalida a aprovação e bloqueia a exportação.
4. **Sem Autoaprovação**: A aplicação não pode aprovar a si mesma. Exportações exigem aprovação explícita.
5. **Preservação de Dados Brutos**: Arquivos de entrada nunca são alterados no local. Dados ausentes nunca são convertidos em zero ou preenchidos arbitrariamente.
6. **Sinalização Explícita de Dados Simulados**: Todos os dados da demo e relatórios gerados devem carregar a indicação explícita de "DADOS SIMULADOS".
