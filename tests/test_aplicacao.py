"""Executa a aplicação inteira com o ``AppTest`` do Streamlit.

Mesma razão de existir do teste homônimo no RecifeTB e no manaustb:
`resiliencia.painel` contém a falha de um painel no próprio painel, então
"não lançou exceção" não basta — é preciso conferir também a **ausência de
aviso**, que é o que apareceria no lugar de um gráfico quebrado.

**Mais largo que o do manaustb**, porque este `app.py` ganhou o mapa por
RA/Região de Saúde e o painel de detalhe por clique — o que manaustb nunca
teve (o mapa de lá é SVG estático, sem widget).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

from src.data import config

ANO = config.ANO_MAX_DF
TEMPO_LIMITE = 60
APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(scope="module")
def app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()


def test_sobe_sem_excecao(app: AppTest) -> None:
    assert not app.exception, [e.value for e in app.exception]


def test_nenhum_painel_caiu(app: AppTest) -> None:
    assert not app.warning, [w.value for w in app.warning]
    assert not app.error, [e.value for e in app.error]


def test_nao_ha_mais_grafico_altair(app: AppTest) -> None:
    """Os gráficos são do componente ECharts (`src/grafico_componente.py`).

    O `AppTest` não enxerga o conteúdo de um componente externo: contar
    gráficos ali não é possível, e o desenho de cada um é coberto por
    `tests/test_grafico_componente.py`. O que dá para cobrar daqui é que
    nenhum `st.altair_chart` voltou — o painel inteiro seria misto de novo.
    """
    assert not app.get("vega_lite_chart")


def test_horizonte_comeca_em_meses_do_ano(app: AppTest) -> None:
    """Canal endêmico por padrão, mesmo critério do RecifeTB. Único
    `st.radio` da página agora — recorte e métrica do mapa viraram
    `segmented_control`, como no RecifeTB."""
    assert app.radio[0].value == "Meses do ano"


def test_trocar_para_todos_os_anos_nao_quebra() -> None:
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()
    at.radio[0].set_value("Todos os anos").run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]
    texto = " ".join(m.value for m in at.markdown)
    assert "Casos novos por ano" in texto


def test_kpi_de_casos_aparece(app: AppTest) -> None:
    from src.data import microdado_ra
    from src.theme import componentes as ui

    esperado = ui.formatar_inteiro(microdado_ra.total(ANO))
    texto = " ".join(m.value for m in app.markdown)
    assert "Casos" in texto
    assert esperado in texto


def test_trilha_mostra_distrito_federal_e_o_ano(app: AppTest) -> None:
    texto = " ".join(m.value for m in app.markdown)
    assert "Distrito Federal" in texto
    assert f"Ano: {ANO}" in texto


def test_seletor_de_ano_nao_ultrapassa_o_teto() -> None:
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()
    anos = [int(a) for a in at.selectbox[0].options]
    assert max(anos) == ANO
    assert 2025 not in anos


def test_trocar_o_ano_muda_os_numeros() -> None:
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()
    antes = " ".join(m.value for m in at.markdown)

    at.selectbox[0].select(ANO - 1).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]
    assert " ".join(m.value for m in at.markdown) != antes


def test_topicos_abrem_com_o_conjunto_padrao(app: AppTest) -> None:
    from src.doencas import tuberculose as pack

    escolhidas = app.multiselect[0].value
    assert list(escolhidas) == list(pack.VARIAVEIS_DESTAQUE)
    assert len(pack.variaveis_planas()) > len(pack.VARIAVEIS_DESTAQUE)


def test_sem_topico_escolhido_a_pagina_continua_de_pe() -> None:
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()
    at.multiselect[0].set_value([]).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]
    texto = " ".join(c.value for c in at.caption)
    assert "Nenhuma variável escolhida" in texto


# ---------------------------------------------------------------------------
# Mapa por RA/Região de Saúde — novo neste painel
# ---------------------------------------------------------------------------


def test_recorte_comeca_em_ra(app: AppTest) -> None:
    """`segmented_control`, não `radio` — mesmo widget do RecifeTB para
    Métrica/Nível do mapa, agora que os dois vivem no card de controles."""
    assert app.segmented_control[1].label == "Nível do mapa"
    assert app.segmented_control[1].value == "RA"


def test_metrica_do_mapa_comeca_em_casos(app: AppTest) -> None:
    from src.doencas import tuberculose as pack

    assert app.segmented_control[0].label == "Métrica do mapa"
    assert app.segmented_control[0].value == pack.METRICAS_MAPA[0] == "casos"


def test_trocar_para_regiao_de_saude_nao_quebra() -> None:
    """Desde 14/set/2026 toda RA (hoje 35) tem Região de Saúde (RIACHO FUNDO e SCIA
    preenchidas contra fonte oficial — ver excecoes.md, §4), então não há
    mais aviso de geografia faltante a conferir aqui além do de sempre.

    Regressão do bug achado ao escrever este teste: no nível Região de
    Saúde, chave e nome de exibição são a mesma coluna (`regiao_saude`), e
    o merge do ranking colapsava as duas em "nome" só, sem sobrar "chave"
    — corrigido em `app.py`."""
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()
    at.segmented_control[1].set_value("Região de Saúde").run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]


def test_trocar_metrica_do_mapa_nao_quebra() -> None:
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()
    at.segmented_control[0].set_value("Incidência").run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]


def test_cura_avisa_quantas_ra_ficam_sem_taxa() -> None:
    """Achado na conferência da tela em 14/set/2026: Fercal, Park Way e outras RA
    pequenas ficam sem cura/abandono todo ano — não é bug, é
    `MINIMO_PARA_PERCENTUAL` (proporção sobre poucos encerramentos não é
    confiável). Sem aviso, "sem dado" branco parece painel quebrado; a
    legenda abaixo do mapa agora explica o porquê."""
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()
    at.segmented_control[0].set_value("Cura").run()
    assert not at.exception, [e.value for e in at.exception]
    texto = " ".join(c.value for c in at.caption)
    assert "não mostram esta taxa" in texto
    assert "não é dado faltando" in texto


def test_aba_ranking_existe_e_reage_ao_recorte() -> None:
    """A aba nova — não existe no manaustb, e é o que fecha o paralelo
    visual com o RecifeTB (Evolução / Ranking / Pirâmide, as três abas)."""
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()
    rotulos = [t.label for t in at.tabs]
    assert rotulos[:3] == ["Evolução temporal", "Ranking", "Pirâmide etária"]
    # As seis abas seguintes são as do Boletim da SES-DF.
    assert rotulos[3:] == [
        "Incidência", "Diagnóstico e tratamento", "Perfil", "Desfecho",
        "Coinfecção TB-HIV", "Populações vulneráveis",
    ]

    at.segmented_control[1].set_value("Região de Saúde").run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]


def test_sem_selecao_o_painel_de_detalhe_nao_aparece(app: AppTest) -> None:
    texto = " ".join(m.value for m in app.markdown)
    assert "Região Administrativa:" not in texto
    assert "Região de Saúde:" not in texto


# ---------------------------------------------------------------------------
# O painel inteiro responde à RA selecionada (como no hansepe)
# ---------------------------------------------------------------------------

RA_TESTE = ("RA", "PLANO PILOTO")


def _app_com_ra(geo=RA_TESTE, ano: int | None = None, nivel_do_mapa: str | None = None) -> AppTest:
    """Sobe o app com a região já selecionada — o clique do mapa vem de um
    componente externo que o `AppTest` não enxerga, então a seleção é posta
    direto no estado, que é onde o clique a deixa."""
    from src.estado import Navegacao

    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE)
    at.session_state["detalhe_geo"] = geo
    if nivel_do_mapa is not None:
        # O nível vem do **estado do widget**, e uma seleção de outro nível é
        # descartada de propósito — as chaves de RA não existem na Região de Saúde.
        at.session_state["recorte-mapa"] = nivel_do_mapa
    if ano is not None:
        at.session_state["nav"] = Navegacao(ano=ano)
    return at.run()


def _texto(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_com_ra_selecionada_o_painel_sobe_sem_aviso() -> None:
    at = _app_com_ra()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]
    assert not at.error, [e.value for e in at.error]


def test_com_ra_os_cartoes_mostram_a_regiao_e_nao_o_df() -> None:
    """O subtítulo de cada card diz de onde é o número."""
    texto = _texto(_app_com_ra())
    assert f"Plano Piloto • {ANO}" in texto
    assert f"Distrito Federal • {ANO}" not in texto


def test_com_ra_o_cartao_de_casos_e_o_da_ra_e_nao_o_do_df() -> None:
    from src.data import painel
    from src.theme import componentes as ui

    esperado_ra = ui.formatar_inteiro(painel.kpis(ANO, RA_TESTE).casos)
    esperado_df = ui.formatar_inteiro(painel.kpis(ANO, None).casos)
    assert esperado_ra != esperado_df
    texto = _texto(_app_com_ra())
    assert f">{esperado_ra}<" in texto.replace("\n", "")
    assert f"Distrito Federal • {ANO}" not in texto


def test_a_trilha_do_cabecalho_nomeia_a_regiao() -> None:
    texto = _texto(_app_com_ra())
    assert "Distrito Federal › Plano Piloto" in texto


def test_com_ra_o_aviso_diz_o_que_a_regiao_nao_tem() -> None:
    """A região usa a mesma fonte do DF, então não há mais aviso de "fontes
    diferentes": o aviso diz só o que falta nela — mortalidade e população medida."""
    legendas = " ".join(c.value for c in _app_com_ra().caption)
    assert "mesma fonte do total do DF" in legendas
    assert "mortalidade" in legendas
    assert "não somam" not in legendas


