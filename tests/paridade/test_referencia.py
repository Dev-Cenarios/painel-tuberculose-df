"""Comparação entre as duas fontes do SINAN-TB do DF.

**Não há painel em R do DF** para comparar, diferente do RecifeTB — os dois
lados aqui são as **nossas próprias** extrações: `silver.tuberculose`
(`src/data/microdado.py`, KPIs de topo) e `dados_geolink."DF_geo_TB"`
(`src/data/microdado_ra.py`, mapa e detalhe). `referencia.json` congela o
que as duas davam em 11/set/2026, depois da correção do filtro de
residência (`excecoes.md`, §1).

**Paridade mede concordância, não correção** — mesmo critério do RecifeTB.
As duas fontes nunca vão bater exatamente (§2 do `excecoes.md`), e este
harness não tenta fechar essa conta: ele protege contra **regressão**. Se
uma reextração mudar um total sem que `excecoes.md` seja revisto, o teste
fica vermelho e alguém precisa decidir se o número novo é esperado — não a
suíte, sozinha.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data import microdado, microdado_ra
from src.data.escopo import Escopo

REFERENCIA = json.loads(
    (Path(__file__).parent / "referencia.json").read_text(encoding="utf-8")
)

ANOS = sorted(int(a) for a in REFERENCIA["totais_por_ano"])


# ---------------------------------------------------------------------------
# Cada fonte sozinha — regressão da própria extração
# ---------------------------------------------------------------------------


@pytest.mark.dado
@pytest.mark.parametrize("ano", ANOS)
def test_total_silver_nao_mudou(ano: int) -> None:
    """`silver.tuberculose` (KPIs de topo) no ano, contra o congelado.

    Vermelho aqui quer dizer uma de duas coisas: alguém reextraiu
    `sinan_df` com dado novo do banco (esperado, e `referencia.json` precisa
    ser atualizado), ou uma mudança em `microdado.py`/`kpis.py` alterou a
    contagem sem querer.
    """
    esperado = REFERENCIA["totais_por_ano"][str(ano)]["silver"]
    esc = Escopo(doenca="TUBERCULOSE", ano=ano)
    assert microdado.total(esc) == esperado


@pytest.mark.dado_ra
@pytest.mark.parametrize("ano", ANOS)
def test_total_geolink_nao_mudou(ano: int) -> None:
    """`dados_geolink."DF_geo_TB"` (mapa e detalhe) no ano, contra o
    congelado. Mesma leitura do teste anterior, fonte diferente."""
    esperado = REFERENCIA["totais_por_ano"][str(ano)]["geolink"]
    assert microdado_ra.total(ano) == esperado


# ---------------------------------------------------------------------------
# A divergência entre as duas — registrada, não escondida
# ---------------------------------------------------------------------------


@pytest.mark.dado
@pytest.mark.dado_ra
@pytest.mark.parametrize("ano", ANOS)
def test_divergencia_bate_com_o_registrado(ano: int) -> None:
    """A diferença `geolink - silver` no ano é a mesma do `excecoes.md`.

    Não afirma que a diferença é zero — afirma que ela é a que já foi
    investigada e escrita. Se este teste falhar, a diferença **mudou**, e
    isso é notícia: ou uma das duas extrações trouxe dado novo (2025
    fechando, por exemplo) e `referencia.json`/`excecoes.md` precisam
    acompanhar, ou uma das duas quebrou.
    """
    esc = Escopo(doenca="TUBERCULOSE", ano=ano)
    silver = microdado.total(esc)
    geolink = microdado_ra.total(ano)
    esperado = REFERENCIA["totais_por_ano"][str(ano)]["diferenca"]
    assert geolink - silver == esperado


# ---------------------------------------------------------------------------
# Efeito do filtro de residência (§1 e §3 do excecoes.md)
# ---------------------------------------------------------------------------


@pytest.mark.dado_ra
def test_soma_anual_bate_com_o_total_sem_filtro_extra() -> None:
    """A soma dos 15 anos de `microdado_ra.total()` é o total de linhas do
    parquet — confere que `total()` não está filtrando nada além do ano, e
    que o parquet gerado é mesmo o pós-filtro-de-residência (6.325 linhas,
    não as 7.551 de antes da correção do §1)."""
    soma = sum(
        REFERENCIA["totais_por_ano"][str(ano)]["geolink_notificacoes"] for ano in ANOS
    )
    assert soma == REFERENCIA["geolink_bruto"]["linhas_apos_dedup"]


@pytest.mark.dado_ra
@pytest.mark.parametrize("ano", ANOS)
def test_notificacoes_brutas_nao_mudaram(ano: int) -> None:
    """As notificações brutas do parquet por região, antes do recorte de casos novos
    do Boletim, contra o congelado — o recorte só pode tirar linhas, nunca mudar a
    extração por baixo."""
    bruto = microdado_ra._conectar().execute(
        f"SELECT count(*) FROM read_parquet('{microdado_ra._fonte()}') "
        f"WHERE ano_notificacao = {ano}"
    ).fetchone()[0]
    assert bruto == REFERENCIA["totais_por_ano"][str(ano)]["geolink_notificacoes"]
    assert microdado_ra.total(ano) <= bruto


@pytest.mark.dado_ra
def test_sem_ra_identificada_em_2024_nao_regrediu() -> None:
    """13 casos novos de 2024 sem RA — não as 77 de antes da correção do
    filtro de residência. Se subir muito, a extração pode ter voltado a
    incluir gente de fora do DF (ver excecoes.md, §1 e §3)."""
    valores = microdado_ra.valores(2024, "RA")
    total_2024 = microdado_ra.total(2024)
    sem_ra = total_2024 - int(valores["casos"].sum())
    assert sem_ra == REFERENCIA["geolink_bruto"]["sem_ra_identificada_2024"]


# ---------------------------------------------------------------------------
# O registro tem de acompanhar o código
# ---------------------------------------------------------------------------


def test_toda_divergencia_esta_registrada() -> None:
    """`excecoes.md` existe e nomeia os números que os testes acima
    exercitam — sem isso o registro envelhece calado."""
    texto = (Path(__file__).parent / "excecoes.md").read_text(encoding="utf-8")
    for marca in ("ID_MN_RESI", "530010", "6.325", "6.360", "1.191"):
        assert marca in texto, f"não registrado em excecoes.md: {marca}"
