"""Pré-processa a geometria do Distrito Federal uma vez, em disco.

**35 Regiões Administrativas.** Fonte da malha: a camada oficial "Regiões
Administrativas do Distrito Federal em 2026" do IPEDF
(`catalogo.ipe.df.gov.br/layers/geonode:regioes_administrativas`, domínio
público), em `data/origem/malha_ipedf/`. Ela inclui **Arapoanga** (RA-XXXIV,
Planaltina) e **Água Quente** (RA-XXXV, Recanto das Emas), criadas por leis
publicadas no DODF em 22/12/2022. A malha de subdistritos do Censo 2022 (IBGE),
usada até 08/out/2026, tem só 33 e não as separa.

Três camadas saem daqui:

- ``ra.parquet`` — as 35 Regiões Administrativas, a unidade do painel
- ``regioes_saude.parquet`` — as Regiões de Saúde, dissolvidas a partir das RA
- ``df.parquet`` — o contorno do Distrito Federal

**A população por RA vem do Censo 2022, somada por setor censitário.** O IBGE
não publica população por RA, e as duas RAs novas não existem na malha de
subdistritos. A saída é a malha de **setores censitários** do DF
(`data/origem/setores/DF_setores_CD2022.shp`, 5.418 setores), que traz `v0001`
— população residente do setor. Cada setor é atribuído à RA que contém o seu
**ponto representativo** (um ponto garantidamente dentro do polígono do
setor); os setores cujo ponto cai fora de toda RA — a divisa de uma malha não
coincide com a da outra — vão para a RA mais próxima, e o script diz quantos
foram. A soma tem de ser 2.817.381, a população oficial do DF no Censo 2022, e
o script para se não for. Sai como `populacao_censo2022` em `ra.parquet`, e
somada por Região de Saúde em `regioes_saude.parquet`. Ver
`src/data/microdado_ra.py` para como isso vira incidência por ano (o Censo é um
retrato de 2022 só; os outros anos usam a **proporção** de cada RA aplicada à
população anual do DF inteiro).

É aproximação por ponto: um setor que atravessa a divisa de duas RAs entra
inteiro em uma. Para as RAs grandes isso é ruído; para as pequenas, como
Arapoanga e Água Quente, o erro relativo é maior — está registrado em
`tests/paridade/excecoes.md`.

**As Regiões de Saúde são dissolvidas a partir das RA já simplificadas**, e
não lidas de uma malha própria — não existe uma. O mapeamento RA -> Região de
Saúde vem de `RA_PARA_REGIAO_SAUDE` (`src/data/config.py`).

Uso::

    python -m scripts.preparar_geometria
"""

from __future__ import annotations

import time
from pathlib import Path

import geopandas as gpd
import topojson as tp

from src.data import config
from src.data.escopo import chave_ra

#: CRS métrico para medir área e atribuir setor a RA. SIRGAS 2000 / UTM 23S
#: cobre o DF sem distorção relevante.
CRS_AREA = "EPSG:31983"

#: CRS de saída. O deck.gl desenha em graus.
CRS_SAIDA = "EPSG:4326"

#: Divisor da tolerância — o DF tem ~90 km de largura; 1/2000 dá ~45 m, abaixo
#: do que se percebe numa RA deste tamanho.
DIVISOR = 2000

#: População residente do DF no Censo 2022 (IBGE). A soma dos setores tem de
#: bater, ou algum setor ficou de fora ou foi contado duas vezes.
POPULACAO_DF_CENSO_2022 = 2_817_381

#: Nomes de exibição que o `title()` não acerta: sigla, algarismo romano,
#: acento que o IPEDF não grafa, e a barra de Sol Nascente/Pôr do Sol. As
#: chaves são as de `chave_ra`.
_NOME_ESPECIAL = {
    "SOL NASCENTE/POR DO SOL": "Sol Nascente/Pôr do Sol",
    "AGUA QUENTE": "Água Quente",
    "SIA": "SIA",
    "SCIA": "SCIA",
    "SOBRADINHO II": "Sobradinho II",
    "RIACHO FUNDO II": "Riacho Fundo II",
}
_PALAVRAS_MENORES = {" De ": " de ", " Da ": " da ", " Do ": " do ", " Das ": " das ", " Dos ": " dos "}


