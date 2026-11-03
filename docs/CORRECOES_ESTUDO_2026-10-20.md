# Correções dos fluxos de estudo — 20/10/2026

## Concluído localmente

- Contagens em /estudar/ incluem somente questões revisadas e não rejeitadas, inclusive no progresso do aluno.
- Quiz de uma categoria principal inclui suas subcategorias, em coerência com o total apresentado.
- Envio de resposta no quiz recusa questões pendentes ou rejeitadas.
- Ano e identificadores inválidos não provocam erro de conversão no quiz; parâmetros de categoria inválidos são tratados.
- Percurso da árvore de categorias possui proteção contra ciclos, evitando travamento caso exista hierarquia inconsistente.
- Cobertura de simulados por edital considera apenas questões liberadas.
- Abrir o resultado de uma questão sem justificativa não dispara geração automática. A página informa que ainda não há explicação revisada. Outros recursos de IA acionados explicitamente não foram removidos.
- Simulado recusa alternativa inválida ou de outra questão sem avançar nem finalizar silenciosamente. Finalização voluntária com resposta em branco continua permitida.

## Verificação

A validação anterior terminou com 114 testes aprovados (output/auditoria_aplicacao/test.log). Após a correção adicional do simulado, 27 testes relacionados a disponibilidade e segurança passaram (output/validacao_retomada_20261020/test.log). Esses 27 incluem testes já existentes; os números não devem ser somados como total de casos únicos.

Banco temporário e e-mail em memória nos testes, sem credenciais externas. Nenhuma justificativa foi gerada e o banco real não foi alterado por esta auditoria.

Servidor local iniciado novamente; /health/, /accounts/signup/ e /testar/ responderam HTTP 200.

## Banco de questões

Levantamento de leitura consistente em output/auditoria_banco_20261019_192514/:
- 13.755 questões, 8.387 liberadas, 233 rejeitadas.
- 6.095 liberadas sem justificativa.
- Nenhum grupo de enunciados inteiramente repetidos após normalização de espaços e caixa. Isso não descarta duplicatas aproximadas.
- 337 liberadas com sinal de referência a texto ausente e 179 com sinal de referência a imagem ausente. São heurísticas, não conclusões; um item pode ter vários sinais.
- Casos 292, 303 e 315 precisam de conferência das alternativas na prova original.
- Caso 1352 contém rubrica de correção, não as perguntas referidas.
- Caso 6311 trata de gestão da qualidade dentro da categoria Direito Constitucional.

Os cinco casos estão detalhados em revisao_manual.json. Não foram alterados gabaritos, categorias ou aprovações. As pendências continuam pendentes; este relatório não representa revisão editorial completa.

## Próximas etapas

Conferir os casos editoriais com provas originais, ampliar a revisão dos fluxos de cadastro/recuperação e da experiência móvel. A publicação e os testes de serviços externos em produção continuam dependentes de hospedagem disponível. Nenhum deploy foi feito.
