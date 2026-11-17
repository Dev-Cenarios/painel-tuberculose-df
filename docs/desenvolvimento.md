# Guia de desenvolvimento

Para quem vai mexer no código: comandos, arquitetura e as armadilhas que já
custaram uma investigação. O que o painel mostra e como calcula está no
README e nas outras docs.

Painel de vigilância epidemiológica do SINAN-TB do Distrito Federal, em
Streamlit. Cópia arquitetural do `paineis/manaustb` (core único, doença
como configuração, DuckDB sobre parquet local), com uma diferença central:
**duas fontes do SINAN**, não uma — ver README.md, "Duas fontes do SINAN —
e por quê", antes de tocar em qualquer leitor de dado.

Documentação em português. Código, commits e comentários também.

**O mapa não mora aqui** desde 14/out/2026: `mapa`, `mapa_componente` e
`resiliencia` vêm do **`cenarios-core`** (`../cenarios-core`) 0.5.0, instalado
do wheel em `vendor/` em versão fixa. O que é do DF — altura e largura da
caixa, as duas classificações e a ajuda delas, `QUANTIS = 4`, o quanto o
clique numa RA aproxima, as chaves do clique e as cores de contorno — mora em
`src/theme/mapa.py` e o `app.py` passa ao core. Correção no mapa se faz lá,
solta versão e o wheel é trocado aqui.

## Comandos

```bash
streamlit run app.py                              # aplicação (porta 8515 em dev)
pytest tests/ -v                                  # suíte inteira (~128 testes, ~15-20s)
pytest tests/test_mapa.py -q                       # um módulo
pytest tests/paridade -q                           # só o harness de paridade
pytest -rs                                        # ver o motivo de cada skip

python -m scripts.extrair_sinan_df                # silver.tuberculose (exige VPN)
python -m scripts.extrair_sinan_df_geolink         # dados_geolink."DF_geo_TB" (exige VPN)
python -m scripts.preparar_geometria               # malha das RA/Regiões de Saúde
python -m scripts.preparar_microdado               # reparticiona os 4 parquets por ano
```

Não há linter nem formatter configurados no projeto (`ruff` pode ser
instalado ad-hoc no `.venv` do `sinan` para uma varredura pontual, como foi
feito em 15/set/2026 — não é dependência do projeto).

**Testes sem os dados:** os parquets não são versionados. Sem eles,
`tests/conftest.py` ignora os módulos que dependem de cada fonte — `sinan_df`
(KPIs) e `sinan_df_ra` (mapa) são flags **separadas**, porque um clone pode
ter uma sem ter a outra. O cabeçalho do pytest mostra o estado das duas.

## Arquitetura

**Os números vêm de uma fonte só desde 13/out/2026** (`microdado_ra.py`, no DF
inteiro com `chave=None` e nas regiões); a `silver` só empresta, no DF inteiro, as
variáveis dos tópicos que a outra não tem. Os dois itens abaixo descrevem as duas
fontes como eram — o que cada uma ainda é, mas a fachada já não escolhe entre elas
para os cards.

**Duas fontes, dois módulos — e uma fachada que escolhe entre elas:**

- `src/data/microdado.py` lê `silver.tuberculose` (DF inteiro, sem RA) —
  sustenta os KPIs de topo, canal endêmico, epicurva, pirâmide e composição.
- `src/data/microdado_ra.py` lê `dados_geolink."DF_geo_TB"` (nominal, com
  RA por caso) — sustenta o mapa, o ranking **e, com uma região
  selecionada, o painel inteiro**. **Nunca** soma ou compara com
  `microdado.py`: as duas divergem em volume por serem extrações diferentes
  (ver README).
- `src/data/painel.py` é a **fachada**: `kpis(ano, geo)`, `serie_mensal`,
  `piramide`, `composicao`, `canal`, `epicurva`... com `geo=None` (DF
  inteiro → `microdado.py`) ou `geo=(nível, chave)` (→ `microdado_ra.py`),
  sempre devolvendo a mesma forma de dado. É o **único** lugar onde as duas
  fontes se encontram; `app.py` não escolhe fonte.

