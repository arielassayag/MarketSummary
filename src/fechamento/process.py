"""Definições e gerenciamento das especificações de processo (ProcessSpec).

Fornece os modelos padrão do processo atual hipotético e do processo redesenhado,
garantindo validação de DAG, persistência e exportação.
"""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import ProcessSpec, ProcessStep, StepClassification


def get_default_current_process() -> ProcessSpec:
    """Retorna o processo atual (exemplo hipotético editável)."""
    steps = [
        ProcessStep(
            step_id="step_1_open_files",
            name="Abrir arquivos de preços e planilhas",
            objective="Localizar e abrir manualmente os arquivos de cotações e posições da carteira.",
            inputs=["Planilhas locais", "Terminais de mercado"],
            outputs=["Tabelas abertas na tela"],
            responsible="Analista Júnior",
            dependencies=[],
            completion_rule="Todos os arquivos necessários abertos sem erro de formato.",
            exceptions=["Arquivo corrompido", "Caminho não encontrado"],
            exception_destination="Interrupção manual e busca por backup",
            classification=StepClassification.ELIMINATE,
            observed_time_minutes=None,
            estimated_time_minutes=10.0,
        ),
        ProcessStep(
            step_id="step_2_check_references",
            name="Conferir referências e datas",
            objective="Verificar visualmente se a data das cotações corresponde ao pregão atual.",
            inputs=["Tabelas abertas"],
            outputs=["Confirmação visual de data"],
            responsible="Analista Júnior",
            dependencies=["step_1_open_files"],
            completion_rule="Datas de todos os ativos conferidas com o calendário B3.",
            exceptions=["Data desatualizada em algum ativo"],
            exception_destination="Contato manual com fornecedor de dados",
            classification=StepClassification.CODE,
            observed_time_minutes=None,
            estimated_time_minutes=5.0,
        ),
        ProcessStep(
            step_id="step_3_calc_variations",
            name="Calcular variações e retornos",
            objective="Digitar ou arrastar fórmulas de retorno e contribuição no Excel.",
            inputs=["Cotações e pesos da carteira"],
            outputs=["Colunas de retorno e contribuição"],
            responsible="Analista Júnior",
            dependencies=["step_2_check_references"],
            completion_rule="Planilha calculada com retornos percentuais e em pontos-base.",
            exceptions=["Erro de fórmula (#DIV/0!, #VALOR!)", "Soma de pesos diferente de 100%"],
            exception_destination="Correção manual de fórmulas",
            classification=StepClassification.CODE,
            observed_time_minutes=None,
            estimated_time_minutes=15.0,
        ),
        ProcessStep(
            step_id="step_4_identify_movements",
            name="Identificar movimentos relevantes e destaques",
            objective="Ordenar maiores altas, baixas e principais impactos por setor.",
            inputs=["Colunas calculadas"],
            outputs=["Lista mental ou rascunho de destaques"],
            responsible="Analista",
            dependencies=["step_3_calc_variations"],
            completion_rule="Seleção dos 3 maiores contribuidores positivos e negativos.",
            exceptions=["Movimento atípico sem explicação aparente"],
            exception_destination="Investigação aprofundada",
            classification=StepClassification.CODE,
            observed_time_minutes=None,
            estimated_time_minutes=10.0,
        ),
        ProcessStep(
            step_id="step_5_read_news",
            name="Ler notícias e apurar justificativas",
            objective="Navegar em portais e feeds para buscar fatos relevantes sobre os destaques.",
            inputs=["Feeds de notícias", "Portais financeiros"],
            outputs=["Anotações com manchetes e explicações"],
            responsible="Analista",
            dependencies=["step_4_identify_movements"],
            completion_rule="Pelo menos uma explicação plausível encontrada para cada grande destaque.",
            exceptions=["Nenhuma notícia sobre ativo que oscilou fortemente"],
            exception_destination="Registro de falta de notícia ou especulação de mercado",
            classification=StepClassification.HUMAN,
            observed_time_minutes=None,
            estimated_time_minutes=25.0,
        ),
        ProcessStep(
            step_id="step_6_relate_evidence",
            name="Relacionar evidências aos movimentos",
            objective="Cruzar a narrativa das notícias com os números calculados.",
            inputs=["Anotações de notícias", "Destaques numéricos"],
            outputs=["Estrutura narrativa do comentário"],
            responsible="Analista",
            dependencies=["step_5_read_news"],
            completion_rule="Relações de causalidade estabelecidas ou ausência de nexo sinalizada.",
            exceptions=["Notícia contraditória com a direção do preço"],
            exception_destination="Debate com time de análise",
            classification=StepClassification.HUMAN,
            observed_time_minutes=None,
            estimated_time_minutes=15.0,
        ),
        ProcessStep(
            step_id="step_7_write_commentary",
            name="Escrever o comentário de fechamento",
            objective="Redigir o texto corrido (200-300 palavras) sintetizando o pregão.",
            inputs=["Estrutura narrativa", "Planilha de cálculos"],
            outputs=["Rascunho de texto"],
            responsible="Analista",
            dependencies=["step_6_relate_evidence"],
            completion_rule="Texto completo redigido com introdução, destaques e conclusão.",
            exceptions=["Divergência de estilo ou falta de clareza"],
            exception_destination="Reescrita do parágrafo",
            classification=StepClassification.AI,
            observed_time_minutes=None,
            estimated_time_minutes=20.0,
        ),
        ProcessStep(
            step_id="step_8_review",
            name="Revisão manual do comentário",
            objective="Conferir números digitados no texto contra a planilha e checar coerência.",
            inputs=["Rascunho de texto", "Planilha"],
            outputs=["Texto aprovado ou com correções"],
            responsible="Estrategista Chefe",
            dependencies=["step_7_write_commentary"],
            completion_rule="Aprovação verbal ou via chat pelo gestor.",
            exceptions=["Erro numérico no texto", "Interpretação incorreta de notícia"],
            exception_destination="Devolução para o analista reescrever",
            classification=StepClassification.HUMAN,
            observed_time_minutes=None,
            estimated_time_minutes=15.0,
        ),
        ProcessStep(
            step_id="step_9_copy_distribution",
            name="Copiar para o canal de distribuição",
            objective="Copiar o texto do editor e colar no sistema de e-mail/newsletter.",
            inputs=["Texto aprovado"],
            outputs=["Comentário colado no canal"],
            responsible="Analista Júnior",
            dependencies=["step_8_review"],
            completion_rule="Texto formatado corretamente no canal.",
            exceptions=["Quebra de formatação ou caracteres especiais corrompidos"],
            exception_destination="Ajuste manual da formatação",
            classification=StepClassification.ELIMINATE,
            observed_time_minutes=None,
            estimated_time_minutes=5.0,
        ),
        ProcessStep(
            step_id="step_10_archive_final",
            name="Arquivar versão final",
            objective="Salvar cópia do arquivo com data no diretório compartilhado.",
            inputs=["Arquivo final"],
            outputs=["Arquivo arquivado em disco"],
            responsible="Analista Júnior",
            dependencies=["step_9_copy_distribution"],
            completion_rule="Arquivo salvo com convenção de nomenclatura da empresa.",
            exceptions=["Espaço em disco insuficiente ou permissão negada"],
            exception_destination="Contato com equipe de TI",
            classification=StepClassification.CODE,
            observed_time_minutes=None,
            estimated_time_minutes=5.0,
        ),
    ]

    return ProcessSpec(
        process_id="processo_atual_hipotetico",
        title="Processo Atual (Exemplo Hipotético Editável)",
        description=(
            "Mapeamento do fluxo de trabalho manual típico para elaboração do comentário "
            "de fechamento de mercado. Mostra a dispersão de tempo em tarefas mecânicas e "
            "o alto risco de erros de digitação e alucinações humanas."
        ),
        is_redesign=False,
        steps=steps,
    )


