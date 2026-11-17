"""Extrai o SINAN-TB do DF **por Região Administrativa**, da tabela nominal
`dados_geolink."DF_geo_TB"` (banco `cenarios_ai`).

**Diferente de `extrair_sinan_df.py`**, que lê `silver.tuberculose` (sem
identificador na origem, mas também sem geografia abaixo de município).
`dados_geolink."DF_geo_TB"` é dado **nominal** — 146 colunas, entre elas
`NM_PACIENT`, `NM_MAE_PAC`, `ID_CNS_SUS`, endereço completo e
latitude/longitude geocodificada — mas é a única fonte com RA por caso
(`Regiao_adm`). Este script existe para ligar as duas coisas sem que o
identificador atravesse: mesma disciplina do `preparar_microdado.py` do
RecifeTB — a lista `COLUNAS` abaixo é uma **permissão explícita**, o que não
está nela não sai da consulta.

**RA por coordenada, só para as duas RAs novas, e só em memória.** O rótulo
`Regiao_adm` do banco tem as 33 RAs de antes de dez/2022: gente de Arapoanga
(RA-XXXIV) vem como "PLANALTINA", e de Água Quente (RA-XXXV), como "RECANTO
DAS EMAS". `LATITUDE`/`LONGITUDE` são lidas aqui para corrigir isso e
**descartadas na mesma função** (`atribuir_ra`): nunca entram em `saida`, nem
no parquet — `IDENTIFICADORES_DESCARTADOS` continua valendo, e o teste confere
o arquivo gravado. A regra é conservadora: o rótulo vale, **exceto** quando
(1) o rótulo é a RA-mãe, (2) a coordenada cai no polígono da RA nova (camada
do IPEDF) e (3) o ponto é preciso — não repetido
`config.PONTO_REPETIDO_MINIMO` vezes ou mais. Medido em 08/out/2026: 119
casos em Arapoanga (107 pontos distintos) e 5 em Água Quente (5 pontos). O
ponto mais repetido (278 casos) é geocodificação genérica e cai em
Planaltina mesmo; **não** se usa coordenada para recuperar os 105 casos
"IGNORADO" (64 estão num único ponto genérico, no Plano Piloto) nem para
mover os ~400 casos cujo rótulo e coordenada discordam por outro motivo (168
rotulados Santa Maria com ponto em Samambaia) — nesses a coordenada não é
mais confiável que o rótulo. Ver `tests/paridade/excecoes.md`.

**Duas transformações acontecem aqui, não depois:**

1. **RA e Região de Saúde.** `Regiao_adm` vira `ra_chave`
   (`escopo.chave_ra`, a mesma normalização que a geometria usa) e
   `Regiao_sau1` vira `regiao_saude`, mapeado por
   `config.RA_PARA_REGIAO_SAUDE` — não é o texto bruto do banco, porque
   RIACHO FUNDO e SCIA vêm como "Ignorado" ali e a decisão foi
   deixá-las de fora de qualquer Região de Saúde (ver `config.py`).
2. **Decodificação de código SINAN.** As colunas clínicas chegam como
   inteiro (`FORMA=1`, `HIV=2`...); `sinan_dict` (parquet local de
   `paineis/sinan`, tabela `doenca/variavel/valor -> valor_lbl`, construída
   pelo painel nacional a partir do próprio SINAN) decodifica para o mesmo
   texto que o `silver.tuberculose` do manaustb já trazia pronto — assim
   `src/data/microdado.py` e `src/doencas/tuberculose.py` não precisam saber
   de onde vieram as categorias. Colunas sem cobertura no dicionário (ver
   `SEM_DICIONARIO` abaixo) ficam de fora desta extração, e não com código
   bruto disfarçado de rótulo. **Exceção: `SITUA_ENCE`.** O `valor_lbl` do
   `sinan_dict` para esse campo é reagrupado (Favorável/Desfavorável/Não
   avaliado) — a mesma armadilha que o `docs/desenvolvimento.md` do
   painel nacional (sinan) documenta na regra 5. Aqui ele é decodificado à parte, com o domínio
   oficial do SINAN (`SITUA_ENCE` no módulo), não pelo dicionário.

**Filtro por residência, não por notificação — bug encontrado e corrigido em
11/set/2026.** A primeira versão deste script lia a tabela inteira, sem
filtrar `ID_MN_RESI`. `dados_geolink."DF_geo_TB"` é filtrada por
**notificação** no DF (`SG_UF_NOT=53` em 100% das linhas), não por
residência: 1.191 das 7.551 linhas (15,8%) são de gente notificada no DF mas
residente em 186 municípios de outros estados — casos de referência, comuns
numa capital com rede de saúde terciária. `silver.tuberculose` (a fonte dos
KPIs de topo) filtra por `estado_residencia`/`municipio_residencia`, então
comparar as duas sem o mesmo filtro dava 2024 com 667×569 — 17% de gente
que não é do recorte deste painel. Com `ID_MN_RESI = 530010`, a mesma
comparação cai para 611×571 (7%) — ver `tests/paridade/excecoes.md` para o
que resta e por quê.

Deduplicação: `NU_NOTIFIC` repete (6.360 linhas residentes do DF, 6.325
chaves distintas em 11/set/2026, já com o filtro de residência) — mesmo
critério do RecifeTB, uma linha por notificação
(`row_number() PARTITION BY NU_NOTIFIC ORDER BY DT_NOTIFIC`).

Corte de ano: nenhum. A tabela já para em 2024 (não tem 2025), e 2024 tem
6,3% de `SITUA_ENCE` nulo — bem abaixo do que motivou o corte em
`extrair_sinan_df.py` (23,7% em `silver.tuberculose`, por ser dataset
diferente com cobertura de digitação diferente).

Uso::

    python -m scripts.extrair_sinan_df_geolink
    python -m scripts.extrair_sinan_df_geolink --destino data/origem/sinan_df_ra.parquet
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data import banco  # noqa: E402
from data import config  # noqa: E402
from data.escopo import chave_ra  # noqa: E402

#: Caminho do dicionário de códigos do painel nacional (`paineis/sinan`) —
#: fora deste projeto, mas na mesma máquina (ver memória "dashboard-sinan-pe
#: é desenvolvido neste PC"). Só leitura, e só nesta extração — o app deste
#: painel nunca lê daqui.
SINAN_DICT = (
    Path(__file__).resolve().parents[2] / "sinan" / "data" / "parquet"
    / "dashboard" / "sinan_dict" / "**" / "*.parquet"
)

#: `SINAN_DICT_DIR` aponta para a **pasta** `sinan_dict`, quando o layout
#: irmão (`../sinan/`) não existe — por exemplo, numa máquina onde só há a
#: cópia do `dashboard-sinan-pe`. Sem a variável, vale o caminho acima.
if os.environ.get("SINAN_DICT_DIR"):
    SINAN_DICT = Path(os.environ["SINAN_DICT_DIR"]) / "**" / "*.parquet"

#: Colunas de identificador — nunca atravessam. Registradas, não só
#: omitidas, para que ninguém as reintroduza achando que foi esquecimento.
IDENTIFICADORES_DESCARTADOS = (
    "NM_PACIENT", "NM_MAE_PAC", "ID_CNS_SUS", "NU_PRONTUA", "NU_PRONT_A",
    "NU_CEP", "NU_CEP2", "NU_TELEFON", "NU_DDD_TEL",
    "NM_LOGRADO", "NU_NUMERO", "NM_COMPLEM", "NM_REFEREN", "ID_LOGRADO",
    "address", "address2", "address3", "ENDERECO_CNEFE",
    "LATITUDE", "LONGITUDE", "CD_SETOR", "FONETICA_N", "SOUNDEX",
    "NU_NOTIFIC", "DT_NASC",
)

#: Coluna bruta do SINAN -> nome decodificado. O nome de saída é o mesmo que
#: `silver.tuberculose` usa (ver `extrair_sinan_manaus.py`/`extrair_sinan_df.py`),
#: para `src/doencas/tuberculose.py` e `src/data/microdado.py` não precisarem
#: de um segundo dicionário de nomes por fonte.
DECODIFICAR = {
    "CS_RACA": "raca_cor",
    "CS_ESCOL_N": "escolaridade",
    "CS_GESTANT": "gestante",
    "POP_RUA": "populacao_situacao_rua",
    "POP_LIBER": "populacao_privada_liberdade",
    "POP_IMIG": "populacao_imigrante",
    "POP_SAUDE": "profissional_saude",
    "BENEF_GOV": "beneficiario_programa_governo",
    "FORMA": "forma_clinica",
    "HIV": "resultado_hiv",
    "AGRAVAIDS": "agravo_aids",
    "AGRAVALCOO": "agravo_alcoolismo",
    "AGRAVDIABE": "agravo_diabetes",
    "AGRAVDOENC": "agravo_doenca_mental",
    "AGRAVOUTRA": "agravo_outros",
    "BACILOSC_E": "baciloscopia_escarro",
    "CULTURA_ES": "cultura_escarro",
    "HISTOPATOL": "histopatologia",
    "RAIOX_TORA": "raio_x_torax",
    "TRATSUP_AT": "tratamento_diretamente_observado_atual",
    "TRANSF": "tipo_transferencia",
}

#: `SITUA_ENCE` **não** entra em `DECODIFICAR`/`sinan_dict` de propósito —
#: `sinan_dict.valor_lbl` reagrupa este campo em "Favorável"/"Desfavorável"/
#: "Não avaliado" (conferido em 11/set/2026: código 1 e código 9, Cura e
#: Abandono primário, os dois viram categorias diferentes de qualquer
#: encerramento clínico específico). É a mesma armadilha que o
#: `docs/desenvolvimento.md` do sinan documenta na regra 5 ("nunca por `valor_lbl`" para
#: `SITUA_ENCE`) — usar o dicionário aqui daria `cura_pct`/`abandono_pct`
#: calculados sobre a categoria errada, sem erro nenhum aparecer.
#:
#: O domínio abaixo é o oficial do SINAN/DataSUS para tuberculose, o mesmo
#: que `_ENCERRAMENTOS_VALIDOS` em `src/data/kpis.py` já espera — conferido
#: contra a distribuição bruta (`SITUA_ENCE=1` é 57% das 7.429 linhas com
#: valor, plausível para "Cura"; nenhum código fora de 0–10).
SITUA_ENCE = {
    "1": "Cura",
    "2": "Abandono",
    "3": "Obito por TB",
    "4": "Obito por outras causas",
    "5": "Transferencia",
    "6": "TB-DR",
    "7": "Mudanca de diagnostico",
    "8": "Mudanca de esquema",
    "9": "Abandono primario",
    "10": "Falencia",
    "0": "Nao informado",
}

#: Colunas clínicas **sem** entrada em `sinan_dict` para TUBERCULOSE, medido
#: em 11/set/2026 (`TRAT_SUPER`, `RIFAMPICIN`, `ISONIAZIDA`, `AGRAVDROGA`,
#: `AGRAVTABAC`, `TEST_MOLEC` têm zero linhas no dicionário). Ficam de fora
#: desta extração — mostrar um código bruto como se fosse rótulo (ex.: "1")
#: é pior que omitir a variável. Reentram no dia em que o dicionário nacional
#: cobrir essas colunas para TB; nada no core impede isso, é só preencher
#: `DECODIFICAR` e tirar daqui.
SEM_DICIONARIO = (
    "TRAT_SUPER", "RIFAMPICIN", "ISONIAZIDA", "AGRAVDROGA", "AGRAVTABAC",
)

#: `TRATAMENTO` (tipo de entrada) tem o dicionário **incompleto**: só traz
#: Caso novo, Não sabe e Pós-óbito, e 137 das 610 notificações de 2024 saíam
#: sem tipo — entre elas todo reingresso após abandono, que o Boletim da SES-DF
#: não conta como caso novo. Domínio oficial da ficha do SINAN-TB, no mesmo
#: grafia de `silver.tuberculose` (acentos fora), que é o que `kpis.py` espera.
TIPO_ENTRADA = {
    "1": "Caso novo",
    "2": "Recidiva",
    "3": "Reingresso apos abandono",
    "4": "Nao sabe",
    "5": "Transferencia",
    "6": "Pos-obito",
}

#: `TEST_MOLEC` (teste rápido molecular, TRM-TB) — sem entrada no dicionário,
#: domínio oficial da ficha. Sustenta a "proporção que realizou o TRM" e a
#: confirmação laboratorial do Boletim (Gráfico 2).
TESTE_MOLECULAR = {
    "1": "Detectavel sensivel a Rifampicina",
    "2": "Detectavel resistente a Rifampicina",
    "3": "Nao detectavel",
    "4": "Inconclusivo",
    "5": "Nao realizado",
}

#: Contatos do caso: identificados (`NU_CONTATO`) e examinados (`NU_COMU_EX`).
#: Numéricos, mantidos como vêm — sustentam o Gráfico 6 do Boletim.
CONTATOS = {"NU_CONTATO": "contatos_identificados", "NU_COMU_EX": "contatos_examinados"}

#: Colunas mantidas sem decodificar — já são o tipo certo (data, texto livre,
#: geografia já resolvida) ou serão transformadas por conta própria
#: (`NU_IDADE_N`, ver `_idade_anos`).
COLUNAS_DIRETAS = (
    "NU_ANO", "DT_NOTIFIC", "DT_DIAG", "DT_INIC_TR", "DT_ENCERRA",
    "CS_SEXO", "NU_IDADE_N", "Regiao_adm", "Regiao_sau1", "SITUA_ENCE",
    "TRATAMENTO", "TEST_MOLEC", "NU_CONTATO", "NU_COMU_EX",
)

#: Lidas só para atribuir a RA nova e descartadas em seguida — ver `atribuir_ra`.
#: Estão em `IDENTIFICADORES_DESCARTADOS`: nunca chegam ao parquet.
COORDENADAS = ("LATITUDE", "LONGITUDE")


def _idade_anos(bruta: "pd.Series") -> "pd.Series":  # noqa: F821
    """`NU_IDADE_N` no SINAN é código posicional: 1º dígito = unidade (4 =
    anos), os 3 seguintes = valor — mesma codificação que
    `extrair_obitos_tb_df.py` decodifica para o SIM (fonte diferente, mesma
    convenção de origem DataSUS). Só ``4`` (anos) sobrevive; hora/dia/mês
    (unidades 1/2/3) e "mais de 100 anos" (5) viram nulo — a pirâmide etária
    não precisa aproximar essas unidades a zero, um caso sem idade em anos
    completos some da pirâmide em vez de contar como recém-nascido.
    """
    import pandas as pd

    s = bruta.astype("string").str.zfill(4)
    unidade = s.str[0]
    valor = pd.to_numeric(s.str[1:], errors="coerce")
    return valor.where(unidade == "4")


def _carregar_dicionario() -> "pd.DataFrame":  # noqa: F821
    import duckdb

    con = duckdb.connect()
    return con.execute(
        f"""
        SELECT variavel, valor, valor_lbl
        FROM read_parquet('{SINAN_DICT.as_posix()}')
        WHERE doenca = 'TUBERCULOSE'
        """
    ).fetchdf()


def poligonos_ra() -> "gpd.GeoDataFrame":  # noqa: F821
    """As 35 RAs do IPEDF em CRS métrico, só ``chave`` e geometria. Sem
    simplificar: a atribuição usa o polígono oficial, não o do mapa."""
    import geopandas as gpd

    caminho = (
        Path(__file__).resolve().parents[1] / "data" / "origem" / "malha_ipedf"
        / "regioes_administrativas.shp"
    )
    if not caminho.is_file():
        # Sem o shapefile do IPEDF (que não é versionado nem vai na imagem),
        # a malha já simplificada de `data/geo/ra.parquet` serve: a atribuição só
        # decide quem está dentro das RAs novas, e a fronteira simplificada
        # muda no máximo casos de beira — comparado em out/2026, 0 diferença.
        simplificada = Path(__file__).resolve().parents[1] / "data" / "geo" / "ra.parquet"
        if simplificada.is_file():
            import geopandas as gpd

            geo = gpd.read_parquet(simplificada).to_crs("EPSG:31983")
            return geo[["ra_chave", "geometry"]].rename(columns={"ra_chave": "chave"})
        raise SystemExit(
            f"{caminho} não encontrado. Baixe a camada `regioes_administrativas` do "
            f"IPEDF (catalogo.ipe.df.gov.br) — ver `scripts/preparar_geometria.py`."
        )
    # UTF-8 explícito: sem `.cpg` o geopandas lê Latin-1 e a chave sai errada.
    geo = gpd.read_file(caminho, encoding="utf-8").to_crs("EPSG:31983")
    geo["chave"] = geo["ra_nome"].map(chave_ra)
    return geo[["chave", "geometry"]]


def atribuir_ra(
    rotulo: "pd.Series",  # noqa: F821
    latitude: "pd.Series",  # noqa: F821
    longitude: "pd.Series",  # noqa: F821
    poligonos: "gpd.GeoDataFrame",  # noqa: F821
) -> "tuple[pd.Series, dict[str, int]]":  # noqa: F821
    """Chave da RA de cada caso: o rótulo do banco, corrigido para as RAs novas.

    Devolve ``(ra_chave, estatísticas)``. As três séries de entrada têm o mesmo
    índice. **A coordenada não sai desta função** — vira só a decisão de mover ou
    não. Regra e justificativa: docstring do módulo.

    ``estatísticas``: ``movidos_<RA>`` por RA nova; ``barrados_ponto_repetido``
    (cairiam na RA nova, mas o ponto é genérico); ``rotulo_igual_mae_fora`` (o
    rótulo é a RA-mãe mas o ponto cai fora do polígono novo — fica como estava).
    """
    import geopandas as gpd
    import pandas as pd

    rot = rotulo.map(chave_ra)

    pontos = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(longitude, latitude), index=rotulo.index, crs="EPSG:4326"
    ).to_crs("EPSG:31983")
    dentro = gpd.sjoin(pontos, poligonos, how="left", predicate="within")
    dentro = dentro[~dentro.index.duplicated(keep="first")]
    coord = dentro["chave"].reindex(rotulo.index)

    # Quantos casos dividem o mesmo ponto. NaN (sem coordenada) não agrupa e dá
    # NaN, que é "não preciso" — a comparação abaixo é falsa para NaN.
    repeticoes = (
        pd.DataFrame({"lat": latitude, "lon": longitude})
        .groupby(["lat", "lon"])["lat"]
        .transform("size")
    )
    preciso = repeticoes < config.PONTO_REPETIDO_MINIMO

    cairia = coord.isin(config.RA_MAE) & (rot == coord.map(config.RA_MAE))
    mover = cairia & preciso

    estatisticas = {f"movidos_{ra}": int((mover & (coord == ra)).sum()) for ra in config.RA_MAE}
    estatisticas["barrados_ponto_repetido"] = int((cairia & ~preciso).sum())
    estatisticas["rotulo_mae_ponto_fora_da_ra_nova"] = int(
        rot.isin(config.RA_MAE.values()).sum() - cairia.sum()
    )
    return rot.where(~mover, coord), estatisticas


def extrair() -> "tuple[pd.DataFrame, dict[str, int]]":  # noqa: F821
    import pandas as pd

    # LATITUDE/LONGITUDE entram só para `atribuir_ra` e saem antes de `saida`.
    colunas_brutas = list(COLUNAS_DIRETAS) + list(DECODIFICAR) + list(COORDENADAS)
    colunas_sql = ", ".join(f'"{c}"' for c in colunas_brutas)
    sql = f"""
        SELECT {colunas_sql}
        FROM (
            SELECT *, row_number() OVER (
                PARTITION BY "NU_NOTIFIC" ORDER BY "DT_NOTIFIC"
            ) AS _ordem
            FROM {config.GEOLINK_TABELA}
            -- Residência, não notificação: a tabela é filtrada por
            -- SG_UF_NOT=53 (DF) na origem, mas 1.191 das 7.551 linhas são
            -- de gente notificada no DF e residente em outro município —
            -- ver docstring do módulo. `530010` é `config.MUN_DF`.
            WHERE "ID_MN_RESI" = 530010
        ) t
        WHERE _ordem = 1
    """
    bruto = banco.consultar(sql)

    saida = pd.DataFrame(index=bruto.index)
    saida["ano_notificacao"] = bruto["NU_ANO"].astype("Int64")
    saida["dt_notificacao"] = bruto["DT_NOTIFIC"]
    saida["dt_diagnostico"] = bruto["DT_DIAG"]
    saida["dt_inicio_tratamento"] = bruto["DT_INIC_TR"]
    saida["dt_encerramento"] = bruto["DT_ENCERRA"]
    saida["sexo"] = bruto["CS_SEXO"].map({"M": "Masculino", "F": "Feminino"})
    saida["idade_anos"] = _idade_anos(bruto["NU_IDADE_N"])
    saida["ra_chave"], estatisticas_ra = atribuir_ra(
        bruto["Regiao_adm"], bruto["LATITUDE"], bruto["LONGITUDE"], poligonos_ra()
    )
    # A coordenada cumpriu o único papel dela. Sai da memória antes de qualquer
    # outra coisa, e `saida` nunca a teve.
    bruto = bruto.drop(columns=list(COORDENADAS))
    saida["regiao_saude"] = saida["ra_chave"].map(config.RA_PARA_REGIAO_SAUDE)

    saida["situacao_encerramento"] = _chave_inteira(bruto["SITUA_ENCE"]).map(SITUA_ENCE)
    saida["tipo_entrada"] = _chave_inteira(bruto["TRATAMENTO"]).map(TIPO_ENTRADA)
    saida["teste_molecular_rapido"] = _chave_inteira(bruto["TEST_MOLEC"]).map(TESTE_MOLECULAR)
    for coluna_bruta, coluna_nova in CONTATOS.items():
        saida[coluna_nova] = pd.to_numeric(bruto[coluna_bruta], errors="coerce").astype("Int64")

    dicionario = _carregar_dicionario()
    for coluna_bruta, coluna_nova in DECODIFICAR.items():
        tabela = dicionario.loc[dicionario["variavel"] == coluna_bruta]
        # `valor` no dicionário é texto e pode ter zero à esquerda (`"03"`);
        # normaliza os dois lados para o mesmo inteiro-como-texto — a coluna
        # bruta do banco chega `float64` por ter nulo (`1` vira `1.0`), e
        # comparar com `astype(str)` sem passar por inteiro derrubava a
        # decodificação inteira sem erro nenhum aparecer (medido: todas as
        # colunas saíam `None`).
        mapa = {
            str(int(float(v))): rotulo
            for v, rotulo in zip(tabela["valor"], tabela["valor_lbl"], strict=False)
            if str(v).strip().lstrip("-").isdigit()
        }
        saida[coluna_nova] = _chave_inteira(bruto[coluna_bruta]).map(mapa)

    return saida, estatisticas_ra


def _chave_inteira(bruta: "pd.Series") -> "pd.Series":  # noqa: F821
    """``1.0`` -> ``"1"``, preservando nulo. Ver o comentário em `extrair()`
    sobre por que isto não pode ser um `astype(str)` direto."""
    import pandas as pd

    return pd.to_numeric(bruta, errors="coerce").astype("Int64").astype("string")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--destino",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "origem" / "sinan_df_ra.parquet",
    )
    a = p.parse_args()

    if not banco.configurado():
        raise SystemExit(
            "Credenciais ausentes. Copie .env.exemplo para .env e preencha "
            "CENARIOS_HOST/CENARIOS_USER/CENARIOS_PASSWORD."
        )
    if not SINAN_DICT.parents[1].is_dir():
        raise SystemExit(
            f"Dicionário de códigos não encontrado em {SINAN_DICT.parents[1]}. "
            f"Precisa do painel `paineis/sinan` na mesma máquina, com os "
            f"dados já preparados."
        )

    df, estatisticas_ra = extrair()
    a.destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(a.destino, index=False, compression="zstd")

    print(f"{len(df)} linhas, {len(df.columns)} colunas em {a.destino}")
    print(df["ano_notificacao"].value_counts().sort_index().to_string())
    print(f"sem RA (ra_chave='IGNORADO'): {(df['ra_chave'] == 'IGNORADO').sum()}")
    print("RAs novas, por coordenada precisa:", estatisticas_ra)
    assert not (set(df.columns) & set(COORDENADAS)), "coordenada vazou para a saída"
    print(f"sem Região de Saúde: {df['regiao_saude'].isna().sum()}")


if __name__ == "__main__":
    main()
