"""Linha "Dados até / Processado em": gravação, leitura e exibição."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from scripts import preparar_microdado
from src.data import config, painel

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _parquet(caminho: Path, ultima: str) -> Path:
    pd.DataFrame({"dt_notificacao": pd.to_datetime(["2024-03-01", ultima]).date}).to_parquet(caminho)
    return caminho


def test_grava_o_fim_da_serie_e_a_hora_do_processamento(tmp_path: Path) -> None:
    a = _parquet(tmp_path / "a.parquet", "2024-12-30")
    b = _parquet(tmp_path / "b.parquet", "2024-12-31")
    destino = tmp_path / "saida" / "PROCEDENCIA.json"
    registro = preparar_microdado.gravar_procedencia({"silver": a, "geolink": b}, destino)
    assert registro["dados_ate"] == "2024-12-31"
    assert registro["fontes"]["silver"]["dados_ate"] == "2024-12-30"
    assert registro["fontes"]["geolink"]["linhas"] == 2
    assert json.loads(destino.read_text(encoding="utf-8")) == registro
    # com fuso: "08/10" às 23h não pode virar outro dia ao ser lido noutra máquina
    assert registro["processado_em"][-6] in "+-"


def test_fonte_ausente_nao_derruba_a_gravacao(tmp_path: Path) -> None:
    a = _parquet(tmp_path / "a.parquet", "2024-12-30")
    registro = preparar_microdado.gravar_procedencia(
        {"silver": a, "geolink": tmp_path / "nao_existe.parquet"}, tmp_path / "P.json"
    )
    assert list(registro["fontes"]) == ["silver"]


def _registro(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conteudo: str | None) -> None:
    caminho = tmp_path / "PROCEDENCIA.json"
    if conteudo is not None:
        caminho.write_text(conteudo, encoding="utf-8")
    monkeypatch.setattr(config, "procedencia_path", lambda: caminho)


def test_formata_para_o_leitor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _registro(tmp_path, monkeypatch, json.dumps({
        "processado_em": "2026-10-08T17:20-03:00",
        "dados_ate": "2024-12-31",
        "fontes": {"silver": {"dados_ate": "2024-12-30", "extraido_em": "2026-10-08T14:52-03:00"}},
    }))
    p = painel.procedencia()
    assert p["dados_ate"] == "dez/2024"
    assert p["processado_em"] == "08/10/2026"
    assert "2024 de propósito" in p["ajuda"] and "30/12/2024" in p["ajuda"]


@pytest.mark.parametrize("conteudo", [None, "", "{quebrado", "{}", '{"dados_ate": null, "processado_em": 3}'])
def test_registro_ausente_ou_ilegivel_nao_derruba_o_painel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, conteudo: str | None
) -> None:
    _registro(tmp_path, monkeypatch, conteudo)
    assert painel.procedencia() is None


def test_o_app_mostra_a_linha() -> None:
    if not config.procedencia_path().is_file():
        pytest.skip("PROCEDENCIA.json ausente (rode scripts.preparar_microdado)")
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    html = " ".join(m.value for m in at.markdown)
    assert "Dados até" in html and "Processado em" in html
    assert f"dez/{date.fromisoformat(json.loads(config.procedencia_path().read_text('utf-8'))['dados_ate']).year}" in html
