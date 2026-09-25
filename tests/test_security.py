"""Testes de segurança e resiliência a ataques e injeções."""


from fechamento.exports import export_artifacts, sanitize_filename
from fechamento.providers import DemoProvider
from fechamento.storage import Storage
from fechamento.workflow import WorkflowController


def test_prompt_injection_in_news_does_not_affect_state_or_prices() -> None:
    """A notícia com tentativa de injeção ('ignore as regras...') não deve alterar preços nem permissões."""
    storage = Storage(":memory:")
    controller = WorkflowController(storage)

    # Executa com o pacote normal, que inclui a notícia maliciosa news_injection_test_01
    ctx = controller.execute_flow("data/demo/normal", DemoProvider())

    # Preços continuam corretos e intactos no FactBook
    petr_fact = ctx.evidence.factbook.get_fact("asset.PETR4.return_pct")
    assert petr_fact is not None
    assert petr_fact.value != 999.0  # Não alterou o preço para 999
    assert petr_fact.formatted_value == "+2,99%"

    # O estado não foi promovido para APPROVED
    assert ctx.run.state != "APPROVED"
    assert ctx.run.approval_hash is None


def test_path_traversal_sanitization() -> None:
    malicious_run_id = "../../../etc/passwd"
    sanitized = sanitize_filename(malicious_run_id)
    assert "/" not in sanitized
    assert ".." not in sanitized


def test_html_escaping_in_exports() -> None:
    """Garante que tags HTML/JS sejam devidamente escapadas no HTML exportado."""
    storage = Storage(":memory:")
    controller = WorkflowController(storage)
    ctx = controller.execute_flow("data/demo/normal", DemoProvider())

    # Injeta texto malicioso com script tag
    malicious_text = "Comentário com ataque <script>alert('XSS')</script> e <b>negrito</b>."
    ctx = controller.edit_text(ctx, malicious_text, author="Testador")
    ctx = controller.approve(ctx, approver="Aprovador")

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = export_artifacts(ctx, output_base_dir=tmpdir)
        html_file = paths["html"]
        with open(html_file, encoding="utf-8") as f:
            html_content = f.read()

        # Deve conter entidades escapadas &lt;script&gt; e NÃO a tag crua <script>
        assert "<script>" not in html_content
        assert "&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;" in html_content
