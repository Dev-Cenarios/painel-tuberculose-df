"""Estado de navegação do painel.

**Muito mais simples que o do RecifeTB, e de propósito** — mesmo raciocínio
do `manaustb`. Não existe mapa nem subdivisão do Distrito Federal (ver
`src/data/config.py`), então não há "caminho" para navegar: o único estado
que muda tela a tela é o **ano**.

Deliberadamente sem dependência do Streamlit: a máquina de estados é testada
sozinha, e o `app.py` só guarda uma instância em ``st.session_state``.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import config


@dataclass
class Navegacao:
    """Recorte corrente. Mutável — a aplicação guarda uma instância viva."""

    doenca: str = config.TUBERCULOSE
    ano: int = config.ANO_MAX_DF

    def trilha(self, local: str | None = None) -> str:
        """Breadcrumb do recorte, para a faixa de cabeçalho. ``local`` é o nome
        da RA/Região selecionada: o painel inteiro responde a ela, e a faixa
        precisa dizer de qual."""
        trecho = "Distrito Federal" if not local else f"Distrito Federal › {local}"
        return f"{trecho} • Ano: {self.ano}"
