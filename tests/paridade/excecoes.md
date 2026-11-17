# Divergências entre as duas fontes do SINAN-TB do DF

Este painel lê o SINAN-TB do Distrito Federal de **duas tabelas diferentes**
do banco `cenarios_ai`, e as duas não devem bater exatamente:

| | `silver.tuberculose` | `dados_geolink."DF_geo_TB"` |
|---|---|---|
| Usada por | KPIs de topo (`src/data/microdado.py`, `kpis.py`) | Mapa e painel de detalhe (`src/data/microdado_ra.py`) |
| Geografia | Só município (DF inteiro) | Região Administrativa por caso |
| Filtro | `estado_residencia`/`municipio_residencia` | `ID_MN_RESI` (ver §1) |

**Toda diferença numérica entre as duas precisa estar registrada aqui, com
medição — o que não estiver listado e divergir é bug.** Mesmo critério do
`tests/paridade/excecoes.md` do RecifeTB: "paridade mede concordância, não
correção" — nenhuma das duas é automaticamente a certa, e onde divergirem a
fonte que decide é o Boletim Epidemiológico da SES-DF, não uma preferência
entre os dois pipelines.

---

## 1. Notificação × residência — bug encontrado e corrigido

`dados_geolink."DF_geo_TB"` é filtrada por **notificação** no DF
(`SG_UF_NOT = 53` em 100% das 7.551 linhas originais), não por residência.
1.191 linhas (15,8%) eram de gente **notificada no DF, residente em outro
município** — 186 municípios diferentes, espalhados pelo Brasil. É esperado
numa capital com rede de saúde terciária: gente de fora vem se tratar aqui.

`silver.tuberculose`, a fonte dos KPIs de topo, filtra por
`estado_residencia`/`municipio_residencia` — ou seja, as duas tabelas
respondiam perguntas diferentes ("quem foi notificado aqui" contra "quem
mora aqui"), e a extração original (`extrair_sinan_df_geolink.py`, primeira
versão) não filtrava por residência. Isso inflava o volume do mapa em ~17%
sobre o esperado, e foi descoberto ao tentar registrar a divergência aqui:

| Ano | `silver` (residência, deduplicado) | `geolink`, sem filtro | `geolink`, com `ID_MN_RESI=530010` |
|---:|---:|---:|---:|
| 2023 | 507 | 621 | 568 |
| 2024 | 569 | 668 | 610 |

**Corrigido em 11/set/2026**: `extrair_sinan_df_geolink.py` agora filtra
`WHERE "ID_MN_RESI" = 530010` (o código de Brasília, `config.MUN_DF`), antes
da deduplicação por `NU_NOTIFIC`. O total caiu de 7.551 para 6.360 linhas
(6.325 após dedup). A tabela abaixo (§2) é medida **depois** dessa correção
— o que resta já é o residual de duas extrações diferentes, não o filtro
errado.

Fechado por: correção de código. Não depende de resposta de ninguém.

---

## 2. Volume ainda diverge, ano a ano — em aberto

Mesmo com as duas fontes filtradas por residência no DF, o total anual não
bate. Medido em 08/out/2026 (a medição de 11/set/2026 está no §8), **lendo pelo
mesmo caminho que o app usa**
(`microdado.total()`/`microdado_ra.total()`, já deduplicados — não a
contagem crua do banco, que fica de 1 a 2 notificações acima em alguns anos
por conta do `sk_sinan_tube` repetido):

| Ano | `silver.tuberculose` | `dados_geolink` (residência) | Diferença | Diferença (%) |
|---:|---:|---:|---:|---:|
| 2010 | 302 | 278 | −24 | −7,9% |
| 2011 | 337 | 316 | −21 | −6,2% |
| 2012 | 405 | 442 | +37 | +9,1% |
| 2013 | 342 | 359 | +17 | +5,0% |
| 2014 | 426 | 447 | +21 | +4,9% |
| 2015 | 374 | 410 | +36 | +9,6% |
| 2016 | 371 | 412 | +41 | +11,1% |
| 2017 | 339 | 366 | +27 | +8,0% |
| 2018 | 410 | 427 | +17 | +4,1% |
| 2019 | 408 | 451 | +43 | +10,5% |
| 2020 | 355 | 412 | +57 | +16,1% |
| 2021 | 337 | 394 | +57 | +16,9% |
| 2022 | 372 | 433 | +61 | +16,4% |
| 2023 | 486 | 568 | +82 | +16,9% |
| 2024 | 550 | 610 | +60 | +10,9% |

