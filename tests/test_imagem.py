"""Abre a imagem Docker construída e confere o que foi parar dentro dela.

O `.dockerignore` diz o que **não** deve entrar. Este teste confere o que
**entrou** — são coisas diferentes: um `.dockerignore` mal escrito não dá
erro, dá uma imagem com dado nominal dentro, e ninguém descobre até alguém
abrir o tarball. Mais crítico aqui que no RecifeTB: este painel tem **duas**
fontes, e uma delas (`sinan_df_ra`) é nominal antes de
`extrair_sinan_df_geolink.py` descartar identificador — a poda tem de ter
acontecido **antes** do parquet ser copiado para a imagem, não depois.

Roda só quando a imagem existe. Sem Docker, ou sem a imagem construída, é
pulado — não é falha de código, é ausência de artefato.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

IMAGEM = "dashboard-tb-df:latest"


def _docker() -> str | None:
    return shutil.which("docker")


def _imagem_existe() -> bool:
    docker = _docker()
    if not docker:
        return False
    saida = subprocess.run(
        [docker, "image", "inspect", IMAGEM],
        capture_output=True, text=True, timeout=30,
    )
    return saida.returncode == 0


precisa_da_imagem = pytest.mark.skipif(
    not _imagem_existe(),
    reason=f"imagem {IMAGEM} não construída — `docker build -t {IMAGEM} .`",
)


def _listar(caminho: str) -> list[str]:
    """Arquivos sob ``caminho`` dentro da imagem, sem subir um container que
    fique: `--rm` e um `find` só."""
    saida = subprocess.run(
        [_docker(), "run", "--rm", "--entrypoint", "find", IMAGEM,
         caminho, "-type", "f"],
        capture_output=True, text=True, timeout=120,
    )
    if saida.returncode != 0:
        return []
    return [linha for linha in saida.stdout.splitlines() if linha]


@precisa_da_imagem
def test_nenhum_csv_ou_shapefile_dentro_da_imagem() -> None:
    """**O teste que não pode ficar vermelho.** `data/origem/` guarda o
    shapefile do Censo e os parquets crus extraídos do banco — nenhum dos
    dois tem lugar na imagem."""
    arquivos = _listar("/app")
    proibidos = [
        a for a in arquivos
        if a.lower().endswith((".csv", ".shp", ".shx", ".dbf", ".prj", ".cpg"))
    ]
    assert not proibidos, f"arquivo de origem dentro da imagem: {proibidos}"


@precisa_da_imagem
def test_pasta_de_origem_nao_existe_na_imagem() -> None:
    arquivos = _listar("/app/data")
    origem = [a for a in arquivos if "/origem/" in a]
    assert not origem, f"data/origem/ dentro da imagem: {origem[:5]}"


@precisa_da_imagem
def test_os_dados_das_duas_fontes_estao_la() -> None:
    """O contrário do anterior: dado demais é vazamento, dado de menos é
    painel em branco na VM. As duas fontes precisam estar — `sinan_df` para
    os KPIs, `sinan_df_ra` para o mapa, mais a geometria e a população."""
    arquivos = _listar("/app/data")
    assert any("/parquet/dashboard/sinan_df/" in a for a in arquivos)
    assert any("/parquet/dashboard/sinan_df_ra/" in a for a in arquivos)
    assert any(a.endswith("/parquet/dashboard/populacao_df.parquet") for a in arquivos)
    assert any(a.endswith("/parquet/dashboard/obitos_tb_df.parquet") for a in arquivos)
    assert any(a.endswith("/geo/ra.parquet") for a in arquivos)
    assert any(a.endswith("/geo/regioes_saude.parquet") for a in arquivos)
    assert any(a.endswith("/geo/df.parquet") for a in arquivos)
    # a linha "Dados até / Processado em" lê isto; sem ele a imagem não diz de quando são os números
    assert any(a.endswith("/parquet/dashboard/PROCEDENCIA.json") for a in arquivos)


@precisa_da_imagem
def test_o_microdado_geolinkado_da_imagem_nao_tem_identificador() -> None:
    """Confere o parquet **de dentro da imagem**, não o do disco local — é o
    que de fato viaja. `sinan_df_ra` é a fonte nominal antes da extração; um
    build a partir de um `data/` errado passaria no teste local
    (`test_microdado.py`) e falharia aqui."""
    script = (
        "import duckdb, glob;"
        "f = glob.glob('/app/data/parquet/dashboard/sinan_df_ra/**/*.parquet', recursive=True)[0];"
        "print(','.join(c[0] for c in duckdb.connect().execute("
        "f\"describe select * from read_parquet('{f}')\").fetchall()))"
    )
    saida = subprocess.run(
        [_docker(), "run", "--rm", "--entrypoint", "python", IMAGEM, "-c", script],
        capture_output=True, text=True, timeout=120,
    )
    assert saida.returncode == 0, saida.stderr
    colunas = {c.upper() for c in saida.stdout.strip().split(",")}
    proibidas = {
        "NM_PACIENT", "NM_MAE_PAC", "DT_NASC", "ID_CNS_SUS", "NU_PRONTUA",
        "NU_CEP", "NU_CEP2", "NU_TELEFON", "NU_DDD_TEL", "NM_LOGRADO",
        "LATITUDE", "LONGITUDE", "NU_NOTIFIC",
    }
    vazadas = sorted(colunas & proibidas)
    assert not vazadas, f"identificador no parquet da imagem: {vazadas}"


@precisa_da_imagem
def test_o_codigo_de_preparo_nao_viaja() -> None:
    """`scripts/` lê o banco e o shapefile de origem. Não tem o que fazer
    numa imagem que não os tem — e é uma pista a menos sobre onde moram."""
    arquivos = _listar("/app")
    assert not any("/scripts/" in a for a in arquivos)
    assert not any("/tests/" in a for a in arquivos)


@precisa_da_imagem
def test_sobe_e_responde_saudavel() -> None:
    """Sobe o container de verdade (não `--rm` de um comando só) e espera o
    endpoint de saúde do Streamlit responder — a mesma verificação que o
    `HEALTHCHECK` da imagem faz, exercitada aqui antes de ir para a VM."""
    import time

    nome = "dftb-teste-imagem"
    subprocess.run([_docker(), "rm", "-f", nome], capture_output=True)
    try:
        subida = subprocess.run(
            [_docker(), "run", "-d", "--name", nome, "-p", "18509:8501", IMAGEM],
            capture_output=True, text=True, timeout=30,
        )
        assert subida.returncode == 0, subida.stderr

        ok = False
        for _ in range(30):
            resp = subprocess.run(
                [_docker(), "exec", nome, "curl", "-fsS", "http://localhost:8501/_stcore/health"],
                capture_output=True, text=True, timeout=10,
            )
            if resp.returncode == 0 and resp.stdout.strip() == "ok":
                ok = True
                break
            time.sleep(2)
        assert ok, "healthcheck não respondeu 'ok' em 60s"
    finally:
        subprocess.run([_docker(), "rm", "-f", nome], capture_output=True)


@precisa_da_imagem
def test_os_componentes_e_a_previa_estao_na_imagem() -> None:
    """`COPY src/` não reclama de arquivo que um `.dockerignore` novo engoliu:
    o painel subiria sem mapa e sem gráficos. Confere o que **entrou**."""
    # O componente do mapa vem dentro do cenarios-core, instalado do wheel.
    arquivos = (
        _listar("/app/src")
        + _listar("/usr/local/lib/python3.13/site-packages/cenarios_core")
        + _listar("/usr/local/lib/python3.13/site-packages/streamlit/static")
    )
    for esperado in (
        "componente_mapa/mapa.js", "componente_mapa/deck.min.js", "componente_mapa/deck-json.min.js",
        "componente_grafico/grafico.js", "componente_grafico/echarts.min.js",
    ):
        assert any(a.endswith("/" + esperado) for a in arquivos), f"{esperado} fora da imagem"
    assert any(a.endswith("/static/preview.png") for a in arquivos), "prévia fora do estático"
    assert _listar("/app/assets"), "assets/ fora da imagem (a bandeira do DF não chegaria à VM)"


@precisa_da_imagem
def test_o_html_da_imagem_se_anuncia_como_o_painel() -> None:
    """O build injeta título e Open Graph no HTML do Streamlit. Sem isso, o link
    compartilhado no WhatsApp aparece como "Streamlit"."""
    script = (
        "import pathlib, streamlit;"
        "print((pathlib.Path(streamlit.__file__).parent / 'static' / 'index.html').read_text(encoding='utf-8'))"
    )
    saida = subprocess.run(
        [_docker(), "run", "--rm", "--entrypoint", "python", IMAGEM, "-c", script],
        capture_output=True, text=True, timeout=120,
    )
    assert saida.returncode == 0, saida.stderr
    assert "og:title" in saida.stdout and "Distrito Federal" in saida.stdout
    assert "<title>Streamlit</title>" not in saida.stdout
