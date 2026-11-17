"""Fachada de dados do painel: o painel inteiro responde a uma RA/Região.

Quando se clica numa Região Administrativa (ou numa Região de Saúde), **todo** o
painel se molda a ela — KPIs, evolução temporal, pirâmide, tópicos —, como no
hansepe quando se clica num município. O app pergunta sempre ``(ano, geo)``:

- ``geo is None`` — DF inteiro.
- ``geo = (nível, chave)`` — uma RA ou Região de Saúde.

**Uma fonte só: `dados_geolink."DF_geo_TB"` (`microdado_ra.py`).** Desde
13/out/2026 o DF inteiro também lê dela, sem filtro de região. Antes ele lia
`silver.tuberculose`, e as duas fontes divergiam em volume — o card do DF e a soma do
mapa nunca fechavam. A medição contra o Boletim da SES-DF decidiu: a fonte por
região fica a menos de 2% do Boletim em casos novos, a `silver` (recarregada em
06/out, ver `tests/paridade/excecoes.md` §8) de 6 a 8% abaixo. O DF inteiro agora é a
soma das regiões, mais os casos sem RA identificada.

`silver.tuberculose` continua alimentando só o que a fonte por região não traz: as
variáveis dos tópicos que existem apenas nela (ocupação, resistência...), no DF
inteiro. Os números dos cards, dos gráficos e do mapa vêm todos da mesma fonte.

**O que muda ao entrar numa RA, e o app avisa:**

- A **mortalidade** não existe por RA: o SIM não traz RA de residência na nossa
  extração. O card fica vazio, com a explicação, em vez de mostrar zero. No DF
  inteiro ela existe.
- A **incidência** da RA usa a população estimada pela proporção do Censo 2022 —
  aproximação, não série medida. A do DF inteiro usa a população do Boletim.
- Percentuais sobre menos de `MINIMO_PARA_PERCENTUAL` registros somem, como no
  mapa.
- A série começa em 2010, no DF e nas regiões.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd

from . import canal as _canal
from . import config, kpis as _kpis, microdado, microdado_ra
from .escopo import Escopo

#: ``(nível, chave)`` — ``("RA", "PLANO PILOTO")`` — ou ``None`` para o DF.
Geo = tuple[str, str] | None

#: Mesmo limiar de publicabilidade do mapa e do `microdado.py`.
MINIMO_PARA_PERCENTUAL = microdado_ra.MINIMO_PARA_PERCENTUAL

POR_100K = _kpis.POR_100K



def _escopo(ano: int) -> Escopo:
    return Escopo(doenca=config.TUBERCULOSE, ano=ano)


def _regional(geo: Geo) -> tuple[str, str | None]:
    """``(nível, chave)`` para a fonte por região; o DF inteiro é ``("RA", None)``
    — sem filtro de região."""
    return geo if geo is not None else ("RA", None)


def fonte(geo: Geo) -> str:
    """Nome curto da fonte, para o rótulo que o app põe na tela."""
    return 'dados_geolink."DF_geo_TB"'


def anos(geo: Geo) -> list[int]:
    """Anos com dado: de 2010 em diante, no DF e nas regiões."""
    return microdado_ra.anos_disponiveis()


def ano_valido(ano: int, geo: Geo) -> int:
    """O ano pedido, ou o mais próximo que a fonte da geografia tem."""
    disponiveis = anos(geo)
    if ano in disponiveis:
        return ano
    return min(disponiveis, key=lambda a: (abs(a - ano), a))


def kpis(ano: int, geo: Geo) -> _kpis.Kpis:
    nivel, chave = _regional(geo)
    r = microdado_ra.resumo(ano, nivel, chave)
    populacao = microdado_ra.populacao_de(ano, nivel, chave)
    # O SIM não traz RA: a mortalidade só existe para o DF inteiro.
    obitos = microdado.obitos_tb_ano(ano) if geo is None else None

    def _pct(n: int, den: int) -> float | None:
        # Mesmo corte do mapa: proporção sobre menos de 5 registros é ruído.
        return n / den * 100 if den >= MINIMO_PARA_PERCENTUAL else None

    return _kpis.Kpis(
        casos=r["casos"],
        cura_pct=_pct(r["cura_n"], r["coorte"]),
        cura_n=r["cura_n"],
        abandono_pct=_pct(r["abandono_n"], r["coorte"]),
        abandono_n=r["abandono_n"],
        hiv_pos_pct=_pct(r["hiv_pos_n"], r["casos"]),
        hiv_pos_n=r["hiv_pos_n"],
        coorte=r["coorte"],
        testados_hiv=r["testados_hiv"],
        incid=r["casos"] / populacao * POR_100K if populacao else None,
        populacao=round(populacao) if populacao else None,
        # Sem mortalidade por RA, e `None` — não zero.
        mortalidade=obitos / populacao * POR_100K if obitos is not None and populacao else None,
        obitos_tb=obitos,
    )


def serie_mensal(ano: int, geo: Geo) -> pd.DataFrame:
    return microdado_ra.serie_mensal(ano, *_regional(geo))


def serie_anual(geo: Geo) -> pd.DataFrame:
    return microdado_ra.serie_anual(*_regional(geo))


def piramide(ano: int, geo: Geo) -> pd.DataFrame:
    return microdado_ra.piramide(ano, *_regional(geo))


def composicao(ano: int, variavel: str, geo: Geo) -> pd.DataFrame:
    if geo is None and not microdado_ra.variavel_presente(variavel):
        # No DF inteiro, a variável que só a `silver` tem (ocupação, resistência...)
        # ainda vem de lá — a única exceção à fonte única, e o app diz qual é.
        return microdado.composicao(_escopo(ano), variavel)
    nivel, chave = _regional(geo)
    return microdado_ra.composicao(ano, variavel, nivel=nivel, chave=chave)


def variavel_disponivel(variavel: str, geo: Geo) -> bool:
    """Se a variável existe na fonte desta geografia: no DF inteiro, em qualquer
    uma das duas; numa região, só na fonte por região."""
    if geo is None and variavel.lower() in {c.lower() for c in microdado._colunas()}:
        return True
    return microdado_ra.variavel_presente(variavel)


def canal(ano: int, geo: Geo) -> _canal.Canal:
    return _canal.montar(ano, geo=_regional(geo))


def epicurva(ano_max: int, geo: Geo) -> pd.DataFrame:
    return _canal.epicurva(ano_max, geo=_regional(geo))


# ---------------------------------------------------------------------------
# Procedência: até quando vão os dados e quando foram processados
# ---------------------------------------------------------------------------

_MESES_CURTOS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")


def _data_br(texto: str) -> str:
    """``2026-10-08T17:50-03:00`` -> ``08/10/2026``."""
    return datetime.fromisoformat(texto).strftime("%d/%m/%Y")


def procedencia() -> dict[str, str] | None:
    """O que a linha "Dados até / Processado em" mostra, ou ``None`` se o registro
    não existe (`PROCEDENCIA.json`, gravado por `scripts/preparar_microdado.py`).

    Devolve ``dados_ate`` ("dez/2024"), ``processado_em`` ("08/10/2026") e
    ``ajuda`` — o texto do "i", que diz o que cada data significa e que o corte em
    2024 é deliberado. Registro ausente ou ilegível dá ``None``, e o painel sobe sem
    a linha em vez de cair.
    """
    caminho = config.procedencia_path()
    if not caminho.is_file():
        return None
    try:
        registro = json.loads(caminho.read_text(encoding="utf-8"))
        ate = date.fromisoformat(registro["dados_ate"])
        processado = _data_br(registro["processado_em"])
    except (OSError, ValueError, KeyError, TypeError):
        return None

    fontes = registro.get("fontes", {})
    nomes = {"silver": "DF inteiro", "geolink": "por região"}
    por_fonte = "; ".join(
        f"{nomes.get(n, n)}: notificações até {date.fromisoformat(f['dados_ate']).strftime('%d/%m/%Y')}, "
        f"extraídas do banco em {_data_br(f['extraido_em'])}"
        for n, f in fontes.items()
        if f.get("dados_ate") and f.get("extraido_em")
    )
    ajuda = (
        "Dados até: a notificação mais recente do SINAN nas extrações. O painel corta "
        "em 2024 de propósito — 2025 ainda não tem encerramento fechado. "
        "Processado em: quando as extrações foram preparadas para o painel."
        + (f" {por_fonte}." if por_fonte else "")
        + " O SINAN é atualizado retroativamente, então os números mudam entre extrações."
    )
    return {
        "dados_ate": f"{_MESES_CURTOS[ate.month - 1]}/{ate.year}",
        "processado_em": processado,
        "ajuda": ajuda,
    }
