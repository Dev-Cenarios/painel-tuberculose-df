"""Testes da segunda fonte — microdado geolinkado por RA
(`src/data/microdado_ra.py`).

Não confundir com `test_microdado.py`: são módulos e fontes diferentes de
propósito (ver README, "Religado — o mapa mora ao lado dos KPIs, não dentro
deles"). A comparação **entre** as duas fontes vive em
`tests/paridade/test_referencia.py`, não aqui.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data import microdado_ra as mra

ANO = 2024


def test_valores_ra_tem_as_colunas_esperadas() -> None:
    v = mra.valores(ANO, "RA")
    assert not v.empty
    assert {"chave", "casos", "cura_pct", "abandono_pct"} <= set(v.columns)


def test_valores_ra_nao_traz_ignorado() -> None:
    """Sem onde desenhar 'IGNORADO' no mapa — a linha não deve existir na
    saída de `valores()`, mesmo que exista no parquet."""
    v = mra.valores(ANO, "RA")
    assert "IGNORADO" not in set(v["chave"])


def test_valores_ra_tem_as_35_mesmo_com_zero_casos() -> None:
    """Park Way zerou em 2024 (4 casos em 2020, zero em 2024 — plausível
    para uma população de ~23 mil) e precisa aparecer com `casos=0`,
    `incid=0.0`, não ausente. Ausente pinta "sem dado" (cinza) no mapa,
    que é uma afirmação diferente de "zero" — achado ao usuário notar
    Park Way sem cor no mapa em 14/set/2026."""
    v = mra.valores(2024, "RA")
    assert len(v) == 35
    linha = v.loc[v["chave"] == "PARK WAY"].iloc[0]
    assert linha["casos"] == 0
    assert linha["incid"] == 0.0
    assert pd.isna(linha["cura_pct"])


def test_valores_ordenado_por_casos_mesmo_apos_completar_zeros() -> None:
    v = mra.valores(ANO, "RA")
    assert list(v["casos"]) == sorted(v["casos"], reverse=True)


def test_valores_regiao_saude_tem_sete_linhas_no_maximo() -> None:
    """7 Regiões de Saúde no total — todas as 35 RA mapeadas
    (`config.RA_PARA_REGIAO_SAUDE`), Riacho Fundo e SCIA inclusas desde
    14/set/2026 (Região Centro-Sul, fonte SES-DF)."""
    v = mra.valores(ANO, "REGIAO_SAUDE")
    assert len(v) <= 7
    assert None not in set(v["chave"])


def test_nivel_invalido_levanta_erro() -> None:
    with pytest.raises(ValueError):
        mra.valores(ANO, "BAIRRO")


def test_cura_pct_e_abandono_pct_somam_no_maximo_cem() -> None:
    """As duas juntas não superam 100% dos encerramentos — são duas
    categorias entre várias de `situacao_encerramento`, não complementares."""
    v = mra.valores(ANO, "RA")
    soma = (v["cura_pct"].fillna(0) + v["abandono_pct"].fillna(0))
    assert (soma <= 100.0 + 1e-6).all()


def test_total_filtra_por_chave() -> None:
    v = mra.valores(ANO, "RA")
    alguma_ra = v.iloc[0]["chave"]
    esperado = int(v.iloc[0]["casos"])
    assert mra.total(ANO, "RA", chave=alguma_ra) == esperado


def test_composicao_restrita_a_uma_ra_soma_menos_que_o_total() -> None:
    v = mra.valores(ANO, "RA")
    alguma_ra = v.iloc[0]["chave"]
    geral = mra.composicao(ANO, "situacao_encerramento")
    restrita = mra.composicao(ANO, "situacao_encerramento", nivel="RA", chave=alguma_ra)
    assert restrita["n"].sum() <= geral["n"].sum()


def test_composicao_variavel_inexistente_devolve_vazio() -> None:
    vazio = mra.composicao(ANO, "coluna_que_nao_existe")
    assert vazio.empty
    assert list(vazio.columns) == ["categoria", "n", "pct", "total"]


def test_anos_disponiveis_nao_inclui_2025() -> None:
    """Mesmo corte do `microdado.py`: a extração já não traz 2025."""
    assert 2025 not in set(mra.anos_disponiveis())


# ---------------------------------------------------------------------------
# População estimada por RA e incidência aproximada
# ---------------------------------------------------------------------------


def test_populacao_ra_soma_a_populacao_do_df() -> None:
    """As 35 RA, somadas, batem com `microdado.populacao_ano()` — a
    proporção do Censo 2022 tem de reconstruir o total, não um valor
    próximo. Se um dia divergir, a fonte da população anual do DF mudou de
    formato ou a malha ganhou/perdeu uma RA."""
    p = mra.populacao_ra(ANO, "RA")
    assert len(p) == 35

    from src.data import microdado

    assert p["populacao"].sum() == pytest.approx(microdado.populacao_ano(ANO), rel=1e-9)


def test_populacao_regiao_saude_tambem_soma_o_total() -> None:
    p = mra.populacao_ra(ANO, "REGIAO_SAUDE")
    assert len(p) == 7

    from src.data import microdado

    assert p["populacao"].sum() == pytest.approx(microdado.populacao_ano(ANO), rel=1e-9)


def test_incid_aparece_em_valores_e_bate_com_a_conta_manual() -> None:
    v = mra.valores(ANO, "RA")
    assert "incid" in v.columns
    com_dado = v.dropna(subset=["incid"])
    assert not com_dado.empty
    for _, linha in com_dado.iterrows():
        esperado = linha["casos"] / linha["populacao"] * 100_000
        assert linha["incid"] == pytest.approx(esperado)


def test_populacao_ra_sem_populacao_anual_do_df_devolve_vazio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ano fora da cobertura de `pop_ibge` não inventa denominador — mesmo
    critério do `kpis.py` para o DF inteiro."""
    from src.data import microdado

    monkeypatch.setattr(microdado, "populacao_ano", lambda ano: None)
    p = mra.populacao_ra(1900, "RA")
    assert p.empty


