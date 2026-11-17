"""Séries do Boletim da SES-DF (Gevist/Divep/SVS, mar/2026), por Região de Saúde.

O painel passou a desenhar, além do mapa e dos tópicos, os gráficos do Boletim
"Panorama epidemiológico da tuberculose no Distrito Federal": a mesma pergunta,
a mesma coorte e a mesma divisão (as sete Regiões de Saúde mais o DF), para que
quem lê um e outro encontre o mesmo número no mesmo gráfico. Este módulo calcula
as séries; `grafico_componente` as desenha.

**Fonte: a extração por região** (`microdado_ra`), e não a do DF inteiro — só ela
sabe a Região de Saúde de cada caso. O "Distrito Federal" de cada série sai dela
também (todos os casos, inclusive os sem região), para a linha do DF e as das
regiões saírem da mesma conta.

**Coortes, como no Boletim:**

- *casos novos* — `config.SQL_CASO_NOVO`, em tudo;
- *pulmonares com confirmação laboratorial* — incidência (Gráfico 1), TDO
  (Gráfico 3), contatos (Gráfico 6) e desfecho (Gráfico 7);
- *pulmonares* — proporção que fez o TRM (Gráfico 2).

**O que não é possível, e fica de fora:**

- 2025: a extração do banco termina em dez/2024, e o Boletim vai até 2025;
- mortalidade por região (Gráfico 9): o SIM não traz a região;
- incidência na população privada de liberdade (Gráfico 10): falta o
  denominador (estimativas da Secretaria Nacional de Políticas Penais).

A incidência por região usa a população estimada pela proporção do Censo 2022
(`microdado_ra.populacao_ra`), como o mapa: o Boletim usa projeções do IPEDF por
região, que não temos.
"""

from __future__ import annotations

import pandas as pd

from . import microdado, microdado_ra

#: O Boletim começa em 2021; a série aqui acompanha, até o último ano da fonte.
ANO_INICIAL = 2021

DF = "Distrito Federal"

#: As sete Regiões de Saúde, na ordem em que o Boletim as lista (alfabética).
REGIOES = (
    "Regiao Central", "Regiao Centro-Sul", "Regiao Leste", "Regiao Norte",
    "Regiao Oeste", "Regiao Sudoeste", "Regiao Sul",
)

#: Corte de publicabilidade — o mesmo de todo o painel.
MINIMO = microdado_ra.MINIMO_PARA_PERCENTUAL

_PULMONAR = "coalesce(forma_clinica LIKE 'Pulmonar%', false)"
_PULMONAR_LAB = microdado_ra.SQL_PULMONAR_LAB
_COM_TRM = (
    "teste_molecular_rapido IN ('Detectavel sensivel a Rifampicina', "
    "'Detectavel resistente a Rifampicina', 'Nao detectavel', 'Inconclusivo')"
)
_TDO = "tratamento_diretamente_observado_atual = 'Sim'"


def rotulo(regiao: str) -> str:
    """``"Regiao Centro-Sul"`` -> ``"Centro-Sul"``."""
    return regiao.removeprefix("Regiao ")


def anos() -> list[int]:
    return [a for a in microdado_ra.anos_disponiveis() if a >= ANO_INICIAL]


def _consultar(sql: str, params: list | None = None) -> pd.DataFrame:
    return microdado_ra._conectar().execute(sql, params or []).fetchdf()


