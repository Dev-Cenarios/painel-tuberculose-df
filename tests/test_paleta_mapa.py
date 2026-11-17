"""As rampas explícitas do mapa: o que elas prometem à leitura."""

from __future__ import annotations

import pytest

from src.doencas import tuberculose as pack
from src.theme import cores, visao

METRICAS = tuple(pack.PALETA_MAPA)


def test_toda_metrica_do_mapa_tem_rampa_explicita() -> None:
    """Sem ela o mapa cai na rampa gerada, cujo topo é quase preto."""
    faltando = [m for m in pack.METRICAS_MAPA if m not in pack.PALETA_MAPA]
    assert not faltando, f"sem rampa explícita: {faltando}"


@pytest.mark.parametrize("metrica", METRICAS)
def test_a_rampa_tem_sete_tons_e_escurece_sempre(metrica: str) -> None:
    """Do claro ao escuro, sem voltar atrás: classe maior tem de ser mais
    escura em qualquer visão de cor — a luminosidade é o canal que o
    daltonismo não apaga."""
    rampa = pack.rampa_mapa(metrica)
    assert len(rampa) == 7
    luz = [visao.luminosidade(c) for c in rampa]
    assert all(a > b for a, b in zip(luz, luz[1:], strict=False)), luz


@pytest.mark.parametrize("metrica", METRICAS)
def test_o_tom_mais_claro_se_distingue_do_fundo_branco(metrica: str) -> None:
    """Tom quase branco deixava as regiões de classe baixa invisíveis e o mapa
    parecia furado (o mesmo defeito corrigido no hansepe em set/2026)."""
    assert cores.contraste(pack.rampa_mapa(metrica)[0], "#FFFFFF") >= 1.15


@pytest.mark.parametrize("metrica", METRICAS)
def test_os_passos_da_rampa_nao_tem_degrau_enorme(metrica: str) -> None:
    luz = [visao.luminosidade(c) for c in pack.rampa_mapa(metrica)]
    passos = [a - b for a, b in zip(luz, luz[1:], strict=False)]
    assert max(passos) <= 2.2 * min(passos), passos


def test_metrica_sem_paleta_cai_na_rampa_gerada() -> None:
    assert len(pack.rampa_mapa("hiv_pos_pct")) == 7