def test_sem_ra_nao_ha_aviso_do_que_a_regiao_nao_tem(app: AppTest) -> None:
    legendas = " ".join(c.value for c in app.caption)
    assert "mesma fonte do total do DF" not in legendas


def test_nao_ha_mais_painel_de_detalhe_embaixo_do_mapa() -> None:
    """A janela abaixo do mapa saiu: a região selecionada molda o painel
    inteiro, e não abre um painel à parte."""
    texto = _texto(_app_com_ra())
    assert "Região Administrativa: Plano Piloto" not in texto


def test_os_titulos_das_secoes_dizem_a_regiao() -> None:
    texto = _texto(_app_com_ra())
    for secao in ("Canal endêmico", "Epicurva por mês", "Tópicos de interesse"):
        assert f"{secao} — Plano Piloto" in texto, secao


def test_a_pilula_devolve_o_painel_inteiro_ao_df() -> None:
    at = _app_com_ra()
    assert [b for b in at.button if b.key == "voltar_df"]
    at.button(key="voltar_df").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["detalhe_geo"] is None
    texto = _texto(at)
    assert f"Distrito Federal • {ANO}" in texto
    assert f"Plano Piloto • {ANO}" not in texto


def test_sem_ra_nao_ha_pilula(app: AppTest) -> None:
    # `AppTest.button(key=...)` levanta `KeyError` se não existe, em vez de
    # devolver vazio — daí varrer a lista.
    assert not [b for b in app.button if b.key == "voltar_df"]


