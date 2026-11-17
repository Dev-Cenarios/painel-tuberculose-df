"""Testes dos KPIs — inclui `incid` e `mortalidade`, que dependem dos
parquets opcionais de população e óbitos por TB (ver
`scripts/extrair_populacao_df.py` e `scripts/extrair_obitos_tb_df.py`).
"""

from __future__ import annotations

import pytest

from src.data import config, kpis
from src.data.escopo import Escopo

ANO = config.ANO_MAX_DF


@pytest.fixture(scope="module")
def df() -> Escopo:
    return Escopo(doenca="TUBERCULOSE", ano=ANO)


def test_incid_e_mortalidade_calculados_quando_ha_populacao(df: Escopo) -> None:
    k = kpis.calcular(df)
    assert k.populacao is not None
    assert k.incid is not None
    assert k.mortalidade is not None
    # Incidência de TB por 100 mil não passa de algumas centenas em nenhuma
    # UF brasileira — um valor de milhares indicaria denominador errado
    # (ex.: população de um sexo só). Medido no DF em 2024: ~19.
    assert 0 < k.incid < 500
    assert 0 <= k.mortalidade < 50


def test_incid_bate_com_a_conta_manual(df: Escopo) -> None:
    k = kpis.calcular(df)
    assert k.incid == pytest.approx(k.casos / k.populacao * 100_000)


def test_mortalidade_bate_com_a_conta_manual(df: Escopo) -> None:
    k = kpis.calcular(df)
    assert k.mortalidade == pytest.approx(k.obitos_tb / k.populacao * 100_000)


def test_kpis_sem_populacao_ficam_none_nao_zero(monkeypatch: pytest.MonkeyPatch, df: Escopo) -> None:
    """Um ano sem população extraída não pode virar incidência 0 — 0 diz
    "sem casos", `None` diz "sem denominador". São afirmações diferentes."""
    from src.data import microdado

    monkeypatch.setattr(microdado, "populacao_ano", lambda ano: None)
    k = kpis.calcular(df)
    assert k.incid is None
    assert k.mortalidade is None
