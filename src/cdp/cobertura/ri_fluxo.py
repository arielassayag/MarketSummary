"""Bridge RI: configuração/corte confiados vêm do chamador, nunca do livro."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from ..data.ri_captura.adapter import autenticar
from ..data.ri_captura.configuracao import carregar_contexto_ri
from ..data.ri_captura.observado import instant, sha
from ..data.ri_captura.transporte import gravar_insumos_ri, reabrir_insumos_ri
from ..data.snapshot import load_snapshot
from ..data.store import MarketStore
from .ri_consumo import _corte, validar_conjunto
from .ri_observada import ativo

SCHEMA = "cdp.ri.fluxo_arquivado/v1"


@dataclass(frozen=True, slots=True)
class AutoridadeFluxoRI:
    """Referência externa explícita. Reabre os bytes/âncoras em cada operação."""
    configuracao: Path
    sha256_esperado: str

    def reabrir(self, md):
        contexto = carregar_contexto_ri(self.configuracao, sha256_esperado=self.sha256_esperado)
        return autenticar(contexto, md)


def exigir(params, autoridade, conhecimento_ate, md):
    if not ativo(params):
        if autoridade is not None or conhecimento_ate is not None:
            raise ValueError("RI fluxo: autoridade/corte exige opt-in explícito")
        return None
    if type(autoridade) is not AutoridadeFluxoRI:
        raise ValueError("RI fluxo: configuração externa e digest obrigatórios")
    if not isinstance(conhecimento_ate, datetime):
        raise ValueError("RI fluxo: corte datetime explícito obrigatório")
    instant(conhecimento_ate)
    from .temporal import ativo as temporal_ativo
    if params.versao != "2026-10.8" or not temporal_ativo(params):
        raise ValueError("RI fluxo: exige .8 e política temporal explícita")
    return autoridade.reabrir(md)


def carregar_mercado(raiz, as_of, modo=None):
    raiz = Path(raiz)
    as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    modo = modo or ("snapshot" if (raiz / "manifest.json").exists() else "store")
    if modo == "snapshot":
        return load_snapshot(raiz, verify=True), modo
    if modo == "store":
        return MarketStore(raiz).load(as_of, verify=True), modo
    raise ValueError("RI fluxo: formato de mercado desconhecido")


def conferir_mercado(md, raiz):
    if raiz is None:
        raise ValueError("RI fluxo: raiz externa dos bytes originais do mercado obrigatória")
    reaberto, modo = carregar_mercado(raiz, md.as_of)
    if reaberto.manifest.model_dump(mode="json") != md.manifest.model_dump(mode="json"):
        raise ValueError("RI fluxo: mercado recebido difere dos bytes originais verificados")
    for nome in ("close", "adj_close", "volume", "fx", "fundamentals", "short_interest",
                 "lending", "benchmarks", "rates"):
        if not getattr(reaberto, nome).equals(getattr(md, nome)):
            raise ValueError("RI fluxo: tabela de mercado recebida difere dos bytes originais")
    if (not reaberto.universe.lines.equals(md.universe.lines)
            or not reaberto.universe.issuers.equals(md.universe.issuers)
            or reaberto.universe.source_sha256 != md.universe.source_sha256
            or reaberto.news != md.news):
        raise ValueError("RI fluxo: universo/notícias recebidos divergem dos bytes originais")
    return modo


def _membro(raiz, nome):
    # Store usa base/D/arquivo e daily/D/arquivo; snapshot simples usa só nomes.
    rel = Path(nome)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("RI fluxo: membro de mercado fora da raiz explícita")
    root = Path(raiz).resolve()
    path = (root / rel).resolve()
    path.relative_to(root)
    return path


def arquivar(tmp, fornecedor, params, autoridade, conhecimento_ate, raiz_mercado):
    """Sela matéria-prima sem transcrever pacote nem importar autoridade para o livro."""
    md = fornecedor.md
    exigir(params, autoridade, conhecimento_ate, md)
    _corte(params, fornecedor, conhecimento_ate)
    modo = conferir_mercado(md, raiz_mercado)
    tmp = Path(tmp)
    destino = tmp / "ri" / "mercado"
    destino.mkdir(parents=True)
    arquivos = {}
    nomes = {f.path: f.sha256 for f in md.manifest.files}
    if modo == "snapshot":
        nomes["manifest.json"] = sha((Path(raiz_mercado) / "manifest.json").read_bytes())
    for nome, digest in sorted(nomes.items()):
        raw = _membro(raiz_mercado, nome).read_bytes()
        if sha(raw) != digest:
            raise ValueError("RI fluxo: bytes de mercado não conferem com manifesto")
        out = _membro(destino, nome)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        arquivos[str(out.relative_to(tmp))] = digest
    transporte = gravar_insumos_ri(tmp / "ri" / "insumos", raiz_saida=tmp,
                                   fornecedor=fornecedor, params=params, conhecimento_ate=conhecimento_ate)
    for file in (tmp / "ri" / "insumos").iterdir():
        arquivos[str(file.relative_to(tmp))] = sha(file.read_bytes())
    metadata = {"schema": SCHEMA, "configuracao_sha256": autoridade.sha256_esperado,
                "conhecimento_ate": instant(conhecimento_ate).isoformat(),
                "mercado_formato": modo, "mercado_content_hash": md.manifest.content_hash(),
                "insumos_manifest_sha256": transporte, "fornecedor_externo_obrigatorio": True,
                "publicacao_inferida": False, "pit_certificado": False}
    return metadata, arquivos


def reabrir(snap, params, *, autoridade, conhecimento_ate):
    """Corte externo esperado é reconferido; o carimbo no snapshot não o autoriza."""
    metadata = snap.manifest.get("ri_fluxo")
    if not isinstance(metadata, dict) or metadata.get("schema") != SCHEMA:
        raise ValueError("RI fluxo: arquivo operacional obrigatório")
    if not ativo(params):
        raise ValueError("RI fluxo: arquivo RI exige política explícita arquivada")
    md, _ = carregar_mercado(snap.pasta / "ri" / "mercado",
                            snap.manifest["prices_as_of"], metadata["mercado_formato"])
    contexto = exigir(params, autoridade, conhecimento_ate, md)
    if (metadata["configuracao_sha256"] != autoridade.sha256_esperado
            or metadata["conhecimento_ate"] != instant(conhecimento_ate).isoformat()
            or md.manifest.content_hash() != metadata["mercado_content_hash"]
            or md.manifest.content_hash() != snap.manifest["base_mercado"]["content_hash"]):
        raise ValueError("RI fluxo: configuração, corte ou mercado externo diverge do snapshot")
    fornecedor = reabrir_insumos_ri(snap.pasta / "ri" / "insumos",
        sha256_esperado=metadata["insumos_manifest_sha256"], md=md, contexto=contexto,
        params=params, conhecimento_ate=conhecimento_ate)
    if fornecedor.dados.corte_temporal != snap.manifest.get("corte_temporal"):
        raise ValueError("RI fluxo: corte tipado diverge do manifesto")
    return fornecedor


def recalcular(snap, params, *, autoridade, conhecimento_ate, cortes=None):
    """Percurso normal completo, desde DadosPublicos/MarketData; pacote não é autoridade."""
    import gzip
    import json

    import pandas as pd

    from .fontes import csv_canonico
    from .livro import ler_pacotes
    from .motor import arredondar, executar, modelo_json, resumo_linha
    fornecedor = reabrir(snap, params, autoridade=autoridade, conhecimento_ate=conhecimento_ate)
    anterior, provedores = preparar_anterior(snap.pasta.parent.parent, snap.as_of, params,
                                            autoridade=autoridade, cortes=cortes)
    from dataclasses import replace
    fornecedor = replace(fornecedor, anteriores=provedores)
    ex = executar(fornecedor.md, fornecedor.dados, params, snap.as_of,
                  emissores=snap.manifest["emissores"],
                  anterior=anterior,
                  ri_fornecedor=fornecedor, conhecimento_ate=conhecimento_ate)
    validar_conjunto(ex.pacotes, params, fornecedor=fornecedor, conhecimento_ate=conhecimento_ate)
    erros = []
    esperado = ler_pacotes(snap.pasta, snap.manifest)
    if arredondar(ex.pacotes) != esperado:
        erros.append(f"{snap.as_of}: pacotes reextraídos não conferem com o arquivo normalizado")
    if arredondar(ex.contexto) != snap._json("contexto.json"):
        erros.append(f"{snap.as_of}: contexto integral reextraído não confere")
    if arredondar(ex.rf) != snap.manifest["taxa_livre_risco"]:
        erros.append(f"{snap.as_of}: taxa livre de risco integral não confere")
    if arredondar(ex.insumos_etf) != json.loads(gzip.decompress(snap._bytes("insumos/etfs.json.gz"))):
        erros.append(f"{snap.as_of}: insumos ETF integrais não conferem")
    tabela = pd.DataFrame([resumo_linha(ex, iid) for iid in ex.emissores])
    if csv_canonico(tabela).encode("utf-8") != snap._bytes("modelos.csv"):
        erros.append(f"{snap.as_of}: tabela integral de modelos não confere")
    esperados_etf = {nome[5:-5] for nome in snap.manifest["arquivos"]
                     if nome.startswith("etfs/") and nome.endswith(".json")}
    if set(ex.etfs) != esperados_etf:
        erros.append(f"{snap.as_of}: conjunto de ETFs não confere")
    for iid in ex.emissores:
        if modelo_json(ex, iid, params, ri_fornecedor=fornecedor,
                       conhecimento_ate=conhecimento_ate) != snap.modelo(iid):
            erros.append(f"{snap.as_of}: {iid} seções integrais reextraídas não conferem")
    linhas_etf = []
    for ticker, etf in sorted(ex.etfs.items()):
        pub = snap.etf(ticker)
        if arredondar(etf) != {k: v for k, v in pub.items() if k not in ("is_synthetic", "aviso_dados")}:
            erros.append(f"{snap.as_of}: {ticker} ETF integral reextraído não confere")
        e = arredondar(etf)
        linhas_etf.append({c: e.get(c) for c in ("iid", "ticker", "moeda", "preco", "preco_alvo", "upside",
            "retorno_esperado", "r_bu", "r_td", "cobertura", "visao_ilf", "metodo", "tem_alvo")})
    if csv_canonico(pd.DataFrame(linhas_etf)).encode("utf-8") != snap._bytes("etfs.csv"):
        erros.append(f"{snap.as_of}: tabela integral de ETFs não confere")
    return erros


def autoridade_args(args):
    path, digest = getattr(args, "ri_config", None), getattr(args, "ri_config_sha256", None)
    if path is None and digest is None:
        return None
    if path is None or digest is None:
        raise ValueError("RI fluxo: --ri-config e --ri-config-sha256 são inseparáveis")
    return AutoridadeFluxoRI(Path(path), digest)


def cortes_args(args):
    out = {}
    for item in getattr(args, "ri_corte", None) or []:
        dia, value = item.split("=", 1)
        cut = instant(value)
        if dia in out:
            raise ValueError("RI fluxo: corte externo duplicado para a data")
        out[dia] = cut
    return out


def adicionar_argumentos(parser, *, executar=False):
    parser.add_argument("--ri-config", help="configuração de autoridade confiada FORA do livro")
    parser.add_argument("--ri-config-sha256", help="digest previamente confiado dessa configuração")
    parser.add_argument("--ri-corte", action="append", help="corte externo esperado DATA=ISO_COM_FUSO (repetível)")
    if executar:
        parser.add_argument("--ri-conhecimento-ate", help="instante atual explícito com fuso; separado dos preços/publicação")
        parser.add_argument("--valuation", help="parâmetros de valuation explícitos")
        parser.add_argument("--parametros-cobertura", help="pasta dos parâmetros de cobertura")



def preparar_anterior(book, as_of, params, *, autoridade, cortes):
    """Recorta endpoints anteriores por cortes externos; nenhuma autoridade vem do livro."""
    from .contexto import montar_contexto
    from .insumos import preparar, taxa_publica
    from .livro import carregar_anterior, datas_snapshots, ler_pacotes, snapshot
    from .motor import arredondar
    from .parametros import carregar_parametros
    from .resultado import ativo as resultado_ativo
    from .resultado import visao
    anterior = carregar_anterior(Path(book), as_of, excluir=as_of)
    providers = []
    for dia in datas_snapshots(Path(book)):
        if dia >= as_of:
            continue
        snap = snapshot(Path(book), dia)
        if snap.manifest.get("ri_fluxo") is None:
            continue
        cfg = snap.pasta / "configuracao"
        prev = carregar_parametros(cfg / "valuation.yaml", cfg / "cobertura")
        if prev.hash() != params.hash():
            raise ValueError("RI fluxo: endpoint anterior exige a mesma configuração econômica arquivada")
        cut = (cortes or {}).get(dia.isoformat())
        provider = reabrir(snap, prev, autoridade=autoridade, conhecimento_ate=cut)
        pacotes = preparar(provider.md, provider.dados, prev,
                           sorted(str(i) for i in provider.md.universe.issuers.index), dia)
        if resultado_ativo(prev):
            pacotes = {iid: visao(pac, prev) for iid, pac in pacotes.items()}
        rf, _, fonte = taxa_publica(provider.dados, provider.md, str(prev.cc["rf_usd_serie"]), dia)
        ctx = montar_contexto(pacotes, prev, rf, fonte,
                             ri_fornecedor=provider, conhecimento_ate=cut)
        if arredondar(ctx) != snap._json("contexto.json"):
            raise ValueError("RI fluxo: contexto anterior não corresponde à reextração")
        arquivados = ler_pacotes(snap.pasta, snap.manifest)
        autorizados = set((provider.dados.ri_contexto.document.issuer_id,))
        for iid in snap.manifest["emissores"]:
            if iid in autorizados and arredondar(pacotes[iid]) != arquivados[iid]:
                raise ValueError("RI fluxo: pacote anterior não corresponde à reextração")
            if iid in anterior.estado and anterior.estado[iid][0].get("as_of") == dia.isoformat():
                pacote = pacotes[iid] if iid in autorizados else anterior.estado[iid][0]
                anterior.estado[iid] = (pacote, ctx, rf)
        providers.append(provider)
    return anterior, tuple(providers)


def snapshot_exige_ri(snap):
    """Detecta obrigação; metadata jamais fornece a autoridade externa solicitada."""
    if snap.manifest.get("ri_fluxo") is not None:
        return True
    cfg = snap.pasta / "configuracao" / "valuation.yaml"
    if not cfg.exists():
        return False
    raw = cfg.read_text(encoding="utf-8")
    if "captura_observada_identidade" not in raw:
        return False
    import yaml
    val = yaml.safe_load(raw)
    return (val.get("qualidade") or {}).get("ri_disponibilidade_metodo") == "captura_observada_identidade"


def livro_exige_ri(book):
    """Só detecta opt-in; livro legado não ganha verificação adicional implícita."""
    from types import SimpleNamespace

    from .livro import datas_snapshots
    for dia in datas_snapshots(Path(book)):
        pasta = Path(book) / "cobertura" / dia.isoformat()
        import json
        manifest = json.loads((pasta / "manifest.json").read_text(encoding="utf-8"))
        if (pasta / "ri").exists() or snapshot_exige_ri(SimpleNamespace(manifest=manifest, pasta=pasta)):
            return True
    return False



def conferir_configuracao(params, arquivos_config):
    """RI exige bytes explícitos que representam exatamente os parâmetros em uso."""
    from .parametros import carregar_parametros
    if not ativo(params):
        return
    if not isinstance(arquivos_config, dict) or not arquivos_config:
        raise ValueError("RI fluxo: arquivos_config explícitos obrigatórios antes da escrita")
    if set(arquivos_config) != set(params.arquivos):
        raise ValueError("RI fluxo: mapa explícito incompleto ou incompatível com os parâmetros")
    for rel, esperado in params.arquivos.items():
        if rel.startswith("/") or ".." in Path(rel).parts:
            raise ValueError("RI fluxo: caminho de configuração inválido")
        arquivo = Path(arquivos_config[rel])
        if not arquivo.is_file() or sha(arquivo.read_bytes()) != esperado:
            raise ValueError(f"RI fluxo: configuração física ausente ou divergente: {rel}")
    val = Path(arquivos_config["valuation.yaml"])
    pasta = Path(arquivos_config["cobertura/arquetipos.csv"]).parent
    esperado = {"valuation.yaml": val}
    esperado.update({f"cobertura/{nome}": pasta / nome for nome in
                    ("arquetipos.csv", "betas_setor.csv", "unidades.csv", "sotp.yaml", "etfs.yaml")})
    if "resultado_evidencias.json" in params.arquivos:
        esperado["resultado_evidencias.json"] = val.parent / "resultado_evidencias.json"
    if any(Path(arquivos_config[k]).resolve() != v.resolve() for k, v in esperado.items()):
        raise ValueError("RI fluxo: arquivos_config não representa a raiz física recarregável")
    fisicos = carregar_parametros(val, pasta)
    if not ativo(fisicos) or fisicos != params:
        raise ValueError("RI fluxo: política explícita/configuração física difere dos parâmetros")


def conferir_livro_antes_de_escrita(book, params, *, autoridade, cortes, agora):
    """Leitura pura: autentica o histórico e somente a cauda canônica recuperável.

    A detecção independe da política da chamada. O conteúdo arquivado nunca fornece
    autoridade/corte. Uma falta na trilha ou no livro só pode ser a última cauda,
    preservada em eventos.jsonl e no selo; nenhuma escrita ocorre nesta validação.
    """
    import json

    from ..audit import GENESIS_HASH, AuditEvent, _event_hash
    from ..hashing import sha256_file, sha256_obj
    from .livro import GENESIS, LivroErro, conferir_corte, datas_snapshots, eventos, snapshot
    from .motor import arredondar
    from .parametros import carregar_parametros
    from .placar import calcular_placar

    book = Path(book)
    if not livro_exige_ri(book):
        return
    if params is None or not ativo(params):
        raise ValueError("RI fluxo: histórico RI exige opt-in explícito antes de reparar/gravar")
    if type(autoridade) is not AutoridadeFluxoRI:
        raise ValueError("RI fluxo: histórico exige configuração externa e digest antes da escrita")
    if not isinstance(cortes, dict):
        raise ValueError("RI fluxo: cortes externos do histórico obrigatórios antes da escrita")
    limite = instant(agora) if isinstance(agora, datetime) else None
    if limite is None:
        raise ValueError("RI fluxo: instante atual explícito obrigatório antes da escrita")
    dias = datas_snapshots(book)
    completos, selos = [], []
    prefixo_ultimo = 0
    head = GENESIS
    for dia in dias:
        snap = snapshot(book, dia)
        for rel, digest in snap.manifest.get("arquivos", {}).items():
            arquivo = snap.pasta / rel
            if not arquivo.is_file() or sha256_file(arquivo) != digest:
                raise LivroErro(f"RI fluxo: histórico ausente/adulterado: {dia}/{rel}")
        if snapshot_exige_ri(snap):
            cfg = snap.pasta / "configuracao"
            anteriores = carregar_parametros(cfg / "valuation.yaml", cfg / "cobertura")
            if anteriores.hash() != params.hash():
                raise ValueError("RI fluxo: histórico exige a mesma configuração econômica antes da escrita")
            corte = cortes.get(dia.isoformat())
            if not isinstance(corte, datetime) or instant(corte) > limite:
                raise ValueError(f"RI fluxo: corte externo ausente/futuro para {dia}")
            reabrir(snap, anteriores, autoridade=autoridade, conhecimento_ate=corte)
        if snap.manifest.get("corte_temporal") is not None:
            conferir_corte(snap, limite)
            contrato = snap.manifest["corte_temporal"]
            from .livro import ler_pacotes
            pacotes = ler_pacotes(snap.pasta, snap.manifest)
            if any(p.get("corte_temporal") != contrato or p.get("as_of") != dia.isoformat()
                   for p in pacotes.values()):
                raise LivroErro("RI fluxo: corte temporal histórico dos pacotes diverge")
            if any((snap.modelo(iid) or {}).get("corte_temporal") != contrato
                   for iid in snap.manifest.get("emissores", [])):
                raise LivroErro("RI fluxo: corte temporal histórico dos modelos diverge")
        ant = snap.manifest.get("livro_anterior") or {}
        if ant.get("n_eventos") != len(completos) or ant.get("head") != head:
            raise LivroErro("RI fluxo: histórico não continua o selo anterior")
        prefixo_ultimo = len(completos)
        bruto = snap._bytes("eventos.jsonl")
        if bruto is None:
            raise LivroErro("RI fluxo: eventos históricos selados ausentes")
        cauda = [json.loads(linha) for linha in bruto.decode().splitlines() if linha.strip()]
        for ev in cauda:
            esperado = sha256_obj({k: v for k, v in ev.items() if k != "event_hash"})
            if (ev.get("seq") != len(completos) or ev.get("prev_hash") != head
                    or ev.get("event_hash") != esperado or ev.get("as_of") != dia.isoformat()):
                raise LivroErro("RI fluxo: encadeamento histórico selado inválido")
            completos.append(ev)
            head = esperado
        selo = json.loads((snap.pasta / "selo.json").read_text())
        if selo.get("n_eventos") != len(completos) or selo.get("livro_head") != head:
            raise LivroErro("RI fluxo: selo histórico não corresponde aos eventos")
        if sha256_obj(arredondar(calcular_placar(completos, None, dia))) != sha256_obj(snap.placar()):
            raise LivroErro("RI fluxo: placar histórico não corresponde aos eventos")
        selos.append(sha256_obj(selo))
    feitos = eventos(book)
    if feitos != completos[:len(feitos)] or len(feitos) not in (len(completos), prefixo_ultimo):
        raise LivroErro("RI fluxo: livro não é completo nem a cauda canônica recuperável")
    arquivo_trilha = book / "audit_log.jsonl"
    trilha = ([AuditEvent.model_validate_json(linha) for linha in arquivo_trilha.read_text().splitlines()
               if linha.strip()] if arquivo_trilha.is_file() else [])
    head_trilha = GENESIS_HASH
    for i, ev in enumerate(trilha):
        digest = _event_hash(ev.seq, ev.ts, ev.event_type, ev.actor, ev.week,
                             ev.payload_hash, ev.summary, ev.prev_hash)
        if ev.seq != i or ev.prev_hash != head_trilha or ev.event_hash != digest:
            raise LivroErro("RI fluxo: trilha histórica inválida")
        head_trilha = digest
    registrados = [e.payload_hash for e in trilha if e.event_type == "COVERAGE_SNAPSHOT"]
    if registrados not in (selos, selos[:-1]):
        raise LivroErro("RI fluxo: trilha não é completa nem falta somente o último selo")