def test_o_seletor_de_busca_acompanha_a_regiao() -> None:
    at = _app_com_ra()
    busca = next(s for s in at.selectbox if s.label.startswith("Buscar"))
    assert busca.value == "PLANO PILOTO"


def test_buscar_uma_ra_molda_o_painel() -> None:
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run()
    busca = next(s for s in at.selectbox if s.label.startswith("Buscar"))
    busca.select("PLANO PILOTO").run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]
    assert at.session_state["detalhe_geo"] == RA_TESTE
    assert f"Plano Piloto • {ANO}" in _texto(at)


def test_por_ra_o_seletor_de_ano_comeca_em_2010() -> None:
    at = _app_com_ra()
    anos = [int(a) for a in at.selectbox[0].options]
    assert min(anos) == 2010 and max(anos) == ANO


def test_ano_anterior_a_2010_cede_ao_entrar_numa_ra() -> None:
    """A fonte por região começa em 2010: selecionar uma RA estando em 2005 leva
    o painel a 2010, em vez de quebrar ou mostrar zeros enganosos."""
    at = _app_com_ra(ano=2005)
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]
    assert at.session_state["nav"].ano == 2010
    assert at.selectbox[0].value == 2010


def test_variaveis_so_do_df_ficam_no_lugar_e_nao_encurtam_a_grade() -> None:
    """Antes elas saíam da grade com uma legenda ("Fora desta grade..."). Isso
    mudava o pareamento das colunas e remontava todos os gráficos que vinham
    depois: a página piscava. Agora o gráfico fica no lugar, com um recado."""
    legendas = " ".join(c.value for c in _app_com_ra().caption)
    assert "Fora desta grade" not in legendas


