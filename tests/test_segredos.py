"""Guarda contra credencial versionada.

Mesmo teste do manaustb — existe pelo mesmo quase-acidente (credencial no
`.env.exemplo`, que é versionado, em vez do `.env`). Único ajuste: o DFTB
ainda não é um repositório git próprio nesta máquina (a família toda vive
sob `Painéis_Cenários`, e nem essa raiz tem `.git` hoje) — a varredura por
`git ls-files` pula em vez de falhar quando não há repositório, para não
travar a suíte por um `git init` que ainda não aconteceu.

**Achado real ao rodar de verdade pela primeira vez (14/set/2026):** a
constante abaixo se chamava `CHAVES_SECRETAS`, e "SECRET" é um dos radicais
que a varredura procura — o próprio nome da constante disparava um falso
positivo contra si mesma. Nem aqui nem no manaustb esse teste tinha
rodado de fato antes (os dois sem `.git`), então o defeito ficou latente.
Renomeada para `CHAVES_SIGILOSAS`, que não casa com nenhum radical.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

#: Chaves do modelo que precisam ficar vazias. `CENARIOS_HOST` entrou na lista
#: em out/2026: não é senha, mas é IP de rede interna e não vai para o GitHub.
#: Porta e nome do banco seguem com valor — sozinhos não dizem onde fica nada.
CHAVES_SIGILOSAS = ("CENARIOS_HOST", "CENARIOS_USER", "CENARIOS_PASSWORD")


def test_o_modelo_de_env_nao_tem_credencial_preenchida() -> None:
    """`.env.exemplo` é versionado. Preenchê-lo publica a senha."""
    modelo = RAIZ / ".env.exemplo"
    assert modelo.is_file(), "o modelo sumiu — sem ele ninguém sabe o que preencher"

    for linha in modelo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = (p.strip() for p in linha.split("=", 1))
        if chave in CHAVES_SIGILOSAS:
            assert not valor, (
                f"{chave} está preenchida em .env.exemplo, que é VERSIONADO. "
                f"Mova para .env (ignorado pelo git) e restaure o modelo com "
                f"`git checkout -- .env.exemplo`."
            )


def test_o_env_de_verdade_continua_ignorado() -> None:
    """Se alguém tirar `.env` do `.gitignore`, o próximo `add -A` publica tudo."""
    ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert any(linha.strip() == ".env" for linha in ignorados), (
        ".env saiu do .gitignore"
    )


def test_nenhum_arquivo_versionado_carrega_senha() -> None:
    """Varredura ampla, para o caso de a senha ir parar em outro lugar.

    Procura atribuição a uma chave de aparência secreta com valor não vazio.
    Ignora o que é claramente exemplo — `<sua-senha>`, `xxx`, `troque-me`.

    Pula quando `RAIZ` não é (ainda) um repositório git — `git ls-files`
    devolve status 128 nesse caso, e isso não é "senha vazou", é "ainda não
    existe controle de versão para varrer".
    """
    try:
        saida = subprocess.run(
            ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("sem repositório git em " + str(RAIZ) + " — nada a varrer ainda")

    # Duas formas, e nao uma: chave em MAIUSCULAS, como manda a convencao de
    # configuracao, **ou** valor entre aspas. Sem essa restricao a anotacao de
    # tipo `def _px(token: str)` casava, e o teste acusava `src/graficos.py`.
    padrao = re.compile(
        r"""^(?!\s*\#).*?(?:
              (?P<maiuscula>[A-Z_]*(?:PASSWORD|SENHA|SECRET|TOKEN|API_KEY)[A-Z_]*)
              \s*[=:]\s*(?P<v1>[^\s"',\#]+)
            | (?i:password|senha|secret|token|api_key)
              \s*[=:]\s*["'](?P<v2>[^"']+)["']
        )""",
        re.VERBOSE,
    )
    placeholders = {"", "none", "null", "xxx", "troque-me", "sua-senha", "changeme"}

    suspeitos = []
    for nome in saida.stdout.splitlines():
        caminho = RAIZ / nome
        if not caminho.is_file() or caminho.suffix in {".png", ".jpg", ".jpeg", ".ico"}:
            continue
        try:
            texto = caminho.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            achado = padrao.match(linha)
            if not achado:
                continue
            valor = (achado.group("v1") or achado.group("v2") or "").strip("<>{}")
            if valor.lower() in placeholders or valor.startswith(("os.", "$", "%")):
                continue
            suspeitos.append(f"{nome}:{n}")

    assert not suspeitos, "possível segredo em arquivo versionado: " + ", ".join(suspeitos)
