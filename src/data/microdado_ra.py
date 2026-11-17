"""Leitura do microdado geolinkado por RA — a fonte com Região Administrativa por caso.

**Não é a mesma fonte que `microdado.py`.** Aquele lê `silver.tuberculose`
(via `extrair_sinan_df.py`) e sustenta os KPIs de DF inteiro; este lê
`dados_geolink."DF_geo_TB"` (via `extrair_sinan_df_geolink.py`) e é a única
fonte com Região Administrativa por caso. As duas divergem em volume —
667 x 569 notificações em 2024, medido em 11/set/2026 — porque são extrações
diferentes do mesmo SINAN. **Nunca somar ou comparar os dois lado a lado**;
ver README, "Divergência a documentar". Este módulo existe só para o mapa e
o ranking por RA/Região de Saúde — não para reconciliar com o `microdado.py`.

**Incidência por RA — aproximada, não medida ano a ano.** A única
população por RA que existe é do Censo 2022 (`v0001` dos setores
censitários, somado por RA, gravada em `data/geo/ra.parquet` por
`preparar_geometria.py`). Não há série anual por RA como há para o DF
inteiro (`microdado.populacao_ano`, de `pop_ibge`). `populacao_ra()`
estima a população de cada RA num ano qualquer como:

    populacao_DF(ano) × (populacao_censo2022(RA) / populacao_censo2022(DF))

— a **proporção** de cada RA no Censo 2022, aplicada à população anual do
DF inteiro. Pressupõe que a distribuição relativa da população entre RA
não mudou muito entre 2010 e 2024, o que não é verdade em regiões de
expansão urbana recente (Águas Claras, Sol Nascente/Pôr do Sol) — é uma
aproximação, documentada aqui e em `tests/paridade/excecoes.md`, não uma
medição.
"""

from __future__ import annotations

import duckdb
import geopandas as gpd
import pandas as pd

from . import config, microdado
from .microdado import FAIXAS, MESES

#: Mesmo limiar de publicabilidade do `microdado.py` e do RecifeTB.
MINIMO_PARA_PERCENTUAL = 5

#: Confirmação laboratorial, como em `microdado.SQL_PULMONAR_LAB` — a mesma conta
#: nas duas fontes, com o nome da coluna de baciloscopia que esta fonte usa. Com ela
#: a fonte por região reproduz o Boletim a menos de 2% (293 contra 296 em 2024).
SQL_PULMONAR_LAB = (
    "coalesce(forma_clinica LIKE 'Pulmonar%' AND ("
    "baciloscopia_escarro = 'Positiva' OR cultura_escarro = 'Positiva' "
    "OR teste_molecular_rapido LIKE 'Detectavel%'), false)"
)


def _fonte() -> str:
    base = config.dashboard_dir() / "sinan_df_ra"
    if not base.is_dir():
        raise FileNotFoundError(
            f"Dado não encontrado em {base}.\n"
            f"Gere com: python -m scripts.extrair_sinan_df_geolink && "
            f"python -m scripts.preparar_microdado"
        )
    return (base / "**" / "*.parquet").as_posix()


def _conectar() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


def _tabela() -> str:
    """O microdado por região já restrito a **casos novos**, como o Boletim da
    SES-DF os conta (`config.SQL_CASO_NOVO`). Pelo parquet cru só passam a lista de
    anos e a de colunas."""
    return f"(SELECT * FROM read_parquet('{_fonte()}') WHERE {config.SQL_CASO_NOVO})"


def anos_disponiveis() -> list[int]:
    linhas = _conectar().execute(
        f"SELECT DISTINCT ano_notificacao FROM read_parquet('{_fonte()}') ORDER BY 1"
    ).fetchall()
    return [int(linha[0]) for linha in linhas]


#: Nível geográfico do agregado — nomeia a coluna que agrupa e o arquivo de
#: geometria onde a população do Censo 2022 está gravada.
NIVEIS = {
    "RA": ("ra_chave", "ra.parquet"),
    "REGIAO_SAUDE": ("regiao_saude", "regioes_saude.parquet"),
}


