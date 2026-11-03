# Correções locais — 19/10/2026

Implementado:
- Página inicial sem preço, assinatura, upgrade ou cotas antigas; IA sujeita a limites e disponibilidade. Exemplo visual identificado como ilustrativo.
- Cadastro real do allauth com links para termos/privacidade e preservação de nome/email quando há erro de validação.
- Política de privacidade: descrição operacional alinhada aos provedores presentes no código e retirada da referência a um checkbox inexistente. Isso não constitui auditoria jurídica.
- Demonstração limitada a três questões já existentes e conferidas (1124, 1145, 1148 no banco local). Manifesto portátil por texto e assinatura do conteúdo, categoria e alternativas; não depende dos IDs de produção. Mudanças invalidam a seleção até nova conferência. Nenhuma explicação foi gerada.
- Demonstração com explicações, manutenção da questão ao recarregar, verificação da questão apresentada e limite no envio. Sem fallback para conteúdo aleatório; banco sem a seleção completa apresenta indisponibilidade.
- HTML das explicações Markdown sanitizado com nh3; scripts, eventos e URLs perigosas removidos. Documentação: https://nh3.readthedocs.io/en/stable/index.html
- Respostas e erros retornados pela API do resultado de simulados escapados antes da inserção em HTML.

Validação:
- 108 testes Django aprovados em banco isolado, sem credenciais externas.
- 5 testes existentes do frontend aprovados.
- Cadastro e resposta da demonstração conferidos no navegador local.
- Logs em output/auditoria_aplicacao/; imagem em output/demo-corrigida.png.

Pendências reais:
- Qualidade editorial do banco completo: o isolamento da demonstração não corrige classificações erradas ou as 6095 questões revisadas sem justificativa identificadas na auditoria anterior. Não alterados gabaritos, categorias, aprovação ou justificativas do banco.
- Conferir no banco de produção a presença da seleção da demonstração antes do lançamento.
- Hospedagem Railway indisponível na auditoria anterior: ainda faltam publicação do código corrigido, build Linux e testes de domínio, banco, e-mail, login Google e armazenamento no ambiente ativo. Nenhum deploy realizado nesta rodada.
- README histórico marcado como tal; guia de deploy atual em DEPLOY_RAILWAY.md.
- Otimização do CSS e divisão do módulo legado são melhorias posteriores; não foram tratadas como correções obrigatórias de funcionamento.

A geração automática de justificativas permanece interrompida.
