# Eventos corporativos e retificação financeira — plano

Objetivo: corrigir o split de EMBJ, bloquear retorno sem base ajustada e anexar os resultados retificados sem alterar arquivos originais.

Execução nesta sessão, sem agentes adicionais. Desenvolvimento em ramo próprio; operação somente no executor designado, com gate manual e trava conforme autorização do operador.

- [ ] Regressões offline: split direto/reverso, posição comprada/vendida, preço já ajustado (não duplicar), vigência do ratio, evento ausente e evidência adulterada.
- [ ] Catálogo de eventos com fonte primária arquivada e SHA-256; aplicação por data aos retornos e quantidades, incluindo ADRs. Ausência de barra ajustada em posição mantida bloqueia o registro.
- [ ] Retificação append-only da cauda: original/CSV/relatório preservados; candidato integral recalculado pelo motor; recibo vincula original, candidato, diagnóstico e evidência. A leitura corrente e o próximo fechamento usam o registro retificado.
- [ ] Verificação de originais e retificações, adulteração/remoção, idempotência e continuação da série; efetivações nunca repetidas.
- [ ] CLI com prévia, confirmação por execução/trava e publicação oficial; relatório retificado em pasta própria com identificação explícita.
- [ ] Testes relevantes, lint, conferência de documentação e passagem de bastão. Integrar somente fontes no main e sincronizar oficialmente o executor.
- [ ] No executor: gate autorizado pelo operador, recalcular e publicar os anexos, conferir integridade e liberar trava.
- [ ] Gerar PDF/email corrigidos em saída nova, validar e revisar todas as páginas; deduplicar pelo assunto de correção e confirmar Gmail.