def _por_serie(numerador: str, denominador: str) -> pd.DataFrame:
    """Proporção ``numerador / denominador`` (em %) por ano, em cada Região de
    Saúde e no DF. Colunas ``serie``, ``ano``, ``n``, ``total`` e ``valor``.

    Sem valor (``NaN``) quando o denominador é zero — uma região sem casos na
    coorte no ano não tem proporção, e desenhar zero afirmaria outra coisa. Com
    denominador pequeno o valor existe, como no Boletim, mas o ``total`` vai junto
    para o tooltip dizer sobre quantos casos ele foi calculado.
    """
    corpo = f"""
        count(*) FILTER (WHERE {denominador}) AS total,
        count(*) FILTER (WHERE {denominador} AND {numerador}) AS n
        FROM {microdado_ra._tabela()}
        WHERE ano_notificacao >= {ANO_INICIAL}
    """
    regioes = _consultar(
        f"SELECT ano_notificacao AS ano, regiao_saude AS serie, {corpo} "
        f"AND regiao_saude IS NOT NULL GROUP BY 1, 2"
    )
    df = _consultar(f"SELECT ano_notificacao AS ano, '{DF}' AS serie, {corpo} GROUP BY 1")
    saida = pd.concat([regioes, df], ignore_index=True)
    saida["valor"] = (saida["n"] / saida["total"] * 100).where(saida["total"] > 0)
    return _completar(saida, ["serie", "ano"], ("n", "total"))