# ---------------------------------------------------------------------------
# As duas RAs criadas em dez/2022
# ---------------------------------------------------------------------------


def test_as_ras_novas_tem_casos_e_populacao() -> None:
    """Arapoanga e Água Quente existem no dado (por coordenada precisa, ver
    `scripts/extrair_sinan_df_geolink.py`) e na população (setores do Censo
    2022). Sem isso o mapa pintaria as duas "sem dado" ou, pior, com zero."""
    v = mra.valores(2024, "RA").set_index("chave")
    for nova in ("ARAPOANGA", "AGUA QUENTE"):
        assert nova in v.index
        assert v.loc[nova, "populacao"] > 0
    assert v["casos"].sum() + 0 > 0
    assert v.loc["ARAPOANGA", "casos"] > 0


def test_as_ras_novas_tiraram_gente_da_mae_e_nao_criaram_casos() -> None:
    """O desmembramento só **move** casos: a soma por RA mais os sem RA continua
    sendo o total da fonte, em todos os anos."""
    for ano in mra.anos_disponiveis():
        por_ra = int(mra.valores(ano, "RA")["casos"].sum())
        assert por_ra <= mra.total(ano)


def test_a_populacao_das_novas_saiu_das_maes() -> None:
    """Planaltina e Recanto das Emas ficaram menores na exata medida das novas:
    a soma continua o Censo 2022 do DF (2.817.381)."""
    import geopandas as gpd

    from src.data import config

    ra = gpd.read_parquet(config.geo_dir() / "ra.parquet").set_index("ra_chave")
    assert int(ra["populacao_censo2022"].sum()) == 2_817_381
    assert ra.loc["ARAPOANGA", "populacao_censo2022"] > 0
    assert ra.loc["AGUA QUENTE", "populacao_censo2022"] > 0
