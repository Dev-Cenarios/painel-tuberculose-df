"""Pacote de configuração da Tuberculose — Distrito Federal.

Mesmo padrão de *disease pack* do RecifeTB e do hansepe: o core é único e a
doença é configuração. Cores, rótulos, ordem dos KPIs, métricas do mapa e
variáveis de composição vêm daqui. `incid` e `mortalidade` entram no layout de
KPI (`pop_ibge` e `sim_mortalidade`, ver `scripts/extrair_populacao_df.py` e
`scripts/extrair_obitos_tb_df.py`) — os dois ficam `None` em anos sem população
ou óbito extraído, em vez de mostrar zero fabricado.
"""

from __future__ import annotations

from ..theme import cores

DOENCA = "TUBERCULOSE"
TITULO = "Monitoramento Tuberculose"
TITULO_CURTO = "Tuberculose"

#: Cor por **métrica**, seguindo a família Cenários — mesma paleta semântica
#: do RecifeTB e do hansepe (decisão 6 do painel nacional: cor é por métrica,
#: não por doença). O cromo institucional (`primary`/`secondary`) é o azul do
#: hansepe; a cor da **doença** só entra nas métricas e nas rampas do mapa.
#:
#: Não existe cor oficial da tuberculose no Brasil (pesquisado em 08/out/2026
#: no Ministério da Saúde, na OPAS e no Stop TB). O coral `#EA5352` é o da capa
#: do Boletim Epidemiológico de Tuberculose do Ministério (mar/2025) — é a
#: identidade daquele documento, adotada aqui por decisão do projeto; `incid` e
#: `mortalidade` são os tons secundários do mesmo boletim (`#B25068`, `#7E1936`).
CORES = {
    "primary": "#12346B",
    "secondary": "#1E73BE",
    "accent": "#4A8EFF",
    "casos": "#EA5352",
    "cura": "#16A34A",
    "cura_pct": "#16A34A",
    "abandono_pct": "#B45309",
    "hiv_pos_pct": "#BE185D",
    "incid": "#B25068",
    "mortalidade": "#7E1936",
}

ROTULOS = {
    "casos": "Casos novos",
    "cura_pct": "Proporção de cura (%)",
    "abandono_pct": "Abandono (%)",
    "hiv_pos_pct": "Coinfecção TB-HIV (%)",
    "incid": "Incidência (por 100 mil hab.)",
    "mortalidade": "Mortalidade por TB (por 100 mil hab.)",
}

#: Quais KPIs aparecem e em que ordem. Seis, como no RecifeTB e no manaustb.
#: Casos e incidência abrem a faixa (o par mais lido em vigilância),
#: mortalidade fecha perto de cura/abandono (mesmo bloco de desfecho).
LAYOUT_KPI = ("casos", "incid", "cura_pct", "abandono_pct", "hiv_pos_pct", "mortalidade")

#: Fração exibida sob o valor do card, mesmo mecanismo do RecifeTB e do
#: manaustb.
FRACAO_KPI = {
    "cura_pct": ("cura_n", "coorte"),
    "abandono_pct": ("abandono_n", "coorte"),
    "hiv_pos_pct": ("hiv_pos_n", "casos"),
    "incid": ("casos", "populacao"),
    "mortalidade": ("obitos_tb", "populacao"),
}

#: Métricas que o mapa por RA/Região de Saúde sabe desenhar
#: (`src/data/microdado_ra.py`) — casos, incidência, cura e abandono.
#: `incid` aqui é **aproximada**, não medida: `microdado_ra.populacao_ra()`
#: estima a população de cada RA a partir da proporção do Censo 2022, não
#: de uma série anual por RA (que não existe) — ver a docstring daquele
#: módulo e `tests/paridade/excecoes.md`.
METRICAS_MAPA: tuple[str, ...] = ("casos", "incid", "cura_pct", "abandono_pct")

#: Métricas em que uma queda é boa.
BOM_SE_CAI = frozenset({"abandono_pct", "hiv_pos_pct", "incid", "mortalidade"})

#: Métricas exibidas com casas decimais. `incid`/`mortalidade` são taxa por
#: 100 mil, não percentual, mas usam o mesmo formatador decimal.
TAXAS = frozenset({"cura_pct", "abandono_pct", "hiv_pos_pct", "incid", "mortalidade"})


def cor(metrica: str) -> str:
    return CORES.get(metrica, CORES["secondary"])


def cortes_fixos(metrica: str) -> tuple[float, ...] | None:
    """Sem régua oficial por RA, sempre `None`. A TB não tem classes de
    endemicidade por Região Administrativa, e inventar uma daria autoridade de
    parâmetro a corte nosso. Mantida porque `doencas.CONTRATO` exige o
    atributo."""
    return None


