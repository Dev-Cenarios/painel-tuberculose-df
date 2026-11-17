"""Leitura do microdado do SINAN do Distrito Federal — uma linha por
notificação.

**É a única camada de dado deste painel**, mesma decisão do `manaustb`. O
RecifeTB tem duas fontes: uma agregada (`incidence`, `sinan_landing`, vindas
do painel nacional) para KPIs, mapa e ranking, e o microdado só para
composição, meses e pirâmide — que o nacional não desce a bairro. Aqui não
existe camada agregada nenhuma: a extração
(`scripts/extrair_sinan_df.py`) lê direto de `silver.tuberculose` e já
entrega uma linha por notificação, deduplicada. Todo elemento da tela — KPI
incluso — sai daqui.

Os valores das colunas já vêm em texto legível (``"Cura"``, ``"Masculino"``,
``"Pulmonar"``) em vez de código do SINAN. Não há `sinan_dict` para
traduzir: a categoria já é o rótulo.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from . import config
from .escopo import Escopo

#: Abaixo disto o percentual não é publicável — proporção sobre poucos
#: registros não é achado, é ruído. Mesmo limiar do RecifeTB e do manaustb.
MINIMO_PARA_PERCENTUAL = 5

#: Faixas da pirâmide etária, iguais às do RecifeTB e do manaustb — quinquênios
#: até 19 anos, décadas daí em diante.
FAIXAS = (
    (0, 4, "0 a 4 anos"),
    (5, 9, "5 a 9 anos"),
    (10, 14, "10 a 14 anos"),
    (15, 19, "15 a 19 anos"),
    (20, 29, "20 a 29 anos"),
    (30, 39, "30 a 39 anos"),
    (40, 49, "40 a 49 anos"),
    (50, 59, "50 a 59 anos"),
    (60, 69, "60 a 69 anos"),
    (70, 79, "70 a 79 anos"),
    (80, 200, "80 anos ou mais"),
)

#: Idade em anos completos a partir de ``idade_notificada`` — mesma regra do
#: manaustb. O campo chega como texto (``"023 ano(s)"``, ``"008 mes(es)"``,
#: ``"005 dia(s)"``); meses e dias viram zero ano completo.
_IDADE_EM_ANOS = r"""
    CASE
        WHEN regexp_matches(trim(idade_notificada), 'ano')
            THEN TRY_CAST(regexp_extract(trim(idade_notificada), '(\d+)', 1) AS INTEGER)
        WHEN regexp_matches(trim(idade_notificada), '(m.s\(es\)|dia\(s\))')
            THEN 0
        ELSE NULL
    END
