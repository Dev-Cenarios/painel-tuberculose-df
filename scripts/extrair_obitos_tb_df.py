"""Extrai óbitos por tuberculose no Distrito Federal (`public.sim_mortalidade`,
banco `cenarios_ai`) — numerador da mortalidade.

**Atenção: `sim_mortalidade` é dado bruto do SIM/DataSUS**, ~100 colunas,
tudo `text`, sem filtro nenhum aplicado na origem — a tabela inteira cobre
todas as causas de óbito do Brasil. O filtro de causa (TB) e de município
acontece **dentro do SQL, antes de qualquer linha sair do banco** — nunca se
faz `SELECT *` nem se traz a tabela sem filtro para o Python, mesma disciplina
de `extrair_sinan_df.py` e do equivalente em Manaus.

Filtro de causa: CID-10 `A15`–`A19` (`left(causabas, 3) BETWEEN 'A15' AND
'A19'`) — códigos de tuberculose no capítulo I do CID-10.

Filtro de município — dois formatos, não um, e o mesmo padrão de Manaus:
`codmunres` grava o DF como código de 7 dígitos (`'5300108'`) em registros
até 2005 e de 6 dígitos (`'530010'`) a partir de 2006, sem sobreposição de
anos entre os dois — conferido por ano em 11/set/2026.
`codmunres IN ('530010', '5300108')` cobre a série inteira.

Colunas mantidas — mesma lista e mesmo raciocínio de `extrair_obitos_tb_manaus.py`:
só o que sustenta o KPI de mortalidade e uma composição simples (sexo).

- ``ano_obito`` — extraído de ``dtobito`` (texto **DDMMYYYY**; os 4 últimos
  caracteres são o ano — ``right(dtobito, 4)``).
- ``sexo`` — código bruto do SIM (``'1'`` masculino, ``'2'`` feminino,
  ``'0'``/nulo ignorado); decodificado em Python.
- ``idade`` — código posicional do SIM: 1º dígito é a unidade (``4`` = anos),
  os três dígitos seguintes são o valor. Decodificado em Python.
- ``causabas`` — mantido em 4 caracteres (ex.: ``A162``).

Corte de ano: **2026 fica fora, 2025 fica dentro** — mesma decisão do
manaustb, e pelo mesmo motivo: óbito não tem o desfecho em aberto que caso de
TB tem (a data e a causa não mudam depois de registradas), então o corte é
por completude de carga, não de campo. Medido em 11/set/2026: o DF tem 34
óbitos por TB em 2025 (dentro da faixa 22–40 dos anos fechados anteriores) e
12 em 2026 — claramente o ano civil em curso.

Uso::

    python -m scripts.extrair_obitos_tb_df
    python -m scripts.extrair_obitos_tb_df --destino data/origem/obitos_tb_df.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data import banco  # noqa: E402

#: Último ano incluído. Ver docstring do módulo para o porquê de ser 2025,
#: diferente do `config.ANO_MAX_DF` (2024) do SINAN.
ANO_MAX_OBITO = 2025

#: Formatos de `codmunres` que cobrem o DF na série histórica inteira — ver
#: docstring do módulo.
CODMUNRES_DF = ("530010", "5300108")

_SEXO = {"1": "Masculino", "2": "Feminino"}


def _decodificar_idade(bruta: "pd.Series") -> "pd.Series":  # noqa: F821
    """Código posicional do SIM: 1º dígito = unidade (4 = anos), os outros
    3 = valor. Só ``4`` (anos) vira idade em anos completos — mesma regra de
    `extrair_obitos_tb_manaus.py`; o KPI de mortalidade não desce a faixa
    etária hoje.
    """
    import pandas as pd

    s = bruta.astype("string").str.strip()
    unidade = s.str[0]
    valor = pd.to_numeric(s.str[1:], errors="coerce")
    return valor.where(unidade == "4")


def extrair() -> "pd.DataFrame":  # noqa: F821
    marcadores = ", ".join(["%s"] * len(CODMUNRES_DF))
    sql = f"""
        SELECT
            right(dtobito, 4)::int AS ano_obito,
            sexo,
            idade,
            left(causabas, 4) AS causabas
        FROM public.sim_mortalidade
        WHERE left(causabas, 3) BETWEEN 'A15' AND 'A19'
          AND codmunres IN ({marcadores})
          AND right(dtobito, 4)::int <= %s
    """
    df = banco.consultar(sql, params=[*CODMUNRES_DF, ANO_MAX_OBITO])
    df["sexo"] = df["sexo"].astype("string").str.strip().map(_SEXO)
    df["idade_anos"] = _decodificar_idade(df["idade"])
    return df[["ano_obito", "sexo", "idade_anos", "causabas"]]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--destino",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "origem" / "obitos_tb_df.parquet",
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

    print(f"{len(df)} óbitos por TB em {a.destino}")
    print(df["ano_obito"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
