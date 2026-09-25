# Progresso do Projeto — Fechamento (AI Notes #8)

Este documento acompanha o status de implementação das etapas do projeto.

## Checklist de Etapas

- [x] Configuração inicial do workspace (`AGENTS.md`, `.agents/rules/`, `pyproject.toml`)
- [x] Especificação do Processo (`ProcessSpec`, `docs/processo_atual.md`, `docs/processo_redesenhado.md`)
- [x] Criação dos pacotes de demonstração sintéticos (`data/demo/normal/`, `data/demo/corrupted/`)
- [x] Contratos de Dados (`contracts.py`)
- [x] Ingestão e Validação Rigorosa (`ingestion.py`)
- [x] Cálculos Financeiros Determinísticos (`metrics.py`)
- [x] FactBook e Organização de Evidências (`evidence.py`)
- [x] Provedores de Narrativa (`DemoProvider` determinístico e `GeminiProvider` opcional)
- [x] Validação de Rascunho e Resolução de Placeholders (`validation.py`)
- [x] Máquina de Estados e Persistência SQLite (`workflow.py`, `storage.py`)
- [x] Módulo de Exportação com Bloqueio por Hash (`exports.py`)
- [x] Interface Streamlit com 4 Abas (`app.py`)
- [x] CLI executável (`__main__.py`)
- [x] Suíte Completa de Testes (`tests/`)
- [x] Documentação de Evidências e Roteiro de Demo (`evidencias_ai_notes_08.md`, `demo_script.md`, `README.md`)
- [x] Validação final ponta a ponta e testes automatizados passando (34/34)