def _nome_exibicao(nome: str, chave: str) -> str:
    if chave in _NOME_ESPECIAL:
        return _NOME_ESPECIAL[chave]
    texto = " ".join(str(nome).split()).title()
    for velho, novo in _PALAVRAS_MENORES.items():
        texto = texto.replace(velho, novo)
    return texto


def simplificar(geo: gpd.GeoDataFrame, divisor: int) -> tuple[gpd.GeoDataFrame, float]:
    """Simplifica preservando as fronteiras compartilhadas — ver o mesmo
    procedimento em `paineis/RecifeTB/scripts/preparar_geometria.py` para o
    porquê de ser topológico e não `shapely.simplify` por feição."""
    xmin, _, xmax, _ = geo.total_bounds
    tolerancia = (xmax - xmin) / divisor
    if tolerancia <= 0:
        return geo, 0.0

    area_antes = geo.to_crs(CRS_AREA).area.sum()

    if len(geo) < 2:
        saida = geo.copy()
        saida["geometry"] = saida.geometry.simplify(tolerancia, preserve_topology=True)
    else:
        topologia = tp.Topology(geo, prequantize=False, shared_coords=False)
        saida = topologia.toposimplify(tolerancia).to_gdf()
        saida = saida.set_crs(geo.crs, allow_override=True)
        saida = saida[list(geo.columns)]

    invalidas = ~saida.geometry.is_valid
    if invalidas.any():
        saida.loc[invalidas, "geometry"] = saida.loc[invalidas, "geometry"].buffer(0)

    area_depois = saida.to_crs(CRS_AREA).area.sum()
    erro = abs(area_depois - area_antes) / area_antes * 100 if area_antes else 0.0
    return saida, erro


def _tamanho(caminho: Path) -> float:
    return caminho.stat().st_size / 1e6


def _ler_ra_ipedf(origem: Path) -> gpd.GeoDataFrame:
    """As 35 RAs do IPEDF, com chave e nome de exibição, em CRS métrico."""
    caminho = origem / "malha_ipedf" / "regioes_administrativas.shp"
    if not caminho.is_file():
        raise FileNotFoundError(
            f"{caminho} não encontrado. Baixe a camada `regioes_administrativas` "
            f"(SHAPE-ZIP) de catalogo.ipe.df.gov.br e extraia em {caminho.parent}."
        )
    # UTF-8 explícito: o shapefile do IPEDF não traz `.cpg`, e sem ele o
    # geopandas lê em Latin-1 e "Núcleo" vira "NAºcleo" — chave errada, sem erro.
    geo = gpd.read_file(caminho, encoding="utf-8").to_crs(CRS_AREA)
    chave = geo["ra_nome"].map(chave_ra)
    return gpd.GeoDataFrame(
        {
            "ra_chave": chave,
            "ra_nome": [_nome_exibicao(n, c) for n, c in zip(geo["ra_nome"], chave, strict=True)],
            "ra_codigo": geo["ra_codigo"].astype(str),
            "regiao_saude": chave.map(config.RA_PARA_REGIAO_SAUDE),
        },
        geometry=geo.geometry,
        crs=CRS_AREA,
    )


