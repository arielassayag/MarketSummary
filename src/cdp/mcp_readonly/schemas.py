"""Contratos de transporte próprios, sem introspecção de aliases financeiros."""
from __future__ import annotations

import math
from itertools import zip_longest
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

MAX_CELULAS = 10_000
MEMBROS = (
    "fund.yaml", "valuation.yaml", "nomes.yaml", "universo.csv",
    "cobertura/arquetipos.csv", "cobertura/betas_setor.csv", "cobertura/unidades.csv",
    "cobertura/sotp.yaml", "cobertura/etfs.yaml",
)


def _numero(value):
    if type(value) not in (int, float):
        raise ValueError("Número JSON explícito exigido; bool e texto não são números")
    try:
        if not math.isfinite(value):
            raise ValueError("Número não finito recusado")
        return float(value)
    except OverflowError as exc:
        raise ValueError("Número fora do transporte finito") from exc


Numero = Annotated[float, BeforeValidator(_numero)]
Dimensao = Annotated[int, Field(ge=1, le=128)]
Forma = Annotated[list[Dimensao], Field(max_length=4)]
EstadoNumero = Literal["finito", "nan", "mais_infinito", "menos_infinito"]
Sha = Annotated[str, Field(pattern="^[0-9a-f]{64}$")]


class Fechado(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class EntradaKE(Fechado):
    rf: Numero
    beta: Numero
    erp: Numero
    lam: Numero
    crp: Numero


class EscalarPB(Fechado):
    tipo: Literal["escalar"]
    valor: Numero

    def forma(self) -> list[int]:
        return []


class AusentePB(Fechado):
    tipo: Literal["ausente"]


class ArrayPB(Fechado):
    tipo: Literal["array"]
    forma: Forma
    valores: Annotated[list[Numero | AusentePB], Field(min_length=1, max_length=MAX_CELULAS)]

    @model_validator(mode="after")
    def conferir_forma(self):
        if math.prod(self.forma) != len(self.valores):
            raise ValueError("Forma e número de células divergem")
        return self


OperandoPB = Annotated[EscalarPB | ArrayPB | AusentePB, Field(discriminator="tipo")]


def forma_pb(operandos) -> list[int]:
    shapes = [x.forma if isinstance(x, ArrayPB) else [] for x in operandos]
    result = []
    for axes in zip_longest(*(reversed(s) for s in shapes), fillvalue=1):
        non_unit = set(axes) - {1}
        if len(non_unit) > 1:
            raise ValueError("Formas incompatíveis para broadcast")
        result.append(max(axes))
    shape = list(reversed(result))
    if math.prod(shape) > MAX_CELULAS:
        raise ValueError("Broadcast excede o limite de células do transporte")
    return shape


class EntradaPB(Fechado):
    roe: OperandoPB
    ke: OperandoPB
    g: OperandoPB
    estrito: bool = True

    @model_validator(mode="after")
    def conferir_broadcast(self):
        forma_pb((self.roe, self.ke, self.g))
        return self


class EntradaPreenchimento(Fechado):
    ordem_acoes: Annotated[int, Field(ge=-(2**53 - 1), le=2**53 - 1)]
    capacidade_usd: Numero
    preco_usd: Numero


class NumeroObservado(Fechado):
    valor: Numero | None
    estado: EstadoNumero

    @model_validator(mode="after")
    def conferir_estado(self):
        if (self.estado == "finito") != (self.valor is not None):
            raise ValueError("Estado numérico e presença do valor divergem")
        return self


class Erro(Fechado):
    tipo: Literal["erro"] = "erro"
    codigo: Literal["ENTRADA_INVALIDA", "TECNICA_DESCONHECIDA", "KERNEL_RECUSOU"]
    mensagem: Annotated[str, Field(max_length=512)]


class SucessoKE(Fechado):
    tipo: Literal["sucesso"] = "sucesso"
    custo: NumeroObservado
    unidade: Literal["taxa_decimal"] = "taxa_decimal"
    moeda_base: Literal["USD"] = "USD"


class SucessoPB(Fechado):
    tipo: Literal["sucesso"] = "sucesso"
    forma: Forma
    valores: Annotated[list[Numero | None], Field(min_length=1, max_length=MAX_CELULAS)]
    estados: Annotated[list[EstadoNumero], Field(min_length=1, max_length=MAX_CELULAS)]
    estrito: bool
    unidade: Literal["x"] = "x"

    @model_validator(mode="after")
    def conferir_celulas(self):
        if math.prod(self.forma) != len(self.valores) or len(self.valores) != len(self.estados):
            raise ValueError("Forma, valores e estados divergem na saída")
        for value, state in zip(self.valores, self.estados, strict=True):
            NumeroObservado(valor=value, estado=state)
        return self


class SucessoPreenchimento(Fechado):
    tipo: Literal["sucesso"] = "sucesso"
    acoes: Annotated[int, Field(ge=-(2**53 - 1), le=2**53 - 1)]
    unidade: Literal["acoes_inteiras_assinadas"] = "acoes_inteiras_assinadas"
    capacidade_unidade: Literal["USD"] = "USD"
    preco_unidade: Literal["USD_por_acao_da_linha"] = "USD_por_acao_da_linha"


class SaidaBase(Fechado):
    contrato: Literal["cdp.mcp.resultado/v1"] = "cdp.mcp.resultado/v1"
    versao_motor: str
    origem: Literal["operandos_declarados"] = "operandos_declarados"


class SaidaKE(SaidaBase):
    tecnica: Literal["calcular_ke"] = "calcular_ke"
    resultado: Annotated[SucessoKE | Erro, Field(discriminator="tipo")]


class SaidaPB(SaidaBase):
    tecnica: Literal["avaliar_pb_justificado"] = "avaliar_pb_justificado"
    resultado: Annotated[SucessoPB | Erro, Field(discriminator="tipo")]


class SaidaPreenchimento(SaidaBase):
    tecnica: Literal["estimar_preenchimento"] = "estimar_preenchimento"
    resultado: Annotated[SucessoPreenchimento | Erro, Field(discriminator="tipo")]


class SaidaDesconhecida(SaidaBase):
    tecnica: Literal["desconhecida"] = "desconhecida"
    resultado: Erro


class TecnicaCatalogo(Fechado):
    nome: Literal["calcular_ke", "avaliar_pb_justificado", "estimar_preenchimento"]
    unidade: str
    input_schema_sha256: Sha
    output_schema_sha256: Sha


class Catalogo(Fechado):
    contrato: Literal["cdp.mcp.catalogo/v1"] = "cdp.mcp.catalogo/v1"
    versao_motor: str
    transporte: Literal["stdio"] = "stdio"
    tecnicas: Annotated[list[TecnicaCatalogo], Field(min_length=3, max_length=3)]
    aviso: Literal["Operandos declarados; sem identidade, operação ou autoridade financeira"]


class RecursoExemplo(Fechado):
    contrato: Literal["cdp.mcp.recurso-exemplo/v1"] = "cdp.mcp.recurso-exemplo/v1"
    origem: Literal["EXEMPLO"] = "EXEMPLO"
    nome: Literal["latam_simulado_v1"] = "latam_simulado_v1"
    aviso: Literal["DADOS SIMULADOS"] = "DADOS SIMULADOS"
    membro: str
    sha256: Sha
    tipo_conteudo: Literal["application/json", "application/yaml", "text/csv"]
    conteudo_utf8: str


class ManifestoExemplo(Fechado):
    schema_id: Literal["cdp.tecnicas.exemplo/v1"] = Field(alias="schema")
    papel: Literal["EXEMPLO"]
    nome: Literal["latam_simulado_v1"]
    aviso: Literal["DADOS SIMULADOS"]
    membros: dict[str, Sha]

    @model_validator(mode="after")
    def conferir_membros(self):
        if set(self.membros) != set(MEMBROS):
            raise ValueError("Manifesto fora da lista fechada de membros")
        return self
