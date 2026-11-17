"""Recorte temporal — o ``Escopo``.

**Muito mais raso que o do RecifeTB, e de propósito** — mesmo raciocínio do
`manaustb`. Lá o `Escopo` carregava nível geográfico (BR/UF/MUN/BAIRRO), UF,
município e bairro, porque o dataset nacional por baixo tinha essa
profundidade inteira. Aqui a extração (`scripts/extrair_sinan_df.py`) já
filtra por `municipio_residencia = 'Brasília'` — não sobra nível para
navegar. O único recorte que muda tela a tela é o **ano**.

Mantido como dataclass, e não um `int` solto pelo código, para a doença ficar
junto do ano num só objeto.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from . import config


#: Grafias que as fontes dão a uma mesma RA e que a normalização de acento e
#: caixa não junta: o IPEDF escreve "Sol Nascente e Pôr do Sol"; o IBGE e o
#: banco, "Sol Nascente/Pôr do Sol". A chave de sempre é a do banco.
_ALIAS_RA = {"SOL NASCENTE E POR DO SOL": "SOL NASCENTE/POR DO SOL"}


def chave_ra(nome: str) -> str:
    """Forma canônica do nome de uma Região Administrativa: sem acento, sem
    caixa, sem espaço duplo — mesmo critério de `chave_bairro()` no RecifeTB.

    É o que liga `Regiao_adm` de `dados_geolink."DF_geo_TB"` a `NM_SUBDIST`
    da malha de RAs (hoje a do IPEDF): as fontes grafam RA de jeito
    um pouco diferente ("Sol Nascente/Pôr do Sol" x "SOL NASCENTE/POR DO
    SOL"), e a chave normalizada é a única forma que bate 1:1 nas 33 —
    conferido em 11/set/2026, nenhuma sobra de nenhum dos dois lados.
    """
    texto = unicodedata.normalize("NFKD", str(nome or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    chave = " ".join(texto.upper().split())
    return _ALIAS_RA.get(chave, chave)


@dataclass(frozen=True, slots=True)
class Escopo:
    """Recorte de análise: doença e ano. O Distrito Federal é implícito — o
    único valor."""

    doenca: str
    ano: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "doenca", str(self.doenca or config.TUBERCULOSE).strip().upper())
        object.__setattr__(self, "ano", int(self.ano))

    @property
    def ano_anterior(self) -> int:
        return self.ano - 1
