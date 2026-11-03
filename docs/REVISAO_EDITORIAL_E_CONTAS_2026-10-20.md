# Revisão editorial e jornada de contas — 20/10/2026

## Correções aplicadas

- Questão 1352: retirada da seleção de questões revisadas (`revisada=0`). O conteúdo era uma rubrica de avaliação com conceitos 0, 1 e 2, sem as perguntas que deveriam ser respondidas. Não foi rejeitada definitivamente.
- Questão 6311: categoria alterada de Direito Constitucional (252) para Administração (339). O enunciado trata de princípios de gestão da qualidade. Referência temática: https://www.iso.org/iso/pub100080.pdf. Essa correção de classificação não constitui validação do gabarito.
- Cadastro: removida a promessa de um código de seis dígitos; a mensagem agora informa apenas que será enviado um código para confirmar o e-mail.

Gabaritos, enunciados, alternativas e justificativas das duas questões foram preservados. A aplicação das correções editoriais conferiu os registros e suas alternativas contra as cópias lidas antes da alteração e verificou que somente os campos previstos mudaram.

Backup: `backups/antes_correcao_editorial_20261020_144054.sqlite3`.
Evidências antes/depois: `output/correcao_editorial_20261020_144054/`.
Verificação de integridade SQLite: OK.

## Validação da jornada de contas

Quatro testes de integração em `quiz/tests/test_jornada_conta.py`, todos aprovados:

1. Cadastro com senhas diferentes preserva o nome informado e não cria usuário.
2. Confirmação de cadastro recusa código inválido e aceita o válido, verificando o endereço e autenticando o usuário.
3. Recuperação de senha permite trocar a senha, invalida a anterior e impede reutilizar o link.
4. Recuperação para endereço desconhecido exibe a mesma confirmação genérica.

Execução isolada com e-mail em memória, sem mensagens reais: `output/jornada_conta_20261020/`.
Também passaram coleta de arquivos estáticos, migrações, verificação de ausência de novas migrações e consultas às páginas básicas realizadas pelo executor.
Os testes não comprovam entrega real de e-mail, OAuth ou funcionamento na hospedagem.

## Pendências editoriais preservadas

Questões 292, 303 e 315 continuam dependendo da prova original e do gabarito oficial para esclarecer alternativas ausentes ou incorretas. Não foram completadas por suposição nem tiveram gabaritos alterados.

O relatório anterior `output/auditoria_banco_20261019_192514/revisao_manual.json` permanece como registro histórico. Este documento registra a resolução de dois dos cinco casos daquele relatório.

## Publicação

Nenhum deploy ou alteração de plano foi realizado. A disponibilidade da hospedagem e os serviços externos ainda precisam de verificação no ambiente de produção.
