"""Testes da navegação — bem mais curtos que os do RecifeTB.

Sem mapa, sem RA, sem Região de Saúde dentro da `Navegacao`: o único estado
que ela guarda é o ano. O mapa por RA tem o estado próprio dele
(`st.session_state.detalhe_geo`, em `app.py`) — ver README, "Religado — o
mapa mora ao lado dos KPIs, não dentro deles".
"""

from __future__ import annotations

from src.data import config
from src.estado import Navegacao


def test_comeca_no_ano_maximo() -> None:
    nav = Navegacao()
    assert nav.ano == config.ANO_MAX_DF


def test_trilha_mostra_distrito_federal_e_o_ano() -> None:
    nav = Navegacao(ano=2020)
    trilha = nav.trilha()
    assert "Distrito Federal" in trilha
    assert "2020" in trilha
