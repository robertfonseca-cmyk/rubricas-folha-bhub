"""Uma "tratativa" é um departamento sendo processado dentro do mesmo processo de
contabilização. Empresa e CNPJ são fixos pro processo inteiro; cada tratativa tem
sua própria natureza, Tipo da Integração e sequência de histórico/lançamento.

Adicionado em 2026-08-21 a pedido do Robert: às vezes é preciso cadastrar rubricas
de mais de um departamento diferente no mesmo processo, cada um podendo ter (ou
não) a mesma natureza, e cada um com seu próprio número de lançamento.
"""

from dataclasses import dataclass


@dataclass
class TratativaDepartamento:
    id: int
    departamento: str
    natureza_empresa: str
    tipo_integracao: int
    ultimo_historico: int
    ultimo_lancamento: int
