"""O que o mapa do DFTB tem de próprio: a caixa, as classificações e a casca.

O mapa vem do cenarios-core, que não sabe que está desenhando o DF. O que é
daqui entra por parâmetro e mora neste arquivo desde 14/out/2026, quando o
mapa foi para o core — antes estava em `src/mapa.py`.
"""

from __future__ import annotations

from cenarios_core.mapa import Contornos

#: Altura do mapa, em pixels. O DF é compacto — o bounding box é ~1,6 vez mais
#: largo que alto —, então numa caixa mais alta que isto o mapa vira uma faixa
#: no meio com vazio em cima e embaixo; é a largura do painel que limita o
#: zoom, não a altura.
ALTURA = 400

#: Largura assumida do painel — o Streamlit não informa a largura real ao
#: servidor. O DF é compacto (bounding box de ~0,9° x 0,6°), então o erro de
#: zoom por um palpite de largura errado pesa pouco.
LARGURA = 560

#: Como as cores repartem os valores. Só duas: a TB não tem régua oficial de
#: endemicidade por Região Administrativa, e inventar uma daria autoridade de
#: parâmetro a corte nosso. (O core tem também a escala fixa; o DFTB não a
#: oferece.)
CLASSIFICACOES = ("NATURAL", "QUARTIL")

ROTULO_CLASSIFICACAO = {
    "NATURAL": "Quebras naturais",
    "QUARTIL": "Quartis",
}

AJUDA_CLASSIFICACAO = """Como as cores repartem os valores.

**Quebras naturais** agrupam Regiões parecidas e separam as diferentes — é o padrão, porque poucas RAs concentram a maior parte dos casos e uma escala linear deixaria o resto numa cor só.

**Quartis** põem um quarto das Regiões em cada cor. Fácil de explicar, mas a régua muda a cada ano e a métrica."""

CLASSIFICACAO_PADRAO = "NATURAL"

#: Quartis de verdade: um quarto das RAs em cada cor. O padrão do core são
#: cinco classes (os quintis de PE); vai ao mapa **e** à escala que pinta o
#: ranking, para a barra e a RA terem a mesma cor.
QUANTIS = 4

#: Quanto o clique numa RA aproxima: a vizinhança mostrada (vezes o tamanho da
#: RA) e o piso (fração do DF). O padrão do core é o de PE (5 e 0,28) e, no DF,
#: deixava 13 das 35 RAs sem aproximação nenhuma. Estes reproduzem o foco que o
#: DFTB tinha antes do core — medido nas 35 RAs em 14/out/2026: cada uma fica
#: entre 0,83 e 1,21 vez o zoom de antes, mediana 1,02.
FOCO_VIZINHANCA = 1.4
FOCO_MINIMO = 0.14

#: Chaves das feições, na ordem de precedência: a RA (`ra_chave`) e a Região
#: de Saúde (`regiao_saude`). O padrão do core são as municipais do IBGE.
CAMPOS_CLIQUE = ("ra_chave", "regiao_saude")

# --- Casca ------------------------------------------------------------------

#: Cinza de quem **não** está na faixa clicada na legenda. Baixar a opacidade
#: dos outros falhava justamente para a faixa mais baixa, o tom mais claro da
#: rampa, que não se distinguia do resto — o mapa inteiro ficava claro. Cinza
#: chapado tira a cor dos outros em vez de enfraquecê-la, e sobra uma única
#: matiz na tela: a da faixa escolhida. A malha continua desenhada, que é o
#: que mantém a referência do DF.
CINZA_APAGADO = (226, 228, 233)

#: Contorno de quem está na faixa escolhida. Escuro, para marcar uma RA pequena
#: de cor clara — só com o preenchimento, a faixa mais baixa some.
CONTORNO_REALCADO = (94, 28, 52, 235)

#: Contorno de quem ficou de fora: some no cinza, para não desenhar 30 molduras
#: competindo com as poucas que interessam.
CONTORNO_APAGADO = (205, 208, 214, 180)

#: Contorno de quem **não tem dado**. Escuro e sempre — independente de haver
#: faixa escolhida. O preenchimento sozinho não separa "sem dado" da faixa mais
#: baixa (o cinza #F3F4F6 contra o tom mais claro da rampa confunde em
#: daltonismo), e nenhum outro cinza resolve: qualquer um move o problema de
#: lugar, porque a rampa ocupa o eixo de luminosidade inteiro. O contorno é
#: outro canal — traço escuro contra traço claro, que nenhum tipo de
#: daltonismo apaga. Confundir "sem dado" com "valor baixo" é ler um número que
#: não existe.
CONTORNO_SEM_DADO = (71, 78, 92, 255)

#: Divisa comum: um rosé acinzentado do meio da rampa, que contrasta com os dois
#: extremos dela. Branco só desenhava a RA sobre os tons escuros, e nas classes
#: claras a malha virava uma mancha.
CONTORNO_PADRAO = (140, 98, 110, 205)

#: O que vai ao `mapa.deck(..., contornos=)`, nas espessuras de antes: 0,8 px
#: de divisa e 1,1 px com uma faixa realçada.
CONTORNOS = Contornos(
    padrao=CONTORNO_PADRAO,
    sem_dado=CONTORNO_SEM_DADO,
    realcado=CONTORNO_REALCADO,
    apagado=CONTORNO_APAGADO,
    preenchimento_apagado=CINZA_APAGADO,
    largura=0.8,
    largura_realce=1.1,
)
