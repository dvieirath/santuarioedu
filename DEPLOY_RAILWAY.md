# Publicação Railway — SantuarioEdu

Revisado em 19/10/2026. O projeto remoto está com trial expirado e os três serviços offline.
Não confundir configuração preparada com aplicação publicada e validada.

## Preparação concluída

- railway.json usa RAILPACK, substituindo Nixpacks.
- Python 3.14.6, alinhado ao ambiente local validado e à série 3.14 usada no CI.
- Build: pip install -r requirements.txt && python manage.py collectstatic --noinput --clear.
- Inicialização: migrações seguidas de Gunicorn na porta fornecida pelo Railway.
- Healthcheck /health/ com tolerância de 120 segundos.
- Procfile não redefine bloqueios de login nem tenta criar administrador automaticamente.
- No painel, DATABASE_URL foi preparada como ${{Postgres.DATABASE_URL}} em lugar de
  ${{Postgres.DATABASE_PUBLIC_URL}}. Está em staged changes, ainda não efetivada em um deploy.

## Verificação local sem serviços externos

Execute:

```powershell
.\venv\Scripts\python.exe scripts/testes/validar_deploy.py
```

O verificador ignora .env e credenciais do ambiente, usa banco/cache/arquivos temporários
em output/deploy_validation e não modifica o banco principal. Valida segurança de produção,
collectstatic, migrações, divergência entre modelos e migrações e quatro rotas via HTTPS simulado.
Logs e results.json permanecem nessa pasta. Não testa PostgreSQL, Redis, R2 ou serviços de e-mail.

## Ao reativar o plano

1. Revisar e versionar o conjunto atual de alterações. Há alterações anteriores nesta cópia,
   inclusive a migração 0058, que não devem ser omitidas ao publicar os modelos correspondentes.
   As mudanças desta preparação ainda são locais; não houve commit, push ou publicação.
2. Publicar o código validado de forma coordenada com a alteração pendente DATABASE_URL.
   Não aplicar o botão Deploy Changes ao código antigo apenas para testar a referência.
3. Confirmar Postgres e Redis online e a referência interna do banco resolvida.
4. Conferir os logs da nova construção. A tentativa de 10/08/2026 falhou sem logs disponíveis;
   não foi possível atribuir nem comprovar a correção da causa histórica.
5. Conferir domínio público e certificados: /health/ precisa retornar 200 e db/cache true.
   Na inspeção, domínio próprio respondeu 403 e endereço railway.app respondeu 404.
6. Fazer backup do PostgreSQL antes de sincronizar dados locais. As justificativas locais
   não são enviadas ao PostgreSQL por um push do código. Não substituir o banco remoto.
7. Testar imagens no R2, cadastro/login, confirmação de e-mail e fluxos usados pelo produto.
   Não presumir que credenciais cadastradas continuam válidas.
8. Verificar política de backups no painel; existência de volume não comprova backup automático.

## Configuração que foi conferida

Repositório dvieirath/santuarioedu, branch main; DEBUG=False; SITE_URL=https://www.santuarioedu.com.br;
ALLOWED_HOSTS e DJANGO_ALLOWED_HOSTS incluem domínio raiz, www, domínio Railway e host do healthcheck.
CSRF_TRUSTED_ORIGINS inclui os três endereços públicos HTTPS. CACHE_URL usa Redis interno.
Há variáveis para R2, e-mail e integrações; seus serviços não foram exercitados nesta preparação.

O painel informa que Config as Code será encerrado em 01/12/2026. As páginas públicas consultadas
continuam documentando railway.json; portanto a atualização para Railpack não resolve, por si só,
a futura migração da configuração. Planejar transferência dos comandos/healthcheck para o painel
ou IaC antes do prazo, preservando os serviços e volumes existentes.

## Limites da validação

Não há Docker disponível neste computador para construir a imagem Linux. A checagem local não
substitui o build Railpack, Gunicorn/Linux, migrações PostgreSQL e testes de integrações em produção.
A geração automática de justificativas permanece encerrada por solicitação do usuário.

Fontes oficiais:
- https://docs.railway.com/config-as-code/reference
- https://railpack.com/languages/python
- https://docs.railway.com/guides/private-networking#using-reference-variables
