"""Portal público (GitHub Pages): ``cdp site construir|conferir`` e os workflows do Actions.

Monta o site a partir de livros temporários (demonstração offline e livro vazio), nunca do livro
do repositório: documentos completos (SEO, CSP, dados estruturados), dados abertos com SHA-256,
manifesto e somas, avisos de dados simulados, guardas, determinismo e conferência."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import warnings
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from cdp import site as st
from cdp.config import load_config
from cdp.workflow.runtime import Runtime

ROOT = Path(__file__).resolve().parents[2]
BRT = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 10, 9, 20, 0, tzinfo=BRT)
COMMIT = "a" * 40
SHA_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def demo(tmp_path_factory) -> Path:
    from cdp.workflow.demo import run_demo

    out = tmp_path_factory.mktemp("site_demo")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        run_demo(out, days=2)
    return out


def _cfg_desde(inicio: date):
    cfg = load_config()
    return cfg.model_copy(update={"fund": cfg.fund.model_copy(update={"inception_date": inicio})})


def _rt(raiz: Path, cfg=None) -> Runtime:
    return Runtime(cfg or load_config(), raiz / "book", raiz / "market", raiz / "reports")


def _build(rt, saida: Path, **kw) -> dict:
    op = st.Opcoes(saida=saida, raiz=ROOT, base_url="https://exemplo.test/cdp", agora=AGORA,
                   commit=COMMIT, **kw)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return st.construir(rt, op)


@pytest.fixture(scope="module")
def site_sintetico(demo, tmp_path_factory) -> Path:
    """Livro da demonstração tratado como livro real (data de início na primeira semana dele)."""
    saida = tmp_path_factory.mktemp("s1") / "_site"
    _build(_rt(demo, _cfg_desde(date(2024, 3, 4))), saida)
    return saida


def _arvore(pasta: Path) -> dict[str, str]:
    return {p.relative_to(pasta).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(pasta.rglob("*")) if p.is_file()}


def test_built_site_passes_the_checks(site_sintetico):
    assert st.conferir(site_sintetico) == []
    for rel in ("index.html", "data.json", "404.html", "robots.txt", "sitemap.xml",
                "manifest.json", "SHA256SUMS", "favicon.svg", "og.png", "apple-touch-icon.png",
                "site.css", "dados/index.html", "dados/datapackage.json",
                "marca/marca_tinta.webp"):
        assert (site_sintetico / rel).is_file(), rel
    assert len(list(site_sintetico.glob("painel-*.css"))) == 1
    assert len(list(site_sintetico.glob("painel-*.js"))) == 1


def test_index_is_a_complete_document(site_sintetico):
    idx = (site_sintetico / "index.html").read_text(encoding="utf-8")
    assert idx.startswith("<!doctype html>\n<html lang=\"pt-BR\">")
    assert '<link rel="canonical" href="https://exemplo.test/cdp/">' in idx
    assert 'property="og:image" content="https://exemplo.test/cdp/og.png"' in idx
    assert "Content-Security-Policy" in idx and "upgrade-insecure-requests" in idx
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', idx,
                              re.S).group(1))
    tipos = {g["@type"] for g in ld["@graph"]}
    assert tipos == {"WebSite", "Dataset"}
    assert "FinancialProduct" not in idx and "InvestmentFund" not in idx
    assert 'id="cdp-data">null</script>' in idx  # a página busca data.json ao lado
    assert "Transparência e auditoria" in idx and 'href="dados/"' in idx
    assert idx.index('class="site-auditoria"') < idx.index('<footer class="foot" id="foot">')
    assert f"/tree/{COMMIT}" in idx


def test_simulated_book_is_marked_and_kept_out_of_search(site_sintetico):
    man = json.loads((site_sintetico / "manifest.json").read_text(encoding="utf-8"))
    assert man["dados_simulados"] is True and man["indexado"] is False
    for rel in ("index.html", "404.html", "dados/index.html"):
        txt = (site_sintetico / rel).read_text(encoding="utf-8")
        assert "DADOS SIMULADOS" in txt and "noindex" in txt, rel
    assert "Disallow: /" in (site_sintetico / "robots.txt").read_text()
    pkg = json.loads((site_sintetico / "dados/datapackage.json").read_text(encoding="utf-8"))
    assert pkg["title"].startswith("DADOS SIMULADOS") and "DADOS SIMULADOS" in pkg["keywords"]
    csv = next(site_sintetico.glob("dados/**/positions_v*.csv"))
    assert "DADOS SIMULADOS" not in csv.read_text(encoding="utf-8").splitlines()[0]


def test_manifest_sums_and_datapackage_bind_every_byte(site_sintetico):
    man = json.loads((site_sintetico / "manifest.json").read_text(encoding="utf-8"))
    assert man["source_commit"] == COMMIT and man["agora"] == AGORA.isoformat()
    arquivos = man["arquivos"]
    assert set(arquivos) == set(_arvore(site_sintetico)) - {"manifest.json", "SHA256SUMS"}
    somas = (site_sintetico / "SHA256SUMS").read_text().splitlines()
    assert any(s.endswith("  manifest.json") for s in somas)
    pkg = json.loads((site_sintetico / "dados/datapackage.json").read_text(encoding="utf-8"))
    assert pkg["$schema"].endswith("/datapackage.json") and pkg["resources"]
    nomes = [r["name"] for r in pkg["resources"]]
    assert len(nomes) == len(set(nomes))
    for r in pkg["resources"]:
        assert re.fullmatch(r"[a-z0-9._-]+", r["name"]) and ".." not in r["path"]
        assert r["hash"] == "sha256:" + arquivos[f"dados/{r['path']}"]["sha256"]
        if r["format"] == "csv":
            assert r["schema"]["fields"]
    grupos = {r["grupo"] for r in pkg["resources"]}
    assert {"carteira", "livro", "registro", "relatorios", "configuracao", "auditoria"} <= grupos


def test_open_data_are_exact_copies_without_shadow_results(demo, site_sintetico):
    pos = sorted((demo / "book").glob("*/positions_v*.csv"))[-1]
    copia = site_sintetico / "dados/livro" / pos.relative_to(demo / "book")
    assert copia.read_bytes() == pos.read_bytes()
    tudo = list(_arvore(site_sintetico))
    assert not any("shadow" in p or "sombra" in p for p in tudo)
    assert not any(p.endswith("attempts.json") for p in tudo)
    assert any(p.startswith("dados/carteira_atual/positions_v") for p in tudo)
    data = json.loads((site_sintetico / "data.json").read_text(encoding="utf-8"))
    assert data["meta"]["publication"]["nivel"] == 0
    assert data["meta"]["publication"]["reports_dir"] == "dados/relatorios"


def test_page_data_is_uncut():
    lim = st.limites_site()
    assert lim.posicoes_sombra == 0
    assert lim.pregoes >= st.GRANDE and lim.comentarios >= st.GRANDE
    assert lim.semanas_completas >= st.GRANDE and lim.notas_completas is True


def test_build_is_deterministic_and_read_only(demo, tmp_path):
    rt = _rt(demo, _cfg_desde(date(2024, 3, 4)))
    antes = _arvore(demo)
    _build(rt, tmp_path / "a")
    _build(rt, tmp_path / "b")
    assert _arvore(tmp_path / "a") == _arvore(tmp_path / "b")
    assert _arvore(demo) == antes  # nunca grava fora de --saida


def test_real_build_has_no_simulated_band_and_carries_the_legal_notice(tmp_path):
    saida = tmp_path / "_site"
    out = _build(_rt(tmp_path), saida)
    assert out["dados_simulados"] is False and out["indexado"] is True
    assert st.conferir(saida) == []
    idx = (saida / "index.html").read_text(encoding="utf-8")
    assert 'class="site-sim"' not in idx and "site-aviso" in idx
    assert st.carregar_site(ROOT)["aviso_legal"] in idx
    assert "Allow: /" in (saida / "robots.txt").read_text()
    assert "Ainda não há arquivos do fundo" in (saida / "dados/index.html").read_text(
        encoding="utf-8")


def test_demo_option_builds_from_the_offline_demonstration(demo, tmp_path, monkeypatch):
    import cdp.workflow.demo as dm

    def copia(out, days=6, **kw):
        shutil.copytree(demo, out, dirs_exist_ok=True)

    monkeypatch.setattr(dm, "run_demo", copia)
    out = _build(_rt(tmp_path), tmp_path / "_demo", demo=True)
    assert out["dados_simulados"] and not out["indexado"]
    man = json.loads((tmp_path / "_demo/manifest.json").read_text(encoding="utf-8"))
    assert man["perfil"] == "demo"
    assert st.conferir(tmp_path / "_demo") == []
    idx = (tmp_path / "_demo/index.html").read_text(encoding="utf-8")
    assert "<title>DADOS SIMULADOS — " in idx and 'class="site-sim"' in idx


def test_guards_pending_book_and_broken_integrity(demo, tmp_path, monkeypatch):
    with pytest.raises(st.ErroSite) as exc:  # livro com chaves anteriores à data de início
        _build(_rt(demo), tmp_path / "x")
    assert exc.value.codigo == st.AGUARDANDO_ABERTURA
    rt = _rt(tmp_path)
    monkeypatch.setattr(rt, "verify_all", lambda: (False, ["livro: cadeia quebrada"]))
    with pytest.raises(st.ErroSite) as exc:
        _build(rt, tmp_path / "y")
    assert exc.value.codigo == 1 and "verify" in str(exc.value)
    assert not (tmp_path / "y").exists()


def test_output_folder_protections(tmp_path):
    for ruim in (ROOT, ROOT / "book", ROOT / "reports" / "x"):
        with pytest.raises(st.ErroSite):
            st._preparar_saida(ruim, ROOT)
    outra = tmp_path / "outra"
    outra.mkdir()
    (outra / "importante.txt").write_text("x")
    with pytest.raises(st.ErroSite):
        st._preparar_saida(outra, ROOT)
    assert (outra / "importante.txt").exists()


def test_conferir_catches_tampering(site_sintetico, tmp_path, monkeypatch):
    s = tmp_path / "s"
    shutil.copytree(site_sintetico, s)
    (s / ".env").write_text("TOKEN=x")
    (s / "site.css").unlink()
    alvo = next(s.glob("dados/**/*.csv"))
    alvo.write_text(alvo.read_text() + "\n")
    probs = "\n".join(st.conferir(s))
    assert "nome proibido" in probs and "fora do manifesto: .env" in probs
    assert "arquivo obrigatório ausente: site.css" in probs
    (s / "site.css").write_text("x")
    probs = "\n".join(st.conferir(s))
    assert f"difere do manifesto: {alvo.relative_to(s).as_posix()}" in probs
    monkeypatch.setattr(st, "MAX_ARQUIVO", 10)
    assert "acima de 25 MiB" in "\n".join(st.conferir(site_sintetico))


def test_collect_filters_shadow_attempts_and_pre_inception(tmp_path):
    b = tmp_path / "book"
    for rel in ("2026-10-02/positions_v1.csv", "2026-10-09/positions_v1.csv",
                "2026-10-09/decision_v1.json", "2026-10-09/attempts.json",
                "2026-10-09/shadow_quant.json", "track_record_shadow/track_record.csv",
                "track_record/records/2026-10-09.json", "cobertura/2026-10-08/modelos.csv",
                "audit_log.jsonl"):
        (b / rel).parent.mkdir(parents=True, exist_ok=True)
        (b / rel).write_text("x")
    r = tmp_path / "reports"
    for k in range(25):
        d = f"2026-11-{k + 1:02d}"
        (r / "risk" / d).mkdir(parents=True)
        (r / "risk" / d / "risco_1330.md").write_text("x")
    (r / "daily/2026-10-05").mkdir(parents=True)
    (r / "daily/2026-10-05/relatorio.md").write_text("x")
    # backtests: só a metodologia em vigor (nota de calendário da regra atual de fund.yaml)
    from cdp.backtest.engine import rebalance_rule

    rt = _rt(tmp_path)
    regra = rebalance_rule(rt.cfg)[0]
    outra = next(r_ for r_ in st.MARCA_CALENDARIO if r_ != regra)
    for pasta, marca in (("2026-10-05", st.MARCA_CALENDARIO[outra]),
                         ("2026-10-09", st.MARCA_CALENDARIO[regra]), ("2026-10-10", None)):
        (r / "backtest" / pasta / "v1").mkdir(parents=True)
        (r / "backtest" / pasta / "CALIBRACAO.md").write_text("x")
        notas = [marca + " (…)"] if marca else ["sem calendário"]
        (r / "backtest" / pasta / "v1/metrics.json").write_text(json.dumps({"notes": notas}))
    assert st.backtests_vigentes(rt) == (["2026-10-09"], ["2026-10-05", "2026-10-10"])
    pares = st.coletar_dados(rt, ROOT, risco_ultimas=20)
    destinos = {a.destino for _, a in pares}
    assert "dados/livro/2026-10-09/positions_v1.csv" in destinos
    assert "dados/livro/2026-10-02/positions_v1.csv" not in destinos  # antes do início
    assert "dados/livro/cobertura/2026-10-08/modelos.csv" in destinos  # gênese da cobertura
    assert not any("attempts" in d or "shadow" in d for d in destinos)
    assert "dados/carteira_atual/positions_v1.csv" in destinos
    assert "dados/relatorios/daily/2026-10-05/relatorio.md" not in destinos
    assert "dados/relatorios/backtest/2026-10-09/CALIBRACAO.md" in destinos  # metodologia
    assert "dados/relatorios/backtest/2026-10-09/v1/metrics.json" in destinos
    assert not any("backtest/2026-10-05" in d or "backtest/2026-10-10" in d for d in destinos)
    assert len([d for d in destinos if "/risk/" in d]) == 20
    assert "dados/configuracao/fund.yaml" in destinos
    descr = {a.destino: a.descricao for _, a in pares}
    assert descr["dados/livro/audit_log.jsonl"].startswith("Trilha de auditoria")


# ------------------------------------------------------------------------------ workflows


def _wf(nome: str) -> dict:
    wf = yaml.safe_load((ROOT / ".github/workflows" / nome).read_text(encoding="utf-8"))
    wf["on"] = wf.pop(True, wf.get("on"))
    return wf


def _steps(wf: dict):
    for job in wf["jobs"].values():
        yield from job.get("steps", [])


@pytest.mark.parametrize("nome", ["cdp-site.yml", "cdp-ci.yml"])
def test_workflows_are_least_privilege_and_pinned(nome: str):
    wf = _wf(nome)
    assert wf["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in wf["on"]
    for s in _steps(wf):
        if "uses" in s:
            assert SHA_RE.match(s["uses"]), s["uses"]
        if "run" in s:
            assert "${{" not in s["run"], s.get("name")
    for nome_job, job in wf["jobs"].items():
        perms = job.get("permissions", {})
        if nome_job != "publicar":
            assert "pages" not in perms and "id-token" not in perms
    checkouts = [s for s in _steps(wf) if s.get("uses", "").startswith("actions/checkout@")]
    assert checkouts and all(s["with"]["persist-credentials"] is False for s in checkouts)


def test_site_workflow_contract():
    wf = _wf("cdp-site.yml")
    caminhos = wf["on"]["push"]["paths"]
    # o mesmo conjunto que `cdp estado --rede` usa para PORTAL_DEFASADO
    esperado = {c if "." in c.rsplit("/", 1)[-1] else c + "/**" for c in st.CAMINHOS_DO_PORTAL}
    assert set(caminhos) == esperado
    assert "docs/cdp/marca/**" in caminhos
    assert wf["on"]["push"]["branches"] == ["main"]
    assert wf["concurrency"] == {"group": "pages", "cancel-in-progress": False}
    pub = wf["jobs"]["publicar"]
    assert pub["permissions"] == {"pages": "write", "id-token": "write"}
    assert pub["environment"]["name"] == "github-pages"
    assert pub["if"] == "needs.construir.outputs.publicar == 'true'"
    montar = next(s for s in _steps(wf) if s.get("id") == "montar")["run"]
    assert "site construir" in montar and "site conferir" in montar and '"$rc" -eq 3' in montar
    # a demonstração nunca vai ao endereço público (só artefato de prévia)
    demo = re.search(r'if \[ "\$DEMO" = "true" \]; then\n\s*# A demonstração.*?else', montar,
                     re.S)
    assert demo and "publicar=false" in demo.group(0) and "publicar=true" not in demo.group(0)
    assert "manifest.json" in json.dumps(wf["jobs"]["conferir-no-ar"])


def test_ci_workflow_contract():
    wf = _wf("cdp-ci.yml")
    runs = "\n".join(s.get("run", "") for s in _steps(wf))
    for cmd in ("ruff check .", "pytest", "cdp verify", "cdp rotinas verificar",
                "cdp skills verificar", "cdp site construir --demo", "cdp site conferir"):
        assert cmd in runs, cmd
    assert wf["concurrency"]["cancel-in-progress"] is True
    assert "secrets." not in (ROOT / ".github/workflows/cdp-ci.yml").read_text()


def test_open_data_page_speaks_to_investors(site_sintetico):
    pagina = (site_sintetico / "dados/index.html").read_text(encoding="utf-8")
    visivel = re.sub(r"<[^>]+>", " ", pagina.split("<body>", 1)[1])
    for jargao in ("Frictionless", "sha256sum", "git clone", "git checkout", "uv run",
                   "uv sync", "ÍNTEGRO"):
        assert jargao not in visivel, jargao
    assert re.search(r"Registro íntegro — \d+ eventos? conferidos?", visivel)
    for rotulo in ("catálogo dos arquivos", "manifesto da publicação", "somas de verificação"):
        assert rotulo in visivel
    assert st.texto_integridade({"resultado": "ÍNTEGRO"}, 1) == \
        "Registro íntegro — 1 evento conferido"
    assert "não verificada" in st.texto_integridade({}, None)


def test_page_data_lifts_audit_and_risk_caps_and_drops_superseded_backtests(tmp_path,
                                                                            monkeypatch):
    from cdp.backtest.engine import rebalance_rule
    from cdp.workflow import painel

    rt = _rt(tmp_path)
    regra = rebalance_rule(rt.cfg)[0]
    outra = next(r_ for r_ in st.MARCA_CALENDARIO if r_ != regra)
    for pasta, marca in (("2026-10-05", outra), ("2026-11-02", regra)):
        m = tmp_path / "reports/backtest" / pasta / "v1/metrics.json"
        m.parent.mkdir(parents=True)
        m.write_text(json.dumps({"notes": [st.MARCA_CALENDARIO[marca]]}))
    visto: dict = {}

    class Pare(Exception):
        pass

    def falso(rt_, **kw):
        visto.update(kw)
        visto["pastas"] = sorted(p.name for p in Path(kw["backtest_root"]).iterdir())
        raise Pare

    monkeypatch.setattr(painel, "painel_data", falso)
    with pytest.raises(Pare):
        st.dados_do_painel(rt, AGORA)
    assert visto["audit_tail"] >= st.GRANDE and visto["max_risk_full_runs"] >= st.GRANDE
    assert visto["max_risk_runs"] >= st.GRANDE and visto["pastas"] == ["2026-11-02"]
