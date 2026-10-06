# Roteiro do espelho privado do painel — artifact no claude.ai (opcional, só operador)

Roteiro de sessão, não de rotina. O **portal público** do CDP é o site no GitHub Pages, montado
pelo GitHub Actions a partir do livro a cada push em `main` (`docs/cdp/SITE.md`). O artifact
privado do claude.ai é só um **espelho opcional** do painel, para quem opera.

## Regras

- **Nenhuma rotina sem supervisão publica artifacts**, em nenhum app: na nuvem, a publicação com
  arquivos de apoio pede confirmação e a rotina ficaria parada; os outros apps não têm a
  ferramenta.
- Só a pedido do operador, numa **sessão interativa do Claude** (Claude Code ou claude.ai) com a
  ferramenta `Artifact`. Em outro harness, não há espelho: o painel é o portal público.
- O artifact é criado uma única vez, pelo operador, e o link fica em
  `artifacts/painel/ARTIFACT_URL`; este roteiro nunca cria um artifact novo.
- Os arquivos do painel são gravados pelo código: leia-os, nunca os edite. Numa sessão de
  desenvolvimento, nunca faça commit de `artifacts/`.

## Passos

O procedimento completo, com cada conferência, está em `docs/cdp/LOCAL.md`, seção 10:

1. **Gerar o painel** (seção 10.1), num clone em dia com `main`:
   `uv run python -m cdp painel --sem-local`. Anote o bloco `artifact`. Com
   `artifact.publicavel: false` ou sem `artifact.url`, não publique: relate.
2. **Ler o que será publicado** (seção 10.2): cada arquivo de `artifact.arquivos_para_ler`, por
   inteiro.
3. **Publicar no mesmo artifact** (seção 10.3): `read`, `list` com `scope: "files"` e `publish`,
   nessa ordem, conferindo a versão da página publicada antes; nunca `force`.
4. **Registrar a página publicada** (seção 10.4), só depois de uma publicação bem-sucedida com
   `artifact.pagina_mudou: true`: `uv run python -m cdp painel --publicado`.

## Resumo

Uma linha: publicado (link de `artifacts/painel/ARTIFACT_URL`) ou o motivo de não ter publicado.
