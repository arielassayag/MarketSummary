"""Nove consultas operacionais nativas sobre um contexto físico explícito de leitura.

Não prepara arquivos, não executa gates e não concede autoridade operacional. Os resultados
são os retornos integrais dos delegates existentes, conservando negativos e ausências.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path, PosixPath

from ..leitura_arquivos import ReceptorArquivos, ativar_receptor, ler_texto, receber_fd
from .leitura_contratos import (
    ContextoLeituraInvalido,
    EntradaJSON,
    FalhaLeitura,
    FerramentaLeitura,
    FonteLeituraIndisponivel,
    IngressoLeituraInvalido,
    RespostaConsulta,
    TentativaDeEfeitoLeitura,
    schema_ingresso,
)
from .leitura_serializacao import (
    _json_exato,
    hash_resultado,
    serializar_valor,
    validar_schema_exato,
)

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_RAIZES = {"repositorio", "livro", "mercado", "relatorios", "publico", "rascunhos"}
_PARAMETROS = (
    "valuation.yaml",
    "cobertura/arquetipos.csv",
    "cobertura/betas_setor.csv",
    "cobertura/unidades.csv",
    "cobertura/sotp.yaml",
    "cobertura/etfs.yaml",
)
_REGISTRADOS: dict[int, _SeloRegistro] = {}


def _instante(raw: str) -> datetime:
    if type(raw) is not str or not raw.endswith(("Z", "+00:00")):
        raise ValueError("Instante deve ser UTC explícito")
    out = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if out.tzinfo is None or out.utcoffset() != timedelta(0):
        raise ValueError("Instante deve ser UTC explícito")
    return out


def _civil(raw: str) -> date:
    if type(raw) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) is None:
        raise ValueError("Data civil deve ser ISO exata")
    return date.fromisoformat(raw)


def _json_unico(body: bytes):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("Chave JSON duplicada")
            result[k] = v
        return result

    def nonfinite(value):
        raise ValueError("Número JSON não finito")

    return json.loads(body.decode("utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)


def _seletores_declarados(manifest, tool, a):
    for key in ("agora", "gerado_em"):
        if key in a and _instante(a[key]) != _instante(manifest["agora"]):
            raise IngressoLeituraInvalido("Relógio difere do contexto")
    if "offset_pc_minutos" in a and a["offset_pc_minutos"] != manifest["offset_pc_minutos"]:
        raise IngressoLeituraInvalido("Observação do PC difere do contexto")
    if "conhecimento_ate" in a and _instante(a["conhecimento_ate"]) != _instante(
        manifest["conhecimento_ate"]
    ):
        raise IngressoLeituraInvalido("Corte difere do contexto")
    for key in ("data", "sessao", "semana"):
        if key in a and _civil(a[key]) > _civil(manifest["as_of"]):
            raise IngressoLeituraInvalido("Data posterior ao corte recebido")
    if tool == FerramentaLeitura.VALIDAR.value:
        if a["mente_esperada"] != manifest["mente_esperada"]:
            raise IngressoLeituraInvalido("Autoria esperada difere do contexto")
        if a["documento_sha256"] not in manifest["documentos"]:
            raise IngressoLeituraInvalido("Documento não recebido")


@dataclass(frozen=True, slots=True)
class _SeloRegistro:
    contexto: object
    sha256: str
    corpo: bytes
    path: Path
    m6: tuple
    config_hash: str
    recebido_em: str


@dataclass(frozen=True, slots=True)
class ContextoLeituraRecebido:
    """Só uma instância devolvida/registrada pelo receptor nominal pode ingressar no leitor."""

    sha256: str
    corpo: bytes
    path: Path
    m6: tuple
    raizes: tuple[tuple[str, Path], ...]
    membros: tuple[tuple[str, tuple[str, str, str]], ...]
    declaracoes: dict
    cfg: object
    config_hash: str
    parametros: object
    universo: object
    nomes: dict
    rotinas: object
    eventos_macro: dict
    runtime: object
    recebido_em: str
    _receptor_entrada: ReceptorArquivos

    def receptor(self):
        seal = _REGISTRADOS.get(id(self))
        if seal is None or seal.contexto is not self:
            raise ContextoLeituraInvalido("Contexto não recebido pela folha")
        return self._receptor_entrada


def receber_contexto_leitura(path: str | Path) -> ContextoLeituraRecebido:
    """Recebe o contexto nominal público; nenhum parâmetro concede autoridade."""
    return _receber_contexto_nativo(path)


def _receber_contexto_nativo(
    path: str | Path, selo: _SeloRegistro | None = None
) -> ContextoLeituraRecebido:
    """Recebe manifesto e parsers nativos; não procura CWD/default ou recurso de pacote."""
    from ..cobertura.parametros import _parametros_de_textos
    from ..config import load_config
    from ..rotinas import carregar
    from ..universe import load_universe, nomes_do_corpo
    from .agenda import carregar_eventos_macro
    from .runtime import Runtime

    try:
        if type(path) not in (str, PosixPath):
            raise ValueError("Path do host não é str/Path nativo exato")
        p = Path(path)
        body, m6 = receber_fd(p, limite=1048576)
        if selo is not None and (body != selo.corpo or m6 != selo.m6 or p != selo.path):
            error = ContextoLeituraInvalido("Manifesto difere do selo original antes dos parsers")
            error.codigo, error.readset = "LEITURA_INSTAVEL", ()
            raise error
        manifest = _json_unico(body)
        _json_exato(manifest)
        fields = {
            "schema",
            "somente_leitura",
            "raizes",
            "membros",
            "entradas",
            "parametros",
            "documentos",
            "ambiente_identidade",
            "mente_esperada",
            "as_of",
            "conhecimento_ate",
            "agora",
            "offset_pc_minutos",
        }
        if type(manifest) is not dict or set(manifest) != fields:
            raise ValueError("Campos do manifesto divergentes")
        if (
            manifest["schema"] != "cdp.contexto_leitura/v1"
            or manifest["somente_leitura"] is not True
        ):
            raise ValueError("Manifesto exige schema literal e leitura True")
        roots = manifest["raizes"]
        if type(roots) is not dict or set(roots) != _RAIZES:
            raise ValueError("Raízes fechadas ausentes")
        roots = {k: Path(v) for k, v in roots.items() if type(v) is str}
        if set(roots) != _RAIZES or any(
            not v.is_absolute() or ".." in v.parts for v in roots.values()
        ):
            raise ValueError("Raízes exigem paths absolutos")
        # Não resolve symlinks: o próprio dir_fd confirma cada raiz ao ler seus membros.
        members = manifest["membros"]
        if type(members) is not dict or len(members) > 4096:
            raise ValueError("Catálogo de membros inválido/excessivo")
        parsed = {}
        for mid, spec in members.items():
            if (
                type(mid) is not str
                or not mid
                or type(spec) is not dict
                or set(spec) != {"raiz", "relativo", "sha256"}
            ):
                raise ValueError("Descritor de membro inválido")
            root, rel, sha = spec["raiz"], spec["relativo"], spec["sha256"]
            if (
                type(root) is not str
                or root not in _RAIZES
                or type(rel) is not str
                or not rel
                or Path(rel).is_absolute()
                or ".." in Path(rel).parts
                or type(sha) is not str
                or _HASH.fullmatch(sha) is None
            ):
                raise ValueError("Path/hash de membro inválido")
            # Famílias físicas: nenhuma autorização livre de credencial/executor externo.
            if root == "repositorio" and not (
                rel.startswith("configs/cdp/") or rel == ".cdp/local.yaml"
            ):
                raise ValueError("Membro do repositório fora das configurações/identidade")
            parsed[mid] = (root, rel, sha)
        entries = manifest["entradas"]
        if type(entries) is not dict or set(entries) != {
            "mandato",
            "universo",
            "nomes",
            "rotinas",
            "executor",
            "identidade",
            "eventos_macro",
        }:
            raise ValueError("Entradas nativas incompletas")
        if any(type(v) is not str or v not in parsed for v in entries.values()):
            raise ValueError("Entrada sem membro declarado")
        params = manifest["parametros"]
        if (
            type(params) is not dict
            or not set(_PARAMETROS).issubset(params)
            or any(type(v) is not str or v not in parsed for v in params.values())
        ):
            raise ValueError("Parâmetros explícitos incompletos")
        docs = manifest["documentos"]
        if type(docs) is not dict or any(
            _HASH.fullmatch(k) is None
            or type(v) is not str
            or v not in parsed
            or parsed[v][2] != k
            or parsed[v][0] != "rascunhos"
            for k, v in docs.items()
        ):
            raise ValueError("Documento não vinculado ao corpo físico")
        env = manifest["ambiente_identidade"]
        if (
            type(env) is not dict
            or set(env) - {"CDP_HARNESS", "CDP_EXECUTOR"}
            or any(type(v) is not str for v in env.values())
        ):
            raise ValueError("Ambiente de identidade não fechado")
        from ..contracts import HARNESS_MINDS

        if (
            type(manifest["mente_esperada"]) is not str
            or manifest["mente_esperada"] not in HARNESS_MINDS
        ):
            raise ValueError("Autoria esperada inválida")
        now, cutoff = _instante(manifest["agora"]), _instante(manifest["conhecimento_ate"])
        as_of = _civil(manifest["as_of"])
        offset = manifest["offset_pc_minutos"]
        if (
            type(offset) is not int
            or not -840 <= offset <= 840
            or cutoff > now
            or as_of > cutoff.date()
        ):
            raise ValueError("Relógio/cortes inválidos")
        receiver = ReceptorArquivos(roots, parsed)

        def physical(mid):
            rid, rel, _ = parsed[mid]
            return roots[rid] / rel

        with ativar_receptor(receiver):
            cfg = load_config(physical(entries["mandato"]))
            # Cache legado não evita recepção: o corpo é recebido antes do parser explícito.
            import yaml

            names = nomes_do_corpo(
                yaml.safe_load(receiver.ler(physical(entries["nomes"])).decode("utf-8"))
            )
            receiver.nomes = names
            universe = load_universe(physical(entries["universo"]), nomes=names)
            routines = carregar(physical(entries["rotinas"]))
            # Estes paths são os exatos que executor.verificar lerá, sem alias do manifesto.
            for key, rel in (
                ("executor", "configs/cdp/executor.yaml"),
                ("identidade", ".cdp/local.yaml"),
            ):
                if physical(entries[key]) != roots["repositorio"] / rel:
                    raise ValueError("Origem de identidade/executor não é o path nativo")
                receiver.ler(physical(entries[key]))
            texts = {
                name: receiver.ler(physical(mid)).decode("utf-8") for name, mid in params.items()
            }
            parameters = _parametros_de_textos(texts)
            events = carregar_eventos_macro(physical(entries["eventos_macro"]))
            if events.get("erro"):
                raise ValueError("Calendário macro declarado inválido")
            receiver.fechar()
        pc = now.astimezone(timezone(timedelta(minutes=offset)))
        rt = Runtime(
            cfg,
            roots["livro"],
            roots["mercado"],
            roots["relatorios"],
            clock=lambda: now,
            teses_root=roots["rascunhos"],
            expected_mind=manifest["mente_esperada"],
            somente_leitura=True,
            leitura_parametros=parameters,
            leitura_eventos_macro=events,
            leitura_publico_root=roots["publico"],
            leitura_pc=pc,
        )
        out = ContextoLeituraRecebido(
            hashlib.sha256(body).hexdigest(),
            body,
            p,
            m6,
            tuple(roots.items()),
            tuple(parsed.items()),
            manifest,
            cfg,
            cfg.config_hash(),
            parameters,
            universe,
            names,
            routines,
            events,
            rt,
            datetime.now(UTC).isoformat(),
            receiver,
        )
        _REGISTRADOS[id(out)] = _SeloRegistro(
            out, out.sha256, body, p, m6, out.config_hash, out.recebido_em
        )
        return out
    except ContextoLeituraInvalido:
        raise
    except (TentativaDeEfeitoLeitura, OSError, ValueError, TypeError, KeyError) as exc:
        error = ContextoLeituraInvalido("Contexto físico/contrato inválido: " + type(exc).__name__)
        received = locals().get("receiver")
        error.readset = received.referencias() if type(received) is ReceptorArquivos else ()
        error.codigo = (
            received.falha.codigo
            if type(received) is ReceptorArquivos and received.falha
            else "CORPO_INVALIDO"
        )
        raise error from exc


class LeitorOperacional:
    """Despacho de leitura nominal; todos os dados vêm de delegates nativos existentes."""

    def __init__(self, contexto: ContextoLeituraRecebido):
        if (
            type(contexto) is not ContextoLeituraRecebido
            or _REGISTRADOS.get(id(contexto)) is None
            or _REGISTRADOS[id(contexto)].contexto is not contexto
        ):
            raise ContextoLeituraInvalido("Contexto deve ter sido recebido pela folha")
        self._contexto = contexto
        self._selo = _REGISTRADOS[id(contexto)]

    def _falha_sem_contexto_novo(self, tool, failure, status, readset=()):
        seal = self._selo
        original = _json_unico(seal.corpo)
        return RespostaConsulta(
            tool,
            seal.sha256,
            original["as_of"],
            original["conhecimento_ate"],
            original["agora"],
            seal.recebido_em,
            readset,
            "nao_verificado",
            "recepcao_atual",
            "nao_avaliada",
            (),
            status,
            None,
            failure,
            None,
        )

    def consultar(self, ferramenta: str, argumentos: Mapping[str, EntradaJSON]) -> RespostaConsulta:
        if type(ferramenta) is not str or ferramenta not in tuple(
            x.value for x in FerramentaLeitura
        ):
            raise IngressoLeituraInvalido("Ferramenta fora da enumeração fechada")
        seal = self._selo
        try:
            if type(argumentos) is not dict:
                raise IngressoLeituraInvalido("Tipos de ingresso não são literais")
            validar_schema_exato(argumentos, schema_ingresso(ferramenta))
            if argumentos["contexto_sha256"] != seal.sha256:
                raise IngressoLeituraInvalido("CONTEXTO_DESCONHECIDO")
            _seletores_declarados(_json_unico(seal.corpo), ferramenta, argumentos)
        except ValueError as exc:
            code = (
                "CONTEXTO_DESCONHECIDO"
                if str(exc) == "CONTEXTO_DESCONHECIDO"
                else "INGRESSO_INVALIDO"
            )
            return self._falha_sem_contexto_novo(
                ferramenta, FalhaLeitura(code, str(exc)), "recusado"
            )
        private = None
        try:
            private = _receber_contexto_nativo(seal.path, seal)
            if (
                private.corpo != seal.corpo
                or private.m6 != seal.m6
                or private.sha256 != seal.sha256
                or private.config_hash != seal.config_hash
            ):
                return self._falha_sem_contexto_novo(
                    ferramenta,
                    FalhaLeitura("LEITURA_INSTAVEL", "Contexto difere do selo original"),
                    "indisponivel",
                    private.receptor().referencias(),
                )
            # Objeto por chamada: nenhum alias público nem troca do contexto deste leitor.
            return LeitorOperacional(private)._consultar_recebido(ferramenta, argumentos)
        except ContextoLeituraInvalido as exc:
            return self._falha_sem_contexto_novo(
                ferramenta,
                FalhaLeitura(exc.codigo, "Reconstrução nativa do contexto recusada"),
                "indisponivel",
                exc.readset,
            )
        finally:
            if private is not None:
                _REGISTRADOS.pop(id(private), None)

    def _consultar_recebido(
        self, ferramenta: str, argumentos: Mapping[str, EntradaJSON]
    ) -> RespostaConsulta:
        if type(ferramenta) is not str or ferramenta not in tuple(
            x.value for x in FerramentaLeitura
        ):
            raise IngressoLeituraInvalido("Ferramenta fora da enumeração fechada")
        ctx = self._contexto
        receiver = ctx.receptor()
        result, failure, status, integrity, semantic = (
            None,
            None,
            "disponivel",
            "nao_verificado",
            "nao_avaliada",
        )
        hashes = ()
        tool = ferramenta
        try:
            if type(ferramenta) is not str or type(argumentos) is not dict:
                raise IngressoLeituraInvalido("Tipos de ingresso não são literais")
            validar_schema_exato(argumentos, schema_ingresso(ferramenta))
            if argumentos["contexto_sha256"] != ctx.sha256:
                raise IngressoLeituraInvalido("CONTEXTO_DESCONHECIDO")
            self._seletores(ferramenta, argumentos)
            body, m6 = receber_fd(ctx.path, limite=1048576)
            if body != ctx.corpo or m6 != ctx.m6 or ctx.cfg.config_hash() != ctx.config_hash:
                raise FonteLeituraIndisponivel("LEITURA_INSTAVEL", "Contexto mudou após recepção")
            with ativar_receptor(receiver):
                # Entradas efetivas re-recebidas em cada consulta, mesmo quando parser já retido.
                entry_ids = [
                    *ctx.declaracoes["entradas"].values(),
                    *ctx.declaracoes["parametros"].values(),
                ]
                for mid in dict.fromkeys(entry_ids):
                    root, rel, _ = dict(ctx.membros)[mid]
                    receiver.ler(dict(ctx.raizes)[root] / rel)
                receiver.conferir_recusa()
                native, integrity, semantic, hashes = self._despachar(ferramenta, argumentos)
                receiver.fechar()
                result = serializar_valor(native)
                receiver.fechar()
        except IngressoLeituraInvalido as exc:
            status = "recusado"
            failure = FalhaLeitura(
                "CONTEXTO_DESCONHECIDO"
                if str(exc) == "CONTEXTO_DESCONHECIDO"
                else "INGRESSO_INVALIDO",
                str(exc),
            )
        except TentativaDeEfeitoLeitura:
            failure = receiver.falha or FalhaLeitura(
                "EFEITO_RECUSADO", "Delegate tentou efeito fora do contrato"
            )
            status = "recusado" if failure.codigo == "EFEITO_RECUSADO" else "indisponivel"
        except FonteLeituraIndisponivel as exc:
            status, failure = "indisponivel", FalhaLeitura(exc.codigo, exc.mensagem, exc.membros)
        except FileNotFoundError:
            status, failure = (
                "indisponivel",
                FalhaLeitura("ARQUIVO_AUSENTE", "Arquivo nativo requerido ausente"),
            )
        except Exception as exc:
            status, failure = (
                "indisponivel",
                FalhaLeitura(
                    "ERRO_NATIVO",
                    "Delegate nativo encerrou sem resultado",
                    tipo_excecao_nativa=type(exc).__name__,
                ),
            )
        if failure is not None:
            result, hashes, integrity, semantic = None, (), "nao_verificado", "nao_avaliada"
        return RespostaConsulta(
            tool,
            ctx.sha256,
            ctx.declaracoes["as_of"],
            ctx.declaracoes["conhecimento_ate"],
            ctx.declaracoes["agora"],
            ctx.recebido_em,
            receiver.referencias(),
            integrity,
            "recepcao_atual",
            semantic,
            tuple(hashes),
            status,
            result,
            failure,
            hash_resultado(result) if result is not None else None,
        )

    def _seletores(self, tool, a):
        ctx = self._contexto
        _seletores_declarados(ctx.declaracoes, tool, a)
        if "emissor" in a and a["emissor"] not in ctx.universo.issuers.index:
            raise IngressoLeituraInvalido("Emissor fora do universo recebido")
        if tool == FerramentaLeitura.COBERTURA.value and "instrumento_tipo" in a:
            iid = a["instrumento_id"]
            if a["instrumento_tipo"] == "emissor":
                if iid not in ctx.universo.issuers.index:
                    raise IngressoLeituraInvalido("Emissor fora do universo recebido")
            else:
                # Mesma identidade de insumos_etf: ETF_<ticker antes do ponto>.
                etfs = {
                    "ETF_" + item["ticker"].split(".")[0] for item in ctx.parametros.etfs["etfs"]
                }
                if iid not in etfs:
                    raise IngressoLeituraInvalido("ETF fora do catálogo recebido")

    def _despachar(self, tool, a):
        rt, ctx = self._contexto.runtime, self._contexto
        if tool == FerramentaLeitura.ESTADO.value:
            from ..estado import estado

            result = estado(
                rt,
                raiz=dict(ctx.raizes)["repositorio"],
                agora=_instante(a["agora"]),
                rapido=a["rapido"],
                rede=False,
                rot=ctx.rotinas,
                env=dict(ctx.declaracoes["ambiente_identidade"]),
            )
            return result, "nao_verificado", "nao_avaliada", ()
        if tool == FerramentaLeitura.AGENDA.value:
            from .agenda import agenda

            return agenda(rt, now=_instante(a["agora"])), "nao_verificado", "nao_avaliada", ()
        if tool == FerramentaLeitura.INTEGRIDADE.value:
            return self._integridade(a["escopo"])
        if tool == FerramentaLeitura.FATOS.value:
            fb, _ = self._preparado(a)
            ids = a["fact_ids"]
            if any(fid not in fb.facts for fid in ids):
                raise FonteLeituraIndisponivel(
                    "PREPARADO_AUSENTE", "Referência de fato desconhecida"
                )
            # Seleção explícita do consumidor; mantém os Fact nativos sem recalcular/alterar.
            result = fb if not ids else tuple(fb.facts[fid] for fid in ids)
            return result, "nao_verificado", "nao_avaliada", (("factbook", fb.factbook_hash()),)
        if tool == FerramentaLeitura.VALIDAR.value:
            return self._validar(a)
        if tool == FerramentaLeitura.CARTEIRA.value:
            return self._carteira(a)
        if tool == FerramentaLeitura.RISCO.value:
            return self._risco(a)
        if tool == FerramentaLeitura.COBERTURA.value:
            return self._cobertura(a)
        if tool == FerramentaLeitura.PACOTE.value:
            from .pacote import construir_pacote, render_pacote

            kwargs = (
                {"semana": _civil(a["semana"])} if "semana" in a else {"data": _civil(a["data"])}
            )
            if "emissor" in a:
                kwargs["emissor"] = a["emissor"]
            p = construir_pacote(rt, a["etapa"], mente=a["mente"], **kwargs)
            return (
                (p, render_pacote(p, gerado_em=a["gerado_em"])),
                "nao_verificado",
                "nao_avaliada",
                p.origem,
            )
        raise IngressoLeituraInvalido("Ferramenta desconhecida")

    def _preparado(self, a):
        from ..contracts import FactBook

        rt = self._contexto.runtime
        stage = a["etapa"]
        if stage == "tese":
            from .tese import load_prepared, thesis_dir

            return load_prepared(thesis_dir(rt.book_root, _civil(a["semana"])))
        if stage == "nota":
            from .notas import load_prepared, nota_dir

            return load_prepared(nota_dir(rt.book_root, a["emissor"], _civil(a["data"])))
        if stage.startswith("comentario-"):
            folder = (
                rt.reports_root
                / ("daily" if stage == "comentario-diario" else "semanal")
                / a["data"]
            )
            fb = FactBook.model_validate_json(ler_texto(folder / "factbook.json", encoding="utf-8"))
            analysis = (
                json.loads(ler_texto(folder / "dados.json", encoding="utf-8"))
                if stage == "comentario-semanal"
                else None
            )
            return fb, analysis
        # A projeção context.json omite formula/inputs e não é FactBook completo. Reconstrução
        # usa a receita nativa e manifesto de prepare autenticado, sem store_override/prepare I/O.
        from ..research.pm_agent import pm_factbook

        week = _civil(a["semana"])
        md, info = rt.market_for_week(
            week, live=False, briefing_dir=rt.week_dir(week) / "briefing", record=False
        )
        if info["config_hash"] != rt.cfg.config_hash():
            raise FonteLeituraIndisponivel(
                "INTEGRIDADE_DA_FONTE", "Configuração não é a do prepare recebido"
            )
        native_ctx = rt._context(
            md, week, conhecimento_ate=_instante(self._contexto.declaracoes["conhecimento_ate"])
        )
        fb = rt._factbook(
            native_ctx,
            list(native_ctx.panel.assets.index),
            conhecimento_ate=_instante(self._contexto.declaracoes["conhecimento_ate"]),
        )
        pm_ctx = rt._pm_context(md, native_ctx, week, fb, rt._analysis_ts(info))
        return pm_factbook(pm_ctx), pm_ctx

    def _validar(self, a):
        from ..contracts import mente_divergente

        ctx, rt = self._contexto, self._contexto.runtime
        mid = ctx.declaracoes["documentos"][a["documento_sha256"]]
        root, rel, _ = dict(ctx.membros)[mid]
        path = dict(ctx.raizes)[root] / rel
        # O receptor lê antes do parser: ausência não aciona templates/preparação.
        ler_texto(path, encoding="utf-8")
        fb, analysis = self._preparado(a)
        stage, out, issues = a["etapa"], None, []
        if stage == "tese":
            from .tese import load_thesis_file

            out, issues = load_thesis_file(path, fb, analysis, expected_mind=a["mente_esperada"])
        elif stage == "nota":
            from .notas import load_note_file

            out, issues = load_note_file(path, fb, analysis, expected_mind=a["mente_esperada"])
        elif stage == "comentario-diario":
            from ..research.commentary import (
                default_allowed_terms,
                parse_commentary_file,
                verify_commentary,
            )

            out, issues = parse_commentary_file(path)
            if out is not None:
                issues += verify_commentary(out, fb, default_allowed_terms(fb))
                if problem := mente_divergente(out.mind, a["mente_esperada"]):
                    issues.append(problem)
        elif stage == "comentario-semanal":
            from ..research.comentario_semanal import (
                parse_comentario,
                termos_permitidos,
                verificar_comentario,
            )

            out, issues = parse_comentario(path)
            if out is not None:
                issues += verificar_comentario(out, fb, analysis["mudancas"], termos_permitidos(fb))
                if problem := mente_divergente(out.mind, a["mente_esperada"]):
                    issues.append(problem)
        else:
            from ..research.pm_agent import load_pm_decision_file, load_research_pack_file

            if stage == "pesquisa":
                out, issues = load_research_pack_file(path, analysis, now=rt.now())
            else:
                out, issues = load_pm_decision_file(path, analysis, mind=a["mente_esperada"])
            if problem := mente_divergente(out.mind, a["mente_esperada"]):
                issues.append(problem)
        # Retorno de diagnóstico fechado em dados nativos, sem fallback/declarar publicação.
        return (
            {"valido": not issues, "saida_nativa": out, "problemas": issues},
            "nao_verificado",
            "negativa_pelo_delegate" if issues else "validada_pelo_delegate",
            (("factbook", fb.factbook_hash()), ("documento", a["documento_sha256"])),
        )

    def _carteira(self, a):
        rt = self._contexto.runtime
        d = _civil(a["data"])
        shadow = a["lado"] == "sombra"
        if a["visao"] == "diaria":
            track = rt.track(shadow)
            ok, errors = track.verify()
            if not ok:
                raise FonteLeituraIndisponivel(
                    "INTEGRIDADE_DA_FONTE", "Track record nativo não íntegro"
                )
            result = track.get(d)
            hashes = (("record", result.record_hash),) if result is not None else ()
        else:
            if shadow:
                from .daily import ShadowBook

                result = ShadowBook(rt.track(True), rt.book).load_booked(d)
            else:
                result = rt.book.load_booked(d)
            hashes = (("approval", result.approval_hash),) if result is not None else ()
        if result is None:
            raise FonteLeituraIndisponivel("ARQUIVO_AUSENTE", "Carteira nativa do seletor ausente")
        return result, "integro", "nao_avaliada", hashes

    def _risco(self, a):
        import pandas as pd

        from ..risk.analytics import risk_decomposition
        from .risco_diario import load, restore

        rt = self._contexto.runtime
        track = rt.track(a["lado"] == "sombra")
        record = track.get(_civil(a["sessao"]))
        if record is None:
            raise FonteLeituraIndisponivel("ARQUIVO_AUSENTE", "Registro diário ausente")
        ok, errors = track.verify()
        if not ok:
            raise FonteLeituraIndisponivel("INTEGRIDADE_DA_FONTE", "Track record não íntegro")
        diagnostic = load(track, record)
        if diagnostic is None or diagnostic["models"].get(a["modelo"]) is None:
            raise FonteLeituraIndisponivel("ARQUIVO_AUSENTE", "Modelo diário arquivado ausente")
        model = restore(diagnostic["models"][a["modelo"]])
        result = risk_decomposition(pd.Series(diagnostic["weights"], dtype=float), model)
        return result, "integro", "nao_avaliada", tuple(record.input_hashes.items())

    def _cobertura(self, a):
        from ..cobertura.livro import conferir_corte, ultimo_snapshot

        rt = self._contexto.runtime
        snap = ultimo_snapshot(
            rt.book_root, _civil(a["data"]), conhecimento_ate=_instante(a["conhecimento_ate"])
        )
        if snap is None:
            raise FonteLeituraIndisponivel("ARQUIVO_AUSENTE", "Retrato nativo ausente no corte")
        conferir_corte(snap, _instante(a["conhecimento_ate"]))
        if a["visao"] in ("tabela", "estado") and snap._bytes("modelos.csv") is None:
            raise FonteLeituraIndisponivel("ARQUIVO_AUSENTE", "Tabela nativa ausente")
        if a["visao"] == "tabela":
            result = snap.tabela()
        elif a["visao"] == "estado":
            table = snap.estado()
            result = (
                table.loc[[a["instrumento_id"]]] if a["instrumento_id"] in table.index else None
            )
        else:
            result = (
                snap.etf(a["instrumento_id"])
                if a["instrumento_tipo"] == "etf"
                else snap.modelo(a["instrumento_id"])
            )
        if result is None:
            raise FonteLeituraIndisponivel(
                "ARQUIVO_AUSENTE", "Modelo nativo do instrumento ausente"
            )
        return result, "integro", "nao_avaliada", (("snapshot", snap.manifest_sha256),)

    def _integridade(self, scope):
        rt = self._contexto.runtime
        if scope == "livro":
            result = rt.book.verify_integrity()
        elif scope == "mercado":
            result = rt.store.verify_chain()
        elif scope == "track":
            result = rt.track().verify()
        elif scope == "cobertura":
            from ..cobertura.livro import verificar

            result = verificar(rt.book_root, recalcular=False)
        else:
            # Verify_all tem tratamento legado de exceção como sem-track. Esses resultados
            # continuam visíveis, mas cada componente obrigatório é conferido sem esse escape.
            result = rt.verify_all()
            rt.store.verify_chain()  # ausência/erro não pode virar íntegro no ramo completo
            rt.track().verify()
        return result, "integro" if result[0] else "falho", "nao_avaliada", ()