**Fluxo:** `app.py` (única página) → `src/estado.py` (`Navegacao`: doença +
ano) e `st.session_state.detalhe_geo` (RA/Região selecionada, vira o
argumento `geo`) → `src/data/painel.py` → os dois módulos de dado →
`cenarios_core.mapa` + `cenarios_core.mapa_componente` e
`src/grafico_componente.py` (visual). O mapa e o ranking leem `microdado_ra.valores()` direto: são
sempre por região, haja seleção ou não.

- **`src/data/escopo.py`** — `Escopo(doenca, ano)` para `microdado.py`;
  `chave_ra()` normaliza nome de RA (sem acento/caixa) — é o que liga
  `dados_geolink` à malha do Censo, as duas grafam RA de jeito diferente.
- **`src/data/config.py`** — âncoras do DF (`MUN_DF`, `ANO_MAX_DF`,
  `ANO_MAX_OBITO_DF`) e `RA_PARA_REGIAO_SAUDE` (as 35 RA mapeadas contra
  fonte oficial da SES-DF).
- **`src/data/canal.py`** — canal endêmico e epicurva. Adaptação do
  RecifeTB: sem população mensal na extração do DF, a taxa mensal usa a
  população **anual** (`pop_ibge`) aplicada a cada mês do ano — não é
  precisão perdida por acidente, é a única fonte que existe.
- **`src/doencas/`** — *disease pack*: só tuberculose. `carregar()` confere
  o `CONTRATO` no carregamento; `app.py` recebe o pack, nunca o importa
  direto.
- **`src/data/boletim.py` + `src/grafico_boletim.py`** — os gráficos do Boletim da
  SES-DF por Região de Saúde (seção "Indicadores do Boletim" do `app.py`). Lê só a
  fonte por região. **`config.SQL_CASO_NOVO` é a definição de caso novo do
  Boletim e passa por `_tabela()` em `microdado.py` e `microdado_ra.py`: toda
  leitura que sustenta um número deve sair dela, nunca do parquet cru** (só a lista
  de anos e a de colunas leem o cru). Definições e distância ao Boletim:
  `tests/paridade/excecoes.md` §10.
- **`cenarios_core.mapa`** (do core) — monta o *spec* do deck.gl (pydeck)
  com quebras naturais/quartis, contornos por feição, destaque com etiqueta e
  foco da câmera na RA selecionada; a ilha é detectada pela geometria e o DF
  não tem nenhuma. O foco usa `FOCO_VIZINHANCA`/`FOCO_MINIMO` do
  `src/theme/mapa.py`: com o padrão do core (o de PE) 13 das 35 RAs não
  aproximavam ao clique. **Quem desenha** é `cenarios_core.mapa_componente`,
  um componente próprio — nunca `st.pydeck_chart`,
  que recria o canvas a cada rerun e mata o voo da câmera. O clique volta
  com um `nonce`; o último tratado fica em `session_state["clique_mapa"]`.
- **`src/grafico_componente.py`** — gráficos em ECharts (cada função devolve
  a *opção*, um dict). O Altair saiu do projeto. Item de dado leva `name` e a
  série leva `id` fixo: é o que faz o ECharts animar a troca de recorte.
- **Depois de editar `grafico.js`**, rode
  `python -m scripts.versionar_js` (o `mapa.js` mora no core, que tem o seu): o `?v=<hash>` no `index.html` é o que faz o
  navegador buscar o arquivo novo, e `test_mapa_componente.py` cobra o carimbo.
- **`cenarios_core.resiliencia`** — `painel()` contém a falha de um painel no
  próprio painel. No Streamlit, exceção no corpo do script troca a página
  inteira pelo traceback.

### Regras que falham em silêncio

Violá-las não dá erro — dá número errado ou coluna faltando.