def _completar(dados: pd.DataFrame, chaves: list[str], zeros: tuple[str, ...]) -> pd.DataFrame:
    """Garante uma linha para cada série em cada ano: região sem nenhum caso no ano
    não aparece no ``GROUP BY``, e a linha dela no gráfico furaria. As contagens
    viram zero; o ``valor`` continua ausente."""
    series = [*REGIOES, DF]
    grade = pd.MultiIndex.from_product([series, anos()], names=chaves).to_frame(index=False)
    saida = grade.merge(dados, on=chaves, how="left")
    for coluna in zeros:
        saida[coluna] = saida[coluna].fillna(0).astype(int)
    saida["serie"] = pd.Categorical(saida["serie"], categories=series, ordered=True)
    return saida.sort_values(["serie", "ano"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Incidência — Gráfico 1 e Tabela 1
# ---------------------------------------------------------------------------


def incidencia_pulmonar_lab() -> pd.DataFrame:
    """Gráfico 1: coeficiente de incidência (por 100 mil) de tuberculose pulmonar
    com confirmação laboratorial, por Região de Saúde e DF. Colunas ``serie``,
    ``ano``, ``n`` e ``valor``. A população de cada região é estimada (ver o
    docstring do módulo); a do DF é a do Boletim."""
    casos = _consultar(
        f"""
        SELECT ano_notificacao AS ano, regiao_saude AS serie, count(*) AS n
        FROM {microdado_ra._tabela()}
        WHERE ano_notificacao >= {ANO_INICIAL} AND {_PULMONAR_LAB}
          AND regiao_saude IS NOT NULL
        GROUP BY 1, 2
        """
    )
    df = _consultar(
        f"""
        SELECT ano_notificacao AS ano, '{DF}' AS serie, count(*) AS n
        FROM {microdado_ra._tabela()}
        WHERE ano_notificacao >= {ANO_INICIAL} AND {_PULMONAR_LAB}
        GROUP BY 1
        """
    )
    saida = _completar(pd.concat([casos, df], ignore_index=True), ["serie", "ano"], ("n",))

    populacao = {}
    for ano in anos():
        regioes = microdado_ra.populacao_ra(ano, "REGIAO_SAUDE").set_index("chave")["populacao"]
        populacao.update({(s, ano): p for s, p in regioes.items()})
        populacao[(DF, ano)] = microdado.populacao_ano(ano)
    chaves = list(zip(saida["serie"].astype(str), saida["ano"], strict=True))
    saida["populacao"] = [populacao.get(k) for k in chaves]
    saida["valor"] = saida["n"] / saida["populacao"] * 100_000
    return saida[["serie", "ano", "n", "valor"]]


# ---------------------------------------------------------------------------
# Diagnóstico e tratamento — Gráficos 2, 3 e 6
# ---------------------------------------------------------------------------


def trm_realizado() -> pd.DataFrame:
    """Gráfico 2: dos casos novos pulmonares, quem fez o teste rápido molecular.
    Colunas ``ano``, ``categoria`` ("Realizou", "Não realizou", "Ign/Branco"),
    ``n``, ``total`` e ``pct`` — só o DF, como o Boletim."""
    dados = _consultar(
        f"""
        SELECT ano_notificacao AS ano,
               CASE WHEN {_COM_TRM} THEN 'Realizou'
                    WHEN teste_molecular_rapido = 'Nao realizado' THEN 'Não realizou'
                    ELSE 'Ign/Branco' END AS categoria,
               count(*) AS n
        FROM {microdado_ra._tabela()}
        WHERE ano_notificacao >= {ANO_INICIAL} AND {_PULMONAR}
        GROUP BY 1, 2
        """
    )
    return _em_percentual(dados, ["Realizou", "Não realizou", "Ign/Branco"])


def tdo_por_regiao() -> pd.DataFrame:
    """Gráfico 3: proporção dos casos novos pulmonares com confirmação laboratorial
    que fizeram o tratamento diretamente observado. Colunas de :func:`_por_serie`."""
    return _por_serie(_TDO, _PULMONAR_LAB)


def contatos_examinados() -> pd.DataFrame:
    """Gráfico 6: contatos examinados sobre identificados, entre os casos novos
    pulmonares com confirmação laboratorial. Colunas ``serie``, ``ano``, ``n``
    (examinados), ``total`` (identificados) e ``valor`` (%)."""
    corpo = f"""
        coalesce(sum(contatos_examinados), 0) AS n,
        coalesce(sum(contatos_identificados), 0) AS total
        FROM {microdado_ra._tabela()}
        WHERE ano_notificacao >= {ANO_INICIAL} AND {_PULMONAR_LAB}
    """
    regioes = _consultar(
        f"SELECT ano_notificacao AS ano, regiao_saude AS serie, {corpo} "
        f"AND regiao_saude IS NOT NULL GROUP BY 1, 2"
    )
    df = _consultar(f"SELECT ano_notificacao AS ano, '{DF}' AS serie, {corpo} GROUP BY 1")
    saida = pd.concat([regioes, df], ignore_index=True)
    saida["n"] = saida["n"].astype(int)
    saida["total"] = saida["total"].astype(int)
    saida["valor"] = (saida["n"] / saida["total"] * 100).where(saida["total"] > 0)
    return _completar(saida, ["serie", "ano"], ("n", "total"))


# ---------------------------------------------------------------------------
# Perfil — Tabelas 2 e 4, Gráficos 4 e 5
# ---------------------------------------------------------------------------

_FAIXAS = (
    (0, 4, "0-4"), (5, 9, "5-9"), (10, 14, "10-14"), (15, 19, "15-19"),
    (20, 34, "20-34"), (35, 49, "35-49"), (50, 64, "50-64"), (65, 79, "65-79"),
    (80, 200, "80 e+"),
)

#: As faixas do Boletim são desiguais (a de 20 a 34 tem 15 anos); não são as
#: do `microdado.FAIXAS` da pirâmide.
ESCOLARIDADE = {
    "Analfabeto": "Analfabeto",
    "1ª a 4ª série incompleta do EF": "Ensino fundamental incompleto",
    "4ª série completa do EF (antigo 1º grau)": "Ensino fundamental incompleto",
    "5ª a 8ª série incompleta do EF (antigo ginásio/1º grau)": "Ensino fundamental incompleto",
    "Ensino fundamental completo": "Ensino fundamental completo",
    "Ensino médio incompleto": "Ensino médio incompleto",
    "Ensino médio completo": "Ensino médio completo",
    "Educação superior incompleta": "Educação superior incompleta",
    "Educação superior completa": "Educação superior completa",
    "Não se aplica": "Não se aplica",
}
_ORDEM_ESCOLARIDADE = [
    "Ign/Branco", "Analfabeto", "Ensino fundamental incompleto",
    "Ensino fundamental completo", "Ensino médio incompleto", "Ensino médio completo",
    "Educação superior incompleta", "Educação superior completa", "Não se aplica",
]
_ORDEM_RACA = ["Ign/Branco", "Branca", "Preta", "Amarela", "Parda", "Indígena"]


def _em_percentual(dados: pd.DataFrame, ordem: list[str]) -> pd.DataFrame:
    """Soma 100% por ano. Colunas ``ano``, ``categoria``, ``n``, ``total``, ``pct``,
    na ordem de ``ordem`` (que é a do campo, não a da frequência)."""
    if dados.empty:
        return pd.DataFrame(columns=["ano", "categoria", "n", "total", "pct"])
    dados = dados.copy()
    dados["total"] = dados.groupby("ano")["n"].transform("sum")
    dados["pct"] = dados["n"] / dados["total"] * 100
    dados["categoria"] = pd.Categorical(dados["categoria"], categories=ordem, ordered=True)
    return dados.sort_values(["ano", "categoria"]).reset_index(drop=True)


def _distribuicao(expressao: str, ordem: list[str], onde: str = "TRUE") -> pd.DataFrame:
    dados = _consultar(
        f"""
        SELECT ano_notificacao AS ano, {expressao} AS categoria, count(*) AS n
        FROM {microdado_ra._tabela()}
        WHERE ano_notificacao >= {ANO_INICIAL} AND {onde}
        GROUP BY 1, 2
        """
    )
    return _em_percentual(dados, ordem)


def sexo() -> pd.DataFrame:
    """Tabela 2: proporção de casos novos por sexo."""
    return _distribuicao(
        "CASE WHEN sexo IN ('Masculino', 'Feminino') THEN sexo ELSE 'Ign/Branco' END",
        ["Masculino", "Feminino", "Ign/Branco"],
    )


def faixa_etaria() -> pd.DataFrame:
    """Tabela 4: proporção de casos novos por faixa etária (as faixas do Boletim)."""
    casos = " ".join(
        f"WHEN idade_anos BETWEEN {a} AND {b} THEN '{r}'" for a, b, r in _FAIXAS
    )
    return _distribuicao(
        f"CASE {casos} ELSE 'Ign/Branco' END",
        [r for _, _, r in _FAIXAS] + ["Ign/Branco"],
        onde="idade_anos IS NOT NULL",
    )


def raca_cor() -> pd.DataFrame:
    """Gráfico 4: proporção de casos novos por raça/cor."""
    return _distribuicao(
        "CASE WHEN raca_cor IN ('Branca', 'Preta', 'Amarela', 'Parda') THEN raca_cor "
        "WHEN raca_cor LIKE 'Ind%' THEN 'Indígena' ELSE 'Ign/Branco' END",
        _ORDEM_RACA,
    )


def escolaridade() -> pd.DataFrame:
    """Gráfico 5: proporção de casos novos por escolaridade, nas nove classes do
    Boletim (as séries do fundamental agrupadas em "incompleto")."""
    casos = " ".join(
        f"WHEN trim(escolaridade) = '{k}' THEN '{v}'" for k, v in ESCOLARIDADE.items()
    )
    dados = _distribuicao(f"CASE {casos} ELSE 'Ign/Branco' END", _ORDEM_ESCOLARIDADE)
    return dados


# ---------------------------------------------------------------------------
# Desfecho — Tabela 5 e Gráfico 7
# ---------------------------------------------------------------------------

#: Desfechos, na ordem de empilhamento do Boletim (de baixo para cima). Os que o
#: Boletim não separa — TB-DR, falência, mudança de esquema — ficam em "Outros".
DESFECHOS = [
    "Cura", "Abandono", "Óbito por tuberculose", "Óbito por outras causas",
    "Transferência", "Abandono primário", "Outros", "Ign/Branco",
]
_ROTULO_DESFECHO = {
    "Cura": "Cura", "Abandono": "Abandono",
    "Obito por TB": "Óbito por tuberculose",
    "Obito por outras causas": "Óbito por outras causas",
    "Transferencia": "Transferência", "Abandono primario": "Abandono primário",
    "TB-DR": "Outros", "Falencia": "Outros", "Mudanca de esquema": "Outros",
}


def desfecho_por_regiao(ano: int) -> pd.DataFrame:
    """Gráfico 7: situação de encerramento dos casos novos pulmonares com
    confirmação laboratorial, por Região de Saúde e DF, no ano. Colunas ``serie``,
    ``categoria``, ``n``, ``total`` e ``pct``. Casos ainda sem encerramento entram
    como "Ign/Branco" — é o que torna o último ano um piso, e o texto do app diz."""
    casos = " ".join(f"WHEN situacao_encerramento = '{k}' THEN '{v}'" for k, v in _ROTULO_DESFECHO.items())
    base = f"""
        SELECT {{serie}} AS serie,
               CASE {casos} ELSE 'Ign/Branco' END AS categoria, count(*) AS n
        FROM {microdado_ra._tabela()}
        WHERE ano_notificacao = ? AND {_PULMONAR_LAB} {{extra}}
        GROUP BY 1, 2
    """
    regioes = _consultar(
        base.format(serie="regiao_saude", extra="AND regiao_saude IS NOT NULL"), [ano]
    )
    df = _consultar(base.format(serie=f"'{DF}'", extra=""), [ano])
    dados = pd.concat([regioes, df], ignore_index=True)
    if dados.empty:
        return pd.DataFrame(columns=["serie", "categoria", "n", "total", "pct"])
    dados["total"] = dados.groupby("serie")["n"].transform("sum")
    dados["pct"] = dados["n"] / dados["total"] * 100
    dados["categoria"] = pd.Categorical(dados["categoria"], categories=DESFECHOS, ordered=True)
    dados["serie"] = pd.Categorical(dados["serie"], categories=[*REGIOES, DF], ordered=True)
    return dados.sort_values(["serie", "categoria"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Coinfecção TB-HIV — Gráfico 8 e Tabela 6
# ---------------------------------------------------------------------------


def hiv_testagem() -> pd.DataFrame:
    """Gráfico 8: proporção de casos novos que fizeram o teste de HIV e proporção
    com resultado positivo (as duas sobre todos os casos novos). Colunas ``ano``,
    ``categoria`` ("Realizou", "Positivo"), ``n``, ``total`` e ``valor``."""
    dados = _consultar(
        f"""
        SELECT ano_notificacao AS ano, count(*) AS total,
               count(*) FILTER (WHERE resultado_hiv IN ('Positivo', 'Negativo')) AS realizou,
               count(*) FILTER (WHERE resultado_hiv = 'Positivo') AS positivo
        FROM {microdado_ra._tabela()}
        WHERE ano_notificacao >= {ANO_INICIAL}
        GROUP BY 1 ORDER BY 1
        """
    )
    longo = dados.melt(
        id_vars=["ano", "total"], value_vars=["realizou", "positivo"],
        var_name="categoria", value_name="n",
    )
    longo["categoria"] = longo["categoria"].map({"realizou": "Realizou", "positivo": "Positivo"})
    longo["valor"] = longo["n"] / longo["total"] * 100
    return longo.sort_values(["categoria", "ano"]).reset_index(drop=True)


def hiv_por_regiao() -> pd.DataFrame:
    """Tabela 6: proporção de casos novos com HIV positivo, por Região de Saúde."""
    return _por_serie("resultado_hiv = 'Positivo'", "TRUE")


# ---------------------------------------------------------------------------
# Populações vulneráveis — Gráficos 11 e 12
# ---------------------------------------------------------------------------


def privados_de_liberdade() -> pd.DataFrame:
    """Gráfico 11: proporção de casos novos em pessoas privadas de liberdade."""
    return _por_serie("populacao_privada_liberdade = 'Sim'", "TRUE")


def situacao_de_rua() -> pd.DataFrame:
    """Gráfico 12: proporção de casos novos em pessoas em situação de rua."""
    return _por_serie("populacao_situacao_rua = 'Sim'", "TRUE")