def test_trocar_o_nivel_do_mapa_limpa_a_regiao() -> None:
    """As chaves de RA não existem no nível de Região de Saúde."""
    at = _app_com_ra()
    at.segmented_control[1].set_value("Região de Saúde").run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["detalhe_geo"] is None
    assert f"Distrito Federal • {ANO}" in _texto(at)


def test_selecionar_uma_regiao_de_saude_tambem_molda_o_painel() -> None:
    from src.data import microdado_ra

    chave = str(microdado_ra.valores(ANO, "REGIAO_SAUDE").sort_values("casos", ascending=False)["chave"].iloc[0])
    at = _app_com_ra(geo=("REGIAO_SAUDE", chave), nivel_do_mapa="Região de Saúde")
    assert not at.exception, [e.value for e in at.exception]
    assert not at.warning, [w.value for w in at.warning]
    assert f"{chave} • {ANO}" in _texto(at)


# ---------------------------------------------------------------------------
# Sem piscadas: estrutura fixa e uma passada por interação
# ---------------------------------------------------------------------------
# O Streamlit identifica cada elemento pela **posição na árvore**. Se entrar ou
# sair um elemento acima de um componente, o componente é destruído e recriado —
# o mapa e 18 gráficos, ao clicar em "Ver o DF inteiro". Estes testes cobram que a
# árvore seja a mesma com e sem região selecionada.


def _forma(no, profundidade: int = 0, limite: int = 3, saida=None, prefixo: str = "") -> list[str]:
    """Tipos dos filhos, recursivamente, sem entrar nos espaços reservados
    (`nota-regiao`, `barra-voltar`), cujo **conteúdo** pode mudar."""
    saida = [] if saida is None else saida
    filhos = getattr(no, "children", None)
    if filhos is None:
        return saida
    for i, filho in filhos.items():
        ident = str(getattr(getattr(filho, "proto", None), "id", "") or "")
        reservado = any(k in ident for k in ("nota-regiao", "barra-voltar"))
        saida.append(f"{prefixo}{i}:{filho.type}{'[reservado]' if reservado else ''}")
        if profundidade < limite and not reservado:
            _forma(filho, profundidade + 1, limite, saida, prefixo + "  ")
    return saida


def test_a_estrutura_da_pagina_e_a_mesma_com_e_sem_regiao(app: AppTest) -> None:
    com_regiao = _forma(_app_com_ra().main)
    sem_regiao = _forma(app.main)
    diferentes = [(i, a, b) for i, (a, b) in enumerate(zip(sem_regiao, com_regiao, strict=False)) if a != b]
    assert len(sem_regiao) == len(com_regiao), "a árvore mudou de tamanho"
    assert not diferentes, (
        "um elemento entrou ou saiu acima dos componentes — o mapa e os gráficos "
        f"seriam recriados (piscada): {diferentes[:4]}"
    )


