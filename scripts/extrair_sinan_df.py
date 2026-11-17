"""Extrai o SINAN-TB do Distrito Federal da base `silver.tuberculose`
(banco `cenarios_ai`).

`silver.tuberculose` já vem sem identificador nominal — nomes de coluna
traduzidos, sem NM_PACIENT/NM_MAE_PAC/endereço/CNS. Mesmo assim, a lista de
colunas abaixo é uma **permissão explícita**, no mesmo espírito do
`preparar_microdado.py` do RecifeTB e de `extrair_sinan_manaus.py`: o que não
está em COLUNAS não atravessa, mesmo que exista na origem.

Recorte: `municipio_residencia = 'Brasília'` e
`estado_residencia = 'Distrito Federal'`. Não há geocodificação por Região
Administrativa nessa fonte — confirmado em 11/set/2026: as 10.266 notificações
do DF trazem só `municipio_residencia='Brasília'` e
`regional_residencia='Distrito Federal'`, sem coluna de RA em nenhuma tabela
do banco. O parquet gerado aqui é o teto de granularidade espacial disponível
hoje: nível DF inteiro — mesma limitação que levou o `manaustb` a sair sem
mapa coroplético nem seletor de área.

Corte de ano: **2025 fica fora.** A notificação em si está quase completa,
mas `situacao_encerramento` não — 23,7% dos casos de 2025 estão
"Não informado" contra 2,3% em 2024, porque o tratamento de TB leva meses
para fechar e o ano ainda não teve tempo de encerrar. Incluir 2025 junto com
anos fechados distorce qualquer indicador de desfecho (cura, abandono) que
olhe a série completa. Ano corrente reentra quando a extração for refeita e
ele já não for mais o ano corrente.

Deduplicação: mesma regra do RecifeTB e do manaustb — `sk_sinan_tube` pode se
repetir (registros de acompanhamento concorrentes); fica uma linha por chave
(`row_number() PARTITION BY sk_sinan_tube ORDER BY dt_notificacao`), para não
contar a notificação mais de uma vez.

Uso::

    python -m scripts.extrair_sinan_df
    python -m scripts.extrair_sinan_df --destino data/origem/sinan_df_tb.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data import banco  # noqa: E402

#: Colunas mantidas. Idêntica à lista do manaustb — mesma fonte, mesmo painel
#: de origem (RecifeTB) a que os dois pretendem chegar o mais perto possível.
COLUNAS = (
    # tempo
    "ano_notificacao",
    "dt_notificacao",
    "dt_diagnostico",
    "dt_inicio_tratamento",
    "dt_encerramento",
    # geografia — só o que a fonte sustenta: município, sem RA
    "estado_notificacao",
    "municipio_notificacao",
    "estado_residencia",
    "municipio_residencia",
    "regional_residencia",
    # perfil
    "sexo",
    "idade_notificada",
    "ano_nascimento",
    "raca_cor",
    "escolaridade",
    "gestante",
    "ocupacao",
    "populacao_situacao_rua",
    "populacao_privada_liberdade",
    "populacao_imigrante",
    "profissional_saude",
    "beneficiario_programa_governo",
    # composição clínica
    "tipo_entrada",
    "forma_clinica",
    "extrapulmonar_localizacao_1",
    "resultado_hiv",
    "agravo_aids",
    "agravo_alcoolismo",
    "agravo_diabetes",
    "agravo_doenca_mental",
    "agravo_drogas_ilicitas",
    "agravo_tabagismo",
    "agravo_outros",
    # diagnóstico
    "baciloscopia_diagnostico_1a_amostra",
    "baciloscopia_diagnostico_2a_amostra",
    "cultura_escarro",
    "histopatologia",
    "teste_molecular_rapido",
    "raio_x_torax",
    # tratamento e desfecho
    "tratamento_diretamente_observado",
    "tratamento_diretamente_observado_atual",
    "situacao_encerramento",
    "tipo_transferencia",
    "resistencia_rifampicina",
    "resistencia_isoniazida",
)

#: Descartadas de propósito — mesma lista do manaustb, reproduzida aqui para
#: registrar que a decisão foi conferida de novo para o DF, não copiada às
#: cegas: nenhuma das dez tinha dado de composição relevante lá.
FORA_DE_ESCOPO = (
    "numero_contatos_identificados", "numero_contatos_examinados",
    "situacao_9_meses_codigo_bruto", "situacao_12_meses_codigo_bruto",
    "teste_sensibilidade", "resistencia_etambutol", "resistencia_estreptomicina",
    "resistencia_pirazinamida", "resistencia_etionamida", "resistencia_outras_drogas",
)


def extrair() -> "pd.DataFrame":  # noqa: F821
    colunas_sql = ", ".join(f'"{c}"' for c in COLUNAS)
    sql = f"""
        SELECT {colunas_sql}
        FROM (
            SELECT *, row_number() OVER (
                PARTITION BY sk_sinan_tube ORDER BY dt_notificacao
            ) AS _ordem
            FROM silver.tuberculose
            WHERE municipio_residencia = 'Brasília'
              AND estado_residencia = 'Distrito Federal'
              AND ano_notificacao <= 2024
        ) t
        WHERE _ordem = 1
    """
    return banco.consultar(sql)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--destino",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "origem" / "sinan_df_tb.parquet",
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

    print(f"{len(df)} linhas, {len(df.columns)} colunas em {a.destino}")
    print(df["ano_notificacao"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
