# Identidade visual do CDP — "Sertão em xilogravura"

Guia da marca no portal do fundo (o painel publicado como artifact, gerado de
`src/cdp/workflow/painel_template.html`). Vale para quem mexer no template, no estilo ou nos
arquivos desta pasta.

| Arquivo | O que é |
|---|---|
| `cdp-logo.png` | A marca original (1536 × 1024, RGBA, fundo transparente). Fonte única de tudo. |
| `marca_tinta.webp` | Máscara alfa da tinta: letras, cabra, mandacaru, chapada, ASSET MANAGEMENT (960 × 596). |
| `marca_sol.webp` | Máscara alfa da cor especial: o sol listrado e a estrela da régua (960 × 596). |
| `marca_cabra.webp` | Máscara alfa da cabeça da cabra, com o chifre inteiro (120 × 98): o emblema das abas. |
| `../../../scripts/cdp_marca.py` | Regera as três máscaras a partir de `cdp-logo.png` e o bloco CSS do template. |

## 1. Conceito

O portal é impresso como a marca: **tinta de xilogravura sobre papel de cal** e uma única cor
especial — o **sol queimado** do logo — usada só em ornamento. A cor que trabalha (links, foco,
botões, série do CDP nos gráficos) é o **anil** das portas e janelas das casas caiadas do sertão.

A terra do Ceará fica nas bordas da página, nunca no meio dos dados:

- no cabeçalho, o céu riscado a goiva e o horizonte com a chapada do Araripe, o
  mandacaru-candelabro e o xique-xique;
- no rodapé, a contracapa de tinta: a chapada entalhada, o sol listrado da marca nascendo atrás
  dela, o chão rachado e a assinatura com a marca completa;
- em toda régua, a estrela de 8 pontas do chapéu de couro (a da régua do logo).

A área de dados fica limpa, sóbria e densa, para alocadores. **Claro** é "cal a pino" (padrão).
**Escuro** é "a matriz invertida": tinta de osso sobre carvão, como na composição escura da marca,
com o sol mais quente.

## 2. A marca no portal

O portal nunca usa a imagem colorida. A marca é pintada por **máscaras alfa** com os tokens do
tema, então troca de cor sozinha com o tema e continua nítida em qualquer tela:

- `::before` pinta `marca_tinta` em `var(--tinta)` — tinta no claro, osso no escuro;
- `::after` pinta `marca_sol` em `var(--sol)` — o sol e a estrela da régua.

| Uso | Peça | Tamanho | Cor |
|---|---|---|---|
| Cabeçalho (desktop e tablet) | **Marca completa**, com ASSET MANAGEMENT e a régua com estrela | `clamp(208px, 22vw, 312px)` de largura: 312 px a partir de ~1.420 px, 282 px a 1.280 px; proporção da máscara (`--marca-proporcao`). A coluna da direita (posição e selos) tem base de 300 px e quebra o texto por dentro, alinhada à direita, então fica na linha da marca acima de 1.120 px; abaixo disso desce inteira, alinhada à esquerda | `--tinta` + `--sol` |
| Cabeçalho (≤ 640 px) | Recorte **sem a linha ASSET MANAGEMENT** (as mesmas máscaras, do topo, `--marca-proporcao-topo`) | 128 px | idem |
| Rodapé | **Marca completa** como assinatura, embaixo, no centro | 220 px (176 px no celular) | osso do rodapé (`--ink` do `.foot`) + `--sol` |
| Barra de abas (fixa no topo) | **Cabeça da cabra** (`marca_cabra.webp`, a barra do D apagada) | 39 × 32 px; some ≤ 640 px | `--tinta` |
| Favicon | Estrela de 8 pontas sobre quadrado de tinta (SVG embutido no `<head>`) | — | `#e08a45` sobre `#1d1611` |

