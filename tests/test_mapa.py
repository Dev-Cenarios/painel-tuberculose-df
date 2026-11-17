"""Mapa coroplético por RA/Região de Saúde (`src/mapa.py`).

Não testa desenho pixel a pixel — confere que a geometria carrega, que a
classificação de cor produz uma escala coerente, e que o `deck()` monta sem
estourar para os dois níveis que o painel oferece. `preparar_geometria` em
si (leitura do shapefile) não roda em teste — o parquet já gerado é o que
se testa, mesma regra do resto da família: teste não depende de o
shapefile de origem estar presente, só do parquet derivado dele.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest

from cenarios_core import mapa
from src.data import config, microdado_ra as mra
from src.doencas import tuberculose as pack

ANO = 2024


def _geo_disponivel() -> bool:
    return (config.geo_dir() / "ra.parquet").is_file()


pytestmark = pytest.mark.skipif(
    not _geo_disponivel(),
    reason="precisa de data/geo/*.parquet — rode python -m scripts.preparar_geometria",
)


@pytest.fixture(scope="module")
def ra() -> gpd.GeoDataFrame:
    return gpd.read_parquet(config.geo_dir() / "ra.parquet")


@pytest.fixture(scope="module")
def regioes_saude() -> gpd.GeoDataFrame:
    return gpd.read_parquet(config.geo_dir() / "regioes_saude.parquet")


# ---------------------------------------------------------------------------
# Geometria
# ---------------------------------------------------------------------------


def test_malha_de_ra_tem_35_feicoes(ra: gpd.GeoDataFrame) -> None:
    """35 RAs desde a camada do IPEDF (08/out/2026): as 33 de antes mais
    Arapoanga e Água Quente, criadas em dez/2022."""
    assert len(ra) == len(config.RA_PARA_REGIAO_SAUDE) == 35
    assert {"ARAPOANGA", "AGUA QUENTE"} <= set(ra["ra_chave"])


def test_a_malha_e_o_dado_falam_das_mesmas_ras(ra: gpd.GeoDataFrame) -> None:
    """Cada chave de RA da malha tem de estar no mapeamento de Região de Saúde,
    e vice-versa — uma RA a mais ou a menos de um lado desenharia polígono sem
    dado, ou dado sem polígono."""
    assert set(ra["ra_chave"]) == set(config.RA_PARA_REGIAO_SAUDE)


def test_as_ras_novas_vem_da_ra_mae_na_regiao_de_saude(ra: gpd.GeoDataFrame) -> None:
    for nova, mae in config.RA_MAE.items():
        assert config.RA_PARA_REGIAO_SAUDE[nova] == config.RA_PARA_REGIAO_SAUDE[mae]


def test_malha_de_regioes_de_saude_tem_sete_feicoes(regioes_saude: gpd.GeoDataFrame) -> None:
    """As 35 RA dissolvem em 7 Regiões de Saúde — nem 8 (alguma sem região) nem
    35."""
    assert len(regioes_saude) == 7


def test_chave_de_ra_nao_repete(ra: gpd.GeoDataFrame) -> None:
    assert not ra["ra_chave"].duplicated().any()


def test_todas_as_ra_tem_regiao_de_saude(ra: gpd.GeoDataFrame) -> None:
    """Riacho Fundo e SCIA vinham sem Região de Saúde no dado
    (`Regiao_sau1='Ignorado'` sem excessão) — preenchidas em 14/set/2026
    contra fonte oficial da SES-DF (`config.RA_PARA_REGIAO_SAUDE`, ver
    `excecoes.md` §3). Nenhuma RA deveria ficar de fora mais."""
    assert not ra["regiao_saude"].isna().any()


# ---------------------------------------------------------------------------
# Classificação de cor
# ---------------------------------------------------------------------------


def test_escala_natural_cobre_do_minimo_ao_maximo() -> None:
    valores = pd.Series([1, 5, 8, 14, 25, 53, 80])
    escala = mapa.escala_natural(valores, pack.rampa_mapa("casos"))
    assert escala.cortes[0] == 1.0
    assert escala.cortes[-1] == 80.0
    assert len(escala.rotulos) <= mapa.CLASSES


def test_escala_vazia_nao_estoura() -> None:
    escala = mapa.escala_natural(pd.Series([], dtype=float), pack.rampa_mapa("casos"))
    assert escala.rotulos == []
    assert mapa.ROTULO_SEM_DADO in escala.cores


def test_classificar_devolve_sem_dado_para_nulo() -> None:
    valores = pd.Series([1, 10, None])
    escala = mapa.escala_natural(valores, pack.rampa_mapa("casos"))
    classes = mapa.classificar(valores, escala)
    assert classes.iloc[-1] == mapa.ROTULO_SEM_DADO


# ---------------------------------------------------------------------------
# `deck()` — os dois níveis que o app oferece
# ---------------------------------------------------------------------------


@pytest.mark.dado_ra
@pytest.mark.parametrize("metrica", ["casos", "incid", "cura_pct", "abandono_pct"])
def test_deck_monta_por_ra_para_cada_metrica(ra: gpd.GeoDataFrame, metrica: str) -> None:
    valores = mra.valores(ANO, "RA").set_index("chave")[metrica]
    desenho, escala = mapa.deck(
        ra, valores, chave="ra_chave", coluna_nome="ra_nome",
        rampa=pack.rampa_mapa(metrica), rotulo_metrica=pack.rotulo_curto(metrica),
    )

    # JSON **estrito**, como o `JSON.parse` do componente: `NaN` é recusado. Cura e
    # Abandono têm RAs sem taxa, e foi aí que o mapa parou de trocar de cor.
    def recusa(constante: str):
        raise ValueError(f"não é JSON válido: {constante}")

    import json

    assert json.loads(desenho.to_json(), parse_constant=recusa)
    assert escala.rotulos


@pytest.mark.dado_ra
def test_deck_monta_por_regiao_de_saude(regioes_saude: gpd.GeoDataFrame) -> None:
    """Regressão do bug em que `chave == coluna_nome` duplicava a coluna e
    `.map()` quebrava com "first argument must be callable" (corrigido
    11/set/2026)."""
    valores = mra.valores(ANO, "REGIAO_SAUDE").set_index("chave")["casos"]
    desenho, escala = mapa.deck(
        regioes_saude, valores, chave="regiao_saude", coluna_nome="regiao_saude",
        rampa=pack.rampa_mapa("casos"), rotulo_metrica="Casos",
    )
    assert desenho.to_json()
    assert escala.rotulos
