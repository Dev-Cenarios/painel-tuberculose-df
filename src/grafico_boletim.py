"""Gráficos no desenho do Boletim da SES-DF, em ECharts.

Cada função devolve a *opção* (um dict) para `grafico_componente.desenhar`, como as
de lá. O desenho é o do Boletim, gráfico a gráfico — linhas por Região de Saúde e
uma linha tracejada para o DF (Gráficos 1, 3, 6, 11 e 12), colunas empilhadas em
100% por ano (2, 4 e 5) ou por região (7), colunas agrupadas (8) —, e as decisões
de forma que o hansepe tomou ao aproximar-se do Boletim da SES-PE valem aqui:

- **legenda embaixo e centrada**, nunca no topo nem numa calha;
- **categorias na ordem do campo** (ignorado primeiro), não na da frequência;
- **eixo de 0 a 100 fixo** nos percentuais, para que a variação de dois pontos não
  pareça um tombo;
- a **régua do Ministério** (85% de cura, 5% de abandono) desenhada como linha de
  referência, quando o indicador tem uma.

As cores das séries vêm do manual de identidade dos painéis do Cenários, em ordem
fixa: foram validadas contra os seis tipos de daltonismo e contra o contraste, e
refazê-las no olho quebra a validação.
"""

from __future__ import annotations

import unicodedata

import pandas as pd

from .data import boletim
from .grafico_componente import (
    _COR_EIXO,
    _FONTE_PX,
    _base,
    _eixo_valor,
    _recado,
    _valor,
    cor_sobre,
)
from .theme import cores as paleta
from .theme import visao

#: Uma cor por Região de Saúde, na ordem do Boletim. Paleta de séries do manual
#: (fundo claro); o DF não usa nenhuma: é cinza escuro e tracejado, para ler como
#: "o total" e não como uma oitava região.
COR_REGIAO = {
    "Regiao Central": "#3891C0",
    "Regiao Centro-Sul": "#C0663C",
    "Regiao Leste": "#6C5CA8",
    "Regiao Norte": "#5A9E2E",
    "Regiao Oeste": "#8E3B46",
    "Regiao Sudoeste": "#B08A1E",
    "Regiao Sul": "#3F4E9E",
}
COR_DF = "#4B5563"

#: Cor de cada desfecho. Semântica, e não uma rampa: cura é verde e as perdas
#: (abandono, óbito) são quentes — o leitor lê a cor antes da legenda.
COR_DESFECHO = {
    "Cura": "#16A34A",
    "Abandono": "#B45309",
    "Óbito por tuberculose": "#7E1936",
    "Óbito por outras causas": "#B25068",
    "Transferência": "#3F4E9E",
    "Abandono primário": "#E0A458",
    "Outros": "#8E8A99",
    "Ign/Branco": "#C3C7CE",
}

#: Categorias que não são classe, em cinza e fora da rampa.
COR_SEM_CLASSE = "#C3C7CE"
_SEM_CLASSE = ("ignorado", "nao se aplica", "em branco", "sem informacao", "ign/branco")

#: Cinza do fio entre as faixas empilhadas: o único que contrasta com as duas
#: pontas de uma rampa e sobrevive aos dois temas.
_FIO = "rgba(127,127,127,.7)"


