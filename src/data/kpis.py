"""KPIs do painel, calculados direto do microdado.

**Com incidência e mortalidade**, desde que `scripts/extrair_populacao_df.py`
e `scripts/extrair_obitos_tb_df.py` tenham rodado — mesmas fontes que o
RecifeTB e o manaustb usam (`pop_ibge`, `sim_mortalidade`), adaptadas ao que
existe para o DF. Os dois KPIs ficam `None` (não zero, nem fabricado) quando
o parquet de população ou de óbitos não existe — um card ausente é honesto,
um card com taxa fabricada não é. Os demais KPIs seguem só o que o microdado
sustenta sozinho: contagem e proporção sobre o próprio universo de
notificações.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import microdado
from .escopo import Escopo

#: Fator da taxa por 100 mil habitantes.
POR_100K = 100_000

#: Valores de `situacao_encerramento` observados no dado. Repetidos aqui, e
#: não descobertos em tempo de execução — mesma razão do manaustb: olhar o
#: dado a cada rerun para redescobrir a grafia seria caro e mudaria o KPI
#: sozinho se a extração um dia grafar diferente.
_ENCERRAMENTOS_VALIDOS = (
    "Cura", "Abandono", "Abandono primario", "Obito por TB",
    "Obito por outras causas", "Transferencia", "TB-DR",
    "Mudanca de esquema", "Falencia",
)


def _div(numerador, denominador, fator: float = 1.0) -> float | None:
    if not denominador:
        return None
    return numerador / denominador * fator


@dataclass
class Kpis:
    casos: int | None = None
    cura_pct: float | None = None
    cura_n: int | None = None
    abandono_pct: float | None = None
    abandono_n: int | None = None
    hiv_pos_pct: float | None = None
    hiv_pos_n: int | None = None
    coorte: int | None = None
    testados_hiv: int | None = None
    incid: float | None = None
    populacao: int | None = None
    mortalidade: float | None = None
    obitos_tb: int | None = None


def calcular(esc: Escopo) -> Kpis:
    """Faixa de KPIs do ano do escopo.

    ``casos`` são casos novos, como no Boletim da SES-DF (`config.SQL_CASO_NOVO`).
    ``cura_pct`` e ``abandono_pct`` seguem o Boletim também: sobre a coorte de
    casos novos **pulmonares com confirmação laboratorial** do ano, contando os que
    ainda não encerraram — por isso a cura de um ano recente é um piso.
    Abandono soma "Abandono" e "Abandono primario": são o mesmo desfecho
    clínico, a extração só os separa por quando na linha do tempo
    aconteceram. ``hiv_pos_pct`` é a proporção de casos novos com HIV positivo
    (Tabela 6 do Boletim), não a positividade entre os testados.
    """
    hiv = microdado.composicao(esc, "resultado_hiv")
    casos = microdado.total(esc)
    desfecho = microdado.desfecho_coorte(esc.ano)
    coorte = desfecho["coorte"]

    def _n(df, *categorias):
        if df.empty:
            return 0
        return int(df.loc[df["categoria"].isin(categorias), "n"].sum())

    cura_n = desfecho["cura_n"]
    abandono_n = desfecho["abandono_n"]

    testados_hiv = _n(hiv, "Positivo", "Negativo")
    hiv_pos_n = _n(hiv, "Positivo")

    populacao = microdado.populacao_ano(esc.ano)
    obitos_tb = microdado.obitos_tb_ano(esc.ano)

    return Kpis(
        casos=casos,
        cura_pct=_div(cura_n, coorte, 100),
        cura_n=cura_n,
        abandono_pct=_div(abandono_n, coorte, 100),
        abandono_n=abandono_n,
        hiv_pos_pct=_div(hiv_pos_n, casos, 100),
        hiv_pos_n=hiv_pos_n,
        coorte=coorte,
        testados_hiv=testados_hiv,
        incid=_div(casos, populacao, POR_100K),
        populacao=populacao,
        mortalidade=_div(obitos_tb, populacao, POR_100K) if obitos_tb is not None else None,
        obitos_tb=obitos_tb,
    )
