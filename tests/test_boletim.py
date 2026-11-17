"""Séries do Boletim da SES-DF (`src/data/boletim.py`) e a definição de caso novo.

Os valores de referência são os do Boletim "Panorama epidemiológico da
tuberculose no Distrito Federal, 2021 a 2025" (mar/2026). A extração do painel é
outra (outubro/2026, até dez/2024) e não bate número a número: os testes fixam a
**distância tolerada**, para que uma mudança de definição que afaste o painel do
Boletim fique vermelha.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data import boletim, config, microdado, microdado_ra
from src.grafico_boletim import empilhado_100, linhas_por_regiao

#: Casos novos de todas as formas, Tabela 3 do Boletim, "ambos os sexos".
CASOS_NOVOS_BOLETIM = {2021: 314, 2022: 332, 2023: 424, 2024: 475}
#: Pulmonares com confirmação laboratorial, Tabela 1, linha "Distrito Federal".
PULMONAR_LAB_BOLETIM = {2021: 182, 2022: 224, 2023: 262, 2024: 296}


def _perto(valor: float, esperado: float, tolerancia: float) -> bool:
    return abs(valor - esperado) / esperado <= tolerancia


# ---------------------------------------------------------------------------
# Definições
# ---------------------------------------------------------------------------


def test_caso_novo_exclui_reingresso_recidiva_e_transferencia() -> None:
    sql = config.SQL_CASO_NOVO
    assert "'Caso novo'" in sql and "'Nao sabe'" in sql and "'Pos-obito'" in sql
    for fora in ("Reingresso", "Recidiva", "Transferencia"):
        assert fora not in sql
    assert "Mudanca de diagnostico" in sql


def test_populacao_do_boletim_reproduz_o_coeficiente_publicado() -> None:
    """475 casos novos em 2024 sobre a população derivada dá o 14,8 do Boletim."""
    assert round(475 / config.POPULACAO_IPEDF_DERIVADA[2024] * 100_000, 1) == 14.8
    assert round(314 / config.POPULACAO_IPEDF_DERIVADA[2021] * 100_000, 1) == 10.2


@pytest.mark.dado
def test_serie_de_populacao_nao_da_degrau_em_2021() -> None:
    """Antes de 2021 a população é a do IBGE reescalada para continuar a do IPEDF:
    um degrau de ~5% entre 2020 e 2021 faria o canal endêmico ler uma queda de
    incidência que não existe."""
    p2020, p2021 = microdado.populacao_ano(2020), microdado.populacao_ano(2021)
    assert p2020 and p2021
    assert 0 < (p2021 - p2020) / p2020 < 0.012


# ---------------------------------------------------------------------------
# Aderência ao Boletim
# ---------------------------------------------------------------------------


@pytest.mark.dado_ra
@pytest.mark.parametrize("ano", sorted(CASOS_NOVOS_BOLETIM))
def test_casos_novos_por_regiao_perto_do_boletim(ano: int) -> None:
    assert _perto(microdado_ra.total(ano), CASOS_NOVOS_BOLETIM[ano], 0.05)


@pytest.mark.dado_ra
def test_incidencia_pulmonar_do_df_perto_do_boletim() -> None:
    serie = boletim.incidencia_pulmonar_lab()
    df = serie[serie["serie"].astype(str) == boletim.DF].set_index("ano")
    for ano, n in PULMONAR_LAB_BOLETIM.items():
        assert _perto(int(df.loc[ano, "n"]), n, 0.04), ano


@pytest.mark.dado_ra
def test_toda_regiao_tem_linha_em_todo_ano() -> None:
    """Região sem caso no ano não some do `GROUP BY` e fura a linha do gráfico."""
    for serie in (boletim.tdo_por_regiao(), boletim.hiv_por_regiao(), boletim.incidencia_pulmonar_lab()):
        assert len(serie) == (len(boletim.REGIOES) + 1) * len(boletim.anos())


@pytest.mark.dado_ra
def test_distribuicoes_somam_cem_por_ano() -> None:
    for dados in (boletim.sexo(), boletim.faixa_etaria(), boletim.raca_cor(),
                  boletim.escolaridade(), boletim.trm_realizado()):
        soma = dados.groupby("ano")["pct"].sum()
        assert (soma.round(6) == 100).all()


@pytest.mark.dado_ra
def test_escolaridade_nao_perde_categoria_do_campo() -> None:
    """Toda escolaridade do dado cai numa das nove classes do Boletim — nada vaza
    para "Ign/Branco" por grafia diferente (acento, ª)."""
    bruto = microdado_ra._conectar().execute(
        f"SELECT DISTINCT trim(escolaridade) FROM {microdado_ra._tabela()} "
        "WHERE escolaridade IS NOT NULL"
    ).fetchall()
    sem_classe = [v for (v,) in bruto if v not in boletim.ESCOLARIDADE and v != "Ignorado"]
    assert not sem_classe, sem_classe


@pytest.mark.dado_ra
def test_desfecho_por_regiao_fecha_em_cem() -> None:
    ano = boletim.anos()[-1]
    soma = boletim.desfecho_por_regiao(ano).groupby("serie", observed=True)["pct"].sum()
    assert (soma.round(6) == 100).all()


# ---------------------------------------------------------------------------
# Opções de gráfico
# ---------------------------------------------------------------------------


def _linhas() -> pd.DataFrame:
    series = [*boletim.REGIOES, boletim.DF]
    return pd.DataFrame(
        [{"serie": s, "ano": a, "valor": 10.0 + i} for i, s in enumerate(series) for a in (2021, 2022)]
    )


def test_linhas_tem_uma_serie_por_regiao_mais_o_df_tracejado() -> None:
    opt = linhas_por_regiao(_linhas(), rotulo="x")
    assert len(opt["series"]) == len(boletim.REGIOES) + 1
    df = next(s for s in opt["series"] if s["name"] == boletim.DF)
    assert df["lineStyle"]["type"] == "dashed"
    assert opt["legend"].get("type") != "scroll"


def test_destaque_recua_as_outras_regioes() -> None:
    opt = linhas_por_regiao(_linhas(), rotulo="x", destaque="Regiao Leste")
    por_nome = {s["name"]: s for s in opt["series"]}
    assert por_nome["Leste"]["lineStyle"]["opacity"] == 1
    assert por_nome["Norte"]["lineStyle"]["opacity"] < 1
    assert por_nome[boletim.DF]["lineStyle"]["opacity"] == 1


def test_ponto_sem_valor_nao_e_ligado() -> None:
    dados = _linhas().assign(valor=lambda d: d["valor"].where(d["ano"] != 2022))
    opt = linhas_por_regiao(dados, rotulo="x")
    assert all(s["connectNulls"] is False for s in opt["series"])


def test_empilhado_respeita_a_ordem_do_campo_e_nao_a_da_aparicao() -> None:
    ordem = ["Ign/Branco", "Branca", "Amarela", "Parda"]
    dados = pd.DataFrame({
        "ano": [2021, 2021, 2022, 2022, 2022],
        "categoria": pd.Categorical(["Ign/Branco", "Parda", "Ign/Branco", "Amarela", "Parda"],
                                    categories=ordem, ordered=True),
        "pct": [20.0, 80.0, 10.0, 5.0, 85.0],
    })
    opt = empilhado_100(dados, x="ano", cor="#6C5CA8")
    assert [s["name"] for s in opt["series"]] == ["Ign/Branco", "Amarela", "Parda"]
    assert opt["yAxis"]["max"] == 100


def test_empilhado_sem_dado_devolve_recado() -> None:
    opt = empilhado_100(pd.DataFrame(columns=["ano", "categoria", "pct"]), x="ano")
    assert "title" in opt and not opt.get("series")


# ---------------------------------------------------------------------------
# Tópicos de interesse
# ---------------------------------------------------------------------------


def test_topicos_nao_oferecem_tipo_de_entrada() -> None:
    """Entre casos novos o tipo de entrada tem só três valores, quase todos "caso
    novo": o gráfico não diz nada. Fora da abertura e do seletor."""
    from src import doencas

    pack = doencas.carregar()
    assert "tipo_entrada" not in pack.variaveis_planas()
    assert "teste_molecular_rapido" in pack.VARIAVEIS_DESTAQUE


def test_todo_equivalente_no_boletim_e_um_topico_que_existe() -> None:
    from src import doencas

    pack = doencas.carregar()
    assert set(pack.EQUIVALENTE_NO_BOLETIM) <= set(pack.variaveis_planas())


@pytest.mark.dado_ra
def test_tdo_vem_preenchido_no_df_inteiro() -> None:
    """O TDO de `silver.tuberculose` é "Não informado" em todas as linhas; o tópico
    lê a fonte por região mesmo sem região selecionada."""
    from src.data import painel

    dados = painel.composicao(boletim.anos()[-1], "tratamento_diretamente_observado_atual", None)
    assert not dados.empty
    assert "Sim" in set(dados["categoria"])