"""


def _fonte() -> str:
    """Glob do parquet particionado por ano, gerado por
    `scripts/preparar_microdado.py`."""
    base = config.dashboard_dir() / "sinan_df"
    if not base.is_dir():
        raise FileNotFoundError(
            f"Dado não encontrado em {base}.\n"
            f"Gere com: python -m scripts.preparar_microdado"
        )
    return (base / "**" / "*.parquet").as_posix()


def _conectar() -> duckdb.DuckDBPyConnection:
    """Conexão DuckDB nova a cada chamada — dataset pequeno (~9,6 mil linhas),
    mesmo critério do manaustb."""
    return duckdb.connect()


def _tabela() -> str:
    """O microdado já restrito a **casos novos**, como o Boletim da SES-DF os conta
    (`config.SQL_CASO_NOVO`). Toda leitura que sustenta um número do painel passa
    por aqui — pelo parquet cru só passam a lista de anos e a lista de colunas."""
    return f"(SELECT * FROM read_parquet('{_fonte()}') WHERE {config.SQL_CASO_NOVO})"


#: Confirmação laboratorial, na definição do Caderno de Indicadores da TB (a que o
#: Boletim usa): baciloscopia positiva, cultura positiva ou TRM-TB detectável.
#: Conferido contra o Boletim: dá 182 (2021) e 296 (2024) casos pulmonares
#: confirmados — exatamente os da Tabela 1.
SQL_PULMONAR_LAB = (
    "(forma_clinica LIKE 'Pulmonar%' AND ("
    "baciloscopia_diagnostico_1a_amostra = 'Positiva' OR cultura_escarro = 'Positiva' "
    "OR teste_molecular_rapido LIKE 'Detectavel%'))"
)


def _onde(esc: Escopo) -> tuple[str, list]:
    return "ano_notificacao = ?", [esc.ano]


def anos_disponiveis() -> list[int]:
    """Anos com dado no parquet particionado, do mais antigo ao mais recente."""
    fonte = _fonte()
    linhas = _conectar().execute(
        f"SELECT DISTINCT ano_notificacao FROM read_parquet('{fonte}') ORDER BY 1"
    ).fetchall()
    return [int(linha[0]) for linha in linhas]


def total(esc: Escopo) -> int:
    """Notificações no ano do escopo."""
    onde, params = _onde(esc)
    linha = _conectar().execute(
        f"SELECT count(*) FROM {_tabela()} WHERE {onde}", params
    ).fetchone()
    return int(linha[0]) if linha else 0


def composicao(esc: Escopo, variavel: str) -> pd.DataFrame:
    """Distribuição de uma variável do SINAN, com percentual quando cabe.

    Devolve ``categoria``, ``n``, ``pct`` e ``total``. Sem dicionário para
    traduzir: a categoria já chega como texto (ver docstring do módulo).

    ``pct`` vem nulo inteiro quando ``total`` não alcança
    :data:`MINIMO_PARA_PERCENTUAL`.
    """
    colunas = {c.lower() for c in _colunas()}
    if variavel.lower() not in colunas:
        return pd.DataFrame(columns=["categoria", "n", "pct", "total"])

    onde, params = _onde(esc)
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


#: Nomes de mês em minúscula — o gráfico fatia os três primeiros caracteres e
#: capitaliza, então a grafia daqui é a que aparece no eixo.
MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def serie_mensal(esc: Escopo) -> pd.DataFrame:
    """Notificações por mês do ano do escopo. Colunas ``mes``, ``mes_nome`` e
    ``valor``.

    Os doze meses vêm sempre, inclusive os zerados — uma série que pula o mês
    desenha a linha ligando novembro a janeiro como se dezembro não tivesse
    existido.
    """
    onde, params = _onde(esc)
    sql = f"""
        WITH m AS (
            SELECT month(dt_notificacao) AS mes
            FROM {_tabela()}
            WHERE {onde}
        )
        SELECT g.mes, count(m.mes) AS valor
        FROM generate_series(1, 12) AS g(mes)
        LEFT JOIN m ON m.mes = g.mes
        GROUP BY g.mes
        ORDER BY g.mes
    """
    dados = _conectar().execute(sql, params).fetchdf()
    dados["mes_nome"] = [MESES[int(m) - 1] for m in dados["mes"]]
    return dados[["mes", "mes_nome", "valor"]]


def serie_anual() -> pd.DataFrame:
    """Notificações por ano, todo o histórico disponível. Colunas ``ano`` e
    ``valor``."""
    sql = f"""
        SELECT ano_notificacao AS ano, count(*) AS valor
        FROM {_tabela()}
        GROUP BY 1
        ORDER BY 1
    """
    return _conectar().execute(sql).fetchdf()


def piramide(esc: Escopo) -> pd.DataFrame:
    """Casos por sexo e faixa etária no ano do escopo. Colunas ``sexo``,
    ``faixa_ord``, ``faixa_etaria`` e ``valor``.

    Só Masculino e Feminino: ``sexo`` traz uma linha "Ignorado" no dataset
    inteiro — um terceiro lado de um caso não é legível numa pirâmide.

    Sem população nem taxa por 100 mil: a extração do DF não traz denominador
    populacional por faixa etária. `grafico_componente.piramide` já lida com isso — o
    toggle "por 100 mil" só aparece quando a coluna `pop` existe.
    """
    onde, params = _onde(esc)
    casos = " ".join(
        f"WHEN idade BETWEEN {ini} AND {fim} THEN {ini}" for ini, fim, _ in FAIXAS
    )
    rotulos = " ".join(
        f"WHEN {ini} THEN '{rotulo}'" for ini, _, rotulo in FAIXAS
    )
    sql = f"""
        WITH base AS (
            SELECT trim(sexo) AS sexo, {_IDADE_EM_ANOS} AS idade
            FROM {_tabela()}
            WHERE {onde}
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
    dados = _conectar().execute(sql, params).fetchdf()
    # `grafico_componente.piramide` espera "M"/"F" para colorir e posicionar os dois
    # lados.
    dados["sexo"] = dados["sexo"].map({"Masculino": "M", "Feminino": "F"})
    return dados


def populacao_ano(ano: int) -> int | None:
    """População estimada do Distrito Federal no ano, ou `None` se o parquet
    de população não existir ou o ano não tiver linha.

    Série do Boletim (projeções do IPEDF, derivada dos coeficientes que ele publica,
    2021 em diante) continuada para trás pela do IBGE (`public.pop_ibge`), reescalada.
    Ver `config.POPULACAO_IPEDF_DERIVADA`.
    """
    if ano in config.POPULACAO_IPEDF_DERIVADA:
        return config.POPULACAO_IPEDF_DERIVADA[ano]
    ibge = _populacao_ibge(ano)
    if ibge is None or ano > min(config.POPULACAO_IPEDF_DERIVADA):
        return ibge
    # Antes de 2021 o Boletim não tem coeficiente. A série do IBGE continua a do
    # IPEDF **reescalada** pela razão dos dois em 2021: sem isso a população daria
    # um degrau de ~5% entre 2020 e 2021, e o canal endêmico (que compara o ano
    # com os cinco anteriores) leria uma queda de incidência que não existe.
    primeiro = min(config.POPULACAO_IPEDF_DERIVADA)
    base_ibge = _populacao_ibge(primeiro)
    if not base_ibge:
        return ibge
    return round(ibge * config.POPULACAO_IPEDF_DERIVADA[primeiro] / base_ibge)


def _populacao_ibge(ano: int) -> int | None:
    """População do DF no ano em `pop_ibge`, ou `None` sem o parquet ou o ano."""
    caminho = config.populacao_path()
    if not caminho.is_file():
        return None
    linha = _conectar().execute(
        "SELECT populacao FROM read_parquet(?) WHERE ano = ?",
        [caminho.as_posix(), ano],
    ).fetchone()
    return int(linha[0]) if linha else None


def desfecho_coorte(ano: int) -> dict[str, int]:
    """Cura e abandono na coorte do Boletim: casos novos **pulmonares com
    confirmação laboratorial** do ano. ``coorte`` é o denominador — todos os casos
    da coorte, inclusive os ainda sem encerramento, como na Tabela 5 do Boletim
    (que tem a coluna "Ign/Branco")."""
    linha = _conectar().execute(
        f"""
        SELECT count(*),
               coalesce(sum((situacao_encerramento = 'Cura')::int), 0),
               coalesce(sum((situacao_encerramento IN ('Abandono', 'Abandono primario'))::int), 0)
        FROM {_tabela()}
        WHERE ano_notificacao = ? AND {SQL_PULMONAR_LAB}
        """,
        [ano],
    ).fetchone()
    return {"coorte": int(linha[0]), "cura_n": int(linha[1]), "abandono_n": int(linha[2])}


def obitos_tb_ano(ano: int) -> int | None:
    """Óbitos por tuberculose (CID-10 A15–A19) no Distrito Federal no ano, ou
    `None` se o parquet de óbitos não existir.

    Fonte: `public.sim_mortalidade` (SIM/DataSUS), já filtrado por causa e
    município na extração — aqui é só soma por ano. Cobre até
    `config.ANO_MAX_OBITO_DF`; um ano fora dessa faixa sempre soma zero
    porque a extração não trouxe a linha, não porque não houve óbito.
    """
    caminho = config.obitos_tb_path()
    if not caminho.is_file():
        return None
    linha = _conectar().execute(
        "SELECT count(*) FROM read_parquet(?) WHERE ano_obito = ?",
        [caminho.as_posix(), ano],
    ).fetchone()
    return int(linha[0]) if linha else 0


def _colunas() -> list[str]:
    """Colunas presentes no parquet — pedir uma coluna ausente devolveria
    erro de binder em vez de resposta vazia."""
    return [
        linha[0]
        for linha in _conectar().execute(
            f"DESCRIBE SELECT * FROM read_parquet('{_fonte()}')"
        ).fetchall()
    ]
