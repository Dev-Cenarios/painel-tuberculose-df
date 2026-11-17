"""Localização dos dados e constantes de domínio — recorte do Distrito Federal.

Os parquets não são versionados. A raiz é resolvida nesta ordem:

1. variável de ambiente ``SINAN_DATA_DIR``
2. ``data/`` na raiz do projeto (padrão)

**Não há seletor de UF/município neste painel**, pelo mesmo motivo do
`manaustb`: a extração já vem recortada para o Distrito Federal
(`scripts/extrair_sinan_df.py` filtra `municipio_residencia = 'Brasília'`), e
o Distrito Federal é município único na UF — não há subdivisão a navegar
como no RecifeTB (bairro/Distrito Sanitário) porque o SINAN nacional não
relaciona caso de TB a Região Administrativa (confirmado em `cenarios_ai`,
mesma investigação que fechou essa pergunta para Manaus).
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    """Raiz dos dados. Ver docstring do módulo para a ordem de resolução."""
    env = os.environ.get("SINAN_DATA_DIR", "").strip()
    return Path(env).resolve() if env else PROJECT_ROOT / "data"


def dashboard_dir() -> Path:
    """Diretório com o dataset parquet particionado por ano."""
    return data_dir() / "parquet" / "dashboard"


def geo_dir() -> Path:
    """Diretório com a malha do Centro-Oeste/DF, se um mapa de contexto vier
    a existir (decisão pendente — ver README). Nenhum módulo lê daqui ainda."""
    return data_dir() / "geo"


def origem_dir() -> Path:
    """Diretório com os parquets extraídos do banco (`sinan_df_tb.parquet`,
    `populacao_df.parquet`, `obitos_tb_df.parquet`)."""
    return data_dir() / "origem"


def procedencia_path() -> Path:
    """`PROCEDENCIA.json`, gravado por `scripts/preparar_microdado.py`: até
    quando vão os dados e quando foram processados. Mora ao lado dos parquets
    e viaja com eles na imagem."""
    return dashboard_dir() / "PROCEDENCIA.json"


def populacao_path() -> Path:
    """Parquet de população do DF por ano, pronto para leitura em runtime
    (não particionado — poucas linhas, uma por ano)."""
    return dashboard_dir() / "populacao_df.parquet"


def obitos_tb_path() -> Path:
    """Parquet de óbitos por TB no DF, pronto para leitura em runtime (não
    particionado — poucas centenas de linhas no total)."""
    return dashboard_dir() / "obitos_tb_df.parquet"


# ---------------------------------------------------------------------------
# Doença
# ---------------------------------------------------------------------------
#: Só tuberculose existe hoje — mantido como constante nomeada, e não string
#: crua espalhada pelo código, mesmo raciocínio do manaustb.
TUBERCULOSE = "TUBERCULOSE"


# ---------------------------------------------------------------------------
# Recorte fixo: Distrito Federal
# ---------------------------------------------------------------------------
#: Código IBGE do DF (6 dígitos, como grava `silver.tuberculose`/SINAN) e
#: sigla da UF. Não navegável — todo o painel vive dentro deste recorte.
MUN_DF = "530010"
UF_DF = "DF"

#: Último ano fechado do SINAN. Medido em `cenarios_ai` em 11/set/2026:
#: `situacao_encerramento` "Não informado" é 23,7% em 2025 contra 2,3% em
#: 2024 — mesmo padrão que levou o manaustb a cortar em 2024 (lá: 30,9% x
#: 0,7%). 2026 é o ano civil em curso (64,3% não informado, 14 notificações).
#: Reproduzido aqui como teto do seletor de ano.
ANO_MAX_DF = 2024

#: Último ano incluído nos óbitos por TB (`sim_mortalidade`). **Diferente**
#: de `ANO_MAX_DF`, mesmo raciocínio do manaustb: óbito não tem o desfecho em
#: aberto que caso de TB tem. Medido: 2025 tem 34 óbitos por TB no DF, dentro
#: da faixa dos anos fechados anteriores (22–40); 2026 tem 12, claramente o
#: ano civil incompleto. `scripts/extrair_obitos_tb_df.py` inclui 2025 e
#: exclui 2026.
ANO_MAX_OBITO_DF = 2025

#: Malha geográfica: **por Região Administrativa**, decidida em
#: 11/set/2026. O SINAN nacional (`silver.tuberculose`, usado nos KPIs de
#: DF inteiro) não desce a RA — mas `dados_geolink."DF_geo_TB"` (banco
#: `cenarios_ai`, dado nominal) sim, via a coluna `Regiao_adm`.
#:
#: **35 RAs, desde 08/out/2026.** A malha é a camada oficial "Regiões
#: Administrativas do Distrito Federal em 2026" do IPEDF (catalogo.ipe.df.gov.br),
#: que inclui Arapoanga (RA-XXXIV) e Água Quente (RA-XXXV), criadas em
#: dez/2022. Antes eram 33, da malha de subdistritos do Censo 2022 (IBGE). A
#: população continua sendo a do Censo 2022, agora somada por **setor
#: censitário** dentro de cada RA — ver `scripts/preparar_geometria.py`.
GEOLINK_TABELA = 'dados_geolink."DF_geo_TB"'

# ---------------------------------------------------------------------------
# Definições do Boletim da SES-DF (Gevist/Divep/SVS), mar/2026
# ---------------------------------------------------------------------------
#: **Caso novo**, como o Boletim conta: tipo de entrada "Caso novo", "Não sabe" ou
#: "Pós-óbito" — fora recidiva, reingresso após abandono e transferência — e fora
#: os encerrados como "mudança de diagnóstico", "por não corresponderem a casos
#: confirmados da doença". Medido em out/2026, essa regra dá 470 casos em 2024
#: pela fonte por região e 437 pela do DF inteiro, contra 475 no Boletim; antes o
#: painel contava toda notificação (550 e 610). Vale para as duas fontes, que
#: grafam o tipo de entrada igual.
SQL_CASO_NOVO = (
    "(tipo_entrada IN ('Caso novo', 'Nao sabe', 'Pos-obito') "
    "AND coalesce(situacao_encerramento, '') <> 'Mudanca de diagnostico')"
)

#: População do DF que o Boletim usa nos coeficientes (projeções do IPEDF).
#: **Derivada, não copiada de uma tabela**: o Boletim publica casos e coeficiente
#: por ano na Tabela 3 ("ambos os sexos"), e a população sai de
#: casos / coeficiente x 100 mil — 475 / 14,8 em 2024. O erro vem do arredondamento
#: do coeficiente a uma casa: até 0,4%. Troque pela tabela do IPEDF quando
#: houver; é só este dicionário.
POPULACAO_IPEDF_DERIVADA = {
    2021: 3_078_431,  # 314 / 10,2
    2022: 3_132_075,  # 332 / 10,6
    2023: 3_164_179,  # 424 / 13,4
    2024: 3_209_459,  # 475 / 14,8
    2025: 3_232_877,  # 472 / 14,6
}

#: RA -> Região de Saúde. 31 das 33 RA de então vieram medidas direto em
#: `dados_geolink."DF_geo_TB"` em 11/set/2026 (agrupando por `Regiao_adm` e
#: `Regiao_sau1` — associação 1:1, não escolha nossa). As chaves aqui já
#: passaram por `escopo.chave_ra`.
#:
#: **RIACHO FUNDO e SCIA vinham como `Regiao_sau1='Ignorado'`** no dado —
#: gente notificada nessas duas RA, sem excessão, nunca tem a Região de
#: Saúde preenchida na fonte. Preenchidas em 14/set/2026 contra duas fontes
#: oficiais da SES-DF (`saude.df.gov.br/regiao-centro-sul` e o Decreto
#: 37.515/2016, art. 3º): as duas pertencem à **Região Centro-Sul** — o que
#: bate com o padrão dos vizinhos que o dado já dava certos (Candangolândia,
#: Guará, Núcleo Bandeirante, Park Way, Riacho Fundo II e SIA, todos
#: Centro-Sul). Ver `tests/paridade/excecoes.md`, §3.
RA_PARA_REGIAO_SAUDE: dict[str, str | None] = {
    "AGUA QUENTE": "Regiao Sudoeste",
    "AGUAS CLARAS": "Regiao Sudoeste",
    "ARAPOANGA": "Regiao Norte",
    "ARNIQUEIRA": "Regiao Sudoeste",
    "BRAZLANDIA": "Regiao Oeste",
    "CANDANGOLANDIA": "Regiao Centro-Sul",
    "CEILANDIA": "Regiao Oeste",
    "CRUZEIRO": "Regiao Central",
    "FERCAL": "Regiao Norte",
    "GAMA": "Regiao Sul",
    "GUARA": "Regiao Centro-Sul",
    "ITAPOA": "Regiao Leste",
    "JARDIM BOTANICO": "Regiao Leste",
    "LAGO NORTE": "Regiao Central",
    "LAGO SUL": "Regiao Central",
    "NUCLEO BANDEIRANTE": "Regiao Centro-Sul",
    "PARANOA": "Regiao Leste",
    "PARK WAY": "Regiao Centro-Sul",
    "PLANALTINA": "Regiao Norte",
    "PLANO PILOTO": "Regiao Central",
    "RECANTO DAS EMAS": "Regiao Sudoeste",
    "RIACHO FUNDO": "Regiao Centro-Sul",
    "RIACHO FUNDO II": "Regiao Centro-Sul",
    "SAMAMBAIA": "Regiao Sudoeste",
    "SANTA MARIA": "Regiao Sul",
    "SAO SEBASTIAO": "Regiao Leste",
    "SCIA": "Regiao Centro-Sul",
    "SIA": "Regiao Centro-Sul",
    "SOBRADINHO": "Regiao Norte",
    "SOBRADINHO II": "Regiao Norte",
    "SOL NASCENTE/POR DO SOL": "Regiao Oeste",
    "SUDOESTE/OCTOGONAL": "Regiao Central",
    "TAGUATINGA": "Regiao Sudoeste",
    "VARJAO": "Regiao Central",
    "VICENTE PIRES": "Regiao Sudoeste",
}

#: As duas RAs criadas em dez/2022 e a RA de que cada uma saiu. O dado de
#: casos (`Regiao_adm`) ainda rotula essa gente com a RA-mãe — foi o que
#: o SINAN gravou —, e é isso que `extrair_sinan_df_geolink.py` corrige.
#:
#: **Região de Saúde das duas, medida no dado em 08/out/2026:** os 115
#: casos de Planaltina que a coordenada põe em Arapoanga têm
#: `Regiao_sau1 = Regiao Norte` (115 de 115), e os 5 de Recanto das Emas que
#: caem em Água Quente têm `Regiao Sudoeste` (5 de 5) — a mesma de cada RA-mãe.
#: Confirmar contra o decreto da SES-DF, como foi feito para Riacho Fundo e
#: SCIA (§3 de `excecoes.md`).
RA_MAE: dict[str, str] = {
    "ARAPOANGA": "PLANALTINA",
    "AGUA QUENTE": "RECANTO DAS EMAS",
}

#: Um ponto de coordenada que se repete **este número de vezes ou mais** entre
#: os casos é geocodificação genérica (centro de bairro, de CEP, da cidade),
#: e não a localização do caso. Medido em 08/out/2026: o ponto mais repetido
#: tem 278 casos, e 40 pontos concentram 28% dos residentes. Um ponto genérico
#: que por acaso caia numa RA nova não pode mover caso nenhum para ela.
PONTO_REPETIDO_MINIMO = 5
