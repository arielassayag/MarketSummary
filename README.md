# Fechamento — AI Notes #8 e #9

> **Antes de automatizar, entenda e redesenhe o trabalho.**
> Aplicação local, didática e funcional para redesenhar o processo de elaboração do comentário de fechamento do mercado brasileiro, materializando a distinção entre **código determinístico, síntese com IA generativa e julgamento humano**.

---

## 1. Visão Geral

Este projeto acompanha a série de publicações do *AI Notes* (edições #8 e #9). O objetivo é demonstrar na prática como uma rotina profissional de mercado financeiro é reconstruída e automatizada com segurança:
- **Quais etapas desaparecem:** abertura manual de planilhas e colagem de textos.
- **Quais viram regras em código:** ingestão, validação de tipos, cálculos de retornos e contribuições em bps, FactBook determinístico e verificação de integridade.
- **Quais dependem de interpretação (IA):** redação preliminar de narrativa com placeholders rigorosamente delimitados (`{{fact:id}}`).
- **Onde uma pessoa continua responsável:** julgamento qualitativo de causalidade, revisão lado a lado com evidências e aprovação formal vinculada a hash criptográfico.

> [!IMPORTANT]
> **Aviso de Dados Simulados**: Todos os preços, pesos de carteira e notícias do pacote de demonstração são **estritamente sintéticos**. Tickers reais da B3 foram usados apenas com finalidade didática.

---

## 2. Instalação Rápida

Requisitos: Python **3.12+** e gerenciador de pacotes **uv**.

```bash
# Sincronizar dependências e criar o ambiente virtual (.venv)
uv sync --extra dev
```

---

## 3. Como Executar

### Execução com Dados 100% Reais e OpenRouter
Para executar o pipeline com dados reais da B3/BACEN (Pregão de 11/02/2026) e gerar o comentário via OpenRouter:

```bash
uv run python -m fechamento run --scenario-dir data/real/2026-02-11 --provider openrouter --model google/gemini-2.5-flash
```

Ou usando o provedor determinístico com dados reais (offline):
```bash
uv run python -m fechamento run --scenario-dir data/real/2026-02-11 --provider demo
```

Para aprovar e exportar uma execução via terminal:
```bash
# Aprovação explícita
uv run python -m fechamento approve <run_id> --approver "Seu Nome"

# Exportação segura dos artefatos
uv run python -m fechamento export <run_id>
```

### Demonstração Sintética Offline (CLI)
Executa a demonstração sintética determinística:

```bash
uv run python -m fechamento demo
```

### Interface Gráfica Web (Streamlit)
Inicia a aplicação local no navegador:

```bash
uv run streamlit run app.py --server.address 127.0.0.1
```

A interface está organizada em 4 áreas:
1. **1. Processo:** Visualização em DAG (Mermaid) do processo atual vs redesenhado, com tabela editável de parâmetros.
2. **2. Executar:** Seleção de cenários (Normal vs Corrompido) e provedores (Demo vs Gemini), exibindo motivos de eventuais bloqueios.
3. **3. Revisar:** Inspeção lado a lado de texto e evidências (`FactBook` e notícias), editor de revisões, botão de aprovação e exportação.
4. **4. Evidências:** Histórico de auditoria persistido em SQLite (`fechamento.db`), métricas objetivas do sistema e formulário de medição manual.

---

## 4. Configuração Opcional do Provedor Gemini

O modo `DemoProvider` é **100% offline, determinístico e não requer chaves de API**. Caso deseje testar a integração com o modelo Gemini:

1. Configure a variável de ambiente:
   ```bash
   export GEMINI_API_KEY="sua-chave-aqui"
   ```
2. Na aba **2. Executar**, selecione `GeminiProvider` e marque a opção para autorizar chamadas externas.

O modelo não tem acesso a ferramentas, execução de código ou navegação web; ele recebe exclusivamente o `FactBook` e as notícias elegíveis, e deve responder em JSON validado por schema com placeholders `{{fact:id}}`.

---

## 5. Testes e Qualidade de Código

Para rodar a suíte completa de 34 testes automatizados:

```bash
uv run pytest
```

Para verificar conformidade com as regras de estilo e linting:

```bash
uv run ruff check .
```

---

## 6. Documentação Detalhada

- [`docs/guia_brasilapi_mercado.md`](file:///Users/arielassayag/codigos/MarketSummary/docs/guia_brasilapi_mercado.md): Coleta de dados de mercado 100% reais e gratuitos via BrasilAPI, AwesomeAPI e B3.
- [`docs/guia_openrouter_modelos_free.md`](file:///Users/arielassayag/codigos/MarketSummary/docs/guia_openrouter_modelos_free.md): Guia de uso dos modelos de ponta gratuitos (`:free`) no OpenRouter (Llama 3.3 70B, DeepSeek R1).
- [`docs/processo_atual.md`](file:///Users/arielassayag/codigos/MarketSummary/docs/processo_atual.md): Mapeamento do fluxo manual tradicional e diagnóstico crítico.
- [`docs/processo_redesenhado.md`](file:///Users/arielassayag/codigos/MarketSummary/docs/processo_redesenhado.md): Matriz de mudanças, princípios de redesenho e justificativas.
- [`docs/evidencias_ai_notes_08.md`](file:///Users/arielassayag/codigos/MarketSummary/docs/evidencias_ai_notes_08.md): Resultados empíricos, testes de bloqueio, limitações e backlog.
- [`docs/demo_script.md`](file:///Users/arielassayag/codigos/MarketSummary/docs/demo_script.md): Roteiro guiado de 5 minutos para apresentação.
- [`AGENTS.md`](file:///Users/arielassayag/codigos/MarketSummary/AGENTS.md): Regras e invariantes para desenvolvimento automatizado.