def _populacao_censo() -> dict[str, pd.DataFrame]:
    """`{nivel: DataFrame(chave, populacao_censo2022)}` — lido uma vez por
    processo (os parquets de geometria não mudam em runtime)."""
    if not hasattr(_populacao_censo, "_cache"):
        cache = {}
        for nivel, (coluna, arquivo) in NIVEIS.items():
            caminho = config.geo_dir() / arquivo
            if not caminho.is_file():
                continue
            geo = gpd.read_parquet(caminho)
            cache[nivel] = geo[[coluna, "populacao_censo2022"]].rename(
                columns={coluna: "chave"}
            )
        _populacao_censo._cache = cache
    return _populacao_censo._cache


def populacao_ra(ano: int, nivel: str = "RA") -> pd.DataFrame:
    """População estimada de cada RA/Região de Saúde no ano — ver a
    docstring do módulo para o método (proporção do Censo 2022 aplicada à
    população anual do DF). Colunas ``chave`` e ``populacao``.

    Devolve vazio se a geometria (`data/geo/`) ou a população anual do DF
    (`microdado.populacao_ano`) não estiverem disponíveis — sem inventar
    denominador.
    """
    censo = _populacao_censo().get(nivel.upper())
    populacao_df = microdado.populacao_ano(ano)
    if censo is None or censo.empty or populacao_df is None:
        return pd.DataFrame(columns=["chave", "populacao"])

    total_censo = censo["populacao_censo2022"].sum()
    saida = censo.copy()
    saida["populacao"] = (
        saida["populacao_censo2022"] / total_censo * populacao_df
    )
    return saida[["chave", "populacao"]]


def valores(ano: int, nivel: str = "RA") -> pd.DataFrame:
    """Casos novos, cura, abandono e incidência por RA ou por Região de Saúde,
    no ano.

    ``casos`` são casos novos (`config.SQL_CASO_NOVO`); ``cura_pct`` e
    ``abandono_pct`` saem sobre a ``coorte`` do Boletim: os casos novos pulmonares
    com confirmação laboratorial, encerrados ou não.

    Colunas: a coluna geográfica (``ra_chave`` ou ``regiao_saude`` — como
    ``chave``), ``casos``, ``cura_pct``, ``cura_n``, ``abandono_pct``,
    ``abandono_n``, ``coorte``, ``populacao`` e ``incid``. As duas
    últimas vêm nulas quando `populacao_ra()` não tem de onde estimar (ver
    a docstring do módulo — é aproximação, não medição).

    Linhas sem geografia (``ra_chave='IGNORADO'`` ou ``regiao_saude`` nulo)
    ficam fora — não há onde desenhá-las no mapa, e um valor "IGNORADO"
    coloriria um polígono que não existe.

    **Toda RA/Região aparece, mesmo com zero casos no ano.** Sem isso, uma
    RA pequena que zerou (Park Way em 2024: 4 casos em 2020, zero em 2024 —
    plausível para uma população de ~23 mil) simplesmente não teria linha,
    e o mapa pintaria "sem dado" (cinza) em vez do tom mais claro da
    escala — as duas coisas são afirmações diferentes: "não sei" contra
    "sei, e é zero". `casos`/`incid` saem ``0`` de verdade nesse caso;
    `cura_pct`/`abandono_pct` continuam nulos, porque não há como calcular
    uma taxa de cura sobre uma coorte vazia.
    """
    coluna, _ = NIVEIS.get(nivel.upper(), (None, None))
    if coluna is None:
        raise ValueError(f"Nível inválido: {nivel!r}. Esperado {tuple(NIVEIS)}.")

    sql = f"""
        WITH base AS (
            SELECT "{coluna}" AS chave, situacao_encerramento,
                   {SQL_PULMONAR_LAB} AS na_coorte
            FROM {_tabela()}
            WHERE ano_notificacao = ?
              AND "{coluna}" IS NOT NULL AND "{coluna}" <> 'IGNORADO'
        )
        SELECT
            chave,
            count(*) AS casos,
            sum(na_coorte::int) AS coorte,
            sum((na_coorte AND situacao_encerramento = 'Cura')::int) AS cura_n,
            sum((na_coorte AND situacao_encerramento IN ('Abandono', 'Abandono primario'))::int) AS abandono_n
        FROM base
        GROUP BY chave
        ORDER BY casos DESC
    """
    dados = _conectar().execute(sql, [ano]).fetchdf()

    # Completa com zero as RA/Regiões que não têm nenhuma linha no ano —
    # ver a docstring desta função para o porquê. Sem a malha (geometria
    # ausente), não há lista de chaves para completar contra, e o
    # comportamento cai no antigo: só o que teve caso aparece.
    todas = _populacao_censo().get(nivel.upper())
    if todas is not None and not todas.empty:
        dados = todas[["chave"]].merge(dados, on="chave", how="left")
        for col in ("casos", "coorte", "cura_n", "abandono_n"):
            dados[col] = dados[col].fillna(0)
        # O merge não preserva o `ORDER BY casos DESC` da consulta —
        # reordena, para quem lê `valores()` direto (sem passar pelo
        # ranking, que já ordena por conta própria) continuar vendo a RA
        # de mais casos primeiro.
        dados = dados.sort_values("casos", ascending=False).reset_index(drop=True)

    if dados.empty:
        return pd.DataFrame(
            columns=["chave", "casos", "coorte", "cura_n", "abandono_n",
                     "cura_pct", "abandono_pct", "populacao", "incid"]
        )

    def _pct(n, den):
        return (n / den * 100).where(den >= MINIMO_PARA_PERCENTUAL)

    dados["cura_pct"] = _pct(dados["cura_n"], dados["coorte"])
    dados["abandono_pct"] = _pct(dados["abandono_n"], dados["coorte"])

    populacao = populacao_ra(ano, nivel)
    dados = dados.merge(populacao, on="chave", how="left")
    dados["incid"] = (dados["casos"] / dados["populacao"] * 100_000).where(
        dados["populacao"] > 0
    )
    return dados


