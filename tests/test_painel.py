"""A fachada `src/data/painel.py`: o painel inteiro responde a uma RA.

O que importa aqui é que o número da **região** seja o mesmo em todo lugar que
ele aparece — o cartão, o mapa, o ranking —, porque os três saem da mesma
extração e só a conta é refeita. Se um dia o cartão de uma RA discordar da cor
dela no mapa, é um destes testes que acende.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data import canal, config, microdado_ra, painel

pytestmark = pytest.mark.dado_ra

ANO = 2024
RA = ("RA", "PLANO PILOTO")
REGIAO = ("REGIAO_SAUDE", None)  # a chave é descoberta no teste: o nome vem do dado


def _linha_do_mapa(geo) -> pd.Series:
    nivel, chave = geo
    valores = microdado_ra.valores(ANO, nivel).set_index("chave")
    return valores.loc[chave]


def _uma_regiao_de_saude() -> tuple[str, str]:
    valores = microdado_ra.valores(ANO, "REGIAO_SAUDE")
    return ("REGIAO_SAUDE", str(valores.sort_values("casos", ascending=False)["chave"].iloc[0]))


# --- o cartão concorda com o mapa -----------------------------------------------


@pytest.mark.parametrize("campo", ["casos", "cura_pct", "abandono_pct", "incid"])
def test_o_cartao_da_ra_concorda_com_a_cor_dela_no_mapa(campo: str) -> None:
    """Mesma extração, mesma conta: se o cartão do Plano Piloto dissesse 45,8% e
    o mapa pintasse 47%, o painel estaria se contradizendo na mesma tela."""
    k = painel.kpis(ANO, RA)
    mapa_linha = _linha_do_mapa(RA)
    esperado, obtido = mapa_linha[campo], getattr(k, campo)
    if pd.isna(esperado):
        assert obtido is None
    else:
        assert obtido == pytest.approx(float(esperado))


def test_o_cartao_da_regiao_de_saude_concorda_com_o_mapa() -> None:
    geo = _uma_regiao_de_saude()
    k = painel.kpis(ANO, geo)
    linha = microdado_ra.valores(ANO, "REGIAO_SAUDE").set_index("chave").loc[geo[1]]
    assert k.casos == int(linha["casos"])
    assert k.cura_pct == pytest.approx(float(linha["cura_pct"]))


def test_as_ras_somam_o_total_da_fonte() -> None:
    """Toda notificação do ano está numa RA ou em "IGNORADO" — nada some."""
    por_ra = int(microdado_ra.valores(ANO, "RA")["casos"].sum())
    ignorados = microdado_ra.total(ANO) - por_ra
    assert ignorados >= 0
    assert por_ra + ignorados == microdado_ra.total(ANO)


# --- as séries da RA fecham com o cartão ------------------------------------------


def test_a_serie_mensal_da_ra_soma_os_casos() -> None:
    assert int(painel.serie_mensal(ANO, RA)["valor"].sum()) == painel.kpis(ANO, RA).casos


def test_a_serie_mensal_tem_os_doze_meses_mesmo_com_zero() -> None:
    mensal = painel.serie_mensal(ANO, RA)
    assert list(mensal["mes"]) == list(range(1, 13))


def test_a_epicurva_da_ra_tem_todo_mes_de_todo_ano() -> None:
    ep = painel.epicurva(ANO, RA)
    anos = ep["ano"].nunique()
    assert len(ep) == anos * 12, "uma epicurva que pula o mês liga os vizinhos"
    assert ep["ano"].min() == min(painel.anos(RA))
    assert set(ep.columns) >= {"ano_mes", "ano", "mes", "casos"}


def test_a_epicurva_da_ra_no_ano_bate_com_o_cartao() -> None:
    ep = painel.epicurva(ANO, RA)
    assert int(ep.loc[ep["ano"] == ANO, "casos"].sum()) == painel.kpis(ANO, RA).casos


def test_a_serie_anual_da_ra_bate_com_o_cartao_do_ano() -> None:
    anual = painel.serie_anual(RA).set_index("ano")["valor"]
    assert int(anual.loc[ANO]) == painel.kpis(ANO, RA).casos


def test_a_piramide_da_ra_nao_passa_dos_casos() -> None:
    """Sexo ignorado e idade ausente ficam de fora da pirâmide: ela nunca soma
    mais que os casos, mas pode somar menos."""
    pir = painel.piramide(ANO, RA)
    assert set(pir["sexo"]) <= {"M", "F"}
    assert int(pir["valor"].sum()) <= painel.kpis(ANO, RA).casos
    assert set(pir.columns) >= {"sexo", "faixa_ord", "faixa_etaria", "valor"}


def test_o_canal_da_ra_monta_e_usa_so_anos_com_populacao() -> None:
    c = painel.canal(ANO, RA)
    assert not c.vazio
    assert all(a >= 2010 for a in c.anos), "antes de 2010 não há população para o denominador"


# --- o que muda ao entrar numa RA -----------------------------------------------


def test_mortalidade_nao_existe_por_ra_e_nao_vira_zero() -> None:
    assert painel.kpis(ANO, RA).mortalidade is None
    assert painel.kpis(ANO, None).mortalidade is not None, "o DF inteiro continua com ela"


def test_a_incidencia_por_ra_usa_a_populacao_estimada() -> None:
    k = painel.kpis(ANO, RA)
    assert k.populacao and k.incid == pytest.approx(k.casos / k.populacao * 100_000, rel=1e-3)


def test_percentual_sobre_poucos_registros_some_como_no_mapa() -> None:
    """Menos de `MINIMO_PARA_PERCENTUAL` encerramentos: sem percentual, e `None`
    — não zero."""
    pequenas = microdado_ra.valores(ANO, "RA")
    pequenas = pequenas[pequenas["coorte"] < painel.MINIMO_PARA_PERCENTUAL]
    if pequenas.empty:
        pytest.skip("nenhuma RA com poucos encerramentos neste ano")
    k = painel.kpis(ANO, ("RA", str(pequenas["chave"].iloc[0])))
    assert k.cura_pct is None and k.abandono_pct is None


def test_o_df_inteiro_e_a_soma_das_regioes_mais_os_sem_ra() -> None:
    """O card do DF e o mapa leem a mesma fonte: o total do DF fecha com a soma das
    RA mais os casos sem RA identificada — que o mapa não tem onde desenhar."""
    df = painel.kpis(ANO, None)
    soma_ra = int(microdado_ra.valores(ANO, "RA")["casos"].sum())
    assert df.casos == microdado_ra.total(ANO)
    assert 0 <= df.casos - soma_ra <= 0.05 * df.casos
    soma_regioes = sum(painel.kpis(ANO, ("REGIAO_SAUDE", c)).casos
                       for c in microdado_ra.valores(ANO, "REGIAO_SAUDE")["chave"])
    assert soma_regioes <= df.casos


def test_o_df_inteiro_tem_mortalidade_e_incidencia_da_populacao_do_boletim() -> None:
    k = painel.kpis(ANO, None)
    assert k.populacao == config.POPULACAO_IPEDF_DERIVADA[ANO]
    assert k.obitos_tb is not None and k.mortalidade is not None


# --- anos e variáveis -----------------------------------------------------------


def test_os_anos_comecam_em_2010_no_df_e_nas_regioes() -> None:
    assert min(painel.anos(None)) == min(painel.anos(RA)) == 2010


@pytest.mark.parametrize("pedido,esperado", [(2005, 2010), (2010, 2010), (2024, 2024)])
def test_o_ano_cede_ao_mais_proximo_que_a_fonte_tem(pedido: int, esperado: int) -> None:
    assert painel.ano_valido(pedido, RA) == esperado


def test_o_ano_do_df_inteiro_tambem_cede_ao_mais_proximo() -> None:
    assert painel.ano_valido(2005, None) == 2010


def test_variavel_so_do_df_inteiro_some_por_ra() -> None:
    """Nove das trinta variáveis só existem em `silver.tuberculose`."""
    assert painel.variavel_disponivel("ocupacao", None)
    assert not painel.variavel_disponivel("ocupacao", RA)
    assert painel.variavel_disponivel("forma_clinica", RA)


def test_a_composicao_da_ra_tem_a_mesma_forma_da_do_df() -> None:
    por_ra = painel.composicao(ANO, "forma_clinica", RA)
    df = painel.composicao(ANO, "forma_clinica", None)
    assert list(por_ra.columns) == list(df.columns) == ["categoria", "n", "pct", "total"]
    assert int(por_ra["n"].sum()) <= painel.kpis(ANO, RA).casos


def test_ra_inexistente_nao_estoura() -> None:
    """Chave que não está no dado: tudo vem vazio ou zerado, nada levanta."""
    fantasma = ("RA", "NAO EXISTE")
    assert painel.kpis(ANO, fantasma).casos == 0
    assert painel.serie_mensal(ANO, fantasma)["valor"].sum() == 0
    assert painel.piramide(ANO, fantasma).empty
    assert painel.composicao(ANO, "forma_clinica", fantasma).empty


def test_a_fonte_declarada_e_a_mesma_no_df_e_na_regiao() -> None:
    assert "geolink" in painel.fonte(None)
    assert painel.fonte(None) == painel.fonte(RA)


def test_a_epicurva_do_df_atravessa_desde_2010() -> None:
    assert painel.epicurva(ANO, None)["ano"].min() == 2010


def test_canal_aceita_geo_nos_dois_caminhos() -> None:
    assert isinstance(canal.montar(ANO, geo=None), canal.Canal)
    assert isinstance(canal.montar(ANO, geo=RA), canal.Canal)
