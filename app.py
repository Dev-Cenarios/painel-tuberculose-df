"""Painel de Monitoramento da Tuberculose — Distrito Federal.

Mesma disposição de tela do hansepe: faixa de identificação, KPIs numa
faixa só, controles numa faixa própria acima das duas colunas, mapa à
esquerda e um aglomerado de abas (Evolução temporal / Ranking / Pirâmide
etária) à direita, tópicos de interesse embaixo.

**Clicar numa Região Administrativa (ou de Saúde) molda o painel inteiro a
ela** — KPIs, evolução temporal, pirâmide e tópicos —, como no hansepe quando
se clica num município. O mapa voa até a região e a pílula "Ver o DF inteiro"
devolve tudo ao total. **Os números vêm de uma fonte só**,
`dados_geolink."DF_geo_TB"` (a única com RA por caso), no DF inteiro e nas
regiões — o total do DF fecha com a soma das regiões e dos casos sem RA. Quem
decide isso é `src/data/painel.py`; a `silver.tuberculose` só empresta as
variáveis dos tópicos que a outra não tem.

**Este arquivo é composição, não lógica.** Toda conta vive em `src/data/`.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cenarios_core import mapa, mapa_componente, resiliencia

from src import doencas, grafico_boletim, grafico_componente
from src.data import boletim, canal, config, microdado_ra, painel
from src.estado import Navegacao
from src.theme import componentes as ui
from src.theme import mapa as mapa_df

pack = doencas.carregar()

st.set_page_config(
    page_title=f"{pack.TITULO} — Distrito Federal",
    layout="wide",
    initial_sidebar_state="collapsed",
)

#: Os seis KPIs numa faixa só, como no RecifeTB — quem faz caber em tela
#: estreita é o CSS compartilhado (`stHorizontalBlock:has(.kpi-card)`,
#: `flex-wrap` + `min-width: 150px`), não uma segunda linha de `st.columns`.
POR_LINHA = 6

ALTURA_PAINEL = 320

#: Piso da altura de um gráfico de composição e largura do nome no eixo.
ALTURA_MINIMA_TOPICO = 175
LARGURA_ROTULO_TOPICO = 130

TODO_O_DF = "— todo o DF —"

ROTULO_NIVEL = {"RA": "Região Administrativa", "REGIAO_SAUDE": "Região de Saúde"}
ROTULO_NIVEL_PLURAL = {"RA": "Regiões Administrativas", "REGIAO_SAUDE": "Regiões de Saúde"}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
# As funções cacheadas recebem valores primitivos — `geo` é uma tupla
# `(nível, chave)` ou `None` —, nunca o `Escopo`: objeto mutável como chave de
# cache é a mesma armadilha documentada no guia de desenvolvimento
# do painel nacional (`docs/desenvolvimento.md` do sinan).


@st.cache_resource
def _anos(geo) -> list[int]:
    return painel.anos(geo)


@st.cache_data(show_spinner=False)
def _kpis(ano: int, geo):
    return painel.kpis(ano, geo)


@st.cache_data(show_spinner=False)
def _serie_anual(geo):
    return painel.serie_anual(geo)


@st.cache_data(show_spinner=False)
def _piramide(ano: int, geo):
    return painel.piramide(ano, geo)


@st.cache_data(show_spinner=False)
def _composicao(ano: int, variavel: str, geo):
    return painel.composicao(ano, variavel, geo)


@st.cache_data(show_spinner=False)
def _canal(ano: int, geo):
    return painel.canal(ano, geo)


@st.cache_data(show_spinner=False)
def _epicurva(ano: int, geo):
    return painel.epicurva(ano, geo)


@st.cache_data(show_spinner=False)
def _boletim(nome: str, ano: int | None = None):
    """Uma série do Boletim (`src/data/boletim.py`) pelo nome da função. Só o nome e
    o ano atravessam o cache — nunca a função."""
    funcao = getattr(boletim, nome)
    return funcao() if ano is None else funcao(ano)


# -- fonte com RA: o mapa e o ranking sempre leem daqui -----------------------
# Ver `src/data/microdado_ra.py`. A mesma fonte dos KPIs, no DF e nas regiões.


@st.cache_resource
def _anos_ra() -> list[int]:
    return microdado_ra.anos_disponiveis()


@st.cache_data(show_spinner=False)
def _valores_ra(ano: int, nivel: str):
    return microdado_ra.valores(ano, nivel)


@st.cache_resource
def _geo_ra():
    import geopandas as gpd

    return gpd.read_parquet(config.geo_dir() / "ra.parquet")


@st.cache_resource
def _geo_regioes_saude():
    import geopandas as gpd

    return gpd.read_parquet(config.geo_dir() / "regioes_saude.parquet")


def _geo(nivel: str):
    return _geo_ra() if nivel == "RA" else _geo_regioes_saude()


@st.cache_resource
def _geojson(nivel: str):
    """Geometrias em GeoJSON, memoizadas **só a geometria**: a cor e o valor
    mudam a cada interação, e guardá-los aqui serviria mapa velho."""
    return mapa.geometrias_geojson(_geo(nivel))


def _coluna_chave(nivel: str) -> str:
    return "ra_chave" if nivel == "RA" else "regiao_saude"


def _coluna_nome(nivel: str) -> str:
    return "ra_nome" if nivel == "RA" else "regiao_saude"


def _nome_de(nivel: str, chave: str) -> str:
    """Nome de exibição de uma RA/Região de Saúde a partir da chave — cai na
    própria chave se não achar (região de saúde já é o nome)."""
    try:
        geo = _geo(nivel)
        coluna_chave, coluna_nome = _coluna_chave(nivel), _coluna_nome(nivel)
        achado = geo.loc[geo[coluna_chave] == chave, coluna_nome]
        return achado.iloc[0] if not achado.empty else chave
    except Exception:  # a malha ausente não derruba o cabeçalho
        return chave


# ---------------------------------------------------------------------------
# Callbacks — uma passada por interação
# ---------------------------------------------------------------------------
# Um botão que muda o estado e chama `st.rerun()` faz o script rodar **duas
# vezes**: a primeira desenha um estado intermediário, a segunda o definitivo, e
# o olho vê as duas — era a piscada ao clicar em "Ver o DF inteiro". O callback
# roda **antes** do script, então ele já nasce com o estado novo.


def _ao_mudar_ano() -> None:
    st.session_state.nav.ano = st.session_state["ano"]


def _voltar_ao_df() -> None:
    st.session_state.detalhe_geo = None


def _ao_buscar() -> None:
    nivel_ = "RA" if (st.session_state.get("recorte-mapa") or "RA") == "RA" else "REGIAO_SAUDE"
    escolhida = st.session_state.get(f"busca_{nivel_}")
    st.session_state.detalhe_geo = (nivel_, escolhida) if escolhida else None


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

if "nav" not in st.session_state:
    st.session_state.nav = Navegacao(ano=max(_anos(None)))
nav: Navegacao = st.session_state.nav

# A RA/Região selecionada persiste entre execuções — o clique do deck.gl (ou
# da barra do ranking) não chega como evento único, e sim como estado que
# continua lá na próxima passada (mesma armadilha documentada no RecifeTB).
if "detalhe_geo" not in st.session_state:
    st.session_state.detalhe_geo = None

# O nível do mapa vem do **estado do widget**, lido antes de ele ser desenhado:
# os KPIs ficam acima do controle, e a seleção precisa ser válida para o nível
# corrente já na primeira linha da página. Trocar RA <-> Região de Saúde
# invalida a seleção, porque as chaves de um lado não existem no outro.
nivel = "RA" if (st.session_state.get("recorte-mapa") or "RA") == "RA" else "REGIAO_SAUDE"
if st.session_state.detalhe_geo and st.session_state.detalhe_geo[0] != nivel:
    st.session_state.detalhe_geo = None

# O clique no mapa e no ranking volta como valor do componente, que o Streamlit
# guarda em `st.session_state[key]`. Lido **aqui, antes de desenhar qualquer
# coisa**, o clique já vale na passada em que ele chegou: o painel inteiro nasce
# com a região nova, sem a passada intermediária que um `st.rerun()` no meio do
# script causava. O `nonce` impede o mesmo clique de ser tratado duas vezes.
for _componente, _nonce, _alvo_do_clique in (
    # O mapa vem do core, que por padrão lê chaves municipais: as do DF
    # (RA, Região de Saúde) vão junto.
    ("mapa", "clique_mapa",
     lambda ev, visto: mapa_componente.alvo_do_clique(ev, visto, mapa_df.CAMPOS_CLIQUE)),
    ("ranking", "clique_ranking", grafico_componente.alvo_do_clique),
):
    _alvo, _novo = _alvo_do_clique(
        st.session_state.get(_componente), st.session_state.get(_nonce)
    )
    if _novo:
        st.session_state[_nonce] = _novo
    if _alvo:
        st.session_state.detalhe_geo = (nivel, _alvo)

#: ``(nível, chave)`` da região selecionada, ou ``None`` para o DF inteiro. É o
#: argumento que faz o painel inteiro responder a ela.
geo = st.session_state.detalhe_geo
selecionado = geo[1] if geo else None
local = _nome_de(*geo) if geo else "Distrito Federal"

# O seletor de busca segue a seleção (que pode ter vindo do mapa). O valor é
# posto no estado **antes** do widget existir, e o widget não leva `index`.
st.session_state[f"busca_{nivel}"] = selecionado

# A fonte por região só vai de 2010 em diante; o ano corrente cede ao mais
# próximo que ela tem. O estado do widget acompanha, ou o seletor ficaria com
# um valor que não está mais nas opções.
if "ano" not in st.session_state:
    st.session_state["ano"] = nav.ano
ano_ok = painel.ano_valido(nav.ano, geo)
if ano_ok != nav.ano:
    nav.ano = ano_ok
    st.session_state["ano"] = ano_ok

st.markdown(ui.css_base(), unsafe_allow_html=True)
st.markdown(ui.css_layout(), unsafe_allow_html=True)
st.markdown(
    f"<style>:root{{--intro-accent:{pack.CORES['primary']};}}</style>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cabeçalho e KPIs
# ---------------------------------------------------------------------------

st.markdown(
    ui.faixa_intro(
        f"Painel de Monitoramento da {pack.TITULO_CURTO} do DF",
        escopo=nav.trilha(local if geo else None),
        cor=pack.CORES["primary"],
    ),
    unsafe_allow_html=True,
)

# "Dados até / Processado em", à direita, sob o cabeçalho. O elemento existe
# **sempre** — sem o registro vai um vazio —, para a árvore da página não depender
# de o arquivo existir (posição na árvore é o que o Streamlit usa para identificar).
_procedencia = painel.procedencia()
st.markdown(
    ui.procedencia(
        _procedencia["dados_ate"], _procedencia["processado_em"], ajuda=_procedencia["ajuda"]
    )
    if _procedencia
    else '<div aria-hidden="true"></div>',
    unsafe_allow_html=True,
)

#: A métrica que o mapa pinta, lida do estado do widget **antes** de ele ser
#: desenhado: os cards ficam acima do seletor, e lendo o retorno do widget
#: eles realçariam a métrica antiga até o rerun seguinte. O estado do widget
#: já vem atualizado no início da passada.
metrica_em_foco = st.session_state.get("metrica-mapa") or pack.METRICAS_MAPA[0]


def _ajuda_do_card(metrica: str, valor) -> str:
    """Texto do "i" do card. Com região selecionada, acrescenta o que muda de
    significado ao sair do DF inteiro."""
    partes = [pack.rotulo(metrica), pack.descricao(metrica)]
    if geo is not None:
        if metrica == "mortalidade":
            partes.append(
                "Não existe por região: o SIM não traz a Região Administrativa de "
                "residência na nossa extração."
            )
        elif metrica == "incid":
            partes.append(
                "Aproximada: a população da região é estimada pela proporção do "
                "Censo 2022 aplicada à população anual do DF."
            )
        elif metrica in ("cura_pct", "abandono_pct", "hiv_pos_pct") and valor is None:
            partes.append(
                f"Sem dado: menos de {painel.MINIMO_PARA_PERCENTUAL} registros nesta "
                f"região — proporção sobre tão poucos casos não é confiável."
            )
    return " — ".join(p for p in partes if p)


def _card(metrica: str, atual, anterior) -> None:
    """Um card de KPI. Realça a métrica ativa do mapa, como no hansepe."""
    valor = getattr(atual, metrica, None)
    antes = getattr(anterior, metrica, None) if anterior else None
    taxa = metrica in pack.TAXAS
    sub = f"{local} • {nav.ano}"
    if fracao := pack.FRACAO_KPI.get(metrica):
        num, den = (getattr(atual, campo, None) for campo in fracao)
        if num is not None and den:
            sub += f" • {ui.formatar_inteiro(num)} de {ui.formatar_inteiro(den)}"
    st.markdown(
        ui.kpi_card(
            pack.rotulo_curto(metrica),
            ui.formatar_decimal(valor) if taxa else ui.formatar_inteiro(valor),
            cor=pack.cor(metrica),
            subtitulo=sub,
            selecionado=metrica == metrica_em_foco,
            badge_delta=ui.delta(
                valor, antes, taxa=taxa, bom_se_cai=metrica in pack.BOM_SE_CAI,
            ),
            ajuda=_ajuda_do_card(metrica, valor),
            icone=pack.icone(metrica),
        ),
        unsafe_allow_html=True,
    )


with resiliencia.painel("Indicadores"):
    atual = _kpis(nav.ano, geo)
    anterior = _kpis(nav.ano - 1, geo) if nav.ano - 1 in _anos(geo) else None

    # Chave própria para o CSS mirar **esta** faixa e não qualquer linha que
    # contenha um `.kpi-card` — ver `.st-key-faixa-kpis` em `css_layout`.
    with st.container(key="faixa-kpis"):
        for coluna, metrica in zip(st.columns(POR_LINHA), pack.LAYOUT_KPI, strict=True):
            with coluna:
                _card(metrica, atual, anterior)

    # Contêiner **sempre presente**: o Streamlit identifica o elemento pela
    # posição na árvore, e uma legenda que aparece só com região selecionada
    # empurra tudo o que vem depois um lugar para baixo — o mapa e todos os
    # gráficos eram destruídos e recriados. Aqui só o texto muda; a altura é
    # reservada por CSS (`.st-key-nota-regiao`), então nada se mexe.
    with st.container(key="nota-regiao"):
        if geo is not None:
            st.caption(
                f"**{local}** — o painel inteiro mostra só esta região. Os números são da "
                f"mesma fonte do total do DF; o que a região não tem é a mortalidade "
                f"(o SIM não traz a região) e a população, que é estimada pela "
                f"proporção do Censo 2022."
            )
        else:
            st.caption(
                "Clique numa região no mapa, no ranking ou na busca: o painel inteiro "
                "passa a mostrar só ela."
            )


# ---------------------------------------------------------------------------
# Controles — Ano / Métrica do mapa / Nível / Cores / Busca, numa faixa só
# ---------------------------------------------------------------------------

with resiliencia.painel("Controles"), st.container(border=True, key="cartao-controles"):
    col_ano, col_metrica, col_recorte, col_cores, col_busca = st.columns(
        [1.1, 3.6, 2.7, 2.5, 2.5], vertical_alignment="top"
    )

    with col_ano:
        # Sem `index`: o estado do widget (`key="ano"`) é a única fonte do valor,
        # e ele acompanha o ano quando a região selecionada o corrige. A troca é
        # um callback, não um `st.rerun()`: uma passada só.
        st.selectbox("Ano", _anos(geo), key="ano", on_change=_ao_mudar_ano)

    with col_metrica:
        metrica_mapa = st.segmented_control(
            "Métrica do mapa", pack.METRICAS_MAPA,
            format_func=pack.rotulo_curto, default=pack.METRICAS_MAPA[0],
            key="metrica-mapa",
            help="Define o que o mapa pinta e o que o ranking ordena.",
        ) or pack.METRICAS_MAPA[0]

    with col_recorte:
        st.segmented_control(
            "Nível do mapa", ["RA", "Região de Saúde"], default="RA", key="recorte-mapa",
            help="Regiões Administrativas, ou agregado por Região de Saúde.",
        )

    with col_cores:
        classificacao = st.segmented_control(
            "Cores", mapa_df.CLASSIFICACOES,
            format_func=mapa_df.ROTULO_CLASSIFICACAO.get,
            default=mapa_df.CLASSIFICACAO_PADRAO, key="classificacao",
            help=mapa_df.AJUDA_CLASSIFICACAO,
        ) or mapa_df.CLASSIFICACAO_PADRAO

    with col_busca:
        # O valor mora no estado (`busca_<nível>`), posto no início do script para
        # acompanhar o clique no mapa; a escolha do usuário volta por callback.
        try:
            geo_busca = _geo(nivel)
            nomes_busca = dict(
                zip(geo_busca[_coluna_chave(nivel)], geo_busca[_coluna_nome(nivel)], strict=True)
            )
            opcoes_busca = [None, *sorted(nomes_busca, key=lambda c: nomes_busca[c])]
            st.selectbox(
                f"Buscar {ROTULO_NIVEL[nivel]}",
                opcoes_busca,
                key=f"busca_{nivel}",
                format_func=lambda c: TODO_O_DF if c is None else nomes_busca[c],
                on_change=_ao_buscar,
            )
        except Exception:  # a busca não derruba o resto dos controles
            st.caption("Busca indisponível: malha geográfica não encontrada.")


# ---------------------------------------------------------------------------
# Preparo comum ao mapa e ao ranking — a mesma escala de cor para os dois
# ---------------------------------------------------------------------------

anos_ra = _anos_ra()
ano_mapa = nav.ano if nav.ano in anos_ra else max(anos_ra)
valores_ra = _valores_ra(ano_mapa, nivel)

escala_mapa = None
if not valores_ra.empty:
    serie_valores = valores_ra.set_index("chave")[metrica_mapa]
    escala_mapa = mapa.escala(
        serie_valores, pack.rampa_mapa(metrica_mapa),
        metodo=classificacao, decimais=0 if metrica_mapa == "casos" else 1,
        quantis=mapa_df.QUANTIS,
    )


def _ao_clicar_na_legenda() -> None:
    """Guarda a faixa realçada **antes** do mapa ser desenhado.

    A legenda fica embaixo do mapa que ela comanda. Lido no ponto do widget, o
    clique só chegaria ao mapa no rerun seguinte. Clicar na faixa já marcada
    desmarca, e o mapa volta inteiro.
    """
    st.session_state["faixa_realcada"] = st.session_state.get("faixa_legenda")


def _detalhes_tooltip(valores: pd.DataFrame, metrica: str):
    """Linhas extras do tooltip: as **outras** métricas do mapa, com a bolinha
    na cor de cada uma. A pintada já vem no título do balão."""
    casas = {"casos": 0, "incid": 1, "cura_pct": 1, "abandono_pct": 1}
    indexado = valores.set_index("chave")
    return [
        (pack.rotulo_curto(m), indexado[m], pack.cor(m), casas[m])
        for m in pack.METRICAS_MAPA
        if m != metrica
    ]


esquerda, direita = st.columns([5, 6], gap="medium")

with esquerda, st.container(border=True, key="cartao-mapa"), resiliencia.painel("Mapa"):
    st.markdown(
        ui.titulo_painel(
            "Distribuição geográfica",
            ajuda=(
                "Clique numa região: o painel inteiro passa a mostrar só ela. "
                "A mesma fonte dos números do DF inteiro: a soma das regiões, mais os "
                "casos sem Região Administrativa identificada, que o mapa não "
                "desenha, dá o total do DF."
            ),
        ),
        unsafe_allow_html=True,
    )

    if valores_ra.empty:
        st.caption("Sem dado geolinkado para este ano.")
    else:
        camada = _geo(nivel)
        chave_geo, nome_geo = _coluna_chave(nivel), _coluna_nome(nivel)

        mapa_deck, escala_ = mapa.deck(
            camada, serie_valores, chave=chave_geo, coluna_nome=nome_geo,
            rampa=pack.rampa_mapa(metrica_mapa), rotulo_metrica=pack.rotulo(metrica_mapa),
            decimais=0 if metrica_mapa == "casos" else 1,
            altura=mapa_df.ALTURA, largura=mapa_df.LARGURA, geometrias=_geojson(nivel),
            destacado=selecionado, metodo=classificacao, quantis=mapa_df.QUANTIS,
            foco_vizinhanca=mapa_df.FOCO_VIZINHANCA, foco_minimo=mapa_df.FOCO_MINIMO,
            detalhes=_detalhes_tooltip(valores_ra, metrica_mapa),
            faixa_realcada=st.session_state.get("faixa_realcada"),
            contornos=mapa_df.CONTORNOS,
        )
        # Componente próprio, com `key` **estável**: é ela que mantém o deck
        # vivo entre reruns e faz a câmera voar de uma RA à outra e a cor
        # interpolar, em vez de trocar de slide. O clique volta com um nonce; o
        # último tratado fica em `session_state` para o mesmo evento não
        # navegar duas vezes.
        # O clique é tratado no início do script (`st.session_state["mapa"]`), não aqui.
        mapa_componente.desenhar(
            mapa_deck, altura=mapa_df.ALTURA, key="mapa",
            titulo=f"Mapa do Distrito Federal: {pack.rotulo(metrica_mapa)}",
        )

        # A legenda é clicável: clicar numa faixa apaga o resto do mapa, e
        # clicar de novo devolve. É um `st.pills`, e os quadradinhos de cor, que
        # o widget não tem, entram por CSS. O número de cada faixa vai no
        # próprio rótulo.
        contagem = mapa.classificar(serie_valores, escala_).value_counts()
        faixas = [r for r in escala_.rotulos if r in escala_.cores]

        def _rotulo_faixa(r: str, _contagem=contagem) -> str:
            return f"{r}  ({int(_contagem.get(r, 0))})"

        st.markdown(
            ui.titulo_legenda(pack.rotulo(metrica_mapa), ROTULO_NIVEL_PLURAL[nivel]),
            unsafe_allow_html=True,
        )
        st.markdown(
            ui.cores_das_faixas("faixa_legenda", [escala_.cores[r] for r in faixas]),
            unsafe_allow_html=True,
        )
        st.pills(
            "Faixa em destaque", faixas, format_func=_rotulo_faixa,
            selection_mode="single", key="faixa_legenda",
            on_change=_ao_clicar_na_legenda, label_visibility="collapsed",
        )
        if metrica_mapa == "incid":
            st.caption(
                "Incidência aproximada: população de cada RA estimada pela "
                "proporção do Censo 2022 aplicada à população anual do DF — "
                "não é uma série de população por RA medida ano a ano."
            )
        if metrica_mapa in ("cura_pct", "abandono_pct"):
            sem_taxa = int(valores_ra[metrica_mapa].isna().sum())
            if sem_taxa:
                st.caption(
                    f"{sem_taxa} de {len(valores_ra)} {ROTULO_NIVEL_PLURAL[nivel]} não "
                    f"mostram esta taxa: menos de {microdado_ra.MINIMO_PARA_PERCENTUAL} "
                    f"encerramentos no ano — proporção sobre tão poucos casos não é "
                    f"confiável, não é dado faltando."
                )
        elif sem_dado := int(contagem.get(mapa.ROTULO_SEM_DADO, 0)):
            st.caption(f"{sem_dado} {ROTULO_NIVEL_PLURAL[nivel]} sem dado, em cinza.")

        ignorados = int(microdado_ra.total(ano_mapa) - valores_ra["casos"].sum())
        if ignorados > 0:
            rotulo_geo = "RA identificada" if nivel == "RA" else "Região de Saúde"
            st.caption(
                f"{ignorados} notificações de {ano_mapa} sem {rotulo_geo} "
                f"não aparecem no mapa."
            )

    # Contêiner **sempre presente**, com a altura reservada por CSS: o botão
    # aparece e some dentro dele sem deslocar nada. Pílula com borda — o estilo vem
    # de `.st-key-voltar_df` em `css_layout`. O callback devolve o painel inteiro ao
    # total do DF antes do script rodar, e o mapa **voa** de volta em vez de piscar.
    with st.container(key="barra-voltar"):
        if selecionado:
            st.button(
                "◀ Ver o DF inteiro", key="voltar_df",
                help=f"Sair de {local}", on_click=_voltar_ao_df,
            )
        else:
            # Um contêiner **vazio não existe no DOM** — e a altura reservada por
            # CSS some com ele. Um elemento vazio o mantém lá, ocupando o espaço
            # que a pílula ocupará.
            st.markdown('<div aria-hidden="true"></div>', unsafe_allow_html=True)


def _com_local(titulo: str) -> str:
    """Título de seção que diz de onde são os números quando há região."""
    return f"{titulo} — {local}" if geo else titulo


with direita, st.container(border=True, key="cartao-graficos"):
    aba_evolucao, aba_ranking, aba_piramide = st.tabs(
        ["Evolução temporal", "Ranking", "Pirâmide etária"]
    )

    with aba_evolucao, resiliencia.painel("Evolução temporal"):
        horizonte = st.radio(
            "Horizonte", ["Meses do ano", "Todos os anos"],
            horizontal=True, label_visibility="collapsed", key="horizonte-evolucao",
        )

        if horizonte == "Meses do ano":
            canal_atual = _canal(nav.ano, geo)
            figura = grafico_componente.canal_endemico(
                canal_atual, rotulo=pack.rotulo("incid"), cor=pack.cor("incid"),
            )
            titulo_serie = "Canal endêmico"
            rodape = ""
            if canal_atual.anos:
                fora = canal.meses_fora_da_faixa(canal_atual)
                acima = int((fora["posicao"] == "acima").sum())
                rodape = grafico_componente.AVISO_CANAL.format(
                    n=len(canal_atual.anos),
                    anos=", ".join(str(a) for a in canal_atual.anos),
                )
                if geo is not None:
                    rodape += (
                        " Na região, a população é estimada pela proporção do Censo "
                        "2022 e, com poucos casos por mês, a faixa oscila muito — leia "
                        "como tendência, não como limite."
                    )
                if acima:
                    rodape += f" Em {nav.ano}, **{acima} de 12 meses** ficaram acima do topo da faixa."
            else:
                rodape = (
                    "Sem anos anteriores com população extraída para formar a "
                    "faixa — `pop_ibge` só cobre 2010 em diante."
                )
        else:
            serie_hist = _serie_anual(geo)
            figura = grafico_componente.evolucao_anual(
                serie_hist, rotulo="Casos novos", cor=pack.cor("casos"), ano=nav.ano,
            )
            titulo_serie = "Casos novos por ano"
            rodape = (
                "2025 fica fora da série: a notificação está completa, mas a "
                "situação de encerramento ainda não fechou naquele ano."
            )

        st.markdown(
            ui.titulo_painel(
                _com_local(titulo_serie), ajuda=rodape if horizonte == "Meses do ano" else ""
            ),
            unsafe_allow_html=True,
        )
        # Mesma `key` para o canal e a série anual: a instância do gráfico
        # fica viva ao trocar o horizonte, e o ECharts anima a passagem de um
        # para o outro em vez de redesenhar.
        grafico_componente.desenhar(figura, altura=ALTURA_PAINEL - 90, key="evolucao")
        if horizonte == "Todos os anos":
            st.caption(rodape)

        # A epicurva fica sempre embaixo, como no RecifeTB: o canal dobra o
        # tempo em doze meses e pergunta se o mês fugiu do padrão daquele
        # mês; a epicurva estica o tempo numa linha só e pergunta para onde
        # a doença vem indo.
        st.markdown(ui.titulo_painel(_com_local("Epicurva por mês")), unsafe_allow_html=True)
        grafico_componente.desenhar(
            grafico_componente.epicurva(
                _epicurva(nav.ano, geo), rotulo="Casos novos", cor=pack.cor("casos"),
                ano_em_foco=nav.ano,
            ),
            altura=220, key="epicurva",
        )

    with aba_ranking, resiliencia.painel("Ranking"):
        if valores_ra.empty:
            st.markdown(ui.painel_vazio("Ranking", "Sem dado para este recorte."), unsafe_allow_html=True)
        else:
            # `dict.fromkeys` deduplica: no nível Região de Saúde, chave e
            # nome são a mesma coluna (`regiao_saude`), e selecioná-la duas
            # vezes faria o rename colapsar as duas em "nome" só, sem
            # sobrar "chave" — mesmo bug já corrigido em `mapa.deck()`.
            coluna_chave, coluna_nome = _coluna_chave(nivel), _coluna_nome(nivel)
            colunas_geo = list(dict.fromkeys([coluna_chave, coluna_nome]))
            geo_nomes = _geo(nivel)[colunas_geo].rename(columns={coluna_chave: "chave"})
            if coluna_chave == coluna_nome:
                # Região de Saúde: chave e nome são a mesma coluna — o nome
                # de exibição é a própria chave, sem coluna extra a juntar.
                geo_nomes["nome"] = geo_nomes["chave"]
            else:
                geo_nomes = geo_nomes.rename(columns={coluna_nome: "nome"})

            tabela = valores_ra.merge(geo_nomes, on="chave", how="left")
            tabela = tabela[["chave", "nome", metrica_mapa]].rename(columns={metrica_mapa: "valor"})
            tabela = tabela.dropna(subset=["valor"]).sort_values("valor", ascending=False)

            maximo = len(tabela)
            top_n = (
                st.slider("Quantos exibir", 5, maximo, min(15, maximo), step=5,
                          key=f"top_n_{nivel}")
                if maximo > 5
                else maximo
            )

            exibidas = tabela.head(top_n)
            grafico_componente.desenhar(
                grafico_componente.ranking(
                    exibidas, rotulo=pack.rotulo_curto(metrica_mapa),
                    cor=pack.cor(metrica_mapa), escala=escala_mapa,
                    selecionado=selecionado,
                    casas=0 if metrica_mapa == "casos" else 1,
                ),
                altura=max(
                    ALTURA_PAINEL, grafico_componente.ALTURA_MIN_RANKING,
                    grafico_componente.ALTURA_BARRA_RANKING * len(exibidas)
                    + grafico_componente.ALTURA_EIXO_RANKING,
                ),
                key="ranking",
            )
            # O clique na barra é tratado no início do script
            # (`st.session_state["ranking"]`).

    with aba_piramide, resiliencia.painel("Pirâmide etária"):
        dados_pir = _piramide(nav.ano, geo)
        st.markdown(ui.titulo_painel(_com_local("Casos por sexo e faixa etária")), unsafe_allow_html=True)
        st.caption(
            "Sem taxa por 100 mil: a extração não traz população do DF por "
            "faixa etária."
        )
        faixas_pir = dados_pir["faixa_etaria"].nunique() if not dados_pir.empty else 0
        grafico_componente.desenhar(
            grafico_componente.piramide(dados_pir, rotulo="Casos"),
            altura=max(ALTURA_PAINEL - 60, 280, 30 * faixas_pir),
            key="piramide",
        )


# ---------------------------------------------------------------------------
# Indicadores do Boletim da SES-DF
# ---------------------------------------------------------------------------
# Os gráficos do "Panorama epidemiológico da tuberculose no Distrito Federal"
# (Gevist/Divep/SVS/SES-DF), no desenho do Boletim, para quem lê um e o outro
# encontrar o mesmo número no mesmo gráfico. São sempre por **Região de Saúde**,
# como o Boletim; com uma região selecionada no mapa, a Região de Saúde dela ganha
# destaque nas linhas. As contas moram em `src/data/boletim.py`.

ALTURA_BOLETIM = 330
ANO_FINAL_BOLETIM = "o último ano da extração"

#: Meta do Ministério da Saúde para o abandono (5%) e a cura (85%).
_META_INCIDENCIA = (10.0, "Meta: menos de 10 por 100 mil")


def _regiao_em_destaque() -> str | None:
    """Região de Saúde que contém a seleção do mapa, ou ``None`` sem seleção."""
    if not geo:
        return None
    nivel_, chave_ = geo
    return config.RA_PARA_REGIAO_SAUDE.get(chave_) if nivel_ == "RA" else chave_


def _grafico_boletim(titulo: str, ajuda: str, opcao: dict, *, key: str, altura: int = ALTURA_BOLETIM) -> None:
    st.markdown(ui.titulo_painel(titulo, ajuda=ajuda), unsafe_allow_html=True)
    grafico_componente.desenhar(opcao, altura=altura, key=key)


with resiliencia.painel("Indicadores do Boletim"), st.container(
    border=True, key="cartao-boletim"
):
    st.markdown(
        ui.titulo_painel(
            "Indicadores do Boletim da SES-DF",
            ajuda=(
                "Os gráficos do Boletim \"Panorama epidemiológico da tuberculose no "
                "Distrito Federal\" (Gevist/Divep/SVS/SES-DF, mar/2026), calculados "
                "sobre a extração por região do SINAN. Mesmas coortes e mesma divisão "
                "em sete Regiões de Saúde; o Boletim vai a 2025 e a extração termina "
                "em dez/2024. Casos novos: tipo de entrada caso novo, não sabe ou "
                "pós-óbito, sem mudança de diagnóstico."
            ),
        ),
        unsafe_allow_html=True,
    )
    destaque = _regiao_em_destaque()
    # Elemento **sempre presente**, como a nota da região lá em cima: o Streamlit
    # identifica o elemento pela posição na árvore, e uma legenda que só existe com
    # região selecionada empurra tudo o que vem depois — os gráficos eram recriados.
    st.caption(
        f"**{boletim.rotulo(destaque)}** em destaque: é a Região de Saúde de {local}."
        if destaque
        else "Selecione uma região no mapa: a Região de Saúde dela ganha destaque nas linhas."
    )

    (aba_inc, aba_diag, aba_perfil, aba_desf, aba_hiv, aba_vuln) = st.tabs([
        "Incidência", "Diagnóstico e tratamento", "Perfil", "Desfecho",
        "Coinfecção TB-HIV", "Populações vulneráveis",
    ])

    with aba_inc:
        _grafico_boletim(
            "Incidência de TB pulmonar com confirmação laboratorial",
            "Gráfico 1 do Boletim: casos novos pulmonares com confirmação "
            "laboratorial (baciloscopia ou cultura positivas, ou TRM-TB detectável) "
            "por 100 mil habitantes. A população das regiões é estimada pela "
            "proporção do Censo 2022 sobre a do DF (IPEDF); o Boletim usa projeções "
            "do IPEDF por região, então as linhas das regiões diferem um pouco.",
            grafico_boletim.linhas_por_regiao(
                _boletim("incidencia_pulmonar_lab"), rotulo="Casos por 100 mil hab.",
                destaque=destaque, regua=_META_INCIDENCIA,
            ),
            key="bol-incidencia",
        )

    with aba_diag:
        col_trm, col_tdo = st.columns(2, gap="medium")
        with col_trm:
            _grafico_boletim(
                "Casos pulmonares que fizeram o TRM-TB",
                "Gráfico 2 do Boletim: proporção de casos novos de tuberculose "
                "pulmonar que realizaram o teste rápido molecular.",
                grafico_boletim.empilhado_100(
                    _boletim("trm_realizado"), x="ano", nome_x="Ano de diagnóstico",
                    cores={"Realizou": "#3891C0", "Não realizou": "#C0663C", "Ign/Branco": "#C3C7CE"},
                    valores=True,
                ),
                key="bol-trm",
            )
        with col_tdo:
            _grafico_boletim(
                "Tratamento diretamente observado (TDO)",
                "Gráfico 3 do Boletim: proporção dos casos novos pulmonares com "
                "confirmação laboratorial que fizeram o TDO, por Região de Saúde.",
                grafico_boletim.linhas_por_regiao(
                    _boletim("tdo_por_regiao"), rotulo="% em TDO", maximo=100,
                    destaque=destaque,
                ),
                key="bol-tdo",
            )
        _grafico_boletim(
            "Contatos examinados",
            "Gráfico 6 do Boletim: contatos examinados sobre os identificados, dos "
            "casos novos pulmonares com confirmação laboratorial. Região com poucos "
            "casos oscila muito de um ano para o outro.",
            grafico_boletim.linhas_por_regiao(
                _boletim("contatos_examinados"), rotulo="% examinados", maximo=100,
                destaque=destaque,
            ),
            key="bol-contatos",
        )

    with aba_perfil:
        col_a, col_b = st.columns(2, gap="medium")
        with col_a:
            _grafico_boletim(
                "Sexo", "Tabela 2 do Boletim: proporção de casos novos por sexo.",
                grafico_boletim.empilhado_100(
                    _boletim("sexo"), x="ano", nome_x="Ano de diagnóstico",
                    cores={"Masculino": "#3F4E9E", "Feminino": "#C0663C", "Ign/Branco": "#C3C7CE"},
                    valores=True,
                ),
                key="bol-sexo",
            )
        with col_b:
            _grafico_boletim(
                "Faixa etária",
                "Tabela 4 do Boletim: proporção de casos novos por faixa etária.",
                grafico_boletim.empilhado_100(
                    _boletim("faixa_etaria"), x="ano", nome_x="Ano de diagnóstico",
                    cor="#3891C0", valores=True,
                ),
                key="bol-faixa",
            )
        col_c, col_d = st.columns(2, gap="medium")
        with col_c:
            _grafico_boletim(
                "Raça/cor",
                "Gráfico 4 do Boletim: proporção de casos novos segundo raça/cor.",
                grafico_boletim.empilhado_100(
                    _boletim("raca_cor"), x="ano", nome_x="Ano de diagnóstico",
                    cor="#6C5CA8", valores=True,
                ),
                key="bol-raca",
            )
        with col_d:
            _grafico_boletim(
                "Escolaridade",
                "Gráfico 5 do Boletim: proporção de casos novos segundo escolaridade. "
                "Mais da metade é ignorada ou em branco em todo o período — limita o "
                "que se pode dizer dos determinantes sociais.",
                grafico_boletim.empilhado_100(
                    _boletim("escolaridade"), x="ano", nome_x="Ano de diagnóstico",
                    cor="#5A9E2E",
                ),
                key="bol-escolaridade",
            )

    with aba_desf:
        anos_bol = boletim.anos()
        primeiro, ultimo = anos_bol[0], anos_bol[-1]
        col_p, col_u = st.columns(2, gap="medium")
        for coluna_, ano_ in ((col_p, primeiro), (col_u, ultimo)):
            with coluna_:
                _grafico_boletim(
                    f"Situação de encerramento — {ano_}",
                    "Gráfico 7 do Boletim: situação de encerramento dos casos novos "
                    "pulmonares com confirmação laboratorial, por Região de Saúde. "
                    "Casos que ainda não encerraram entram como Ign/Branco, então o "
                    "ano mais recente subestima a cura. Metas do Ministério: 85% de "
                    "cura e 5% ou menos de abandono.",
                    grafico_boletim.empilhado_100(
                        _boletim("desfecho_por_regiao", ano_), x="serie",
                        cores=grafico_boletim.COR_DESFECHO,
                        rotulos_x={s: (boletim.rotulo(s) if s != boletim.DF else "DF")
                                   for s in [*boletim.REGIOES, boletim.DF]},
                        inclinar=True, valores=True,
                    ),
                    key=f"bol-desfecho-{ano_}", altura=ALTURA_BOLETIM + 30,
                )

    with aba_hiv:
        col_h, col_r = st.columns(2, gap="medium")
        with col_h:
            _grafico_boletim(
                "Testagem para HIV e positividade",
                "Gráfico 8 do Boletim: proporção de casos novos que fizeram o teste "
                "de HIV e proporção com resultado positivo — as duas sobre todos os "
                "casos novos do ano.",
                grafico_boletim.colunas_agrupadas(
                    _boletim("hiv_testagem"),
                    cores={"Realizou": "#3891C0", "Positivo": "#BE185D"},
                ),
                key="bol-hiv",
            )
        with col_r:
            _grafico_boletim(
                "Coinfecção TB-HIV por região",
                "Tabela 6 do Boletim: proporção de casos novos com HIV positivo, por "
                "Região de Saúde.",
                grafico_boletim.linhas_por_regiao(
                    _boletim("hiv_por_regiao"), rotulo="% com HIV positivo", destaque=destaque,
                ),
                key="bol-hiv-regiao",
            )

    with aba_vuln:
        col_ppl, col_psr = st.columns(2, gap="medium")
        with col_ppl:
            _grafico_boletim(
                "Pessoas privadas de liberdade",
                "Gráfico 11 do Boletim: proporção de casos novos em pessoas privadas "
                "de liberdade. A Região Leste abriga o Complexo Penitenciário da "
                "Papuda. O coeficiente de incidência na população prisional "
                "(Gráfico 10) não é calculado: falta o denominador, as estimativas "
                "da Secretaria Nacional de Políticas Penais.",
                grafico_boletim.linhas_por_regiao(
                    _boletim("privados_de_liberdade"), rotulo="% dos casos novos",
                    destaque=destaque,
                ),
                key="bol-ppl",
            )
        with col_psr:
            _grafico_boletim(
                "Pessoas em situação de rua",
                "Gráfico 12 do Boletim: proporção de casos novos em pessoas em "
                "situação de rua. Variações podem refletir o registro da condição "
                "no SINAN, e não só a transmissão.",
                grafico_boletim.linhas_por_regiao(
                    _boletim("situacao_de_rua"), rotulo="% dos casos novos",
                    destaque=destaque,
                ),
                key="bol-psr",
            )

    st.caption(
        "Fonte: SINAN, extração por região do banco `cenarios_ai`. Referência: "
        "Boletim \"Panorama epidemiológico da tuberculose no Distrito Federal, 2021 a "
        "2025\" (SES-DF, mar/2026), que também usa 2025 e a mortalidade por região — "
        "ainda fora desta extração. Nada aqui é recalculado a partir do PDF: são as "
        "mesmas definições aplicadas ao microdado."
    )


# ---------------------------------------------------------------------------
# Linha 2: composição
# ---------------------------------------------------------------------------

TOPICOS_POR_LINHA = 2

AJUDA_TOPICOS = (
    "Distribuição percentual de cada variável do SINAN entre os casos novos do ano "
    "selecionado. Quando o Boletim da SES-DF tem o gráfico da mesma variável, a "
    "linha de baixo do tópico diz onde, na seção acima. "
    "As dez que abrem são um recorte de leitura comum em vigilância de TB; as "
    "demais estão no seletor. Abaixo de cinco registros o percentual não é "
    "publicável e só a contagem aparece. Com uma região selecionada, só as "
    "variáveis que a extração por região traz."
)


def _desenhar_topico(variavel: str, rotulo: str, altura: int) -> None:
    dados = _composicao(nav.ano, variavel, geo)
    # Variável que só existe no DF inteiro: o gráfico **continua no lugar**, com um
    # recado, em vez de sair da grade. Tirar o gráfico mudava o pareamento das
    # colunas e remontava todos os que vinham depois.
    recado = (
        "Só existe para o DF inteiro"
        if geo is not None and not painel.variavel_disponivel(variavel, geo)
        else None
    )
    grafico_componente.desenhar(
        grafico_componente.composicao(
            dados,
            rotulo=rotulo,
            cor=pack.cor("casos"),
            largura_rotulo=LARGURA_ROTULO_TOPICO,
            recado_vazio=recado,
        ),
        altura=altura,
        key=f"topico-{variavel}",
    )
    if not dados.empty and dados["pct"].isna().all():
        st.caption(
            f"Base de {int(dados['total'].iloc[0])} registros — pequena demais "
            f"para percentual. Só a contagem aparece."
        )
    # Sempre um elemento aqui (texto ou espaço), para os dois gráficos da linha
    # terminarem na mesma altura com ou sem equivalente no Boletim.
    equivalente = pack.EQUIVALENTE_NO_BOLETIM.get(variavel)
    st.caption(
        f"Por ano, no Boletim: {equivalente}, na seção acima." if equivalente else " "
    )


with resiliencia.painel("Tópicos de interesse"), st.container(
    border=True, key="cartao-composicao"
):
    st.markdown(
        ui.titulo_painel(_com_local("Tópicos de interesse"), ajuda=AJUDA_TOPICOS),
        unsafe_allow_html=True,
    )
    planas = pack.variaveis_planas()
    escolhidas = st.multiselect(
        "Variáveis",
        sorted(planas, key=lambda v: planas[v]),
        default=list(pack.VARIAVEIS_DESTAQUE),
        format_func=lambda v: planas[v],
        label_visibility="collapsed",
        placeholder="Escolha as variáveis a exibir",
    )

    if not escolhidas:
        st.caption(
            "Nenhuma variável escolhida. Use o campo acima para trazer as que "
            "interessam."
        )
    else:
        for inicio in range(0, len(escolhidas), TOPICOS_POR_LINHA):
            linha = escolhidas[inicio : inicio + TOPICOS_POR_LINHA]
            # A altura sai do dado do **DF inteiro**, com ou sem região. Calculada
            # sobre o dado da região, a grade encolhia 330px ao entrar numa região
            # (os gráficos "só existe para o DF inteiro" ficam baixos) e crescia de
            # volta ao sair: a página inteira abaixo da grade se mexia.
            altura = max(
                grafico_componente.altura_composicao(len(_composicao(nav.ano, v, None)))
                for v in linha
            )
            altura = max(altura, ALTURA_MINIMA_TOPICO)

            colunas = st.columns(TOPICOS_POR_LINHA, gap="medium")
            for coluna, variavel in zip(colunas, linha, strict=False):
                with coluna:
                    _desenhar_topico(variavel, planas[variavel], altura)


# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------

st.caption(
    f"Fonte: SINAN/Ministério da Saúde; população do IPEDF (a do Boletim da SES-DF). Recorte por município de "
    f"residência (Brasília). Série exibida: {min(_anos(geo))}–{max(_anos(geo))}. "
    f"Dados preliminares, sujeitos a alteração — o SINAN é atualizado "
    f"retroativamente.  \n"
    f"Fonte dos números desta tela: {painel.fonte(geo)}, no DF e nas "
    f"regiões. Só as variáveis dos tópicos que ela não traz (ocupação, "
    f"resistência...) vêm de `silver.tuberculose`, e só no DF inteiro."
)