def test_a_estrutura_tambem_nao_muda_numa_regiao_de_saude() -> None:
    from src.data import microdado_ra

    chave = str(microdado_ra.valores(ANO, "REGIAO_SAUDE").sort_values("casos", ascending=False)["chave"].iloc[0])
    a = _forma(_app_com_ra(geo=("REGIAO_SAUDE", chave), nivel_do_mapa="Região de Saúde").main)
    b = _forma(AppTest.from_file(APP, default_timeout=TEMPO_LIMITE).run().main)
    # o nível do mapa muda a malha, não a árvore da página
    assert len(a) == len(b)


def test_o_script_nunca_chama_st_rerun() -> None:
    """`st.rerun()` no meio do script é uma **segunda passada**: a primeira desenha
    um estado intermediário e o olho vê as duas. Clique e troca de ano usam
    callback, que roda antes do script."""
    fonte = Path(APP).read_text(encoding="utf-8")
    codigo = "\n".join(l for l in fonte.splitlines() if not l.lstrip().startswith("#"))
    assert "st.rerun(" not in codigo


def test_um_clique_no_mapa_seleciona_a_regiao_na_mesma_passada() -> None:
    """O clique volta como valor do componente (`session_state["mapa"]`) e é lido
    no início do script — a região já vale nessa passada, sem `st.rerun()`."""
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE)
    at.session_state["mapa"] = {"nonce": "teste-1", "properties": {"ra_chave": "PLANO PILOTO"}}
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["detalhe_geo"] == RA_TESTE
    assert f"Plano Piloto • {ANO}" in _texto(at)


def test_um_clique_no_ranking_tambem() -> None:
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE)
    at.session_state["ranking"] = {"nonce": "teste-1", "name": "Plano Piloto", "chave": "PLANO PILOTO"}
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["detalhe_geo"] == RA_TESTE


def test_o_mesmo_clique_nao_e_tratado_duas_vezes() -> None:
    """O valor do componente persiste entre passadas. Sem o `nonce`, voltar ao DF
    reselecionaria a região do último clique."""
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE)
    at.session_state["mapa"] = {"nonce": "teste-1", "properties": {"ra_chave": "PLANO PILOTO"}}
    at.run()
    assert at.session_state["detalhe_geo"] == RA_TESTE
    at.button(key="voltar_df").click().run()
    assert at.session_state["detalhe_geo"] is None
    at.run()  # outra passada qualquer, com o mesmo valor ainda no estado do componente
    assert at.session_state["detalhe_geo"] is None


def test_um_clique_novo_depois_do_voltar_funciona() -> None:
    at = AppTest.from_file(APP, default_timeout=TEMPO_LIMITE)
    at.session_state["mapa"] = {"nonce": "teste-1", "properties": {"ra_chave": "PLANO PILOTO"}}
    at.run()
    at.button(key="voltar_df").click().run()
    at.session_state["mapa"] = {"nonce": "teste-2", "properties": {"ra_chave": "GAMA"}}
    at.run()
    assert at.session_state["detalhe_geo"] == ("RA", "GAMA")


def test_trocar_o_ano_e_uma_passada_so_e_a_busca_acompanha_a_regiao() -> None:
    at = _app_com_ra()
    at.selectbox[0].select(ANO - 1).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["nav"].ano == ANO - 1
    assert at.session_state["detalhe_geo"] == RA_TESTE
    busca = next(s for s in at.selectbox if s.label.startswith("Buscar"))
    assert busca.value == "PLANO PILOTO"


def test_voltar_ao_df_leva_a_busca_junto() -> None:
    at = _app_com_ra()
    at.button(key="voltar_df").click().run()
    busca = next(s for s in at.selectbox if s.label.startswith("Buscar"))
    assert busca.value is None
