"""Extrai a população do Distrito Federal (`public.pop_ibge`, banco
`cenarios_ai`) — denominador da incidência.

`pop_ibge` é estimativa IBGE por município/ano/sexo/idade, sem nada nominal
— mesmo raciocínio do `extrair_populacao_manaus.py`: não há recorte de
privacidade a fazer aqui. A soma por ano já acontece no SQL.

Cobertura confirmada em `pop_ibge` para o DF (`cod_mun = '5300108'`, código
IBGE de 7 dígitos — diferente do `MUN_DF` de 6 dígitos usado no SINAN, ver
`src/data/config.py`): 2010–2025, todos os anos presentes.

Uso::

    python -m scripts.extrair_populacao_df
    python -m scripts.extrair_populacao_df --destino data/origem/populacao_df.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data import banco  # noqa: E402

#: Código IBGE de 7 dígitos do Distrito Federal, como gravado em
#: `pop_ibge.cod_mun`. Não confundir com `config.MUN_DF` (6 dígitos, usado no
#: SINAN) — cada fonte grava o município num formato diferente.
COD_MUN_DF = "5300108"


def extrair() -> "pd.DataFrame":  # noqa: F821
    sql = """
        SELECT ano::int AS ano, sum(populacao)::bigint AS populacao
        FROM public.pop_ibge
        WHERE cod_mun = %s
        GROUP BY ano
        ORDER BY ano
    """
    return banco.consultar(sql, params=[COD_MUN_DF])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--destino",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "origem" / "populacao_df.parquet",
    )
    a = p.parse_args()

    if not banco.configurado():
        raise SystemExit(
            "Credenciais ausentes. Copie .env.exemplo para .env e preencha "
            "CENARIOS_HOST/CENARIOS_USER/CENARIOS_PASSWORD (ou reaproveite o .env de paineis/sinan)."
        )

    df = extrair()
    a.destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(a.destino, index=False, compression="zstd")

    print(f"{len(df)} anos em {a.destino}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
