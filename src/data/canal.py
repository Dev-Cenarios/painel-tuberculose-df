"""Canal endêmico: o ano corrente contra a faixa histórica.

Mesma ideia do RecifeTB (`paineis/RecifeTB/src/data/canal.py`, que reconstrói
o método do painel em R): o ano selecionado desenhado sobre a faixa
interquartil dos anos anteriores — "março está dentro do que o DF costuma
ter em março", não "quantos casos houve em março".

**Adaptação de fonte.** O RecifeTB lê `_cache_ts`, que já traz taxa mensal
pronta (população por mês, do painel nacional). Aqui não existe isso: a
única população que a extração do DF tem é anual (`pop_ibge`,
`microdado.populacao_ano`). A incidência mensal usada aqui é
``casos_do_mês / população_do_ano × 100.000`` — a população do ano inteiro
aplicada a cada mês dele, mesma convenção que o RecifeTB já usa entre anos
diferentes (população de cada ano, não uma fixa — ver `excecoes.md` §5 de
lá). Um mês de dezembro e um de janeiro do mesmo ano dividem o mesmo
denominador; é a melhor aproximação disponível sem população mês a mês.

**Sem população, sem canal.** Anos anteriores a 2010 (a extração do SINAN
do DF começa em 2001, mas `pop_ibge` só cobre 2010 em diante) são pulados
na faixa de referência, igual ao RecifeTB pular ano sem parquet — a faixa
histórica só usa o que tem denominador de verdade.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import microdado, microdado_ra
from .escopo import Escopo

#: Quantos anos anteriores compõem a faixa — mesmo padrão do RecifeTB
#: (decisão de lá: três é pouco, cinco estabiliza a faixa).
ANOS_REFERENCIA = 5

#: Fator da taxa por 100 mil — mesmo de `kpis.POR_100K`, repetido aqui para
#: este módulo não depender de `kpis.py` só por uma constante.
POR_100K = 100_000


@dataclass(frozen=True, slots=True)
class Canal:
    """As três camadas do gráfico, já prontas para desenhar — mesma forma
    do `Canal` do RecifeTB, para `src/grafico_componente.py::canal_endemico` desenhar
    os dois sem alteração."""

    faixa: pd.DataFrame
    referencia: pd.DataFrame
    atual: pd.DataFrame
    anos: tuple[int, ...]

    @property
    def vazio(self) -> bool:
        return self.atual.empty or self.faixa.empty


def _incidencia_mensal(ano: int, geo: tuple[str, str] | None = None) -> pd.DataFrame:
    """Incidência por 100 mil em cada mês de ``ano``. Vazio se o ano não
    tiver população extraída (`microdado.populacao_ano` devolve `None`).

    Com ``geo`` — ``(nível, chave)`` de uma RA/Região —, a contagem vem de
    `microdado_ra` e o denominador é a população **estimada** dela
    (`microdado_ra.populacao_de`: proporção do Censo 2022 aplicada à população
    anual do DF). É aproximação, e numa RA pequena a taxa mensal oscila muito.
    """
    vazia = pd.DataFrame(columns=["mes", "mes_nome", "valor"])
    if geo is None:
        populacao = microdado.populacao_ano(ano)
        if populacao is None:
            return vazia
        serie = microdado.serie_mensal(Escopo(doenca="TUBERCULOSE", ano=ano))
    else:
        nivel, chave = geo
        populacao = microdado_ra.populacao_de(ano, nivel, chave)
        if not populacao:
            return vazia
        serie = microdado_ra.serie_mensal(ano, nivel, chave)

    if serie.empty:
        return vazia

    return serie.assign(valor=serie["valor"] / populacao * POR_100K)[
        ["mes", "mes_nome", "valor"]
    ]


def montar(
    ano: int, anos_referencia: int = ANOS_REFERENCIA,
    geo: tuple[str, str] | None = None,
) -> Canal:
    """Monta o canal endêmico do ano dado.

    Anos de referência sem população extraída são simplesmente pulados — a
    faixa fica mais estreita (menos anos), não errada.
    """
    atual = _incidencia_mensal(ano, geo)
    if atual.empty:
        vazia = pd.DataFrame(columns=["mes", "mes_nome", "valor"])
        return Canal(
            faixa=pd.DataFrame(columns=["mes", "mes_nome", "q1", "q3"]),
            referencia=pd.DataFrame(columns=["mes", "mes_nome", "ano", "valor"]),
            atual=vazia,
            anos=(),
        )

    anteriores: list[pd.DataFrame] = []
    for ano_ref in range(ano - anos_referencia, ano):
        serie = _incidencia_mensal(ano_ref, geo)
        if not serie.empty:
            anteriores.append(serie.assign(ano=ano_ref))

    meses = atual[["mes", "mes_nome"]].drop_duplicates().sort_values("mes")

    if not anteriores:
        return Canal(
            faixa=meses.assign(q1=np.nan, q3=np.nan),
            referencia=pd.DataFrame(columns=["mes", "mes_nome", "ano", "valor"]),
            atual=atual,
            anos=(),
        )

    historico = pd.concat(anteriores, ignore_index=True)
    quartis = (
        historico.groupby("mes")["valor"]
        .agg(
            q1=lambda s: float(np.quantile(s, 0.25)),
            q3=lambda s: float(np.quantile(s, 0.75)),
        )
        .reset_index()
    )

    return Canal(
        faixa=meses.merge(quartis, on="mes", how="left"),
        referencia=historico[["mes", "mes_nome", "ano", "valor"]],
        atual=atual,
        anos=tuple(sorted(historico["ano"].unique())),
    )


def meses_fora_da_faixa(canal: Canal) -> pd.DataFrame:
    """Meses do ano corrente acima do Q3 ou abaixo do Q1 — mesma função do
    RecifeTB, copiada sem alteração (opera só sobre o `Canal`)."""
    if canal.vazio:
        return pd.DataFrame(columns=["mes", "mes_nome", "valor", "q1", "q3", "posicao"])

    juncao = canal.atual.merge(canal.faixa[["mes", "q1", "q3"]], on="mes", how="left")
    acima = juncao["valor"] > juncao["q3"]
    abaixo = juncao["valor"] < juncao["q1"]
    fora = juncao[acima | abaixo].copy()
    fora["posicao"] = np.where(fora["valor"] > fora["q3"], "acima", "abaixo")
    return fora.reset_index(drop=True)


def epicurva(
    ano_max: int, ano_min: int | None = None,
    geo: tuple[str, str] | None = None,
) -> pd.DataFrame:
    """Série mensal de **contagem** (não taxa) atravessando todos os anos —
    o par do canal. Colunas ``ano_mes``, ``ano``, ``mes``, ``casos``.

    Contagem, não incidência: diferente do canal, a epicurva não precisa de
    população — e não pular anos sem `pop_ibge` é o ponto: a extração do
    SINAN do DF começa em 2001, bem antes de 2010, e a epicurva é o único
    gráfico deste painel que mostra esse histórico inteiro.
    """
    if geo is not None:
        # Uma consulta só, do primeiro ano geolinkado em diante; antes disso
        # não há dado por RA (a fonte começa em 2010).
        nivel, chave = geo
        primeiro = max(
            ano_min if ano_min is not None else 0, min(microdado_ra.anos_disponiveis())
        )
        partes = [microdado_ra.casos_por_mes(primeiro, ano_max, nivel, chave)]
    else:
        primeiro = ano_min if ano_min is not None else min(microdado.anos_disponiveis())
        partes = []
        for ano in range(primeiro, ano_max + 1):
            serie = microdado.serie_mensal(Escopo(doenca="TUBERCULOSE", ano=ano))
            if not serie.empty:
                partes.append(serie.rename(columns={"valor": "casos"}).assign(ano=ano))

    if not partes:
        return pd.DataFrame(columns=["ano_mes", "ano", "mes", "casos"])

    tudo = pd.concat(partes, ignore_index=True)
    tudo["ano_mes"] = (
        tudo["ano"].astype(str) + "-" + tudo["mes"].astype(int).astype(str).str.zfill(2)
    )
    return tudo.sort_values(["ano", "mes"])[["ano_mes", "ano", "mes", "casos"]].reset_index(drop=True)