Congelado em `referencia.json`, e conferido a cada execução por
`test_referencia.py`.

**Padrão observado, não explicado:** 2010 e 2011 são os únicos anos em que
`dados_geolink` fica **abaixo** de `silver`; de 2012 em diante ele fica
sistematicamente acima, com a diferença crescendo até 2020-2023. Não há
teste de causa fechado ainda — hipóteses não descartadas:

- As duas tabelas podem ter pipelines de ingestão diferentes, com
  cobertura de completude diferente por ano (`silver` é uma camada tratada
  à parte, `dados_geolink` é geolinkado a partir de outra extração).
- A chave de deduplicação é diferente em espécie: `silver` dedupa por
  `sk_sinan_tube` (chave própria daquela tabela), `dados_geolink` por
  `NU_NOTIFIC` (chave do SINAN bruto) — não é garantido que as duas
  concordem sobre quais linhas são "a mesma notificação".
- Pode haver critério de retificação/retransmissão que uma capta e a outra
  não, mudando o ano de referência de uma fração dos casos.

**Consequência na tela:** o card "Casos" do topo e a soma do mapa por RA
nunca vão bater exatamente para o mesmo ano — e não devem ser comparados
como se fossem a mesma contagem. Isso já está escrito nos dois módulos
(`microdado.py`, `microdado_ra.py`) e no `README.md`.

Em aberto. Não bloqueia o painel — nenhum dos dois números está errado
por si, e o Boletim da SES-DF (quando cruzado) é quem resolve qual, se
algum, dos dois bate com a contagem oficial.

---

## 3. Sem RA identificada — efeito colateral do filtro do §1

Antes da correção do §1, 1.289 das 7.551 linhas (17%) apareciam como
`ra_chave='IGNORADO'`. Depois do filtro por residência, caiu para **104 de
6.325** (1,6%) — a maior parte das linhas sem RA eram justamente as pessoas
não residentes no DF, cuja RA de fato não existe (elas moram em outro
município). O resíduo de 104 é gente residente no DF sem RA preenchida na
notificação — não investigado a fundo, volume pequeno demais para valer a
pena agora.

## 4. RIACHO FUNDO e SCIA sem Região de Saúde — fechado

`Regiao_sau1` vem como `'Ignorado'` para **100%** das notificações dessas
duas RA (99 de SCIA, 104 de RIACHO FUNDO, conferido linha a linha em
11/set/2026) — não é ruído, é lacuna sistemática de `dados_geolink."DF_geo_TB"`
para as duas. As outras 31 RA têm associação 1:1 com uma Região de Saúde.

**Fechado em 14/set/2026** contra duas fontes oficiais da SES-DF:

- [Região Centro-Sul](https://www.saude.df.gov.br/regiao-centro-sul) —
  "Candangolândia, Cidade Estrutural, Guará, Park Way, Núcleo Bandeirante,
  Riacho Fundo I, Riacho Fundo II, Setor de Indústria e Abastecimento (SIA)
  e Setor Complementar de Indústria e Abastecimento (SCIA)".
- Decreto 37.515/2016, art. 3º — mesma composição da Região Centro-Sul.

As duas entram em **Região Centro-Sul** — o que já era esperado: todos os
outros vizinhos da mesma região (Candangolândia, Guará, Núcleo Bandeirante,
Park Way, Riacho Fundo II, SIA) já saíam Centro-Sul no dado medido, e as
duas faltantes completam o mesmo grupo, não abrem um novo.

`config.RA_PARA_REGIAO_SAUDE` atualizado; `scripts/extrair_sinan_df_geolink.py`
e `scripts/preparar_geometria.py` reexecutados. As 33 RA de então (hoje 35, §9) tinham Região
de Saúde — nenhuma fica de fora do dissolve.

## 5. Incidência por RA — aproximação declarada, não medida

**Não existe população por RA ano a ano.** A única fonte de população por
RA é o Censo 2022 (`v0001` dos setores censitários, somado por RA — §9; um
retrato de um ano só); a população **anual** só existe para o DF inteiro (`pop_ibge`,
via `microdado.populacao_ano`).

`microdado_ra.populacao_ra()` estima a população de cada RA num ano
qualquer como a proporção da RA no Censo 2022 aplicada à população anual
do DF:

    populacao_RA(ano) = populacao_DF(ano) × (populacao_censo2022(RA) / 2.817.381)

Conferido em 14/set/2026 (com 33 RA; refeito em 08/out/2026 com 35, §9): as RA somadas reproduzem
`microdado.populacao_ano(ano)` **exatamente**, para qualquer ano — a
proporção fecha por construção. O que a conta **não** captura é a
mudança de distribuição espacial da população dentro do DF entre 2010 e
2024 — RA de expansão urbana recente (Águas Claras, Sol Nascente/Pôr do
Sol) provavelmente cresceram mais que a média do DF nesse período, e RA
mais antigas menos. A incidência por RA em anos distantes de 2022 carrega
esse viés, na direção de subestimar a incidência das RA que mais
cresceram e sobrestimar a das que mais estagnaram.

**Não fica em aberto por falta de solução — fica documentado por ser a
única solução disponível.** A alternativa seria não oferecer incidência
por RA; a decisão foi oferecer com o aviso explícito na tela (`app.py`,
card do mapa) e aqui, em vez de esconder a aproximação atrás de um número
que parece medido.

## 6. Zero casos ≠ sem dado — bug encontrado na conferência da tela, corrigido

**Achado ao vivo em 14/set/2026: Park Way aparecia sem cor no mapa.**
`microdado_ra.valores()` fazia `GROUP BY` só sobre as linhas que existiam
no ano — uma RA com **zero** notificações simplesmente não gerava linha
na saída, e o mapa pintava essa ausência como "sem dado" (cinza), a
mesma cor que uma RA sem população estimada teria. As duas coisas não são
a mesma afirmação: "não sei" contra "sei, e é zero".

Conferido: Park Way (RA pequena, ~23 mil hab.) teve 4 casos em 2020, 1 em
2021, 2 em 2022, 2 em 2023 e **zero em 2024** — plausível para o volume
dela, não um erro de extração.

**Corrigido**: `valores()` agora completa contra a lista cheia de
RA/Região de Saúde (a mesma que a geometria carrega), preenchendo
`casos`/`encerramentos`/`cura_n`/`abandono_n` com 0 onde não havia linha.
`incid` sai `0.0` (valor real, colorido no tom mais claro da escala);
`cura_pct`/`abandono_pct` continuam nulos — não existe taxa de cura sobre
zero encerramentos, e isso é "sem dado" de verdade, não uma contagem
zerada.

## 7. Cura/abandono "sem dado" em RA pequenas — auditado, não é bug

**Notado na conferência da tela em 14/set/2026**: Fercal, Park Way e SCIA
apareciam sem cura/abandono. Auditoria completa antes de responder —
todos os anos (2010–2024), os dois recortes (RA e Região de Saúde),
conferindo `encerramentos ≤ casos`, `cura_n + abandono_n ≤ encerramentos`,
percentual dentro de `[0, 100]`, incidência não negativa e nunca nula
quando há casos e população. **Zero inconsistências.**

Caso a caso:

- **SCIA não tinha bug** — tem cura/abandono em quase todos os anos
  (26,7%/46,7% em 2024). Só ficou sem taxa em 2010 e 2011, quando teve
  menos de 5 encerramentos.
- **Fercal e Park Way** ficam sem taxa em praticamente **todo ano**,
  2010–2024 — não é falha, é porque nunca chegam a 5 encerramentos
  (`microdado_ra.MINIMO_PARA_PERCENTUAL`), a mesma regra do RecifeTB e do
  manaustb: proporção sobre poucos casos não é achado, é ruído.

Em 14/set/2026, 8 das 33 RA ficam sem cura/abandono nesse critério —
número real, não bug, mas silencioso o bastante para parecer painel
incompleto. Adicionada legenda explícita no mapa (`app.py`, quando a
métrica é Cura/Abandono) e `ajuda` no card de detalhe, contando quantas
RA/Regiões ficam de fora e por quê — a mesma decisão de transparência do
§5 (incidência aproximada): não escondido, explicado.

Em 08/out/2026, com as 35 RA, **9 das 35** ficam sem cura em 2024 pelo mesmo
critério — as duas novas entram nessa conta porque são pequenas (Água Quente
teve 1 caso em 2024).

---

## 8. `silver.tuberculose` foi recarregada em 06/out/2026 — referência atualizada

**Os 30 testes de paridade do `silver` ficaram vermelhos em 08/out/2026**, ao
refazer as extrações pela primeira vez desde 11/set. O código de extração **não
mudou** (`extrair_sinan_df.py`, o mesmo filtro `municipio_residencia =
'Brasília'`, a mesma deduplicação por `sk_sinan_tube`). O que mudou foi a
tabela de origem:

- `pg_stat_user_tables` de `silver.tuberculose`: `last_autovacuum` em
  06/out/2026 16:21 e `last_analyze` em 19:31 — um recarregamento em lote,
  **depois** do congelamento de 11/set. A tabela tem ~2,2 milhões de linhas.
- O `silver` passou a dar de **7 a 30 casos a menos por ano, em todos os anos**,
  inclusive 2010 (325 → 302) e 2024 (569 → 550) — padrão sistemático, não de
  atualização retroativa (que mexeria nos anos recentes, não em 2010).
- Nenhuma variação de filtro reproduz o número antigo: sem deduplicar, o
  resultado é o mesmo (não há `sk_sinan_tube` repetido entre residentes do DF), e
  filtros mais frouxos passam do congelado. **Não é problema de código nosso.**
- O `dados_geolink` ficou **idêntico nos 15 anos** — o que também confirma que a
  extração dele não mudou.

| Ano | `silver` em 11/set | `silver` em 08/out | Diferença |
|---:|---:|---:|---:|
| 2010 | 325 | 302 | −23 |
| 2011 | 358 | 337 | −21 |
| 2012 | 435 | 405 | −30 |
| 2013 | 362 | 342 | −20 |
| 2014 | 435 | 426 | −9 |
| 2015 | 393 | 374 | −19 |
| 2016 | 382 | 371 | −11 |
| 2017 | 351 | 339 | −12 |
| 2018 | 417 | 410 | −7 |
| 2019 | 419 | 408 | −11 |
| 2020 | 376 | 355 | −21 |
| 2021 | 354 | 337 | −17 |
| 2022 | 397 | 372 | −25 |
| 2023 | 507 | 486 | −21 |
| 2024 | 569 | 550 | −19 |

`referencia.json` foi **atualizado** (decidido em 08/out/2026) e guarda
os valores de 11/set em `_sobre.historico`. **Em aberto, e não é nosso:** não
sabemos *por que* a recarga tirou casos. Quem mantém `silver.tuberculose` deve
saber dizer se a nova carga é a correta (por exemplo, uma deduplicação ou uma
reclassificação de residência que passou a valer) — uma queda de ~5% em todos os
anos merece essa conversa. A diferença `geolink − silver` do §2 cresceu por
causa disso, não por mudança no geolink.

---

## 9. 35 Regiões Administrativas — critério de atribuição por coordenada

Desde 08/out/2026 o painel tem **35 RAs**, não 33. **Arapoanga** (RA-XXXIV, saiu
de Planaltina) e **Água Quente** (RA-XXXV, saiu de Recanto das Emas) foram
criadas por leis publicadas no DODF em 22/12/2022. A malha é a camada oficial
"Regiões Administrativas do Distrito Federal em 2026" do IPEDF (domínio
público).

**O dado de casos não as traz.** `Regiao_adm` em `dados_geolink."DF_geo_TB"` só
tem as 33 de antes (mais "IGNORADO"): quem mora em Arapoanga vem rotulado
"PLANALTINA". Um mapa de 35 RAs sozinho deixaria as duas novas vazias. A saída
foi usar `LATITUDE`/`LONGITUDE` — **só em memória, descartadas na mesma função**
(`atribuir_ra`, em `extrair_sinan_df_geolink.py`); nunca entram no parquet, e
`test_atribuicao_ra.py` confere isso.

**A regra é conservadora, e foi escolhida depois de medir a coordenada**
(decidido em 08/out/2026). O rótulo vale, **exceto** quando (1) o
rótulo é a RA-mãe, (2) a coordenada cai no polígono da RA nova e (3) o ponto é
preciso (não repetido `config.PONTO_REPETIDO_MINIMO` = 5 vezes ou mais).

O que a medição mostrou (6.360 casos residentes, antes da deduplicação):

- 100% têm coordenada e 100% caem dentro de alguma RA; **91,7% concordam com o
  rótulo antigo**.
- **A geocodificação tem muitos pontos genéricos:** o ponto mais repetido tem 278
  casos; 40 pontos concentram 1.769 casos (28%). Um ponto genérico não localiza
  o caso.
- Os casos que a coordenada põe em **Arapoanga** (119) e **Água Quente** (5) são
  pontos **precisos** — 107 e 5 pontos distintos, no máximo 4 casos por ponto,
  nenhum em ponto repetido. Por isso a regra os move com segurança. Após a
  deduplicação: **114 casos para Arapoanga e 5 para Água Quente**, 0 barrados.
- As duas RAs novas tiraram a Região de Saúde das mães, medida no dado: 115 de
  115 casos de Arapoanga têm `Regiao_sau1 = Regiao Norte`; 5 de 5 de Água
  Quente, `Regiao Sudoeste`. **Confirmar contra o decreto da SES-DF**, como foi
  feito para Riacho Fundo e SCIA (§3).

**O que ficou de fora, de propósito:**

- **Os 104 casos "IGNORADO" não são recuperados por coordenada.** Todos têm
  coordenada e todos cairiam numa RA, mas 64 estão num **único ponto genérico**,
  no Plano Piloto — a coordenada não diz a RA deles. Continuam "IGNORADO"
  (e fora do mapa, §3).
- **As ~400 outras discordâncias entre rótulo e coordenada não são movidas.** A
  maior: **168 casos rotulados "Santa Maria" com ponto em Samambaia** (em 150
  pontos distintos, ou seja, não é ponto genérico; Santa Maria e Samambaia nem
  são vizinhas). Não sabemos qual dos dois está errado — rótulo ou
  geocodificação —, e mover caso por coordenada fora do desmembramento conhecido
  seria trocar um erro possível por outro. **Em aberto e vale uma conversa com
  quem mantém o `DF_geo_TB`.**

**Efeito nos totais:** nenhum. A reatribuição só **move** casos entre RAs — o
total do geolink é o mesmo em todos os anos (conferido contra `referencia.json`).
Planaltina e Recanto das Emas perderam exatamente os casos que as novas ganharam.

**População por RA — mudou de método, e fecha igual.** A malha do IBGE não tem
as duas RAs novas (usa subdistritos do Censo 2022, 33). Agora a população
(`populacao_censo2022`) é a do Censo 2022 **somada por setor censitário** (5.418
setores do DF, `v0001`), cada setor na RA que contém o seu ponto representativo:

- A soma dá **2.817.381**, a população oficial do DF no Censo 2022, e o script
  para se não for.
- Nenhum setor precisou do critério "RA mais próxima": todos os pontos caíram
  dentro de alguma RA.
- As **31 RAs que não foram desmembradas não mudaram nem 1 habitante** em
  relação à malha antiga — o que confirma que as duas malhas coincidem fora do
  desmembramento.
- Arapoanga ficou com **46.170** (saíram de Planaltina: 179.989 → 133.819) e Água
  Quente com **10.717** (saíram de Recanto das Emas: 115.550 → 104.833).

**Ressalva sobre Água Quente:** a imprensa noticiou ~30 mil habitantes para a
área; o Censo por setor dentro do polígono oficial do IPEDF (9,5 km²) dá 10,7
mil. A diferença pode ser o polígono (a notícia pode se referir a uma área maior
que a que virou a RA) ou a data (2022 contra estimativas). **Não é medida; é a
conta do Censo sobre o polígono oficial.** A incidência dela é a mais frágil do
painel (5 casos no histórico inteiro, 1 em 2024).

**Aproximação por ponto:** um setor que atravessa a divisa de duas RAs entra
inteiro em uma. Para RA grande é ruído; para as pequenas, o erro relativo pesa
mais — é o mesmo tipo de aproximação do §5, agora também na população.

---

## 10. O painel passa a falar a língua do Boletim da SES-DF — 13/out/2026

O Boletim "Panorama epidemiológico da tuberculose no Distrito Federal, 2021 a 2025"
(Gevist/Divep/SVS/SES-DF, mar/2026) é, desde o §2, a referência que decide onde as
duas fontes divergirem. Lido inteiro e cruzado com o painel, mudou isto:

**Casos novos, não notificações.** Os cards, o mapa e todos os gráficos contavam
toda notificação do ano (550 em 2024 pela `silver`, 610 pela `geolink`); o Boletim
conta **casos novos** — tipo de entrada "caso novo", "não sabe" ou "pós-óbito", sem
recidiva, reingresso após abandono e transferência, e sem os encerrados como
"mudança de diagnóstico" (`config.SQL_CASO_NOVO`). Com a regra, 437 (`silver`) e 470
(`geolink`) em 2024, contra **475** no Boletim. Os totais congelados em
`referencia.json` agora são de casos novos; as notificações brutas ficam em
`silver_notificacoes`/`geolink_notificacoes`.

**A `geolink` deixava o tipo de entrada em branco em 137 das 610 notificações de
2024** — o dicionário do SINAN só traz três dos seis códigos —, e era exatamente a
recidiva, o reingresso e a transferência. Corrigido em `extrair_sinan_df_geolink.py`
(`TIPO_ENTRADA`, domínio oficial da ficha), que também passou a trazer o TRM
(`TEST_MOLEC`) e os contatos (`NU_CONTATO`, `NU_COMU_EX`). A atribuição de RA ficou
idêntica à implantada (diferença 0 em 6.325 linhas × ano).

**Cura e abandono na coorte do Boletim:** casos novos **pulmonares com confirmação
laboratorial** (baciloscopia ou cultura positivas, ou TRM-TB detectável), com os
ainda sem encerramento no denominador (a coluna "Ign/Branco" da Tabela 5). Abandono
2024 no DF: 16,4% pelo painel, 16,9% no Boletim. A cura do painel dá 53,4% contra
49,7%: o painel tem dados mais frescos (extração de outubro; a do Boletim, de
4/2/2026), com mais encerramentos fechados — hipótese, não medida. **Coinfecção
TB-HIV** é positivos sobre **todos** os casos novos (Tabela 6), e não sobre os
testados.

**População do Boletim (IPEDF) no lugar da do IBGE.** O painel mostrava incidência
de 19,08 em 2024; o Boletim, 14,8. A diferença não era só do numerador: o IBGE
(`pop_ibge`) dá 2,98 milhões em 2024, e as projeções do IPEDF, ~3,21 milhões.
`config.POPULACAO_IPEDF_DERIVADA` deriva a população de **casos ÷ coeficiente** da
Tabela 3 do Boletim (erro de até 0,4%, do arredondamento do coeficiente); antes de
2021, a série do IBGE é reescalada para continuá-la, sem degrau. **Trocar pela
tabela do IPEDF quando houver** — é só esse dicionário.

**Aderência medida (2021–2024):** pulmonares com confirmação laboratorial, 182 → 181
(2021) e 296 → 293 (2024) pela `geolink`; 182 e 296 exatos pela `silver` na
definição do Caderno de Indicadores. TRM em 2021: 57,4% contra 57,3%. Contatos
examinados em 2021: 51,8% contra 52,1%. A `silver`, recarregada em 06/out (§8), fica
6–8% abaixo do Boletim em casos novos; a `geolink` fica a ≤ 2%. **Quem abre a
decisão:** passar os cards do DF inteiro também para a `geolink` acabaria com as duas
fontes na tela — não foi feito.

**O que o Boletim traz e o painel ainda não pode:**

- **2025.** O Boletim vai a 2025; a `dados_geolink."DF_geo_TB"` termina em 2024
  (medido: 611 notificações em 2024, nenhuma em 2025).
- **Mortalidade.** O Boletim dá 3,7/100 mil em 2024 e 2,1 em 2023; o SIM extraído
  (CID A15–A19, residentes) dá 40 e 22 óbitos, ou 1,2 e 0,7. A razão é de ~3 nos dois
  anos. Não investigado: ou o Boletim usa outro corte de causa, ou a extração
  `extrair_obitos_tb_df.py` perde óbitos. **Em aberto, e a pergunta é para a
  Gevist.**
- **Incidência na população privada de liberdade** (Gráfico 10): falta o
  denominador (estimativas da Secretaria Nacional de Políticas Penais).
- **Água Quente.** A Tabela 1 do Boletim lista 34 RAs, sem ela; o painel tem 35.

**Erros do próprio Boletim — não copiar:**

- Tabela 1: o coeficiente de 2022 repete o de 2021 em várias linhas com número de
  casos diferente — Oeste (33 e 43 casos, 6,4 nos dois), Sul (19 e 22, 6,8), Sudoeste
  e Ceilândia, entre outras. Parece coeficiente copiado de um ano para o outro.
- Tabela 3: o título diz "2015 a 2024"; as colunas são 2021 a 2025.
- Anexo I: o texto e a Tabela 2 trazem percentuais diferentes (tabagismo 88,0 e 87,7;
  drogas ilícitas 86,8 e 86,4; alcoolismo 86,3 e 86); o título da Tabela 3 repete o da
  Tabela 1; contatos consistentes saem 98,4% no texto e 98,3% na tabela.
- Texto de populações vulneráveis cita "Região Centro"; a região é a Central.
- Capa de março/2026, anexo de junho/2026, arquivo datado de 16/07.

---

## 11. O DF inteiro passa a ler a fonte por região — 13/out/2026

Decidido pelo §10: a fonte por região fica a ≤ 2% do Boletim em casos novos (321, 337,
444 e 470 contra 314, 332, 424 e 475, em 2021–2024) e a `silver` de 6 a 8% abaixo
(294, 307, 406, 437). Os cards, a série, a pirâmide, o canal e a epicurva do DF
inteiro agora leem `microdado_ra` com `chave=None` (sem filtro de região); o total do
DF fecha com a soma das RA mais os casos sem RA identificada (13 em 2024).

Consequências:

- **O §2 deixa de aparecer na tela**: o card e o mapa não divergem mais. A medição
  continua em `referencia.json` e nos testes, como registro de qual extração é qual.
- **A série do DF começa em 2010**, não em 2001: a fonte por região não tem antes.
- **A mortalidade segue só no DF inteiro** (SIM, sem região), sobre a população do
  Boletim.
- **Variáveis só da `silver`** (ocupação, resistência, localização extrapulmonar...)
  seguem vindo dela no DF inteiro e somem por região, como antes. É a única exceção.
