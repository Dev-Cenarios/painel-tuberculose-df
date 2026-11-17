"""Pacotes de configuração por doença.

Mesmo mecanismo do RecifeTB: o core é único e a doença é configuração. O pack
em uso é resolvido nesta ordem:

1. o nome passado a :func:`carregar`
2. variável de ambiente ``SINAN_DOENCA``
3. ``tuberculose`` (padrão)
"""

from __future__ import annotations

import importlib
import os
import pkgutil
from types import ModuleType

PADRAO = "tuberculose"

#: O que o core lê de qualquer pack. Mantém `rampa_mapa`/`cortes_fixos` no
#: contrato mesmo sem mapa neste painel: são stubs que devolvem vazio/`None`
#: em `tuberculose.py`, e exigi-los aqui garante que um pack futuro sem mapa
#: ainda declare a função — só o comportamento muda, a superfície não.
CONTRATO = (
    "DOENCA",
    "TITULO",
    "LAYOUT_KPI",
    "FRACAO_KPI",
    "BOM_SE_CAI",
    "TAXAS",
    "INDICADORES_PROGRAMA",
    "cor",
    "rotulo",
    "rotulo_curto",
    "descricao",
    "grupo_da",
    "variaveis_planas",
    "cortes_fixos",
    "icone",
)


def disponiveis() -> tuple[str, ...]:
    return tuple(sorted(m.name for m in pkgutil.iter_modules(__path__)))


def carregar(nome: str | None = None) -> ModuleType:
    nome = (nome or os.environ.get("SINAN_DOENCA", "")).strip() or PADRAO
    if nome not in disponiveis():
        raise ValueError(
            f"doença desconhecida: {nome!r}. "
            f"Disponíveis: {', '.join(disponiveis())}"
        )
    pack = importlib.import_module(f"{__name__}.{nome}")
    if faltando := [attr for attr in CONTRATO if not hasattr(pack, attr)]:
        raise AttributeError(
            f"o pack {nome!r} não cumpre o contrato: falta "
            f"{', '.join(faltando)}"
        )
    return pack