#: Rampas do mapa, **explícitas** — uma de 7 tons por métrica, do claro ao
#: escuro. A rampa gerada de `cores.rampa` mistura a cor base com preto, e o
#: tom do topo saía quase preto (e some no tema escuro). Aqui o escuro é um
#: vinho/verde/marrom que ainda se lê como cor, e o claro é um tom que se
#: distingue do fundo branco — um tom quase branco deixava as regiões de classe
#: baixa invisíveis e o mapa parecia furado. Passos de luminosidade regulares
#: (conferidos em `tests/test_paleta_mapa.py`), que é o canal que nenhum tipo de
#: daltonismo apaga.
#:
#: `casos` vai do coral à cor do boletim do Ministério (`#7E1936`); `incid` usa
#: o rosé secundário do mesmo boletim, para as duas métricas não parecerem a
#: mesma no mapa.
PALETA_MAPA = {
    "casos": (
        "#F6C6C4", "#F2A3A1", "#EE7C7A", "#EA5352", "#C73B47", "#A02A48", "#7E1936",
    ),
    "incid": (
        "#EFD0D8", "#E0A9B8", "#CC8097", "#B25068", "#93385A", "#762348", "#541434",
    ),
    "cura_pct": (
        "#D9F1E1", "#B0E2C1", "#80D09B", "#4DB97A", "#16A34A", "#107A38", "#0B5628",
    ),
    "abandono_pct": (
        "#FBE3C4", "#F6C98F", "#EEAA58", "#DA8523", "#B45309", "#8A3E08", "#5E2A06",
    ),
}


def rampa_mapa(metrica: str) -> list[str]:
    """Rampa de tons do mapa por RA/Região de Saúde: a explícita da métrica,
    ou, para uma métrica sem paleta, a gerada a partir da cor dela."""
    explicita = PALETA_MAPA.get(metrica)
    return list(explicita) if explicita else cores.rampa(cor(metrica))


ROTULOS_CURTOS = {
    "casos": "Casos",
    "cura_pct": "Cura",
    "abandono_pct": "Abandono",
    "hiv_pos_pct": "Coinfecção TB-HIV",
    "incid": "Incidência",
    "mortalidade": "Mortalidade",
}


#: Miolo de SVG 24x24 de cada card, desenhado à direita num disco na cor da
#: métrica — os mesmos traços do hansepe onde a ideia é a mesma (curva de
#: detecção, pulso de casos, check de cura).
ICONES_KPI = {
    "casos": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "incid": '<path d="M12 14l3.5-5"/><path d="M4 18a8 8 0 1 1 16 0"/>',
    "cura_pct": '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    "abandono_pct": '<circle cx="12" cy="12" r="9"/><path d="M8.5 8.5l7 7M15.5 8.5l-7 7"/>',
    "hiv_pos_pct": '<path d="M12 21s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.6-7 10-7 10z"/>',
    "mortalidade": '<path d="M12 3v18M7 8h10"/>',
}


def icone(metrica: str) -> str:
    return ICONES_KPI.get(metrica, "")


def rotulo(metrica: str) -> str:
    return ROTULOS.get(metrica, metrica)


def rotulo_curto(metrica: str) -> str:
    return ROTULOS_CURTOS.get(metrica, rotulo(metrica))


#: Variáveis do SINAN oferecidas na composição, com nome de coluna já
#: traduzido (minúsculo, `snake_case`) — mesma fonte e a mesma curadoria do
#: manaustb, já que os dois painéis leem de `silver.tuberculose`.
VARIAVEIS: dict[str, dict[str, str]] = {
    "Perfil": {
        "raca_cor": "Raça/cor",
        "escolaridade": "Escolaridade",
        "gestante": "Gestante",
        "ocupacao": "Ocupação",
    },
    "Populações específicas": {
        "populacao_situacao_rua": "População em situação de rua",
        "populacao_privada_liberdade": "População privada de liberdade",
        "populacao_imigrante": "População imigrante",
        "profissional_saude": "Profissional de saúde",
        "beneficiario_programa_governo": "Beneficiário de programa do governo",
    },
    "Agravos associados": {
        "agravo_aids": "Agravo: aids",
        "agravo_alcoolismo": "Agravo: alcoolismo",
        "agravo_diabetes": "Agravo: diabetes",
        "agravo_doenca_mental": "Agravo: doença mental",
        "agravo_drogas_ilicitas": "Agravo: uso de drogas ilícitas",
        "agravo_tabagismo": "Agravo: tabagismo",
        "agravo_outros": "Agravo: outro",
    },
    "Clínica e diagnóstico": {
        "forma_clinica": "Forma clínica",
        "extrapulmonar_localizacao_1": "Localização extrapulmonar",
        "resultado_hiv": "Coinfecção HIV",
        "baciloscopia_diagnostico_1a_amostra": "Baciloscopia (1ª amostra)",
        "cultura_escarro": "Cultura de escarro",
        "raio_x_torax": "Raio-X de tórax",
        "histopatologia": "Histopatologia",
        "teste_molecular_rapido": "Teste molecular rápido",
    },
    "Tratamento e desfecho": {
        "tratamento_diretamente_observado_atual": "Tratamento diretamente observado",
        "situacao_encerramento": "Situação de encerramento",
        "tipo_transferencia": "Transferência",
        "resistencia_rifampicina": "Resistência à rifampicina",
        "resistencia_isoniazida": "Resistência à isoniazida",
    },
}

