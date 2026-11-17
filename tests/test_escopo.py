"""Testes do ``Escopo`` — versão enxuta, sem nível geográfico.

O `Escopo` do RecifeTB carrega BR/UF/MUN/BAIRRO porque o dataset nacional por
baixo tem essa profundidade. Aqui a extração já é só o Distrito Federal,
então o `Escopo` só carrega doença e ano — não há o que validar de
geografia. (A RA por caso existe, mas vive numa fonte separada —
`src/data/microdado_ra.py` — e não passa pelo `Escopo`; ver README.)
"""

from __future__ import annotations

from src.data.escopo import Escopo, chave_ra


def test_doenca_e_normalizada_para_maiuscula() -> None:
    esc = Escopo(doenca="tuberculose", ano=2024)
    assert esc.doenca == "TUBERCULOSE"


def test_ano_vira_inteiro() -> None:
    esc = Escopo(doenca="TUBERCULOSE", ano="2024")
    assert esc.ano == 2024
    assert isinstance(esc.ano, int)


def test_ano_anterior() -> None:
    esc = Escopo(doenca="TUBERCULOSE", ano=2024)
    assert esc.ano_anterior == 2023


# ---------------------------------------------------------------------------
# chave_ra — normalização que liga o dado de casos à geometria
# ---------------------------------------------------------------------------


def test_chave_ra_remove_acento_e_maiusculiza() -> None:
    assert chave_ra("Sol Nascente/Pôr do Sol") == "SOL NASCENTE/POR DO SOL"


def test_chave_ra_colapsa_espaco_duplo() -> None:
    assert chave_ra("Plano  Piloto") == "PLANO PILOTO"


def test_chave_ra_de_vazio_nao_estoura() -> None:
    assert chave_ra(None) == ""
    assert chave_ra("") == ""
