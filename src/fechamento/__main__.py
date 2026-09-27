"""Interface de linha de comando (CLI) do projeto Fechamento — AI Notes #8.

Permite executar a demonstração determinística, validar pacotes de dados,
revisar, aprovar e exportar artefatos diretamente pelo terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .contracts import WorkflowState
from .exports import export_artifacts
from .ingestion import load_and_validate_package
from .providers.demo_provider import DemoProvider
from .storage import Storage
from .workflow import WorkflowController


def cmd_demo(args: argparse.Namespace) -> None:
    """Executa a demonstração determinística offline a partir do pacote normal."""
    package_dir = Path("data/demo/normal")
    if not package_dir.exists():
        print(f"Erro: diretório de demonstração {package_dir} não encontrado.", file=sys.stderr)
        sys.exit(1)

    print("==================================================================")
    print("  FECHAMENTO — AI NOTES #8: DEMONSTRAÇÃO DETERMINÍSTICA (CLI)")
    print("==================================================================")
    print("Aviso: Todos os dados, carteira e notícias são ESTRITAMENTE SIMULADOS.\n")

    storage = Storage()
    controller = WorkflowController(storage=storage)
    provider = DemoProvider()

    print(f"[*] Ingerindo pacote e executando fluxo funcional em '{package_dir}'...")
    ctx = controller.execute_flow(package_dir, provider)

    print(f"[*] Estado final da execução: {ctx.run.state.value}")
    print(f"[*] Run ID: {ctx.run.run_id}")

    if ctx.run.state == WorkflowState.BLOCKED:
        print(f"\n[!] PROCESSO BLOQUEADO: {ctx.run.blocking_reason}")
        sys.exit(1)

    if ctx.run.state == WorkflowState.FAILED:
        print(f"\n[!] PROCESSO FALHOU: {ctx.run.blocking_reason}")
        sys.exit(1)

    # Exibição das métricas calculadas
    if ctx.metrics:
        print("\n--- RESUMO QUANTITATIVO (Cálculo Determinístico em Código) ---")
        print(f" - IBOV (simulado): {ctx.metrics.ibov_return_pct * 100:+.2f}%")
        print(f" - USD/BRL: {ctx.metrics.usd_brl.change_pct * 100:+.2f}% ({ctx.metrics.usd_brl.direction_description})")
        print(f" - Carteira Long-Only: {ctx.metrics.portfolio_return_pct * 100:+.2f}%")
        print(f" - Spread vs IBOV: {ctx.metrics.portfolio_vs_ibov_bps:+.1f} bps")
        print(f" - Reconciliação Matemática: {'CONFORME' if ctx.metrics.reconciled else 'DIVERGENTE'}")
        print("\nTop Contribuidores Positivos:")
        for a in ctx.metrics.top_positive_contributors[:3]:
            print(f"   * {a.ticker} ({a.sector}): {a.return_pct * 100:+.2f}% retorno | {a.contribution_bps:+.1f} bps contribuição")
        print("Top Detratores:")
        for a in ctx.metrics.top_negative_contributors[:3]:
            print(f"   * {a.ticker} ({a.sector}): {a.return_pct * 100:+.2f}% retorno | {a.contribution_bps:+.1f} bps contribuição")

    if ctx.ingestion and ctx.ingestion.excluded_news:
        print("\n--- EXCLUSÕES DOCUMENTADAS (Filtro de Corte) ---")
        for n, reason in ctx.ingestion.excluded_news:
            print(f" - [{n.news_id}] {n.title[:50]}... -> Excluída: {reason}")

    print("\n--- CONFERÊNCIA DETERMINÍSTICA DO RASCUNHO ---")
    for check in ctx.checks:
        status = "[PASS]" if check.passed else "[FAIL]"
        print(f" {status} {check.name}")

    print("\n--- RASCUNHO DO COMENTÁRIO (Aguardando Revisão Humana) ---")
    print(ctx.latest_revision.text if ctx.latest_revision else "Nenhum texto gerado.")

    print("\n==================================================================")
    print("O sistema interrompeu propositalmente no estado IN_REVIEW.")
    print("A aplicação NÃO se autoaprova.")
    print("Para aprovar e exportar via CLI, utilize:")
    print(f"  uv run python -m fechamento approve {ctx.run.run_id} --approver \"Seu Nome\"")
    print(f"  uv run python -m fechamento export {ctx.run.run_id}")
    print("Ou abra a interface web:")
    print("  uv run streamlit run app.py --server.address 127.0.0.1")
    print("==================================================================")


def cmd_approve(args: argparse.Namespace) -> None:
    """Aprova explicitamente uma execução específica."""
    storage = Storage()
    run = storage.get_run(args.run_id)
    if not run:
        print(f"Erro: Run '{args.run_id}' não encontrada no histórico.", file=sys.stderr)
        sys.exit(1)

    revisions = storage.get_revisions(args.run_id)
    if not revisions:
        print(f"Erro: Nenhuma revisão encontrada para a run '{args.run_id}'.", file=sys.stderr)
        sys.exit(1)

    # Reconstrução do contexto para aprovação
    controller = WorkflowController(storage=storage)
    package_dir = Path("data/real") / run.scenario_id
    if not package_dir.exists():
        package_dir = Path("data/demo") / run.scenario_id
    if not package_dir.exists():
        package_dir = Path("data/demo/normal")

    from .workflow import WorkflowContext
    ctx = WorkflowContext(
        run=run,
        package_dir=package_dir,
        revisions=revisions,
    )

    ctx = controller.approve(ctx, approver=args.approver)
    print(f"[+] Run '{args.run_id}' APROVADA com sucesso por '{args.approver}'!")
    print(f"[+] Approval Hash: {ctx.run.approval_hash}")
    print(f"Para exportar: uv run python -m fechamento export {args.run_id}")


def cmd_export(args: argparse.Namespace) -> None:
    """Exporta artefatos de uma run aprovada."""
    storage = Storage()
    run = storage.get_run(args.run_id)
    if not run:
        print(f"Erro: Run '{args.run_id}' não encontrada.", file=sys.stderr)
        sys.exit(1)

    if run.state != WorkflowState.APPROVED:
        print(f"Erro: Run '{args.run_id}' está no estado '{run.state.value}'. Apenas runs APPROVED podem ser exportadas.", file=sys.stderr)
        sys.exit(1)

    revisions = storage.get_revisions(args.run_id)
    package_dir = Path("data/real") / run.scenario_id
    if not package_dir.exists():
        package_dir = Path("data/demo") / run.scenario_id
    if not package_dir.exists():
        package_dir = Path("data/demo/normal")

    # Reconstrução do contexto para exportação sem resetar o estado
    from .evidence import organize_evidence
    from .metrics import compute_all_metrics
    from .workflow import WorkflowContext

    ingestion = load_and_validate_package(package_dir)
    metrics = compute_all_metrics(ingestion.quotes, ingestion.positions)
    evidence = organize_evidence(
        metrics=metrics,
        manifest=ingestion.manifest,  # type: ignore[arg-type]
        eligible_news=ingestion.eligible_news,
        excluded_news=ingestion.excluded_news,
    )
    ctx = WorkflowContext(
        run=run,
        package_dir=package_dir,
        ingestion=ingestion,
        metrics=metrics,
        evidence=evidence,
        revisions=revisions,
    )

    paths = export_artifacts(ctx, output_base_dir=args.output_dir)
    print(f"[+] Exportação concluída com sucesso para a run '{args.run_id}':")
    for k, p in paths.items():
        print(f" - {k}: {p}")


def cmd_run(args: argparse.Namespace) -> None:
    """Executa o pipeline funcional permitindo escolher cenário e provedor."""
    package_dir = Path(args.scenario_dir)
    if not package_dir.exists():
        print(f"Erro: diretório de dados '{package_dir}' não encontrado.", file=sys.stderr)
        sys.exit(1)

    storage = Storage()
    controller = WorkflowController(storage=storage)

    if args.provider.lower() == "openrouter":
        from .providers.openrouter_provider import OpenRouterProvider
        model = args.model or "openrouter/free"
        if not (model == "openrouter/free" or model.endswith(":free")) and not args.allow_paid:
            print("Erro: modelo pago exige --allow-paid. Para esta edição use --model openrouter/free.", file=sys.stderr)
            sys.exit(1)
        provider = OpenRouterProvider(model_name=model)
        if not provider.api_key.strip():
            print("Erro: configure OPENROUTER_API_KEY no arquivo .env da pasta do projeto. Crie sua chave em https://openrouter.ai/settings/keys. A demo funciona sem chave.", file=sys.stderr)
            sys.exit(1)
    elif args.provider.lower() == "gemini":
        from .providers.gemini_provider import GeminiProvider
        provider = GeminiProvider(model_name=args.model or "gemini-2.5-flash", enabled=True)
    else:
        provider = DemoProvider()

    print("==================================================================")
    print(f"  FECHAMENTO — EXECUÇÃO (Provedor: {provider.__class__.__name__})")
    print(f"  Cenário: {package_dir}")
    print("==================================================================\n")

    ctx = controller.execute_flow(package_dir, provider)
    print(f"[*] Estado final: {ctx.run.state.value}")
    print(f"[*] Run ID: {ctx.run.run_id}")

    if ctx.run.state == WorkflowState.BLOCKED:
        print(f"\n[!] PROCESSO BLOQUEADO: {ctx.run.blocking_reason}")
        sys.exit(1)

    if ctx.run.state == WorkflowState.FAILED:
        print(f"\n[!] PROCESSO FALHOU: {ctx.run.blocking_reason}")
        sys.exit(1)

    if ctx.metrics:
        print("\n--- RESUMO QUANTITATIVO DETERMINÍSTICO ---")
        print(f" - IBOV: {ctx.metrics.ibov_return_pct * 100:+.2f}%")
        print(f" - USD/BRL: {ctx.metrics.usd_brl.change_pct * 100:+.2f}% ({ctx.metrics.usd_brl.direction_description})")
        print(f" - Carteira: {ctx.metrics.portfolio_return_pct * 100:+.2f}%")
        print(f" - Spread vs IBOV: {ctx.metrics.portfolio_vs_ibov_bps:+.1f} bps")

    if ctx.ingestion and ctx.ingestion.manifest:
        print(f"\nData de referência: {ctx.ingestion.manifest.reference_date}")
        if ctx.ingestion.manifest.is_synthetic:
            print("ATENÇÃO: O PACOTE CONTÉM DADOS OU CARTEIRA SIMULADOS.")
        if ctx.ingestion.manifest.data_notice:
            print(ctx.ingestion.manifest.data_notice)
    for check in ctx.checks:
        print(f"[{'PASS' if check.passed else 'ATENÇÃO'}] {check.name}")
    print("\n--- RASCUNHO GERADO ---")
    print(ctx.latest_revision.text if ctx.latest_revision else "Nenhum texto.")


def cmd_fetch(args: argparse.Namespace) -> None:
    """Coleta sem chave de IA, preservando o pacote anterior."""
    from .live_fetcher import build_live_market_package
    try:
        package = build_live_market_package(args.output_dir)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Coleta interrompida: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Pacote salvo em: {package}")
    print("Cotações públicas; CARTEIRA SIMULADA. Confira horários e limitações em sources.json.")
    print(f'Próximo passo: uv run python -m fechamento run --scenario-dir "{package}" --provider demo')


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="fechamento",
        description="Fechamento — AI Notes #8: Redesenho do processo de fechamento de mercado.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcomando demo
    sub_demo = subparsers.add_parser("demo", help="Executa a demonstração determinística offline.")
    sub_demo.set_defaults(func=cmd_demo)

    sub_fetch = subparsers.add_parser("fetch", help="Coleta dados públicos e cria uma carteira didática, sem usar IA.")
    sub_fetch.add_argument("--output-dir", required=True, help="Pasta nova para os dados; não sobrescreve pacotes existentes.")
    sub_fetch.set_defaults(func=cmd_fetch)

    # Subcomando run
    sub_run = subparsers.add_parser("run", help="Executa o pipeline especificando cenário e provedor.")
    sub_run.add_argument("--scenario-dir", default="data/demo/normal", help="Caminho do pacote; padrão: demonstração simulada.")
    sub_run.add_argument("--provider", default="demo", choices=["demo", "openrouter", "gemini"], help="Provedor de narrativa.")
    sub_run.add_argument("--model", default=None, help="OpenRouter: openrouter/free por padrão. Gemini: gemini-2.5-flash.")
    sub_run.add_argument("--allow-paid", action="store_true", help="Autoriza explicitamente um modelo pago do OpenRouter.")
    sub_run.set_defaults(func=cmd_run)

    # Subcomando approve
    sub_app = subparsers.add_parser("approve", help="Aprova um comentário em revisão.")
    sub_app.add_argument("run_id", help="Identificador da execução.")
    sub_app.add_argument("--approver", default="Revisor Humano", help="Nome do aprovador.")
    sub_app.set_defaults(func=cmd_approve)

    # Subcomando export
    sub_exp = subparsers.add_parser("export", help="Exporta artefatos de uma execução aprovada.")
    sub_exp.add_argument("run_id", help="Identificador da execução.")
    sub_exp.add_argument("--output-dir", default="outputs", help="Diretório de saída.")
    sub_exp.set_defaults(func=cmd_export)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
