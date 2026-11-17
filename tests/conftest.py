"""Configuração da suíte.

Nenhum dos dois parquets é versionado. Sem isto, o pytest quebra na
**coleta** de qualquer módulo que leia dado, com um `FileNotFoundError` vindo
do topo do arquivo — mesmo critério do `conftest.py` do manaustb.

**Duas fontes, duas flags.** `sinan_df` sustenta os KPIs de topo
(`microdado.py`); `sinan_df_ra` sustenta o mapa e o painel de detalhe
(`microdado_ra.py`, `tests/paridade/`). Um clone pode ter uma e não a outra
— por exemplo, alguém que só regerou `extrair_sinan_df.py` mas não rodou o
`extrair_sinan_df_geolink.py` ainda.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data import config as config_dados

#: Módulos que leem o parquet de `sinan_df` (KPIs de DF inteiro).
PRECISAM_DE_DADOS = (
    "test_kpis.py",
    "test_microdado.py",
    "test_aplicacao.py",  # a página inteira, KPIs inclusos
)

#: Módulos que leem o parquet de `sinan_df_ra` (mapa, detalhe, paridade).
PRECISAM_DE_DADOS_RA = (
    "test_microdado_ra.py",
    "test_mapa.py",
    "test_aplicacao.py",  # a página inteira, mapa incluso
)


def _dados_presentes() -> bool:
    return (config_dados.dashboard_dir() / "sinan_df").is_dir()


def _dados_ra_presentes() -> bool:
    return (config_dados.dashboard_dir() / "sinan_df_ra").is_dir()


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers", "dado: precisa do parquet de sinan_df; pulado quando ele não está lá"
    )
    config.addinivalue_line(
        "markers", "dado_ra: precisa do parquet de sinan_df_ra; pulado quando ele não está lá"
    )


def pytest_collection_modifyitems(items) -> None:
    pular_dado = pytest.mark.skip(reason="precisa do parquet de sinan_df — ver README")
    pular_ra = pytest.mark.skip(reason="precisa do parquet de sinan_df_ra — ver README")
    for item in items:
        if not _dados_presentes() and item.get_closest_marker("dado"):
            item.add_marker(pular_dado)
        if not _dados_ra_presentes() and item.get_closest_marker("dado_ra"):
            item.add_marker(pular_ra)


collect_ignore: list[str] = []

if not _dados_presentes():
    collect_ignore += list(PRECISAM_DE_DADOS)
if not _dados_ra_presentes():
    collect_ignore += list(PRECISAM_DE_DADOS_RA) + ["paridade/test_referencia.py"]

if collect_ignore:
    print(
        f"\n[conftest] {len(collect_ignore)} módulos ignorados por dado ausente em "
        f"{config_dados.dashboard_dir()}.\n"
        f"           sinan_df:    python -m scripts.extrair_sinan_df && "
        f"python -m scripts.preparar_microdado\n"
        f"           sinan_df_ra: python -m scripts.extrair_sinan_df_geolink && "
        f"python -m scripts.preparar_microdado\n"
        f"           (as duas extrações exigem VPN e credenciais em .env).\n"
    )


def pytest_report_header() -> str:
    origem = Path(config_dados.dashboard_dir())
    estado_df = "presentes" if _dados_presentes() else "AUSENTES"
    estado_ra = "presentes" if _dados_ra_presentes() else "AUSENTES"
    return f"dados: sinan_df {estado_df}, sinan_df_ra {estado_ra} ({origem})"
