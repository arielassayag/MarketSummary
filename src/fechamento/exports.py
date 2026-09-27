"""Módulo de exportação segura de artefatos de fechamento de mercado.

Gera os arquivos finais em Markdown, HTML estilizado e JSON.
A exportação é estritamente bloqueada se o estado não for APPROVED ou se houver
qualquer divergência no hash do texto revisado em relação ao hash aprovado.
"""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from .contracts import WorkflowState
from .workflow import WorkflowContext, compute_approval_hash, verify_context_integrity

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #FFFFFF;
            color: #1C252E;
            line-height: 1.6;
            margin: 0;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 780px;
            margin: 0 auto;
            background: #FFFFFF;
            border: 1px solid #E0E0E0;
            border-radius: 8px;
            padding: 32px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        .badge-synthetic {{
            display: inline-block;
            background-color: #FF6200;
            color: #FFFFFF;
            font-weight: 700;
            font-size: 0.8rem;
            padding: 4px 10px;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 16px;
        }}
        .header {{
            border-bottom: 2px solid #C3EBF7;
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        h1 {{
            font-size: 1.6rem;
            color: #1C252E;
            margin: 0 0 8px 0;
        }}
        .meta {{
            font-size: 0.9rem;
            color: #637381;
        }}
        .content p {{
            margin-bottom: 1.2rem;
            text-align: justify;
        }}
        .footer {{
            margin-top: 32px;
            padding-top: 16px;
            border-top: 1px solid #E0E0E0;
            font-size: 0.8rem;
            color: #637381;
            background-color: #F8F9FA;
            padding: 16px;
            border-radius: 6px;
        }}
        .hash-code {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            background: #EEEEEE;
            padding: 2px 6px;
            border-radius: 4px;
            word-break: break-all;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="badge-synthetic">Dados Simulados — AI Notes #8</div>
        <div class="header">
            <h1>Comentário de Fechamento de Mercado</h1>
            <div class="meta">
                <strong>Data de Referência:</strong> {reference_date} &bull;
                <strong>Fuso Horário:</strong> America/Sao_Paulo &bull;
                <strong>Aprovado por:</strong> {approved_by}
            </div>
        </div>
        <div class="content">
            {content_html}
        </div>
        <div class="footer">
            <div><strong>Selo de Governança e Versão (Hash SHA-256):</strong></div>
            <div class="hash-code">{approval_hash}</div>
            <div style="margin-top: 8px;">
                {disclaimer}
            </div>
        </div>
    </div>
</body>
</html>
"""


def sanitize_filename(name: str) -> str:
    """Evita path traversal e caracteres perigosos no nome de arquivos."""
    clean = re.sub(r"\.\.+", "_", name)
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", clean)
    return clean.strip("_") or "unnamed"


def export_artifacts(
    ctx: WorkflowContext,
    output_base_dir: str | Path = "outputs",
) -> dict[str, Path]:
    """Exporta o comentário aprovado nos formatos Markdown, HTML e JSON.

    Bloqueia estritamente se o estado não for APPROVED ou se o hash divergir.
    """
    if ctx.run.state != WorkflowState.APPROVED:
        raise PermissionError(
            f"Exportação estritamente bloqueada: o processo está no estado '{ctx.run.state.value}'. "
            "A exportação final requer aprovação humana prévia."
        )

    if not ctx.latest_revision:
        raise ValueError("Exportação bloqueada: nenhuma revisão encontrada no contexto.")

    if not ctx.run.approval_hash:
        raise ValueError("Exportação bloqueada: hash de aprovação ausente.")

    verify_context_integrity(ctx)

    # Verificação de segurança criptográfica: o hash do texto atual bate com o hash aprovado?
    expected_hash = compute_approval_hash(
        inputs_hash=ctx.run.inputs_hash,
        facts_hash=ctx.run.facts_hash or "",
        text_hash=ctx.latest_revision.text_hash,
        approver=ctx.run.approved_by or "",
    )

    if expected_hash != ctx.run.approval_hash:
        raise ValueError(
            "Exportação bloqueada: o texto atual foi modificado após a aprovação! "
            f"Hash aprovado: {ctx.run.approval_hash} | Hash recalculado: {expected_hash}"
        )

    # Diretório seguro de exportação
    safe_run_id = sanitize_filename(ctx.run.run_id)
    out_dir = Path(output_base_dir) / safe_run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    final_text = ctx.latest_revision.text
    ref_date = str(ctx.evidence.factbook.reference_date) if ctx.evidence else "N/A"
    approver = ctx.run.approved_by or "Revisor Humano"
    app_hash = ctx.run.approval_hash

    is_synthetic = ctx.evidence.factbook.is_synthetic if ctx.evidence else True

    # 1. Exportação Markdown (comentario.md)
    md_path = out_dir / "comentario.md"
    if is_synthetic:
        header_title = "# Comentário de Fechamento de Mercado — DADOS SIMULADOS\n\n"
        header_warning = "> **Aviso**: Todos os números, carteira e notícias deste documento são estritamente simulados.\n\n"
        badge_html = '<div class="badge-synthetic">Dados Simulados — AI Notes #8</div>'
        page_title = "Comentário de Fechamento — DADOS SIMULADOS"
        disclaimer = (
            "Este documento é uma demonstração didática gerada pelo projeto Fechamento — AI Notes #8. "
            "Valores, pesos e notícias são estritamente simulados."
        )
    else:
        header_title = "# Comentário de Fechamento de Mercado — DADOS REAIS B3 / BACEN\n\n"
        header_warning = "> **Proveniência**: Dados 100% reais extraídos da B3 Oficial e Banco Central do Brasil (PTAX Olinda).\n\n"
        badge_html = '<div class="badge-synthetic" style="background-color: #1B5E20;">Dados 100% Reais — B3 & BACEN</div>'
        page_title = "Comentário de Fechamento — DADOS REAIS B3 / BACEN"
        disclaimer = (
            "Este documento foi gerado a partir de dados 100% reais da B3, Banco Central do Brasil (PTAX), "
            "BrasilAPI e AwesomeAPI pelo projeto Fechamento — AI Notes #8."
        )

    data_notice = ctx.evidence.factbook.data_notice if ctx.evidence else ""
    if data_notice:
        header_title = "# Comentário de Mercado — CONTÉM DADOS OU CARTEIRA SIMULADOS\n\n" if is_synthetic else "# Comentário de Mercado\n\n"
        header_warning = f"> **Limitações e origem dos dados:** {data_notice}\n\n"
        disclaimer = data_notice
        badge_html = '<div class="badge-synthetic">Contém dados ou carteira simulados</div>' if is_synthetic else '<div class="badge-synthetic">Dados declarados reais no pacote</div>'

    md_content = (
        f"{header_title}"
        f"{header_warning}"
        f"- **Data de Referência:** {ref_date}\n"
        f"- **Aprovado por:** {approver}\n"
        f"- **Data de Aprovação:** {ctx.run.approved_at.isoformat() if ctx.run.approved_at else 'N/A'}\n"
        f"- **Approval Hash (SHA-256):** `{app_hash}`\n\n"
        f"---\n\n"
        f"{final_text}\n\n"
        f"---\n\n"
        f"*Documento gerado e aprovado via Fechamento — AI Notes #8.*\n"
    )
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # 2. Exportação HTML estilizado e escapado (comentario.html)
    html_path = out_dir / "comentario.html"
    paragraphs_escaped = [
        f"<p>{html.escape(p.strip())}</p>"
        for p in final_text.split("\n\n")
        if p.strip()
    ]
    content_html = "\n            ".join(paragraphs_escaped)

    html_content = HTML_TEMPLATE.format(
        page_title=html.escape(page_title),
        reference_date=html.escape(ref_date),
        approved_by=html.escape(approver),
        content_html=content_html,
        approval_hash=html.escape(app_hash),
        disclaimer=html.escape(disclaimer),
    )
    # Substitui o badge se for dados reais
    if not is_synthetic or data_notice:
        html_content = html_content.replace(
            '<div class="badge-synthetic">Dados Simulados — AI Notes #8</div>',
            badge_html,
        )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # 3. Exportação JSON com bundle completo de fatos, referências e metadados (bundle.json)
    bundle_path = out_dir / "bundle.json"
    bundle_data = {
        "run_id": ctx.run.run_id,
        "scenario_id": ctx.run.scenario_id,
        "state": WorkflowState.EXPORTED.value,
        "is_synthetic": is_synthetic,
        "data_notice": data_notice,
        "reference_date": ref_date,
        "approved_by": approver,
        "approved_at": ctx.run.approved_at.isoformat() if ctx.run.approved_at else None,
        "approval_hash": app_hash,
        "inputs_hash": ctx.run.inputs_hash,
        "facts_hash": ctx.run.facts_hash,
        "text_hash": ctx.latest_revision.text_hash,
        "commentary_text": final_text,
        "facts": {
            f_id: f.model_dump(mode="json") for f_id, f in (ctx.evidence.factbook.facts if ctx.evidence else {}).items()
        },
        "checks": [c.model_dump(mode="json") for c in ctx.checks],
        "revisions": [r.model_dump(mode="json") for r in ctx.revisions],
        "exported_files": [
            "comentario.md",
            "comentario.html",
            "bundle.json",
        ],
    }
    with open(bundle_path, "w", encoding="utf-8") as f:
        json.dump(bundle_data, f, indent=2, ensure_ascii=False)

    # Transição do estado para EXPORTED
    ctx.run = ctx.run.model_copy(
        update={
            "state": WorkflowState.EXPORTED,
            "updated_at": datetime.now(UTC),
        }
    )
    if ctx.storage:
        ctx.storage.save_run(ctx.run)
        ctx.storage.log_audit_event(ctx.run.run_id, "STATE_EXPORTED", "Arquivos Markdown, HTML e JSON exportados.")

    return {
        "markdown": md_path,
        "html": html_path,
        "bundle": bundle_path,
    }
