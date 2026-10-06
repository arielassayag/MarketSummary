# Replicar o CDP — o seu portal e a sua carteira, com qualquer assistente de IA

Três níveis, do mais simples ao completo. Todos usam só dados públicos, código aberto e o plano
de IA que você já tem (Claude, ChatGPT/Codex, Gemini ou outro).

| Nível | Para quê | Guia |
|---|---|---|
| 1. Auditar | conferir e recalcular o que o CDP publicou | `docs/cdp/REPRODUZIR.md` |
| 2. Espelhar o portal | ter uma cópia do portal publicada de graça | seção 2 abaixo |
| 3. Operar a sua carteira | rodar o processo inteiro com a sua data de início | seção 3 abaixo |

Custos: hospedagem zero (GitHub Pages e Actions em repositório público); IA = o seu plano.
Aviso: é uma carteira simulada para pesquisa; não capte recursos nem ofereça investimento com
ela (regras da CVM). Verifique a licença do repositório antes de redistribuir.

## 1. Auditar

`docs/cdp/REPRODUZIR.md`: clonar, `uv sync`, `uv run python -m cdp verify`, recalcular modelos e
decisões a partir dos insumos públicos arquivados e reproduzir qualquer etapa da mente em qualquer
assistente com `cdp mente pacote`. No portal, a página **Dados abertos e auditoria** traz cada
arquivo com o seu código de verificação e o link para a versão do repositório que o gerou.

## 2. Espelhar o portal

1. Faça um fork de `arielassayag/MarketSummary` no GitHub.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → habilite os workflows (forks começam com agendamentos desligados) → `cdp-site` →
   Run workflow. O portal fica em `https://<seu-usuário>.github.io/<repositório>/`.
4. Para acompanhar o livro original, use "Sync fork" quando quiser; o workflow republica.
5. Antes de haver carteira, rode o `cdp-site` com a opção de demonstração: um portal completo
   marcado DADOS SIMULADOS, montado só como artefato da execução (baixe e abra localmente; nunca
   vai ao endereço público).

## 3. Operar a sua carteira

1. **Fork e ambiente**: clone o seu fork; `uv sync --extra dev --extra ai`;
   `uv run python -m cdp demo` (confere que tudo roda offline).
2. **Livro novo**: num ramo próprio, remova o livro e os relatórios da carteira herdados
   (`git rm -r book pesquisa reports/daily reports/weekly reports/semanal reports/risk` e os
   arquivos `docs/cdp/teses/*.json`), mantenha `data/` (dados públicos de mercado) e a pesquisa
   de metodologia (`reports/backtest`) e ajuste à mão:
   - `configs/cdp/fund.yaml` → `fund.inception_date` (a sua data de início; mudar o mandato é
     decisão sua e entra no histórico);
   - `configs/cdp/site.yaml` → `base_url` e `repositorio`;
   - `configs/cdp/rotinas.yaml` → `repositorio`;
   - `configs/cdp/executor.yaml` → o seu executor (`local-pc`, `claude-cloud`,
     `github-actions`…) e o seu nome.
   Confira com `uv run python -m cdp rotinas verificar` e `uv run python -m cdp verify`; faça o
   commit e o merge no seu `main`.
3. **Escolha o harness e o agendador** (`docs/cdp/AUTOMACAO.md`):
   - Claude Code na nuvem: `uv run python -m cdp rotinas exportar --alvo claude-routines`;
   - Codex pelo plano (ChatGPT): `codex login` na sua máquina e
     `uv run python -m cdp rotinas exportar --alvo cron --harness codex` (o script de rotina faz o
     git fora do sandbox do Codex);
   - Codex, Gemini CLI ou outro no GitHub Actions (chave de API do modelo):
     `uv run python -m cdp rotinas exportar --alvo github-actions` (Antigravity: experimental);
   - PC próprio: `uv run python -m cdp rotinas exportar --alvo cron` (ou `launchd`, `windows`,
     `claude-desktop`).
   Registre a identidade do executor (`CDP_EXECUTOR` no ambiente das rotinas — nunca no
   ambiente das suas sessões interativas —, ou
   `uv run python -m cdp executor registrar --como local-pc` no clone dedicado às rotinas).
4. **Portal**: ligue o Pages (seção 2); a cada gravação das rotinas o portal atualiza.
5. **Conferência**: `uv run python -m cdp estado --rede --formato md`; no portal, `manifest.json`
   deve trazer a última versão de `origin/main` que muda o portal, e `sha256sum -c SHA256SUMS`
   deve passar (`docs/cdp/SITE.md`, "Conferir uma publicação").

## Continuidade entre assistentes

O processo não depende do assistente: `AGENTS.md` é o manual de qualquer harness, os roteiros
ficam em `docs/cdp/playbooks/`, a agenda em `configs/cdp/rotinas.yaml` e as skills abertas em
`.agents/skills/`. Para trocar de assistente no meio do caminho, peça ao novo: "leia `AGENTS.md`
e continue a operação do CDP" — ele começa por `uv run python -m cdp estado`.