**Acessibilidade.** O logo do cabeçalho tem `role="img"` e
`aria-label="CDP Asset Management — Cabra da Peste"`; o texto "CDP" que o script escreve no
elemento fica escondido. Ornamentos são pseudo-elementos vazios (fora da árvore de
acessibilidade). No **alto contraste do sistema** (`forced-colors: active`, Windows) o navegador
troca os fundos por `Canvas`, o que apagaria tudo o que é pintado por máscara: logo, emblema e
assinatura do rodapé saem em `CanvasText` (`forced-color-adjust: none`) e a aba ativa, que perde
a régua de sol, ganha sublinhado. Ornamentos de papel (estrelas, renda, horizonte) somem nesse
modo, de propósito.

**Sem máscara CSS** (navegador antigo, `@supports not (mask-image)`): os ornamentos recortados
somem (sairiam blocos e quadrados de cor) e a marca volta a ser o texto "CDP" em Cinzel, na tinta.
**Limitação conhecida:** o Safari do macOS 10.15 ou anterior não decodifica WebP; ali a máscara
falha, o logo e o emblema não aparecem (o nome do fundo continua no cabeçalho). Uma reserva em PNG
custaria ~90 KB de base64 e levaria o estilo a ~254 KB, colado no limite de 260 KB por arquivo.

**Área de proteção.** No mínimo 1/4 da altura das letras "CDP" em volta da marca (≈ 25 px a
312 px de largura): 26 px acima, 28 px até o filete separador do nome do fundo, ~27 px até a
chapada do horizonte; 30 px ou mais em volta da assinatura do rodapé.

**Tamanhos mínimos.**

| Peça | Mínimo |
|---|---|
| Marca completa | 156 px (abaixo disso ASSET MANAGEMENT fica com menos de 5 px: use o recorte) |
| Recorte sem ASSET MANAGEMENT | 96 px |
| Cabeça da cabra | 20 px |

**Não faça:**

- recolorir o sol com uma cor de dado;
- pôr brilho, halo ou sombra atrás da marca (a xilogravura fica nítida);
- esticar ou distorcer (a proporção vem da máscara);
- pôr a marca sobre foto ou textura;
- tinta sobre tinta (no rodapé escuro a marca é osso);
- redesenhar a régua com estrela fora da marca;
- criar monogramas alternativos (nada de "ferro" em letra sem serifa).

## 3. Paleta (tokens)

Três estados, sem JavaScript de tema além do atributo `data-theme`:

- **claro** no `:root` puro (padrão);
- **escuro do sistema**: `@media screen and (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }`;
- **escuro escolhido**: `@media screen { :root[data-theme="dark"] }`.

Os blocos escuros valem só na **tela**: impresso, o portal sai sempre no papel claro (o bloco de
impressão só clareia papel, céu e rodapé), sem uma terceira cópia da paleta.

