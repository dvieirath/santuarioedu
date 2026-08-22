"""Perfil + conta — extraidas de views/_todos.py."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.auth import logout as _auth_logout
from django.utils import timezone

from ..models import (
    Conquista, RespostaUsuario, MetaEstudo, NivelUsuario,
    Perfil, ConcursoPreferido,
)

User = get_user_model()



# Catch-all: importa todos os simbolos de _todos que ainda nao foram extraidos.
# Assim helpers, constantes e funcoes internas continuam acessiveis apos o split.
from ._todos import *  # noqa: F401,F403
from ._todos import _silencioso

@login_required
def perfil(request):
    try:
        perfil = request.user.perfil
    except Perfil.DoesNotExist:
        perfil = Perfil.objects.create(usuario=request.user)

    if request.method == 'POST':
        # Atualizar informações básicas do usuário
        request.user.first_name = request.POST.get('first_name', request.user.first_name)
        request.user.last_name = request.POST.get('last_name', request.user.last_name)
        request.user.email = request.POST.get('email', request.user.email)
        request.user.save()

        # Atualizar informações do perfil
        perfil.telefone = request.POST.get('telefone', perfil.telefone)
        perfil.bio = request.POST.get('bio', perfil.bio)
        
        # Atualizar foto
        if 'foto' in request.FILES:
            perfil.foto = request.FILES['foto']
            
        perfil.save()
        
        # Atualizar senha
        senha = request.POST.get('senha')
        confirmacao_senha = request.POST.get('confirmacao_senha')
        if senha:
            if senha == confirmacao_senha:
                request.user.set_password(senha)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
            else:
                messages.error(request, 'As senhas não coincidem. Tente novamente.')
                return redirect('perfil')

        messages.success(request, 'Perfil atualizado com sucesso!')
        return redirect('perfil')

    return render(request, 'quiz/perfil.html', {'perfil': perfil})

@login_required
def excluir_conta(request):
    """
    Permite ao usuário excluir sua conta permanentemente (LGPD - direito ao esquecimento).
    Exige confirmação digitando o username + senha (allauth) ou confirmação dupla.
    """
    if request.method == 'POST':
        confirmacao = (request.POST.get('confirmacao') or '').strip()
        if confirmacao != request.user.username:
            messages.error(request, 'Confirmação inválida. Digite seu nome de usuário exatamente.')
            return redirect('excluir_conta')

        usuario = request.user
        username = usuario.username

        # Log de auditoria antes de excluir
        try:
            LogSistema.objects.create(
                nivel='AVISO',
                origem='auth',
                mensagem=f'Conta excluída pelo próprio usuário: {username}',
                detalhe=f'IP={request.META.get("REMOTE_ADDR", "")}',
            )
        except Exception:
            _silencioso("view_bloco_7")
        # Faz logout antes de deletar
        from django.contrib.auth import logout
        logout(request)

        # Deleta o usuário — todos os dados em cascata (Simulado, Respostas, etc.)
        usuario.delete()
        messages.success(request, f'Sua conta "{username}" foi excluída permanentemente. Sentiremos sua falta!')
        return redirect('home')

    return render(request, 'quiz/excluir_conta.html')

def perfil_publico(request, username):
    """Perfil público de um usuário (visível a qualquer visitante — compartilhável)."""
    alvo = get_object_or_404(User, username=username)
    respostas = RespostaUsuario.objects.filter(usuario=alvo)
    total = respostas.count()
    acertos = respostas.filter(acertou=True).count()
    pct = round(acertos / total * 100, 1) if total else 0

    conquistas = Conquista.objects.filter(usuario=alvo).order_by('-desbloqueado_em')[:8]

    try:
        meta = alvo.meta
    except MetaEstudo.DoesNotExist:
        meta = None

    # Top disciplinas — 1 query agregada em vez de N por categoria
    from django.db.models import Count, Q
    stats = (respostas
        .values('questao__categoria__nome')
        .annotate(total=Count('id'), acertos=Count('id', filter=Q(acertou=True)))
        .filter(total__gte=5))
    por_cat = [{
        'nome': s['questao__categoria__nome'] or '—',
        'pct':  round(s['acertos'] / s['total'] * 100),
        'total': s['total'],
    } for s in stats]
    por_cat.sort(key=lambda x: x['pct'], reverse=True)

    try:
        perfil_obj = alvo.perfil
    except Perfil.DoesNotExist:
        perfil_obj = None

    sou_eu = request.user == alvo

    return render(request, 'quiz/perfil_publico.html', {
        'alvo': alvo,
        'perfil_obj': perfil_obj,
        'total': total,
        'acertos': acertos,
        'pct': pct,
        'conquistas': conquistas,
        'meta': meta,
        'por_cat': por_cat[:6],
        'sou_eu': sou_eu,
    })

@login_required(login_url='account_login')
def compartilhar_conquista(request, codigo):
    """
    Pagina de share de uma conquista desbloqueada.
    Mesmo padrao do compartilhar_simulado: preview Stories + botoes redes.
    """
    if codigo not in CONQUISTAS_META:
        from django.http import Http404
        raise Http404('Conquista nao encontrada')

    conquista_obj = Conquista.objects.filter(
        usuario=request.user, codigo=codigo,
    ).first()

    if not conquista_obj:
        messages.error(request, 'Voce ainda nao desbloqueou essa conquista.')
        return redirect('conquistas')

    meta_c = CONQUISTAS_META[codigo]
    raridade = meta_c.get('raridade', 'comum')
    raridade_cores = RARIDADE_CORES.get(raridade, RARIDADE_CORES['comum'])

    # Copy adaptativa a raridade
    if raridade == 'lendaria':
        titulo = f'🌈 Desbloqueei uma conquista LENDÁRIA: "{meta_c["label"]}"'
    elif raridade == 'epica':
        titulo = f'💎 Conquista épica desbloqueada: "{meta_c["label"]}"'
    elif raridade == 'rara':
        titulo = f'🏆 Consegui: "{meta_c["label"]}" ({raridade_cores["label"]})'
    else:
        titulo = f'🎯 Desbloqueei: "{meta_c["label"]}"'

    return render(request, 'quiz/compartilhar_conquista.html', {
        'codigo':          codigo,
        'conquista':       conquista_obj,
        'meta':            meta_c,
        'raridade':        raridade,
        'raridade_label':  raridade_cores['label'],
        'titulo_share':    titulo,
        'total_desbloqueadas': Conquista.objects.filter(usuario=request.user).count(),
    })
