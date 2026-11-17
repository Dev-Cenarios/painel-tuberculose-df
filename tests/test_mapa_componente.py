"""O componente próprio do mapa: o que o Python promete ao JavaScript."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from cenarios_core import mapa, mapa_componente

from src import doencas
from src.theme import mapa as mapa_df

pack = doencas.carregar()


# ---------------------------------------------------------------------------
# Clique
# ---------------------------------------------------------------------------


def test_os_campos_de_clique_sao_as_colunas_de_chave_do_mapa() -> None:
    """Se uma coluna de chave mudar de nome em `app.py` (`_coluna_chave`), o
    clique deixa de navegar sem dar erro. O padrão do core são as chaves
    municipais; as do DF moram em `src/theme/mapa.py` e o `app.py` as passa."""
    assert mapa_df.CAMPOS_CLIQUE == ("ra_chave", "regiao_saude")
    ev = {"nonce": "n-1", "properties": {"ra_chave": "VARJAO", "regiao_saude": "Norte"}}
    assert mapa_componente.alvo_do_clique(ev, None, mapa_df.CAMPOS_CLIQUE) == ("VARJAO", "n-1")


# ---------------------------------------------------------------------------
# Enquadramento — funções puras, sem geopandas
# ---------------------------------------------------------------------------


def test_o_foco_tem_tamanho_minimo() -> None:
    """RA pequena não vira zoom máximo num contorno de poucos pixels: o piso
    do DF (`FOCO_MINIMO`, fração do recorte) segura."""
    df = (-48.3, -16.05, -47.3, -15.5)
    pequena = (-47.90, -15.84, -47.89, -15.83)  # ~1 km
    x0, y0, x1, y1 = mapa.enquadrar_foco(df, pequena, vizinhanca=mapa_df.FOCO_VIZINHANCA,
                                         minimo=mapa_df.FOCO_MINIMO)
    assert x1 - x0 >= (df[2] - df[0]) * mapa_df.FOCO_MINIMO - 1e-9
    assert (x0 + x1) / 2 == pytest.approx(-47.895)


def test_o_foco_de_ra_grande_ganha_folga_proporcional() -> None:
    df = (-48.3, -16.05, -47.3, -15.5)
    grande = (-48.2, -16.0, -47.95, -15.75)
    x0, _, x1, _ = mapa.enquadrar_foco(df, grande, vizinhanca=mapa_df.FOCO_VIZINHANCA,
                                       minimo=mapa_df.FOCO_MINIMO)
    assert x1 - x0 == pytest.approx(0.25 * mapa_df.FOCO_VIZINHANCA)


def test_aproximar_na_ra_aumenta_o_zoom() -> None:
    """Com o foco padrão do core (o de PE) 13 das 35 RAs não aproximavam nada;
    com o do DF, uma RA pequena aproxima de verdade."""
    df = (-48.3, -16.05, -47.3, -15.5)
    ra = (-47.9, -15.85, -47.88, -15.83)
    caixa = {"largura": mapa_df.LARGURA, "altura": mapa_df.ALTURA}
    inteiro = mapa.enquadrar(df, **caixa)["zoom"]
    foco = mapa.enquadrar(mapa.enquadrar_foco(df, ra, vizinhanca=mapa_df.FOCO_VIZINHANCA,
                                              minimo=mapa_df.FOCO_MINIMO), **caixa)["zoom"]
    assert foco > inteiro + 1


# ---------------------------------------------------------------------------
# `deck()` com geometria sintética — duas caixas fazem de RA
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def duas_ras():
    gpd = pytest.importorskip("geopandas")
    from shapely.geometry import box

    return gpd.GeoDataFrame(
        {"ra_chave": ["A", "B", "C"], "ra_nome": ["Alfa", "Beta", "Gama"]},
        geometry=[box(-48.0, -16.0, -47.9, -15.9), box(-47.9, -16.0, -47.8, -15.9),
                  box(-47.8, -16.0, -47.7, -15.9)],
        crs="EPSG:4326",
    )


def _deck(camada, valores, **extra):
    return mapa.deck(
        camada, pd.Series(valores, index=["A", "B", "C"]), chave="ra_chave",
        coluna_nome="ra_nome", rampa=pack.rampa_mapa("incid"), rotulo_metrica="x",
        contornos=mapa_df.CONTORNOS, foco_vizinhanca=mapa_df.FOCO_VIZINHANCA,
        foco_minimo=mapa_df.FOCO_MINIMO, **extra,
    )


def _camada_geo(desenho):
    spec = json.loads(desenho.to_json())
    return next(c for c in spec["layers"] if c["@@type"] == "GeoJsonLayer" and c.get("id") == "geografia")


def test_camada_de_geografia_tem_id_fixo_e_transicao(duas_ras) -> None:
    """Sem `id` estável o deck.gl não interpola a cor entre reruns."""
    desenho, _ = _deck(duas_ras, [1.0, 2.0, 3.0])
    geo = _camada_geo(desenho)
    assert geo["id"] == "geografia"
    assert geo["transitions"] == {"getFillColor": mapa.TRANSICAO_COR_MS}


def test_o_spec_sai_compacto_e_sem_mapa_de_fundo(duas_ras) -> None:
    desenho, _ = _deck(duas_ras, [1.0, 2.0, 3.0])
    assert "\n" not in desenho.to_json(), "a indentação do pydeck voltou"
    assert desenho.map_style == mapa.ESTILO_SEM_FUNDO


def test_sem_dado_leva_contorno_escuro_haja_ou_nao_faixa(duas_ras) -> None:
    """O preenchimento sozinho não separa "sem dado" do valor baixo."""
    desenho, escala = _deck(duas_ras, [1.0, None, 3.0])
    props = {f["properties"]["ra_chave"]: f["properties"] for f in _camada_geo(desenho)["data"]["features"]}
    assert props["B"]["contorno"] == list(mapa_df.CONTORNO_SEM_DADO)
    assert props["A"]["contorno"] == list(mapa_df.CONTORNO_PADRAO)

    realcada = escala.rotulos[0]
    desenho2, _ = _deck(duas_ras, [1.0, None, 3.0], faixa_realcada=realcada)
    props2 = {f["properties"]["ra_chave"]: f["properties"] for f in _camada_geo(desenho2)["data"]["features"]}
    assert props2["B"]["contorno"] == list(mapa_df.CONTORNO_SEM_DADO)


def test_faixa_realcada_apaga_as_outras_em_cinza_chapado(duas_ras) -> None:
    _, escala = _deck(duas_ras, [1.0, 50.0, 100.0])
    realcada = escala.rotulos[0]
    desenho, _ = _deck(duas_ras, [1.0, 50.0, 100.0], faixa_realcada=realcada)
    props = {f["properties"]["ra_chave"]: f["properties"] for f in _camada_geo(desenho)["data"]["features"]}
    assert props["A"]["cor"] != list(mapa_df.CINZA_APAGADO) and props["A"]["contorno"] == list(mapa_df.CONTORNO_REALCADO)
    assert props["C"]["cor"] == list(mapa_df.CINZA_APAGADO) and props["C"]["contorno"] == list(mapa_df.CONTORNO_APAGADO)


def test_faixa_que_nao_existe_na_escala_nao_apaga_ninguem(duas_ras) -> None:
    """O rótulo guardado da última interação sobrevive à troca de métrica."""
    desenho, _ = _deck(duas_ras, [1.0, 50.0, 100.0], faixa_realcada="9999 a 9999")
    props = [f["properties"] for f in _camada_geo(desenho)["data"]["features"]]
    assert all(p["cor"] != list(mapa_df.CINZA_APAGADO) for p in props)


def test_geometria_memoizada_e_nao_memoizada_desenham_o_mesmo(duas_ras) -> None:
    sem, _ = _deck(duas_ras, [1.0, 2.0, 3.0])
    com, _ = _deck(duas_ras, [1.0, 2.0, 3.0], geometrias=mapa.geometrias_geojson(duas_ras))
    geo_sem = [f["geometry"] for f in _camada_geo(sem)["data"]["features"]]
    geo_com = [f["geometry"] for f in _camada_geo(com)["data"]["features"]]
    assert geo_sem == geo_com


def test_o_valor_do_tooltip_nao_e_arredondado_como_geometria(duas_ras) -> None:
    desenho, _ = _deck(duas_ras, [39.100684, 2.0, 3.0])
    props = _camada_geo(desenho)["data"]["features"][0]["properties"]
    assert props["valor"] == pytest.approx(39.100684)


def test_destaque_acrescenta_halo_traco_e_etiqueta_e_aproxima(duas_ras) -> None:
    inteiro, _ = _deck(duas_ras, [1.0, 2.0, 3.0])
    foco, _ = _deck(duas_ras, [1.0, 2.0, 3.0], destacado="B")
    tipos = [c["@@type"] for c in json.loads(foco.to_json())["layers"]]
    assert tipos.count("GeoJsonLayer") == 3 and tipos.count("TextLayer") == 1
    zoom = lambda d: json.loads(d.to_json())["initialViewState"]["zoom"]  # noqa: E731
    assert zoom(foco) > zoom(inteiro)


def test_o_destaque_nao_rouba_o_clique(duas_ras) -> None:
    foco, _ = _deck(duas_ras, [1.0, 2.0, 3.0], destacado="B")
    camadas = json.loads(foco.to_json())["layers"]
    assert all(c.get("pickable") is False for c in camadas if c.get("id") != "geografia")


def test_destaque_de_chave_inexistente_nao_estoura(duas_ras) -> None:
    desenho, _ = _deck(duas_ras, [1.0, 2.0, 3.0], destacado="NAO-EXISTE")
    assert len(json.loads(desenho.to_json())["layers"]) == 1


def test_regiao_de_saude_com_chave_igual_ao_nome(duas_ras) -> None:
    """Regressão: `chave == coluna_nome` duplicava a coluna e `.map()` quebrava
    com "first argument must be callable"."""
    regioes = duas_ras.rename(columns={"ra_chave": "regiao_saude"}).drop(columns="ra_nome")
    desenho, escala = mapa.deck(
        regioes, pd.Series([1.0, 2.0, 3.0], index=["A", "B", "C"]), chave="regiao_saude",
        coluna_nome="regiao_saude", rampa=pack.rampa_mapa("casos"), rotulo_metrica="Casos",
    )
    assert desenho.to_json() and escala.rotulos


def test_o_tooltip_lista_as_outras_metricas(duas_ras) -> None:
    detalhes = [("Casos", pd.Series({"A": 10.0, "B": 20.0, "C": 30.0}), "#EA5352", 0)]
    desenho, _ = _deck(duas_ras, [1.0, 2.0, 3.0], detalhes=detalhes)
    props = _camada_geo(desenho)["data"]["features"][0]["properties"]
    assert props["d0"] == "10"
    assert "{d0}" in desenho._tooltip["html"] and "Casos" in desenho._tooltip["html"]


# ---------------------------------------------------------------------------
# Versão dos scripts e CSS do balão
# ---------------------------------------------------------------------------


def test_scripts_dos_componentes_levam_a_versao_no_nome() -> None:
    """O Streamlit serve `.js` com `Cache-Control: public` e só o `index.html`
    com `no-cache`. Sem o `?v=<hash>` no `src`, quem já abriu o painel uma vez
    continua com o JavaScript antigo. O hash tem de ser o do arquivo atual;
    mudou o JS, muda o carimbo (`scripts/versionar_js.py`).

    O hash é de bytes com quebra de linha LF — o mesmo cálculo do script —,
    porque o checkout no Windows vem em CRLF e o Docker em Linux, não.
    """
    import hashlib
    import re

    from src import grafico_componente

    for pasta in (mapa_componente.DIRETORIO, grafico_componente.DIRETORIO):
        html = (pasta / "index.html").read_text(encoding="utf-8")
        scripts = re.findall(r'<script src="([^"?]+)\?v=([0-9a-f]{8})"></script>', html)
        assert scripts, f"{pasta.name}: script sem ?v="
        for nome, versao in scripts:
            conteudo = (pasta / nome).read_bytes().replace(b"\r\n", b"\n")
            esperado = hashlib.sha1(conteudo).hexdigest()[:8]
            assert versao == esperado, f"{pasta.name}/{nome}: carimbo {versao} != {esperado} — rode scripts/versionar_js.py"


def test_o_css_do_tooltip_mira_a_classe_que_o_deck_cria() -> None:
    """O deck nomeia o balão `deck-tooltip`, não `tooltip`. CSS que não casa
    não dá erro, só não faz nada — por isso o teste é sobre o nome da classe."""
    html = (mapa_componente.DIRETORIO / "index.html").read_text(encoding="utf-8")
    assert ".deck-tooltip" in html
    assert "\n  .tooltip {" not in html, "a regra morta voltou"


def test_o_tooltip_fica_a_esquerda_do_ponteiro() -> None:
    """Posição fixa, não calculada: medir a caixa renderizada e virar o balão
    para o lado que coubesse piscava a cada movimento do mouse."""
    html = (mapa_componente.DIRETORIO / "index.html").read_text(encoding="utf-8")
    assert "translate(calc(-100% - 14px), 12px)" in html

    js = (mapa_componente.DIRETORIO / "mapa.js").read_text(encoding="utf-8")
    assert "requestAnimationFrame" not in js, "o reposicionamento que piscava voltou"


def test_o_mapa_limita_a_altura_pela_largura() -> None:
    """A altura vem do Python, que não sabe a largura do aparelho. O componente
    mede a própria largura e põe um teto. Só limita, nunca aumenta: em tela de
    trabalho a altura do Python continua valendo."""
    js = (mapa_componente.DIRETORIO / "mapa.js").read_text(encoding="utf-8")
    assert "function alturaUtil" in js
    assert "Math.min(pedida" in js, "o teto tem de limitar, não substituir"


def test_a_roda_do_mouse_nao_da_zoom_no_mapa() -> None:
    """Rolar a página com o cursor sobre o mapa não pode virar zoom. Substitui o
    `script_travar_zoom`, que existia para o `st.pydeck_chart`."""
    js = (mapa_componente.DIRETORIO / "mapa.js").read_text(encoding="utf-8")
    assert "scrollZoom: false" in js


# ---------------------------------------------------------------------------
# Valor ausente: o `NaN` que deixava o mapa parado ao escolher Cura/Abandono
# ---------------------------------------------------------------------------


def _json_estrito(texto: str) -> dict:
    """Parse que recusa `NaN`/`Infinity` como o `JSON.parse` do navegador."""

    def recusa(constante: str):
        raise ValueError(f"não é JSON válido: {constante}")

    return json.loads(texto, parse_constant=recusa)


def test_todas_as_ras_sem_valor_tambem_nao_quebra(duas_ras) -> None:
    desenho, escala = _deck(duas_ras, [float("nan")] * 3)
    _json_estrito(desenho.to_json())
    assert not escala.rotulos