1. **`microdado_ra.valores()` sempre completa as 35 RA (ou 7 Regiões),
   mesmo com zero casos.** Sem isso, uma RA sem notificação no ano some da
   tabela em vez de aparecer com `casos=0` — e o mapa pinta "sem dado"
   (cinza), a mesma cor de "sem população pra calcular". São afirmações
   diferentes. Achado ao vivo em 14/set/2026 (Park Way); ver
   `excecoes.md` §6 antes de tocar em `valores()`.
2. **`cura_pct`/`abandono_pct` somem sob `MINIMO_PARA_PERCENTUAL=5`
   encerramentos** — de propósito, mesma regra do RecifeTB/manaustb. Não é
   bug se uma RA pequena nunca mostrar essas taxas; é bug se a legenda que
   explica isso desaparecer do `app.py`.
3. **`chave` e o nome de exibição são a mesma coluna no nível
   `REGIAO_SAUDE`** (`regiao_saude`), diferente de `RA` (`ra_chave` x
   `ra_nome`). Selecionar as duas sem `dict.fromkeys` para deduplicar
   colapsa o rename e uma das duas colunas simplesmente não existe depois
   — aconteceu duas vezes neste projeto (`mapa.deck()` e o merge do
   ranking em `app.py`), as duas corrigidas. Qualquer código novo que junte
   `_coluna_chave(nivel)` com `_coluna_nome(nivel)` precisa do mesmo cuidado.
4. **`SITUA_ENCE` não pode ser decodificado pelo `sinan_dict`** (usado em
   `extrair_sinan_df_geolink.py` para as outras colunas clínicas) — o
   `valor_lbl` daquele dicionário reagrupa em Favorável/Desfavorável, não
   nas categorias clínicas (Cura, Abandono...) que `kpis.py` e
   `microdado_ra.py` esperam. Decodificado à parte, com o domínio oficial
   do SINAN escrito no próprio script.
5. **`ID_MN_RESI`, não a ausência de filtro**, é o que faz
   `extrair_sinan_df_geolink.py` representar residentes do DF — a tabela de
   origem é filtrada por notificação, não por residência. Sem o filtro,
   15,8% das linhas são de gente de outro município. Ver excecoes.md §1.
6. **Nunca chame `Escopo`/`Navegacao` com nível de RA.** Elas só carregam
   doença+ano — a RA vive em `st.session_state.detalhe_geo` e entra nos
   dados pelo argumento `geo` da fachada `painel.py` (ver README). E o
   `app.py` **não** importa `microdado.py` para os números do painel:
   passa por `painel.py`, ou o cartão e o gráfico podem sair de fontes
   diferentes na mesma tela.
7. **Capture `Exception`, nunca `BaseException`** em qualquer novo bloco de
   resiliência — `st.rerun()` levanta `RerunException`, que herda de
   `BaseException` para atravessar `except Exception`.

### Dados

Não versionados (`/data/` no `.gitignore`, com barra inicial — sem ela o
padrão casaria com `src/data/`). Esperados em `data/parquet/dashboard/` (dois
subdiretórios: `sinan_df/` e `sinan_df_ra/`, gerados por fontes diferentes) e
`data/geo/` (`ra.parquet`, `regioes_saude.parquet`, `df.parquet`, gerados por
`preparar_geometria.py` a partir da camada de RAs do IPEDF em
`data/origem/malha_ipedf/` e dos setores do Censo 2022 em `data/origem/setores/`).

**35 RAs, e as duas novas (Arapoanga, Água Quente) não vêm no rótulo do banco.**
`extrair_sinan_df_geolink.py` as atribui por coordenada, só para a RA-mãe com ponto
preciso, e descarta a coordenada na mesma função — critério e números em
`tests/paridade/excecoes.md` §9. Ordem das extrações com RA nova: baixar a malha do
IPEDF → `preparar_geometria` → `extrair_sinan_df_geolink` → `preparar_microdado`.

Credenciais do banco em `.env` (fora do git) — copiar de `.env.exemplo`.
`test_segredos.py` varre o repositório por credencial versionada a cada
execução; pula a varredura por `git ls-files` se o repositório ainda não
tiver `.git` (não é o caso deste projeto desde 11/set/2026).