| grupo | token | claro | escuro |
|---|---|---|---|
| Papel e tinta | `--bg` | `#f4efe5` | `#12100d` |
|  | `--surface` | `#fffdf8` | `#1b1713` |
|  | `--surface-2` | `#efe8db` | `#25201a` |
|  | `--surface-3` | `#f8f4ec` | `#171410` |
|  | `--ink` | `#1d1611` | `#efe6d5` |
|  | `--ink-2` | `#4a3e33` | `#cbbfa9` |
|  | `--muted` | `#685a4b` | `#a39682` |
|  | `--line` | `#d8ccb8` | `#3a3129` |
|  | `--grid` | `#e8e0d1` | `#29231d` |
| Interação (anil) | `--accent` | `#2b4596` | `#9aaee8` |
|  | `--accent-2` | `#1e3274` | `#bac7f0` |
|  | `--accent-soft` | `#e4e8f5` | `#232842` |
|  | `--on-accent` | `#ffffff` | `#12100d` |
| Posição | `--long` | `#0c6670` | `#4fb0b8` |
|  | `--long-soft` | `#d9ecee` | `#15302f` |
|  | `--short` | `#8f3417` | `#e5764f` |
|  | `--short-soft` | `#f6e0d6` | `#3b2219` |
|  | `--shadow` | `#8b816f` | `#a39a86` |
| Sinal e divergente | `--pos-ink` | `#1c6b3d` | `#86d9ae` |
|  | `--neg-ink` | `#b0281f` | `#ff7f70` |
|  | `--div-pos` | `#2b4fa8` | `#7f9be6` |
|  | `--div-neg` | `#c0412f` | `#e5685f` |
| Categóricas (gráficos) | `--c1` anil | `#2b4fa8` | `#7a9ae8` |
|  | `--c2` quixaba | `#6a3c5e` | `#dcbaf7` |
|  | `--c3` mandacaru | `#24876a` | `#4fbf93` |
|  | `--c4` ouro velho | `#7f6a12` | `#e8d170` |
|  | `--c5` ipê | `#a24f93` | `#dc8cc0` |
|  | `--c6` caatinga | `#57514a` | `#857d6e` |
| Estado | `--ok` / `--ok-bg` | `#1d6b3e` / `#e0efe2` | `#86d9ae` / `#15301f` |
|  | `--warn` / `--warn-bg` / `--warn-mark` | `#7a4e00` / `#f8ebcc` / `#b07f0a` | `#f0c45e` / `#352a10` / `#dca42a` |
|  | `--crit` / `--crit-bg` / `--crit-mark` | `#ab261d` / `#f9dfda` / `#cc3f33` | `#ff8476` / `#3c1a16` / `#e5574d` |
|  | `--info` / `--info-bg` | `#2b4596` / `#e4e8f5` | `#a9b8ec` / `#20253b` |
|  | `--na` / `--na-bg` | `#685a4b` / `#eee7da` | `#a39682` / `#26201a` |
|  | `--band` | `#d8ebda` | `#1c3a29` |
| Dados simulados | `--sim` / `--sim-2` / `--sim-ink` | `#f2c230` / `#e0aa14` / `#1d1700` | `#f0bc3a` / `#d9a01f` / `#1a1206` |
| Marca e ornamento (nunca dado) | `--tinta` | `#1d1611` | `#efe6d5` |
|  | `--sol` | `#b9692f` | `#e9a043` |
|  | `--sol-ink` (sobrancelhas) | `#8e4a16` | `#f0a75a` |
|  | `--on-sol` (texto selecionado) | `#12100d` | `#12100d` |
|  | `--filete` | `#1d1611` | `#8f826f` |
|  | `--renda` | `#b8a487` | `#5a4b3c` |
|  | `--ceu-1` / `--ceu-2` | `#fcfaf5` / `#f3e6d0` | `#0e0c0a` / `#21170f` |
|  | `--ceu-brasa` | `rgba(236, 170, 96, 0.22)` | `rgba(222, 124, 44, 0.3)` |
|  | `--ceu-risco` | `rgba(29, 22, 17, 0.2)` | `rgba(239, 230, 213, 0.14)` |
|  | `--horizonte` | `#1d1611` | `#0a0807` |
|  | `--chao` / `--chao-line` | `#fffdf8` / `#1d1611` | `#0d0b09` / `#2c241d` |
|  | `--mast-sep` | `#d3c4ab` | `#3d3229` |
|  | `--foot-bg` | `#1d1611` | `#261d16` |
|  | `--sel-bg` / `--sel-ink` | `#1d1611` / `#fbf7ef` | `#efe6d5` / `#12100d` |
|  | `--grao` | grão claro | grão escuro |

**Rodapé** (contracapa de tinta nos dois temas; tokens redefinidos no próprio `.foot`):
`--ink #f1e8d6`, `--ink-2 #d6c9b1`, `--muted #b3a58e`, `--line #4d4034`, `--surface #2b2219`,
`--accent #b3c3f2`, `--sel-bg #f1e8d6` / `--sel-ink #1d1611`; fundo `--foot-bg`.

### 3.1 Contraste (WCAG 2.x)