def total(ano: int, nivel: str = "RA", chave: str | None = None) -> int:
    """Notificações do ano, opcionalmente filtradas a uma RA/Região de Saúde."""
    coluna, _ = NIVEIS.get(nivel.upper(), (None, None))
    if coluna is None:
        raise ValueError(f"Nível inválido: {nivel!r}. Esperado {tuple(NIVEIS)}.")

    onde = "ano_notificacao = ?"
    params: list = [ano]
    if chave is not None:
        onde += f' AND "{coluna}" = ?'
        params.append(chave)

    linha = _conectar().execute(
        f"SELECT count(*) FROM {_tabela()} WHERE {onde}", params
    ).fetchone()
    return int(linha[0]) if linha else 0


def composicao(ano: int, variavel: str, *, nivel: str = "RA", chave: str | None = None) -> pd.DataFrame:
    """Distribuição de uma variável, opcionalmente restrita a uma RA/Região de
    Saúde — mesma forma de `microdado.composicao()` (``categoria``, ``n``,
    ``pct``, ``total``), para o painel de detalhe reaproveitar o mesmo
    gráfico."""
    coluna_geo, _ = NIVEIS.get(nivel.upper(), (None, None))
    if coluna_geo is None:
        raise ValueError(f"Nível inválido: {nivel!r}. Esperado {tuple(NIVEIS)}.")

    colunas = {c.lower() for c in _colunas()}
    if variavel.lower() not in colunas:
        return pd.DataFrame(columns=["categoria", "n", "pct", "total"])

    onde = "ano_notificacao = ?"
    params: list = [ano]
    if chave is not None:
        onde += f' AND "{coluna_geo}" = ?'
        params.append(chave)

    sql = f"""
        SELECT trim("{variavel}") AS categoria, count(*) AS n
        FROM {_tabela()}
        WHERE {onde}
          AND "{variavel}" IS NOT NULL
          AND trim("{variavel}") <> ''
        GROUP BY 1
        ORDER BY n DESC
    """
    dados = _conectar().execute(sql, params).fetchdf()
    if dados.empty:
        return pd.DataFrame(columns=["categoria", "n", "pct", "total"])

    soma = float(dados["n"].sum())
    dados["pct"] = (dados["n"] / soma * 100) if soma >= MINIMO_PARA_PERCENTUAL else pd.NA
    dados["total"] = soma
    return dados[["categoria", "n", "pct", "total"]].reset_index(drop=True)