#: Conjunto inicial da grade de composição — as dez mais lidas na vigilância,
#: o resto continua no seletor.
VARIAVEIS_DESTAQUE = (
    "situacao_encerramento",
    "forma_clinica",
    "resultado_hiv",
    "teste_molecular_rapido",
    "raca_cor",
    "agravo_alcoolismo",
    "agravo_drogas_ilicitas",
    "agravo_tabagismo",
    "populacao_situacao_rua",
    "tratamento_diretamente_observado_atual",
)

#: Onde está, na seção "Indicadores do Boletim", o gráfico por ano (ou por região)
#: da mesma variável. Os tópicos mostram um ano só; o Boletim mostra o movimento.
EQUIVALENTE_NO_BOLETIM = {
    "situacao_encerramento": "Gráfico 7, aba Desfecho",
    "resultado_hiv": "Gráfico 8 e Tabela 6, aba Coinfecção TB-HIV",
    "raca_cor": "Gráfico 4, aba Perfil",
    "escolaridade": "Gráfico 5, aba Perfil",
    "populacao_situacao_rua": "Gráfico 12, aba Populações vulneráveis",
    "populacao_privada_liberdade": "Gráfico 11, aba Populações vulneráveis",
    "teste_molecular_rapido": "Gráfico 2, aba Diagnóstico e tratamento",
    "tratamento_diretamente_observado_atual": "Gráfico 3, aba Diagnóstico e tratamento",
}


def variaveis_planas() -> dict[str, str]:
    return {c: r for grupo in VARIAVEIS.values() for c, r in grupo.items()}


def grupo_da(codigo: str) -> str:
    for grupo, itens in VARIAVEIS.items():
        if codigo in itens:
            return grupo
    return "Outras"


DESCRICOES = {
    "casos": (
        "Casos novos de tuberculose, todas as formas, por município de residência — "
        "como o Boletim da SES-DF os conta: tipo de entrada \"caso novo\", \"não "
        "sabe\" ou \"pós-óbito\", sem recidiva, reingresso após abandono, "
        "transferência nem encerrados como mudança de diagnóstico."
    ),
    "cura_pct": (
        "Cura entre os casos novos **pulmonares com confirmação laboratorial** do "
        "ano (baciloscopia ou cultura positivas, ou TRM-TB detectável) — a coorte "
        "da Tabela 5 do Boletim. Casos que ainda não encerraram contam no "
        "denominador, então a cura do ano mais recente é um piso. Meta do "
        "Ministério: 85%."
    ),
    "abandono_pct": (
        "Abandono e abandono primário somados, na mesma coorte da cura (casos novos "
        "pulmonares com confirmação laboratorial). Meta do Ministério: 5% ou menos."
    ),
    "hiv_pos_pct": (
        "Casos novos com HIV positivo sobre **todos** os casos novos do ano — a "
        "proporção de coinfecção TB-HIV da Tabela 6 do Boletim. Quem não foi "
        "testado fica no denominador."
    ),
    "incid": (
        "Casos novos do ano sobre a população do Distrito Federal x 100 mil "
        "habitantes. A população é a das projeções do IPEDF que o Boletim usa "
        "(derivada dos coeficientes que ele publica; antes de 2021, a do IBGE "
        "reescalada para continuá-la)."
    ),
    "mortalidade": (
        "Óbitos com causa básica de tuberculose (CID-10 A15–A19, "
        "`sim_mortalidade`/SIM) no ano, por residência no Distrito Federal, "
        "sobre a população estimada x 100 mil habitantes. Diferente do "
        "desfecho \"Óbito por TB\" do encerramento do SINAN: aqui a fonte é a "
        "declaração de óbito, não a ficha de acompanhamento do caso — os "
        "dois podem divergir."
    ),
}


def descricao(metrica: str) -> str | None:
    return DESCRICOES.get(metrica)


#: Vazio de propósito — não há extração de indicadores de programa (contatos
#: examinados, retratamento) para o DF. Mesma decisão do RecifeTB e do
#: manaustb.
INDICADORES_PROGRAMA: tuple = ()