Todo par de texto passa AA (≥ 4,5); marcas gráficas passam ≥ 3.

| uso | par | claro | escuro |
|---|---|---|---|
| corpo sobre papel | `ink` / `bg` | 15,59 | 15,33 |
| texto secundário | `ink-2` / `surface` | 10,19 | 9,81 |
| legendas | `muted` / `surface` | 6,55 | 6,14 |
| legenda em cabeçalho de tabela | `muted` / `surface-2` | 5,47 | 5,57 |
| subtítulo no céu do cabeçalho | `ink-2` / `ceu-2` | 8,40 | 9,68 |
| sobrancelha no papel | `sol-ink` / `bg` | 5,83 | 9,39 |
| links (anil) | `accent` / `surface` | 8,63 | 8,14 |
| texto em botão anil | `on-accent` / `accent` | 8,77 | 8,68 |
| carimbo selecionado | `sel-ink` / `sel-bg` | 16,72 | 15,33 |
| texto selecionado | `on-sol` / `sol` | 4,63 | 8,66 |
| selo short (o mais justo) | `short` / `short-soft` | 6,20 | 4,92 |
| carimbo DADOS SIMULADOS | `sim-ink` / `sim` | 10,67 | 10,55 |
| ornamento sol (gráfico) | `sol` / `bg` | 3,58 | 8,66 |
| filetes (gráfico) | `filete` / `bg` | 15,59 | 5,06 |
| rodapé: fontes | `muted` / `foot-bg` | 7,39 | 6,84 |

**Daltonismo** (ΔE2000 após simulação, Machado 2009): long × short fica ≥ 29 em todas as
simulações; o sol (ornamento) foi afastado do short (dado) — por isso o short claro é um barro
escuro `#8f3417`; long ficou mais azul (`#0c6670`) para se separar do positivo; positivo ×
negativo mantém verde/vermelho e, sob protanopia, se apoia no sinal +/−, sempre exibido; a
paleta categórica tem pior par ≥ 7,8 em qualquer simulação (`--c1` × `--c5` sob protanopia).
`--c2` era um urucum laranja a ΔE 7,8 (claro) / 5,9 (escuro) do sol, ou seja, o sol da marca
dentro dos gráficos; virou **quixaba** (o fruto roxo-escuro da quixabeira da caatinga; lilás no
escuro): a ΔE 37,8 / 45,5 do sol, ≥ 14 / 26 do short, ≥ 13 / 12 do `--c4` e do `--warn-mark` e
≥ 12,7 / 11,0 do `--c5` em qualquer simulação, sem piorar o pior par categórico.

## 4. Tipografia

Um único `<link>` do Google Fonts: Alegreya (400–800, itálico 400), Cinzel (600–700),
IBM Plex Mono (400, 500) e IBM Plex Sans (400–600, itálico 400).

| Papel | Família | Desktop | ≤ 640 px | Notas |
|---|---|---|---|---|
| Nome do fundo (`.brand-name`) | Cinzel 600 | 31 px / 1,05, +0,05em | 19 px | A voz de "ASSET MANAGEMENT" |
| Título de seção (`.sec-h h2`) | Cinzel 600 | 22 px / 1,2, +0,045em | 19 px | Precedido de estrela de 15 px |
| Títulos do rodapé, carregamento | Cinzel 600 | 16 / 15 / 20 px | — | |
| Carimbo DADOS SIMULADOS | Cinzel 700 | 17 px, +0,14em | 14 px | Entre duas estrelas, moldura de tinta de 2 px |
| Capitular | Cinzel 700 | 2,9em | — | Letra de papel recortada num bloco de tinta |
| Título da tese | Alegreya 700 | 34 px / 1,12 | 26 px (28 a ≤ 900) | |
| Título do destaque (`.th-hl-t`) | Alegreya 700 | 25 px / 1,2 | 21 px | |
| Títulos de bloco e cartão | Alegreya 700 | 17,5 px / 1,25 | — | |
| Abertura da tese (`.md.lead-md`) | Alegreya 400 | 19 px / 1,55 | 17 px | Algarismos alinhados |
| Narrativa (`.md`, `.prose`) | Alegreya 400 | 17 px / 1,58 | 16 px | Algarismos alinhados |
| Interface, abas | IBM Plex Sans 400–600 | 14 px | 13,5 px | |
| Sobrancelha (`.eyebrow`) | Plex Sans 600, caixa alta | 11,5 px, +0,14em, `--sol-ink` | 11 px | Estrela de 11 px antes; nunca Cinzel (tem datas) |
| Rótulo / valor de indicador | Plex Sans 600 | 11 px +0,09em / 23 px | — | "VaR 1 dia" mantém o `1` legível |
| Tabelas | Plex Sans | 13 px (cabeçalho 12 px) | — | Algarismos tabulares |
| Códigos e tickers | IBM Plex Mono | 0,9em | — | |

