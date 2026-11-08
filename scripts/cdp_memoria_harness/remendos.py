"""Prepara e aplica intervenções de texto propostas e julgadas em tarefas do Codex."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import tempfile
from pathlib import Path

BRACOS = "BC"
ROTULOS = "XY"


def unico(pares):
    dado = dict(pares)
    if len(dado) != len(pares):
        raise ValueError("JSON com chaves repetidas")
    return dado


def ler(path):
    return decodificar(path.read_bytes())


def decodificar(bruto):
    return json.loads(bruto, object_pairs_hook=unico)


def hash_bytes(bruto):
    return hashlib.sha256(bruto).hexdigest()


def sha(path):
    return hash_bytes(path.read_bytes())


def gravar(path, dado):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(dado, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    path.chmod(0o444)


def indexar(lista, chave="id"):
    if not isinstance(lista, list):
        raise ValueError("Lista esperada")
    indice = {}
    for item in lista:
        id_ = item[chave]
        if not isinstance(id_, str) or not id_.strip() or id_ in indice:
            raise ValueError(f"Identificador inválido ou duplicado: {id_!r}")
        indice[id_] = item
    return indice


def ponteiro(objeto, caminho):
    if not isinstance(caminho, str) or not caminho.startswith("/") or len(caminho) > 250:
        raise ValueError("Ponteiro de prova inválido")
    for parte in caminho[1:].split("/"):
        if "~" in parte.replace("~0", "").replace("~1", ""):
            raise ValueError("Escape de ponteiro inválido")
        parte = parte.replace("~1", "/").replace("~0", "~")
        if isinstance(objeto, list):
            if not parte.isascii() or not parte.isdecimal() or str(int(parte)) != parte:
                raise ValueError("Índice de prova inválido")
            objeto = objeto[int(parte)]
        elif isinstance(objeto, dict):
            objeto = objeto[parte]
        else:
            raise ValueError("Ponteiro não chega a um campo do caso")
    return objeto


def texto(valor, limite):
    if not isinstance(valor, str) or valor != valor.strip() or not valor or len(valor) > limite:
        raise ValueError("Texto vazio, com espaços externos ou acima do limite")
    return valor


def conferir(p, caso, base):
    if set(p) != {"id", "operacao", "ancora", "texto", "provas", "motivo"}:
        raise ValueError("Campos da proposta incompatíveis")
    if p["operacao"] not in ("inserir", "corrigir"):
        raise ValueError("Operação inválida")
    ancora = texto(p["ancora"], 320)
    mudanca = texto(p["texto"], 420)
    texto(p["motivo"], 400)
    if p["id"] not in ("p1", "p2", "p3"):
        raise ValueError("ID fora dos rótulos neutros da proposta")
    if len(ancora.splitlines()) != 1 or len(mudanca.splitlines()) != 1 or mudanca == ancora:
        raise ValueError("Trecho ultrapassa uma linha ou repete a âncora")
    inicio = base.find(ancora)
    if len(ancora) < 12 or inicio < 0 or base.find(ancora, inicio + 1) >= 0:
        raise ValueError("A âncora precisa ocorrer uma única vez na referência")
    fim = inicio + len(ancora)
    if p["operacao"] == "inserir" and (
        ancora[-1] not in ".!?…" or (fim < len(base) and not base[fim].isspace())
    ):
        raise ValueError("A inserção precisa ocorrer depois de uma frase completa")
    provas = p["provas"]
    if not isinstance(provas, list) or not 1 <= len(provas) <= 3:
        raise ValueError("Quantidade de provas inválida")
    for prova in provas:
        if set(prova) != {"ponteiro", "trecho"}:
            raise ValueError("Campos de prova incompatíveis")
        fonte = ponteiro(caso, prova["ponteiro"])
        literal = fonte if isinstance(fonte, str) else json.dumps(
            fonte, ensure_ascii=False, separators=(",", ":")
        )
        if texto(prova["trecho"], 280) not in literal:
            raise ValueError(f"Trecho de prova ausente em {prova['ponteiro']}")
    return inicio, fim


def arquivos_de_entrada(trilha):
    return [f"casos-{trilha}.json", f"referencia-{trilha}.json"] + [
        f"propostas-{trilha}-{arm}.json" for arm in BRACOS
    ]


def preparar(raiz, trilha):
    brutos = {name: (raiz / name).read_bytes() for name in arquivos_de_entrada(trilha)}
    lacres = {name: hash_bytes(bruto) for name, bruto in brutos.items()}
    casos, bases, *propostas = [indexar(decodificar(bruto)["casos"]) for bruto in brutos.values()]
    if any(itens.keys() != casos.keys() for itens in [bases, *propostas]):
        raise ValueError("Casos incompatíveis nas entradas")
    destino = raiz / f"preparo-{trilha}"
    if destino.exists():
        raise FileExistsError(destino)
    resultado, chave, recusas = [], {}, []
    rng = secrets.SystemRandom()
    for id_, caso in casos.items():
        base = bases[id_]["analise"]
        texto(base, 12000)
        arms = list(BRACOS)
        rng.shuffle(arms)
        chave[id_] = dict(zip(ROTULOS, arms, strict=True))
        opcoes = []
        for rotulo, arm in chave[id_].items():
            candidatas = indexar(propostas[BRACOS.index(arm)][id_]["propostas"])
            if len(candidatas) > 3:
                raise ValueError(f"Mais de três propostas em {id_}/{arm}")
            intervalos, aceitas = [], []
            for p in candidatas.values():
                try:
                    inicio, fim = conferir(p, caso, base)
                    if any(inicio < b and a < fim for a, b in intervalos):
                        raise ValueError("Âncora sobreposta a outra proposta do braço")
                except (ValueError, IndexError, KeyError, TypeError) as erro:
                    recusas.append({"caso": id_, "braco": arm, "id": p["id"], "motivo": str(erro)})
                else:
                    intervalos.append((inicio, fim))
                    aceitas.append(p | {"motivo": "Conferir a proposta contra o dossiê."})
            opcoes.append({"rotulo": rotulo, "propostas": aceitas})
        resultado.append({"id": id_, "caso": caso, "referencia": base, "opcoes": opcoes})

    with tempfile.TemporaryDirectory(dir=raiz) as tmp:
        pasta = Path(tmp) / "preparo"
        pasta.mkdir()
        pacote = pasta / "para-validacao.json"
        mascara = pasta / "chave-validacao.json"
        gravar(pacote, {"casos": resultado})
        gravar(mascara, chave)
        mascara.chmod(0o400)
        gravar(pasta / "recusas-mecanicas.json", {"recusas": recusas})
        gravar(pasta / "lacres.json", lacres | {p.name: sha(p) for p in (pacote, mascara)})
        digest = sha(pacote)
        pasta.rename(destino)
    return destino, digest


def aplicar(raiz, trilha, parecer_path):
    origem = raiz / f"preparo-{trilha}"
    pacote = origem / "para-validacao.json"
    mascara = origem / "chave-validacao.json"
    lacres = ler(origem / "lacres.json")
    origens = {name: raiz / name for name in arquivos_de_entrada(trilha)}
    origens.update({pacote.name: pacote, mascara.name: mascara})
    if lacres.keys() != origens.keys():
        raise ValueError("O manifesto precisa lacrar todas as entradas")
    brutos = {name: path.read_bytes() for name, path in origens.items()}
    if any(hash_bytes(bruto) != lacres[name] for name, bruto in brutos.items()):
        raise ValueError("Entrada alterada depois da preparação")
    caso_dado = indexar(decodificar(brutos[pacote.name])["casos"])
    chave = decodificar(brutos[mascara.name])
    parecer_bruto = parecer_path.read_bytes()
    parecer = decodificar(parecer_bruto)
    if set(parecer) != {"pacote_sha256", "casos"} or parecer["pacote_sha256"] != lacres[pacote.name]:
        raise ValueError("Parecer não corresponde ao pacote lacrado")
    por_caso = indexar(parecer["casos"])
    if por_caso.keys() != caso_dado.keys():
        raise ValueError("Parecer precisa decidir todos os casos")
    resultados = {arm: [] for arm in BRACOS}
    relato = []
    for id_, caso in caso_dado.items():
        propostas = indexar(caso["opcoes"], "rotulo")
        opcoes = indexar(por_caso[id_]["opcoes"], "rotulo")
        if opcoes.keys() != propostas.keys() or set(chave[id_].values()) != set(BRACOS):
            raise ValueError("Rótulos incompatíveis")
        for rotulo, dados in opcoes.items():
            arm = chave[id_][rotulo]
            base = caso["referencia"]
            alteracoes = indexar(propostas[rotulo]["propostas"])
            decisoes = indexar(dados["decisoes"])
            if decisoes.keys() != alteracoes.keys():
                raise ValueError(f"Parecer não cobriu as propostas de {id_}/{rotulo}")
            aceitas = []
            for id_proposta, decisao in decisoes.items():
                if set(decisao) != {"id", "decisao", "motivo"}:
                    raise ValueError("Campos do parecer incompatíveis")
                texto(decisao["motivo"], 800)
                if decisao["decisao"] not in ("aceitar", "rejeitar"):
                    raise ValueError("Decisão inválida")
                p = alteracoes[id_proposta]
                if decisao["decisao"] == "aceitar":
                    inicio, fim = conferir(p, caso["caso"], base)
                    if p["operacao"] == "inserir":
                        inicio, mudanca = fim, " " + p["texto"]
                    else:
                        mudanca = p["texto"]
                    aceitas.append((inicio, fim, mudanca))
                relato.append({"caso": id_, "braco": arm, "operacao": p["operacao"]} | decisao)
            saida = base
            for inicio, fim, mudanca in sorted(aceitas, reverse=True):
                saida = saida[:inicio] + mudanca + saida[fim:]
            resultados[arm].append({"id": id_, "analise": saida})
    destino = raiz / f"aplicado-{trilha}"
    if destino.exists():
        raise FileExistsError(destino)
    with tempfile.TemporaryDirectory(dir=raiz) as tmp:
        pasta = Path(tmp) / "aplicado"
        pasta.mkdir()
        for arm, resultado in resultados.items():
            gravar(pasta / f"revisao-{trilha}-{arm}.json", {"casos": resultado})
        gravar(pasta / "aplicacao.json", {
            "parecer_sha256": hash_bytes(parecer_bruto), "decisoes": relato,
        })
        pasta.rename(destino)
    return destino


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acao", choices=("preparar", "aplicar"))
    parser.add_argument("raiz", type=Path)
    parser.add_argument("trilha", choices=("risco", "valuation"))
    parser.add_argument("--parecer", type=Path)
    args = parser.parse_args()
    if args.acao == "preparar":
        print(*preparar(args.raiz, args.trilha))
    else:
        print(aplicar(args.raiz, args.trilha, args.parecer or args.raiz / f"parecer-{args.trilha}.json"))


if __name__ == "__main__":
    main()
