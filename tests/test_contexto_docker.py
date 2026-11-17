"""O contexto de build: o que o `Dockerfile` copia e o que o `.dockerignore` barra.

Roda **sem Docker**. O erro que este arquivo existe para pegar é silencioso até
o build: um padrão novo no `.dockerignore` que engole um arquivo que o
`Dockerfile` copia (foi o caso de `scripts/`, que barra o script das metatags
que o próprio `Dockerfile` roda) só aparece como `COPY failed` na VM, ou pior —
como um painel sem a bandeira, porque o `COPY assets/` não achou nada.

O casador de padrões é uma aproximação da semântica do Docker: `*` e `?` não
cruzam `/`, `**` cruza, um padrão casa o caminho **ou qualquer diretório pai**
dele, `!` reinclui, e vale a última linha que casar.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


# --- o casador -------------------------------------------------------------


def _regex(padrao: str) -> re.Pattern[str]:
    p = padrao.strip("/")
    saida, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            saida += "(?:.*/)?"
            i += 3
        elif p.startswith("**", i):
            saida += ".*"
            i += 2
        elif p[i] == "*":
            saida += "[^/]*"
            i += 1
        elif p[i] == "?":
            saida += "[^/]"
            i += 1
        else:
            saida += re.escape(p[i])
            i += 1
    return re.compile(f"^{saida}$")


def _padroes() -> list[tuple[bool, re.Pattern[str]]]:
    linhas = (RAIZ / ".dockerignore").read_text(encoding="utf-8").splitlines()
    padroes = []
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        negado = linha.startswith("!")
        padroes.append((negado, _regex(linha[1:] if negado else linha)))
    return padroes


def barrado(caminho: str, padroes=None) -> bool:
    padroes = _padroes() if padroes is None else padroes
    partes = caminho.split("/")
    resultado = False
    for negado, rx in padroes:
        if any(rx.match("/".join(partes[:n])) for n in range(1, len(partes) + 1)):
            resultado = not negado
    return resultado


# --- o próprio casador ------------------------------------------------------


def test_o_casador_segue_a_semantica_do_docker() -> None:
    p = [(False, _regex("*.md")), (False, _regex("tests/")), (False, _regex("**/*.csv")),
         (False, _regex("scripts/")), (True, _regex("scripts/ok.py"))]
    assert barrado("README.md", p)
    assert not barrado("src/leia.md", p), "`*.md` só casa na raiz, como no Docker"
    assert barrado("tests/test_a.py", p), "padrão com `/` final barra o diretório inteiro"
    assert barrado("data/x/y.csv", p) and barrado("a.csv", p)
    assert barrado("scripts/outro.py", p)
    assert not barrado("scripts/ok.py", p), "`!` reinclui, e a última linha que casa vence"


# --- o que o Dockerfile copia ------------------------------------------------


def _fontes_do_dockerfile() -> list[str]:
    fontes = []
    for linha in (RAIZ / "Dockerfile").read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha.startswith("COPY "):
            continue
        tokens = [t for t in shlex.split(linha)[1:] if not t.startswith("--")]
        fontes += tokens[:-1]  # o último é o destino
    return fontes


def _arquivos(fonte: str) -> list[str]:
    caminho = RAIZ / fonte.rstrip("/")
    if caminho.is_file():
        return [fonte.rstrip("/")]
    if caminho.is_dir():
        return sorted(
            p.relative_to(RAIZ).as_posix() for p in caminho.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        )
    return []


def test_o_dockerfile_copia_codigo_componentes_e_assets() -> None:
    fontes = _fontes_do_dockerfile()
    for esperado in ("app.py", "src/", ".streamlit/", "assets/", "scripts/preparar_metatags.py"):
        assert esperado in fontes, f"o Dockerfile não copia {esperado}"


@pytest.mark.parametrize("fonte", [f for f in _fontes_do_dockerfile() if not f.startswith("data/")])
def test_o_dockerignore_nao_engole_o_que_o_dockerfile_copia(fonte: str) -> None:
    """Cada arquivo de cada `COPY` (menos `data/`, que não é versionado) tem de
    sobreviver ao `.dockerignore`."""
    arquivos = _arquivos(fonte)
    assert arquivos, f"`COPY {fonte}` não acharia nada no contexto"
    engolidos = [a for a in arquivos if barrado(a)]
    assert not engolidos, f"barrados pelo .dockerignore: {engolidos[:5]}"


def test_os_componentes_estao_no_contexto() -> None:
    """Se o `.dockerignore` barrasse `*.js` o painel subiria sem mapa e sem
    gráficos, e o `COPY src/` não reclamaria."""
    for nome in (
        # O do mapa vem dentro do wheel do cenarios-core, em `vendor/`.
        "vendor/cenarios_core-0.5.0-py3-none-any.whl",
        "src/componente_grafico/grafico.js", "src/componente_grafico/echarts.min.js",
        "src/componente_grafico/index.html",
    ):
        assert (RAIZ / nome).is_file(), nome
        assert not barrado(nome), f"{nome} barrado pelo .dockerignore"


def test_o_que_nao_deve_viajar_continua_barrado() -> None:
    for nome in (
        "data/origem/malha/df.shp", "data/origem/sinan.parquet", "dados/qualquer.csv",
        "tests/test_mapa.py", "docs/x.md", "README.md", ".env", "scripts/extrair_sinan_df.py",
        "scripts/preparar_preview.py",
    ):
        assert barrado(nome), f"{nome} deveria estar barrado"


# --- metatags e prévia ---------------------------------------------------------


def test_o_dockerfile_injeta_as_metatags_e_leva_a_previa_ao_estatico() -> None:
    texto = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    assert "preparar_metatags.py" in texto
    assert "streamlit/static/preview.png" in texto


def test_a_url_das_metatags_e_a_do_docker_compose() -> None:
    from scripts import preparar_metatags as mt

    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert "cenarios/dftb" in compose
    assert mt.URL.endswith("/cenarios/dftb/")
    assert mt.IMAGEM == mt.URL + "preview.png"


def test_injetar_poe_titulo_descricao_e_open_graph() -> None:
    from scripts import preparar_metatags as mt

    html = f"<head>{mt.ANCORA}</head>"
    novo = mt.injetar(html)
    assert mt.ANCORA not in novo and novo.count("<title>") == 1
    for marca in ("og:title", "og:description", "og:image", "twitter:card", mt.TITULO):
        assert marca in novo, marca
    assert mt.injetar(novo) == novo, "rodar duas vezes não pode duplicar nada"


def test_injetar_falha_alto_se_a_ancora_sumir() -> None:
    from scripts import preparar_metatags as mt

    with pytest.raises(mt.AncoraNaoEncontrada):
        mt.injetar("<head><title>Outra coisa</title></head>")


def test_a_ancora_existe_no_streamlit_instalado() -> None:
    """Se uma versão nova do Streamlit mudar o HTML, o build da imagem quebra.
    Melhor descobrir aqui, antes de ir para a VM."""
    import streamlit

    from scripts import preparar_metatags as mt

    indice = Path(streamlit.__file__).parent / "static" / "index.html"
    if not indice.is_file():
        pytest.skip("o Streamlit instalado não traz static/index.html")
    html = indice.read_text(encoding="utf-8")
    assert mt.ANCORA in html or "og:title" in html


def test_a_imagem_de_previa_tem_o_tamanho_do_open_graph() -> None:
    from PIL import Image

    previa = RAIZ / "assets" / "preview.png"
    assert previa.is_file(), "rode `python -m scripts.preparar_preview`"
    with Image.open(previa) as imagem:
        assert imagem.size == (1200, 630)
    # O WhatsApp descarta prévia acima de ~300 kB.
    assert previa.stat().st_size < 300 * 1024