Reservas: Cinzel → "Trajan Pro", "Cormorant SC", "Times New Roman", Georgia; Alegreya →
"Source Serif 4", "Iowan Old Style", Georgia, Cambria; Plex → fontes do sistema.

**Regra:** Cinzel só em texto sem algarismos — o `1` da Cinzel parece um `I`.

**Algarismos da Alegreya:** o padrão dela são os algarismos de texto (o `10` de "10 maiores
posições" vira "Io"). Títulos de bloco e cartão, aberturas (`.lead`), narrativa (`.md`, `.prose`),
título da tese e do destaque usam `font-variant-numeric: lining-nums proportional-nums`, numa
regra só, **depois** de todas as regras com o atalho `font:` (que zera `font-variant-numeric`);
as tabelas do Markdown voltam aos algarismos tabulares.

## 5. Ornamentos

Todos são SVG monocromáticos em data URI (máscaras ou fundos) que pegam a cor dos tokens, mais
gradientes CSS. Ficam embutidos no fim do `<style>` do template; nenhuma imagem externa.

| Ornamento | Onde | Tamanho e cor |
|---|---|---|
| Céu de goiva: riscos horizontais, mais densos perto do horizonte (as listras do sol) | `.mast::before`, 56 px de baixo do cabeçalho | `--ceu-risco`; período de 1.600 px |
| Horizonte de xilogravura: chapada do Araripe com estrias, mandacaru-candelabro (não saguaro), xique-xique, caatinga e chão riscado | `.mast::after` | 48 px (36 no celular); vinheta centrada na coluna, o chão segue liso até as bordas |
| Estrela de 8 pontas (proporção da régua do logo) | títulos de seção, sobrancelhas, marcadores de lista, linha do tempo, `hr`, capa do destaque, aba ativa, renda, carimbo de dados simulados | 11–24 px, `--sol` |
| Régua com estrela (a do logo) | aba ativa: dois filetes de 2 px e uma estrela de 12 px | `--sol`; não muda a largura da aba |
| Filete de tipografia (grosso 2 px + fino 1 px) | sob cada `.sec-h` | `--filete` |
| Filete de prelo (2 px) | topo das tabelas (`.scroll`) e dos indicadores (`.tile`); filete de tinta sob `th` | `--filete`, `--ink-2` |
| Capa de folheto de cordel: moldura dupla (2 + 1 px, 6 px de vão) aberta no topo para uma estrela de 24 px | `.th-hl` (destaque da Visão geral) | só gradientes |
| Capitular de xilogravura | primeira letra da abertura da tese | bloco de `--tinta`, letra de papel |
| Renda de bilro: bico com losango e picô, duas corridas com vão para a estrela | entre seções (`.panel > .sec + .sec`) | 344 × 14 px, `--renda`; estrela de 15 px `--sol`; centradas no vão entre seções (`--vao`: 36 px, 28 no celular) |
| Pesponto (costura de couro tracejada) | linha do tempo `.tl` | 2 px tracejado `--line` |
| Chapada do rodapé (paredão entalhado, mandacaru, rachaduras) | `.foot::before`, subindo do papel | 90 px (68 no celular), `--foot-bg` |
| Sol listrado nascendo atrás da chapada | `.foot::after` | disco de 72 px (54 no celular) |
| Chão rachado (Voronoi periódico) | fundo do rodapé; abaixo dele a terra continua lisa (`box-shadow`) quando a página é mais curta que a janela | osso a 7%, ladrilho de 260 px |
| Grão de papel (ruído fractal) | `body` e `.tnav` (`background-image`) | um por tema, ~0,4 KB |
| Cabeça da cabra | `.tabs-in::before` | máscara `marca_cabra.webp`; a barra de abas tem a altura final (50 px, 46 no celular) desde o carregamento |

Sem sombra nem `filter` em peça recortada por máscara: o filtro roda antes da máscara e a sombra
some (a "borda quente" do horizonte e da chapada no escuro nunca apareceu e saiu do estilo).

O `html` (a tela fora da página na rolagem elástica do Mac e do iPhone) é o `--ceu-1` do topo do
cabeçalho: puxar no topo não mostra uma faixa de tinta sobre a cal. O rodapé vazio (carregando ou
sem dados) é `display: flow-root` com 120 px de altura mínima: a margem não atravessa a caixa e
a contracapa aparece inteira, com a chapada e o sol.

## 6. Gráficos

`--accent` (anil) é a série do CDP, a exposição líquida, o uso de limite e as barras ativas;
`--shadow` é a série de referência quantitativa; `--c1`…`--c6` as séries categóricas; `--div-pos`
/ `--div-neg` o divergente; `--long` / `--short` a borboleta e as barras de posição; `--band` a
banda de volatilidade; `--grid` / `--line` grade e eixos. **`--sol` nunca entra num gráfico.**

## 7. Cores semânticas

| Significado | Tokens | Regra |
|---|---|---|
| Long / short | `--long` (mandacaru), `--short` (barro/cobre) | Como no texto da página: "compra em verde-azulado, venda em cobre". Tema long e short ao mesmo tempo ganha selo **neutro** (`.nchip.LS`, `.side.LS`). |
| Positivo / negativo | `--pos-ink`, `--neg-ink` | Sempre com sinal +/− |
| ok / alerta / excesso / info / n/d | `--ok*`, `--warn*`, `--crit*`, `--info*`, `--na*` | Sempre com rótulo de texto no selo; `*-mark` em barras e bordas |
| Dados simulados | `--sim`, `--sim-2`, `--sim-ink` | Faixa listrada com filetes de tinta, carimbo em Cinzel entre estrelas, selo `k-sim` contornado, faixa de 6 px sob as abas fixas |
| Marca e ornamento | `--tinta`, `--sol`, `--filete`, `--renda` | Nunca um valor de dado |

## 8. Movimento

Nada novo: sem transições, parallax ou ornamentos animados. A única animação é a barra de
carregamento (`.boot-bar`), no sol. Com `prefers-reduced-motion` a barra fica cheia e parada
(opacidade 0,6).

## 9. Impressão

Os temas escuros valem só na tela, então imprimir do escuro sai em papel branco com a paleta
clara. O bloco de impressão deixa papel, superfícies, céu e rodapé brancos, tinta preta e sem
grão; esconde céu, horizonte, emblema das abas, renda, chapada, sol e assinatura do rodapé; o
cabeçalho ganha filete de tinta de 2 px e a marca encolhe para 200 px; o rodapé fica branco com
filete de tinta no topo. Marca, estrelas, filetes, capa do destaque, indicadores, tabelas e
selos usam `print-color-adjust: exact`.

- **Grades viram blocos** no papel (`.panel`, `.sec`, `.cols*`, `.stack`): um bloco com
  `break-inside: avoid` que pula de página empurra o resto; numa grade, o Chromium não cresce o
  contêiner e o rodapé branco cobria o fim da seção (os últimos eventos da Visão geral).
- A capa do destaque (`.th-hl`) ganha 10 px de borda transparente no topo: a estrela fica dentro
  da caixa e pula de página com ela, em vez de sobrar sozinha no pé da página anterior.
- A marca impressa leva `filter: opacity(1)`: achata as duas máscaras numa camada só no PDF. Sem
  isso o PDF do Chromium desenha um filete na borda da caixa da marca (cinza no poppler; uma
  barra de sol à direita no Preview do Mac).

## 10. Faça / não faça

**Faça**

- Use o sol só em ornamento e em "onde você está" (aba ativa, estrela, régua).
- Use o anil em tudo o que é clicável e na série do CDP.
- Mantenha a Cinzel em textos curtos sem algarismos; sobrancelhas, indicadores e tabelas ficam
  em Plex.
- Um filete de tipografia por seção e uma capa de folheto por página (`.th-hl`).
- Área de dados sem textura além do grão do papel.
- DADOS SIMULADOS sempre à vista: faixa, faixa sob as abas e selos.
- Teste os dois temas, 375/390 px, 1.120–1.440 px e a impressão. Com a Plex, as nove abas e o
  emblema cabem a partir de ~1.270 px (recuo das abas de 10 px, 8 px até 1.320 px); abaixo disso,
  ou com a fonte de reserva (Google Fonts bloqueado), as abas rolam com as bordas esmaecidas, e o
  `scroll-padding` deixa a aba ativa ou focada fora do esmaecimento.

**Não faça**

- Laranja para sinalizar dado, alerta ou "short".
- Cinzel em números, datas, abas, cabeçalhos de tabela ou rótulos de indicador.
- Pôr do sol brilhando atrás do logo, céu estrelado ou clichês de deserto (saguaro, caubói,
  Texas/México).
- Ornamento dentro de tabelas e gráficos.
- Repetir o horizonte nas bordas: é uma vinheta centrada.
- `mask-composite`, `backdrop-filter`, `:has()` ou recortes ajustados a pixel: ornamentos escalam
  por porcentagem ou `contain`.
- Transformar o `body` em coluna flex.
- Cores de dado nos ornamentos.

## 11. Manutenção

- **Máscaras e bloco CSS:** `uv run --extra dev python scripts/cdp_marca.py --mascaras` regrava
  as três máscaras a partir de `cdp-logo.png` e troca, no template, o bloco entre
  `/* >>> marca: … */` e `/* <<< marca */` (data URIs base64 em linhas de até 1.800 caracteres,
  mais as proporções `--marca-proporcao` e `--marca-proporcao-topo`); `--template` só regrava o
  bloco a partir das máscaras gravadas. Sem essas opções o script só lê: imprime o bloco,
  `--check` confere o template e `--previa DIR` grava composições PNG nos dois temas para revisão.
  O Pillow (com WebP) está no extra `dev`. Os parâmetros (limiar do halo, separação tinta × sol
  pela cor, folga, recorte da cabra) estão no topo do script.
- **Ornamentos:** ficam embutidos no template (fim do `<style>`); não dependem da marca.
- **Teste:** `tests/cdp/test_painel.py::test_template_carries_the_brand_identity` exige que o
  template traga exatamente as máscaras desta pasta, os tokens e os três estados de tema, o nome
  acessível do logo e o estilo e o script dentro do limite de publicação (≤ 260 KB, linhas ≤
  2.000 caracteres).
- **Orçamento:** máscaras ≈ 48 KB (tinta 39 KB, sol 4,8 KB, cabra 4,3 KB), ≈ 64 KB em base64;
  estilo publicado ≈ 164 KB; script ≈ 244 KB (uma única linha nova: o tema salvo aplicado antes de
  os dados chegarem).
- Mudar o template muda a versão da página: a próxima rotina republica a casca, o estilo e o
  script do painel (ver `docs/cdp/LOCAL.md`, §10).
