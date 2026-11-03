"""APIs relacionadas a questoes — extraidas de views/_todos.py."""
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST, require_http_methods
from django_ratelimit.decorators import ratelimit
from django.http import JsonResponse
from ._todos import _is_staff

from ..models import (
    Questao, Alternativa, AnotacaoUsuario, ComentarioQuestao,
    AvaliacaoQuestao, QuestaoMarcada,
)



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403
from ._todos import _COTA_DIARIA_EXPLICACOES, _is_staff, _silencioso

@login_required
@user_passes_test(lambda u: u.is_staff)
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def api_editar_questao(request, questao_id):
    try:
        data = json.loads(request.body)
        novo_texto = data.get('texto')
        if novo_texto:
            questao = Questao.objects.get(id=questao_id)
            questao.texto = novo_texto
            questao.save()
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Texto vazio'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def api_justificativa_questao(request, questao_id):
    """Gera (ou retorna) justificativa IA para uma questão. Usado no gabarito do simulado."""
    questao = get_object_or_404(Questao, id=questao_id)
    if questao.justificativa:
        return JsonResponse({'justificativa': questao.justificativa, 'gerado_agora': False})
    try:
        resultado = gerar_justificativa_ia(questao)
        if resultado:
            if isinstance(resultado, dict):
                justificativa = (resultado.get('justificativa') or '').strip()
                questao.assunto = resultado.get('assunto', questao.assunto or '')
            else:
                justificativa = str(resultado).strip()
            if not justificativa:
                return JsonResponse(
                    {'erro': 'A IA não retornou uma explicação. Tente novamente em alguns instantes.'},
                    status=503,
                )
            questao.justificativa = justificativa
            questao.save()
            return JsonResponse({'justificativa': questao.justificativa, 'gerado_agora': True})
    except Exception as e:
        return JsonResponse({'erro': str(e)}, status=500)
    return JsonResponse({'erro': 'Não foi possível gerar o comentário.'}, status=500)

@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def api_admin_questao(request, questao_id):
    """Retorna dados de uma questão como JSON para popular o modal de edição."""
    from django.shortcuts import get_object_or_404
    questao = get_object_or_404(Questao, id=questao_id)
    alternativas = list(questao.alternativa_set.values('id', 'texto', 'correta'))
    return JsonResponse({
        'id': questao.id,
        'texto': questao.texto,
        'tipo': questao.tipo,
        'categoria_id': questao.categoria_id,
        'justificativa': questao.justificativa or '',
        'alternativas': alternativas,
    })

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def api_avaliar_questao(request, questao_id):
    """
    AJAX POST: { "dificuldade": 1|2|3 }
    Salva/atualiza a avaliação de dificuldade e ajusta o SRS.
    """
    questao = get_object_or_404(Questao, id=questao_id)
    try:
        data = json.loads(request.body)
        dif  = int(data.get('dificuldade', 2))
        if dif not in (1, 2, 3):
            return JsonResponse({'erro': 'Dificuldade inválida'}, status=400)
    except Exception:
        return JsonResponse({'erro': 'JSON inválido'}, status=400)

    AvaliacaoQuestao.objects.update_or_create(
        usuario=request.user, questao=questao,
        defaults={'dificuldade': dif},
    )

    # Ajusta SRS: fácil → intervalo maior, difícil → menor
    hoje = timezone.localdate()
    srs, _ = RevisaoEspacada.objects.get_or_create(
        usuario=request.user, questao=questao,
        defaults={'proxima_revisao': hoje},
    )
    # Mapeia dificuldade percebida para acertou no SM-2
    # Fácil=True (aumenta intervalo), Difícil=False (reinicia)
    srs.atualizar(acertou=(dif == 1))

    labels = {1: 'Fácil', 2: 'Médio', 3: 'Difícil'}
    return JsonResponse({
        'status': 'ok',
        'dificuldade': dif,
        'label': labels[dif],
        'proxima_revisao': str(srs.proxima_revisao),
    })