def _sem_classe(categoria: str) -> bool:
    texto = unicodedata.normalize("NFKD", str(categoria).lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return any(marca in texto for marca in _SEM_CLASSE)


def cores_das_categorias(categorias: list[str], base: str) -> dict[str, str]:
    """Uma cor por categoria, do mais claro ao mais escuro na ordem recebida.

    A ordem do campo é, na maioria das variáveis da ficha, também uma ordem de
    gravidade ou de grau (escolaridade, faixa etária). Uma rampa faz a sequência das
    cores dizer isso — e tons de uma rampa diferem em luminosidade, o canal que
    nenhum daltonismo apaga. As categorias sem classe ficam em cinza, fora dela.
    """
    com_classe = [c for c in categorias if not _sem_classe(c)]
    if not com_classe:
        return {c: COR_SEM_CLASSE for c in categorias}
    rampa = paleta.rampa(base)
    luz = [visao.luminosidade(c) for c in rampa]
    if len(com_classe) == 1:
        alvos = [(max(luz) + min(luz)) / 2]
    else:
        passo = (max(luz) - min(luz)) / (len(com_classe) - 1)
        alvos = [max(luz) - i * passo for i in range(len(com_classe))]
    # Por luminosidade, e não por posição: a rampa não é linear em L*, e escolher
    # por posição põe duas vizinhas a ΔE de 9 — indistinguíveis empilhadas.
    escolhidos = [rampa[min(range(len(luz)), key=lambda i: abs(luz[i] - a))] for a in alvos]
    cores = dict(zip(com_classe, escolhidos, strict=True))
    return {c: cores.get(c, COR_SEM_CLASSE) for c in categorias}


def _fundo(nomes: list[str], *, inclinar: bool = False, largura: int = 330) -> int:
    """Margem de baixo para o eixo, o nome do eixo e a legenda, que quebra em linhas
    quando não cabe. A conta estima o comprimento de cada item (cerca de 6,5px por
    letra mais o quadradinho e a folga) contra a largura de um gráfico em meia
    coluna. Legenda rolável foi descartada: esconde metade das séries atrás de uma
    seta."""
    linhas, ocupado = 1, 0
    for nome in nomes:
        item = len(nome) * 6.5 + 36
        if ocupado and ocupado + item > largura:
            linhas, ocupado = linhas + 1, 0
        ocupado += item
    return 46 + 20 * linhas + (20 if inclinar else 0)


def _legenda(nomes: list[str]) -> dict:
    return {
        "data": nomes, "bottom": 0, "left": "center", "icon": "roundRect",
        "itemWidth": 12, "itemHeight": 10, "itemGap": 14,
        "textStyle": {"fontSize": _FONTE_PX, "fontWeight": "normal"},
    }


def _eixo_x(rotulos: list[str], nome: str = "", *, inclinar: bool = False) -> dict:
    return {
        "type": "category", "data": rotulos,
        "name": nome, "nameLocation": "middle", "nameGap": 28,
        "axisLine": {"lineStyle": {"color": _COR_EIXO}},
        "axisTick": {"show": False},
        "axisLabel": {"fontSize": _FONTE_PX, "interval": 0, **({"rotate": 20} if inclinar else {})},
    }


# ---------------------------------------------------------------------------
# Linhas por Região de Saúde — Gráficos 1, 3, 6, 11 e 12
# ---------------------------------------------------------------------------


def linhas_por_regiao(
    dados: pd.DataFrame,
    *,
    rotulo: str,
    casas: int = 1,
    maximo: float | None = None,
    destaque: str | None = None,
    regua: tuple[float, str] | None = None,
) -> dict:
    """Uma linha por Região de Saúde e uma tracejada para o DF, ano a ano.

    ``dados`` vem de `boletim` (colunas ``serie``, ``ano``, ``valor`` e, para o
    tooltip, ``n``/``total`` quando existem). ``destaque`` é a Região de Saúde que
    contém a seleção do painel: ganha espessura, e as outras recuam. ``regua`` é
    ``(valor, rótulo)`` de uma linha de referência — a meta do Ministério.

    Ponto sem valor (região sem casos na coorte naquele ano) fica **vazio**, e a
    linha não o atravessa: ligar o ano anterior ao seguinte afirmaria um valor que
    não existe.
    """
    opt = _base()
    if dados.empty:
        return _recado(opt, "Sem série para este indicador")
    anos = [str(int(a)) for a in sorted(dados["ano"].unique())]

    series = []
    for serie in [*boletim.REGIOES, boletim.DF]:
        parte = dados[dados["serie"].astype(str) == serie].set_index("ano")
        if parte.empty:
            continue
        eh_df = serie == boletim.DF
        cor = COR_DF if eh_df else COR_REGIAO[serie]
        em_foco = destaque in (None, serie) or eh_df
        nome = serie if eh_df else boletim.rotulo(serie)
        itens = []
        for ano in anos:
            linha = parte.loc[int(ano)] if int(ano) in parte.index else None
            valor = _valor(linha["valor"]) if linha is not None else None
            itens.append({"name": ano, "value": valor})
        series.append({
            "id": f"serie-{serie}", "name": nome, "type": "line",
            "data": itens, "connectNulls": False,
            "symbol": "circle", "symbolSize": 6 if serie == destaque else 5,
            "lineStyle": {
                "width": 3.5 if (eh_df or serie == destaque) else 2,
                "color": cor, "type": "dashed" if eh_df else "solid",
                "opacity": 1 if em_foco else 0.35,
            },
            "itemStyle": {"color": cor, "opacity": 1 if em_foco else 0.35},
            "emphasis": {"focus": "series"},
            "z": 5 if eh_df or serie == destaque else 3,
            **(
                {"markLine": {
                    "silent": True, "symbol": "none",
                    "lineStyle": {"color": "#9CA3AF", "type": "dotted", "width": 1.5},
                    "label": {"formatter": regua[1], "position": "insideEndTop",
                              "fontSize": _FONTE_PX, "color": "#6B7280"},
                    "data": [{"yAxis": regua[0]}],
                }} if regua and eh_df else {}
            ),
        })

    nomes = [s["name"] for s in series]
    opt.update({
        "grid": {"left": 56, "right": 16, "top": 20, "bottom": _fundo(nomes)},
        "xAxis": _eixo_x(anos, "Ano de diagnóstico") | {"boundaryGap": True},
        "yAxis": {**_eixo_valor(rotulo), "min": 0, **({"max": maximo} if maximo else {})},
        "series": series,
        "legend": _legenda(nomes),
    })
    opt["tooltip"].update({"trigger": "axis", "casas": casas, "rotuloValor": ""})
    return opt


# ---------------------------------------------------------------------------
# Colunas empilhadas em 100% — Gráficos 2, 4, 5 e 7
# ---------------------------------------------------------------------------


def empilhado_100(
    dados: pd.DataFrame,
    *,
    x: str,
    cor: str | None = None,
    cores: dict[str, str] | None = None,
    nome_x: str = "",
    rotulo: str = "% dos casos",
    inclinar: bool = False,
    rotulos_x: dict[str, str] | None = None,
    valores: bool = False,
) -> dict:
    """Colunas empilhadas em 100%: ``x`` é a coluna do eixo (``ano`` ou ``serie``);
    ``categoria`` e ``pct`` dizem o que empilha e quanto.

    Empilhado, e não lado a lado, porque o que se compara é a **composição**: o
    volume de casos muda entre os anos, e lado a lado um ano com metade dos casos
    pareceria ter metade de tudo. A ordem de empilhamento é a ordem em que a
    categoria aparece em ``dados`` — que quem chama já ordenou pelo campo.

    ``cores`` (categoria → cor) tem precedência sobre ``cor``, que gera uma rampa
    quando as categorias são graus de uma mesma coisa. ``valores`` escreve o
    percentual dentro de cada fatia que cabe.
    """
    opt = _base()
    if dados.empty:
        return _recado(opt, "Sem série para esta variável")
    posicoes = list(dict.fromkeys(dados[x]))
    nomes_x = [(rotulos_x or {}).get(str(p), str(p)) for p in posicoes]
    if isinstance(dados["categoria"].dtype, pd.CategoricalDtype):
        # A ordem do campo, e não a da primeira aparição: uma categoria que falta no
        # primeiro ano (Amarela, em 2021) entraria no fim da pilha.
        presentes = set(dados["categoria"].astype(str))
        categorias = [str(c) for c in dados["categoria"].cat.categories if str(c) in presentes]
    else:
        categorias = [str(c) for c in dict.fromkeys(dados["categoria"])]
    mapa_cor = cores or cores_das_categorias(categorias, cor or "#3891C0")

    series = []
    for categoria in categorias:
        parte = dados[dados["categoria"].astype(str) == categoria].set_index(x)["pct"]
        itens = []
        for p, nome in zip(posicoes, nomes_x, strict=True):
            valor = _valor(parte.get(p))
            item = {"name": nome, "value": valor}
            # Fatia fina demais para caber o número: o rótulo some, o valor segue no
            # tooltip.
            if valores and (valor is None or valor < 6):
                item["label"] = {"show": False}
            itens.append(item)
        fundo = mapa_cor.get(categoria, COR_SEM_CLASSE)
        series.append({
            "id": f"cat-{categoria}", "name": categoria, "type": "bar", "stack": "composicao",
            "data": itens, "barCategoryGap": "24%",
            "itemStyle": {"color": fundo, "borderColor": _FIO, "borderWidth": 1},
            **({"label": {
                "show": True, "position": "inside", "color": cor_sobre(fundo),
                "fontSize": _FONTE_PX - 1, "casas": 0,
            }} if valores else {}),
        })
    series[-1]["itemStyle"]["borderRadius"] = [2, 2, 0, 0]

    opt.update({
        "grid": {"left": 56, "right": 16, "top": 16, "bottom": _fundo(categorias, inclinar=inclinar)},
        "xAxis": _eixo_x(nomes_x, nome_x, inclinar=inclinar) | {"boundaryGap": True},
        "yAxis": {**_eixo_valor(rotulo), "min": 0, "max": 100},
        "series": series,
        "legend": _legenda(categorias),
    })
    opt["tooltip"].update({
        "trigger": "axis", "axisPointer": {"type": "shadow"},
        "rotuloValor": "%", "casas": 1,
    })
    return opt


# ---------------------------------------------------------------------------
# Colunas agrupadas — Gráfico 8
# ---------------------------------------------------------------------------


def colunas_agrupadas(
    dados: pd.DataFrame,
    *,
    cores: dict[str, str],
    rotulo: str = "Proporção (%)",
    casas: int = 1,
) -> dict:
    """Duas ou mais séries lado a lado por ano, com o valor em cima de cada coluna.
    ``dados`` tem ``ano``, ``categoria`` e ``valor``. Eixo de 0 a 100 fixo."""
    opt = _base()
    if dados.empty:
        return _recado(opt, "Sem série para este indicador")
    anos = [str(int(a)) for a in sorted(dados["ano"].unique())]
    series = []
    for categoria, fundo in cores.items():
        parte = dados[dados["categoria"] == categoria].set_index("ano")["valor"]
        series.append({
            "id": f"col-{categoria}", "name": categoria, "type": "bar",
            "data": [{"name": a, "value": _valor(parte.get(int(a)))} for a in anos],
            "itemStyle": {"color": fundo, "borderRadius": [3, 3, 0, 0]},
            "barCategoryGap": "34%",
            "label": {"show": True, "position": "top", "fontSize": _FONTE_PX, "casas": casas},
        })
    opt.update({
        "grid": {"left": 56, "right": 16, "top": 24, "bottom": _fundo(list(cores))},
        "xAxis": _eixo_x(anos, "Ano de diagnóstico") | {"boundaryGap": True},
        "yAxis": {**_eixo_valor(rotulo), "min": 0, "max": 100},
        "series": series,
        "legend": _legenda(list(cores)),
    })
    opt["tooltip"].update({
        "trigger": "axis", "axisPointer": {"type": "shadow"}, "casas": casas,
    })
    return opt
