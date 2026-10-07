"""Revisão mensal dos modelos da cobertura (DADOS SIMULADOS): calendário, pacote do código,
validação da leitura da gestão, publicação imutável com evento na trilha e leitura para o portal.

Tudo offline: a cobertura sintética da demonstração (``cdp.cobertura.demo.gerar``) grava dois
retratos; os testes que gravam usam cópias do livro.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cdp.calendar import rebalance_schedule
from cdp.config import load_config
from cdp.workflow.demo import DEMO_HISTORY_START, DEMO_SEED, DemoStore, demo_sessions
from cdp.workflow.runtime import Runtime

R = pytest.importorskip("cdp.cobertura.revisao")

BRT = ZoneInfo("America/Sao_Paulo")
#: Mandato fixo (montagem às segundas, regra legada): as datas da demonstração não dependem de
#: mudanças em configs/cdp/fund.yaml.
LEGACY = Path(__file__).resolve().parent / "fixtures" / "fund_legado.yaml"
CFG = load_config(LEGACY)
SESSOES = demo_sessions(12, cfg=CFG)
D1, D2 = SESSOES[0], SESSOES[5]          # 2024-03-04 e 2024-03-11 (dias de montagem)


@pytest.fixture(scope="module")
def market():
    from cdp.data.synthetic import make_synthetic_market

    return make_synthetic_market(seed=DEMO_SEED, start=DEMO_HISTORY_START, as_of=SESSOES[-1])


@pytest.fixture(scope="module")
def base(tmp_path_factory, market):
    try:
        from cdp.cobertura.demo import gerar
    except ImportError as exc:  # pragma: no cover - motor da cobertura ausente
        pytest.skip(f"cobertura indisponível: {exc!r}")
    root = tmp_path_factory.mktemp("cdp_revisao")
    rt = _rt(root, market)
    gerar(rt, [D1, D2])
    return root


def _rt(root: Path, market, at: datetime | None = None, mind: str | None = "codex") -> Runtime:
    clock = at or datetime.combine(D2, datetime.min.time(), BRT).replace(hour=21)
    return Runtime(CFG, root / "book", root / "market", root / "reports",
                   store_override=DemoStore(market), clock=lambda: clock, teses_root=None,
                   expected_mind=mind)


def _copia(base: Path, tmp_path: Path) -> Path:
    dst = tmp_path / "copia"
    shutil.copytree(base / "book", dst / "book")
    return dst


def _gestao(fb, pac) -> dict:
    """Leitura da gestão válida: texto próprio, números só por fatos, evidências declaradas."""
    rev = json.loads(R.template_revisao(fb, pac, "codex").model_dump_json())
    rev["resumo"] = ("No período, a cobertura terminou com {{fact:rev.n_com_alvo_citavel}} "
                     "emissores com preço-alvo citável e confiança C em {{fact:rev.confianca.c.pct}} "
                     "dos modelos; a dispersão mediana entre métodos foi "
                     "{{fact:rev.metodos.cv_mediana}}. As maiores revisões vieram de estimativas e "
                     "de juros; nenhuma mudança de parâmetro é proposta sem conferência da fonte.")
    for m in rev["modelos_reavaliados"]:
        fid = f"rev.mov.{m['issuer_id']}.var_alvo"
        m["leitura"] = (f"Alvo revisto em {{{{fact:{fid}}}}}; a ponte mostra que a revisão veio "
                        "dos fundamentos, sem mudança de método.")
        m["conclusao"] = "manter"
        m["evidencias"] = [fid]
    rev["fontes"] = [{"id": "F1", "instituicao": "NYU Stern (Damodaran Online)",
                      "titulo": "Country Default Spreads and Risk Premiums",
                      "url": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html",
                      "publicado_em": "2024-01-05"}]
    rev["parametros_revisados"][0]["evidencias"] = ["F1"]
    return rev


# ----------------------------------------------------------------------------- calendário


def test_calendar_of_the_monthly_review():
    """A revisão é no último dia de montagem de cada mês (regra do mandato), nunca antes do
    início do mandato."""
    marco = rebalance_schedule(date(2024, 3, 1), date(2024, 3, 31), CFG)
    assert R.ultimo_rebalanceamento_do_mes(2024, 3, CFG) == marco[-1] == date(2024, 3, 25)
    assert R.e_ultimo_rebalanceamento_do_mes(date(2024, 3, 25), CFG)
    assert not R.e_ultimo_rebalanceamento_do_mes(D2, CFG)
    real = load_config()
    out = rebalance_schedule(date(2026, 10, 1), date(2026, 10, 31), real)
    assert R.ultimo_rebalanceamento_do_mes(2026, 10, real) == out[-1]
    prox = R.proxima_revisao(date(2026, 10, 6), real)
    assert prox == out[-1] and prox >= real.fund.inception_date and prox.weekday() <= 4


# ----------------------------------------------------------------------------- pacote


def test_package_facts_and_briefing(base, market, tmp_path):
    root = _copia(base, tmp_path)
    rt = _rt(root, market)
    assert R.situacao(rt.book_root, D2)["etapa"] == "preparar"
    res = R.preparar(rt, D2)
    pasta = R.pasta_revisao(rt.book_root, D2)
    assert set(res["arquivos"]) == {R.FATOS_MD, R.FACTBOOK_JSON, R.PACOTE_JSON, R.SCHEMA_JSON}
    assert not (pasta / R.REVISAO_JSON).exists() and res["publicada"] is False
    assert R.situacao(rt.book_root, D2)["etapa"] == "escrever"
    pac, fb = R._carregar_preparados(pasta)
    assert pac["retrato"]["data"] == D2.isoformat() and pac["retrato"]["sintetico"] is True
    assert fb.is_synthetic and fb.as_of == D2
    movs = pac["mudancas_alvo"]
    assert movs and len(movs) <= R.N_MUDANCAS
    assert [abs(m["var_alvo"]) for m in movs] == sorted((abs(m["var_alvo"]) for m in movs),
                                                       reverse=True)
    assert pac["reavaliacao_obrigatoria"] == [m["issuer_id"] for m in movs[:R.N_REAVALIACAO_OBRIGATORIA]]
    for m in movs:
        for c in R.COMPONENTES_PONTE:
            assert f"rev.mov.{m['issuer_id']}.ponte.{c}" in fb.facts
        assert fb.facts[f"rev.mov.{m['issuer_id']}.alvo_fim"].value == pytest.approx(m["alvo_fim"])
    ids = {it["id"] for it in pac["parametros"]}
    assert {"damodaran_crp", "damodaran_erp", "persistencia_painel", "arquetipos",
            "sotp_participacoes", "pesos_metodos", "etf_composicao",
            "versao_metodologia"} <= ids
    for it in pac["parametros"]:
        assert it["situacao_codigo"] in R.SITUACOES_CODIGO
    n = fb.facts["rev.n_emissores"].value
    assert n == sum(fb.facts[f"rev.rating.{r}.n"].value
                    for r in ("compra", "neutro", "venda", "em_revisao", "sem_alvo"))
    # placar sem vencidas: taxa ausente (nunca zero)
    assert fb.facts["rev.placar.acerto_vencimento"].value is None
    assert "n/d" in fb.facts["rev.placar.acerto_vencimento"].formatted
    md = (pasta / R.FATOS_MD).read_text(encoding="utf-8")
    assert "DADOS SIMULADOS" in md and "revisao.json" in md
    for i in ids:
        assert f"`{i}`" in md
    for iid in pac["reavaliacao_obrigatoria"]:
        assert f"`{iid}`" in md
    # idempotente
    antes = {p.name: p.read_bytes() for p in pasta.iterdir()}
    R.preparar(rt, D2)
    assert {p.name: p.read_bytes() for p in pasta.iterdir()} == antes


def test_example_is_valid_and_publication_by_the_research(base, market, tmp_path, capsys):
    from cdp.__main__ import main

    root = _copia(base, tmp_path)
    rt = _rt(root, market)
    R.preparar(rt, D2)
    pasta = R.pasta_revisao(rt.book_root, D2)
    pac, fb = R._carregar_preparados(pasta)
    assert R.verificar_revisao(R.template_revisao(fb, pac, "codex"), fb, pac, "codex") == []
    (pasta / R.REVISAO_JSON).write_text(json.dumps(_gestao(fb, pac), ensure_ascii=False),
                                        encoding="utf-8")
    assert R.situacao(rt.book_root, D2)["etapa"] == "validar_e_publicar"
    v = R.validar(rt, D2)
    assert v["ok"], v["problemas"]
    n_ev = len(rt.book.audit.events())
    res = R.publicar(rt, D2)
    assert res["autoria"] == "mente" and res["mind"] == "codex" and res["problemas"] == []
    evs = rt.book.audit.events()
    assert len(evs) == n_ev + 1 and evs[-1].event_type == R.AUDIT_EVENT
    assert R.verificar_revisoes(rt.book_root) == []
    assert R.situacao(rt.book_root, D2) == {"etapa": "publicada", "publicada": True}
    doc = R.carregar_revisao(rt.book_root)
    assert doc["data"] == D2 and R.listar_revisoes(rt.book_root) == [D2]
    md = doc["markdown"]
    assert "{{" not in md and "DADOS SIMULADOS" in md
    assert "Revisão mensal dos modelos da cobertura" in md and "Ajustes recomendados" in md
    for proibido in ("codex", "claude", "gemini", "chatgpt", "mente", "json", "hash"):
        assert not re.search(rf"\b{proibido}\b", md.lower()), proibido
    assert fb.facts["rev.n_com_alvo_citavel"].formatted in md
    pub = doc["publicada"]
    assert pub["hashes"]["revisao_json"] and pub["rendered"]["fontes"][0]["id"] == "F1"
    # imutável
    with pytest.raises(FileExistsError):
        R.publicar(rt, D2)
    assert R.preparar(rt, D2)["publicada"] is True
    # CLI: a mesma revisão já publicada é recusada (código 1, JSON com o erro)
    argv = ["--book", str(rt.book_root), "--market", str(root / "market"),
            "--reports", str(root / "reports"), "cobertura", "revisao-mensal", "publicar",
            "--date", D2.isoformat()]
    assert main(argv) == 1
    assert '"ok": false' in capsys.readouterr().out
    # adulteração do texto publicado é detectada
    (pasta / R.REVISAO_MD).write_text(md + "\nacréscimo\n", encoding="utf-8")
    assert R.verificar_revisoes(rt.book_root)


def test_validation_refuses_free_numbers_missing_items_and_bad_sources(base, market, tmp_path):
    root = _copia(base, tmp_path)
    rt = _rt(root, market)
    R.preparar(rt, D2)
    pasta = R.pasta_revisao(rt.book_root, D2)
    pac, fb = R._carregar_preparados(pasta)
    boa = _gestao(fb, pac)
    fora = pac["mudancas_alvo"][-1]["issuer_id"]

    def problemas(mudar) -> list[str]:
        rev = json.loads(json.dumps(boa))
        mudar(rev)
        (pasta / R.REVISAO_JSON).write_text(json.dumps(rev, ensure_ascii=False), encoding="utf-8")
        res = R.validar(rt, D2)
        assert res["ok"] is False
        return res["problemas"]

    def num(r):
        r["resumo"] += " A cobertura subiu 12,5% no mês."
    assert any("número fora de fato" in p for p in problemas(num))

    def extenso(r):
        r["resumo"] += " Foram treze por cento dos modelos."
    assert any("número fora de fato" in p for p in problemas(extenso))

    def inexistente(r):
        r["resumo"] += " Ver {{fact:rev.nao_existe}}."
    assert any("fato inexistente" in p for p in problemas(inexistente))

    def sem_evidencia(r):
        r["modelos_reavaliados"][0]["leitura"] += " Confiança C em {{fact:rev.confianca.c.pct}}."
    assert any("sem estar nas evidências" in p for p in problemas(sem_evidencia))

    def item_faltando(r):
        r["parametros_revisados"] = r["parametros_revisados"][1:]
    assert any("sem revisão" in p for p in problemas(item_faltando))

    def item_estranho(r):
        r["parametros_revisados"].append({"item": "inventado", "situacao": "em_dia",
                                          "comentario": "sem fonte", "evidencias": []})
    assert any("fora da lista" in p for p in problemas(item_estranho))

    def sem_obrigatorio(r):
        r["modelos_reavaliados"] = r["modelos_reavaliados"][1:]
    assert any("sem reavaliação" in p for p in problemas(sem_obrigatorio))

    def emissor_fora(r):
        r["modelos_reavaliados"].append({"issuer_id": "XX_INEXISTENTE", "leitura": "fora da cobertura",
                                         "conclusao": "manter", "evidencias": ["rev.n_emissores"]})
    assert any("fora da cobertura" in p for p in problemas(emissor_fora))

    def evidencia_ruim(r):
        r["ajustes_recomendados"].append({"titulo": "Ajuste", "descricao": "Conferir a fonte do item.",
                                          "prioridade": "baixa", "tipo": "processo",
                                          "referencia": None, "evidencias": ["F9"]})
    assert any("nem fonte declarada" in p for p in problemas(evidencia_ruim))

    def fonte_futura(r):
        r["fontes"][0]["publicado_em"] = (D2 + timedelta(days=3)).isoformat()
    assert any("look-ahead" in p for p in problemas(fonte_futura))

    def fonte_ip(r):
        r["fontes"][0]["url"] = "https://10.0.0.1/premio"
    assert any("endereço IP" in p for p in problemas(fonte_ip))

    def nome_de_app(r):
        r["resumo"] += " Texto revisado pelo ChatGPT."
    assert any("guia de estilo" in p for p in problemas(nome_de_app))

    def link(r):
        r["riscos_do_processo"][0]["descricao"] += " Veja https://exemplo.com/x."
    assert any("marcação/URL" in p for p in problemas(link))

    def data_errada(r):
        r["data"] = D1.isoformat()
    assert any("difere da revisão" in p for p in problemas(data_errada))

    def mente(r):
        r["mind"] = "gemini"
    assert any("mente desta execução" in p for p in problemas(mente))

    def conclusao(r):
        r["modelos_reavaliados"][0]["conclusao"] = "comprar"
    assert problemas(conclusao)
    assert fora  # há mudanças além das obrigatórias (só elas são exigidas)


def test_code_text_is_published_when_the_research_is_missing(base, market, tmp_path):
    root = _copia(base, tmp_path)
    rt = _rt(root, market)
    res = R.publicar(rt, D2)  # sem pacote nem revisao.json: recalcula e publica o automático
    assert res["autoria"] == "codigo" and res["mind"] is None
    assert any("texto automático" in p for p in res["problemas"])
    doc = R.carregar_revisao(rt.book_root, D2)
    assert "Versão automática" in doc["markdown"] and "{{" not in doc["markdown"]
    assert R.verificar_revisoes(rt.book_root) == []


@pytest.mark.parametrize("alteracao", ("texto", "json", "retrato_lista", "retrato_texto", "retrato_nulo", "ausente"))
def test_verify_cli_detects_monthly_review_tampering(base, market, tmp_path, capsys, monkeypatch,
                                                   alteracao):
    """A verificação geral e a CLI recusam revisão mensal com texto alterado após o selo."""
    from cdp.__main__ import main

    root = _copia(base, tmp_path)
    rt = _rt(root, market)
    R.publicar(rt, D2)
    ok, msgs = rt.verify_all()
    assert ok and "revisões mensais: íntegras" in msgs
    monkeypatch.setattr(Runtime, "from_args", lambda args: rt)
    assert main(["verify"]) == 0
    capsys.readouterr()
    pasta = R.pasta_revisao(rt.book_root, D2)
    if alteracao == "texto":
        md = pasta / R.REVISAO_MD
        md.write_text(md.read_text(encoding="utf-8") + "\nTexto alterado.\n", encoding="utf-8")
    elif alteracao == "json":
        (pasta / R.PUBLICADA_JSON).write_text("null", encoding="utf-8")
    elif alteracao.startswith("retrato_"):
        publicada = pasta / R.PUBLICADA_JSON
        doc = json.loads(publicada.read_text(encoding="utf-8"))
        doc["retrato"] = {"retrato_lista": ["corrompido"], "retrato_texto": "corrompido",
                          "retrato_nulo": None}[alteracao]
        publicada.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    else:
        (pasta / R.PUBLICADA_JSON).unlink()
    ok, msgs = rt.verify_all()
    assert not ok and any("revisões mensais:" in m for m in msgs)
    if alteracao.startswith("retrato_"):
        from cdp.cobertura.livro import LivroErro
        from cdp.workflow.painel_cobertura import carregar

        with pytest.raises(LivroErro, match="Revisão mensal em conferência"):
            carregar(rt.book_root)
    assert main(["verify"]) == 1
    assert "FALHA DE INTEGRIDADE" in capsys.readouterr().out


def test_portal_loads_sealed_monthly_review_without_authorship_identifiers(base, market, tmp_path):
    """O portal lê a revisão selada por data, exporta seu texto completo e recusa adulteração."""
    from cdp.workflow import painel_cobertura as PC
    from cdp.workflow.painel_publicacao import expandir

    root = _copia(base, tmp_path)
    rt = _rt(root, market)
    R.publicar(rt, D2)
    ent = PC.carregar(rt.book_root)
    arquivos = PC.exportar(ent)
    assert PC.conferir(arquivos) == []
    doc = expandir(json.loads(arquivos[PC.ARQUIVO]))
    itens = doc["monthly_reviews"]["itens"]
    assert len(itens) == 1 and itens[0]["data"] == D2.isoformat()
    revisao = expandir(json.loads(arquivos[itens[0]["file"]]))
    assert revisao["markdown"] == R.carregar_revisao(rt.book_root, D2)["markdown"]
    assert revisao["meta"]["data_notice"] == "DADOS SIMULADOS"
    assert not {"mind", "modelo_ia", "hashes", "autoria"} & set(revisao)
    anterior = expandir(json.loads(PC.exportar(PC.carregar(rt.book_root, ate=D1))[PC.ARQUIVO]))
    assert anterior["monthly_reviews"]["itens"] == []
    md = R.pasta_revisao(rt.book_root, D2) / R.REVISAO_MD
    md.write_text("Texto adulterado.", encoding="utf-8")
    from cdp.cobertura.livro import LivroErro

    with pytest.raises(LivroErro, match="Revisão mensal em conferência"):
        PC.carregar(rt.book_root)


def test_dates_without_look_ahead_and_forward_only(base, market, tmp_path):
    root = _copia(base, tmp_path)
    cedo = _rt(root, market, at=datetime(2024, 3, 8, 21, 0, tzinfo=BRT))
    with pytest.raises(R.RevisaoErro, match="posterior a hoje"):
        R.preparar(cedo, D2)
    rt = _rt(root, market)
    R.publicar(rt, D2)
    with pytest.raises(R.RevisaoErro, match="só anda para a frente"):
        R.preparar(rt, D1)
    vazio = _rt(tmp_path / "vazio", market)
    assert R.situacao(vazio.book_root, D2)["etapa"] == "sem_retrato"
    with pytest.raises(R.RevisaoErro, match="Sem retrato"):
        R.preparar(vazio, D2)


def test_cli_prepare_and_validate(base, market, tmp_path, capsys, monkeypatch):
    from cdp.__main__ import main

    root = _copia(base, tmp_path)
    monkeypatch.setenv("CDP_HARNESS", "codex")
    fixo = datetime.combine(D2, datetime.min.time(), BRT).replace(hour=21)
    monkeypatch.setattr(Runtime, "now", lambda self: fixo)
    argv = ["--config", str(LEGACY), "--book", str(root / "book"), "--market",
            str(root / "market"), "--reports", str(root / "reports"), "cobertura",
            "revisao-mensal"]
    assert main(argv + ["preparar", "--date", D2.isoformat()]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["publicada"] is False and out["itens_verificacao"]
    assert main(argv + ["validar", "--date", D2.isoformat()]) == 1  # revisao.json ausente
    assert "ausente" in capsys.readouterr().out