@login_required
@require_POST
@ratelimit(key='user', rate='10/m', method='POST', block=True)
def api_explicar_questao(request):
    """
    Gera explicação personalizada para uma questão errada.
    Body JSON: { questao_id, alternativa_id (opcional) }
    """
    try:
        body      = json.loads(request.body)
        questao_id = int(body.get('questao_id', 0))
        alt_id     = body.get('alternativa_id')
    except Exception:
        return JsonResponse({'erro': 'Payload inválido'}, status=400)

    # --- Cota diária ---
    hoje = timezone.localdate()
    usadas_hoje = ExplicacaoIA.objects.filter(
        usuario=request.user,
        criado_em__date=hoje,
    ).count()
    if usadas_hoje >= _COTA_DIARIA_EXPLICACOES:
        return JsonResponse({
            'erro': f'Limite de {_COTA_DIARIA_EXPLICACOES} explicações/dia atingido. Volte amanhã!',
            'cota_esgotada': True,
        }, status=429)

    # --- Busca questão ---
    try:
        questao = Questao.objects.select_related('categoria').get(id=questao_id)
    except Questao.DoesNotExist:
        return JsonResponse({'erro': 'Questão não encontrada'}, status=404)

    # --- Alternativa escolhida ---
    alt_obj = None
    alt_escolhida_txt = '(não informada)'
    if alt_id:
        try:
            alt_obj = Alternativa.objects.get(id=alt_id, questao=questao)
            alt_escolhida_txt = alt_obj.texto
        except Alternativa.DoesNotExist:
            pass

    # --- Alternativa correta ---
    alt_correta = questao.alternativa_set.filter(correta=True).first()
    alt_correta_txt = alt_correta.texto if alt_correta else '(gabarito não cadastrado)'

    # --- Rank do usuário ---
    rank = 'Cadete'
    try:
        rank = request.user.nivel.rank_nome
    except Exception:
        _silencioso("view_bloco_11")
    # --- Verifica cache: mesma questão + mesma alt + mesmo dia ---
    cache = ExplicacaoIA.objects.filter(
        usuario=request.user,
        questao=questao,
        alt_escolhida=alt_obj,
        criado_em__date=hoje,
    ).first()
    if cache:
        return JsonResponse({
            'texto':          cache.texto,
            'explicacao_id':  cache.id,
            'util':           cache.util,
            'usadas_hoje':    usadas_hoje,
            'cota_max':       _COTA_DIARIA_EXPLICACOES,
        })

    # --- Gera nova explicação ---
    texto = ai_explicar_erro(
        questao_texto    = questao.texto,
        categoria        = questao.categoria.nome,
        alt_escolhida    = alt_escolhida_txt,
        alt_correta      = alt_correta_txt,
        rank_usuario     = rank,
        usuario          = request.user,
    )

    exp = ExplicacaoIA.objects.create(
        usuario        = request.user,
        questao        = questao,
        alt_escolhida  = alt_obj,
        texto          = texto,
        rank_no_momento= rank,
    )

    return JsonResponse({
        'texto':         texto,
        'explicacao_id': exp.id,
        'util':          None,
        'usadas_hoje':   usadas_hoje + 1,
        'cota_max':      _COTA_DIARIA_EXPLICACOES,
    })

@login_required
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def api_feedback_explicacao(request, explicacao_id):
    """Salva feedback 👍/👎 de uma explicação IA."""
    try:
        exp = ExplicacaoIA.objects.get(id=explicacao_id, usuario=request.user)
    except ExplicacaoIA.DoesNotExist:
        return JsonResponse({'erro': 'Não encontrada'}, status=404)
    try:
        body = json.loads(request.body)
        exp.util = bool(body.get('util'))
        exp.save(update_fields=['util'])
    except Exception:
        return JsonResponse({'erro': 'Inválido'}, status=400)
    return JsonResponse({'ok': True})

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='60/m', method='POST', block=True)
def api_marcar_questao(request, questao_id):
    """Toggle marcar/desmarcar uma questão pra revisar depois.
    Rate limit: 60/min (evita spam)."""
    from ..models import QuestaoMarcada, Questao
    q = get_object_or_404(Questao, id=questao_id)
    marca, criado = QuestaoMarcada.objects.get_or_create(
        usuario=request.user, questao=q,
        defaults={'motivo': (request.POST.get('motivo') or '')[:120]},
    )
    if not criado:
        marca.delete()
        return JsonResponse({'marcada': False})
    return JsonResponse({'marcada': True, 'id': marca.id})

