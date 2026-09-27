"""Máquina de estados explícita e orquestrador do fluxo funcional do Fechamento.

Controla a progressão:
CREATED -> INPUTS_VALIDATED -> METRICS_READY -> DRAFT_READY -> CHECKED -> IN_REVIEW -> APPROVED -> EXPORTED
Caminhos de exceção: BLOCKED, REJECTED, FAILED.

Garante que a aprovação humana seja vinculada aos hashes de entrada, fatos e texto,
e que edições posteriores invalidem a aprovação.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .contracts import (
    CommentaryDraft,
    RevisionRecord,
    ValidationCheckResult,
    WorkflowRun,
    WorkflowState,
)
from .evidence import EvidencePackage, compute_factbook_hash, organize_evidence
from .ingestion import IngestionResult, load_and_validate_package
from .metrics import CalculatedMetrics, compute_all_metrics
from .providers.base import NarrativeProvider, NarrativeRequest
from .storage import Storage
from .validation import validate_draft


def compute_text_hash(text: str) -> str:
    """Gera hash SHA-256 do texto do rascunho ou revisão."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def compute_approval_hash(
    inputs_hash: str,
    facts_hash: str,
    text_hash: str,
    approver: str,
) -> str:
    """Calcula o hash de aprovação vinculando todas as peças do quebra-cabeça."""
    raw = f"{inputs_hash}:{facts_hash}:{text_hash}:{approver}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class WorkflowContext:
    run: WorkflowRun
    package_dir: Path
    ingestion: IngestionResult | None = None
    metrics: CalculatedMetrics | None = None
    evidence: EvidencePackage | None = None
    draft: CommentaryDraft | None = None
    checks: list[ValidationCheckResult] = field(default_factory=list)
    revisions: list[RevisionRecord] = field(default_factory=list)
    storage: Storage | None = field(default=None, repr=False)

    @property
    def latest_revision(self) -> RevisionRecord | None:
        return self.revisions[-1] if self.revisions else None


