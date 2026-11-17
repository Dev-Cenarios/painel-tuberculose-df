"""A regra que põe cada caso na RA certa, incluindo as duas criadas em dez/2022.

`atribuir_ra` é uma função pura: rótulo do banco + coordenada + polígonos. Aqui
ela roda sobre caixas sintéticas, sem banco. O que se cobra é a **conservação**:
o rótulo vale, e só passa para a RA nova o caso que é da RA-mãe, com ponto
preciso dentro do polígono novo. Mover caso por coordenada fora disso é o erro
caro — os dados reais têm geocodificação genérica (um ponto com 278 casos).
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from scripts import extrair_sinan_df_geolink as ex
from src.data import config

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def poligonos() -> gpd.GeoDataFrame:
    """Três caixas lado a lado, em graus, como RAs: a mãe grande, a nova dentro
    do que era a mãe, e uma vizinha qualquer."""
    caixas = {
        "PLANALTINA": box(-47.70, -15.70, -47.50, -15.40),
        "ARAPOANGA": box(-47.60, -15.60, -47.55, -15.55),  # dentro da mãe
        "PARANOA": box(-47.50, -15.70, -47.30, -15.40),
    }
    geo = gpd.GeoDataFrame(
        {"chave": list(caixas)}, geometry=list(caixas.values()), crs="EPSG:4326"
    ).to_crs("EPSG:31983")
    # Como no mundo real, a RA nova **recorta** a mãe: o ponto dentro dela não
    # pode também cair na mãe.
    mae = geo.loc[geo["chave"] == "PLANALTINA", "geometry"].iloc[0]
    nova = geo.loc[geo["chave"] == "ARAPOANGA", "geometry"].iloc[0]
    geo.loc[geo["chave"] == "PLANALTINA", "geometry"] = mae.difference(nova)
    return geo


DENTRO_DA_NOVA = (-15.575, -47.575)  # (lat, lon)
DENTRO_DA_MAE = (-15.45, -47.65)
DENTRO_DA_VIZINHA = (-15.55, -47.40)


def _atribuir(casos: list[tuple], poligonos) -> tuple[pd.Series, dict]:
    df = pd.DataFrame(casos, columns=["rotulo", "lat", "lon"])
    return ex.atribuir_ra(df["rotulo"], df["lat"], df["lon"], poligonos)


def test_mae_com_ponto_preciso_na_ra_nova_passa_para_ela(poligonos) -> None:
    resultado, est = _atribuir([("PLANALTINA", *DENTRO_DA_NOVA)], poligonos)
    assert resultado.tolist() == ["ARAPOANGA"]
    assert est["movidos_ARAPOANGA"] == 1


def test_o_rotulo_com_acento_e_caixa_diferentes_tambem_conta(poligonos) -> None:
    resultado, _ = _atribuir([("Planaltina", *DENTRO_DA_NOVA)], poligonos)
    assert resultado.tolist() == ["ARAPOANGA"]


def test_ponto_generico_repetido_nao_move_ninguem(poligonos) -> None:
    """Cinco casos no mesmo ponto é centro de bairro/CEP, não localização — mesmo
    que o ponto caia dentro da RA nova."""
    n = config.PONTO_REPETIDO_MINIMO
    resultado, est = _atribuir([("PLANALTINA", *DENTRO_DA_NOVA)] * n, poligonos)
    assert set(resultado) == {"PLANALTINA"}
    assert est["movidos_ARAPOANGA"] == 0
    assert est["barrados_ponto_repetido"] == n


def test_logo_abaixo_do_limite_de_repeticao_ainda_move(poligonos) -> None:
    n = config.PONTO_REPETIDO_MINIMO - 1
    resultado, _ = _atribuir([("PLANALTINA", *DENTRO_DA_NOVA)] * n, poligonos)
    assert set(resultado) == {"ARAPOANGA"}


def test_rotulo_que_nao_e_a_mae_nao_muda(poligonos) -> None:
    """Um caso rotulado Paranoá com ponto em Arapoanga fica Paranoá: a coordenada
    não é mais confiável que o rótulo fora do desmembramento conhecido."""
    resultado, est = _atribuir([("PARANOA", *DENTRO_DA_NOVA)], poligonos)
    assert resultado.tolist() == ["PARANOA"]
    assert est["movidos_ARAPOANGA"] == 0


def test_ignorado_nao_e_recuperado_por_coordenada(poligonos) -> None:
    """64 dos 105 "sem RA" reais estão num único ponto genérico: a coordenada não
    diz a RA deles."""
    resultado, _ = _atribuir([("IGNORADO", *DENTRO_DA_NOVA)], poligonos)
    assert resultado.tolist() == ["IGNORADO"]


def test_discordancia_fora_do_desmembramento_nao_e_corrigida(poligonos) -> None:
    """Rótulo Planaltina, ponto numa vizinha (Paranoá): fica Planaltina."""
    resultado, _ = _atribuir([("PLANALTINA", *DENTRO_DA_VIZINHA)], poligonos)
    assert resultado.tolist() == ["PLANALTINA"]


def test_mae_com_ponto_fora_da_ra_nova_continua_mae(poligonos) -> None:
    resultado, est = _atribuir([("PLANALTINA", *DENTRO_DA_MAE)], poligonos)
    assert resultado.tolist() == ["PLANALTINA"]
    assert est["rotulo_mae_ponto_fora_da_ra_nova"] == 1


def test_sem_coordenada_vale_o_rotulo(poligonos) -> None:
    resultado, _ = _atribuir([("PLANALTINA", float("nan"), float("nan"))], poligonos)
    assert resultado.tolist() == ["PLANALTINA"]


def test_a_funcao_nao_devolve_coordenada(poligonos) -> None:
    """Sai a chave da RA, texto — nunca a latitude, a longitude ou o ponto.

    A checagem era `dtype == object`, que até o pandas 2 era como texto vinha.
    No pandas 3 texto tem dtype próprio (`str`) e o teste reprovava com a
    função certa; `is_string_dtype` vale nas duas versões, e conferir cada
    valor tira a dúvida de vez."""
    resultado, est = _atribuir([("PLANALTINA", *DENTRO_DA_NOVA)], poligonos)
    assert isinstance(resultado, pd.Series)
    assert pd.api.types.is_string_dtype(resultado), resultado.dtype
    assert all(isinstance(v, str) for v in resultado)
    assert all(isinstance(v, int) for v in est.values())


def test_o_indice_original_e_preservado(poligonos) -> None:
    df = pd.DataFrame(
        {"rotulo": ["PLANALTINA", "GAMA"], "lat": [DENTRO_DA_NOVA[0], DENTRO_DA_MAE[0]],
         "lon": [DENTRO_DA_NOVA[1], DENTRO_DA_MAE[1]]},
        index=[10, 42],
    )
    resultado, _ = ex.atribuir_ra(df["rotulo"], df["lat"], df["lon"], poligonos)
    assert list(resultado.index) == [10, 42]
    assert resultado.tolist() == ["ARAPOANGA", "GAMA"]


def test_a_agua_quente_segue_a_mesma_regra() -> None:
    assert config.RA_MAE["AGUA QUENTE"] == "RECANTO DAS EMAS"
    assert config.RA_PARA_REGIAO_SAUDE["AGUA QUENTE"] == config.RA_PARA_REGIAO_SAUDE["RECANTO DAS EMAS"]
    assert config.RA_PARA_REGIAO_SAUDE["ARAPOANGA"] == config.RA_PARA_REGIAO_SAUDE["PLANALTINA"]


# --- a coordenada nunca atravessa -------------------------------------------------


def test_coordenada_esta_na_lista_de_identificadores_descartados() -> None:
    assert set(ex.COORDENADAS) <= set(ex.IDENTIFICADORES_DESCARTADOS)


def test_coordenada_nao_esta_na_permissao_de_saida() -> None:
    """`COLUNAS_DIRETAS` e `DECODIFICAR` são a lista do que vira coluna de saída."""
    saida = set(ex.COLUNAS_DIRETAS) | set(ex.DECODIFICAR)
    assert not (saida & set(ex.COORDENADAS))


def test_o_nome_do_ipedf_vira_a_chave_de_sempre() -> None:
    from src.data.escopo import chave_ra

    assert chave_ra("SOL NASCENTE E POR DO SOL") == chave_ra("Sol Nascente/Pôr do Sol")
    assert chave_ra("AGUA QUENTE") == "AGUA QUENTE"
    assert chave_ra("NÚCLEO BANDEIRANTE") == "NUCLEO BANDEIRANTE"