def _populacao_por_ra(ra: gpd.GeoDataFrame, origem: Path) -> tuple[dict[str, int], int, int]:
    """População do Censo 2022 por RA, somando os setores cujo ponto
    representativo cai nela. Devolve ``(população por chave, setores atribuídos
    pela divisa mais próxima, população desses setores)``."""
    caminho = origem / "setores" / "DF_setores_CD2022.shp"
    if not caminho.is_file():
        raise FileNotFoundError(
            f"{caminho} não encontrado. Baixe `DF_setores_CD2022.zip` do IBGE "
            f"(Censo 2022, malha de setores censitários do DF) e extraia em "
            f"{caminho.parent}."
        )
    setores = gpd.read_file(caminho).to_crs(CRS_AREA)
    setores["populacao"] = setores["v0001"].fillna(0).astype("int64")
    pontos = setores[["populacao", "geometry"]].copy()
    pontos["geometry"] = setores.geometry.representative_point()

    dentro = gpd.sjoin(pontos, ra[["ra_chave", "geometry"]], how="left", predicate="within")
    dentro = dentro[~dentro.index.duplicated(keep="first")]
    sem_ra = dentro["ra_chave"].isna()

    por_divisa = 0
    pop_divisa = 0
    if sem_ra.any():
        proximos = gpd.sjoin_nearest(
            pontos.loc[sem_ra[sem_ra].index], ra[["ra_chave", "geometry"]], how="left"
        )
        proximos = proximos[~proximos.index.duplicated(keep="first")]
        dentro.loc[proximos.index, "ra_chave"] = proximos["ra_chave"]
        por_divisa = len(proximos)
        pop_divisa = int(proximos["populacao"].sum())

    soma = dentro.groupby("ra_chave")["populacao"].sum()
    return {str(k): int(v) for k, v in soma.items()}, por_divisa, pop_divisa


def main() -> None:
    origem = config.data_dir() / "origem"
    destino = config.geo_dir()
    destino.mkdir(parents=True, exist_ok=True)

    inicio = time.perf_counter()
    ra = _ler_ra_ipedf(origem)

    if ra["ra_chave"].duplicated().any():
        repetidos = sorted(ra.loc[ra["ra_chave"].duplicated(), "ra_chave"])
        raise SystemExit(
            f"Chave de RA repetida: {repetidos}. "
            f"Um join por RA duplicaria linhas — conserte `chave_ra`."
        )
    sem_regiao = sorted(ra.loc[ra["regiao_saude"].isna(), "ra_chave"])
    if sem_regiao:
        raise SystemExit(
            f"RA sem Região de Saúde em `config.RA_PARA_REGIAO_SAUDE`: {sem_regiao}. "
            f"Sem ela a RA some do dissolve das Regiões de Saúde."
        )

    populacao, por_divisa, pop_divisa = _populacao_por_ra(ra, origem)
    total = sum(populacao.values())
    if total != POPULACAO_DF_CENSO_2022:
        raise SystemExit(
            f"A população somada dos setores é {total:,}, e o Censo 2022 do DF tem "
            f"{POPULACAO_DF_CENSO_2022:,}. Algum setor ficou de fora ou foi contado duas vezes."
        )
    sem_populacao = sorted(set(ra["ra_chave"]) - set(populacao))
    if sem_populacao:
        raise SystemExit(f"RA sem nenhum setor (população zero): {sem_populacao}.")
    ra["populacao_censo2022"] = ra["ra_chave"].map(populacao).astype("int64")
    print(
        f"população: {total:,} habitantes em {len(ra)} RAs "
        f"(setores pela divisa mais próxima: {por_divisa}, {pop_divisa:,} hab. = "
        f"{pop_divisa / total * 100:.2f}%)"
    )

    ra = ra.to_crs(CRS_SAIDA)
    ra, erro = simplificar(ra, DIVISOR)
    caminho = destino / "ra.parquet"
    ra.to_parquet(caminho)
    print(f"ra             {len(ra):>3} feições  {_tamanho(caminho):.3f} MB  "
          f"erro de área {erro:.3f}%")

    regioes = ra.dissolve(
        by="regiao_saude", as_index=False, aggfunc={"populacao_censo2022": "sum"}
    )[["regiao_saude", "populacao_censo2022", "geometry"]]
    caminho = destino / "regioes_saude.parquet"
    regioes.to_parquet(caminho)
    print(f"regioes_saude  {len(regioes):>3} feições  {_tamanho(caminho):.3f} MB")

    contorno = ra.dissolve()[["geometry"]]
    caminho = destino / "df.parquet"
    contorno.to_parquet(caminho)
    print(f"df             {len(contorno):>3} feição   {_tamanho(caminho):.3f} MB")

    print(f"em {time.perf_counter() - inicio:.1f}s")


if __name__ == "__main__":
    main()
