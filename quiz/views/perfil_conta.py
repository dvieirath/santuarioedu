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
        from ..forms import PerfilForm
        from django.contrib.auth.forms import PasswordChangeForm
        from django.contrib.auth import update_session_auth_hash
        from django.db import transaction

        # E-mail changes must go through allauth and ownership verification.
        email = request.POST.get('email', request.user.email).strip()
        if email != request.user.email:
            messages.error(request, 'Use Gerenciar e-mail para confirmar o novo endereço.')
            return redirect('perfil')
        form = PerfilForm(request.POST, request.FILES, instance=perfil)
        password_form = None
        if request.POST.get('senha'):
            password_form = PasswordChangeForm(request.user, {
                'old_password': request.POST.get('senha_atual', ''),
                'new_password1': request.POST.get('senha', ''),
                'new_password2': request.POST.get('confirmacao_senha', ''),
            })
        valid = form.is_valid()
        if password_form is not None:
            valid = password_form.is_valid() and valid
        if not valid:
            for current_form in (form, password_form):
                if current_form is not None:
                    for errors in current_form.errors.values():
                        for error in errors:
                            messages.error(request, error)
            return redirect('perfil')
        with transaction.atomic():
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.save(update_fields=['first_name', 'last_name'])
            form.save()
            if password_form is not None:
                password_form.save()
                update_session_auth_hash(request, request.user)
        messages.success(request, 'Perfil atualizado com sucesso!')
        return redirect('perfil')

    # concurso_pref (opcional) + choices pro select do "Meu concurso alvo"
    concurso_pref = ConcursoPreferido.objects.filter(usuario=request.user).first()
    return render(request, 'quiz/perfil.html', {
        'perfil':            perfil,
        'concurso_pref':     concurso_pref,
        'concursos_choices': ConcursoPreferido.CONCURSOS,
    })

@login_required
def alterar_concurso_pref(request):
    """
    Troca ou remove o concurso alvo do usuario.

    POST params:
      acao='salvar' (default) ou 'remover'
      concurso     = slug de ConcursoPreferido.CONCURSOS (ex: 'prf')
      horas_por_dia= int 1..24
      data_prova_esperada = ISO date opcional
    """
    if request.method != 'POST':
        return redirect('perfil')

    acao = (request.POST.get('acao') or 'salvar').strip()

    if acao == 'remover':
        ConcursoPreferido.objects.filter(usuario=request.user).delete()
        messages.success(request, 'Concurso removido do seu perfil.')
        return redirect('perfil')

    concurso = (request.POST.get('concurso') or '').strip().lower()
    validos = dict(ConcursoPreferido.CONCURSOS).keys()
    if concurso not in validos:
        messages.error(request, 'Concurso inválido — selecione uma opção da lista.')
        return redirect('perfil')

    try:
        horas = max(1, min(24, int(request.POST.get('horas_por_dia') or 2)))
    except (TypeError, ValueError):
        horas = 2

    data_prova = (request.POST.get('data_prova_esperada') or '').strip() or None

    cp, _ = ConcursoPreferido.objects.update_or_create(
        usuario=request.user,
        defaults={
            'concurso':            concurso,
            'horas_por_dia':       horas,
            'data_prova_esperada': data_prova,
        },
    )
    messages.success(request, f'Concurso alvo atualizado para {cp.get_concurso_display()}.')
    return redirect('perfil')


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
