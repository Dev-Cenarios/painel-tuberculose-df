"""Conexão com o banco `cenarios_ai`, onde está o SINAN nacional.

Mesmo padrão do módulo equivalente em `paineis/sinan/src/data/banco.py`:
credenciais em `.env` (fora do git), conexão somente leitura, barreira dupla
(`readonly=True` na sessão + `default_transaction_read_only=on` no servidor).

Serve só para as extrações em `scripts/`. O app deste painel, como o da
família inteira, lê parquet local em runtime — nunca o banco.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]


def _carregar_env() -> None:
    caminho = RAIZ / ".env"
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


def configurado() -> bool:
    _carregar_env()
    return bool(
        os.environ.get("CENARIOS_HOST")
        and os.environ.get("CENARIOS_USER")
        and os.environ.get("CENARIOS_PASSWORD")
    )


@contextmanager
def conectar():
    """Conexão somente leitura. Fecha sozinha ao sair do bloco."""
    import psycopg2

    _carregar_env()
    if not configurado():
        raise RuntimeError(
            "Credenciais ausentes. Copie `.env.exemplo` para `.env` e preencha "
            "`CENARIOS_HOST`, `CENARIOS_USER` e `CENARIOS_PASSWORD`."
        )

    conexao = psycopg2.connect(
        # Sem valor padrão: o endereço do banco é interno e não fica no código.
        host=os.environ["CENARIOS_HOST"],
        port=int(os.environ.get("CENARIOS_PORT", "5432")),
        dbname=os.environ.get("CENARIOS_DB", "cenarios_ai"),
        user=os.environ["CENARIOS_USER"],
        password=os.environ["CENARIOS_PASSWORD"],
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    )
    try:
        conexao.set_session(readonly=True, autocommit=True)
        yield conexao
    finally:
        conexao.close()


def consultar(sql: str, params: list | None = None) -> pd.DataFrame:
    """Executa um SELECT e devolve DataFrame."""
    with conectar() as conexao:
        return pd.read_sql_query(sql, conexao, params=params)
