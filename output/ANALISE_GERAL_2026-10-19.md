# Análise geral — SantuarioEdu — 19/10/2026

## Parecer

Boa base para um beta controlado, mas ainda não pronta para lançamento público amplo.
A prioridade é confiança no conteúdo, consistência da comunicação e operação de produção.
Não faltam recursos: falta concluir e comprovar o caminho principal do aluno.

## Escopo e limites

Inspeção visual local em viewport estreito; página inicial, demo e cadastro. Leitura de código,
consultas somente leitura ao SQLite local, testes automatizados em banco descartável sem .env,
e inspeção do Railway nesta conversa. Não houve avaliação completa de cada questão, teste de
carga, auditoria jurídica, pentest ou testes reais de Google/e-mail/IA/R2. Os números são locais,
não do PostgreSQL do Railway. Não foram alteradas funcionalidades nesta análise.

## O que está bom

- Identidade visual consistente, boa legibilidade e hierarquia nas telas públicas observadas.
- Demo sem cadastro oferece acesso rápido e tem progresso e feedback claros.
- Núcleo de estudo abrangente: questões, simulados, revisão espaçada, erros, metas e progresso.
- Autenticação e testes de acesso entre usuários; testes específicos de senhas, uploads,
  partidas e cache privado. Ter testes é evidência de cuidado, não garantia de segurança absoluta.
- Banco local: 13.755 questões; 8.387 marcadas revisadas. Nenhuma revisada e não rejeitada
  apresentou menos de duas alternativas ou número de corretas diferente de uma na consulta estrutural.
- Pipeline local de preparação passou: segurança Django, coleta de estáticos, migrações,
  consistência de modelos e páginas inicial/health/login/robots.
- Estrutura Railway já contém web, PostgreSQL, Redis e volumes; produção usa DEBUG=False.

## Problemas prioritários

1. Confiança editorial: 6.095 das 8.387 revisadas (72,7%) não têm justificativa armazenada.
   Isso não prova gabarito incorreto, mas enfraquece a proposta de ensinar pelo erro.
   Na demo, questão 6311 de gestão da qualidade foi apresentada em Direito Constitucional.
   É um erro de categorização confirmado; não foi avaliado o gabarito técnico desse item.
2. Mensagem comercial contraditória: a mesma landing diz 'Tudo aqui é grátis. Pra sempre.',
   'Sem plano PRO', 'A partir de R$ 14,90/mês', pagamento Mercado Pago e cancelar assinatura.
   quiz/limits.py confirma modo gratuito; falta remover a comunicação antiga.
3. A demo oculta toda a explicação e pede cadastro. O usuário não experimenta o diferencial
   educacional anunciado. Melhor mostrar ao menos uma resolução completa previamente conferida.
4. Cadastro real em account/signup.html não apresenta links de termos/privacidade junto ao
   formulário. O template antigo registration/cadastro.html tem aceite, mas /cadastro/ redireciona
   para o allauth. Unificar a experiência e verificar o registro necessário segundo a política adotada.
5. Texto de privacidade menciona Gemini, mas o código e ambiente incluem outros provedores.
   Revisar correspondência entre o que é informado, o que é enviado e os serviços efetivamente usados.
   Este é um achado de consistência operacional, não um parecer de conformidade legal.
6. Muitas funcionalidades competem por atenção. Priorizar a jornada: escolher concurso,
   responder, entender o erro, revisar e visualizar evolução. Recursos sociais e preditivos
   podem entrar depois da validação desse percurso com usuários.
7. Dívida técnica: views/_todos.py ainda tem cerca de 5.753 linhas, com imports curinga nos
   módulos. A separação por domínio está incompleta e aumenta risco de regressões.
8. Tailwind é processado no navegador; há permissões unsafe-inline/unsafe-eval na CSP.
   Compilar CSS e reduzir exceções gradualmente, sem confundir isso com vulnerabilidade comprovada.
9. Documentação antiga ainda descreve planos pagos, Nixpacks e Python antigos. O roteiro de
   deploy foi revisado, mas README e outros documentos precisam de reconciliação.

## Antes de colocar no ar

P0 — Resolver plano ou hospedagem; publicar código atual coordenado com a conexão privada
pendente; obter build saudável e HTTP 200 /health/ com banco/cache disponíveis; acertar domínio/HTTPS;
fazer backup com restauração testada; planejar sincronização local/produção sem sobrescrever usuários.

P0 — Retirar contradições comerciais; selecionar conteúdo de lançamento com categoria, enunciado,
imagem, gabarito e explicação conferidos; corrigir especialmente a demo. Não é necessário esperar
justificativas de todo o acervo para lançar um subconjunto confiável. Geração segue interrompida.

P0 — Exercitar cadastro, confirmação de e-mail, login, recuperação de senha, sessão de questões,
simulado, revisão e exclusão de conta em produção; validar arquivos R2 e falhas/quota dos provedores.

P1 — Garantir alertas de erro, política de backup, contato de suporte funcional e limite operacional
para consumo de IA. Há rate limits em endpoints, mas isso não equivale a orçamento global controlado.

P1 — Testar desktop/mobile, teclado, leitores de tela e carga compatível com o público inicial.
O visual estreito observado é bom, mas não comprova toda a responsividade ou acessibilidade.

## Sequência recomendada

1. Coerência da landing/cadastro e curadoria de um conjunto inicial de questões.
2. Publicação, restauração de backup e testes reais das integrações.
3. Beta com grupo pequeno de estudantes; observar conclusão de sessões, erros e retorno para revisão.
4. Ampliar conteúdo e funcionalidades com base no uso, sem prometer cobertura equivalente em 7 concursos.

## Evidências

- output/deploy_validation/results.json: preparação de produção validada na rodada anterior.
- output/auditoria_aplicacao/test.log: suíte principal desta análise.
- Testes frontend: 5/5 passaram (cache privado, recursos públicos e sintaxe de partidas).
- DEPLOY_RAILWAY.md: configuração e pendências da hospedagem.

A primeira execução da suíte ocorreu antes da coleta de estáticos e falhou por manifest ausente.
Essa falha de preparação não deve ser atribuída ao produto; a execução final ocorre após collectstatic.

Resultado final: 100/100 testes Django passaram após preparar os estáticos. Migrações, consistência de modelos e quatro rotas também passaram. Somados aos 5 testes frontend, foram 105 testes aprovados. Integrações externas e operação Linux continuam sem validação real.
