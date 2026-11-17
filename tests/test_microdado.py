"""Testes da camada de microdado — a fonte dos KPIs de DF inteiro.

Igual ao manaustb: não há segunda fonte agregada para reconciliar dentro
deste módulo (a segunda fonte, `microdado_ra.py`, é deliberadamente
separada — ver README). O que se confere aqui é que a leitura é honesta:
sem identificador, idade decodificada corretamente, totais que fecham entre
si.
"""

from __future__ import annotations

import pytest

from src.data import config, microdado
from src.data.escopo import Escopo

ANO = config.ANO_MAX_DF


@pytest.fixture(scope="module")
def df() -> Escopo:
    return Escopo(doenca="TUBERCULOSE", ano=ANO)


# ---------------------------------------------------------------------------
# Privacidade — o teste que não pode ficar vermelho
# ---------------------------------------------------------------------------

#: Identificadores nominais que `silver.tuberculose` já não traz, e que a
#: lista de permissão de `scripts/extrair_sinan_df.py` reforça não deixar
#: passar mesmo que a fonte um dia volte a tê-los.
IDENTIFICADORES = (
    "nome_paciente", "nome_mae", "data_nascimento", "cns", "prontuario",
    "cep", "telefone", "logradouro", "numero", "latitude", "longitude",
    "nu_notific", "sk_sinan_tube",
)


def test_nenhum_identificador_no_parquet() -> None:
    presentes = {c.lower() for c in microdado._colunas()}
    vazados = sorted(i for i in IDENTIFICADORES if i.lower() in presentes)
    assert not vazados, (
        f"identificador de paciente no parquet: {vazados}. "
        f"Ver a lista de permissão em scripts/extrair_sinan_df.py."
    )


# ---------------------------------------------------------------------------
# Idade — campo textual composto ("023 ano(s)", "008 mes(es)")
# ---------------------------------------------------------------------------


def test_piramide_decodifica_idade_em_anos(df: Escopo) -> None:
    p = microdado.piramide(df)
    assert not p.empty
    assert p["faixa_ord"].max() <= 80
    assert (p["valor"] > 0).all()


def test_piramide_so_tem_as_faixas_declaradas(df: Escopo) -> None:
    esperadas = {ini for ini, _, _ in microdado.FAIXAS}
    assert set(microdado.piramide(df)["faixa_ord"]) <= esperadas


def test_piramide_so_traz_M_e_F(df: Escopo) -> None:
    """``Ignorado`` existe — poucos registros no dataset inteiro — e um
    terceiro lado de um caso não é pirâmide, é ruído com eixo."""
    assert set(microdado.piramide(df)["sexo"]) <= {"M", "F"}


# ---------------------------------------------------------------------------
# Reconciliação entre leitores
# ---------------------------------------------------------------------------


def test_serie_mensal_soma_o_total(df: Escopo) -> None:
    assert int(microdado.serie_mensal(df)["valor"].sum()) == microdado.total(df)


def test_serie_mensal_traz_os_doze_meses(df: Escopo) -> None:
    s = microdado.serie_mensal(df)
    assert list(s["mes"]) == list(range(1, 13))


def test_serie_anual_cobre_o_ano_do_escopo(df: Escopo) -> None:
    s = microdado.serie_anual()
    assert ANO in set(s["ano"])
    linha = s.loc[s["ano"] == ANO, "valor"].iloc[0]
    assert int(linha) == microdado.total(df)


def test_serie_anual_nao_inclui_2025() -> None:
    """2025 é excluído na extração — situação de encerramento incompleta
    (23,7% "Não informado" contra 2,3% em 2024, medido em 11/set/2026)."""
    s = microdado.serie_anual()
    assert 2025 not in set(s["ano"])


# ---------------------------------------------------------------------------
# Composição
# ---------------------------------------------------------------------------


def test_composicao_situacao_encerramento_tem_categorias_conhecidas(df: Escopo) -> None:
    categorias = set(microdado.composicao(df, "situacao_encerramento")["categoria"])
    assert "Cura" in categorias
    assert "Abandono" in categorias


def test_percentual_fecha_em_cem(df: Escopo) -> None:
    pct = microdado.composicao(df, "resultado_hiv")["pct"].sum()
    assert pct == pytest.approx(100.0, abs=0.01)


def test_variavel_inexistente_devolve_vazio_e_nao_estoura(df: Escopo) -> None:
    vazio = microdado.composicao(df, "nome_paciente")
    assert vazio.empty
    assert list(vazio.columns) == ["categoria", "n", "pct", "total"]


def test_toda_variavel_oferecida_existe_no_microdado() -> None:
    """Mesma regressão que o RecifeTB documenta: oferecer uma variável sem
    coluna por trás entrega painel vazio, e é pior que não oferecer."""
    from src.doencas import tuberculose as pack

    presentes = {c.lower() for c in microdado._colunas()}
    faltando = sorted(v for v in pack.variaveis_planas() if v.lower() not in presentes)
    assert not faltando, (
        f"variáveis oferecidas sem coluna no parquet: {faltando}."
    )


def test_altura_do_grafico_cresce_com_as_categorias() -> None:
    from src import grafico_componente

    alturas = [grafico_componente.altura_composicao(n) for n in (3, 4, 5, 11)]
    assert alturas == sorted(alturas)
    for anterior, seguinte in zip(alturas, alturas[1:], strict=False):
        assert seguinte > anterior


# ---------------------------------------------------------------------------
# População e óbitos por TB — denominador/numerador de incid/mortalidade
# ---------------------------------------------------------------------------


def test_populacao_ano_plausivel_para_df() -> None:
    """~2,9-3,0 milhões de habitantes em 2024 — a ordem de grandeza real do
    Distrito Federal, não um erro de soma dobrada (sexo) ou de filtro de
    município."""
    pop = microdado.populacao_ano(2024)
    assert pop is not None
    assert 2_500_000 < pop < 3_500_000


def test_populacao_ano_sem_dado_devolve_none() -> None:
    """Ano fora da cobertura de `pop_ibge` (2010–2025) não inventa número."""
    assert microdado.populacao_ano(1999) is None


def test_obitos_tb_ano_plausivel_para_df() -> None:
    """Entre 10 e 100 óbitos/ano é a faixa observada na extração real
    (`scripts/extrair_obitos_tb_df.py`) para os anos recentes — medido: 40
    em 2024."""
    obitos = microdado.obitos_tb_ano(ANO)
    assert obitos is not None
    assert 10 <= obitos <= 100


def test_obitos_tb_ano_fora_da_cobertura_e_zero_nao_none() -> None:
    """Diferente de população: o parquet de óbitos existe, só não tem linha
    para um ano sem cobertura — soma vazia é 0, não ausência de fonte."""
    assert microdado.obitos_tb_ano(1900) == 0
