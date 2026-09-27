# MarketSummary — Fechamento | AI Notes

Aplicação didática para separar coleta, cálculos em Python, redação e revisão humana.

## O que é gratuito — e o que cada modo faz

| Caminho | Internet após instalação | Chave | Resultado |
|---|---|---|---|
| `demo` | Não | Não | Dados simulados e texto por regras; não usa IA |
| `fetch` + `run --provider demo` | Na coleta | Não | Cotações públicas e carteira simulada; texto por regras |
| `run --provider openrouter --model openrouter/free` | Sim | OpenRouter | Rascunho por IA, sujeito à disponibilidade e cotas gratuitas |

Não há garantia de dados em tempo real, fechamento oficial ou disponibilidade contínua. A coleta obrigatória falha sem inventar preços. O modo gratuito não migra para modelos pagos.

## 1. Instalação

Instale [uv](https://docs.astral.sh/uv/getting-started/installation/). No Windows com WinGet:

```powershell
winget install --id astral-sh.uv --exact
```

No macOS/Linux:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Reabra o terminal e confira `uv --version`. Baixe o projeto em **Code → Download ZIP**, extraia e abra o terminal na pasta que contém `pyproject.toml`. Ou, se já tiver Git:

```sh
git clone https://github.com/arielassayag/MarketSummary.git
cd MarketSummary
```

O uv instala o Python necessário:

```sh
uv python install 3.12
uv sync --python 3.12 --locked
uv run python -m fechamento demo
```

Esperado: aviso de simulação, cálculos, rascunho e estado `IN_REVIEW`. A primeira instalação precisa de internet. Esse teste não usa IA nem chave.

## 2. Coleta pública sem chave

```sh
uv run python -m fechamento fetch --output-dir data/real/minha_coleta
uv run python -m fechamento run --scenario-dir data/real/minha_coleta --provider demo
```

A pasta precisa ser nova. Use outro nome para repetir; arquivos anteriores não são sobrescritos. Confira `sources.json`, `quotes.csv`, `positions.csv`, `news.jsonl` e `manifest.json`.

- Ações e índice: Yahoo Finance, com horários da fonte. A referência é a última sessão disponível; o preço atual pode ser intradiário.
- Câmbio: bid e varBid da AwesomeAPI, cuja referência pode diferir da bolsa.
- Taxas: BrasilAPI, na data da consulta; o endpoint não informa data de vigência.
- Notícias: Google News RSS, com `pubDate` e link (possivelmente um redirecionamento). Manchetes não são fatos verificados nem prova de causalidade.
- Carteira: pesos iguais **simulados**. O pacote inteiro é sinalizado como contendo simulação. Preços sem ajuste de dividendos/desdobramentos.

Somente o período diário está implementado. Datas de bolsa/câmbio incompatíveis ou cotação obrigatória ausente interrompem a coleta. Taxas/manchetes ausentes são registradas como limitações. Notícias recentes podem ser posteriores à sessão em fins de semana.

## 3. Configure a IA gratuita

1. Entre em [OpenRouter → Keys](https://openrouter.ai/settings/keys), crie sua conta ou faça login e clique em **Create Key**.
2. Copie `.env.example` para um novo arquivo `.env` na pasta do projeto.
3. Preencha `OPENROUTER_API_KEY="sua-chave"`. No Windows, evite o nome `.env.txt`.
4. Mantenha a chave privada. Use somente dados públicos ou fictícios no exercício.

### O que é `.env`?

Variáveis de ambiente são configurações que o programa lê enquanto executa. Cada uma tem um nome e um valor: `OPENROUTER_API_KEY` é o nome; sua chave é o valor. Assim, o mesmo código usa configurações diferentes em cada computador.

`.env` é um arquivo de texto simples com uma configuração por linha, no formato `NOME=valor`. Neste projeto, `python-dotenv` lê esse arquivo e o Python consulta a chave com `os.environ.get("OPENROUTER_API_KEY")`. O arquivo não configura automaticamente todo o computador nem criptografa seu conteúdo.

Duplique `.env.example` na pasta que contém `pyproject.toml`, renomeie a cópia para `.env`, abra em um editor de texto simples e preencha a chave entre as aspas. Se o arquivo já existir, preserve as outras configurações. Salve antes de executar o programa.

- Windows/Bloco de Notas: em “Salvar como”, escolha “Todos os arquivos”, nome `.env` e UTF-8. Confira que não virou `.env.txt`.
- macOS: `Command + Shift + .` mostra arquivos ocultos no Finder. No TextEdit, use “Formatar → Converter para Texto Simples” e confira que não acrescentou `.txt`.
- O projeto ignora `.env` no Git por meio de `.gitignore`; mantenha esse arquivo privado e compartilhe apenas `.env.example` sem sua chave.


Teste a conexão com números fictícios:

```sh
uv run python examples/chamada_ia.py
```

Rode a IA sobre o pacote coletado:

```sh
uv run python -m fechamento run --scenario-dir data/real/minha_coleta --provider openrouter --model openrouter/free
```

`openrouter/free` escolhe entre modelos gratuitos disponíveis e o código envia um teto zero para os preços dos tokens. A chamada pode falhar por cota, chave, indisponibilidade ou resposta inválida. Confira as [condições atuais](https://openrouter.ai/docs/api-reference/limits) e a [política de dados](https://openrouter.ai/docs/guides/privacy/data-collection). A retenção e o uso para treinamento dependem dos provedores e das configurações, não apenas de ser gratuito.

A CLI exige `--allow-paid` para um modelo pago explicitamente escolhido. Essa opção não faz parte do tutorial gratuito. A integração Gemini é opcional e tem regras próprias de preço; não é usada neste roteiro.

## 4. Revisão e interface

`IN_REVIEW` significa geração concluída e rascunho pronto para revisão humana. Cálculos são feitos em Python; o fluxo completo de IA usa referências ao FactBook e verificações. Isso reduz riscos, mas não garante que uma narrativa seja verdadeira.

```sh
uv run streamlit run app.py --server.address 127.0.0.1
```

A interface permite revisar, aprovar e exportar. A aplicação não se autoaprova. A aprovação vincula a versão do texto e os dados por hash.

### Concluir pela CLI

Depois de revisar o texto, substitua `ID_DA_EXECUCAO` pelo `Run ID` informado na geração:

```sh
uv run python -m fechamento approve ID_DA_EXECUCAO --approver "Seu nome"
uv run python -m fechamento export ID_DA_EXECUCAO
```

A exportação conclui em `EXPORTED` e salva `comentario.md`, `comentario.html` e `bundle.json` em `outputs/ID_DA_EXECUCAO/`. Alterações no pacote ou no texto invalidam a conferência. Para pacotes fora de `data/real` ou `data/demo`, informe também `--scenario-dir CAMINHO` nos comandos de aprovação e exportação.

## 5. Testes

```sh
uv sync --extra dev
uv run pytest
uv run ruff check .
```

Os testes usam respostas controladas para dependências externas. Testes locais não comprovam disponibilidade futura das APIs ou de uma conta nova.