def get_default_redesigned_process() -> ProcessSpec:
    """Retorna o processo redesenhado para a aplicação Fechamento — AI Notes #8."""
    steps = [
        ProcessStep(
            step_id="step_r1_load_validate",
            name="Carregar e validar dados de entrada",
            objective="Ingerir cotações, posições, notícias e manifesto; verificar hashes e integridade.",
            inputs=["quotes.csv", "positions.csv", "news.jsonl", "manifest.json"],
            outputs=["Objetos Quote, Position, NewsItem validados", "Alertas e exclusões"],
            responsible="Sistema (Código)",
            dependencies=[],
            completion_rule="Todos os dados obrigatórios válidos; preços positivos; pesos somando 1.0.",
            exceptions=["Dado obrigatório ausente", "Preço negativo/nulo", "Soma de pesos inválida"],
            exception_destination="Estado BLOCKED com motivo explícito na tela",
            classification=StepClassification.CODE,
            observed_time_minutes=None,
            estimated_time_minutes=0.05,
        ),
        ProcessStep(
            step_id="step_r2_compute_metrics",
            name="Cálculo determinístico de métricas e atribuições",
            objective="Calcular variações, retornos da carteira, contribuições em bps e spread vs IBOV.",
            inputs=["Cotações validadas", "Posições validadas"],
            outputs=["Dicionário de métricas financeiras reconciliadas"],
            responsible="Sistema (Código)",
            dependencies=["step_r1_load_validate"],
            completion_rule="Métricas calculadas por funções puras; soma das contribuições = retorno carteira.",
            exceptions=["Inconsistência de reconciliação matemática"],
            exception_destination="Estado FAILED com log de auditoria",
            classification=StepClassification.CODE,
            observed_time_minutes=None,
            estimated_time_minutes=0.05,
        ),
        ProcessStep(
            step_id="step_r3_organize_evidence",
            name="Construção do FactBook e filtro de notícias",
            objective="Criar repositório imutável de fatos numerados e filtrar notícias pré-corte.",
            inputs=["Métricas calculadas", "Notícias validadas", "Manifesto"],
            outputs=["FactBook estruturado", "Lista de notícias elegíveis"],
            responsible="Sistema (Código)",
            dependencies=["step_r2_compute_metrics"],
            completion_rule="FactBook indexado por fact_id único; notícias pós-corte documentadas e excluídas.",
            exceptions=["Fato obrigatório ausente no catálogo"],
            exception_destination="Estado BLOCKED",
            classification=StepClassification.CODE,
            observed_time_minutes=None,
            estimated_time_minutes=0.05,
        ),
        ProcessStep(
            step_id="step_r4_draft_narrative",
            name="Redigir rascunho com placeholders delimitados",
            objective="Gerar texto estruturado usando FactBook e notícias, com placeholders {{fact:id}}.",
            inputs=["FactBook", "Notícias elegíveis", "Instruções de estilo"],
            outputs=["CommentaryDraft estruturado com placeholders e referências"],
            responsible="IA / Demo determinístico",
            dependencies=["step_r3_organize_evidence"],
            completion_rule="Rascunho retornado em JSON estruturado com parágrafos e tipos de afirmação.",
            exceptions=["Erro de conexão ou schema inválido no LLM"],
            exception_destination="Até 1 retentativa de formato; fallback para DemoProvider ou FAILED",
            classification=StepClassification.AI,
            observed_time_minutes=None,
            estimated_time_minutes=0.2,
        ),
        ProcessStep(
            step_id="step_r5_check_draft",
            name="Conferência determinística do rascunho",
            objective="Resolver placeholders, checar integridade de referências e barrar números fabricados.",
            inputs=["CommentaryDraft", "FactBook"],
            outputs=["Texto renderizado determinístico", "Relatório de verificações"],
            responsible="Sistema (Código)",
            dependencies=["step_r4_draft_narrative"],
            completion_rule="Todos os placeholders resolvidos; zero números financeiros não referenciados.",
            exceptions=["Placeholder não resolvido", "Número financeiro alucinado", "Violação de palavra"],
            exception_destination="Estado FAILED ou devolução para revisão com alerta crítico",
            classification=StepClassification.CODE,
            observed_time_minutes=None,
            estimated_time_minutes=0.05,
        ),
        ProcessStep(
            step_id="step_r6_human_review",
            name="Revisão humana lado a lado com evidências",
            objective="Inspecionar comentário e fatos/notícias simultaneamente; editar se necessário.",
            inputs=["Texto conferido", "Painel de Evidências"],
            outputs=["Texto revisado", "Nova revisão numerada se editado"],
            responsible="Revisor Humano",
            dependencies=["step_r5_check_draft"],
            completion_rule="Revisor inspeciona as afirmações e decide pela aprovação ou rejeição.",
            exceptions=["Discordância com a interpretação de mercado"],
            exception_destination="Edição no painel ou estado REJECTED com justificativa",
            classification=StepClassification.HUMAN,
            observed_time_minutes=None,
            estimated_time_minutes=5.0,
        ),
        ProcessStep(
            step_id="step_r7_human_approval",
            name="Aprovação explícita vinculada a hash",
            objective="Registrar autorização humana formal com vinculação aos hashes de texto e dados.",
            inputs=["Revisão final", "Hashes de entrada, fatos e texto"],
            outputs=["Approval Record assinado com approval_hash"],
            responsible="Revisor Humano",
            dependencies=["step_r6_human_review"],
            completion_rule="Revisor clica em 'Aprovar Comentário'; approval_hash gerado e gravado no SQLite.",
            exceptions=["Tentativa de autoaprovação pelo sistema"],
            exception_destination="Ação bloqueada por código",
            classification=StepClassification.HUMAN,
            observed_time_minutes=None,
            estimated_time_minutes=0.5,
        ),
        ProcessStep(
            step_id="step_r8_export_artifacts",
            name="Exportação segura de artefatos",
            objective="Gerar Markdown, HTML estilizado e JSON do bundle com verificação de aprovação.",
            inputs=["Comentário aprovado", "Approval Hash", "Metadados"],
            outputs=["comentario.md", "comentario.html", "bundle.json em outputs/"],
            responsible="Sistema (Código)",
            dependencies=["step_r7_human_approval"],
            completion_rule="Arquivos gerados com tag de dados simulados; hashes validados.",
            exceptions=["Texto alterado após aprovação ou aprovação ausente"],
            exception_destination="Exportação estritamente bloqueada com erro",
            classification=StepClassification.CODE,
            observed_time_minutes=None,
            estimated_time_minutes=0.05,
        ),
    ]

    return ProcessSpec(
        process_id="processo_redesenhado_ai_notes_08",
        title="Processo Redesenhado (AI Notes #8)",
        description=(
            "Redesenho ponta a ponta do processo: etapas mecânicas eliminadas ou transferidas "
            "para código puro; IA delimitada estritamente à redação estruturada com placeholders; "
            "revisão humana focada em interpretação e aprovação vinculada a hash criptográfico."
        ),
        is_redesign=True,
        steps=steps,
    )


def save_process_spec(spec: ProcessSpec, filepath: str | Path) -> None:
    """Salva a especificação do processo em arquivo JSON."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(spec.model_dump_json(indent=2))


def load_process_spec(filepath: str | Path) -> ProcessSpec:
    """Carrega uma especificação de processo a partir de arquivo JSON."""
    path = Path(filepath)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return ProcessSpec.model_validate(data)