def _colunas() -> list[str]:
    return [
        linha[0]
        for linha in _conectar().execute(
            f"DESCRIBE SELECT * FROM read_parquet('{_fonte()}')"
        ).fetchall()
    ]


# ---------------------------------------------------------------------------
# Leituras filtradas a uma RA/Região de Saúde — o painel inteiro responde a ela
# ---------------------------------------------------------------------------
# Mesmas formas de dado das leituras do DF inteiro em `microdado.py`, para o
# gráfico não saber de que fonte veio. Quem escolhe a fonte é `painel.py`.


def _coluna(nivel: str) -> str:
    coluna, _ = NIVEIS.get(nivel.upper(), (None, None))
    if coluna is None:
        raise ValueError(f"Nível inválido: {nivel!r}. Esperado {tuple(NIVEIS)}.")
    return coluna


def _regiao(coluna: str, chave: str | None) -> tuple[str, list]:
    """Cláusula e parâmetros do filtro de região. ``chave=None`` é o **DF inteiro**,
    sem filtro algum — inclusive os casos sem RA identificada, que o mapa não tem onde
    desenhar mas o total do DF tem de contar."""
    if chave is None:
        return "TRUE", []
    return f'"{coluna}" = ?', [chave]


def resumo(ano: int, nivel: str, chave: str | None) -> dict[str, int]:
    """Contagens que sustentam os KPIs da RA/Região no ano: ``casos``,
    ``coorte``, ``cura_n``, ``abandono_n``, ``testados_hiv`` e
    ``hiv_pos_n``.

    A coorte é a mesma de :func:`valores` — o card da RA e a cor dela no mapa
    precisam somar a mesma coisa.
    """
    coluna = _coluna(nivel)
    onde, params = _regiao(coluna, chave)
    sql = f"""
        SELECT
            count(*) AS casos,
            coalesce(sum({SQL_PULMONAR_LAB}::int), 0) AS coorte,
            coalesce(sum(({SQL_PULMONAR_LAB} AND situacao_encerramento = 'Cura')::int), 0) AS cura_n,
            coalesce(sum(({SQL_PULMONAR_LAB} AND situacao_encerramento IN ('Abandono', 'Abandono primario'))::int), 0) AS abandono_n,
            coalesce(sum((resultado_hiv IN ('Positivo', 'Negativo'))::int), 0) AS testados_hiv,
            coalesce(sum((resultado_hiv = 'Positivo')::int), 0) AS hiv_pos_n
        FROM {_tabela()}
        WHERE ano_notificacao = ? AND {onde}
    """
    linha = _conectar().execute(sql, [ano, *params]).fetchone()
    nomes = ("casos", "coorte", "cura_n", "abandono_n", "testados_hiv", "hiv_pos_n")
    return {n: int(v or 0) for n, v in zip(nomes, linha, strict=True)}


def populacao_de(ano: int, nivel: str, chave: str | None) -> float | None:
    """População estimada **de uma** RA/Região no ano (ver :func:`populacao_ra`
    para o método), ou ``None`` se não houver como estimar. Sem ``chave``, a do DF
    inteiro: a do Boletim (`microdado.populacao_ano`), sem estimar nada."""
    if chave is None:
        populacao = microdado.populacao_ano(ano)
        return float(populacao) if populacao else None
    pop = populacao_ra(ano, nivel)
    achada = pop.loc[pop["chave"] == chave, "populacao"]
    return float(achada.iloc[0]) if not achada.empty else None


