"""Converte os parquets de `data/origem/` nos parquets que `src/data/`
espera em runtime: o microdado particionado por ano, e a população e os
óbitos por TB (usados pelos KPIs `incid` e `mortalidade`, ver
`src/data/kpis.py`).

**Diferente do `preparar_microdado.py` do RecifeTB**, que lê um CSV bruto com
dado nominal e faz a deduplicação e a poda de colunas na hora da conversão.
Aqui os dois já aconteceram — `scripts/extrair_sinan_df.py` filtrou
`municipio_residencia = 'Brasília'`, dedupou por `sk_sinan_tube` e manteve só
as colunas já sem identificador. Este script só reparticiona o microdado por
ano, que é a forma que `microdado.py` lê. População e óbitos não são
particionados — poucas dezenas/centenas de linhas no total — só recomprime e
move para `data/parquet/dashboard/`. Mesmo script do manaustb, com os nomes
de arquivo do DF.

Uso::

    python -m scripts.preparar_microdado
    python -m scripts.preparar_microdado --origem <parquet> --destino <dir>
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import duckdb

from src.data import config


def converter(origem: Path, destino: Path) -> int:
    """Grava ``destino/ano_notificacao=YYYY/part-0.parquet`` e devolve o
    total de linhas."""
    con = duckdb.connect()
    destino.mkdir(parents=True, exist_ok=True)

    con.execute(
        f"""
        COPY (
            SELECT *
            FROM read_parquet(?)
            WHERE ano_notificacao IS NOT NULL
        ) TO '{destino.as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (ano_notificacao), OVERWRITE_OR_IGNORE,
         COMPRESSION ZSTD)
        """,
        [origem.as_posix()],
    )
    return con.execute(
        f"SELECT count(*) FROM read_parquet('{destino.as_posix()}/**/*.parquet')"
    ).fetchone()[0]


def _copiar(origem: Path, destino: Path) -> int:
    """Recomprime um parquet pequeno (população, óbitos) sem particionar."""
    con = duckdb.connect()
    destino.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"""
        COPY (SELECT * FROM read_parquet(?))
        TO '{destino.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        [origem.as_posix()],
    )
    return con.execute(f"SELECT count(*) FROM read_parquet('{destino.as_posix()}')").fetchone()[0]


def gravar_procedencia(origens: dict[str, Path], destino: Path) -> dict:
    """Grava `PROCEDENCIA.json`: até quando vão os dados e quando foram processados.

    ``dados_ate`` é a data de **notificação** mais recente entre as fontes — e o
    painel corta em 2024 de propósito (2025 não tem encerramento fechado), então
    é o fim da série, não "hoje". ``extraido_em`` de cada fonte é a hora do arquivo
    de origem, ou seja, de quando rodou a extração no banco; ``processado_em`` é
    quando este script rodou. O `SINAN` é atualizado retroativamente, e é isto que
    deixa quem lê o painel saber de que dia são os números.
    """
    con = duckdb.connect()
    fontes: dict[str, dict] = {}
    for nome, caminho in origens.items():
        if not caminho.is_file():
            continue
        ate, linhas = con.execute(
            "SELECT max(dt_notificacao), count(*) FROM read_parquet(?)", [caminho.as_posix()]
        ).fetchone()
        fontes[nome] = {
            "dados_ate": ate.isoformat() if ate else None,
            "extraido_em": datetime.fromtimestamp(caminho.stat().st_mtime)
            .astimezone().isoformat(timespec="minutes"),
            "linhas": int(linhas),
        }
    datas = [f["dados_ate"] for f in fontes.values() if f["dados_ate"]]
    registro = {
        "processado_em": datetime.now().astimezone().isoformat(timespec="minutes"),
        "dados_ate": max(datas) if datas else None,
        "fontes": fontes,
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return registro


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--origem", type=Path,
        default=config.origem_dir() / "sinan_df_tb.parquet",
    )
    p.add_argument(
        "--destino", type=Path,
        default=config.dashboard_dir() / "sinan_df",
    )
    a = p.parse_args()

    if not a.origem.is_file():
        raise SystemExit(
            f"Origem não encontrada: {a.origem}\n"
            f"Rode antes: python -m scripts.extrair_sinan_df"
        )

    linhas = converter(a.origem, a.destino)
    print(f"{linhas} linhas em {a.destino}")

    # População e óbitos são opcionais neste passo — os KPIs que dependem
    # deles (`incid`, `mortalidade`) simplesmente saem nulos se a origem não
    # existir (ver `microdado.populacao_ano`/`obitos_tb_ano`), não vale travar
    # o reparticionamento do microdado por causa deles.
    origem_pop = config.origem_dir() / "populacao_df.parquet"
    if origem_pop.is_file():
        n = _copiar(origem_pop, config.populacao_path())
        print(f"{n} anos de população em {config.populacao_path()}")
    else:
        print(f"[aviso] população não encontrada em {origem_pop} — pulando")

    origem_obitos = config.origem_dir() / "obitos_tb_df.parquet"
    if origem_obitos.is_file():
        n = _copiar(origem_obitos, config.obitos_tb_path())
        print(f"{n} óbitos por TB em {config.obitos_tb_path()}")
    else:
        print(f"[aviso] óbitos por TB não encontrados em {origem_obitos} — pulando")

    # Segunda fonte: o microdado geolinkado por RA (`extrair_sinan_df_geolink.py`).
    # Reparticiona igual ao primeiro — mesma função, dataset diferente. Lido
    # por `src/data/microdado_ra.py`, nunca pelo `microdado.py` do DF inteiro:
    # as duas fontes divergem em volume (ver README, "Divergência a
    # documentar") e não devem ser somadas nem comparadas linha a linha.
    origem_ra = config.origem_dir() / "sinan_df_ra.parquet"
    if origem_ra.is_file():
        destino_ra = config.dashboard_dir() / "sinan_df_ra"
        n = converter(origem_ra, destino_ra)
        print(f"{n} linhas (por RA) em {destino_ra}")
    else:
        print(f"[aviso] microdado por RA não encontrado em {origem_ra} — pulando "
              f"(rode: python -m scripts.extrair_sinan_df_geolink)")

    registro = gravar_procedencia(
        {"silver": a.origem, "geolink": origem_ra}, config.procedencia_path()
    )
    print(f"procedência: dados até {registro['dados_ate']}, processado em "
          f"{registro['processado_em']} -> {config.procedencia_path()}")


if __name__ == "__main__":
    main()