class WorkflowController:
    def __init__(self, storage: Storage | None = None) -> None:
        self.storage = storage or Storage()

    def execute_flow(
        self,
        package_dir: str | Path,
        provider: NarrativeProvider,
        run_id: str | None = None,
    ) -> WorkflowContext:
        """Executa o pipeline funcional do início até o estado IN_REVIEW (ou BLOCKED/FAILED).

        A aplicação JAMAIS se autoaprova: ela para em IN_REVIEW para inspeção humana.
        """
        pdir = Path(package_dir)
        actual_run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        now = datetime.now(UTC)

        # 1. Estado CREATED
        run = WorkflowRun(
            run_id=actual_run_id,
            scenario_id=pdir.name,
            state=WorkflowState.CREATED,
            created_at=now,
            updated_at=now,
            inputs_hash="pending",
        )
        self.storage.save_run(run)
        self.storage.log_audit_event(actual_run_id, "RUN_CREATED", f"Execução iniciada para o cenário {pdir}")

        ctx = WorkflowContext(run=run, package_dir=pdir, storage=self.storage)

        # 2. Ingestão e Validação de Entradas
        ingestion = load_and_validate_package(pdir)
        ctx.ingestion = ingestion

        if ingestion.is_blocked:
            reason = " | ".join(ingestion.blocking_errors)
            run = WorkflowRun(
                **{
                    **run.model_dump(),
                    "state": WorkflowState.BLOCKED,
                    "updated_at": datetime.now(UTC),
                    "blocking_reason": reason,
                }
            )
            ctx.run = run
            self.storage.save_run(run)
            self.storage.log_audit_event(actual_run_id, "STATE_BLOCKED", f"Falha na validação de entrada: {reason}")
            return ctx

        # Cálculo do hash canônico das entradas
        inputs_combined = "".join(f.sha256 for f in ingestion.manifest.files)  # type: ignore[union-attr]
        inputs_hash = hashlib.sha256(inputs_combined.encode("utf-8")).hexdigest()

        run = WorkflowRun(
            **{
                **run.model_dump(),
                "state": WorkflowState.INPUTS_VALIDATED,
                "updated_at": datetime.now(UTC),
                "inputs_hash": inputs_hash,
            }
        )
        ctx.run = run
        self.storage.save_run(run)

        # 3. Cálculos Financeiros
        try:
            metrics = compute_all_metrics(ingestion.quotes, ingestion.positions)
            ctx.metrics = metrics
        except Exception as e:
            run = WorkflowRun(
                **{
                    **run.model_dump(),
                    "state": WorkflowState.FAILED,
                    "updated_at": datetime.now(UTC),
                    "blocking_reason": f"Erro nos cálculos de métricas: {e}",
                }
            )
            ctx.run = run
            self.storage.save_run(run)
            self.storage.log_audit_event(actual_run_id, "STATE_FAILED", str(e))
            return ctx

        if not metrics.reconciled:
            reason = f"Divergência de reconciliação matemática da carteira ({metrics.reconciliation_diff_bps:.4f} bps)."
            run = WorkflowRun(
                **{
                    **run.model_dump(),
                    "state": WorkflowState.FAILED,
                    "updated_at": datetime.now(UTC),
                    "blocking_reason": reason,
                }
            )
            ctx.run = run
            self.storage.save_run(run)
            self.storage.log_audit_event(actual_run_id, "STATE_FAILED", reason)
            return ctx

        run = WorkflowRun(
            **{
                **run.model_dump(),
                "state": WorkflowState.METRICS_READY,
                "updated_at": datetime.now(UTC),
            }
        )
        ctx.run = run
        self.storage.save_run(run)

        # 4. Organização de Evidências e FactBook
        assert ingestion.manifest is not None
        evidence = organize_evidence(
            metrics=metrics,
            manifest=ingestion.manifest,
            eligible_news=ingestion.eligible_news,
            excluded_news=ingestion.excluded_news,
        )
        ctx.evidence = evidence
        facts_hash = compute_factbook_hash(evidence.factbook)

        # 5. Geração do Rascunho Narrativo
        req = NarrativeRequest(
            factbook=evidence.factbook,
            eligible_news=evidence.eligible_news,
        )
        narrative_res = provider.generate(req)

        if not narrative_res.success or narrative_res.draft is None:
            reason = narrative_res.error_message or "Falha desconhecida na geração da narrativa."
            run = WorkflowRun(
                **{
                    **run.model_dump(),
                    "state": WorkflowState.FAILED,
                    "updated_at": datetime.now(UTC),
                    "blocking_reason": reason,
                    "provider_used": narrative_res.provider_name,
                    "latency_ms": narrative_res.latency_ms,
                }
            )
            ctx.run = run
            self.storage.save_run(run)
            self.storage.log_audit_event(actual_run_id, "STATE_FAILED", reason)
            return ctx

        draft = narrative_res.draft
        draft_hash = compute_text_hash(
            "\n\n".join(p.text for p in draft.paragraphs)
        )

        run = WorkflowRun(
            **{
                **run.model_dump(),
                "state": WorkflowState.DRAFT_READY,
                "updated_at": datetime.now(UTC),
                "facts_hash": facts_hash,
                "draft_hash": draft_hash,
                "provider_used": narrative_res.provider_name,
                "latency_ms": narrative_res.latency_ms,
                "token_usage": narrative_res.token_usage,
                "cost_usd": narrative_res.cost_usd,
            }
        )
        ctx.run = run
        self.storage.save_run(run)

        # 6. Conferência Determinística do Rascunho
        checked_draft, checks = validate_draft(draft, evidence.factbook, evidence.eligible_news)
        ctx.draft = checked_draft
        ctx.checks = checks

        critical_failures = [c for c in checks if not c.passed and c.severity == "critical"]
        if critical_failures:
            reason = "Falhas críticas na conferência do rascunho: " + "; ".join(c.details for c in critical_failures)
            run = WorkflowRun(
                **{
                    **run.model_dump(),
                    "state": WorkflowState.FAILED,
                    "updated_at": datetime.now(UTC),
                    "blocking_reason": reason,
                }
            )
            ctx.run = run
            self.storage.save_run(run)
            self.storage.log_audit_event(actual_run_id, "STATE_FAILED", reason)
            return ctx

        # Estado CHECKED alcançado com sucesso
        run = WorkflowRun(
            **{
                **run.model_dump(),
                "state": WorkflowState.CHECKED,
                "updated_at": datetime.now(UTC),
            }
        )
        ctx.run = run
        self.storage.save_run(run)

        # 7. Transição para IN_REVIEW e criação da Revisão 1
        initial_text = checked_draft.rendered_text or ""
        initial_hash = compute_text_hash(initial_text)
        rev_1 = RevisionRecord(
            revision_number=1,
            text=initial_text,
            created_at=datetime.now(UTC),
            created_by=narrative_res.provider_name,
            text_hash=initial_hash,
            checks_passed=True,
            notes="Rascunho inicial conferido por código.",
        )
        ctx.revisions = [rev_1]
        self.storage.add_revision(actual_run_id, rev_1)

        run = WorkflowRun(
            **{
                **run.model_dump(),
                "state": WorkflowState.IN_REVIEW,
                "updated_at": datetime.now(UTC),
            }
        )
        ctx.run = run
        self.storage.save_run(run)
        self.storage.log_audit_event(actual_run_id, "STATE_IN_REVIEW", "Rascunho disponibilizado para revisão humana.")

        return ctx

    def edit_text(
        self,
        ctx: WorkflowContext,
        new_text: str,
        author: str = "Revisor Humano",
        notes: str = "",
    ) -> WorkflowContext:
        """Registra uma nova revisão após edição pelo revisor humano.

        Se o rascunho já estava APROVADO, revoga a aprovação e retorna a IN_REVIEW.
        """
        new_hash = compute_text_hash(new_text)
        next_rev_num = (ctx.latest_revision.revision_number + 1) if ctx.latest_revision else 1

        new_rev = RevisionRecord(
            revision_number=next_rev_num,
            text=new_text,
            created_at=datetime.now(UTC),
            created_by=author,
            text_hash=new_hash,
            checks_passed=True,
            notes=notes or "Edição manual pelo revisor.",
        )

        ctx.revisions.append(new_rev)
        self.storage.add_revision(ctx.run.run_id, new_rev)

        # Invalidação da aprovação caso estivesse aprovado
        was_approved = ctx.run.state == WorkflowState.APPROVED
        ctx.run = WorkflowRun(
            **{
                **ctx.run.model_dump(),
                "state": WorkflowState.IN_REVIEW,
                "updated_at": datetime.now(UTC),
                "approval_hash": None,
                "approved_by": None,
                "approved_at": None,
            }
        )
        self.storage.save_run(ctx.run)
        event_msg = f"Revisão #{next_rev_num} criada por {author}."
        if was_approved:
            event_msg += " Aprovação anterior revogada devido a alteração no texto."
        self.storage.log_audit_event(ctx.run.run_id, "REVISION_CREATED", event_msg)

        return ctx

    def approve(
        self,
        ctx: WorkflowContext,
        approver: str = "Revisor Humano",
    ) -> WorkflowContext:
        """Registra a aprovação humana explícita vinculada aos hashes de entrada, fatos e texto."""
        if ctx.run.state not in (WorkflowState.IN_REVIEW, WorkflowState.CHECKED):
            raise ValueError(f"Não é permitido aprovar no estado atual: {ctx.run.state.value}")

        if not ctx.latest_revision:
            raise ValueError("Não há revisão disponível para aprovação.")

        text_hash = ctx.latest_revision.text_hash
        facts_hash = ctx.run.facts_hash or ""
        inputs_hash = ctx.run.inputs_hash

        app_hash = compute_approval_hash(inputs_hash, facts_hash, text_hash, approver)
        now = datetime.now(UTC)

        ctx.run = WorkflowRun(
            **{
                **ctx.run.model_dump(),
                "state": WorkflowState.APPROVED,
                "updated_at": now,
                "approval_hash": app_hash,
                "approved_by": approver,
                "approved_at": now,
            }
        )
        self.storage.save_run(ctx.run)
        self.storage.log_audit_event(
            ctx.run.run_id,
            "STATE_APPROVED",
            f"Comentário aprovado formalmente por {approver}. Hash: {app_hash}",
        )
        return ctx

    def reject(
        self,
        ctx: WorkflowContext,
        reason: str,
        rejector: str = "Revisor Humano",
    ) -> WorkflowContext:
        """Rejeita o comentário com justificativa documentada."""
        now = datetime.now(UTC)
        ctx.run = WorkflowRun(
            **{
                **ctx.run.model_dump(),
                "state": WorkflowState.REJECTED,
                "updated_at": now,
                "blocking_reason": f"Rejeitado por {rejector}: {reason}",
            }
        )
        self.storage.save_run(ctx.run)
        self.storage.log_audit_event(ctx.run.run_id, "STATE_REJECTED", f"Rejeitado por {rejector}: {reason}")
        return ctx