def serie_mensal(ano: int, nivel: str, chave: str | None) -> pd.DataFrame:
    """Notificações por mês do ano na RA/Região. Colunas ``mes``, ``mes_nome`` e
    ``valor`` — os doze meses sempre, inclusive os zerados."""
    coluna = _coluna(nivel)
    onde, params = _regiao(coluna, chave)
    sql = f"""
        WITH m AS (
            SELECT month(dt_notificacao) AS mes
            FROM {_tabela()}
            WHERE ano_notificacao = ? AND {onde}
        )
        SELECT g.mes, count(m.mes) AS valor
        FROM generate_series(1, 12) AS g(mes)
        LEFT JOIN m ON m.mes = g.mes
        GROUP BY g.mes
        ORDER BY g.mes
    """
    dados = _conectar().execute(sql, [ano, *params]).fetchdf()
    dados["mes_nome"] = [MESES[int(m) - 1] for m in dados["mes"]]
    return dados[["mes", "mes_nome", "valor"]]


def serie_anual(nivel: str, chave: str | None) -> pd.DataFrame:
    """Notificações por ano na RA/Região, todo o histórico geolinkado. Colunas
    ``ano`` e ``valor``."""
    coluna = _coluna(nivel)
    onde, params = _regiao(coluna, chave)
    sql = f"""
        SELECT ano_notificacao AS ano, count(*) AS valor
        FROM {_tabela()}
        WHERE {onde}
        GROUP BY 1
        ORDER BY 1
    """
    return _conectar().execute(sql, params).fetchdf()


def casos_por_mes(ano_min: int, ano_max: int, nivel: str, chave: str | None) -> pd.DataFrame:
    """Contagem mensal atravessando os anos, para a epicurva. Colunas ``ano``,
    ``mes`` e ``casos`` — todo mês de todo ano do intervalo, inclusive os zerados
    (uma epicurva que pula o mês liga os vizinhos como se ele não existisse)."""
    coluna = _coluna(nivel)
    onde, params = _regiao(coluna, chave)
    sql = f"""
        WITH m AS (
            SELECT ano_notificacao AS ano, month(dt_notificacao) AS mes
            FROM {_tabela()}
            WHERE ano_notificacao BETWEEN ? AND ? AND {onde}
        )
        SELECT a.ano, g.mes, count(m.mes) AS casos
        FROM generate_series(?, ?) AS a(ano)
        CROSS JOIN generate_series(1, 12) AS g(mes)
        LEFT JOIN m ON m.ano = a.ano AND m.mes = g.mes
        GROUP BY a.ano, g.mes
        ORDER BY a.ano, g.mes
    """
    return _conectar().execute(
        sql, [ano_min, ano_max, *params, ano_min, ano_max]
    ).fetchdf()


def piramide(ano: int, nivel: str, chave: str | None) -> pd.DataFrame:
    """Casos por sexo e faixa etária na RA/Região. Mesmas colunas e faixas de
    `microdado.piramide`: ``sexo`` ("M"/"F"), ``faixa_ord``, ``faixa_etaria``
    e ``valor``."""
    coluna = _coluna(nivel)
    onde, params = _regiao(coluna, chave)
    casos = " ".join(
        f"WHEN idade BETWEEN {ini} AND {fim} THEN {ini}" for ini, fim, _ in FAIXAS
    )
    rotulos = " ".join(f"WHEN {ini} THEN '{rotulo}'" for ini, _, rotulo in FAIXAS)
    sql = f"""
        WITH base AS (
            SELECT trim(sexo) AS sexo, idade_anos AS idade
            FROM {_tabela()}
            WHERE ano_notificacao = ? AND {onde}
        ), faixas AS (
            SELECT sexo, CASE {casos} END AS faixa_ord
            FROM base
            WHERE idade IS NOT NULL AND sexo IN ('Masculino', 'Feminino')
        )
        SELECT sexo, faixa_ord,
               CASE faixa_ord {rotulos} END AS faixa_etaria,
               count(*) AS valor
        FROM faixas
        WHERE faixa_ord IS NOT NULL
        GROUP BY 1, 2
        ORDER BY faixa_ord, sexo
    """
    dados = _conectar().execute(sql, [ano, *params]).fetchdf()
    dados["sexo"] = dados["sexo"].map({"Masculino": "M", "Feminino": "F"})
    return dados


def variavel_presente(variavel: str) -> bool:
    """Se a variável existe nesta fonte. Nove das 30 oferecidas nos tópicos só
    existem em `silver.tuberculose` (ocupação, resistência, TDO...)."""
    return variavel.lower() in {c.lower() for c in _colunas()}