@login_required(login_url='account_login')
@require_http_methods(['GET', 'POST'])
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def api_anotacao(request, questao_id):
    """GET: le anotacao. POST: salva/deleta. Bloqueia outros metodos (PUT/DELETE
    acidentais). Prefetch do browser usa GET, entao mantido — mas so leitura.
    Rate limit: 30 anotacoes/min por user (evita spam)."""
    questao = get_object_or_404(Questao, id=questao_id)
    if request.method == 'POST':
        try:
            data  = json.loads(request.body)
        except ValueError:
            return JsonResponse({'status': 'error', 'msg': 'JSON invalido'}, status=400)
        texto = data.get('texto', '').strip()
        if texto:
            obj, _ = AnotacaoUsuario.objects.update_or_create(
                usuario=request.user, questao=questao,
                defaults={'texto': texto}
            )
        else:
            AnotacaoUsuario.objects.filter(usuario=request.user, questao=questao).delete()
        return JsonResponse({'status': 'ok'})
    # GET
    try:
        obj = AnotacaoUsuario.objects.get(usuario=request.user, questao=questao)
        return JsonResponse({'texto': obj.texto})
    except AnotacaoUsuario.DoesNotExist:
        return JsonResponse({'texto': ''})

@login_required(login_url='account_login')
def api_comentarios(request, questao_id):
    """
    GET  → lista comentários da questão
    POST → cria novo comentário
    """
    questao = get_object_or_404(Questao, id=questao_id)

    if request.method == 'POST':
        try:
            data  = json.loads(request.body)
            texto = data.get('texto', '').strip()
        except Exception:
            return JsonResponse({'erro': 'JSON inválido'}, status=400)

        if not texto or len(texto) < 3:
            return JsonResponse({'erro': 'Comentário muito curto.'}, status=400)
        if len(texto) > 1000:
            return JsonResponse({'erro': 'Comentário muito longo (máx 1000 chars).'}, status=400)

        c = ComentarioQuestao.objects.create(
            usuario=request.user, questao=questao, texto=texto
        )
        return JsonResponse({
            'id':        c.id,
            'texto':     c.texto,
            'usuario':   c.usuario.username,
            'criado_em': c.criado_em.strftime('%d/%m/%Y %H:%M'),
            'upvotes':   0,
        }, status=201)

    # GET
    comentarios = ComentarioQuestao.objects.filter(questao=questao).select_related('usuario')[:50]
    meus_upvotes = set(
        UpvoteComentario.objects.filter(
            usuario=request.user,
            comentario__in=comentarios
        ).values_list('comentario_id', flat=True)
    )
    data = [
        {
            'id':        c.id,
            'texto':     c.texto,
            'usuario':   c.usuario.username,
            'criado_em': c.criado_em.strftime('%d/%m/%Y %H:%M'),
            'upvotes':   c.upvotes,
            'meu_upvote': c.id in meus_upvotes,
            'sou_autor':  c.usuario_id == request.user.id,
        }
        for c in comentarios
    ]
    return JsonResponse({'comentarios': data})

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='60/m', method='POST', block=True)
def api_comentario_upvote(request, comentario_id):
    """Toggle upvote num comentário."""
    c = get_object_or_404(ComentarioQuestao, id=comentario_id)
    obj, criado = UpvoteComentario.objects.get_or_create(
        usuario=request.user, comentario=c
    )
    if criado:
        c.upvotes = c.upvotes + 1
        c.save(update_fields=['upvotes'])
        return JsonResponse({'upvotes': c.upvotes, 'ativo': True})
    else:
        obj.delete()
        c.upvotes = max(0, c.upvotes - 1)
        c.save(update_fields=['upvotes'])
        return JsonResponse({'upvotes': c.upvotes, 'ativo': False})

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='30/m', method='POST', block=True)
def api_comentario_deletar(request, comentario_id):
    """Deleta próprio comentário."""
    c = get_object_or_404(ComentarioQuestao, id=comentario_id, usuario=request.user)
    c.delete()
    return JsonResponse({'status': 'ok'})
