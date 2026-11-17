# Imagem do painel de tuberculose do Distrito Federal.
#
# Autohospedada na VM `wrdocker2`, atrás de nginx — mesmo esquema do
# `tbrecife`/`sinan`: o subcaminho da URL é configurável por
# `BASE_URL_PATH`, e os dados **entram** na imagem (não é volume montado).
#
# Duas fontes de dado, ambas dentro: `sinan_df` (silver.tuberculose, DF
# inteiro) e `sinan_df_ra` (dados_geolink, nominal na origem — já sem
# identificador depois de `extrair_sinan_df_geolink.py`, ver
# tests/test_imagem.py). O CSV/shapefile de origem não entra — `.dockerignore`
# barra `data/origem/`.

FROM python:3.13-slim

WORKDIR /app

# curl     -> healthcheck
# libgomp1 -> DuckDB usa OpenMP para paralelizar
# geopandas não precisa de GDAL do sistema: pyogrio, shapely e pyproj trazem
# GDAL, GEOS e PROJ nas próprias wheels manylinux.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Do lock, não do requirements.txt: aquele declara faixas: dois builds do
# mesmo commit poderiam subir versões diferentes. O lock tem as versões
# exatas com que a suíte passou (`requirements.lock.txt`, gerado num venv
# limpo — só as dependências de runtime, sem as ferramentas de
# desenvolvimento do `.venv` compartilhado com o sinan).
COPY requirements.lock.txt .
# O lock aponta para o wheel do cenarios-core em `vendor/`: vem antes do
# `pip install`, e o build não precisa de rede (nem do GitHub) para o core.
COPY vendor/ vendor/
RUN pip install --no-cache-dir -r requirements.lock.txt

# Título, descrição e Open Graph no HTML que o Streamlit serve. Sem isto, o
# link compartilhado no WhatsApp aparece como "Streamlit" e o domínio: o
# `page_title` é aplicado por JavaScript depois da carga, e nenhum rastreador
# de prévia espera o JS rodar.
#
# O script falha o build se a âncora sumir numa versão nova do Streamlit, em
# vez de gerar em silêncio uma imagem que volta a se anunciar errado.
COPY scripts/preparar_metatags.py /tmp/
RUN python /tmp/preparar_metatags.py && rm /tmp/preparar_metatags.py

# A prévia tem de sair pelo mesmo caminho do painel, então vai para o estático
# do Streamlit: é de lá que o servidor serve tudo sob `/cenarios/dftb/`.
COPY assets/preview.png /usr/local/lib/python3.13/site-packages/streamlit/static/preview.png

# Código. `assets/` leva a bandeira do DF da faixa de identificação — sem ela
# na imagem a faixa degrada para duas colunas, sem aviso nenhum.
COPY app.py .
COPY src/ src/
COPY .streamlit/ .streamlit/
COPY assets/ assets/

# Dados — só o que a aplicação lê. `data/origem/` está barrado no
# `.dockerignore` e não existe neste contexto de build.
COPY data/parquet/ data/parquet/
COPY data/geo/     data/geo/

# Onde os dados estão e qual doença o pack resolve.
ENV SINAN_DATA_DIR=/app/data \
    SINAN_DOENCA=tuberculose \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Caminho sob o qual o painel é servido. Vazio serve na raiz:
#   http://host:8501/
# Com `BASE_URL_PATH=cenarios/dftb` serve em
#   http://host:8501/cenarios/dftb/
# Sem barra inicial nem final — o Streamlit acrescenta.
ENV BASE_URL_PATH=""

EXPOSE 8501

# O healthcheck precisa do mesmo subcaminho do painel: sob `baseUrlPath`, o
# Streamlit responde em `/<caminho>/_stcore/health` e a raiz dá 404.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl --fail "http://localhost:8501/${BASE_URL_PATH:+$BASE_URL_PATH/}_stcore/health" || exit 1

# `sh -c` e não a forma exec: é o shell que expande `BASE_URL_PATH`. A forma
# exec passaria a string literal `${BASE_URL_PATH}` ao Streamlit.
ENTRYPOINT ["sh", "-c", "exec streamlit run app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.baseUrlPath=\"$BASE_URL_PATH\" \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=true \
    --browser.gatherUsageStats=false"]
