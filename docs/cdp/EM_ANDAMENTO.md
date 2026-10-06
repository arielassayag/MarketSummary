# Em andamento — passagem de bastão entre sessões (qualquer harness)

Documento vivo. Quem encerra uma sessão de desenvolvimento atualiza este arquivo: o que mudou, o
que falta, riscos. Quem chega lê aqui antes de mexer em qualquer coisa (`AGENTS.md`, seção 1).
Decisões já tomadas: `docs/cdp/DECISOES.md`.

Última atualização: 2026-10-06 (sessão de desenvolvimento no Claude Code).

## Frentes abertas

| Frente | Estado | Próximo passo |
|---|---|---|
| Operação agnóstica ao harness | `AGENTS.md` canônico, `GEMINI.md`, `.gemini/settings.json`, skills neutras em `.agents/skills/`, `cdp estado`, `cdp rotinas`, `cdp executor`, `cdp trava`, `cdp sincronizar`, `cdp publicar`, `scripts/cdp_rotina.*` | Plugin e skills do Claude passarem a seguir o envelope gate → sincronizar → roteiro → publicar (pedido ao dono do plugin) |
| Nuvem (rotinas do Claude Code) | Prompts e corpos gerados (`cdp rotinas exportar --alvo claude-routines`) | Criar ambientes "CDP" e "CDP-ensaio", criar as rotinas desligadas, ensaio, troca de executor (`docs/cdp/AUTOMACAO.md`) |
| Portal público (GitHub Pages) | `cdp site construir/conferir`, `.github/workflows/cdp-site.yml` | Ativar o Pages (fonte "GitHub Actions") e publicar depois da abertura do livro |
| Carteira inaugural | Data de início 2026-10-09; abertura do livro pela rotina diária | Rotina do PC local abre o livro; montagem na sexta |

## Integração pendente

- Plugin e skills do Claude (`plugins/cdp`, `.claude/skills`): adotar o envelope
  `cdp rotinas gate` → `cdp sincronizar` → roteiro → `cdp publicar` → `cdp trava liberar`;
  espelhar `.agents/skills` em `.claude/skills` (`uv run python -m cdp skills sincronizar --claude`);
  republicar artifact só em sessão interativa; risco e calibração sem regravar o painel.
- `docs/cdp/ROTINAS.md` e `docs/cdp/LOCAL.md`: tabela gerada de `configs/cdp/rotinas.yaml`
  (cobertura às 22:37, risco às 16:03, repescagem de sábado às 10:07); `cdp executor registrar`
  no clone do PC; `scripts/cdp_run_task.*` como invólucros de `scripts/cdp_rotina.*`.
- Painel: perfil "site" sem cortes (hoje o portal usa o nível 0 do artifact com os limites
  liberados), seção "Auditoria e reprodução" lendo `dados/datapackage.json`.
- Licença, Pages ligado, regra do ramo `main`, ambientes e rotinas da nuvem (decisões humanas).

## Riscos conhecidos

- Rotinas da nuvem são um recurso em prévia: o formato da API pode mudar; a documentação só traz
  limites por hora (nenhum limite diário documentado — conferir o uso em
  claude.ai/settings/usage).
- Push da nuvem: o proxy do GitHub não restringe o ramo (recusa só exclusões e o que não é
  ramo), então `cdp-trava` e `HEAD:main` funcionam, limitados só pelas regras do repositório;
  confirmar no ensaio apenas que uma sessão longa de sexta cabe numa execução.
- Kill switch ligado pela rotina de risco enquanto outra rotina segura a trava, com clones
  separados (nuvem): o relatório sai, o kill switch fica retido na máquina descartável. Falta um
  pedido de kill switch mesclável aplicado pela rotina exclusiva seguinte (pedido ao dono do
  monitor de risco).
- Execuções agendadas do GitHub Actions podem atrasar minutos em horários cheios (só alternativa).
- Licença do repositório ainda não definida (`docs/cdp/DECISOES.md`).

## Como continuar

1. `uv sync --extra dev --extra ai` e `uv run python -m cdp estado --formato md`.
2. Escolha a frente na tabela acima; trabalhe em ramo próprio; nunca grave o livro.
3. `uv run pytest tests/cdp -q` e `uv run ruff check .` antes de propor um commit.
4. Atualize este arquivo ao encerrar.
