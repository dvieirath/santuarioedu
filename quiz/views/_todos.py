from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm as _BaseUserCreationForm
from django import forms as _dj_forms


class UserCreationForm(_BaseUserCreationForm):
    """Estende UserCreationForm exigindo email valido + unico."""
    email = _dj_forms.EmailField(
        required=True,
        label='Email',
        help_text='Usaremos para confirmacao de conta e nota fiscal.',
    )

    class Meta(_BaseUserCreationForm.Meta):
        fields = ('username', 'email')

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        from django.contrib.auth.models import User as _User
        if _User.objects.filter(email__iexact=email).exists():
            raise _dj_forms.ValidationError('Ja existe uma conta com esse email.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user
from django.contrib.auth import login
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django_ratelimit.decorators import ratelimit
from django.utils import timezone
from django.db.models import Count, Q, Avg, Sum, F, FloatField
from django.db.models.functions import TruncDate, TruncWeek, Cast
from django.db import models
from datetime import timedelta
import json
from django.contrib.auth.models import User
from ..models import (Questao, Alternativa, RespostaUsuario, MaterialEstudo,
                     Categoria, Perfil, Simulado, RespostaSimulado,
                     QuestaoFavorita, MetaEstudo, Conquista, AnotacaoUsuario,
                     RevisaoEspacada, SessaoEstudo, PushSubscription,
                     Flashcard, DesafioResultado,
                     ResumoIA, GrupoEstudo, MembroGrupo, Notificacao,
                     MetaAvancada, ComentarioQuestao, UpvoteComentario,
                     QuestaoDodia, AvaliacaoQuestao,
                     NivelUsuario,
                     PlanoEstudoDinamico,
                     PreferenciasNotificacao,
                     ExplicacaoIA,
                     RelatorioSimuladoIA,
                     PrevisaoTopico,
                     Duelo, RespostaDuelo,
                     SimuladoColetivo, ParticipanteColetivo, RespostaColetivo,
                     LogSistema)  # PlanoUsuario, CupomDesconto removidos
from ..ai_service import gerar_justificativa_ia, ai_tutor_responder, ai_resumo_disciplina, ai_plano_estudos, ai_explicar_erro, ai_insight_banca, ai_analisar_simulado, ai_gerar_questoes, ai_prever_topicos
try:
    from allauth.socialaccount.models import SocialAccount
    _has_allauth = True
except ImportError:
    _has_allauth = False

# ─── CONQUISTAS ──────────────────────────────────────────────────────────────

CONQUISTAS_META = {
    # Volume
    'primeiro_acerto':   {'label': 'Primeiro Acerto',    'emoji': '🥇', 'desc': 'Acertou sua primeira questão!',      'categoria': 'volume', 'raridade': 'comum'},
    'dez_questoes':      {'label': 'Primeiros Passos',   'emoji': '🌱', 'desc': '10 questões respondidas',            'categoria': 'volume', 'raridade': 'comum'},
    'centenario':        {'label': 'Centenário',         'emoji': '💯', 'desc': '100 questões respondidas',           'categoria': 'volume', 'raridade': 'incomum'},
    'quinhentos':        {'label': '500 Questões',       'emoji': '🚀', 'desc': '500 questões respondidas',           'categoria': 'volume', 'raridade': 'rara'},
    'milenar':           {'label': 'Milenar',            'emoji': '⚡', 'desc': '1000 questões respondidas',          'categoria': 'volume', 'raridade': 'epica'},
    # Streak
    'streak_3':          {'label': 'Constância',         'emoji': '✨', 'desc': '3 dias de estudo seguidos',          'categoria': 'streak', 'raridade': 'comum'},
    'streak_7':          {'label': 'Semana em Chamas',   'emoji': '🔥', 'desc': '7 dias de estudo seguidos',          'categoria': 'streak', 'raridade': 'incomum'},
    'streak_14':         {'label': 'Duas Semanas',       'emoji': '🌪️', 'desc': '14 dias de estudo seguidos',         'categoria': 'streak', 'raridade': 'rara'},
    'streak_30':         {'label': 'Mês Dedicado',       'emoji': '🌟', 'desc': '30 dias de estudo seguidos',         'categoria': 'streak', 'raridade': 'epica'},
    'streak_100':        {'label': 'Lenda Persistente',  'emoji': '💎', 'desc': '100 dias de estudo seguidos',        'categoria': 'streak', 'raridade': 'lendaria'},
    # Precisao
    'atirador':          {'label': 'Atirador de Elite',  'emoji': '🎯', 'desc': '90%+ de acertos em 50+ questões',    'categoria': 'precisao', 'raridade': 'incomum'},
    'sniper':            {'label': 'Sniper',             'emoji': '🏹', 'desc': '95%+ de acertos em 100+ questões',   'categoria': 'precisao', 'raridade': 'rara'},
    'perfeicionista':    {'label': 'Perfeccionista',     'emoji': '🔷', 'desc': '100% de acertos em 20+ questões',    'categoria': 'precisao', 'raridade': 'epica'},
    # Simulados
    'primeiro_simulado': {'label': 'Estreante',          'emoji': '🎬', 'desc': 'Fez seu primeiro simulado',          'categoria': 'simulado', 'raridade': 'comum'},
    'simuladista':       {'label': 'Simuladista',        'emoji': '🏅', 'desc': '5 simulados completos realizados',   'categoria': 'simulado', 'raridade': 'incomum'},
    'veterano_simulado': {'label': 'Veterano de Provas', 'emoji': '🎖️', 'desc': '25 simulados completos realizados',  'categoria': 'simulado', 'raridade': 'rara'},
    'simulado_perfeito': {'label': 'Prova Perfeita',     'emoji': '👑', 'desc': 'Acertou 100% em um simulado',        'categoria': 'simulado', 'raridade': 'epica'},
    # Diversidade
    'enciclopedia':      {'label': 'Enciclopédia',       'emoji': '📚', 'desc': 'Respondeu em todas as matérias',     'categoria': 'diversidade', 'raridade': 'epica'},
    'generalista':       {'label': 'Generalista',        'emoji': '🌐', 'desc': 'Respondeu em 5+ matérias diferentes','categoria': 'diversidade', 'raridade': 'incomum'},
    'especialista':      {'label': 'Especialista',       'emoji': '🔬', 'desc': '100+ questões em uma única matéria', 'categoria': 'diversidade', 'raridade': 'rara'},
    # Horarios
    'madrugador':        {'label': 'Madrugador',         'emoji': '🌅', 'desc': 'Respondeu questão antes das 6h',     'categoria': 'horario', 'raridade': 'incomum'},
    'noturno':           {'label': 'Coruja Noturna',     'emoji': '🌙', 'desc': 'Respondeu questão após 23h',          'categoria': 'horario', 'raridade': 'incomum'},
    # Social
    'primeiro_duelo':    {'label': 'Primeiro Duelo',     'emoji': '⚔️', 'desc': 'Participou do seu primeiro duelo',    'categoria': 'social', 'raridade': 'comum'},
    'duelista':          {'label': 'Duelista',           'emoji': '🛡️', 'desc': 'Participou de 10+ duelos',            'categoria': 'social', 'raridade': 'rara'},
    # Meta
    'colecionador':      {'label': 'Colecionador',       'emoji': '🏆', 'desc': 'Desbloqueou 5+ conquistas',           'categoria': 'meta', 'raridade': 'rara'},
    'lenda':             {'label': 'Lenda',              'emoji': '🌈', 'desc': 'Desbloqueou 15+ conquistas',          'categoria': 'meta', 'raridade': 'lendaria'},
}

# Mapa raridade -> cor (usado pra badges no template)
RARIDADE_CORES = {
    'comum':     {'bg': 'bg-slate-100',   'border': 'border-slate-300',   'text': 'text-slate-700',   'label': 'Comum'},
    'incomum':   {'bg': 'bg-emerald-50',  'border': 'border-emerald-300', 'text': 'text-emerald-700', 'label': 'Incomum'},
    'rara':      {'bg': 'bg-blue-50',     'border': 'border-blue-300',    'text': 'text-blue-700',    'label': 'Rara'},
    'epica':     {'bg': 'bg-violet-50',   'border': 'border-violet-300',  'text': 'text-violet-700',  'label': 'Épica'},
    'lendaria':  {'bg': 'bg-amber-50',    'border': 'border-amber-400',   'text': 'text-amber-700',   'label': 'Lendária'},
}


def verificar_conquistas(user):
    """Verifica condições e desbloqueia conquistas. Retorna lista de novos códigos desbloqueados."""
    ja_tem = set(Conquista.objects.filter(usuario=user).values_list('codigo', flat=True))
    novas  = []

    def _ganhar(codigo):
        if codigo not in ja_tem:
            Conquista.objects.get_or_create(usuario=user, codigo=codigo)
            novas.append(codigo)

    respostas = RespostaUsuario.objects.filter(usuario=user)
    total   = respostas.count()
    acertos = respostas.filter(acertou=True).count()

    # ── Volume ──
    if acertos >= 1:
        _ganhar('primeiro_acerto')
    if total >= 10:
        _ganhar('dez_questoes')
    if total >= 100:
        _ganhar('centenario')
    if total >= 500:
        _ganhar('quinhentos')
    if total >= 1000:
        _ganhar('milenar')

    # ── Precisão ──
    if total >= 50 and total > 0 and (acertos / total) >= 0.90:
        _ganhar('atirador')
    if total >= 100 and (acertos / total) >= 0.95:
        _ganhar('sniper')
    if total >= 20 and acertos == total:  # 100%
        _ganhar('perfeicionista')

    # ── Streak ──
    try:
        meta = user.meta
        if meta.streak_atual >= 3:
            _ganhar('streak_3')
        if meta.streak_atual >= 7:
            _ganhar('streak_7')
        if meta.streak_atual >= 14:
            _ganhar('streak_14')
        if meta.streak_atual >= 30:
            _ganhar('streak_30')
        if meta.streak_atual >= 100:
            _ganhar('streak_100')
    except Exception:
        _silencioso("view_bloco_1")
    # ── Diversidade ──
    cats_respondidas_qs = respostas.values('questao__categoria').distinct()
    cats_respondidas = cats_respondidas_qs.count()
    total_cats = Categoria.objects.count()
    if total_cats > 0 and cats_respondidas >= total_cats:
        _ganhar('enciclopedia')
    if cats_respondidas >= 5:
        _ganhar('generalista')

    # Especialista: 100+ questoes em uma unica matéria
    from django.db.models import Count
    top_cat = (respostas.values('questao__categoria')
               .annotate(n=Count('id')).order_by('-n').first())
    if top_cat and top_cat['n'] >= 100:
        _ganhar('especialista')

    # ── Simulados ──
    sims = Simulado.objects.filter(usuario=user, finalizado=True).count()
    if sims >= 1:
        _ganhar('primeiro_simulado')
    if sims >= 5:
        _ganhar('simuladista')
    if sims >= 25:
        _ganhar('veterano_simulado')

    # Simulado perfeito: 100% em algum simulado
    try:
        from ..models import RespostaSimulado
        # simulado com pelo menos 10 respostas e todas certas
        sims_finalizados = Simulado.objects.filter(usuario=user, finalizado=True)
        for s in sims_finalizados:
            resp = RespostaSimulado.objects.filter(simulado=s)
            n = resp.count()
            if n >= 10 and resp.filter(alternativa__correta=True).count() == n:
                _ganhar('simulado_perfeito')
                break
    except Exception:
        _silencioso("view_bloco_2")
    # ── Horários ──
    try:
        # Django extract() por hora (ORM cross-db)
        from django.db.models.functions import ExtractHour
        horas = respostas.annotate(h=ExtractHour('data')).values_list('h', flat=True).distinct()
        if any(h is not None and h < 6 for h in horas):
            _ganhar('madrugador')
        if any(h is not None and h >= 23 for h in horas):
            _ganhar('noturno')
    except Exception:
        _silencioso("view_bloco_3")
    # ── Duelos ──
    try:
        from ..models import Duelo
        # Duelo tem jogador1/jogador2 (varia por versao); tenta ambos
        n_duelos = 0
        try:
            n_duelos = Duelo.objects.filter(jogador1=user).count() + Duelo.objects.filter(jogador2=user).count()
        except Exception:
            _silencioso("view_bloco_4")
        if n_duelos >= 1:
            _ganhar('primeiro_duelo')
        if n_duelos >= 10:
            _ganhar('duelista')
    except Exception:
        _silencioso("view_bloco_5")
    # ── Meta-conquistas (executar por ULTIMO — depende das outras) ──
    total_conquistas_atual = len(ja_tem) + len(novas)
    if total_conquistas_atual >= 5:
        _ganhar('colecionador')
    if total_conquistas_atual >= 15:
        _ganhar('lenda')

    # Disparar notificação in-app para cada conquista nova
    for codigo in novas:
        try:
            meta_c = CONQUISTAS_META.get(codigo, {})
            Notificacao.objects.create(
                usuario=user,
                tipo='conquista',
                titulo=f'{meta_c.get("emoji","🏆")} {meta_c.get("label", codigo)}',
                mensagem=meta_c.get('desc', ''),
                link='/conquistas/',
            )
        except Exception:
            _silencioso("view_bloco_6")
    return novas


@login_required(login_url='account_login')
def listar_materiais(request):
    materiais = MaterialEstudo.objects.all()
    return render(request, 'quiz/materiais.html', {'materiais': materiais})


@login_required(login_url='account_login')
def dashboard(request):
    """Dashboard blindado: cada bloco tem try/except pra nunca crashar a pagina.
    Se algo falha, seta valor default e loga em LogSistema pra investigar depois."""
    import json as _json
    from ..models import LogSistema

    def _log_falha(bloco, exc):
        try:
            LogSistema.objects.create(
                nivel='ERRO', origem='dashboard',
                mensagem=f'Bloco "{bloco}" falhou pra {request.user.username}',
                detalhe=f'{type(exc).__name__}: {exc}',
                usuario=request.user,
            )
        except Exception:
            pass  # nunca deixa o log matar a resposta

    # ── Defaults seguros ─────────────────────────────────────────────
    ctx = {
        'total_respondidas': 0, 'total_acertos': 0, 'aproveitamento': 0,
        'foto_google': '', 'meta': None, 'questoes_hoje': 0, 'pct_meta': 0,
        'ultimos_simulados': [], 'melhores': [], 'piores': [], 'srs_pendentes': 0,
        'uso_plano': None, 'heatmap_json': '[]',
        'nivel_obj': None, 'subiu_nivel': None, 'rank_novo': '', 'plano_din': None,
    }

    # ── Respostas / aproveitamento ──────────────────────────────────
    try:
        respostas = RespostaUsuario.objects.filter(usuario=request.user)
        ctx['total_respondidas'] = respostas.count()
        ctx['total_acertos'] = respostas.filter(acertou=True).count()
        if ctx['total_respondidas']:
            ctx['aproveitamento'] = round((ctx['total_acertos'] / ctx['total_respondidas'] * 100), 1)
    except Exception as e:
        _log_falha('respostas', e)
        respostas = RespostaUsuario.objects.none()

    # ── Novo usuario (0 respostas) → onboarding ou fluxo de estudo ──────
    # Dashboard cheio de estatisticas nao faz sentido pra quem acabou de cadastrar.
    # Se ainda nao personalizou concurso, manda pro onboarding (ativa trial PRO 7 dias);
    # se ja personalizou (mas ainda nao respondeu), vai direto escolher tema.
    if ctx['total_respondidas'] == 0:
        try:
            from ..models import ConcursoPreferido
            if not ConcursoPreferido.objects.filter(usuario=request.user).exists():
                return redirect('onboarding_concurso')
        except Exception as e:
            _log_falha('onboarding_check', e)
        return redirect('escolher_tema')

    # ── Meta / streak ────────────────────────────────────────────────
    try:
        meta, _created = MetaEstudo.objects.get_or_create(usuario=request.user)
        ctx['meta'] = meta
        ctx['questoes_hoje'] = respostas.filter(data__date=timezone.localdate()).count()
        if meta.questoes_por_dia:
            ctx['pct_meta'] = min(100, round(ctx['questoes_hoje'] / meta.questoes_por_dia * 100))
    except Exception as e:
        _log_falha('meta', e)

    # ── Últimos simulados ───────────────────────────────────────────
    try:
        ctx['ultimos_simulados'] = list(Simulado.objects.filter(
            usuario=request.user, finalizado=True
        ).order_by('-finalizado_em')[:3])
    except Exception as e:
        _log_falha('ultimos_simulados', e)

    # ── Melhores / piores disciplinas ────────────────────────────────
    # Otimizacao: 1 query agregada em vez de N queries por categoria.
    try:
        from django.db.models import Count, Q
        stats_cat = (respostas
            .values('questao__categoria_id', 'questao__categoria__nome')
            .annotate(
                total=Count('id'),
                acertos=Count('id', filter=Q(acertou=True)),
            )
            .filter(total__gte=5)
            .order_by())
        por_cat = [
            {
                'nome':  s['questao__categoria__nome'] or '—',
                'pct':   round(s['acertos'] / s['total'] * 100),
                'total': s['total'],
            }
            for s in stats_cat
        ]
        por_cat.sort(key=lambda x: x['pct'], reverse=True)
        ctx['melhores'] = por_cat[:3]
        ctx['piores'] = sorted(por_cat, key=lambda x: x['pct'])[:3]
    except Exception as e:
        _log_falha('melhores_piores', e)

    # ── Revisão espaçada pendente ────────────────────────────────────
    try:
        ctx['srs_pendentes'] = RevisaoEspacada.objects.filter(
            usuario=request.user, proxima_revisao__lte=timezone.localdate()
        ).count()
    except Exception as e:
        _log_falha('srs', e)

    # ── Foto Google (só se tiver login social) ───────────────────────
    if _has_allauth:
        try:
            social = SocialAccount.objects.get(user=request.user, provider='google')
            ctx['foto_google'] = social.extra_data.get('picture', '')
        except SocialAccount.DoesNotExist:
            pass
        except Exception as e:
            _log_falha('foto_google', e)

    # ── Heatmap ──────────────────────────────────────────────────────
    try:
        ctx['heatmap_json'] = _json.dumps(_heatmap_data(request.user))
    except Exception as e:
        _log_falha('heatmap', e)

    # ── Nível ────────────────────────────────────────────────────────
    try:
        nivel_obj, _created = NivelUsuario.objects.get_or_create(usuario=request.user)
        ctx['nivel_obj'] = nivel_obj
        ctx['subiu_nivel'] = request.session.pop('subiu_nivel', None)
        ctx['rank_novo'] = request.session.pop('rank_nome', '')
    except Exception as e:
        _log_falha('nivel', e)

    # ── Plano dinâmico ───────────────────────────────────────────────
    try:
        ctx['plano_din'] = PlanoEstudoDinamico.objects.filter(usuario=request.user).first()
    except Exception as e:
        _log_falha('plano_din', e)

    # ── Status de uso (Free/PRO/Premium) ─────────────────────────────
    try:
        from ..limits import status_uso
        ctx['uso_plano'] = status_uso(request.user)
    except Exception as e:
        _log_falha('uso_plano', e)

    # ── Onboarding checklist (primeiros 7 dias) ──────────────────────
    # Idempotente: check_and_award so entrega XP das tasks que ainda nao
    # foram recompensadas. resumo() da o estado atual pro template.
    try:
        from .. import onboarding as _onboard
        novas_recompensas = _onboard.check_and_award(request.user)
        ctx['onboarding'] = _onboard.resumo(request.user)
        if novas_recompensas:
            # Mostra flash message pras tasks recem-recompensadas
            for t in novas_recompensas:
                messages.success(
                    request,
                    f"🎉 {t['titulo']}: +{t['xp']} XP ganhos!",
                )
    except Exception as e:
        _log_falha('onboarding', e)

    # ── Concurso preferido (pra CTA "Preparacao completa") ────────────
    try:
        from ..models import ConcursoPreferido
        pref = ConcursoPreferido.objects.filter(usuario=request.user).first()
        ctx['concurso_pref_slug'] = pref.concurso if pref else None
        ctx['concurso_pref'] = pref
    except Exception as e:
        _log_falha('concurso_pref', e)

    # ── Render blindado: se ate o template crashar, redireciona ─────────
    try:
        return render(request, 'quiz/dashboard.html', ctx)
    except Exception as e:
        _log_falha('template_render', e)
        return redirect('escolher_tema')


@login_required(login_url='account_login')
def compartilhar_simulado(request, simulado_id):
    """
    Pagina de compartilhamento do resultado do simulado.
    Gera preview visual (formato Stories 1080x1920 via CSS) + botao pra
    baixar imagem + botao pra copiar link/texto pras redes sociais.
    """
    simulado = get_object_or_404(Simulado, id=simulado_id, usuario=request.user, finalizado=True)
    respostas   = simulado.respostas.select_related('questao__categoria').all()
    respondidas = [r for r in respostas if r.acertou is not None]
    acertos     = sum(1 for r in respondidas if r.acertou)
    total       = len(respondidas)
    aproveitamento = round(acertos / total * 100) if total else 0

    # Copy do share adaptativo
    if aproveitamento >= 80:
        titulo = f'Fechei {acertos}/{total} no simulado. 🚀'
    elif aproveitamento >= 60:
        titulo = f'Acertei {acertos}/{total} no simulado. Bora que bora.'
    elif aproveitamento >= 40:
        titulo = f'Acertei {acertos}/{total}. Cada erro é uma lacuna mapeada.'
    else:
        titulo = f'Fiz {acertos}/{total}. Errar é o começo do aprendizado.'

    hashtags = '#concurso #estudos #santuarioedu'

    return render(request, 'quiz/compartilhar_simulado.html', {
        'simulado':       simulado,
        'aproveitamento': aproveitamento,
        'total':          total,
        'acertos':        acertos,
        'titulo_share':   titulo,
        'hashtags':       hashtags,
    })


# ─── SIMULADO ────────────────────────────────────────────────────────────────

# Editais oficiais de concursos — usados em /simulado/edital/
# Cada edital tem distribuição de questões por disciplina conforme o edital real.
# Se uma disciplina do edital não existir no banco, ela é ignorada
# e a quantidade é redistribuída proporcionalmente entre as disponíveis.
EDITAIS_OFICIAIS = [
    {
        'id': 'prf_2024',
        'nome': 'PRF — Polícia Rodoviária Federal',
        'orgao': 'PRF',
        'banca': 'CESPE / CEBRASPE',
        'ano': 2024,
        'total': 50,
        'duracao_min': 300,
        'cor': 'amber',
        'icone': 'local_police',
        'descricao': 'Edital padrão para Policial Rodoviário Federal com foco em Legislação de Trânsito e Direito Constitucional.',
        'distribuicao': {
            'Legislação de Trânsito':    20,
            'Língua Portuguesa':         10,
            'Raciocínio Lógico':          5,
            'Direito Constitucional':     5,
            'Direito Administrativo':     5,
            'Legislação Complementar':    3,
            'Informática':                2,
        },
    },
    {
        'id': 'pf_agente_2025',
        'nome': 'PF — Agente Administrativo',
        'orgao': 'Polícia Federal',
        'banca': 'CEBRASPE',
        'ano': 2025,
        'total': 120,
        'duracao_min': 240,
        'cor': 'blue',
        'icone': 'shield_person',
        'descricao': 'Concurso PF Agente Administrativo 2025 com foco em Direito Administrativo e Segurança Pública.',
        'distribuicao': {
            'Língua Portuguesa':         20,
            'Raciocínio Lógico e Matemática': 10,
            'Direito Administrativo':    24,
            'Direito Constitucional':    10,
            'Informática':               10,
            'Administração Pública':     30,
            'Segurança Pública':         16,
        },
    },
    {
        'id': 'inss_tecnico_2024',
        'nome': 'INSS — Técnico do Seguro Social',
        'orgao': 'INSS',
        'banca': 'CESPE / CEBRASPE',
        'ano': 2024,
        'total': 80,
        'duracao_min': 240,
        'cor': 'emerald',
        'icone': 'medical_services',
        'descricao': 'Concurso INSS Técnico do Seguro Social com foco em Direito Previdenciário e Ética no Serviço Público.',
        'distribuicao': {
            'Língua Portuguesa':         15,
            'Raciocínio Lógico':         10,
            'Direito Constitucional':    10,
            'Direito Administrativo':    20,
            'Informática':                5,
            'Ética no Serviço Público':  10,
            'Direito Previdenciário':    10,
        },
    },
    {
        'id': 'enem_2024',
        'nome': 'ENEM — Exame Nacional do Ensino Médio',
        'orgao': 'INEP',
        'banca': 'INEP',
        'ano': 2024,
        'total': 45,
        'duracao_min': 270,
        'cor': 'violet',
        'icone': 'school',
        'descricao': 'Simulado no estilo ENEM cobrindo as áreas de Linguagens, Matemática, Ciências Humanas e Naturais.',
        'distribuicao': {
            'ENEM':                      45,
        },
    },
    {
        'id': 'tj_df_analista_2024',
        'nome': 'TJ-DF — Analista Judiciário',
        'orgao': 'Tribunal de Justiça do DF',
        'banca': 'CESPE / CEBRASPE',
        'ano': 2024,
        'total': 100,
        'duracao_min': 300,
        'cor': 'rose',
        'icone': 'gavel',
        'descricao': 'Concurso para Analista Judiciário do TJ-DF com forte presença de Direito Constitucional e Administrativo.',
        'distribuicao': {
            'Língua Portuguesa':         15,
            'Direito Constitucional':    25,
            'Direito Administrativo':    20,
            'Raciocínio Lógico':         10,
            'Informática':               10,
            'Ética no Serviço Público':  10,
            'Administração Pública':     10,
        },
    },
]


# Perfis de simulado genéricos — usados em /simulado/personalizado/
PRF_EDITAL_PERFIS = [
    {
        'id': 'completo',
        'nome': 'Simulado Completo',
        'descricao': '50 questões distribuídas proporcionalmente entre todas as disciplinas disponíveis.',
        'total': 50,
        'proporcoes': {},      # vazio → distribuição automática
        'estrategia': 'proporcional',
    },
    {
        'id': 'rapido',
        'nome': 'Simulado Rápido',
        'descricao': '20 questões em distribuição equilibrada — ideal para um treino curto.',
        'total': 20,
        'proporcoes': {},
        'estrategia': 'proporcional',
    },
    {
        'id': 'pontos_fracos',
        'nome': 'Foco nos Pontos Fracos',
        'descricao': '30 questões priorizando as disciplinas com menor aproveitamento.',
        'total': 30,
        'proporcoes': {},
        'estrategia': 'fracos',
    },
    {
        'id': 'personalizado',
        'nome': 'Personalizado',
        'descricao': 'Monte sua própria distribuição de questões por disciplina.',
        'total': 0,
        'proporcoes': {},
        'estrategia': 'manual',
    },
]


def _check_pode_criar_simulado(request, fallback_url='escolher_tema'):
    """Helper compartilhado pelos 5 modos (edital, personalizado, preditivo,
    prova_real, iniciar_simulado) — verifica simulado ativo + limite do plano.
    Retorna HttpResponse (redirect) se NAO pode criar; None se pode."""
    # 1. Simulado ativo? Manda pro simulado em andamento em vez de criar orfaos
    simulado_ativo = Simulado.objects.filter(
        usuario=request.user, finalizado=False,
    ).first()
    if simulado_ativo and simulado_ativo.segundos_restantes() > 0:
        messages.info(request, 'Voce ja tem um simulado em andamento. Finalize ou aguarde o timer.')
        return redirect('simulado_questao', simulado_id=simulado_ativo.id, numero=1)

    # 2. Limite semanal (gratuito 1/sem, PRO ilimitado)
    from ..limits import pode_iniciar_simulado as _pode, get_plano
    if not _pode(request.user):
        plano = get_plano(request.user)
        if plano == 'gratuito':
            messages.warning(
                request,
                'Voce atingiu o limite de simulados da semana no plano Gratuito. '
                'Faca upgrade para PRO e tenha simulados ilimitados.'
            )
            return redirect('planos')
        messages.warning(request, 'Limite de simulados atingido nesta semana.')
        return redirect(fallback_url)

    return None  # pode criar


# ─── PAINEL DE ADMINISTRAÇÃO DE QUESTÕES ─────────────────────────────────────

def _is_staff(user):
    return user.is_staff or user.is_superuser

@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_painel(request):
    categorias = Categoria.objects.all().order_by('nome')
    dados = []
    for cat in categorias:
        dados.append({
            'id': cat.id,
            'nome': cat.nome,
            'total': cat.questao_set.count(),
        })
    total_geral = Questao.objects.count()
    return render(request, 'quiz/admin/painel.html', {
        'categorias': dados,
        'total_geral': total_geral,
    })


@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_meta_progresso(request):
    """Dashboard de progresso da meta 1000 IA + 1000 oficial por categoria.
    Mostra so raizes canonicas (nao folhas) — 1 linha por disciplina principal.
    Aproveita hierarquia: contagem inclui todas as sub-categorias."""
    from django.db.models import Q as _Q

    META = 1000
    # So raizes (parent=None) — as 9 canonicas apos seed
    raizes = list(Categoria.objects.filter(parent__isnull=True).order_by('nome'))

    dados = []
    for r in raizes:
        ids_sub = r.subarvore_ids()
        qs = Questao.objects.filter(categoria_id__in=ids_sub, revisada=True)
        ia = qs.filter(gerada_por_ia=True).count()
        oficial = qs.filter(gerada_por_ia=False).exclude(banca__isnull=True).exclude(banca='').count()
        # Pendentes (nao revisada) — sinal de trabalho parado
        pendentes = Questao.objects.filter(
            categoria_id__in=ids_sub, revisada=False, rejeitada_definitiva=False,
        ).count()

        pct_ia = min(100, round(ia / META * 100))
        pct_oficial = min(100, round(oficial / META * 100))
        pct_total = round((ia + oficial) / (META * 2) * 100)

        dados.append({
            'id': r.id,
            'nome': r.nome,
            'ia': ia,
            'ia_faltam': max(0, META - ia),
            'pct_ia': pct_ia,
            'oficial': oficial,
            'oficial_faltam': max(0, META - oficial),
            'pct_oficial': pct_oficial,
            'total': ia + oficial,
            'pct_total': pct_total,
            'pendentes_revisao': pendentes,
            'n_filhos_subarvore': len(ids_sub) - 1,  # exclui a raiz
            'concluido': ia >= META and oficial >= META,
        })

    # Ordena: prioridade por % total ASC (menos completa primeiro)
    dados.sort(key=lambda x: (x['concluido'], x['pct_total']))

    # Totais globais
    total_ia = sum(d['ia'] for d in dados)
    total_oficial = sum(d['oficial'] for d in dados)
    total_pendentes = sum(d['pendentes_revisao'] for d in dados)
    meta_total = META * 2 * len(raizes)  # 2000 por raiz

    return render(request, 'quiz/admin/meta_progresso.html', {
        'dados': dados,
        'meta': META,
        'total_ia': total_ia,
        'total_oficial': total_oficial,
        'total_pendentes': total_pendentes,
        'meta_total_global': meta_total,
        'pct_global': round((total_ia + total_oficial) / meta_total * 100) if meta_total else 0,
        'n_categorias': len(raizes),
        'n_concluidas': sum(1 for d in dados if d['concluido']),
    })


@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_questoes(request):
    from django.db.models.functions import Length

    qs = Questao.objects.select_related('categoria').prefetch_related('alternativa_set')

    # Filtros
    cat_id  = request.GET.get('categoria', '')
    busca   = request.GET.get('q', '').strip()
    tipo    = request.GET.get('tipo', '')
    imagem  = request.GET.get('imagem', '')   # 'com' | 'sem'
    apoio   = request.GET.get('apoio', '')    # 'com' | 'sem'
    APOIO_MIN_CHARS = 250  # limite para considerar que tem "texto de apoio"

    if cat_id:
        qs = qs.filter(categoria_id=cat_id)
    if busca:
        qs = qs.filter(texto__icontains=busca)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if imagem == 'com':
        qs = qs.exclude(imagem='').exclude(imagem=None)
    elif imagem == 'sem':
        qs = qs.filter(Q(imagem='') | Q(imagem=None))
    if apoio in ('com', 'sem'):
        qs = qs.annotate(_tlen=Length('texto'))
        if apoio == 'com':
            qs = qs.filter(_tlen__gte=APOIO_MIN_CHARS)
        else:
            qs = qs.filter(_tlen__lt=APOIO_MIN_CHARS)

    qs = qs.order_by('categoria__nome', 'id')

    # Paginação manual simples
    from django.core.paginator import Paginator
    paginator = Paginator(qs, 30)
    page_num  = request.GET.get('page', 1)
    page_obj  = paginator.get_page(page_num)

    categorias = Categoria.objects.all().order_by('nome')

    # Stats para o header
    total_geral    = Questao.objects.count()
    nao_revisadas  = Questao.objects.filter(revisada=False).count()
    maior_cat      = Categoria.objects.annotate(n=Count('questao')).order_by('-n').first()
    maior_disciplina = maior_cat.nome if maior_cat else '—'

    return render(request, 'quiz/admin/questoes.html', {
        'page_obj': page_obj,
        'categorias': categorias,
        'cat_id': cat_id,
        'busca': busca,
        'tipo': tipo,
        'imagem': imagem,
        'apoio': apoio,
        'total_filtrado': qs.count(),
        'total_geral': total_geral,
        'nao_revisadas': nao_revisadas,
        'maior_disciplina': maior_disciplina,
        'erros': [],
    })


@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_questao_criar(request):
    categorias = Categoria.objects.all().order_by('nome')
    erros = []

    if request.method == 'POST':
        cat_id    = request.POST.get('categoria')
        texto     = request.POST.get('texto', '').strip()
        tipo      = request.POST.get('tipo', 'ME')
        alts      = request.POST.getlist('alternativa_texto')
        corretas  = request.POST.getlist('alternativa_correta')  # lista de índices "0","1"...

        if not cat_id:
            erros.append('Selecione uma categoria.')
        if not texto:
            erros.append('O enunciado não pode estar vazio.')
        alts_validas = [a.strip() for a in alts if a.strip()]
        if len(alts_validas) < 2:
            erros.append('Insira pelo menos 2 alternativas.')
        if not corretas:
            erros.append('Marque ao menos uma alternativa correta.')

        if not erros:
            questao = Questao.objects.create(
                categoria_id=cat_id,
                texto=texto,
                tipo=tipo,
                justificativa=request.POST.get('justificativa', '').strip() or None,
            )
            for i, txt in enumerate(alts_validas):
                Alternativa.objects.create(
                    questao=questao,
                    texto=txt,
                    correta=(str(i) in corretas),
                )
            return redirect(f'/admin-questoes/?categoria={cat_id}&criada=1')

    # Se chegou aqui com erros, re-renderiza a lista com o modal aberto
    from django.core.paginator import Paginator
    qs_all = Questao.objects.select_related('categoria').prefetch_related('alternativa_set').order_by('id')
    paginator = Paginator(qs_all, 30)
    page_obj = paginator.get_page(1)
    total_geral = Questao.objects.count()
    nao_revisadas = Questao.objects.filter(revisada=False).count()
    maior_cat = Categoria.objects.annotate(n=Count('questao')).order_by('-n').first()
    return render(request, 'quiz/admin/questoes.html', {
        'page_obj': page_obj, 'categorias': categorias, 'cat_id': '',
        'busca': '', 'tipo': '', 'total_filtrado': total_geral,
        'total_geral': total_geral, 'nao_revisadas': nao_revisadas,
        'maior_disciplina': maior_cat.nome if maior_cat else '—',
        'erros': erros,
    })


@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_questao_editar(request, questao_id):
    from django.shortcuts import get_object_or_404
    questao    = get_object_or_404(Questao, id=questao_id)
    categorias = Categoria.objects.all().order_by('nome')
    alternativas = list(questao.alternativa_set.all())
    erros = []

    if request.method == 'POST':
        cat_id   = request.POST.get('categoria')
        texto    = request.POST.get('texto', '').strip()
        tipo     = request.POST.get('tipo', 'ME')
        alts     = request.POST.getlist('alternativa_texto')
        corretas = request.POST.getlist('alternativa_correta')

        if not cat_id:
            erros.append('Selecione uma categoria.')
        if not texto:
            erros.append('O enunciado não pode estar vazio.')
        alts_validas = [a.strip() for a in alts if a.strip()]
        if len(alts_validas) < 2:
            erros.append('Insira pelo menos 2 alternativas.')
        if not corretas:
            erros.append('Marque ao menos uma alternativa correta.')

        if not erros:
            questao.categoria_id = cat_id
            questao.texto = texto
            questao.tipo = tipo
            questao.justificativa = request.POST.get('justificativa', '').strip() or None
            questao.save()

            # Recria as alternativas
            questao.alternativa_set.all().delete()
            for i, txt in enumerate(alts_validas):
                Alternativa.objects.create(
                    questao=questao,
                    texto=txt,
                    correta=(str(i) in corretas),
                )
            return redirect(f'/admin-questoes/?categoria={cat_id}&editada=1')

    return render(request, 'quiz/admin/questao_form.html', {
        'questao': questao,
        'alternativas': alternativas,
        'categorias': categorias,
        'erros': erros,
        'modo': 'editar',
    })


@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_questao_excluir(request, questao_id):
    from django.shortcuts import get_object_or_404
    questao = get_object_or_404(Questao, id=questao_id)
    cat_id  = questao.categoria_id
    if request.method == 'POST':
        questao.delete()
        return redirect(f'/admin-questoes/?categoria={cat_id}&excluida=1')
    return render(request, 'quiz/admin/questao_excluir.html', {'questao': questao})


# ─── ANALYTICS REAL ──────────────────────────────────────────────────────────


# ─── SPRINT 10E: RELATÓRIO SEMANAL PDF ──────────────────────────────────────

@login_required(login_url='account_login')
def relatorio_semanal(request):
    """Gera relatório PDF via window.print() — CSS @media print."""
    import json as _json
    from datetime import date

    # Período: esta semana (últimos 7 dias) ou semana especificada
    hoje = timezone.now().date()
    semana_str = request.GET.get('semana')
    if semana_str:
        try:
            from datetime import datetime
            inicio_semana = datetime.strptime(semana_str, '%Y-%m-%d').date()
        except Exception:
            inicio_semana = hoje - timedelta(days=hoje.weekday())
    else:
        inicio_semana = hoje - timedelta(days=hoje.weekday())  # segunda-feira
    fim_semana = inicio_semana + timedelta(days=6)

    # Respostas da semana
    respostas_sem = RespostaUsuario.objects.filter(
        usuario=request.user,
        data__date__gte=inicio_semana,
        data__date__lte=fim_semana,
    )
    total_sem   = respostas_sem.count()
    acertos_sem = respostas_sem.filter(acertou=True).count()
    erros_sem   = total_sem - acertos_sem
    aprov_sem   = round(acertos_sem / total_sem * 100, 1) if total_sem else 0

    # Por disciplina (apenas as respondidas na semana)
    cats_sem = []
    for cat in Categoria.objects.all().order_by('nome'):
        r = respostas_sem.filter(questao__categoria=cat)
        t = r.count()
        if t == 0:
            continue
        a = r.filter(acertou=True).count()
        cats_sem.append({
            'nome': cat.nome,
            'total': t,
            'acertos': a,
            'erros': t - a,
            'pct': round(a / t * 100),
        })
    cats_sem.sort(key=lambda x: x['pct'])  # piores primeiro

    # Sessões de estudo na semana
    sessoes_sem = SessaoEstudo.objects.filter(
        usuario=request.user,
        iniciada_em__date__gte=inicio_semana,
        iniciada_em__date__lte=fim_semana,
    )
    total_min_sem = sessoes_sem.aggregate(s=Sum('duracao_seg'))['s'] or 0
    total_min_sem = total_min_sem // 60
    total_sessoes_sem = sessoes_sem.count()

    # Dia a dia na semana
    dias = []
    for i in range(7):
        d = inicio_semana + timedelta(days=i)
        r = respostas_sem.filter(data__date=d)
        t = r.count()
        a = r.filter(acertou=True).count()
        dias.append({
            'data': d,
            'dia_semana': d.strftime('%a'),
            'total': t,
            'acertos': a,
            'pct': round(a / t * 100) if t else 0,
        })

    # Conquistas desbloqueadas na semana
    conquistas_sem = Conquista.objects.filter(
        usuario=request.user,
        desbloqueado_em__date__gte=inicio_semana,
        desbloqueado_em__date__lte=fim_semana,
    )

    # Semanas anteriores/próximas para navegação
    semana_anterior = (inicio_semana - timedelta(days=7)).strftime('%Y-%m-%d')
    semana_proxima  = (inicio_semana + timedelta(days=7)).strftime('%Y-%m-%d')
    semana_atual    = (hoje - timedelta(days=hoje.weekday())).strftime('%Y-%m-%d')

    return render(request, 'quiz/relatorio_semanal.html', {
        'inicio_semana':    inicio_semana,
        'fim_semana':       fim_semana,
        'total_sem':        total_sem,
        'acertos_sem':      acertos_sem,
        'erros_sem':        erros_sem,
        'aprov_sem':        aprov_sem,
        'cats_sem':         cats_sem,
        'dias':             dias,
        'total_min_sem':    total_min_sem,
        'total_sessoes_sem':total_sessoes_sem,
        'conquistas_sem':   conquistas_sem,
        'semana_anterior':  semana_anterior,
        'semana_proxima':   semana_proxima,
        'semana_atual':     semana_atual,
        'eh_semana_atual':  semana_str is None or semana_str == semana_atual,
        'hoje':             hoje,
        'tem_email':        bool(request.user.email),
    })


@login_required(login_url='account_login')
@require_POST
def enviar_relatorio_email(request):
    """Envia o relatório semanal para o e-mail do usuário logado."""
    from django.core.mail import send_mail

    user = request.user
    if not user.email:
        messages.error(request, 'Configure um e-mail no seu perfil primeiro.')
        return redirect('relatorio_semanal')

    hoje = timezone.now().date()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    fim_semana    = inicio_semana + timedelta(days=6)

    respostas = RespostaUsuario.objects.filter(
        usuario=user,
        data__date__gte=inicio_semana,
        data__date__lte=fim_semana,
    )
    total   = respostas.count()
    acertos = respostas.filter(acertou=True).count()
    pct     = round(acertos / total * 100, 1) if total else 0
    nome    = user.first_name or user.username

    corpo = (
        f'Olá, {nome}!\n\n'
        f'Aqui está seu resumo da semana ({inicio_semana.strftime("%d/%m")} a {fim_semana.strftime("%d/%m/%Y")}):\n\n'
        f'  📝 Questões respondidas: {total}\n'
        f'  ✅ Acertos: {acertos}\n'
        f'  📈 Aproveitamento: {pct}%\n\n'
        f'{"🏆 Semana excelente!" if pct >= 70 else "📚 Continue praticando!"}\n\n'
        f'Ver relatório completo: http://127.0.0.1:8000/relatorio-semanal/\n\n'
        f'-- SantuarioEdu\n'
    )
    try:
        send_mail(
            subject      = f'📊 Seu resumo semanal — SantuarioEdu ({pct}% de aproveitamento)',
            message      = corpo,
            from_email   = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@santuarioedu.com.br'),
            recipient_list=[user.email],
            fail_silently= False,
        )
        messages.success(request, f'Relatório enviado para {user.email}!')
    except Exception as e:
        messages.error(request, f'Erro ao enviar e-mail: {e}')

    return redirect('relatorio_semanal')


# ─── Modo Maratona: REMOVIDO em favor do Modo Desafio ────────────────────────


# ─── SPRINT 10A: PROGRESSO POR EDITAL ───────────────────────────────────────

# Distribuição percentual do edital PRF (POLICIAL RODOVIÁRIO FEDERAL)
# Fonte: edital PRF 2024 — distribuição ajustada ao banco de questões
PRF_EDITAL_TOPICOS = [
    {'disciplina': 'Legislação de Trânsito',     'peso': 22, 'icone': 'directions_car',    'cor': 'blue'},
    {'disciplina': 'Língua Portuguesa',           'peso': 12, 'icone': 'menu_book',         'cor': 'violet'},
    {'disciplina': 'Raciocínio Lógico',           'peso':  8, 'icone': 'psychology',        'cor': 'amber'},
    {'disciplina': 'Direito Constitucional',      'peso':  8, 'icone': 'gavel',             'cor': 'green'},
    {'disciplina': 'Direito Administrativo',      'peso':  8, 'icone': 'account_balance',   'cor': 'teal'},
    {'disciplina': 'Legislação Complementar',     'peso':  6, 'icone': 'policy',            'cor': 'indigo'},
    {'disciplina': 'Informática',                 'peso':  6, 'icone': 'computer',          'cor': 'cyan'},
    {'disciplina': 'Matemática',                  'peso':  6, 'icone': 'calculate',         'cor': 'orange'},
    {'disciplina': 'Física',                      'peso':  4, 'icone': 'science',           'cor': 'red'},
    {'disciplina': 'Primeiros Socorros',          'peso':  4, 'icone': 'medical_services',  'cor': 'rose'},
    {'disciplina': 'Direito Penal',               'peso':  4, 'icone': 'security',          'cor': 'slate'},
    {'disciplina': 'Atualidades',                 'peso':  4, 'icone': 'newspaper',         'cor': 'lime'},
    {'disciplina': 'Direito Processual Penal',    'peso':  4, 'icone': 'balance',           'cor': 'purple'},
    {'disciplina': 'Estatística',                 'peso':  4, 'icone': 'bar_chart',         'cor': 'fuchsia'},
]

_COR_MAP = {
    'blue':   ('#3b82f6', '#eff6ff'),
    'violet': ('#7c3aed', '#f5f3ff'),
    'amber':  ('#f59e0b', '#fffbeb'),
    'green':  ('#22c55e', '#f0fdf4'),
    'teal':   ('#14b8a6', '#f0fdfa'),
    'indigo': ('#6366f1', '#eef2ff'),
    'cyan':   ('#06b6d4', '#ecfeff'),
    'orange': ('#f97316', '#fff7ed'),
    'red':    ('#ef4444', '#fef2f2'),
    'rose':   ('#f43f5e', '#fff1f2'),
    'slate':  ('#64748b', '#f8fafc'),
    'lime':   ('#84cc16', '#f7fee7'),
    'purple': ('#a855f7', '#faf5ff'),
    'fuchsia':('#d946ef', '#fdf4ff'),
}

@login_required(login_url='account_login')
def progresso_edital(request):
    """Roadmap visual: progresso do usuário por tópico do edital PRF."""
    import json as _json
    respostas = RespostaUsuario.objects.filter(usuario=request.user)

    # Mapa disciplina → (respondidas, acertos, total_banco)
    stats = {}
    for cat in Categoria.objects.annotate(total_questoes=Count('questao')):
        r = respostas.filter(questao__categoria=cat)
        resp = r.count()
        acert = r.filter(acertou=True).count()
        stats[cat.nome.strip()] = {
            'respondidas': resp,
            'acertos': acert,
            'total_banco': cat.total_questoes,
        }

    topicos = []
    total_ponderado = 0
    progresso_ponderado = 0

    for t in PRF_EDITAL_TOPICOS:
        disc = t['disciplina']
        # Busca correspondência aproximada no banco
        match = None
        for cat_nome in stats:
            if disc.lower() in cat_nome.lower() or cat_nome.lower() in disc.lower():
                match = cat_nome
                break

        s = stats.get(match, {'respondidas': 0, 'acertos': 0, 'total_banco': 0}) if match else {'respondidas': 0, 'acertos': 0, 'total_banco': 0}
        total_banco    = s['total_banco']
        respondidas    = s['respondidas']
        acertos        = s['acertos']
        pct_cobertura  = round(min(respondidas / total_banco * 100, 100), 1) if total_banco else 0
        pct_aproveit   = round(acertos / respondidas * 100, 1) if respondidas else 0

        peso = t['peso']
        total_ponderado += peso
        progresso_ponderado += peso * pct_cobertura / 100

        cor, bg = _COR_MAP.get(t['cor'], ('#6366f1', '#eef2ff'))
        topicos.append({
            'disciplina':    disc,
            'peso':          peso,
            'icone':         t['icone'],
            'cor':           cor,
            'bg':            bg,
            'total_banco':   total_banco,
            'respondidas':   respondidas,
            'acertos':       acertos,
            'pct_cobertura': pct_cobertura,
            'pct_aproveit':  pct_aproveit,
            'nivel':         'forte' if pct_aproveit >= 70 else 'regular' if pct_aproveit >= 50 else 'fraco' if respondidas else 'nenhum',
        })

    progresso_geral = round(progresso_ponderado / total_ponderado * 100, 1) if total_ponderado else 0
    topicos_sorted  = sorted(topicos, key=lambda x: x['pct_aproveit'])  # piores primeiro

    return render(request, 'quiz/progresso_edital.html', {
        'topicos':          topicos,
        'topicos_sorted':   topicos_sorted,
        'progresso_geral':  progresso_geral,
        'total_respondidas': respostas.count(),
    })


# ─── CADERNO DE ERROS ────────────────────────────────────────────────────────


# ─── HISTÓRICO DE SIMULADOS ──────────────────────────────────────────────────


# ─── FAVORITAS ───────────────────────────────────────────────────────────────


# ─── PLANO DE ESTUDOS FUNCIONAL ──────────────────────────────────────────────

@login_required(login_url='account_login')
def plano_estudos(request):
    meta, _ = MetaEstudo.objects.get_or_create(usuario=request.user)

    if request.method == 'POST':
        qtd = int(request.POST.get('questoes_por_dia', 20))
        meta.questoes_por_dia = max(1, min(200, qtd))
        meta.save(update_fields=['questoes_por_dia'])
        return redirect('plano_estudos')

    hoje = timezone.localdate()
    questoes_hoje = RespostaUsuario.objects.filter(
        usuario=request.user, data__date=hoje
    ).count()
    pct_meta = min(100, round(questoes_hoje / meta.questoes_por_dia * 100)) if meta.questoes_por_dia else 0

    # Calendário dos últimos 35 dias (5 semanas)
    atividade_raw = (
        RespostaUsuario.objects
        .filter(usuario=request.user, data__gte=timezone.now()-timedelta(days=34))
        .annotate(dia=TruncDate('data'))
        .values('dia')
        .annotate(total=Count('id'), acertos=Count('id', filter=Q(acertou=True)))
    )
    ativ_map = {item['dia']: item for item in atividade_raw}
    calendario = []
    for i in range(34, -1, -1):
        d = hoje - timedelta(days=i)
        item = ativ_map.get(d, {'total': 0, 'acertos': 0})
        calendario.append({
            'data': d,
            'dia': d.day,
            'diaSemana': ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'][d.weekday()],
            'total': item['total'],
            'acertos': item['acertos'],
            'estudou': item['total'] > 0,
            'meta_atingida': item['total'] >= meta.questoes_por_dia,
        })

    # Stats por disciplina para sugestão
    respostas = RespostaUsuario.objects.filter(usuario=request.user)
    sugestoes = []
    for cat in Categoria.objects.all():
        r = respostas.filter(questao__categoria=cat)
        t = r.count()
        if t < 3:
            continue
        a = r.filter(acertou=True).count()
        pct = round(a / t * 100)
        total_disp = Questao.objects.filter(categoria=cat).count()
        sugestoes.append({'nome': cat.nome, 'id': cat.id, 'pct': pct, 'total': t, 'disponivel': total_disp})
    sugestoes.sort(key=lambda x: x['pct'])   # piores primeiro

    # ── Cronograma semanal inteligente ───────────────────────────────────────
    # Distribui as 5 disciplinas mais fracas nos próximos 7 dias
    # + conta revisão SRS pendente
    srs_pendentes = RevisaoEspacada.objects.filter(
        usuario=request.user,
        proxima_revisao__lte=hoje,
    ).count()

    dias_semana_nomes = ['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo']
    cronograma = []
    fracas = sugestoes[:7]  # até 7 categorias mais fracas
    for i in range(7):
        d = hoje + timedelta(days=i)
        label = dias_semana_nomes[d.weekday()]
        # alterna categorias fracas; inclui SRS no 1º dia se tiver pendentes
        tarefas = []
        if i == 0 and srs_pendentes > 0:
            tarefas.append({
                'tipo': 'srs',
                'nome': f'Revisão Espaçada ({srs_pendentes} pendentes)',
                'url': '/revisao-srs/?start=1',
                'icone': 'neurology',
                'cor': 'emerald',
            })
        if fracas:
            cat = fracas[i % len(fracas)]
            tarefas.append({
                'tipo': 'quiz',
                'nome': cat['nome'],
                'url': f'/quiz/{cat["id"]}/',
                'pct': cat['pct'],
                'icone': 'menu_book',
                'cor': 'blue' if cat['pct'] >= 50 else 'red',
                'cat_id': cat['id'],
            })
        cronograma.append({
            'data': d,
            'dia_num': d.day,
            'label': label,
            'hoje': i == 0,
            'tarefas': tarefas,
        })

    # Próxima categoria recomendada (a mais fraca com questões disponíveis)
    proxima = fracas[0] if fracas else None

    return render(request, 'quiz/plano_estudos.html', {
        'meta': meta,
        'questoes_hoje': questoes_hoje,
        'pct_meta': pct_meta,
        'calendario': calendario,
        'sugestoes': sugestoes[:5],
        'cronograma': cronograma,
        'proxima': proxima,
        'srs_pendentes': srs_pendentes,
        'hoje': hoje,
    })


# ─── REVISÃO INTELIGENTE (questões mais erradas) ─────────────────────────────

@login_required(login_url='account_login')
def quiz_revisao(request, categoria_id=None):
    """Modo revisão: mostra questões priorizando as mais erradas pelo usuário.
    Segue mesma logica de iniciar_quiz POST — limits, idempotencia, XP, SRS,
    conquistas — pra evitar farm de estatisticas via /revisao/."""
    if request.method == 'POST':
        # Limite de plano (revisao tambem conta pro limite diario)
        from ..limits import pode_responder_questao, get_plano
        if not pode_responder_questao(request.user):
            if get_plano(request.user) == 'gratuito':
                messages.warning(
                    request,
                    'Você atingiu o limite diário de questões do plano Gratuito. '
                    'Faça upgrade para PRO e tenha questões ilimitadas.'
                )
                return redirect('planos')
            messages.warning(request, 'Limite diário de questões atingido.')
            return redirect('dashboard')

        # Validacao de alternativa_id
        alternativa_id = request.POST.get('alternativa_id', '').strip()
        if not alternativa_id.isdigit():
            messages.error(request, 'Selecione uma alternativa antes de confirmar.')
            return redirect('quiz_revisao')

        escolha = get_object_or_404(Alternativa, id=int(alternativa_id))
        cat_id_post = request.POST.get('categoria_id')

        # Idempotencia — nao duplica se ja respondeu hoje
        hoje = timezone.localdate()
        ja_respondeu = RespostaUsuario.objects.filter(
            usuario=request.user, questao=escolha.questao, data__date=hoje,
        ).exists()

        xp_ganho = 0
        subiu_nivel = None
        novas_conquistas_qs = []

        if not ja_respondeu:
            RespostaUsuario.objects.create(
                usuario=request.user, questao=escolha.questao, acertou=escolha.correta,
            )
            meta, _ = MetaEstudo.objects.get_or_create(usuario=request.user)
            meta.atualizar_streak()
            srs, _ = RevisaoEspacada.objects.get_or_create(
                usuario=request.user, questao=escolha.questao,
                defaults={'proxima_revisao': timezone.localdate()},
            )
            srs.atualizar(escolha.correta)
            novas_conquistas_qs = verificar_conquistas(request.user)
            if novas_conquistas_qs:
                request.session['novas_conquistas'] = novas_conquistas_qs
            if escolha.correta:
                xp_ganho = 10
                _dar_xp(request.user, xp_ganho, request.session)
                subiu_nivel = request.session.pop('subiu_nivel', None)

        is_favorita = QuestaoFavorita.objects.filter(
            usuario=request.user, questao=escolha.questao
        ).exists()
        try:
            streak_atual = request.user.metaestudo.streak_atual
        except Exception:
            streak_atual = 0

        return render(request, 'quiz/resultado.html', {
            'escolha': escolha, 'categoria_id': cat_id_post,
            'is_favorita': is_favorita, 'modo_revisao': True,
            'ja_respondeu_antes': ja_respondeu,
            'xp_ganho': xp_ganho,
            'streak_atual': streak_atual,
            'subiu_nivel': subiu_nivel,
            'novas_conquistas': [
                {'codigo': c, **CONQUISTAS_META.get(c, {'label': c, 'emoji': '🏆', 'desc': ''})}
                for c in request.session.pop('novas_conquistas', [])
            ],
        })

    # Questões com mais erros do usuário nessa categoria
    filtro = {'usuario': request.user, 'acertou': False}
    if categoria_id:
        filtro['questao__categoria_id'] = categoria_id

    erros_ids = (
        RespostaUsuario.objects.filter(**filtro)
        .values('questao')
        .annotate(n=Count('id'))
        .order_by('-n')
        .values_list('questao', flat=True)
    )

    questao = None
    for qid in erros_ids:
        questao = Questao.objects.filter(id=qid).first()
        if questao:
            break

    if not questao:
        return render(request, 'quiz/sem_questoes.html', {
            'mensagem': 'Parabéns! Não há questões para revisar nesta categoria.'
        })

    return render(request, 'quiz/responder.html', {
        'questao': questao,
        'categoria_id': categoria_id,
        'modo_revisao': True,
    })


# ─── CONQUISTAS ───────────────────────────────────────────────────────────────


# ─── ANOTAÇÕES PESSOAIS ───────────────────────────────────────────────────────


# ─── IMPORTAÇÃO EM LOTE (CSV) ─────────────────────────────────────────────────

@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_importar_csv(request):
    resultado = None
    erros     = []

    if request.method == 'POST' and request.FILES.get('arquivo'):
        import csv, io
        arquivo = request.FILES['arquivo']
        # Limite de tamanho: 5MB. Evita DoS por volume (10k linhas geram
        # 10k Questao + Alternativas).
        if arquivo.size and arquivo.size > 5 * 1024 * 1024:
            erros.append(f'Arquivo muito grande ({arquivo.size // 1024}KB). Limite: 5MB.')
            return render(request, 'quiz/admin/importar_csv.html', {'erros': erros})
        try:
            texto = arquivo.read().decode('utf-8-sig')
            reader = csv.DictReader(io.StringIO(texto))
            criadas = 0
            for i, row in enumerate(reader, start=2):
                try:
                    cat_nome = row.get('categoria', '').strip()
                    enunciado = row.get('texto', row.get('enunciado', '')).strip()
                    if not cat_nome or not enunciado:
                        erros.append(f'Linha {i}: categoria ou enunciado vazio')
                        continue

                    cat, _ = Categoria.objects.get_or_create(nome=cat_nome)
                    tipo = row.get('tipo', 'ME').strip().upper() or 'ME'

                    q = Questao.objects.create(
                        categoria=cat,
                        texto=enunciado,
                        tipo=tipo,
                        justificativa=row.get('justificativa', '').strip() or None,
                        banca=row.get('banca', '').strip() or None,
                        ano=int(row['ano']) if row.get('ano', '').strip().isdigit() else None,
                    )

                    # Alternativas: colunas alt_a, alt_b, alt_c, alt_d (ou alt_1..alt_4)
                    correta_raw = row.get('correta', row.get('gabarito', 'a')).strip().lower()
                    letras = ['a', 'b', 'c', 'd', 'e']
                    alts_criadas = 0
                    for letra in letras:
                        txt = row.get(f'alt_{letra}', row.get(f'alternativa_{letra}', '')).strip()
                        if txt:
                            Alternativa.objects.create(
                                questao=q,
                                texto=txt,
                                correta=(correta_raw == letra),
                            )
                            alts_criadas += 1
                    if alts_criadas < 2:
                        q.delete()
                        erros.append(f'Linha {i}: menos de 2 alternativas — questão ignorada')
                    else:
                        criadas += 1
                except Exception as e:
                    erros.append(f'Linha {i}: {e}')

            resultado = criadas
        except Exception as e:
            erros.append(f'Erro ao processar arquivo: {e}')

    categorias = Categoria.objects.all().order_by('nome')
    formato = [
        ('categoria',     True,  'Nome da categoria (criada automaticamente se não existir)'),
        ('texto',         True,  'Enunciado da questão'),
        ('tipo',          False, 'ME = Múltipla Escolha | CE = Certo ou Errado (padrão: ME)'),
        ('alt_a',         True,  'Texto da alternativa A'),
        ('alt_b',         True,  'Texto da alternativa B'),
        ('alt_c',         False, 'Texto da alternativa C'),
        ('alt_d',         False, 'Texto da alternativa D'),
        ('alt_e',         False, 'Texto da alternativa E'),
        ('correta',       True,  'Letra da alternativa correta: a, b, c, d ou e'),
        ('justificativa', False, 'Explicação / gabarito comentado'),
        ('banca',         False, 'Banca organizadora (ex: CESPE, FCC)'),
        ('ano',           False, 'Ano da prova (ex: 2023)'),
    ]
    return render(request, 'quiz/admin/importar_csv.html', {
        'resultado': resultado,
        'erros': erros,
        'categorias': categorias,
        'formato': formato,
    })


# ─── SPRINT 9D / 10C: IMPORTAÇÃO VIA IA (texto + PDF) ───────────────────────

@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_importar_ia(request):
    """Admin: cola texto bruto OU envia PDF → Gemini extrai questões estruturadas."""
    from ..ai_service import ai_extrair_questoes

    etapa       = 'form'      # 'form' | 'preview' | 'salvo'
    questoes_ia = []
    erros       = []
    texto_bruto = ''
    salvas      = 0
    fonte       = ''          # 'texto' | 'pdf'

    if request.method == 'POST':
        acao = request.POST.get('acao', 'extrair')

        # ── Etapa 1: extrair questões via IA ──────────────────────────────────
        if acao == 'extrair':
            # Prioridade: PDF enviado > texto colado
            pdf_file = request.FILES.get('arquivo_pdf')
            if pdf_file:
                try:
                    import pdfplumber, io
                    with pdfplumber.open(io.BytesIO(pdf_file.read())) as pdf:
                        paginas = [p.extract_text() or '' for p in pdf.pages[:20]]
                    texto_bruto = '\n\n'.join(paginas).strip()
                    fonte = 'pdf'
                    if not texto_bruto:
                        erros.append('O PDF não contém texto extraível (pode ser uma imagem escaneada).')
                except Exception as e:
                    erros.append(f'Erro ao ler o PDF: {e}')
            else:
                texto_bruto = request.POST.get('texto_bruto', '').strip()
                fonte = 'texto'
            if not texto_bruto:
                erros.append('Cole algum texto antes de extrair.')
            else:
                try:
                    questoes_ia = ai_extrair_questoes(texto_bruto)
                    if not questoes_ia:
                        erros.append('A IA não conseguiu extrair questões do texto. Verifique se o texto está legível e tente novamente.')
                    else:
                        etapa = 'preview'
                except Exception as e:
                    erros.append(f'Erro ao chamar a IA: {e}')

        # ── Etapa 2: confirmar e salvar as questões extraídas ─────────────────
        elif acao == 'salvar':
            import json as json_mod
            raw = request.POST.get('questoes_json', '[]')
            try:
                questoes_ia = json_mod.loads(raw)
            except Exception:
                erros.append('Dados inválidos.')
                questoes_ia = []

            for i, q in enumerate(questoes_ia, start=1):
                try:
                    cat_nome  = (q.get('categoria') or 'Geral').strip()
                    enunciado = (q.get('texto') or '').strip()
                    if not enunciado:
                        erros.append(f'Questão {i}: enunciado vazio — ignorada.')
                        continue

                    cat, _ = Categoria.objects.get_or_create(nome=cat_nome)
                    tipo   = (q.get('tipo') or 'ME').strip().upper()

                    ano_val = q.get('ano')
                    try:
                        ano_val = int(ano_val) if ano_val else None
                    except (ValueError, TypeError):
                        ano_val = None

                    questao_obj = Questao.objects.create(
                        categoria    = cat,
                        texto        = enunciado,
                        tipo         = tipo,
                        justificativa= (q.get('justificativa') or '').strip() or None,
                        banca        = (q.get('banca') or '').strip() or None,
                        ano          = ano_val,
                    )

                    alternativas = q.get('alternativas', [])
                    alts_criadas = 0
                    for alt in alternativas:
                        txt_alt = (alt.get('texto') or '').strip()
                        if txt_alt:
                            Alternativa.objects.create(
                                questao = questao_obj,
                                texto   = txt_alt,
                                correta = bool(alt.get('correta', False)),
                            )
                            alts_criadas += 1

                    if alts_criadas < 2:
                        questao_obj.delete()
                        erros.append(f'Questão {i}: menos de 2 alternativas — ignorada.')
                    else:
                        salvas += 1

                except Exception as e:
                    erros.append(f'Questão {i}: {e}')

            etapa = 'salvo'

    import json as _json
    categorias = Categoria.objects.all().order_by('nome')
    return render(request, 'quiz/admin/importar_ia.html', {
        'etapa':          etapa,
        'texto_bruto':    texto_bruto,
        'questoes_ia':    questoes_ia,
        'questoes_ia_json': _json.dumps(questoes_ia, ensure_ascii=False),
        'erros':          erros,
        'salvas':         salvas,
        'categorias':     categorias,
        'fonte':          fonte,
    })


# ─── SPRINT 6: RANKING ───────────────────────────────────────────────────────


# ─── SPRINT 6: REVISÃO ESPAÇADA (SRS) ────────────────────────────────────────


# ─── SPRINT 6: SESSÃO DE ESTUDO (AJAX) ───────────────────────────────────────

@login_required(login_url='account_login')
@require_POST
@ratelimit(key='user', rate='120/m', method='POST', block=True)
def api_sessao(request):
    """Registra fim de sessão de estudo via AJAX (chamado pelo JS ao sair da página)."""
    try:
        data = json.loads(request.body)
        duracao = int(data.get('duracao_seg', 0))
        questoes = int(data.get('questoes', 0))
        if duracao > 0:
            SessaoEstudo.objects.create(
                usuario=request.user,
                duracao_seg=duracao,
                questoes_resp=questoes,
            )
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'msg': str(e)})


# ─── SPRINT 6: PERFIL PÚBLICO ────────────────────────────────────────────────


# ─── PWA ──────────────────────────────────────────────────────────────────────

from django.views.decorators.cache import cache_control
from django.http import HttpResponse
from django.templatetags.static import static as _static_url

@cache_control(max_age=86400)
def pwa_sw(request):
    """Serve service worker from root so it has full-site scope."""
    import os
    sw_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'static', 'quiz', 'sw.js'
    )
    try:
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        content = '// service worker not found'
    return HttpResponse(content, content_type='application/javascript')


@cache_control(max_age=86400)
def pwa_manifest(request):
    """Serve manifest.json from root."""
    import os, json as _j
    mf_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'static', 'quiz', 'manifest.json'
    )
    try:
        with open(mf_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        content = '{}'
    return HttpResponse(content, content_type='application/manifest+json')


def pwa_offline(request):
    """Offline fallback page."""
    return render(request, 'quiz/offline.html')


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINT 11
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 11A — TUTOR IA ──────────────────────────────────────────────────────────


# ─── 11B — FLASHCARDS ────────────────────────────────────────────────────────


@login_required(login_url='account_login')
def flashcard_estudar(request):
    """Modo estudo: exibe flashcards um a um com flip. Após avaliar, agenda revisão."""
    hoje = timezone.localdate()
    cat_id = request.GET.get('categoria', '')

    qs = Flashcard.objects.filter(usuario=request.user)
    if cat_id:
        qs = qs.filter(categoria_id=cat_id)

    # Prioridade: sem data de revisão → vencidos hoje → futuros
    pendentes = list(
        qs.filter(proxima_revisao__isnull=True) |
        qs.filter(proxima_revisao__lte=hoje)
    )

    if request.method == 'POST':
        fc_id = request.POST.get('flashcard_id')
        dificuldade = int(request.POST.get('dificuldade', 2))
        try:
            fc = Flashcard.objects.get(id=fc_id, usuario=request.user)
            fc.registrar_revisao(dificuldade)
        except Flashcard.DoesNotExist:
            pass
        # Redireciona para o próximo (mantendo filtro de categoria)
        url = 'flashcard_estudar'
        if cat_id:
            return redirect(f'{request.path}?categoria={cat_id}')
        return redirect('flashcard_estudar')

    if not pendentes:
        return render(request, 'quiz/sem_questoes.html', {
            'mensagem': 'Todos os flashcards revisados! 🎉',
            'subtexto': 'Crie novos flashcards ou volte amanhã.',
        })

    fc = pendentes[0]
    restantes = len(pendentes) - 1

    return render(request, 'quiz/flashcard_estudar.html', {
        'fc': fc,
        'restantes': restantes,
        'cat_id': cat_id,
    })


# ─── 11C — ANÁLISE POR BANCA ─────────────────────────────────────────────────


# ── Sprint 21 — API: insight IA por banca ─────────────────────────────────────


# ─── 11D — HEATMAP: dados adicionados à view dashboard ───────────────────────
# (a view dashboard já existe; adicionamos o heatmap_json ao contexto via patch)

def _heatmap_data(user):
    """Retorna lista de {date, count} para os últimos 365 dias."""
    import json as _json
    from datetime import date, timedelta as td
    hoje = timezone.localdate()
    inicio = hoje - td(days=364)

    respostas_365 = (
        RespostaUsuario.objects
        .filter(usuario=user, data__date__gte=inicio)
        .annotate(dia=TruncDate('data'))
        .values('dia')
        .annotate(count=Count('id'))
    )
    mapa = {str(r['dia']): r['count'] for r in respostas_365}

    resultado = []
    for i in range(365):
        d = inicio + td(days=i)
        resultado.append({'date': str(d), 'count': mapa.get(str(d), 0)})
    return resultado


# ─── 11E — MODO DESAFIO ──────────────────────────────────────────────────────

@login_required(login_url='account_login')
def modo_desafio(request):
    """
    Modo Desafio: 10 questões aleatórias, 30s cada.
    GET       → configura e exibe a tela de quiz (JS controla o timer)
    POST      → recebe respostas e exibe resultado
    """
    if request.method == 'POST':
        # Processa respostas enviadas em JSON pelo JS
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'erro': 'JSON inválido'}, status=400)

        respostas_raw = data.get('respostas', [])  # [{questao_id, alternativa_id, tempo_seg}]
        acertos = 0
        total   = len(respostas_raw)
        tempo_total = 0

        for item in respostas_raw:
            alt_id = item.get('alternativa_id')
            tempo  = float(item.get('tempo_seg', 0))
            tempo_total += tempo

            if not alt_id:
                continue

            try:
                alt = Alternativa.objects.select_related('questao').get(id=alt_id)
                acertou = alt.correta
                if acertou:
                    acertos += 1
                RespostaUsuario.objects.create(
                    usuario=request.user,
                    questao=alt.questao,
                    acertou=acertou,
                )
            except Alternativa.DoesNotExist:
                pass

        # Pontuação: acerto em 30s=10pts, bônus de velocidade
        pontos = 0
        for item in respostas_raw:
            alt_id = item.get('alternativa_id')
            tempo  = float(item.get('tempo_seg', 30))
            if not alt_id:
                continue
            try:
                alt = Alternativa.objects.get(id=alt_id)
                if alt.correta:
                    bonus = max(0, round((30 - tempo) / 30 * 5))
                    pontos += 10 + bonus
            except Alternativa.DoesNotExist:
                pass

        tempo_medio = round(tempo_total / total, 1) if total else 0

        resultado = DesafioResultado.objects.create(
            usuario=request.user,
            pontos=pontos,
            total=total,
            acertos=acertos,
            tempo_medio_seg=tempo_medio,
        )

        # Atualiza streak + conquistas + XP
        meta, _ = MetaEstudo.objects.get_or_create(usuario=request.user)
        meta.atualizar_streak()
        verificar_conquistas(request.user)

        # XP por participação + bônus se acertou pelo menos 70%
        xp_ganho = 5 + (acertos * 3)
        if total and (acertos / total) >= 0.7:
            xp_ganho += 10  # bônus de boa pontuação
        try:
            _dar_xp(request.user, xp_ganho, request.session)
        except Exception:
            _silencioso("view_bloco_8")
        # Detecta novo recorde pessoal
        from django.db.models import Max
        melhor_anterior = (
            DesafioResultado.objects
            .filter(usuario=request.user)
            .exclude(id=resultado.id)
            .aggregate(m=Max('pontos'))['m']
        ) or 0
        novo_recorde = pontos > melhor_anterior

        # Top 10 global por melhor pontuação
        top10 = list(
            DesafioResultado.objects
            .values('usuario__username', 'usuario__first_name')
            .annotate(melhor=Max('pontos'))
            .order_by('-melhor')[:10]
        )
        top10_clean = [
            {
                'username': r['usuario__username'],
                'nome': r['usuario__first_name'] or r['usuario__username'],
                'melhor': r['melhor'],
                'is_me': r['usuario__username'] == request.user.username,
            }
            for r in top10
        ]

        # Posição do usuário no ranking global
        usuarios_acima = (
            DesafioResultado.objects
            .values('usuario_id')
            .annotate(melhor=Max('pontos'))
            .filter(melhor__gt=pontos)
            .count()
        )
        posicao = usuarios_acima + 1

        return JsonResponse({
            'pontos':       pontos,
            'acertos':      acertos,
            'total':        total,
            'tempo_medio':  tempo_medio,
            'xp_ganho':     xp_ganho,
            'novo_recorde': novo_recorde,
            'recorde_anterior': melhor_anterior,
            'posicao':      posicao,
            'top10':        top10_clean,
            'resultado_id': resultado.id,
        })

    # GET — prepara questões para o quiz JS
    cat_id = request.GET.get('categoria', '')
    # Dificuldade: segundos por questão + total de questões
    dificuldade = request.GET.get('dif', 'normal')  # facil | normal | dificil
    DIFICULDADES = {
        'facil':   {'seg': 45, 'total': 10, 'label': 'Fácil',   'cor': '#16a34a'},
        'normal':  {'seg': 30, 'total': 10, 'label': 'Normal',  'cor': '#f97316'},
        'dificil': {'seg': 20, 'total': 15, 'label': 'Difícil', 'cor': '#dc2626'},
    }
    if dificuldade not in DIFICULDADES:
        dificuldade = 'normal'
    cfg = DIFICULDADES[dificuldade]

    qs = Questao.objects.all()
    if cat_id:
        qs = qs.filter(categoria_id=cat_id)

    questoes = list(qs.order_by('?')[:cfg['total']])
    if len(questoes) < 5:
        return render(request, 'quiz/sem_questoes.html', {
            'mensagem': 'Não há questões suficientes para o Modo Desafio.',
        })

    questoes_data = []
    for q in questoes:
        alts = list(q.alternativa_set.all())
        questoes_data.append({
            'id': q.id,
            'texto': q.texto,
            'tipo': q.tipo,
            'categoria': q.categoria.nome,
            'imagem_url': q.imagem.url if q.imagem else None,
            'alternativas': [
                {'id': a.id, 'texto': a.texto, 'correta': a.correta}
                for a in alts
            ],
        })

    # Ranking global modo desafio
    from django.db.models import Max as _Max
    ranking_desafio = (
        DesafioResultado.objects
        .values('usuario__username', 'usuario__first_name')
        .annotate(melhor=_Max('pontos'))
        .order_by('-melhor')[:10]
    )
    ranking_list = [
        {
            'username': r['usuario__username'],
            'nome': r['usuario__first_name'] or r['usuario__username'],
            'melhor': r['melhor'],
            'is_me': r['usuario__username'] == request.user.username,
        }
        for r in ranking_desafio
    ]

    # Estatísticas pessoais
    minhas_partidas = DesafioResultado.objects.filter(usuario=request.user)
    stats_user = {
        'total_partidas': minhas_partidas.count(),
        'melhor_pontos':  minhas_partidas.aggregate(m=_Max('pontos'))['m'] or 0,
        'ultimas': list(
            minhas_partidas.order_by('-realizado_em')[:5]
            .values('pontos', 'acertos', 'total', 'tempo_medio_seg', 'realizado_em')
        ),
    }

    categorias = Categoria.objects.all().order_by('nome')

    import json as _json
    return render(request, 'quiz/modo_desafio.html', {
        'questoes_json': _json.dumps(questoes_data, ensure_ascii=False),
        'total_questoes': len(questoes_data),
        'segundos_por_questao': cfg['seg'],
        'dificuldade':    dificuldade,
        'dif_label':      cfg['label'],
        'dif_cor':        cfg['cor'],
        'categorias':     categorias,
        'cat_id':         cat_id,
        'ranking':        ranking_list,
        'stats_user':     stats_user,
    })


# ─── PUSH NOTIFICATIONS ───────────────────────────────────────────────────────

from django.conf import settings as django_settings

import logging
_view_logger = logging.getLogger("quiz.views")

def _silencioso(contexto="unknown", exc=None):
    """Loga exception silencioso em vez de 'pass' cru.
    Substitui `except Exception: pass` por chamada rastreavel."""
    if exc is None:
        import sys
        exc = sys.exc_info()[1]
    if exc is not None:
        _view_logger.debug("silencioso[%s]: %s", contexto, exc)


@login_required(login_url='account_login')
def push_config(request):
    """Retorna a chave pública VAPID para o frontend registrar o service worker."""
    return JsonResponse({'publicKey': django_settings.VAPID_PUBLIC_KEY})


@login_required(login_url='account_login')
@require_POST
def push_subscribe(request):
    """Salva ou atualiza a subscription de push do usuário."""
    try:
        data = json.loads(request.body)
        endpoint = data.get('endpoint', '')
        p256dh   = data.get('keys', {}).get('p256dh', '')
        auth     = data.get('keys', {}).get('auth', '')
        if not endpoint or not p256dh or not auth:
            return JsonResponse({'erro': 'Dados incompletos'}, status=400)

        # Impede User B "roubar" endpoint que ja pertence a User A:
        # se endpoint existe com outro dono, rejeita 403.
        existente = PushSubscription.objects.filter(endpoint=endpoint).first()
        if existente and existente.usuario_id != request.user.id:
            return JsonResponse({'erro': 'Endpoint pertence a outro usuario'}, status=403)

        PushSubscription.objects.update_or_create(
            endpoint=endpoint, usuario=request.user,
            defaults={'p256dh': p256dh, 'auth': auth},
        )
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'erro': str(e)}, status=500)


@login_required(login_url='account_login')
@require_POST
def push_unsubscribe(request):
    """Remove a subscription do usuário."""
    try:
        data = json.loads(request.body)
        endpoint = data.get('endpoint', '')
        PushSubscription.objects.filter(endpoint=endpoint).delete()
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'erro': str(e)}, status=500)


@login_required(login_url='account_login')
@require_POST
def push_test(request):
    """Envia uma notificacao de teste. Limpa subscriptions invalidas (410 Gone)
    automaticamente — sem isso acumulava lixo com o tempo (browser desinstalou
    PWA ou desativou permissoes, mas row ficava viva)."""
    from pywebpush import webpush, WebPushException
    subs = list(PushSubscription.objects.filter(usuario=request.user))
    erros = []
    invalidas = []
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=json.dumps({
                    'title': '🎯 SantuarioEdu',
                    'body': 'Notificações ativadas! Você receberá lembretes de revisão.',
                    'url': '/dashboard/',
                }),
                vapid_private_key=django_settings.VAPID_PRIVATE_KEY,
                vapid_claims=django_settings.VAPID_CLAIMS,
            )
        except WebPushException as e:
            # 410 Gone = subscription expirou/foi revogada no browser; deleta
            status = getattr(e.response, 'status_code', None) if e.response else None
            if status in (404, 410):
                invalidas.append(sub.pk)
            else:
                erros.append(str(e))

    if invalidas:
        PushSubscription.objects.filter(pk__in=invalidas).delete()

    if erros:
        return JsonResponse({'ok': False, 'erros': erros, 'limpas': len(invalidas)}, status=207)
    return JsonResponse({'ok': True, 'enviadas': len(subs) - len(invalidas), 'limpas': len(invalidas)})


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINT 12
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 12A — RESUMOS POR IA ────────────────────────────────────────────────────

@login_required(login_url='account_login')
def resumos_lista(request):
    """Lista de disciplinas com opção de gerar resumo por IA."""
    categorias = Categoria.objects.all().order_by('nome')
    resumos_existentes = {r.categoria_id: r for r in ResumoIA.objects.all()}
    dados = []
    for cat in categorias:
        dados.append({
            'id': cat.id,
            'nome': cat.nome,
            'tem_resumo': cat.id in resumos_existentes,
            'gerado_em': resumos_existentes[cat.id].gerado_em if cat.id in resumos_existentes else None,
        })
    return render(request, 'quiz/resumos_lista.html', {'categorias': dados})


@login_required(login_url='account_login')
@ratelimit(key='user', rate='15/h', method='GET', block=True)
def resumo_disciplina(request, categoria_id):
    """Exibe (ou gera) resumo IA de uma disciplina."""
    import json as _json
    categoria = get_object_or_404(Categoria, id=categoria_id)
    regenerar = request.GET.get('regenerar') == '1'

    resumo = None
    try:
        resumo = ResumoIA.objects.get(categoria=categoria)
    except ResumoIA.DoesNotExist:
        pass

    if resumo is None or regenerar:
        conteudo = ai_resumo_disciplina(categoria.nome, usuario=request.user)
        resumo, _ = ResumoIA.objects.update_or_create(
            categoria=categoria,
            defaults={'conteudo': conteudo},
        )

    # Stats do usuário nessa disciplina
    respostas = RespostaUsuario.objects.filter(
        usuario=request.user, questao__categoria=categoria
    )
    total   = respostas.count()
    acertos = respostas.filter(acertou=True).count()
    pct     = round(acertos / total * 100) if total else 0

    return render(request, 'quiz/resumo_disciplina.html', {
        'categoria':  categoria,
        'resumo':     resumo,
        'total':      total,
        'acertos':    acertos,
        'pct':        pct,
    })


# ─── MAPAS MENTAIS ────────────────────────────────────────────────────────────

@login_required(login_url='account_login')
def mapas_lista(request):
    """Lista disciplinas com opção de gerar mapa mental."""
    from ..models import MapaMental
    categorias = Categoria.objects.all().order_by('nome')
    mapas_existentes = {m.categoria_id: m for m in MapaMental.objects.all()}
    dados = []
    for cat in categorias:
        dados.append({
            'id': cat.id,
            'nome': cat.nome,
            'tem_mapa': cat.id in mapas_existentes,
            'gerado_em': mapas_existentes[cat.id].gerado_em if cat.id in mapas_existentes else None,
        })
    return render(request, 'quiz/mapas_lista.html', {'categorias': dados})


@login_required(login_url='account_login')
@ratelimit(key='user', rate='15/h', method='GET', block=True)
def mapa_mental(request, categoria_id):
    """Exibe mapa mental de uma disciplina — 2 fontes possiveis:
    1. **Hierarquia real** do banco (Categoria.filhos + Questao.assunto) —
       gerado localmente, sempre disponivel, sempre atualizado. Preferido
       quando a categoria tem sub-categorias reais no BD.
    2. **IA** — fallback pra categorias sem hierarquia estruturada ou quando
       o usuario forca via ?fonte=ia.

    Query params:
    - ?regenerar=1 -> se fonte IA, chama IA de novo
    - ?fonte=ia   -> forca uso da IA mesmo se hierarquia existe
    - ?fonte=bd   -> forca uso do BD (default se hierarquia disponivel)
    """
    from ..models import MapaMental
    from ..ai_service import ai_mapa_mental as _gerar_mapa_ia

    categoria = get_object_or_404(Categoria, id=categoria_id)
    fonte_pedida = request.GET.get('fonte', '').strip().lower()
    regenerar = request.GET.get('regenerar') == '1'

    # Se categoria tem descendentes OU assuntos suficientes, gera do BD
    tem_hierarquia_bd = bool(categoria.descendentes_ids())
    usar_bd = fonte_pedida == 'bd' or (tem_hierarquia_bd and fonte_pedida != 'ia')

    markdown = None
    if usar_bd:
        markdown = _mapa_mental_do_bd(categoria)
        # Se BD retornou None (categoria vazia sem assuntos), fallback IA
        if markdown:
            mapa, _ = MapaMental.objects.update_or_create(
                categoria=categoria,
                defaults={'mermaid': markdown},
            )
            fonte_usada = 'bd'
        else:
            usar_bd = False  # cai no branch IA abaixo

    if not usar_bd:
        # Fluxo IA — busca mapa existente OU gera novo
        mapa = MapaMental.objects.filter(categoria=categoria).first()

        # Auto-regenera se: nao existe, user pediu regenerar, OU formato antigo (Mermaid)
        precisa_gerar = (
            mapa is None
            or regenerar
            or not (mapa.mermaid or '').lstrip().startswith('#')
        )
        if precisa_gerar:
            codigo = _gerar_mapa_ia(categoria.nome, usuario=request.user)
            mapa, _ = MapaMental.objects.update_or_create(
                categoria=categoria,
                defaults={'mermaid': codigo},
            )
        fonte_usada = 'ia'

    # A esta altura, mapa.mermaid deve ser markdown (comeca com #). Se ainda
    # nao for (IA falhou), mostra fallback simples que markmap ainda renderiza.
    conteudo = (mapa.mermaid or '').lstrip()
    if not conteudo.startswith('#'):
        conteudo = f'# {categoria.nome}\n## Mapa em preparacao\n### Clique em Regenerar'
        mapa.mermaid = conteudo
        mapa.save(update_fields=['mermaid'])

    return render(request, 'quiz/mapa_mental.html', {
        'categoria':         categoria,
        'mapa':              mapa,
        'formato_antigo':    False,  # nunca chega aqui em formato antigo
        'fonte_usada':       fonte_usada,
        'tem_hierarquia_bd': tem_hierarquia_bd,
    })


def _mapa_mental_do_bd(categoria):
    """Constroi markdown do mapa mental usando a arvore real de Categoria
    + assuntos das questoes. Formato compativel com markmap: heading levels
    sequenciais (#, ##, ###...) sem pular niveis."""
    from django.db.models import Count

    linhas = [f'# {categoria.nome}']

    def _adicionar_sub(cat, nivel):
        """Recursivo. nivel = level de heading a usar pros filhos DIRETOS
        (subcategorias); assuntos vao em nivel+1."""
        prefixo = '#' * min(nivel, 5)
        filhos = list(cat.filhos.all().order_by('nome'))
        n_diretas = Questao.objects.filter(categoria=cat).count()

        for f in filhos:
            ids_sub = f.subarvore_ids()
            n_total = Questao.objects.filter(categoria_id__in=ids_sub).count()
            if n_total:
                linhas.append(f'{prefixo} {f.nome} ({n_total})')
            else:
                linhas.append(f'{prefixo} {f.nome}')
            _adicionar_sub(f, nivel + 1)

        # Se tem questoes diretas E nao pulou nivel: assuntos vao no MESMO
        # nivel de headings que os filhos teriam. Se nao tem filhos, os
        # assuntos ocupam o nivel atual (evita pular ## -> ###).
        if n_diretas and nivel < 5:
            top_assuntos = (Questao.objects.filter(categoria=cat)
                            .exclude(assunto__isnull=True).exclude(assunto='')
                            .values('assunto')
                            .annotate(n=Count('id'))
                            .order_by('-n')[:8])
            # Se tem filhos, assuntos ficam DENTRO da subcategoria "Geral"
            # do proprio cat (evita misturar layers). Se nao tem filhos,
            # assuntos ocupam o proprio nivel.
            for a in top_assuntos:
                linhas.append(f'{prefixo} {a["assunto"]} ({a["n"]})')

    _adicionar_sub(categoria, 2)

    if len(linhas) == 1:
        # Categoria sem filhos, sem assuntos, sem questoes classificadas.
        # Retorna None pra caller decidir fallback (usa IA em vez de BD vazio).
        return None

    return '\n'.join(linhas)


# ─── ESTATISTICAS DE INCIDENCIA ──────────────────────────────────────────────

@login_required(login_url='account_login')
def estatisticas_incidencia(request):
    """Painel de estatisticas: incidencia de temas por banca/ano.
    Usa apenas Questao (dados que ja temos), zero IA."""
    from django.db.models import Count
    import json as _json

    cat_id     = request.GET.get('cat', '')
    banca_flt  = request.GET.get('banca', '')

    qs = Questao.objects.all()
    if cat_id.isdigit():
        qs = qs.filter(categoria_id=int(cat_id))
    if banca_flt:
        qs = qs.filter(banca__iexact=banca_flt)

    # Por categoria (top 15)
    por_cat = list(qs.values('categoria__nome')
                   .annotate(total=Count('id'))
                   .order_by('-total')[:15])

    # Por ano (todos os anos com >= 1 questao)
    por_ano = list(qs.exclude(ano__isnull=True)
                   .values('ano')
                   .annotate(total=Count('id'))
                   .order_by('ano'))

    # Por banca (top 10)
    por_banca = list(qs.exclude(banca__isnull=True).exclude(banca='')
                     .values('banca')
                     .annotate(total=Count('id'))
                     .order_by('-total')[:10])

    # Distribuicao ME vs CE
    por_tipo = list(qs.values('tipo').annotate(total=Count('id')))

    return render(request, 'quiz/estatisticas_incidencia.html', {
        'categorias':    Categoria.objects.all().order_by('nome'),
        'bancas_disp':   [b['banca'] for b in Questao.objects.exclude(banca='').exclude(banca__isnull=True)
                          .values('banca').annotate(n=Count('id')).order_by('-n')[:15]],
        'cat_atual':     int(cat_id) if cat_id.isdigit() else None,
        'banca_atual':   banca_flt,
        'total_geral':   qs.count(),
        'por_cat_json':   _json.dumps(por_cat),
        'por_ano_json':   _json.dumps(por_ano),
        'por_banca_json': _json.dumps(por_banca),
        'por_tipo_json':  _json.dumps(por_tipo),
    })


# ─── TIMELINE DE LEIS ────────────────────────────────────────────────────────

@login_required(login_url='account_login')
def timelines_lista(request):
    """Lista todas as timelines de leis cadastradas."""
    from ..models import TimelineLei
    timelines = TimelineLei.objects.all().prefetch_related('categorias')
    return render(request, 'quiz/timelines_lista.html', {
        'timelines': timelines,
    })


@login_required(login_url='account_login')
def timeline_lei_detalhe(request, slug):
    """Exibe timeline de uma lei. Se ?regenerar=1, chama IA de novo.
    Rate limit aplicado SO no branch de regenerar (era global, contava
    leitura pura de timeline ja gerada — 15 leituras/hora bloqueava user PRO)."""
    from ..models import TimelineLei
    from ..ai_service import ai_timeline_lei

    tl = get_object_or_404(TimelineLei, slug=slug)
    regenerar = request.GET.get('regenerar') == '1'

    if regenerar or not tl.mudancas_json:
        # Aplica rate limit manualmente so quando chama IA
        from django_ratelimit.core import is_ratelimited
        limited = is_ratelimited(
            request=request, group='timeline_lei_regenerar',
            key='user', rate='15/h', method='GET', increment=True,
        )
        if limited:
            messages.error(request, 'Muitas regeracoes por hora. Aguarde 60min.')
            return redirect('timelines_lista')

        dados = ai_timeline_lei(tl.titulo, usuario=request.user)
        tl.resumo = dados.get('resumo', tl.resumo)
        tl.mudancas_json = dados.get('mudancas', [])
        if dados.get('ano_original'):
            tl.ano_original = int(dados['ano_original'])
        tl.save()

    return render(request, 'quiz/timeline_lei_detalhe.html', {
        'timeline': tl,
    })


# ─── COMPARATIVO ENTRE BANCAS ────────────────────────────────────────────────

@login_required(login_url='account_login')
def comparativo_lista(request):
    """Lista disciplinas que tem comparativo ou permite gerar."""
    from ..models import ComparativoBanca
    categorias = Categoria.objects.all().order_by('nome')
    tem_comp = set(ComparativoBanca.objects.values_list('categoria_id', flat=True).distinct())
    dados = [{
        'id': c.id, 'nome': c.nome,
        'tem_comparativo': c.id in tem_comp,
        'total_bancas': ComparativoBanca.objects.filter(categoria=c).count() if c.id in tem_comp else 0,
    } for c in categorias]
    return render(request, 'quiz/comparativo_lista.html', {'categorias': dados})


@login_required(login_url='account_login')
@ratelimit(key='user', rate='15/h', method='GET', block=True)
def comparativo_categoria(request, categoria_id):
    """Comparativo de todas as bancas relevantes num tema."""
    from ..models import ComparativoBanca
    from ..ai_service import ai_comparativo_banca
    from django.db.models import Count

    categoria = get_object_or_404(Categoria, id=categoria_id)
    regenerar = request.GET.get('regenerar') == '1'

    # Descobre quais bancas ja tem questoes desse tema no BD
    bancas_com_q = (Questao.objects
                    .filter(categoria=categoria)
                    .exclude(banca='').exclude(banca__isnull=True)
                    .values('banca')
                    .annotate(n=Count('id'))
                    .order_by('-n')[:6])
    bancas = [b['banca'] for b in bancas_com_q]

    if not bancas:
        # Fallback: bancas mais comuns em geral
        bancas = ['Cebraspe', 'CESPE', 'FGV', 'FCC']

    comparativos = []
    for banca_nome in bancas:
        cb, created = ComparativoBanca.objects.get_or_create(
            categoria=categoria, banca=banca_nome,
        )
        if created or regenerar or not cb.estilo:
            dados = ai_comparativo_banca(categoria.nome, banca_nome, usuario=request.user)
            cb.estilo      = dados.get('estilo', '')
            cb.dificuldade = dados.get('dificuldade', '')
            cb.pegadinhas  = dados.get('pegadinhas', '')
            cb.formato     = dados.get('formato', '')
            cb.save()
        comparativos.append(cb)

    return render(request, 'quiz/comparativo_categoria.html', {
        'categoria': categoria,
        'comparativos': comparativos,
    })


# ─── GLOSSARIO ───────────────────────────────────────────────────────────────

@login_required(login_url='account_login')
def glossario_lista(request):
    """Glossario de termos. Suporta ?q=busca e ?cat=id."""
    from ..models import TermoGlossario
    from django.db.models import Q

    q_str  = request.GET.get('q', '').strip()
    cat_id = request.GET.get('cat', '')

    qs = TermoGlossario.objects.all().prefetch_related('categorias')
    if q_str:
        qs = qs.filter(Q(termo__icontains=q_str) | Q(definicao__icontains=q_str))
    if cat_id.isdigit():
        qs = qs.filter(categorias__id=int(cat_id)).distinct()

    return render(request, 'quiz/glossario_lista.html', {
        'termos':     qs[:200],
        'categorias': Categoria.objects.all().order_by('nome'),
        'q':          q_str,
        'cat_atual':  int(cat_id) if cat_id.isdigit() else None,
        'total':      qs.count(),
    })


@login_required(login_url='account_login')
@ratelimit(key='user', rate='6/h', method='POST', block=True)
def glossario_gerar_categoria(request, categoria_id):
    """Gera 30 termos de uma categoria via IA e salva (usado por staff)."""
    from ..models import TermoGlossario
    from ..ai_service import ai_glossario_termos

    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'erro': 'so staff'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'erro': 'metodo invalido'}, status=405)

    categoria = get_object_or_404(Categoria, id=categoria_id)
    termos = ai_glossario_termos(categoria.nome, qtd=30, usuario=request.user)

    criados = 0
    for t in termos:
        termo = (t.get('termo') or '').strip()
        definicao = (t.get('definicao') or '').strip()
        if not termo or not definicao:
            continue
        obj, created = TermoGlossario.objects.get_or_create(
            termo=termo,
            defaults={
                'definicao': definicao,
                'exemplo_uso': (t.get('exemplo_uso') or '').strip(),
            },
        )
        obj.categorias.add(categoria)
        if created:
            criados += 1

    return JsonResponse({'ok': True, 'criados': criados, 'total_recebido': len(termos)})


# ─── 12B — GRUPOS DE ESTUDO ──────────────────────────────────────────────────

@login_required(login_url='account_login')
def grupos_lista(request):
    """Lista grupos do usuário + formulário de criação/entrada."""
    meus_grupos = GrupoEstudo.objects.filter(membros__usuario=request.user).distinct()

    if request.method == 'POST':
        acao = request.POST.get('acao')

        if acao == 'criar':
            nome = request.POST.get('nome', '').strip()
            desc = request.POST.get('descricao', '').strip()
            if nome:
                grupo = GrupoEstudo.objects.create(
                    nome=nome, descricao=desc, criador=request.user
                )
                MembroGrupo.objects.create(grupo=grupo, usuario=request.user, papel='admin')
                Notificacao.criar(
                    request.user, 'grupo',
                    f'Grupo "{grupo.nome}" criado!',
                    f'Compartilhe o código {grupo.codigo} com seus colegas.',
                    link=f'/grupos/{grupo.id}/',
                )
                messages.success(request, f'Grupo "{grupo.nome}" criado! Código: {grupo.codigo}')
                return redirect('grupo_detalhe', grupo_id=grupo.id)
            else:
                messages.error(request, 'Informe um nome para o grupo.')

        elif acao == 'entrar':
            codigo = request.POST.get('codigo', '').strip().upper()
            try:
                grupo = GrupoEstudo.objects.get(codigo=codigo)
                _, criado = MembroGrupo.objects.get_or_create(
                    grupo=grupo, usuario=request.user,
                    defaults={'papel': 'membro'}
                )
                if criado:
                    messages.success(request, f'Você entrou no grupo "{grupo.nome}"!')
                    Notificacao.criar(
                        request.user, 'grupo',
                        f'Você entrou no grupo "{grupo.nome}"',
                        link=f'/grupos/{grupo.id}/',
                    )
                else:
                    messages.info(request, f'Você já é membro do grupo "{grupo.nome}".')
                return redirect('grupo_detalhe', grupo_id=grupo.id)
            except GrupoEstudo.DoesNotExist:
                messages.error(request, f'Código "{codigo}" não encontrado.')

        return redirect('grupos_lista')

    return render(request, 'quiz/grupos_lista.html', {'meus_grupos': meus_grupos})


@login_required(login_url='account_login')
def grupo_detalhe(request, grupo_id):
    """Detalhe de um grupo: membros, ranking, feed de atividade."""
    grupo = get_object_or_404(GrupoEstudo, id=grupo_id)
    # Somente membros podem ver
    if not MembroGrupo.objects.filter(grupo=grupo, usuario=request.user).exists():
        messages.error(request, 'Você não é membro deste grupo.')
        return redirect('grupos_lista')

    membros = MembroGrupo.objects.filter(grupo=grupo).select_related('usuario')
    membros_ids = [m.usuario_id for m in membros]

    # Ranking interno: questões respondidas nos últimos 30 dias
    trinta_dias = timezone.now() - timedelta(days=30)
    ranking_membros = []
    for m in membros:
        r = RespostaUsuario.objects.filter(usuario=m.usuario, data__gte=trinta_dias)
        total   = r.count()
        acertos = r.filter(acertou=True).count()
        pct     = round(acertos / total * 100) if total else 0
        try:
            streak = m.usuario.meta.streak_atual
        except Exception:
            streak = 0
        ranking_membros.append({
            'usuario':  m.usuario,
            'papel':    m.papel,
            'total':    total,
            'acertos':  acertos,
            'pct':      pct,
            'streak':   streak,
        })
    ranking_membros.sort(key=lambda x: (-x['total'], -x['pct']))

    eh_admin = MembroGrupo.objects.filter(
        grupo=grupo, usuario=request.user, papel='admin'
    ).exists()

    # ── FEED DE ATIVIDADE (ultimos 7 dias) ────────────────────────
    # Coleta eventos recentes dos membros e mistura numa timeline.
    # Cada evento tem: tipo, usuario, texto, data, icone/cor.
    sete_dias = timezone.now() - timedelta(days=7)
    eventos = []

    # 1. Conquistas desbloqueadas
    conquistas_recentes = (Conquista.objects
        .filter(usuario_id__in=membros_ids, desbloqueado_em__gte=sete_dias)
        .select_related('usuario')
        .order_by('-desbloqueado_em')[:30])
    for c in conquistas_recentes:
        meta_c = CONQUISTAS_META.get(c.codigo, {})
        raridade = meta_c.get('raridade', 'comum')
        eventos.append({
            'tipo': 'conquista',
            'usuario': c.usuario,
            'texto': f'desbloqueou "{meta_c.get("label", c.codigo)}"',
            'emoji': meta_c.get('emoji', '🏆'),
            'data': c.desbloqueado_em,
            'cor': 'amber' if raridade in ('lendaria', 'epica') else 'primary',
            'raridade': raridade,
        })

    # 2. Simulados finalizados
    from django.db.models import Count, Q
    sims_recentes = (Simulado.objects
        .filter(usuario_id__in=membros_ids, finalizado=True,
                finalizado_em__gte=sete_dias)
        .select_related('usuario')
        .prefetch_related('respostas')
        .order_by('-finalizado_em')[:20])
    for s in sims_recentes:
        respostas = s.respostas.all()
        respondidas = [r for r in respostas if r.acertou is not None]
        acertos = sum(1 for r in respondidas if r.acertou)
        total = len(respondidas)
        if total < 5:  # ignora simulados quase vazios
            continue
        pct = round(acertos / total * 100) if total else 0
        eventos.append({
            'tipo': 'simulado',
            'usuario': s.usuario,
            'texto': f'fez {acertos}/{total} no simulado ({pct}%)',
            'emoji': '🏅' if pct >= 80 else '📝',
            'data': s.finalizado_em,
            'cor': 'secondary' if pct >= 70 else 'primary',
        })

    # 3. Streaks marcos (checa streak_atual atual — nao historico)
    for m in membros:
        try:
            streak = m.usuario.meta.streak_atual
        except Exception:
            continue
        for marco in (30, 14, 7, 3):
            if streak == marco:
                eventos.append({
                    'tipo': 'streak',
                    'usuario': m.usuario,
                    'texto': f'está em {streak} dias de streak',
                    'emoji': '💎' if streak >= 30 else '🔥',
                    'data': timezone.now() - timedelta(hours=1),  # aproxima
                    'cor': 'error',
                })
                break

    # Ordena por data decrescente
    eventos.sort(key=lambda e: e['data'], reverse=True)
    eventos = eventos[:20]  # limita display

    return render(request, 'quiz/grupo_detalhe.html', {
        'grupo':    grupo,
        'ranking':  ranking_membros,
        'eh_admin': eh_admin,
        'total_membros': membros.count(),
        'feed_eventos': eventos,
    })


@login_required(login_url='account_login')
@require_POST
def sair_grupo(request, grupo_id):
    grupo = get_object_or_404(GrupoEstudo, id=grupo_id)
    MembroGrupo.objects.filter(grupo=grupo, usuario=request.user).delete()
    messages.success(request, f'Você saiu do grupo "{grupo.nome}".')
    return redirect('grupos_lista')


# ─── 12C — CENTRAL DE NOTIFICAÇÕES ──────────────────────────────────────────

@login_required(login_url='account_login')
def central_notificacoes(request):
    """Lista todas as notificações do usuário."""
    notifs = Notificacao.objects.filter(usuario=request.user)
    # Marcar todas como lidas ao abrir
    notifs.filter(lida=False).update(lida=True)
    return render(request, 'quiz/central_notificacoes.html', {
        'notificacoes': notifs[:50],
    })


@login_required(login_url='account_login')
def api_notificacoes_recentes(request):
    """Retorna as 5 ultimas notificacoes (nao-lidas priorizadas + preenche
    com lidas recentes ate 5). Consumido pelo dropdown do sino no header."""
    from django.utils.timesince import timesince
    from django.utils import timezone as _tz

    nao_lidas = list(Notificacao.objects.filter(
        usuario=request.user, lida=False,
    ).order_by('-criada_em')[:5])

    faltam = 5 - len(nao_lidas)
    lidas_recentes = []
    if faltam > 0:
        lidas_recentes = list(Notificacao.objects.filter(
            usuario=request.user, lida=True,
        ).order_by('-criada_em')[:faltam])

    todas = nao_lidas + lidas_recentes

    def _serializar(n):
        # Emoji do tipo (primeiro caractere do choice display)
        tipos_emoji = {
            'conquista': '🏆', 'streak': '🔥', 'srs': '🧠',
            'grupo': '👥', 'sistema': '📢',
        }
        return {
            'id': n.id,
            'tipo': n.tipo,
            'emoji': tipos_emoji.get(n.tipo, '🔔'),
            'titulo': n.titulo,
            'mensagem': (n.mensagem or '')[:120],
            'lida': n.lida,
            'link': n.link or '',
            'ha': timesince(n.criada_em, _tz.now()).split(',')[0] + ' atras',
        }

    return JsonResponse({
        'total_nao_lidas': len(nao_lidas),
        'notificacoes': [_serializar(n) for n in todas],
    })


# Helper: criar notificação de conquista (chamado por verificar_conquistas)
def _notif_conquista(user, codigo):
    meta = CONQUISTAS_META.get(codigo, {})
    Notificacao.criar(
        user, 'conquista',
        f'{meta.get("emoji","🏆")} {meta.get("label", codigo)}',
        meta.get('desc', ''),
        link='/conquistas/',
    )


# ─── 12D — EXPORTAÇÃO ────────────────────────────────────────────────────────

@login_required(login_url='account_login')
def exportar_historico_csv(request):
    """Baixa o histórico completo de respostas em CSV."""
    import csv
    from django.http import StreamingHttpResponse

    respostas = (
        RespostaUsuario.objects
        .filter(usuario=request.user)
        .select_related('questao', 'questao__categoria')
        .order_by('-data')
    )

    def gerar_linhas():
        yield 'Data,Disciplina,Questão (início),Acertou\n'
        for r in respostas:
            data   = r.data.strftime('%d/%m/%Y %H:%M')
            disc   = r.questao.categoria.nome if r.questao.categoria else ''
            texto  = r.questao.texto[:80].replace('"', '""')
            acerto = 'Sim' if r.acertou else 'Não'
            yield f'"{data}","{disc}","{texto}","{acerto}"\n'

    resp = StreamingHttpResponse(gerar_linhas(), content_type='text/csv; charset=utf-8-sig')
    resp['Content-Disposition'] = 'attachment; filename="historico_prf_master.csv"'
    return resp


@login_required(login_url='account_login')
def certificado_progresso(request):
    """Página de certificado de horas de estudo (@media print = PDF)."""
    from django.utils import timezone as tz

    respostas = RespostaUsuario.objects.filter(usuario=request.user)
    total     = respostas.count()
    acertos   = respostas.filter(acertou=True).count()
    pct       = round(acertos / total * 100, 1) if total else 0

    sessoes   = SessaoEstudo.objects.filter(usuario=request.user)
    total_seg = sessoes.aggregate(s=Sum('duracao_seg'))['s'] or 0
    horas     = total_seg // 3600
    minutos   = (total_seg % 3600) // 60

    try:
        meta  = request.user.meta
        streak_max = meta.streak_maximo
    except Exception:
        streak_max = 0

    conquistas = Conquista.objects.filter(usuario=request.user)
    simulados  = Simulado.objects.filter(usuario=request.user, finalizado=True).count()

    return render(request, 'quiz/certificado.html', {
        'usuario':    request.user,
        'total':      total,
        'acertos':    acertos,
        'pct':        pct,
        'horas':      horas,
        'minutos':    minutos,
        'streak_max': streak_max,
        'conquistas': conquistas,
        'simulados':  simulados,
        'data_hoje':  tz.localdate(),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINT 13
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 13A — SIMULADO PERSONALIZADO ────────────────────────────────────────────

@login_required(login_url='account_login')
def simulado_personalizado(request):
    """
    Simulado Personalizado: distribuição manual de questões por disciplina + perfis rápidos.
    GET  → exibe perfis pré-configurados e tabela de distribuição
    POST → cria Simulado com a distribuição configurada
    """
    categorias = Categoria.objects.annotate(qtd=Count('questao')).filter(qtd__gt=0).order_by('nome')

    if request.method == 'POST':
        resp = _check_pode_criar_simulado(request, fallback_url='simulado_personalizado')
        if resp: return resp

        # Coleta distribuição categoria → quantidade
        distribuicao = {}
        for cat in categorias:
            try:
                n = int(request.POST.get(f'cat_{cat.id}', '0') or 0)
            except ValueError:
                n = 0
            if n > 0:
                distribuicao[cat.id] = min(n, cat.qtd)

        total_questoes = sum(distribuicao.values())
        if total_questoes < 1:
            messages.error(request, 'Selecione pelo menos 1 questão.')
            return redirect('simulado_personalizado')

        # Tempo: padrão 3 min/questão, mínimo 15min, máximo 6h
        tempo_min = max(15, min(int(request.POST.get('tempo_min', total_questoes * 3)), 360))

        # Sample questões por categoria — filtra apenas revisadas (consistente
        # com os outros modos; antes vazava IA nao aprovada)
        questoes_selecionadas = []
        for cat_id, qtd in distribuicao.items():
            qs = list(Questao.objects.filter(
                categoria_id=cat_id, revisada=True, rejeitada_definitiva=False,
            ).order_by('?')[:qtd])
            questoes_selecionadas.extend(qs)

        import random
        random.shuffle(questoes_selecionadas)

        simulado = Simulado.objects.create(
            usuario=request.user,
            duracao_segundos=tempo_min * 60,
        )

        RespostaSimulado.objects.bulk_create([
            RespostaSimulado(simulado=simulado, questao=q, ordem=i + 1)
            for i, q in enumerate(questoes_selecionadas)
        ])

        messages.success(request, f'Simulado criado com {len(questoes_selecionadas)} questões.')
        return redirect('simulado_questao', simulado_id=simulado.id, numero=1)

    cats_info = [{'id': c.id, 'nome': c.nome, 'disponivel': c.qtd} for c in categorias]
    return render(request, 'quiz/simulado_personalizado.html', {
        'categorias':   cats_info,
        'perfis':       PRF_EDITAL_PERFIS,
        'perfis_json':  json.dumps(PRF_EDITAL_PERFIS),
    })


# ─── 13B — METAS AVANÇADAS ────────────────────────────────────────────────────

@login_required(login_url='account_login')
def metas_avancadas(request):
    """Gerencia metas semanais/mensais do usuário."""
    import datetime as dt

    hoje = timezone.localdate()

    if request.method == 'POST':
        acao = request.POST.get('acao')

        if acao == 'criar':
            periodo        = request.POST.get('periodo', 'semanal')
            questoes_alvo  = int(request.POST.get('questoes_alvo', 50))
            aprov_alvo     = int(request.POST.get('aproveitamento_alvo', 70))

            if periodo == 'semanal':
                inicio = hoje - dt.timedelta(days=hoje.weekday())
                fim    = inicio + dt.timedelta(days=6)
            else:
                inicio = hoje.replace(day=1)
                # último dia do mês
                next_m = (inicio.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
                fim    = next_m - dt.timedelta(days=1)

            # Desativa metas antigas do mesmo período
            MetaAvancada.objects.filter(
                usuario=request.user, periodo=periodo, ativa=True
            ).update(ativa=False)

            MetaAvancada.objects.create(
                usuario=request.user,
                periodo=periodo,
                questoes_alvo=max(1, questoes_alvo),
                aproveitamento_alvo=max(0, min(100, aprov_alvo)),
                inicio=inicio,
                fim=fim,
            )
            messages.success(request, 'Meta criada com sucesso!')

        elif acao == 'desativar':
            meta_id = request.POST.get('meta_id')
            MetaAvancada.objects.filter(id=meta_id, usuario=request.user).update(ativa=False)

        return redirect('metas_avancadas')

    # Metas ativas
    metas_ativas = MetaAvancada.objects.filter(usuario=request.user, ativa=True)
    metas_hist   = MetaAvancada.objects.filter(usuario=request.user, ativa=False).order_by('-inicio')[:10]

    metas_com_prog = []
    for m in metas_ativas:
        prog = m.calcular_progresso()
        metas_com_prog.append({'meta': m, 'prog': prog})

    return render(request, 'quiz/metas_avancadas.html', {
        'metas_ativas': metas_com_prog,
        'metas_hist':   metas_hist,
        'hoje':         hoje,
    })


# ─── 13C — COMENTÁRIOS EM QUESTÕES ───────────────────────────────────────────


# ─── 13D — FILTRO POR ASSUNTO ────────────────────────────────────────────────


# ─── 13E — PAINEL ADMIN AVANÇADO ─────────────────────────────────────────────

@login_required(login_url='account_login')
@user_passes_test(_is_staff, login_url='home')
def admin_stats(request):
    """Painel de estatísticas avançadas da plataforma."""
    import json as _json
    from django.db.models import Max
    from datetime import date

    hoje      = timezone.localdate()
    trinta    = timezone.now() - timedelta(days=30)
    sete      = timezone.now() - timedelta(days=7)

    # ── Usuários ──────────────────────────────────────────────────────────────
    total_users   = User.objects.filter(is_active=True).count()
    ativos_30d    = RespostaUsuario.objects.filter(data__gte=trinta).values('usuario').distinct().count()
    ativos_7d     = RespostaUsuario.objects.filter(data__gte=sete).values('usuario').distinct().count()
    novos_30d     = User.objects.filter(date_joined__gte=trinta).count()

    # ── Questões ──────────────────────────────────────────────────────────────
    total_questoes   = Questao.objects.count()
    total_respostas  = RespostaUsuario.objects.count()
    total_acertos    = RespostaUsuario.objects.filter(acertou=True).count()
    pct_plat         = round(total_acertos / total_respostas * 100, 1) if total_respostas else 0
    respostas_hoje   = RespostaUsuario.objects.filter(data__date=hoje).count()

    # ── Questões mais erradas (top 10) ────────────────────────────────────────
    mais_erradas = (
        RespostaUsuario.objects.filter(acertou=False)
        .values('questao__id', 'questao__texto', 'questao__categoria__nome')
        .annotate(erros=Count('id'))
        .order_by('-erros')[:10]
    )

    # ── Usuários em risco (sem estudar há >3 dias, streak > 0) ────────────────
    tres_dias = timezone.now() - timedelta(days=3)
    em_risco = (
        MetaEstudo.objects.filter(streak_atual__gt=0)
        .annotate(ultima=Max('usuario__respostausuario__data'))
        .filter(ultima__lt=tres_dias)
        .select_related('usuario')[:10]
    )

    # ── Atividade diária (últimos 30 dias) ────────────────────────────────────
    atividade_30d = (
        RespostaUsuario.objects.filter(data__gte=trinta)
        .annotate(dia=TruncDate('data'))
        .values('dia')
        .annotate(respostas=Count('id'), usuarios=Count('usuario', distinct=True))
        .order_by('dia')
    )
    serie_atividade = [
        {'dia': str(a['dia']), 'respostas': a['respostas'], 'usuarios': a['usuarios']}
        for a in atividade_30d
    ]

    # ── Top usuários (últimos 30 dias) ────────────────────────────────────────
    top_usuarios = (
        RespostaUsuario.objects.filter(data__gte=trinta)
        .values('usuario__username', 'usuario__first_name')
        .annotate(total=Count('id'), acertos=Count('id', filter=Q(acertou=True)))
        .order_by('-total')[:10]
    )

    # ── Por disciplina ────────────────────────────────────────────────────────
    por_cat = (
        RespostaUsuario.objects
        .values('questao__categoria__nome')
        .annotate(total=Count('id'), acertos=Count('id', filter=Q(acertou=True)))
        .order_by('-total')
    )
    cats_stats = [
        {
            'nome':    c['questao__categoria__nome'] or 'Sem categoria',
            'total':   c['total'],
            'acertos': c['acertos'],
            'pct':     round(c['acertos'] / c['total'] * 100) if c['total'] else 0,
        }
        for c in por_cat
    ]

    return render(request, 'quiz/admin/stats.html', {
        'total_users':     total_users,
        'ativos_30d':      ativos_30d,
        'ativos_7d':       ativos_7d,
        'novos_30d':       novos_30d,
        'total_questoes':  total_questoes,
        'total_respostas': total_respostas,
        'pct_plat':        pct_plat,
        'respostas_hoje':  respostas_hoje,
        'mais_erradas':    list(mais_erradas),
        'em_risco':        list(em_risco),
        'cats_stats':      cats_stats,
        'top_usuarios':    list(top_usuarios),
        'serie_json':      _json.dumps(serie_atividade),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINT 14
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 14A — RANKING GLOBAL APRIMORADO ─────────────────────────────────────────
# (view ranking já existe no Sprint 6 — template será redesenhado)


# ─── 14B — ESTUDAR DAS FAVORITAS ─────────────────────────────────────────────

@login_required(login_url='account_login')
def quiz_favoritas(request):
    """Quiz usando apenas questões favoritas do usuário (modo estudo)."""
    if request.method == 'POST':
        return iniciar_quiz(request)

    favoritas_ids = list(
        QuestaoFavorita.objects.filter(usuario=request.user)
        .values_list('questao_id', flat=True)
    )
    if not favoritas_ids:
        return render(request, 'quiz/sem_questoes.html', {
            'mensagem': 'Você não tem questões favoritas ainda.',
            'subtexto': 'Marque questões com ⭐ durante o estudo para revisá-las aqui.',
        })

    # Prioriza questões com mais erros
    erros_map = {
        r['questao_id']: r['n']
        for r in RespostaUsuario.objects.filter(
            usuario=request.user, questao_id__in=favoritas_ids, acertou=False
        ).values('questao_id').annotate(n=Count('id'))
    }

    # Questão com mais erros primeiro, ou aleatória se empate
    questao = (
        Questao.objects.filter(id__in=favoritas_ids)
        .order_by('?')
        .first()
    )
    # Prefere a mais errada se existir
    if erros_map:
        mais_errada_id = max(erros_map, key=erros_map.get)
        questao = Questao.objects.get(id=mais_errada_id)

    is_favorita = True  # Sempre favorita neste modo
    anotacao = AnotacaoUsuario.objects.filter(
        usuario=request.user, questao=questao
    ).first()

    return render(request, 'quiz/responder.html', {
        'questao':         questao,
        'categoria_id':    questao.categoria_id,
        'filtros':         {},
        'modo_favoritas':  True,
        'total_favoritas': len(favoritas_ids),
        'is_favorita':     is_favorita,
        'anotacao':        anotacao,
    })


# ─── 14C — ANÁLISE INTELIGENTE DE ERROS ──────────────────────────────────────


# ─── 14D — POMODORO TIMER ────────────────────────────────────────────────────
# Implementado via JS no dashboard.html — sem view backend necessário.


# ─── 14E — FEED DO GRUPO (patch em grupo_detalhe) ────────────────────────────
# O feed de atividade é adicionado ao grupo_detalhe existente abaixo.
# A view original está no Sprint 12 — vamos criar uma versão aprimorada aqui
# que substitui a anterior ao incluir o feed.

@login_required(login_url='account_login')
def grupo_detalhe_v2(request, grupo_id):
    """
    Versão aprimorada do grupo_detalhe com feed de atividade.
    Substitui a view original da Sprint 12.
    """
    grupo = get_object_or_404(GrupoEstudo, id=grupo_id)
    if not MembroGrupo.objects.filter(grupo=grupo, usuario=request.user).exists():
        messages.error(request, 'Você não é membro deste grupo.')
        return redirect('grupos_lista')

    membros = MembroGrupo.objects.filter(grupo=grupo).select_related('usuario')
    trinta_dias = timezone.now() - timedelta(days=30)

    # ── Ranking interno ───────────────────────────────────────────────────────
    ranking_membros = []
    usuarios_ids = [m.usuario_id for m in membros]
    for m in membros:
        r = RespostaUsuario.objects.filter(usuario=m.usuario, data__gte=trinta_dias)
        total   = r.count()
        acertos = r.filter(acertou=True).count()
        pct     = round(acertos / total * 100) if total else 0
        try:
            streak = m.usuario.meta.streak_atual
        except Exception:
            streak = 0
        ranking_membros.append({
            'usuario': m.usuario,
            'papel':   m.papel,
            'total':   total,
            'acertos': acertos,
            'pct':     pct,
            'streak':  streak,
        })
    ranking_membros.sort(key=lambda x: (-x['total'], -x['pct']))

    # ── Feed de atividade (últimas 30 entradas nos últimos 7 dias) ────────────
    sete_dias = timezone.now() - timedelta(days=7)
    feed_qs = (
        RespostaUsuario.objects
        .filter(usuario_id__in=usuarios_ids, data__gte=sete_dias)
        .select_related('usuario', 'questao', 'questao__categoria')
        .order_by('-data')[:40]
    )
    # Agrupa por usuário+hora (sessões de 1h)
    from collections import defaultdict
    sessoes_feed: dict = defaultdict(lambda: {'usuario': None, 'questoes': 0, 'acertos': 0, 'cat': '', 'data': None})
    for r in feed_qs:
        key = (r.usuario_id, r.data.replace(minute=0, second=0, microsecond=0))
        s = sessoes_feed[key]
        s['usuario'] = r.usuario
        s['questoes'] += 1
        if r.acertou:
            s['acertos'] += 1
        s['cat'] = r.questao.categoria.nome if r.questao.categoria else ''
        if s['data'] is None or r.data > s['data']:
            s['data'] = r.data

    feed = sorted(sessoes_feed.values(), key=lambda x: x['data'] or timezone.now(), reverse=True)[:15]

    # ── Conquistas recentes dos membros (últimos 7 dias) ──────────────────────
    conquistas_recentes = (
        Conquista.objects
        .filter(usuario_id__in=usuarios_ids, desbloqueado_em__gte=sete_dias)
        .select_related('usuario')
        .order_by('-desbloqueado_em')[:10]
    )

    eh_admin = MembroGrupo.objects.filter(
        grupo=grupo, usuario=request.user, papel='admin'
    ).exists()

    return render(request, 'quiz/grupo_detalhe.html', {
        'grupo':               grupo,
        'ranking':             ranking_membros,
        'eh_admin':            eh_admin,
        'total_membros':       membros.count(),
        'feed':                feed,
        'conquistas_recentes': list(conquistas_recentes),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINT 15
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 15A — QUESTÃO DO DIA ────────────────────────────────────────────────────

@login_required(login_url='account_login')
def questao_do_dia(request):
    """
    Desafio diário: 1 ÚNICA questão extremamente difícil por dia.
    Prioriza questões com banca='SantuarioEdu (Questão do Dia)' que são
    questões cuidadosamente elaboradas sobre atualidades. Se não houver
    questão destacada disponível, fallback para questão aleatória seeded.
    """
    import random as _random
    import hashlib as _hashlib
    hoje = timezone.localdate()

    # Pool de "questões do dia" cuidadosamente elaboradas (banca destacada).
    # Cada uma é exibida em rotação, uma por dia.
    pool_destaque = list(
        Questao.objects.filter(banca='SantuarioEdu (Questão do Dia)')
        .values_list('id', flat=True)
    )

    seed_str = str(hoje)
    seed_int = int(_hashlib.md5(seed_str.encode(), usedforsecurity=False).hexdigest(), 16) % (2 ** 32)
    _random.seed(seed_int)

    if pool_destaque:
        # Escolhe 1 da pool de destaque
        ids_hoje = [_random.choice(pool_destaque)]
    else:
        # Fallback: 1 questão aleatória do banco inteiro
        todos_ids = list(Questao.objects.values_list('id', flat=True))
        if not todos_ids:
            return render(request, 'quiz/sem_questoes.html', {
                'mensagem': 'Sem questões cadastradas para o desafio do dia.'
            })
        ids_hoje = [_random.choice(todos_ids)]

    questoes_dia = list(Questao.objects.filter(id__in=ids_hoje).prefetch_related('alternativa_set'))

    # Registro do usuário para hoje (apenas 1 questão por dia)
    registro, _ = QuestaoDodia.objects.get_or_create(
        usuario=request.user, data=hoje,
        defaults={'total': 1},
    )
    if registro.total != 1:
        registro.total = 1
        registro.save(update_fields=['total'])

    # POST: responder uma questão
    if request.method == 'POST':
        alternativa_id = request.POST.get('alternativa_id')
        if alternativa_id:
            try:
                alt = Alternativa.objects.select_related('questao').get(id=alternativa_id)
                acertou = alt.correta
                RespostaUsuario.objects.create(
                    usuario=request.user, questao=alt.questao, acertou=acertou
                )
                meta, _ = MetaEstudo.objects.get_or_create(usuario=request.user)
                meta.atualizar_streak()
                verificar_conquistas(request.user)

                # Atualiza SRS
                srs, _ = RevisaoEspacada.objects.get_or_create(
                    usuario=request.user, questao=alt.questao,
                    defaults={'proxima_revisao': hoje}
                )
                srs.atualizar(acertou)

                # Conta quantas das 5 foram respondidas hoje
                resps_hoje = RespostaUsuario.objects.filter(
                    usuario=request.user,
                    questao_id__in=ids_hoje,
                    data__date=hoje,
                ).count()
                acertos_hoje = RespostaUsuario.objects.filter(
                    usuario=request.user,
                    questao_id__in=ids_hoje,
                    data__date=hoje,
                    acertou=True,
                ).count()

                if resps_hoje >= len(questoes_dia) and not registro.concluido:
                    registro.concluido  = True
                    registro.acertos    = acertos_hoje
                    # 1 questão difícil → 100 pts se acertar
                    registro.pontuacao  = acertos_hoje * 100
                    registro.save()
                    msg_corpo = (f'Você acertou a questão de hoje! +{registro.pontuacao} pts!'
                                 if acertos_hoje else
                                 'Não foi dessa vez. Veja a justificativa e tente amanhã!')
                    Notificacao.criar(
                        request.user, 'sistema',
                        '📅 Desafio do dia concluído!',
                        msg_corpo,
                        link='/questao-do-dia/',
                    )

                is_favorita = QuestaoFavorita.objects.filter(
                    usuario=request.user, questao=alt.questao
                ).exists()
                anotacao = AnotacaoUsuario.objects.filter(
                    usuario=request.user, questao=alt.questao
                ).first()

                return render(request, 'quiz/resultado.html', {
                    'escolha':         alt,
                    'categoria_id':    alt.questao.categoria_id,
                    'is_favorita':     is_favorita,
                    'anotacao':        anotacao,
                    'filtros':         {},
                    'modo_dia':        True,
                    'dia_concluido':   registro.concluido,
                    'dia_acertos':     acertos_hoje,
                    'dia_total':       len(questoes_dia),
                    'novas_conquistas': [],
                })
            except Alternativa.DoesNotExist:
                pass
        return redirect('questao_do_dia')

    # GET: próxima questão não respondida hoje
    respondidas_hoje = set(
        RespostaUsuario.objects.filter(
            usuario=request.user, questao_id__in=ids_hoje, data__date=hoje
        ).values_list('questao_id', flat=True)
    )
    proxima = next((q for q in questoes_dia if q.id not in respondidas_hoje), None)

    # Estatísticas históricas do desafio
    dias_concluidos = QuestaoDodia.objects.filter(
        usuario=request.user, concluido=True
    ).count()
    historico = QuestaoDodia.objects.filter(
        usuario=request.user
    ).order_by('-data')[:7]

    # Média da plataforma hoje
    media_plat = None
    total_plat = QuestaoDodia.objects.filter(data=hoje, concluido=True).count()
    if total_plat:
        from django.db.models import Avg as _Avg
        media_plat = QuestaoDodia.objects.filter(data=hoje, concluido=True).aggregate(
            m=_Avg('acertos')
        )['m']
        if media_plat:
            media_plat = round(media_plat, 1)

    return render(request, 'quiz/questao_do_dia.html', {
        'questoes':       questoes_dia,
        'proxima':        proxima,
        'respondidas':    respondidas_hoje,
        'registro':       registro,
        'progresso':      len(respondidas_hoje),
        'total':          len(questoes_dia),
        'dias_concluidos': dias_concluidos,
        'historico':      historico,
        'media_plat':     media_plat,
        'hoje':           hoje,
    })


# ─── 15B — REVISÃO PÓS-SIMULADO ──────────────────────────────────────────────

@login_required(login_url='account_login')
def simulado_revisao(request, simulado_id):
    """
    Revisão do simulado concluído: lista todas as questões erradas com
    gabarito e justificativa. Permite navegar questão a questão.
    """
    simulado = get_object_or_404(Simulado, id=simulado_id, usuario=request.user)
    if not simulado.finalizado:
        messages.error(request, 'O simulado ainda não foi finalizado.')
        return redirect('simulado_resultado', simulado_id=simulado_id)

    modo = request.GET.get('modo', 'erros')  # 'erros' | 'todas'
    idx  = int(request.GET.get('q', 0))      # índice da questão atual

    respostas = simulado.respostas.select_related(
        'questao', 'questao__categoria',
        'alternativa_escolhida'
    ).prefetch_related('questao__alternativa_set').order_by('ordem')

    if modo == 'erros':
        respostas = [r for r in respostas if r.acertou is False]
    else:
        respostas = list(respostas)

    total = len(respostas)
    if not respostas:
        return render(request, 'quiz/simulado_revisao.html', {
            'simulado':    simulado,
            'sem_erros':   True,
            'modo':        modo,
        })

    idx = max(0, min(idx, total - 1))
    atual = respostas[idx]

    # Justificativa: usa a existente ou gera via IA se necessário
    questao = atual.questao
    if not questao.justificativa:
        try:
            result = gerar_justificativa_ia(questao)
            if result:
                questao.justificativa = result.get('justificativa', '')
                if result.get('assunto'):
                    questao.assunto = result['assunto']
                questao.save(update_fields=['justificativa', 'assunto'])
        except Exception:
            _silencioso("view_bloco_9")
    avaliacao = AvaliacaoQuestao.objects.filter(
        usuario=request.user, questao=questao
    ).first()

    return render(request, 'quiz/simulado_revisao.html', {
        'simulado':   simulado,
        'respostas':  respostas,
        'atual':      atual,
        'questao':    questao,
        'idx':        idx,
        'total':      total,
        'modo':       modo,
        'sem_erros':  False,
        'avaliacao':  avaliacao,
        'prev_idx':   idx - 1 if idx > 0 else None,
        'next_idx':   idx + 1 if idx < total - 1 else None,
    })


# ─── 15C — PLANO DE ESTUDOS IA ────────────────────────────────────────────────

@login_required(login_url='account_login')
@ratelimit(key='user', rate='10/h', method='GET', block=True)
def plano_estudos_ia(request):
    """
    Página de plano de estudos gerado por IA, personalizado com base
    nos dados de desempenho do usuário.
    GET  → formulário de configuração
    POST → gera o plano via Gemini
    """
    respostas = RespostaUsuario.objects.filter(usuario=request.user)
    total_resp = respostas.count()

    # Monta dados de desempenho
    cats_data = []
    for cat in Categoria.objects.all():
        r = respostas.filter(questao__categoria=cat)
        t = r.count()
        if t < 3:
            continue
        a = r.filter(acertou=True).count()
        pct = round(a / t * 100)
        cats_data.append({'nome': cat.nome, 'pct': pct, 'total': t})

    cats_data.sort(key=lambda x: x['pct'])
    pontos_fracos  = [c['nome'] for c in cats_data[:3]]
    pontos_fortes  = [c['nome'] for c in cats_data[-3:] if c['pct'] >= 60]
    aprov_geral    = round(
        respostas.filter(acertou=True).count() / total_resp * 100
    ) if total_resp else 0

    plano_gerado = ''
    form_data    = {}

    if request.method == 'POST':
        horas_dia    = int(request.POST.get('horas_dia', 2))
        dias_semana  = int(request.POST.get('dias_semana', 5))
        data_prova   = request.POST.get('data_prova', '').strip()
        form_data = {
            'horas_dia': horas_dia,
            'dias_semana': dias_semana,
            'data_prova': data_prova,
        }

        dados_usuario = {
            'horas_dia':            horas_dia,
            'dias_por_semana':      dias_semana,
            'data_prova':           data_prova,
            'pontos_fracos':        pontos_fracos,
            'pontos_fortes':        pontos_fortes,
            'total_respondidas':    total_resp,
            'aproveitamento_geral': aprov_geral,
        }
        plano_gerado = ai_plano_estudos(dados_usuario, usuario=request.user)

    return render(request, 'quiz/plano_estudos_ia.html', {
        'plano_gerado':  plano_gerado,
        'pontos_fracos': pontos_fracos,
        'pontos_fortes': pontos_fortes,
        'aprov_geral':   aprov_geral,
        'total_resp':    total_resp,
        'form_data':     form_data,
        'cats_data':     cats_data,
    })


# ─── 15D — DIFICULDADE PERCEBIDA (API) ───────────────────────────────────────


# ─── 15E — CARD COMPARTILHÁVEL (dados para Canvas) ───────────────────────────

@login_required(login_url='account_login')
def conquista_card(request, codigo):
    """
    Página dedicada ao card de conquista — renderiza via Canvas para salvar/compartilhar.
    """
    if codigo not in CONQUISTAS_META:
        from django.http import Http404
        raise Http404

    meta = CONQUISTAS_META[codigo]
    desbloqueada = Conquista.objects.filter(
        usuario=request.user, codigo=codigo
    ).first()

    respostas = RespostaUsuario.objects.filter(usuario=request.user)
    total = respostas.count()
    acertos = respostas.filter(acertou=True).count()
    pct = round(acertos / total * 100) if total else 0

    try:
        streak = request.user.meta.streak_atual
    except Exception:
        streak = 0

    return render(request, 'quiz/conquista_card.html', {
        'codigo':       codigo,
        'meta':         meta,
        'desbloqueada': desbloqueada,
        'usuario':      request.user,
        'total':        total,
        'pct':          pct,
        'streak':       streak,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINT 16 — XP & NÍVEIS, MODO TURBO, RELATÓRIO PDF, METAS VISUAL, COMPARATIVO
# ═══════════════════════════════════════════════════════════════════════════════

# ─── helper XP ───────────────────────────────────────────────────────────────

def _dar_xp(usuario, quantidade, session=None):
    obj, _ = NivelUsuario.objects.get_or_create(usuario=usuario)
    subiu  = obj.adicionar_xp(quantidade)
    if subiu and session is not None:
        session['subiu_nivel'] = obj.nivel
        session['rank_nome']   = obj.rank_nome
    return subiu, obj


# ─── FEATURE 1 — Painel XP / Nível ──────────────────────────────────────────


# ─── Modo Turbo: REMOVIDO em favor do Modo Desafio ───────────────────────────


# ─── FEATURE 3 — Relatório PDF ───────────────────────────────────────────────

@login_required
def relatorio_pdf(request):
    respostas = RespostaUsuario.objects.filter(usuario=request.user).select_related('questao__categoria')
    total      = respostas.count()
    acertos    = respostas.filter(acertou=True).count()
    erros      = respostas.filter(acertou=False).count()
    aproveitamento = round(acertos / total * 100) if total else 0

    cats = []
    for cat in Categoria.objects.all():
        r = respostas.filter(questao__categoria=cat)
        t = r.count()
        if not t:
            continue
        a = r.filter(acertou=True).count()
        cats.append({'nome': cat.nome, 'total': t, 'acertos': a, 'pct': round(a / t * 100)})
    cats.sort(key=lambda x: x['pct'])

    conquistas = Conquista.objects.filter(usuario=request.user).count()
    try:
        streak = request.user.meta.streak_atual
    except Exception:
        streak = 0

    nivel, _ = NivelUsuario.objects.get_or_create(usuario=request.user)

    return render(request, 'quiz/relatorio_pdf.html', {
        'total':          total,
        'acertos':        acertos,
        'erros':          erros,
        'aproveitamento': aproveitamento,
        'cats':           cats,
        'conquistas':     conquistas,
        'streak':         streak,
        'nivel':          nivel,
        'hoje':           timezone.now().strftime('%d/%m/%Y'),
        'usuario':        request.user,
    })


# ─── FEATURE 4 — Metas Semanais Visual ───────────────────────────────────────

@login_required
def metas_semanais(request):
    hoje          = timezone.now().date()
    inicio_semana = hoje - timedelta(days=hoje.weekday())
    meta_obj, _   = MetaEstudo.objects.get_or_create(usuario=request.user)
    questoes_meta = max(1, meta_obj.questoes_por_dia)

    LABELS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

    def _dia_stats(d):
        r = RespostaUsuario.objects.filter(
            usuario=request.user,
            data__date=d,
        )
        total_d   = r.count()
        acertos_d = r.filter(acertou=True).count()
        cumprida  = total_d >= questoes_meta
        return {
            'data':     d,
            'label':    LABELS[d.weekday()],
            'total':    total_d,
            'acertos':  acertos_d,
            'cumprida': cumprida,
            'hoje':     d == hoje,
            'futuro':   d > hoje,
            'pct':      min(100, int(total_d / questoes_meta * 100)),
        }

    dias = [_dia_stats(inicio_semana + timedelta(days=i)) for i in range(7)]

    historico = []
    for w in range(3, -1, -1):
        ini = inicio_semana - timedelta(weeks=w)
        dias_sem = [_dia_stats(ini + timedelta(days=i)) for i in range(7)]
        historico.append({
            'inicio':  ini,
            'fim':     ini + timedelta(days=6),
            'dias':    dias_sem,
            'dias_ok': sum(1 for d in dias_sem if d['cumprida']),
        })

    total_semana = sum(d['total'] for d in dias)
    meta_semana  = questoes_meta * 7
    dias_ok      = sum(1 for d in dias if d['cumprida'] and not d['futuro'])

    return render(request, 'quiz/metas_semanais.html', {
        'dias':           dias,
        'historico':      historico,
        'meta_obj':       meta_obj,
        'questoes_meta':  questoes_meta,
        'dias_ok_semana': dias_ok,
        'total_semana':   total_semana,
        'meta_semana':    meta_semana,
        'pct_semana':     min(100, int(total_semana / meta_semana * 100)) if meta_semana else 0,
        'inicio_semana':  inicio_semana,
    })


# ─── FEATURE 5 — Performance Comparativa ─────────────────────────────────────

@login_required
def performance_comparativa(request):
    respostas_user = RespostaUsuario.objects.filter(usuario=request.user)
    total_user     = respostas_user.count()
    acertos_user   = respostas_user.filter(acertou=True).count()
    aprov_user     = round(acertos_user / total_user * 100) if total_user else 0

    comparativo = []
    for cat in Categoria.objects.all():
        r_u  = respostas_user.filter(questao__categoria=cat)
        t_u  = r_u.count()
        if t_u < 2:
            continue
        a_u     = r_u.filter(acertou=True).count()
        pct_u   = round(a_u / t_u * 100)

        r_p  = RespostaUsuario.objects.filter(questao__categoria=cat)
        t_p  = r_p.count()
        a_p  = r_p.filter(acertou=True).count()
        pct_p = round(a_p / t_p * 100) if t_p else 0

        comparativo.append({
            'categoria': cat.nome,
            'user':      pct_u,
            'plat':      pct_p,
            'diff':      pct_u - pct_p,
            't_user':    t_u,
        })
    comparativo.sort(key=lambda x: x['diff'])

    # Percentil
    usuarios_ids = list(RespostaUsuario.objects.values_list('usuario', flat=True).distinct())
    total_usuarios = len(usuarios_ids)
    melhores = 0
    for uid in usuarios_ids:
        r = RespostaUsuario.objects.filter(usuario_id=uid)
        t = r.count()
        a = r.filter(acertou=True).count()
        if t and round(a / t * 100) < aprov_user:
            melhores += 1
    percentil = round(melhores / total_usuarios * 100) if total_usuarios else 0

    t_plat = RespostaUsuario.objects.count()
    a_plat = RespostaUsuario.objects.filter(acertou=True).count()
    aprov_plat = round(a_plat / t_plat * 100) if t_plat else 0

    return render(request, 'quiz/performance_comparativa.html', {
        'comparativo':    comparativo,
        'aprov_user':     aprov_user,
        'aprov_plat':     aprov_plat,
        'percentil':      percentil,
        'total_user':     total_user,
        'total_usuarios': total_usuarios,
    })


# ─── API XP ──────────────────────────────────────────────────────────────────

@login_required
def api_meu_xp(request):
    nivel, _ = NivelUsuario.objects.get_or_create(usuario=request.user)
    return JsonResponse({
        'xp':       nivel.xp_total,
        'nivel':    nivel.nivel,
        'rank':     nivel.rank_nome,
        'pct':      nivel.pct_nivel,
        'xp_falta': nivel.xp_necessario,
    })


# ─── SPRINT 17: MAPA DE CONHECIMENTO VISUAL ──────────────────────────────────

@login_required
def mapa_conhecimento(request):
    """Mapa visual de domínio por disciplina — verde/amarelo/vermelho/novo."""
    import json as _json
    from django.db.models import Max

    banca_filtro = request.GET.get('banca', '').strip()

    # Bancas disponíveis para filtro
    bancas = (Questao.objects
              .exclude(banca__isnull=True).exclude(banca='')
              .values_list('banca', flat=True)
              .distinct().order_by('banca'))

    respostas_user = RespostaUsuario.objects.filter(usuario=request.user)

    categorias = []
    for cat in Categoria.objects.order_by('nome'):
        qs_banco = Questao.objects.filter(categoria=cat)
        if banca_filtro:
            qs_banco = qs_banco.filter(banca=banca_filtro)

        total_banco = qs_banco.count()
        if total_banco == 0:
            continue

        resp_cat = respostas_user.filter(questao__categoria=cat)
        if banca_filtro:
            resp_cat = resp_cat.filter(questao__banca=banca_filtro)

        respondidas = resp_cat.count()
        acertos     = resp_cat.filter(acertou=True).count()
        erros       = respondidas - acertos
        pct         = round(acertos / respondidas * 100) if respondidas else 0
        cobertura   = round(respondidas / total_banco * 100) if total_banco else 0
        ultima      = resp_cat.aggregate(u=Max('data'))['u']

        if respondidas == 0:
            status = 'novo'
        elif pct >= 70:
            status = 'verde'
        elif pct >= 50:
            status = 'amarelo'
        else:
            status = 'vermelho'

        # Sub-tópicos (campo assunto na questão)
        assuntos_qs = (qs_banco
                       .exclude(assunto__isnull=True).exclude(assunto='')
                       .values('assunto')
                       .annotate(total=Count('id'))
                       .order_by('-total')[:8])

        assuntos = []
        for a in assuntos_qs:
            r = resp_cat.filter(questao__assunto=a['assunto'])
            rt = r.count()
            ra = r.filter(acertou=True).count()
            ap = round(ra / rt * 100) if rt else 0
            if rt == 0:
                ast = 'novo'
            elif ap >= 70:
                ast = 'verde'
            elif ap >= 50:
                ast = 'amarelo'
            else:
                ast = 'vermelho'
            assuntos.append({
                'nome': a['assunto'],
                'total_banco': a['total'],
                'respondidas': rt,
                'acertos': ra,
                'pct': ap,
                'status': ast,
            })

        categorias.append({
            'id':          cat.id,
            'nome':        cat.nome,
            'total_banco': total_banco,
            'respondidas': respondidas,
            'acertos':     acertos,
            'erros':       erros,
            'pct':         pct,
            'cobertura':   cobertura,
            'status':      status,
            'ultima':      ultima.strftime('%d/%m/%Y') if ultima else None,
            'assuntos':    assuntos,
        })

    # Ordenar: vermelho primeiro (mais urgente), depois amarelo, verde, novo
    _ordem = {'vermelho': 0, 'amarelo': 1, 'verde': 2, 'novo': 3}
    categorias.sort(key=lambda c: (_ordem[c['status']], -c['respondidas']))

    resumo = {
        'verde':    sum(1 for c in categorias if c['status'] == 'verde'),
        'amarelo':  sum(1 for c in categorias if c['status'] == 'amarelo'),
        'vermelho': sum(1 for c in categorias if c['status'] == 'vermelho'),
        'novo':     sum(1 for c in categorias if c['status'] == 'novo'),
    }

    return render(request, 'quiz/mapa_conhecimento.html', {
        'categorias':      categorias,
        'categorias_json': _json.dumps(categorias, default=str),
        'bancas':          list(bancas),
        'banca_filtro':    banca_filtro,
        'resumo':          resumo,
    })


# ─── SPRINT 18: PLANO DE ESTUDOS DINÂMICO ────────────────────────────────────

def _calcular_peso(pct):
    """Retorna peso de prioridade com base no aproveitamento."""
    if pct is None:  return 1.5   # não iniciado
    if pct < 30:     return 3.2   # crítico
    if pct < 50:     return 2.2   # atenção
    if pct < 70:     return 1.4   # desenvolvendo
    return 0.7                    # dominando — manter


def _recalcular_plano_dinamico(usuario, plano):
    """Redistribui horas por disciplina ponderando pelo aproveitamento."""
    from ..models import PlanoEstudoDinamico   # import local evita circular
    respostas = RespostaUsuario.objects.filter(usuario=usuario)

    # Salva distribuição anterior antes de sobrescrever
    if plano.distribuicao:
        plano.distribuicao_ant = dict(plano.distribuicao)

    total_horas_semana = plano.horas_por_dia * plano.dias_por_semana
    entradas = []

    for cat in Categoria.objects.order_by('nome'):
        total_banco = Questao.objects.filter(categoria=cat).count()
        if total_banco == 0:
            continue
        resp = respostas.filter(questao__categoria=cat)
        respondidas = resp.count()
        acertos     = resp.filter(acertou=True).count()
        pct = round(acertos / respondidas * 100) if respondidas else None

        if pct is None:
            status = 'novo'
        elif pct >= 70:
            status = 'verde'
        elif pct >= 50:
            status = 'amarelo'
        else:
            status = 'vermelho'

        entradas.append({
            'cat_id':      cat.id,
            'nome':        cat.nome,
            'pct':         pct,
            'respondidas': respondidas,
            'total_banco': total_banco,
            'status':      status,
            'peso':        _calcular_peso(pct),
        })

    if not entradas:
        return

    total_peso  = sum(e['peso'] for e in entradas)
    distribuicao = {}
    for e in entradas:
        horas = round((e['peso'] / total_peso) * total_horas_semana, 1)
        horas = max(0.5, horas)
        distribuicao[str(e['cat_id'])] = {
            'cat_id':      e['cat_id'],
            'nome':        e['nome'],
            'pct':         e['pct'],
            'horas_semana': horas,
            'status':      e['status'],
            'respondidas': e['respondidas'],
            'total_banco': e['total_banco'],
        }

    plano.distribuicao   = distribuicao
    plano.data_recalculo = timezone.now()
    plano.save()


def _gerar_calendario_semanal(plano):
    """
    Distribui disciplinas nos dias de estudo de forma balanceada.
    Retorna lista de 7 dicts, um por dia da semana.
    """
    NOMES_DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
    dias_estudo = min(plano.dias_por_semana, 7)

    # Calcula horas disponíveis por dia de estudo
    calendario = []
    for i, nome in enumerate(NOMES_DIAS):
        calendario.append({
            'dia': nome,
            'estudo': i < dias_estudo,
            'horas_total': plano.horas_por_dia if i < dias_estudo else 0,
            'categorias': [],
        })

    if not plano.distribuicao:
        return calendario

    # Ordena por horas decrescente (mais urgente primeiro)
    cats = sorted(plano.distribuicao.values(),
                  key=lambda c: c['horas_semana'], reverse=True)

    # Distribui round-robin ponderado entre os dias de estudo
    # Cada categoria ocupa ceil(horas / horas_por_dia) dias
    acumulado = [0.0] * dias_estudo   # horas já alocadas por dia

    for cat in cats:
        horas_rest  = cat['horas_semana']
        hpd         = plano.horas_por_dia
        dias_nec    = max(1, round(horas_rest / hpd))
        dias_nec    = min(dias_nec, dias_estudo)
        h_por_dia_c = round(horas_rest / dias_nec, 1)

        # Escolhe os dias com menos horas acumuladas
        dias_ordenados = sorted(range(dias_estudo), key=lambda d: acumulado[d])
        for d in dias_ordenados[:dias_nec]:
            if acumulado[d] < plano.horas_por_dia + 0.5:
                calendario[d]['categorias'].append({
                    'nome':   cat['nome'],
                    'horas':  h_por_dia_c,
                    'status': cat.get('status', 'novo'),
                })
                acumulado[d] += h_por_dia_c

    return calendario


@login_required
def plano_dinamico(request):
    import json as _json
    from ..models import PlanoEstudoDinamico

    plano, criado = PlanoEstudoDinamico.objects.get_or_create(usuario=request.user)

    # Primeiro acesso → gera plano automaticamente
    if criado or not plano.distribuicao:
        _recalcular_plano_dinamico(request.user, plano)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        # Salva configurações
        plano.concurso_alvo  = request.POST.get('concurso', plano.concurso_alvo)[:120]
        plano.horas_por_dia  = max(1, min(12, int(request.POST.get('horas_dia',  plano.horas_por_dia))))
        plano.dias_por_semana = max(1, min(7,  int(request.POST.get('dias_semana', plano.dias_por_semana))))
        data_prova_str = request.POST.get('data_prova', '')
        if data_prova_str:
            try:
                from datetime import datetime as _dt
                plano.data_prova = _dt.strptime(data_prova_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        plano.save(update_fields=['concurso_alvo', 'horas_por_dia',
                                   'dias_por_semana', 'data_prova'])

        # Recalcula sempre que o form for submetido
        _recalcular_plano_dinamico(request.user, plano)
        return redirect('plano_dinamico')

    # Diff semana anterior
    diff = []
    if plano.distribuicao and plano.distribuicao_ant:
        for cid, dados in plano.distribuicao.items():
            ant   = plano.distribuicao_ant.get(cid, {})
            delta = round(dados['horas_semana'] - ant.get('horas_semana', 0), 1)
            if abs(delta) >= 0.1:
                diff.append({'nome': dados['nome'], 'delta': delta, 'up': delta > 0})
        diff.sort(key=lambda d: abs(d['delta']), reverse=True)

    # Distribuição ordenada para o template (vermelho→amarelo→verde→novo)
    ordem_status = {'vermelho': 0, 'amarelo': 1, 'novo': 2, 'verde': 3}
    distribuicao_lista = sorted(
        plano.distribuicao.values(),
        key=lambda c: (ordem_status.get(c.get('status', 'novo'), 2), -c['horas_semana'])
    )

    calendario = _gerar_calendario_semanal(plano)

    return render(request, 'quiz/plano_dinamico.html', {
        'plano':             plano,
        'distribuicao':      distribuicao_lista,
        'distribuicao_json': _json.dumps(plano.distribuicao, default=str),
        'diff':              diff[:8],
        'calendario':        calendario,
    })


# ─── Micro-estudo: REMOVIDO ──────────────────────────────────────────────────


@login_required
def preferencias_notificacao(request):
    """Página de configuração de notificações."""
    pref, _ = PreferenciasNotificacao.objects.get_or_create(usuario=request.user)

    if request.method == 'POST':
        pref.lembrete_diario = 'lembrete_diario' in request.POST
        pref.streak_em_risco = 'streak_em_risco' in request.POST
        pref.novidades       = 'novidades'       in request.POST
        # Removido: pref.micro_estudo — campo nao existe no model
        # (atribuia atributo Python em memoria que nunca ia pro banco).
        hora_str = request.POST.get('hora_lembrete', '20:00')
        try:
            from datetime import time as _time
            h, m = hora_str.split(':')
            pref.hora_lembrete = _time(int(h), int(m))
        except Exception:
            _silencioso("view_bloco_10")
        pref.save()
        messages.success(request, 'Preferências salvas com sucesso!')
        return redirect('preferencias_notificacao')

    # hora_lembrete pode ser string (default antigo) ou time object
    hl = pref.hora_lembrete
    if hasattr(hl, 'strftime'):
        hora_str = hl.strftime('%H:%M')
    elif isinstance(hl, str) and hl:
        hora_str = hl
    else:
        hora_str = '20:00'
    return render(request, 'quiz/preferencias_notificacao.html', {
        'pref':     pref,
        'hora_str': hora_str,
    })


# ─── SPRINT 20: TUTOR IA PERSONALIZADO ───────────────────────────────────────

_COTA_DIARIA_EXPLICACOES = 5   # free plan


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 22 — Simulado Preditivo
# ═══════════════════════════════════════════════════════════════════════════════

def _calcular_predicao(user):
    """Calcula nota predita e dados de tendência para o usuário.
    Retorna dict com: nota_predita, confianca, tendencia, historico."""
    from datetime import timedelta as td

    simulados = (
        Simulado.objects
        .filter(usuario=user, finalizado=True)
        .prefetch_related('respostas')
        .order_by('finalizado_em')
    )

    historico = []
    for s in simulados:
        resps = [r for r in s.respostas.all() if r.acertou is not None]
        if not resps:
            continue
        acertos = sum(1 for r in resps if r.acertou)
        historico.append({
            'data':  s.finalizado_em.strftime('%d/%m') if s.finalizado_em else '—',
            'pct':   round(acertos / len(resps) * 100),
            'total': len(resps),
        })

    if not historico:
        return None

    pcts = [h['pct'] for h in historico]

    # Nota predita: média ponderada (mais recente = mais peso)
    n = len(pcts)
    pesos  = list(range(1, n + 1))
    nota   = sum(p * v for p, v in zip(pesos, pcts)) / sum(pesos)
    nota   = max(0.0, min(100.0, round(nota - 3, 1)))  # conservadorismo -3%

    # Tendência: diferença entre média da 2ª metade vs 1ª metade
    mid = max(1, n // 2)
    tendencia = round(sum(pcts[mid:]) / len(pcts[mid:]) - sum(pcts[:mid]) / len(pcts[:mid]), 1) if n >= 2 else 0

    # Confiança: baseada na quantidade de simulados e variância
    confianca = min(95, 50 + n * 5)  # cresce 5% por simulado até 95%

    return {
        'nota_predita': nota,
        'tendencia':    tendencia,
        'confianca':    confianca,
        'historico':    historico[-10:],   # últimos 10
        'total_simulados': n,
    }


@login_required
@ratelimit(key='user', rate='15/h', method='GET', block=True)
def simulado_preditivo(request):
    """Sprint 22 — Página de Simulado Preditivo.
    GET: painel de predição + form para iniciar simulado inteligente.
    POST: cria simulado com questões priorizadas por fraqueza."""
    import json as _json

    predicao = _calcular_predicao(request.user)

    # Categorias com desempenho para o formulário inteligente
    respostas = RespostaUsuario.objects.filter(usuario=request.user)
    cats_stats = (
        respostas
        .values('questao__categoria__id', 'questao__categoria__nome')
        .annotate(
            total=Count('id'),
            acertos=Count('id', filter=Q(acertou=True)),
        )
        .filter(total__gte=3)
        .order_by('acertos')
    )
    cats_com_dados = [
        {
            'id':    c['questao__categoria__id'],
            'nome':  c['questao__categoria__nome'],
            'total': c['total'],
            'pct':   round(c['acertos'] / c['total'] * 100),
        }
        for c in cats_stats
    ]

    if request.method == 'POST':
        resp = _check_pode_criar_simulado(request, fallback_url='simulado_preditivo')
        if resp: return resp

        modo        = request.POST.get('modo', 'fraco')   # 'fraco' | 'balanceado' | 'livre'
        n_questoes  = max(10, min(int(request.POST.get('n_questoes', 30)), 80))
        tempo_min   = max(20, min(int(request.POST.get('tempo_min', 60)), 180))

        # Pool base: sempre filtrado por revisada (consistencia com outros modos)
        base_qs = Questao.objects.filter(revisada=True, rejeitada_definitiva=False)

        # Seleciona categorias com pior desempenho para ponderar seleção
        if modo == 'fraco' and cats_com_dados:
            # Pega categorias abaixo de 70%, priorizando as piores
            fracas = [c['id'] for c in cats_com_dados if c['pct'] < 70]
            if not fracas:
                fracas = [c['id'] for c in cats_com_dados[:3]]
            # 70% das questões das categorias fracas, 30% aleatório
            n_foco   = max(1, int(n_questoes * 0.70))
            n_livre  = n_questoes - n_foco
            qs_foco  = list(
                base_qs.filter(categoria_id__in=fracas).order_by('?')[:n_foco]
            )
            qs_livre = list(
                base_qs.exclude(id__in=[q.id for q in qs_foco]).order_by('?')[:n_livre]
            )
            questoes = qs_foco + qs_livre
        else:
            questoes = list(base_qs.order_by('?')[:n_questoes])

        if len(questoes) < 5:
            messages.error(request, 'Questões insuficientes. Tente outro modo.')
            return redirect('simulado_preditivo')

        import random
        random.shuffle(questoes)
        simulado = Simulado.objects.create(
            usuario=request.user,
            duracao_segundos=tempo_min * 60,
        )
        for i, q in enumerate(questoes, 1):
            RespostaSimulado.objects.create(simulado=simulado, questao=q, ordem=i)

        messages.success(request, f'Simulado inteligente criado com {len(questoes)} questões!')
        return redirect('simulado_questao', simulado_id=simulado.id, numero=1)

    return render(request, 'quiz/simulado_preditivo.html', {
        'predicao':      predicao,
        'predicao_json': _json.dumps(predicao) if predicao else 'null',
        'cats':          cats_com_dados,
    })


@login_required
@require_POST
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def api_gerar_relatorio_simulado(request, simulado_id):
    """Sprint 22 — Gera (ou retorna cached) relatório IA para um simulado finalizado."""
    simulado = get_object_or_404(Simulado, id=simulado_id, usuario=request.user, finalizado=True)

    # Retorna cache se já gerado
    try:
        rel = simulado.relatorio_ia
        return JsonResponse({'texto': rel.texto, 'nota_predita': rel.nota_predita, 'cached': True})
    except RelatorioSimuladoIA.DoesNotExist:
        pass

    # Monta dados para a IA
    respostas = simulado.respostas.select_related('questao__categoria').all()
    respondidas = [r for r in respostas if r.acertou is not None]
    if not respondidas:
        return JsonResponse({'erro': 'Simulado sem respostas válidas'}, status=400)

    acertos  = sum(1 for r in respondidas if r.acertou)
    aprov    = round(acertos / len(respondidas) * 100)

    # Breakdown por categoria
    cats_dict = {}
    for r in respondidas:
        nome = r.questao.categoria.nome
        cats_dict.setdefault(nome, {'total': 0, 'acertos': 0})
        cats_dict[nome]['total'] += 1
        if r.acertou:
            cats_dict[nome]['acertos'] += 1
    cats_stats = [
        {'nome': k, 'pct': round(v['acertos'] / v['total'] * 100), 'total': v['total']}
        for k, v in cats_dict.items()
    ]

    # Histórico de simulados anteriores
    historico_pct = list(
        Simulado.objects
        .filter(usuario=request.user, finalizado=True)
        .exclude(id=simulado_id)
        .order_by('-finalizado_em')
        .values_list('id', flat=True)[:5]
    )
    # Converte IDs em aproveitamentos
    hist_vals = []
    for sid in reversed(historico_pct):
        s = Simulado.objects.filter(id=sid).prefetch_related('respostas').first()
        if not s:
            continue
        rs = [r for r in s.respostas.all() if r.acertou is not None]
        if rs:
            hist_vals.append(round(sum(1 for r in rs if r.acertou) / len(rs) * 100))

    nivel = getattr(request.user, 'nivel_usuario', None)
    rank  = nivel.rank_nome if nivel else 'Cadete'

    resultado = ai_analisar_simulado(aprov, len(respondidas), cats_stats, hist_vals, rank, usuario=request.user)

    rel = RelatorioSimuladoIA.objects.create(
        simulado=simulado,
        texto=resultado['texto'],
        nota_predita=resultado['nota_predita'],
    )
    return JsonResponse({'texto': rel.texto, 'nota_predita': rel.nota_predita, 'cached': False})


@login_required
def relatorio_simulado_ia(request, simulado_id):
    """Sprint 22 — Página completa do relatório IA de um simulado."""
    simulado = get_object_or_404(Simulado, id=simulado_id, usuario=request.user, finalizado=True)
    relatorio = getattr(simulado, 'relatorio_ia', None)

    respostas   = simulado.respostas.select_related('questao__categoria').all()
    respondidas = [r for r in respostas if r.acertou is not None]
    acertos     = sum(1 for r in respondidas if r.acertou)
    aproveitamento = round(acertos / len(respondidas) * 100) if respondidas else 0

    predicao = _calcular_predicao(request.user)

    return render(request, 'quiz/relatorio_simulado_ia.html', {
        'simulado':      simulado,
        'relatorio':     relatorio,
        'aproveitamento': aproveitamento,
        'total':         len(respondidas),
        'acertos':       acertos,
        'predicao':      predicao,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 23 — Geração de Questões IA + Predição de Tópicos
# ═══════════════════════════════════════════════════════════════════════════════

@user_passes_test(lambda u: u.is_staff)
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def admin_gerar_questoes_ia(request):
    """Admin: gera questões originais via IA a partir de categoria + assunto.
    Rate limit 30/h/user evita queima acidental de cota Groq/Gemini.
    GET  → formulário de configuração.
    POST acao=gerar   → chama Gemini, retorna preview.
    POST acao=salvar  → persiste questões geradas no banco."""
    categorias = Categoria.objects.order_by('nome')
    etapa      = 'form'
    questoes_ia = []
    erros       = []
    salvas      = 0

    if request.method == 'POST':
        acao = request.POST.get('acao', 'gerar')

        if acao == 'gerar':
            cat_id      = request.POST.get('categoria_id', '')
            assunto     = request.POST.get('assunto', '').strip()
            quantidade  = max(1, min(int(request.POST.get('quantidade', 5)), 10))
            dificuldade = request.POST.get('dificuldade', 'media')

            try:
                cat = Categoria.objects.get(id=cat_id)
            except (Categoria.DoesNotExist, ValueError):
                erros.append('Selecione uma categoria válida.')
                return render(request, 'quiz/admin/gerar_ia.html', {
                    'categorias': categorias, 'etapa': etapa,
                    'erros': erros, 'questoes_ia': [], 'salvas': 0,
                })

            questoes_ia = ai_gerar_questoes(cat.nome, quantidade, dificuldade, assunto, usuario=request.user)
            if not questoes_ia:
                erros.append('A IA não conseguiu gerar questões. Tente novamente.')
            else:
                etapa = 'preview'

        elif acao == 'salvar':
            import json as _json
            raw = request.POST.get('questoes_json', '[]')
            try:
                questoes_ia = _json.loads(raw)
            except Exception:
                erros.append('Dados inválidos.')
                questoes_ia = []

            for q_data in questoes_ia:
                try:
                    cat_nome = (q_data.get('categoria') or 'Geral').strip()
                    enunciado = (q_data.get('texto') or '').strip()
                    if not enunciado:
                        continue
                    cat, _ = Categoria.objects.get_or_create(nome=cat_nome)
                    questao = Questao.objects.create(
                        categoria=cat,
                        texto=enunciado,
                        tipo='ME',
                        justificativa=q_data.get('justificativa', ''),
                        assunto=q_data.get('assunto', ''),
                        banca='IA',
                        gerada_por_ia=True,
                        revisada=False,
                    )
                    for alt in q_data.get('alternativas', []):
                        Alternativa.objects.create(
                            questao=questao,
                            texto=alt.get('texto', ''),
                            correta=bool(alt.get('correta', False)),
                        )
                    salvas += 1
                except Exception as e:
                    erros.append(f'Erro ao salvar questão: {e}')

            etapa = 'salvo'

    return render(request, 'quiz/admin/gerar_ia.html', {
        'categorias':  categorias,
        'etapa':       etapa,
        'questoes_ia': questoes_ia,
        'erros':       erros,
        'salvas':      salvas,
    })


@login_required
@ratelimit(key='user', rate='10/h', method='GET', block=True)
def previsao_topicos(request):
    """Sprint 23 — Predição de tópicos prováveis para a próxima prova do concurso alvo.
    Recalcula (via IA) no máximo 1x por dia por usuário."""
    import json as _json
    from datetime import timedelta as td

    hoje    = timezone.localdate()
    recalc  = request.GET.get('recalc') == '1'

    # Verifica se já tem previsões de hoje
    previsoes_qs = PrevisaoTopico.objects.filter(
        usuario=request.user,
        atualizado_em__date=hoje,
    ).select_related('categoria').order_by('-probabilidade')

    if previsoes_qs.exists() and not recalc:
        previsoes = list(previsoes_qs)
        recalculado_hoje = True
    else:
        # Monta stats por categoria para a IA
        respostas = RespostaUsuario.objects.filter(usuario=request.user)
        cats_qs = (
            respostas
            .values('questao__categoria__id', 'questao__categoria__nome')
            .annotate(
                total=Count('id'),
                acertos=Count('id', filter=Q(acertou=True)),
                ultima=models.Max('data'),
            )
            .order_by('-total')
        )
        cats_stats = []
        for c in cats_qs:
            ultima = c['ultima']
            if ultima:
                dias = (timezone.now() - ultima).days
            else:
                dias = 999
            t = c['total']
            a = c['acertos']
            cats_stats.append({
                'id':   c['questao__categoria__id'],
                'nome': c['questao__categoria__nome'],
                'total': t,
                'pct':  round(a / t * 100) if t else 0,
                'dias': dias,
            })

        # Também inclui categorias não estudadas
        todas_cats = set(Categoria.objects.values_list('nome', flat=True))
        estudadas  = {c['nome'] for c in cats_stats}
        for nome in (todas_cats - estudadas):
            cats_stats.append({'id': None, 'nome': nome, 'total': 0, 'pct': 0, 'dias': 999})

        raw_previsoes = ai_prever_topicos(cats_stats, usuario=request.user)

        # Salva no banco (upsert)
        previsoes = []
        for p in raw_previsoes:
            nome_cat = p.get('categoria', '').strip()
            if not nome_cat:
                continue
            try:
                cat = Categoria.objects.get(nome=nome_cat)
            except Categoria.DoesNotExist:
                continue
            obj, _ = PrevisaoTopico.objects.update_or_create(
                usuario=request.user, categoria=cat,
                defaults={
                    'probabilidade': float(p.get('probabilidade', 50)),
                    'justificativa': p.get('justificativa', ''),
                },
            )
            previsoes.append(obj)

        previsoes.sort(key=lambda x: x.probabilidade, reverse=True)
        recalculado_hoje = True

    # Separa em faixas para a UI
    alta    = [p for p in previsoes if p.probabilidade >= 70]
    media   = [p for p in previsoes if 40 <= p.probabilidade < 70]
    baixa   = [p for p in previsoes if p.probabilidade < 40]

    previsoes_json = _json.dumps([
        {'nome': p.categoria.nome, 'prob': p.probabilidade}
        for p in previsoes
    ])

    return render(request, 'quiz/previsao_topicos.html', {
        'previsoes':         previsoes,
        'alta':              alta,
        'media':             media,
        'baixa':             baixa,
        'previsoes_json':    previsoes_json,
        'recalculado_hoje':  recalculado_hoje,
        'total':             len(previsoes),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 24 — Modo Prova Real + Laudo de Desempenho
# ═══════════════════════════════════════════════════════════════════════════════

# Distribuição real do edital PRF (aproximada) ─────────────────────────────────
PRF_DISTRIBUICAO = [
    # (disciplina_parcial, n_questoes, peso_pct)
    ('Língua Portuguesa',               20, 18),
    ('Raciocínio Lógico',               10,  9),
    ('Legislação de Trânsito',          20, 18),
    ('Física',                          10,  9),
    ('Primeiros Socorros',              10,  9),
    ('Direito Constitucional',          10,  9),
    ('Direito Administrativo',          10,  9),
    ('Direito Penal',                   10,  9),
    ('Informática',                     10, 10),
]
PRF_TOTAL_QUESTOES = sum(n for _, n, _ in PRF_DISTRIBUICAO)   # 110
PRF_DURACAO_MIN    = 240                                        # 4 horas


@login_required
def modo_prova_real(request):
    """
    Modo Prova Real: simula condições reais de prova de concurso.
    Diferente do Simulado por Edital, este modo:
      • Distribuição oficial do concurso escolhido (PRF, INSS, PF, ENEM, TJ-DF)
      • Cronômetro estrito, sem pausa
      • Modo='prova_real' marca para Simulado (sem revisão durante)
      • Avisos e briefing antes de iniciar

    GET:  mostra cards de concursos disponíveis + regras
    POST: edital_id → cria Simulado modo='prova_real' e redireciona
    """
    cats_qs = Categoria.objects.annotate(qtd=Count('questao')).filter(qtd__gt=0)
    cat_por_nome = {c.nome.lower(): c for c in cats_qs}

    concursos_disponiveis = []
    for edital in EDITAIS_OFICIAIS:
        cobertas = []
        total_real = 0
        for disc, qtd in edital['distribuicao'].items():
            cat = cat_por_nome.get(disc.lower())
            if cat:
                disponivel = min(qtd, cat.qtd)
                cobertas.append({'nome': disc, 'pedido': qtd, 'disponivel': disponivel})
                total_real += disponivel

        concursos_disponiveis.append({
            **edital,
            'cobertas':      cobertas,
            'total_real':    total_real,
            'cobertura_pct': round(total_real / edital['total'] * 100) if edital['total'] else 0,
        })

    if request.method == 'POST':
        resp = _check_pode_criar_simulado(request, fallback_url='modo_prova_real')
        if resp: return resp

        edital_id = request.POST.get('edital_id', '')
        edital = next((e for e in EDITAIS_OFICIAIS if e['id'] == edital_id), None)
        if not edital:
            messages.error(request, 'Concurso inválido.')
            return redirect('modo_prova_real')

        # Monta lista de questões conforme distribuição oficial
        questoes_selecionadas = []
        import random as _random
        for disc, qtd in edital['distribuicao'].items():
            cat = cat_por_nome.get(disc.lower())
            if not cat:
                continue
            disponivel = min(qtd, cat.qtd)
            qs = list(Questao.objects.filter(
                categoria_id=cat.id, revisada=True, rejeitada_definitiva=False,
            ).order_by('?')[:disponivel])
            questoes_selecionadas.extend(qs)

        if len(questoes_selecionadas) < 10:
            messages.error(request, 'Banco insuficiente para o Modo Prova Real deste concurso.')
            return redirect('modo_prova_real')

        _random.shuffle(questoes_selecionadas)

        simulado = Simulado.objects.create(
            usuario=request.user,
            modo='prova_real',
            duracao_segundos=edital['duracao_min'] * 60,
        )
        request.session[f'simulado_{simulado.id}_edital']  = edital['nome']
        request.session[f'simulado_{simulado.id}_banca']   = edital.get('banca', '')

        RespostaSimulado.objects.bulk_create([
            RespostaSimulado(simulado=simulado, questao=q, ordem=i + 1)
            for i, q in enumerate(questoes_selecionadas)
        ])

        messages.success(request, f'Modo Prova Real iniciado — {edital["nome"]}. Boa sorte!')
        return redirect('simulado_questao', simulado_id=simulado.id, numero=1)

    # Histórico de Provas Reais
    historico_pr = (
        Simulado.objects
        .filter(usuario=request.user, modo='prova_real', finalizado=True)
        .order_by('-finalizado_em')[:5]
    )
    historico = []
    for s in historico_pr:
        resps = [r for r in s.respostas.all() if r.acertou is not None]
        if resps:
            a = sum(1 for r in resps if r.acertou)
            historico.append({
                'id':    s.id,
                'data':  s.finalizado_em.strftime('%d/%m/%Y'),
                'pct':   round(a / len(resps) * 100),
                'total': len(resps),
            })

    return render(request, 'quiz/modo_prova_real.html', {
        'concursos': concursos_disponiveis,
        'historico': historico,
    })


@login_required
def laudo_desempenho(request, simulado_id):
    """Sprint 24 — Laudo completo e imprimível de um simulado finalizado."""
    import json as _json

    simulado = get_object_or_404(Simulado, id=simulado_id, usuario=request.user, finalizado=True)

    respostas   = simulado.respostas.select_related(
        'questao__categoria', 'alternativa_escolhida'
    ).order_by('ordem')
    respondidas = [r for r in respostas if r.acertou is not None]
    em_branco   = [r for r in respostas if r.acertou is None]

    total      = respostas.count()
    n_resps    = len(respondidas)
    acertos    = sum(1 for r in respondidas if r.acertou)
    erros      = n_resps - acertos
    aprov      = round(acertos / n_resps * 100, 1) if n_resps else 0.0

    # Breakdown por categoria ──────────────────────────────────────────────────
    cats: dict = {}
    for r in respostas:
        nome = r.questao.categoria.nome
        cats.setdefault(nome, {'total': 0, 'acertos': 0, 'erros': 0, 'branco': 0})
        cats[nome]['total'] += 1
        if r.acertou is True:
            cats[nome]['acertos'] += 1
        elif r.acertou is False:
            cats[nome]['erros'] += 1
        else:
            cats[nome]['branco'] += 1

    cats_list = []
    for nome, v in cats.items():
        t = v['total']
        a = v['acertos']
        cats_list.append({
            'nome':    nome,
            'total':   t,
            'acertos': a,
            'erros':   v['erros'],
            'branco':  v['branco'],
            'pct':     round(a / t * 100) if t else 0,
        })
    cats_list.sort(key=lambda x: x['pct'])

    # Tempo gasto ──────────────────────────────────────────────────────────────
    if simulado.finalizado_em:
        seg = int((simulado.finalizado_em - simulado.iniciado_em).total_seconds())
    else:
        seg = 0
    tempo_fmt = f'{seg // 3600:02d}h {(seg % 3600) // 60:02d}min'

    # Veredicto ────────────────────────────────────────────────────────────────
    # Benchmark comum em concursos públicos brasileiros: ≥70% geral + ≥50% em cada disciplina
    aprovado_geral     = aprov >= 70
    cats_eliminatorias = [c for c in cats_list if c['pct'] < 50 and c['total'] >= 3]
    aprovado_simulado  = aprovado_geral and not cats_eliminatorias

    # Percentil estimado (curva simulada) ──────────────────────────────────────
    if aprov >= 90:
        percentil = 98
    elif aprov >= 80:
        percentil = 90
    elif aprov >= 70:
        percentil = 72
    elif aprov >= 60:
        percentil = 48
    elif aprov >= 50:
        percentil = 28
    else:
        percentil = 12

    # Nota CESPE (se modo prova real ou simulado com CE) ──────────────────────
    resps_ce = [r for r in respondidas if r.questao.tipo == 'CE']
    if resps_ce:
        ac_ce  = sum(1 for r in resps_ce if r.acertou)
        er_ce  = sum(1 for r in resps_ce if not r.acertou)
        nota_ce = round(ac_ce - er_ce * 0.5, 1)
    else:
        nota_ce = None

    # Distribuição para JSON (chart) ───────────────────────────────────────────
    cats_json = _json.dumps([
        {'nome': c['nome'], 'pct': c['pct'], 'total': c['total']}
        for c in sorted(cats_list, key=lambda x: -x['pct'])
    ])

    # Relatorio IA se existir ──────────────────────────────────────────────────
    relatorio_ia = getattr(simulado, 'relatorio_ia', None)

    return render(request, 'quiz/laudo_desempenho.html', {
        'simulado':          simulado,
        'total':             total,
        'n_resps':           n_resps,
        'acertos':           acertos,
        'erros':             erros,
        'em_branco':         len(em_branco),
        'aprov':             aprov,
        'cats_list':         cats_list,
        'cats_json':         cats_json,
        'tempo_fmt':         tempo_fmt,
        'aprovado_simulado': aprovado_simulado,
        'aprovado_geral':    aprovado_geral,
        'cats_eliminatorias': cats_eliminatorias,
        'percentil':         percentil,
        'nota_ce':           nota_ce,
        'relatorio_ia':      relatorio_ia,
    })


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 25 — DUELO EM TEMPO REAL
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def duelo_home(request):
    """Página inicial do Duelo — listar duelos ativos/histórico + form de entrada."""
    user = request.user

    duelos_ativos = Duelo.objects.filter(
        status__in=['aguardando', 'em_andamento']
    ).filter(
        models.Q(criador=user) | models.Q(adversario=user)
    ).select_related('criador', 'adversario', 'categoria')[:10]

    duelos_hist = Duelo.objects.filter(
        status='finalizado'
    ).filter(
        models.Q(criador=user) | models.Q(adversario=user)
    ).select_related('criador', 'adversario', 'categoria')[:10]

    hist_enriquecido = []
    for d in duelos_hist:
        if d.criador == user:
            meus_pts     = d.pontos_criador
            pts_oponente = d.pontos_adversario
            oponente     = d.adversario
        else:
            meus_pts     = d.pontos_adversario
            pts_oponente = d.pontos_criador
            oponente     = d.criador

        if meus_pts > pts_oponente:
            resultado = 'vitoria'
        elif meus_pts < pts_oponente:
            resultado = 'derrota'
        else:
            resultado = 'empate'

        hist_enriquecido.append({
            'duelo':       d,
            'oponente':    oponente,
            'meus_pts':    meus_pts,
            'pts_oponente':pts_oponente,
            'resultado':   resultado,
        })

    categorias = Categoria.objects.all().order_by('nome')

    return render(request, 'quiz/duelo_home.html', {
        'duelos_ativos': duelos_ativos,
        'historico':     hist_enriquecido,
        'categorias':    categorias,
    })


@login_required
@require_POST
def duelo_criar(request):
    """Cria um novo duelo e redireciona para a sala de espera."""
    user = request.user
    categoria_id = request.POST.get('categoria_id') or None
    n_questoes   = int(request.POST.get('n_questoes', 10))
    tempo_por_q  = int(request.POST.get('tempo_por_q', 30))

    n_questoes  = max(5, min(20, n_questoes))
    tempo_por_q = max(15, min(60, tempo_por_q))

    categoria = None
    if categoria_id:
        try:
            categoria = Categoria.objects.get(pk=categoria_id)
        except Categoria.DoesNotExist:
            pass

    # Usa questoes ja revisadas (aprovadas). Campo 'ativo' nao existe em Questao.
    qs = Questao.objects.filter(revisada=True, rejeitada_definitiva=False)
    if categoria:
        qs = qs.filter(categoria=categoria)

    ids = list(qs.values_list('pk', flat=True))
    if len(ids) < n_questoes:
        messages.error(request, 'Questoes insuficientes no banco para este duelo.')
        return redirect('duelo_home')

    import random as _random
    escolhidos = _random.sample(ids, n_questoes)

    duelo = Duelo.objects.create(
        criador=user,
        categoria=categoria,
        n_questoes=n_questoes,
        tempo_por_q=tempo_por_q,
    )
    duelo.questoes.set(escolhidos)

    return redirect('duelo_sala', codigo=duelo.codigo)


@login_required
def duelo_sala(request, codigo):
    """Sala de espera do duelo — exibe codigo para compartilhar."""
    user  = request.user
    duelo = get_object_or_404(Duelo, codigo=codigo)

    if duelo.criador != user and duelo.adversario != user:
        if duelo.status == 'aguardando' and duelo.adversario is None:
            duelo.adversario = user
            duelo.save(update_fields=['adversario'])
        elif duelo.status not in ('aguardando', 'em_andamento'):
            messages.error(request, 'Este duelo nao esta mais disponivel.')
            return redirect('duelo_home')
        else:
            messages.error(request, 'Voce nao faz parte deste duelo.')
            return redirect('duelo_home')

    if duelo.status == 'em_andamento':
        return redirect('duelo_jogar', duelo_id=duelo.pk)

    return render(request, 'quiz/duelo_sala.html', {
        'duelo':       duelo,
        'sou_criador': duelo.criador == user,
    })


@login_required
@require_POST
@ratelimit(key='user', rate='20/m', method='POST', block=True)
def api_duelo_entrar(request):
    """API — entra em um duelo pelo codigo."""
    import json as _json
    try:
        body   = _json.loads(request.body)
        codigo = body.get('codigo', '').strip().upper()
    except Exception:
        return JsonResponse({'erro': 'Payload invalido'}, status=400)

    try:
        duelo = Duelo.objects.get(codigo=codigo)
    except Duelo.DoesNotExist:
        return JsonResponse({'erro': 'Codigo nao encontrado'}, status=404)

    user = request.user
    if duelo.status != 'aguardando':
        return JsonResponse({'erro': 'Duelo nao esta aguardando oponente'}, status=400)
    if duelo.criador == user:
        return JsonResponse({'erro': 'Voce criou este duelo!'}, status=400)
    if duelo.adversario and duelo.adversario != user:
        return JsonResponse({'erro': 'Duelo ja tem oponente'}, status=400)

    duelo.adversario = user
    duelo.save(update_fields=['adversario'])

    return JsonResponse({'ok': True, 'url': '/duelo/sala/{}/'.format(duelo.codigo)})


@login_required
def duelo_jogar(request, duelo_id):
    """Tela principal do jogo — polling via JS a cada 1s."""
    user  = request.user
    duelo = get_object_or_404(Duelo, pk=duelo_id)

    if duelo.criador != user and duelo.adversario != user:
        messages.error(request, 'Voce nao faz parte deste duelo.')
        return redirect('duelo_home')

    if duelo.status == 'finalizado':
        return redirect('duelo_resultado', duelo_id=duelo.pk)

    if duelo.status == 'aguardando' and duelo.adversario is not None:
        from django.utils import timezone as _tz
        duelo.status      = 'em_andamento'
        duelo.iniciado_em = _tz.now()
        duelo.save(update_fields=['status', 'iniciado_em'])

    questoes_lista = list(duelo.questoes_lista)
    questao_atual  = questoes_lista[duelo.questao_atual] if duelo.questao_atual < len(questoes_lista) else None
    # Alternativa nao tem related_name nem campo 'letra' — usa accessor default e ordena por id
    alternativas   = list(questao_atual.alternativa_set.order_by('id')) if questao_atual else []

    ja_respondi = False
    if questao_atual:
        ja_respondi = RespostaDuelo.objects.filter(
            duelo=duelo, usuario=user, questao=questao_atual
        ).exists()

    oponente = duelo.adversario if duelo.criador == user else duelo.criador

    meus_acertos     = RespostaDuelo.objects.filter(duelo=duelo, usuario=user, acertou=True).count()
    acertos_oponente = RespostaDuelo.objects.filter(
        duelo=duelo, usuario=oponente, acertou=True
    ).count() if oponente else 0

    return render(request, 'quiz/duelo_jogar.html', {
        'duelo':            duelo,
        'questao_atual':    questao_atual,
        'alternativas':     alternativas,
        'ja_respondi':      ja_respondi,
        'numero_questao':   duelo.questao_atual + 1,
        'total_questoes':   duelo.n_questoes,
        'oponente':         oponente,
        'meus_acertos':     meus_acertos,
        'acertos_oponente': acertos_oponente,
        'tempo_por_q':      duelo.tempo_por_q,
    })


@login_required
@require_POST
@ratelimit(key='user', rate='60/m', method='POST', block=True)
def api_duelo_responder(request, duelo_id):
    """API — registra resposta e avanca questao se ambos responderam."""
    import json as _json
    from django.utils import timezone as _tz
    from django.db import transaction as _tx

    duelo = get_object_or_404(Duelo, pk=duelo_id)
    user  = request.user

    if duelo.criador != user and duelo.adversario != user:
        return JsonResponse({'erro': 'Acesso negado'}, status=403)

    if duelo.status != 'em_andamento':
        return JsonResponse({'erro': 'Duelo nao esta em andamento'}, status=400)

    try:
        body     = _json.loads(request.body)
        alt_id   = body.get('alternativa_id')
        tempo_ms = int(body.get('tempo_ms', 0))
        q_index  = int(body.get('questao_index', duelo.questao_atual))
    except Exception:
        return JsonResponse({'erro': 'Payload invalido'}, status=400)

    questoes_lista = list(duelo.questoes_lista)
    if q_index >= len(questoes_lista):
        return JsonResponse({'erro': 'Indice invalido'}, status=400)

    questao = questoes_lista[q_index]

    if RespostaDuelo.objects.filter(duelo=duelo, usuario=user, questao=questao).exists():
        return JsonResponse({'ok': True, 'duplicado': True})

    acertou     = False
    alternativa = None
    if alt_id:
        try:
            alternativa = questao.alternativa_set.get(pk=alt_id)
            acertou     = alternativa.correta
        except Exception:
            _silencioso("view_bloco_12")
    RespostaDuelo.objects.create(
        duelo=duelo,
        usuario=user,
        questao=questao,
        alternativa=alternativa,
        acertou=acertou,
        tempo_ms=tempo_ms,
    )

    participantes      = [p for p in [duelo.criador, duelo.adversario] if p]
    respostas_q        = RespostaDuelo.objects.filter(duelo=duelo, questao=questao).count()
    ambos_responderam  = respostas_q >= len(participantes)
    proxima_questao    = duelo.questao_atual
    encerrou           = False

    if ambos_responderam and q_index == duelo.questao_atual:
        with _tx.atomic():
            duelo_locked = Duelo.objects.select_for_update().get(pk=duelo.pk)
            if duelo_locked.questao_atual == q_index:
                duelo_locked.questao_atual += 1
                if duelo_locked.questao_atual >= duelo_locked.n_questoes:
                    pts_c = RespostaDuelo.objects.filter(
                        duelo=duelo, usuario=duelo.criador, acertou=True).count()
                    pts_a = RespostaDuelo.objects.filter(
                        duelo=duelo, usuario=duelo.adversario, acertou=True
                    ).count() if duelo.adversario else 0
                    duelo_locked.pontos_criador    = pts_c
                    duelo_locked.pontos_adversario = pts_a
                    duelo_locked.status            = 'finalizado'
                    duelo_locked.encerrado_em      = _tz.now()
                    duelo_locked.save(update_fields=[
                        'questao_atual', 'pontos_criador', 'pontos_adversario',
                        'status', 'encerrado_em'])
                    encerrou = True
                else:
                    duelo_locked.save(update_fields=['questao_atual'])
                proxima_questao = duelo_locked.questao_atual

    return JsonResponse({
        'ok':              True,
        'acertou':         acertou,
        'proxima_questao': proxima_questao,
        'encerrou':        encerrou,
    })


@login_required
def api_duelo_status(request, duelo_id):
    """API — polling de estado do duelo (GET)."""
    duelo = get_object_or_404(Duelo, pk=duelo_id)
    user  = request.user

    if duelo.criador != user and duelo.adversario != user:
        return JsonResponse({'erro': 'Acesso negado'}, status=403)

    oponente       = duelo.adversario if duelo.criador == user else duelo.criador
    questoes_lista = list(duelo.questoes_lista)
    q_index        = duelo.questao_atual

    oponente_respondeu = False
    if oponente and q_index < len(questoes_lista):
        questao = questoes_lista[q_index]
        oponente_respondeu = RespostaDuelo.objects.filter(
            duelo=duelo, usuario=oponente, questao=questao).exists()

    meus_acertos     = RespostaDuelo.objects.filter(
        duelo=duelo, usuario=user, acertou=True).count()
    acertos_oponente = RespostaDuelo.objects.filter(
        duelo=duelo, usuario=oponente, acertou=True
    ).count() if oponente else 0

    return JsonResponse({
        'status':             duelo.status,
        'questao_atual':      duelo.questao_atual,
        'n_questoes':         duelo.n_questoes,
        'meus_acertos':       meus_acertos,
        'acertos_oponente':   acertos_oponente,
        'oponente_username':  oponente.username if oponente else None,
        'oponente_respondeu': oponente_respondeu,
        'adversario_entrou':  duelo.adversario is not None,
        'url_resultado':      '/duelo/{}/resultado/'.format(duelo.pk) if duelo.status == 'finalizado' else None,
    })


@login_required
def duelo_resultado(request, duelo_id):
    """Pagina de resultado final do duelo."""
    duelo = get_object_or_404(Duelo, pk=duelo_id)
    user  = request.user

    if duelo.criador != user and duelo.adversario != user:
        messages.error(request, 'Voce nao faz parte deste duelo.')
        return redirect('duelo_home')

    if duelo.status not in ('finalizado', 'cancelado'):
        return redirect('duelo_jogar', duelo_id=duelo.pk)

    oponente = duelo.adversario if duelo.criador == user else duelo.criador

    if duelo.criador == user:
        meus_pts     = duelo.pontos_criador
        pts_oponente = duelo.pontos_adversario
    else:
        meus_pts     = duelo.pontos_adversario
        pts_oponente = duelo.pontos_criador

    if meus_pts > pts_oponente:
        resultado = 'vitoria'
    elif meus_pts < pts_oponente:
        resultado = 'derrota'
    else:
        resultado = 'empate'

    questoes_lista = list(duelo.questoes_lista)
    detalhes = []
    for i, q in enumerate(questoes_lista):
        minha_resp    = RespostaDuelo.objects.filter(duelo=duelo, usuario=user, questao=q).first()
        resp_oponente = RespostaDuelo.objects.filter(
            duelo=duelo, usuario=oponente, questao=q).first() if oponente else None
        detalhes.append({
            'numero':        i + 1,
            'questao':       q,
            'minha_resp':    minha_resp,
            'resp_oponente': resp_oponente,
        })

    return render(request, 'quiz/duelo_resultado.html', {
        'duelo':        duelo,
        'oponente':     oponente,
        'meus_pts':     meus_pts,
        'pts_oponente': pts_oponente,
        'resultado':    resultado,
        'detalhes':     detalhes,
        'total':        duelo.n_questoes,
    })


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 26 — SIMULADO COLETIVO
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def coletivo_home(request):
    """Lobby do Simulado Coletivo."""
    user = request.user

    # Salas abertas (aguardando) que o usuário pode entrar
    salas_abertas = SimuladoColetivo.objects.filter(
        status='aguardando'
    ).exclude(
        participantes__usuario=user
    ).select_related('criador', 'categoria').prefetch_related('participantes')[:20]

    # Salas do usuário (ativas ou recentes)
    minhas_salas = SimuladoColetivo.objects.filter(
        models.Q(criador=user) | models.Q(participantes__usuario=user)
    ).distinct().select_related('criador', 'categoria').order_by('-criado_em')[:15]

    categorias = Categoria.objects.all().order_by('nome')

    return render(request, 'quiz/coletivo_home.html', {
        'salas_abertas': salas_abertas,
        'minhas_salas':  minhas_salas,
        'categorias':    categorias,
    })


@login_required
@require_POST
def coletivo_criar(request):
    """Cria uma nova sala de simulado coletivo."""
    user = request.user
    categoria_id  = request.POST.get('categoria_id') or None
    n_questoes    = int(request.POST.get('n_questoes', 10))
    tempo_por_q   = int(request.POST.get('tempo_por_q', 30))
    max_jogadores = int(request.POST.get('max_jogadores', 20))

    n_questoes    = max(5,  min(30, n_questoes))
    tempo_por_q   = max(15, min(60, tempo_por_q))
    max_jogadores = max(2,  min(50, max_jogadores))

    categoria = None
    if categoria_id:
        try:
            categoria = Categoria.objects.get(pk=categoria_id)
        except Categoria.DoesNotExist:
            pass

    # Usa questoes ja revisadas (aprovadas). Campo 'ativo' nao existe em Questao.
    qs = Questao.objects.filter(revisada=True, rejeitada_definitiva=False)
    if categoria:
        qs = qs.filter(categoria=categoria)

    ids = list(qs.values_list('pk', flat=True))
    if len(ids) < n_questoes:
        messages.error(request, 'Questoes insuficientes no banco para este simulado.')
        return redirect('coletivo_home')

    import random as _r
    escolhidos = _r.sample(ids, n_questoes)

    sala = SimuladoColetivo.objects.create(
        criador=user,
        categoria=categoria,
        n_questoes=n_questoes,
        tempo_por_q=tempo_por_q,
        max_jogadores=max_jogadores,
    )
    sala.questoes.set(escolhidos)

    # Criador entra automaticamente
    ParticipanteColetivo.objects.create(simulado=sala, usuario=user)

    return redirect('coletivo_sala', codigo=sala.codigo)


@login_required
def coletivo_sala(request, codigo):
    """Sala de espera — aguarda o criador iniciar."""
    user = request.user
    sala = get_object_or_404(SimuladoColetivo, codigo=codigo)

    # Entrar na sala se ainda não participando
    if not ParticipanteColetivo.objects.filter(simulado=sala, usuario=user).exists():
        if sala.status != 'aguardando':
            messages.error(request, 'Esta sala nao esta mais aberta.')
            return redirect('coletivo_home')
        n_participantes = sala.participantes.count()
        if n_participantes >= sala.max_jogadores:
            messages.error(request, 'Sala cheia.')
            return redirect('coletivo_home')
        ParticipanteColetivo.objects.create(simulado=sala, usuario=user)

    if sala.status == 'em_andamento':
        return redirect('coletivo_jogar', sala_id=sala.pk)
    if sala.status == 'finalizado':
        return redirect('coletivo_resultado', sala_id=sala.pk)

    participantes = sala.participantes.select_related('usuario').order_by('entrou_em')

    return render(request, 'quiz/coletivo_sala.html', {
        'sala':           sala,
        'participantes':  participantes,
        'sou_criador':    sala.criador == user,
        'n_participantes':participantes.count(),
    })


@login_required
@require_POST
def coletivo_iniciar(request, sala_id):
    """Criador inicia o simulado — só ele pode."""
    user = request.user
    sala = get_object_or_404(SimuladoColetivo, pk=sala_id)

    if sala.criador != user:
        return JsonResponse({'erro': 'Apenas o criador pode iniciar'}, status=403)
    if sala.status != 'aguardando':
        return JsonResponse({'erro': 'Sala nao esta aguardando'}, status=400)
    if sala.participantes.count() < 1:
        return JsonResponse({'erro': 'Nenhum participante na sala'}, status=400)

    from django.utils import timezone as _tz
    sala.status      = 'em_andamento'
    sala.iniciado_em = _tz.now()
    sala.save(update_fields=['status', 'iniciado_em'])

    return JsonResponse({'ok': True})


@login_required
def coletivo_jogar(request, sala_id):
    """Tela de jogo do simulado coletivo."""
    user = request.user
    sala = get_object_or_404(SimuladoColetivo, pk=sala_id)

    if not ParticipanteColetivo.objects.filter(simulado=sala, usuario=user).exists():
        messages.error(request, 'Voce nao esta nesta sala.')
        return redirect('coletivo_home')

    if sala.status == 'finalizado':
        return redirect('coletivo_resultado', sala_id=sala.pk)

    questoes_lista = list(sala.questoes_lista)
    idx = sala.questao_atual
    questao_atual = questoes_lista[idx] if idx < len(questoes_lista) else None
    # Alternativa nao tem related_name nem campo 'letra' — usa accessor default e ordena por id
    alternativas  = list(questao_atual.alternativa_set.order_by('id')) if questao_atual else []

    ja_respondi = False
    if questao_atual:
        ja_respondi = RespostaColetivo.objects.filter(
            simulado=sala, usuario=user, questao=questao_atual
        ).exists()

    n_responderam = RespostaColetivo.objects.filter(
        simulado=sala, questao=questao_atual
    ).count() if questao_atual else 0

    n_total = sala.participantes.count()

    meus_pontos = ParticipanteColetivo.objects.filter(
        simulado=sala, usuario=user
    ).values_list('pontos', flat=True).first() or 0

    return render(request, 'quiz/coletivo_jogar.html', {
        'sala':          sala,
        'questao_atual': questao_atual,
        'alternativas':  alternativas,
        'ja_respondi':   ja_respondi,
        'numero_questao':idx + 1,
        'total_questoes':sala.n_questoes,
        'n_responderam': n_responderam,
        'n_total':       n_total,
        'meus_pontos':   meus_pontos,
        'tempo_por_q':   sala.tempo_por_q,
    })


@login_required
@require_POST
@ratelimit(key='user', rate='60/m', method='POST', block=True)
def api_coletivo_responder(request, sala_id):
    """Registra resposta — avanca questao quando todos responderam ou timer expirou."""
    import json as _json
    from django.utils import timezone as _tz
    from django.db import transaction as _tx

    sala = get_object_or_404(SimuladoColetivo, pk=sala_id)
    user = request.user

    if not ParticipanteColetivo.objects.filter(simulado=sala, usuario=user).exists():
        return JsonResponse({'erro': 'Acesso negado'}, status=403)
    if sala.status != 'em_andamento':
        return JsonResponse({'erro': 'Simulado nao em andamento'}, status=400)

    try:
        body     = _json.loads(request.body)
        alt_id   = body.get('alternativa_id')
        tempo_ms = int(body.get('tempo_ms', 0))
        q_index  = int(body.get('questao_index', sala.questao_atual))
    except Exception:
        return JsonResponse({'erro': 'Payload invalido'}, status=400)

    questoes_lista = list(sala.questoes_lista)
    if q_index >= len(questoes_lista):
        return JsonResponse({'erro': 'Indice invalido'}, status=400)

    questao = questoes_lista[q_index]

    if RespostaColetivo.objects.filter(simulado=sala, usuario=user, questao=questao).exists():
        return JsonResponse({'ok': True, 'duplicado': True})

    acertou     = False
    alternativa = None
    if alt_id:
        try:
            alternativa = questao.alternativa_set.get(pk=alt_id)
            acertou     = alternativa.correta
        except Exception:
            _silencioso("view_bloco_13")
    RespostaColetivo.objects.create(
        simulado=sala,
        usuario=user,
        questao=questao,
        alternativa=alternativa,
        acertou=acertou,
        tempo_ms=tempo_ms,
    )

    # Atualizar pontos do participante
    if acertou:
        ParticipanteColetivo.objects.filter(
            simulado=sala, usuario=user
        ).update(pontos=models.F('pontos') + 1)

    # Verificar se todos responderam — avanca questao
    n_part      = sala.participantes.count()
    n_resp_q    = RespostaColetivo.objects.filter(simulado=sala, questao=questao).count()
    encerrou    = False
    proxima     = sala.questao_atual

    if n_resp_q >= n_part and q_index == sala.questao_atual:
        with _tx.atomic():
            sala_lock = SimuladoColetivo.objects.select_for_update().get(pk=sala.pk)
            if sala_lock.questao_atual == q_index:
                sala_lock.questao_atual += 1
                if sala_lock.questao_atual >= sala_lock.n_questoes:
                    sala_lock.status       = 'finalizado'
                    sala_lock.encerrado_em = _tz.now()
                    sala_lock.save(update_fields=['questao_atual', 'status', 'encerrado_em'])
                    encerrou = True
                else:
                    sala_lock.save(update_fields=['questao_atual'])
                proxima = sala_lock.questao_atual

    return JsonResponse({
        'ok':      True,
        'acertou': acertou,
        'proxima': proxima,
        'encerrou':encerrou,
    })


@login_required
def api_coletivo_status(request, sala_id):
    """Polling de estado da sala — GET."""
    sala = get_object_or_404(SimuladoColetivo, pk=sala_id)
    user = request.user

    participando = ParticipanteColetivo.objects.filter(simulado=sala, usuario=user).exists()
    if not participando and sala.criador != user:
        return JsonResponse({'erro': 'Acesso negado'}, status=403)

    questoes_lista = list(sala.questoes_lista)
    q_index = sala.questao_atual
    n_responderam = 0
    if q_index < len(questoes_lista):
        questao = questoes_lista[q_index]
        n_responderam = RespostaColetivo.objects.filter(
            simulado=sala, questao=questao
        ).count()

    # Top-3 ranking ao vivo
    top = list(
        sala.participantes.order_by('-pontos', 'entrou_em')
        .select_related('usuario')[:3]
        .values('usuario__username', 'pontos')
    )

    meus_pontos = ParticipanteColetivo.objects.filter(
        simulado=sala, usuario=user
    ).values_list('pontos', flat=True).first() or 0

    return JsonResponse({
        'status':         sala.status,
        'questao_atual':  sala.questao_atual,
        'n_questoes':     sala.n_questoes,
        'n_responderam':  n_responderam,
        'n_participantes':sala.participantes.count(),
        'meus_pontos':    meus_pontos,
        'top3':           top,
        'url_resultado':  '/coletivo/{}/resultado/'.format(sala.pk) if sala.status == 'finalizado' else None,
        'iniciou':        sala.status == 'em_andamento',
    })


@login_required
def coletivo_resultado(request, sala_id):
    """Ranking final do simulado coletivo."""
    sala = get_object_or_404(SimuladoColetivo, pk=sala_id)
    user = request.user

    if not ParticipanteColetivo.objects.filter(simulado=sala, usuario=user).exists():
        if sala.criador != user:
            messages.error(request, 'Voce nao participou desta sala.')
            return redirect('coletivo_home')

    ranking = list(
        sala.participantes.order_by('-pontos', 'entrou_em')
        .select_related('usuario')
    )

    # Posicao do usuario
    minha_posicao = next(
        (i + 1 for i, p in enumerate(ranking) if p.usuario == user), None
    )
    meus_pontos = next(
        (p.pontos for p in ranking if p.usuario == user), 0
    )

    # Gabarito
    questoes_lista = list(sala.questoes_lista)
    gabarito = []
    for i, q in enumerate(questoes_lista):
        minha_resp = RespostaColetivo.objects.filter(
            simulado=sala, usuario=user, questao=q
        ).first()
        n_acertos = RespostaColetivo.objects.filter(
            simulado=sala, questao=q, acertou=True
        ).count()
        n_total = RespostaColetivo.objects.filter(
            simulado=sala, questao=q
        ).count()
        gabarito.append({
            'numero':     i + 1,
            'questao':    q,
            'minha_resp': minha_resp,
            'n_acertos':  n_acertos,
            'n_total':    n_total,
            'pct_acerto': round(n_acertos * 100 / n_total) if n_total else 0,
        })

    total_participantes = len(ranking)

    return render(request, 'quiz/coletivo_resultado.html', {
        'sala':               sala,
        'ranking':            ranking,
        'minha_posicao':      minha_posicao,
        'meus_pontos':        meus_pontos,
        'total_participantes':total_participantes,
        'gabarito':           gabarito,
    })


# ══════════════════════════════════════════════════════════════════════════════
# SPRINT 28 — MONETIZAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

# ── Definição de planos ────────────────────────────────────────────────────

PLANOS_CONFIG = {
    'gratuito': {
        'nome':      'Gratuito',
        'preco':     0,
        'preco_txt': 'Grátis',
        'cor':       'slate',
        'emoji':     '🎓',
        'recursos': [
            ('check', '20 questões por dia'),
            ('check', 'Quiz por disciplina'),
            ('check', 'Histórico básico'),
            ('check', 'Caderno de erros'),
            ('close', 'Simulado completo ilimitado'),
            ('close', 'Tutor IA'),
            ('close', 'Duelo em Tempo Real'),
            ('close', 'Simulado Coletivo'),
            ('close', 'Relatórios PDF'),
            ('close', 'Análise preditiva de banca'),
        ],
    },
    'pro': {
        'nome':      'PRO',
        'preco':     1490,   # centavos — R$ 14,90/mês
        'preco_txt': 'R$ 14,90/mês',
        'cor':       'violet',
        'emoji':     '🚀',
        'destaque':  True,
        'recursos': [
            ('check', 'Questões ilimitadas'),
            ('check', 'Todos os modos de estudo'),
            ('check', 'Tutor IA personalizado'),
            ('check', 'Simulado completo (110Q)'),
            ('check', 'Duelo em Tempo Real'),
            ('check', 'Simulado Coletivo'),
            ('check', 'Análise preditiva de banca'),
            ('check', 'Relatório de desempenho IA'),
            ('close', 'Relatórios PDF'),
            ('close', 'Suporte prioritário'),
        ],
    },
    'premium': {
        'nome':      'Premium',
        'preco':     2990,   # centavos — R$ 29,90/mês (teto)
        'preco_txt': 'R$ 29,90/mês',
        'cor':       'amber',
        'emoji':     '👑',
        'recursos': [
            ('check', 'Tudo do plano PRO'),
            ('check', 'Relatórios PDF exportáveis'),
            ('check', 'Suporte prioritário por e-mail'),
            ('check', 'Acesso antecipado a novidades'),
            ('check', 'Grupo de estudo exclusivo'),
            ('check', 'Sessões ilimitadas de Tutor IA'),
            ('check', 'Metas e plano personalizado IA'),
            ('check', 'Análise de banca por concurso'),
            ('check', 'Flashcards IA ilimitados'),
            ('check', 'Exportar histórico CSV'),
            ('check', 'Badge "Premium" no perfil'),
        ],
    },
}

# ── Decorator de acesso ────────────────────────────────────────────────────

def requer_plano(plano_minimo='pro'):
    """
    Decorator que exige plano >= plano_minimo.
    Redireciona para /planos/ com mensagem se o plano for insuficiente.
    Uso: @requer_plano('pro') ou @requer_plano('premium')
    """
    from functools import wraps
    ordem = ['gratuito', 'pro', 'premium']

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            # plano removido (app 100% gratuita)
            plano_obj = type("Stub", (), {"plano": "gratuito", "ativo": True})()
            plano_atual = plano_obj.plano if not plano_obj.expirado else 'gratuito'
            if ordem.index(plano_atual) < ordem.index(plano_minimo):
                messages.warning(
                    request,
                    f'Esta funcionalidade requer o plano {plano_minimo.upper()}. '
                    f'Faça upgrade para continuar!'
                )
                return redirect('planos')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def _get_plano_usuario(user):
    """Helper — retorna PlanoUsuario, cria gratuito se não existir."""
    # plano removido
    plano = type("Stub", (), {"plano": "gratuito", "ativo": True})()
    if plano.expirado and plano.plano != 'gratuito':
        plano.plano = 'gratuito'
        plano.ativo = True
        plano.expira_em = None
        plano.save(update_fields=['plano', 'ativo', 'expira_em'])
    return plano


# ── Views ─────────────────────────────────────────────────────────────────

def planos(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


def cancelar_assinatura(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


def minha_assinatura(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


def simular_upgrade(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


def api_meu_plano(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


# ═══════════════════════════════════════════════════════════════════════════════
# PAINEL DE SISTEMA — acesso exclusivo para superusuários
# ═══════════════════════════════════════════════════════════════════════════════

def _is_superuser(user):
    return user.is_superuser


def _registrar_log(nivel, mensagem, origem='sistema', detalhe='', usuario=None):
    """Utilitário para criar entradas no LogSistema de qualquer lugar do código."""
    from ..models import LogSistema
    LogSistema.objects.create(
        nivel=nivel,
        origem=origem,
        mensagem=mensagem,
        detalhe=detalhe,
        usuario=usuario,
    )


@login_required(login_url='account_login')
@user_passes_test(_is_superuser, login_url='admin_painel')
def admin_sistema(request):
    """Painel de configurações e monitoramento do sistema (superuser only)."""
    import django
    import platform
    from ..models import LogSistema
    from django.conf import settings as _s

    # ── Logs ──────────────────────────────────────────────────────────────────
    nivel_filtro = request.GET.get('nivel', '')
    logs_qs = LogSistema.objects.select_related('usuario')
    if nivel_filtro:
        logs_qs = logs_qs.filter(nivel=nivel_filtro)
    logs = logs_qs[:200]

    contagem_nivel = {
        'INFO':    LogSistema.objects.filter(nivel='INFO').count(),
        'AVISO':   LogSistema.objects.filter(nivel='AVISO').count(),
        'ERRO':    LogSistema.objects.filter(nivel='ERRO').count(),
        'CRITICO': LogSistema.objects.filter(nivel='CRITICO').count(),
    }
    total_logs = sum(contagem_nivel.values())

    # ── Usuários ───────────────────────────────────────────────────────────────
    usuarios = User.objects.order_by('-date_joined').select_related()[:100]

    # ── Info do sistema ────────────────────────────────────────────────────────
    total_questoes   = Questao.objects.count()
    total_usuarios   = User.objects.count()
    total_respostas  = RespostaUsuario.objects.count()
    nao_revisadas    = Questao.objects.filter(revisada=False).count()
    questoes_s_img   = Questao.objects.filter(imagem='').count() + Questao.objects.filter(imagem=None).count()
    staff_users      = User.objects.filter(is_staff=True).count()

    info_sistema = {
        'django_version':  django.__version__,
        'python_version':  platform.python_version(),
        'debug':           _s.DEBUG,
        'db_engine':       _s.DATABASES['default']['ENGINE'].split('.')[-1],
        'total_questoes':  total_questoes,
        'nao_revisadas':   nao_revisadas,
        'questoes_s_img':  questoes_s_img,
        'total_usuarios':  total_usuarios,
        'staff_users':     staff_users,
        'total_respostas': total_respostas,
    }

    return render(request, 'quiz/admin/sistema.html', {
        'logs':          logs,
        'total_logs':    total_logs,
        'contagem_nivel': contagem_nivel,
        'nivel_filtro':  nivel_filtro,
        'usuarios':      usuarios,
        'info':          info_sistema,
        'categorias':    Categoria.objects.all().order_by('nome'),
    })


@login_required(login_url='account_login')
@user_passes_test(_is_superuser, login_url='home')
@require_POST
@ratelimit(key='user', rate='60/m', method='POST', block=True)
def api_admin_log_criar(request):
    """Cria um registro manual no LogSistema."""
    from ..models import LogSistema
    data = json.loads(request.body)
    nivel    = data.get('nivel', 'INFO')
    origem   = data.get('origem', 'manual')
    mensagem = data.get('mensagem', '').strip()
    detalhe  = data.get('detalhe', '')

    if not mensagem:
        return JsonResponse({'erro': 'Mensagem obrigatória.'}, status=400)
    if nivel not in ('INFO', 'AVISO', 'ERRO', 'CRITICO'):
        return JsonResponse({'erro': 'Nível inválido.'}, status=400)

    log = LogSistema.objects.create(
        nivel=nivel, origem=origem, mensagem=mensagem,
        detalhe=detalhe, usuario=request.user,
    )
    return JsonResponse({'ok': True, 'id': log.id})


@login_required(login_url='account_login')
@user_passes_test(_is_superuser, login_url='home')
@require_POST
def api_admin_log_deletar(request, log_id):
    """Deleta um registro do LogSistema."""
    from ..models import LogSistema
    log = get_object_or_404(LogSistema, id=log_id)
    log.delete()
    return JsonResponse({'ok': True})


@login_required(login_url='account_login')
@user_passes_test(_is_superuser, login_url='home')
@require_POST
def api_admin_logs_limpar(request):
    """Limpa todos os logs ou apenas de um nível específico."""
    from ..models import LogSistema
    data  = json.loads(request.body)
    nivel = data.get('nivel', '')
    if nivel:
        deleted, _ = LogSistema.objects.filter(nivel=nivel).delete()
    else:
        deleted, _ = LogSistema.objects.all().delete()
    return JsonResponse({'ok': True, 'deletados': deleted})


@login_required(login_url='account_login')
@user_passes_test(_is_superuser, login_url='home')
@require_POST
def api_admin_toggle_staff(request, user_id):
    """Alterna o status is_staff de um usuário."""
    target = get_object_or_404(User, id=user_id)
    if target == request.user:
        return JsonResponse({'erro': 'Você não pode alterar seu próprio status.'}, status=400)
    target.is_staff = not target.is_staff
    target.save(update_fields=['is_staff'])
    _registrar_log(
        'AVISO',
        f'Staff toggled: {target.username} → is_staff={target.is_staff}',
        origem='admin/sistema',
        usuario=request.user,
    )
    return JsonResponse({'ok': True, 'is_staff': target.is_staff, 'username': target.username})


@login_required(login_url='account_login')
@user_passes_test(_is_superuser, login_url='home')
def api_admin_questao_busca(request):
    """Busca rápida de questões para o editor inline do painel de sistema."""
    q = request.GET.get('q', '').strip()
    cat_id = request.GET.get('cat', '')
    qs = Questao.objects.select_related('categoria').prefetch_related('alternativa_set')
    if q:
        qs = qs.filter(Q(texto__icontains=q) | Q(id__icontains=q))
    if cat_id:
        qs = qs.filter(categoria_id=cat_id)
    qs = qs.order_by('id')[:20]
    resultado = []
    for questao in qs:
        resultado.append({
            'id':         questao.id,
            'texto':      questao.texto[:200],
            'categoria':  questao.categoria.nome,
            'tipo':       questao.tipo,
            'revisada':   questao.revisada,
            'assunto':    questao.assunto or '',
            'banca':      questao.banca or '',
            'ano':        questao.ano,
            'imagem_url': questao.imagem.url if questao.imagem else None,
            'alternativas': [
                {'id': a.id, 'texto': a.texto, 'correta': a.correta}
                for a in questao.alternativa_set.all()
            ],
        })
    return JsonResponse({'questoes': resultado})


@login_required(login_url='account_login')
@user_passes_test(_is_superuser, login_url='home')
@require_POST
def api_admin_questao_salvar(request, questao_id):
    """Salva edição rápida de uma questão (texto, assunto, banca, ano, revisada)."""
    questao = get_object_or_404(Questao, id=questao_id)
    data = json.loads(request.body)

    if 'texto' in data:
        questao.texto = data['texto'].strip()
    if 'assunto' in data:
        questao.assunto = data['assunto'].strip() or None
    if 'banca' in data:
        questao.banca = data['banca'].strip() or None
    if 'ano' in data:
        try:
            questao.ano = int(data['ano']) if data['ano'] else None
        except (ValueError, TypeError):
            questao.ano = None
    if 'revisada' in data:
        questao.revisada = bool(data['revisada'])
    if 'justificativa' in data:
        questao.justificativa = data['justificativa'].strip() or None

    questao.save()

    # Salva alternativas se enviadas
    if 'alternativas' in data:
        for alt_data in data['alternativas']:
            try:
                from ..models import Alternativa
                alt = Alternativa.objects.get(id=alt_data['id'], questao=questao)
                alt.texto   = alt_data.get('texto', alt.texto).strip()
                alt.correta = bool(alt_data.get('correta', alt.correta))
                alt.save()
            except Exception:
                _silencioso("view_bloco_14")
    _registrar_log(
        'INFO',
        f'Questão #{questao.id} editada manualmente',
        origem='editor-sistema',
        usuario=request.user,
    )
    return JsonResponse({'ok': True, 'id': questao.id})


# ═══════════════════════════════════════════════════════════════════════════
# CUPONS DE DESCONTO
# ═══════════════════════════════════════════════════════════════════════════

def aplicar_cupom(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD DE MÉTRICAS DO NEGÓCIO (apenas para admin)
# ═══════════════════════════════════════════════════════════════════════════

@login_required(login_url='account_login')
@user_passes_test(lambda u: u.is_superuser)
def metricas_negocio(request):
    """KPIs do produto — usuários, conversão, retenção, conteúdo, IA."""
    from datetime import timedelta
    from django.utils import timezone as _tz
    from django.db.models import Count
    from ..models import (Questao, Simulado, RespostaUsuario,
                         LogSistema)
    User = request.user.__class__
    agora = _tz.now()
    sete  = agora - timedelta(days=7)
    trinta = agora - timedelta(days=30)

    # ── Usuários
    total_usuarios = User.objects.count()
    novos_7d  = User.objects.filter(date_joined__gte=sete).count()
    novos_30d = User.objects.filter(date_joined__gte=trinta).count()
    ativos_7d = RespostaUsuario.objects.filter(data__gte=sete).values('usuario').distinct().count()

    # ── Planos
    plano_free = 0  # monetizacao removida
    plano_pro = 0
    plano_premium = 0
    pagantes = plano_pro + plano_premium
    taxa_conversao = round((pagantes / total_usuarios * 100), 1) if total_usuarios else 0.0

    # ── Engajamento
    total_respostas = RespostaUsuario.objects.count()
    respostas_7d = RespostaUsuario.objects.filter(data__gte=sete).count()
    total_simulados = Simulado.objects.filter(finalizado=True).count()
    simulados_7d = Simulado.objects.filter(finalizado=True, finalizado_em__gte=sete).count()

    # ── Conteúdo
    questoes_total = Questao.objects.count()
    questoes_aprov = Questao.objects.filter(revisada=True).count()
    questoes_pend = Questao.objects.filter(revisada=False, rejeitada_definitiva=False).count()

    # ── Top categorias por uso
    top_cats = (RespostaUsuario.objects.filter(data__gte=trinta)
                .values('questao__categoria__nome')
                .annotate(n=Count('id'))
                .order_by('-n')[:8])

    # ── Eventos recentes
    eventos = LogSistema.objects.order_by('-criado_em')[:15]

    # ── Uso de IA (hoje + tendência 7 dias)
    from ..ai_metrics import stats_do_dia, stats_ultimos_dias
    ia_hoje = stats_do_dia()
    ia_semana = stats_ultimos_dias(7)

    return render(request, 'quiz/admin_metricas.html', {
        'total_usuarios': total_usuarios,
        'novos_7d': novos_7d,
        'novos_30d': novos_30d,
        'ativos_7d': ativos_7d,
        'plano_free': plano_free,
        'plano_pro': plano_pro,
        'plano_premium': plano_premium,
        'pagantes': pagantes,
        'taxa_conversao': taxa_conversao,
        'total_respostas': total_respostas,
        'respostas_7d': respostas_7d,
        'total_simulados': total_simulados,
        'simulados_7d': simulados_7d,
        'questoes_total': questoes_total,
        'questoes_aprov': questoes_aprov,
        'questoes_pend': questoes_pend,
        'top_cats': top_cats,
        'eventos': eventos,
        'ia_hoje': ia_hoje,
        'ia_semana': ia_semana,
    })


# ═══════════════════════════════════════════════════════════════════════════
# SUPORTE AO USUÁRIO
# ═══════════════════════════════════════════════════════════════════════════

@login_required(login_url='account_login')
def suporte_lista(request):
    """Lista de tickets do usuário."""
    from ..models import TicketSuporte
    tickets = TicketSuporte.objects.filter(usuario=request.user).order_by('-criado_em')
    return render(request, 'quiz/suporte_lista.html', {'tickets': tickets})


@login_required(login_url='account_login')
@ratelimit(key='user', rate='5/h', method='POST', block=True)
def suporte_novo(request):
    """Abrir novo ticket. Rate limit 5/h/user evita spam floods:
    cada ticket dispara Discord + Telegram + email (3 notificacoes)."""
    from ..models import TicketSuporte
    from ..forms import SuporteTicketForm
    if request.method == 'POST':
        form = SuporteTicketForm(request.POST)
        if not form.is_valid():
            for erros in form.errors.values():
                for msg in erros:
                    messages.error(request, msg)
            return redirect('suporte_novo')
        assunto    = form.cleaned_data['assunto']
        mensagem   = form.cleaned_data['mensagem']
        categoria  = form.cleaned_data['categoria']
        email_alt  = (request.POST.get('email_contato') or '').strip()
        url_origem = (request.POST.get('url_origem') or '').strip()

        ticket = TicketSuporte.objects.create(
            usuario=request.user,
            categoria=categoria,
            assunto=assunto,
            mensagem=mensagem,
            email_contato=email_alt,
            url_origem=url_origem,
        )

        # Notifica equipe interna (Discord/Telegram) se configurado
        try:
            from ..notificacao_interna import notificar
            notificar(
                titulo=f'📬 Novo ticket #{ticket.id} · {ticket.get_categoria_display()}',
                mensagem=f'**{ticket.assunto}**\n\nPor: {request.user.username}\nUrl: {url_origem}\n\n{mensagem[:300]}',
                cor=0xf59e0b,
            )
        except Exception:
            _silencioso("view_bloco_15")
        # E-mail para equipe de suporte. Antes o check era `if EMAIL_HOST` que
        # so funcionava com SMTP — mas usamos Resend HTTP API via Anymail
        # (EMAIL_HOST fica vazio), entao nenhum email chegava em prod.
        try:
            from django.core.mail import send_mail
            from django.conf import settings as _s
            _backend = getattr(_s, 'EMAIL_BACKEND', '')
            _pode_enviar = _backend and 'console' not in _backend and 'dummy' not in _backend
            if _pode_enviar:
                send_mail(
                    subject=f'[SantuarioEdu] Ticket #{ticket.id} · {ticket.get_categoria_display()}',
                    message=(
                        f'Novo ticket de {request.user.username} ({request.user.email or "sem email"})\n\n'
                        f'Categoria: {ticket.get_categoria_display()}\n'
                        f'Assunto: {ticket.assunto}\n'
                        f'URL origem: {url_origem}\n\n'
                        f'Mensagem:\n{mensagem}\n\n'
                        f'Acesse: /admin/quiz/ticketsuporte/{ticket.id}/change/'
                    ),
                    from_email=_s.DEFAULT_FROM_EMAIL,
                    recipient_list=[getattr(_s, 'SUPORTE_EMAIL', _s.DEFAULT_FROM_EMAIL)],
                    fail_silently=True,
                )
        except Exception:
            _silencioso("view_bloco_16")
        messages.success(request, f'Ticket #{ticket.id} aberto! Responderemos em até 48h úteis.')
        return redirect('suporte_detalhe', ticket_id=ticket.id)

    # GET — formulário
    return render(request, 'quiz/suporte_novo.html', {
        'url_origem': request.GET.get('origem', request.META.get('HTTP_REFERER', '')),
    })


@login_required(login_url='account_login')
def suporte_detalhe(request, ticket_id):
    """Visualiza ticket + adiciona resposta."""
    from ..models import TicketSuporte, RespostaTicket
    ticket = get_object_or_404(TicketSuporte, id=ticket_id, usuario=request.user)

    if request.method == 'POST':
        msg = (request.POST.get('mensagem') or '').strip()
        if msg:
            RespostaTicket.objects.create(
                ticket=ticket, autor=request.user, mensagem=msg, eh_staff=False,
            )
            ticket.status = 'aberto'  # volta a aberto se estava aguardando
            ticket.save(update_fields=['status', 'atualizado_em'])
            messages.success(request, 'Sua mensagem foi enviada.')
            return redirect('suporte_detalhe', ticket_id=ticket.id)

    return render(request, 'quiz/suporte_detalhe.html', {
        'ticket': ticket,
        'respostas': ticket.respostas.all(),
    })


# ═══════════════════════════════════════════════════════════════════════════
# MARCAR QUESTÃO PRA REVISAR DEPOIS
# ═══════════════════════════════════════════════════════════════════════════


@login_required(login_url='account_login')
def questoes_marcadas(request):
    """Lista de questões marcadas pra revisar depois."""
    from ..models import QuestaoMarcada
    marcadas = (QuestaoMarcada.objects
                .filter(usuario=request.user)
                .select_related('questao', 'questao__categoria')
                .order_by('-criado_em'))
    return render(request, 'quiz/questoes_marcadas.html', {'marcadas': marcadas})


# ═══════════════════════════════════════════════════════════════════════════
# ONBOARDING POR CONCURSO + TRIAL PRO 7 DIAS
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# QUIZ "QUAL CONCURSO É PRA VOCÊ?" (lead magnet)
# ═══════════════════════════════════════════════════════════════════════════

def quiz_qual_concurso(request):
    """Quiz público — 5 perguntas → recomenda concurso → captura email."""
    return render(request, 'quiz_qual_concurso.html')


# ═══════════════════════════════════════════════════════════════════════════
# CARD COMPARTILHÁVEL DE PROGRESSO
# ═══════════════════════════════════════════════════════════════════════════

@login_required(login_url='account_login')
def card_progresso(request):
    """Página gera card 1080x1080 (Instagram) com KPIs do usuário."""
    from ..models import RespostaUsuario, Simulado, MetaEstudo
    from django.db.models import Count, Q
    from django.utils import timezone
    from datetime import timedelta

    sete = timezone.now() - timedelta(days=7)
    resps_semana = RespostaUsuario.objects.filter(usuario=request.user, data__gte=sete)
    total = resps_semana.count()
    acertos = resps_semana.filter(acertou=True).count()
    pct = round(acertos / total * 100) if total else 0

    sims = Simulado.objects.filter(
        usuario=request.user, finalizado=True, finalizado_em__gte=sete
    ).count()

    try:
        meta = request.user.meta
        streak = meta.streak_atual
    except Exception:
        streak = 0

    return render(request, 'quiz/card_progresso.html', {
        'total_semana': total,
        'acertos_semana': acertos,
        'pct': pct,
        'sims_semana': sims,
        'streak': streak,
    })


# ═══════════════════════════════════════════════════════════════════════════
# ANÁLISE POR SUBTEMA (granular)
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# REVISÃO RÁPIDA DE QUESTÕES (admin/staff)
# ═══════════════════════════════════════════════════════════════════════════

@login_required(login_url='account_login')
@user_passes_test(lambda u: u.is_staff)
def revisao_questoes_painel(request):
    """Painel dedicado pra revisar questões pendentes — mais rápido que /admin/."""
    from ..models import Categoria, Questao

    # Filtros
    cat_id      = request.GET.get('cat', '')
    apenas_ia   = request.GET.get('ia', '0') == '1'
    ordem       = request.GET.get('ordem', '-id')  # -id, id, ?

    qs = Questao.objects.filter(revisada=False, rejeitada_definitiva=False)
    if apenas_ia:
        qs = qs.filter(gerada_por_ia=True)
    if cat_id:
        qs = qs.filter(categoria_id=cat_id)
    qs = qs.select_related('categoria').prefetch_related('alternativa_set')

    if ordem == '?':
        qs = qs.order_by('?')
    else:
        qs = qs.order_by(ordem)

    # Paginação simples — 1 por vez (vista cartão grande)
    from django.core.paginator import Paginator
    paginator = Paginator(qs, 1)
    page_num = request.GET.get('page', 1)
    page = paginator.get_page(page_num)
    questao = page.object_list[0] if page.object_list else None

    # Stats globais
    total_pendentes = Questao.objects.filter(revisada=False, rejeitada_definitiva=False).count()
    total_aprovadas = Questao.objects.filter(revisada=True).count()
    total_rejeitadas = Questao.objects.filter(rejeitada_definitiva=True).count()

    # Lista de categorias com contador pendente + PATH hierarquico
    # (evita ambiguidade: 'Direito Constitucional' fica 'Direito > Direito Constitucional')
    from django.db.models import Count, Q
    cats_qs = (Categoria.objects
            .annotate(pendentes=Count('questao',
                      filter=Q(questao__revisada=False, questao__rejeitada_definitiva=False)))
            .filter(pendentes__gt=0)
            .select_related('parent')
            .order_by('-pendentes'))

    cats = []
    for c in cats_qs:
        # Reconstroi caminho subindo ate raiz
        partes = [c.nome]
        no = c.parent
        for _ in range(10):
            if not no:
                break
            partes.append(no.nome)
            no = no.parent
        cats.append({
            'id': c.id,
            'nome': c.nome,
            'caminho': ' > '.join(reversed(partes)),
            'pendentes': c.pendentes,
        })

    # Caminho hierarquico da questao atual (pra mostrar no card)
    caminho_questao = ''
    if questao and questao.categoria:
        partes_q = [questao.categoria.nome]
        no_q = questao.categoria.parent
        for _ in range(10):
            if not no_q:
                break
            partes_q.append(no_q.nome)
            no_q = no_q.parent
        caminho_questao = ' > '.join(reversed(partes_q))

    return render(request, 'quiz/revisao_painel.html', {
        'questao': questao,
        'page': page,
        'total_pendentes': total_pendentes,
        'total_aprovadas': total_aprovadas,
        'total_rejeitadas': total_rejeitadas,
        'categorias': cats,
        'cat_atual': int(cat_id) if cat_id.isdigit() else None,
        'apenas_ia': apenas_ia,
        'ordem': ordem,
        'caminho_questao': caminho_questao,
    })


@login_required(login_url='account_login')
@user_passes_test(lambda u: u.is_staff)
@require_POST
def api_revisar_acao(request, questao_id):
    """API de ação rápida: aprovar | reprovar | rejeitar | gerar_justificativa."""
    from ..models import Questao
    q = get_object_or_404(Questao, id=questao_id)
    acao = request.POST.get('acao', '')
    motivo = (request.POST.get('motivo') or '').strip()

    if acao == 'aprovar':
        # ── Bloqueia aprovação de questão sem justificativa ──
        if not (q.justificativa or '').strip():
            return JsonResponse({
                'ok': False,
                'erro': 'sem_justificativa',
                'msg': 'Esta questão não tem justificativa. Gere uma com IA ou edite manualmente antes de aprovar.'
            }, status=400)

        q.revisada = True
        q.motivo_rejeicao = ''
        q.rejeitada_definitiva = False
        q.save(update_fields=['revisada', 'motivo_rejeicao', 'rejeitada_definitiva'])
        return JsonResponse({'ok': True, 'novo_status': 'aprovada'})

    if acao == 'reprovar':
        q.motivo_rejeicao = motivo or (
            'Reprovada pelo revisor. Refaça garantindo clareza no enunciado, '
            'gabarito correto e justificativa completa com base legal.'
        )
        q.revisada = False
        q.save(update_fields=['motivo_rejeicao', 'revisada'])
        return JsonResponse({'ok': True, 'novo_status': 'em_correcao'})

    if acao == 'rejeitar':
        q.rejeitada_definitiva = True
        q.revisada = False
        q.save(update_fields=['rejeitada_definitiva', 'revisada'])
        return JsonResponse({'ok': True, 'novo_status': 'rejeitada'})

    if acao == 'excluir':
        q.delete()
        return JsonResponse({'ok': True, 'novo_status': 'excluida'})

    if acao == 'gerar_justificativa':
        # ── Chama IA na hora e salva no banco ──
        from ..ai_provider import gerar_json, AIError
        from ..prompts_justificativa import montar_prompt

        try:
            prompt = montar_prompt(q)
        except ValueError:
            return JsonResponse({
                'ok': False, 'erro': 'sem_gabarito',
                'msg': 'Não há alternativa marcada como correta. Corrija primeiro.'
            }, status=400)

        try:
            dados = gerar_json(prompt, max_tokens=2500, temperature=0.4, usuario=request.user)
        except AIError as e:
            return JsonResponse({'ok': False, 'erro': 'ia_falhou', 'msg': str(e)[:200]}, status=502)

        just = (dados.get('justificativa') or '').strip()
        assunto = (dados.get('assunto') or '').strip()[:255]
        if not just:
            return JsonResponse({'ok': False, 'erro': 'ia_vazia', 'msg': 'IA não retornou justificativa'}, status=502)

        q.justificativa = just
        if not q.assunto:
            q.assunto = assunto
        q.save(update_fields=['justificativa', 'assunto'])
        return JsonResponse({
            'ok': True,
            'justificativa': just,
            'assunto': q.assunto,
            'chars': len(just),
        })

    return JsonResponse({'ok': False, 'erro': 'ação inválida'}, status=400)


@login_required(login_url='account_login')
@user_passes_test(lambda u: u.is_staff)
def api_revisao_proxima(request):
    """
    Retorna a próxima questão pendente respeitando os filtros — em JSON.
    Substitui o reload de página inteira por um fetch (~200ms vs ~2s).

    Query params:
      cat: id da categoria (opcional)
      ordem: -id | id | ?
      apenas_ia: 0|1
      skip_id: se passado, ignora essa questão (evita mostrar a mesma que foi aprovada)
      problema: 'qualquer' | 'sem_justificativa' | 'sem_gabarito' | 'incompleto' |
                'referencia_imagem' | 'ok' — filtra por tipo de defeito auditado
    """
    from ..models import Questao
    from ..auditoria import detectar_flags, label_flag, FLAGS_GRAVES

    cat_id     = request.GET.get('cat', '')
    apenas_ia  = request.GET.get('apenas_ia', '0') == '1'
    ordem      = request.GET.get('ordem', '-id')
    skip_id    = request.GET.get('skip_id', '')
    problema   = request.GET.get('problema', '')  # opcional

    qs = Questao.objects.filter(revisada=False, rejeitada_definitiva=False)
    if apenas_ia:
        qs = qs.filter(gerada_por_ia=True)
    if cat_id.isdigit():
        qs = qs.filter(categoria_id=int(cat_id))
    if skip_id.isdigit():
        qs = qs.exclude(id=int(skip_id))
    qs = qs.select_related('categoria').prefetch_related('alternativa_set')
    if ordem == '?':
        qs = qs.order_by('?')
    else:
        qs = qs.order_by(ordem)

    # Map de "problema" (UI) → conjunto de flags que satisfazem
    PROBLEMA_MAP = {
        'qualquer':          FLAGS_GRAVES,
        'sem_justificativa': {'sem_justificativa'},
        'sem_gabarito':      {'sem_gabarito', 'multiplos_gabaritos'},
        'incompleto':        {
            'texto_muito_curto',
            'enunciado_termina_em_pontuacao_incompleta',
            'termina_em_conjuncao',
            'marcador_conteudo_faltando',
        },
        'referencia_imagem': {'referencia_a_imagem_sem_imagem'},
        'referencia_texto':  {'referencia_a_texto_ausente'},
        'referencia_apoio':  {'referencia_a_imagem_sem_imagem', 'referencia_a_texto_ausente'},
        'alternativas':      {
            'alternativa_vazia',
            'alternativa_muito_curta',
            'alternativas_duplicadas',
            'alternativa_igual_ao_enunciado',
            'numero_alts_invalido_ce',
            'numero_alts_invalido_me',
        },
    }

    def _passa_filtro(q, alts):
        if not problema:
            return True
        if problema == 'ok':
            return not detectar_flags(q, alts)
        if problema == 'com_imagem_arquivo':
            # So questoes com arquivo de imagem anexado (renderiza <img> real)
            return bool(getattr(q, 'imagem', None))
        if problema == 'com_figura_descrita':
            # So questoes com [FIGURA:...] no texto mas SEM arquivo anexado
            if getattr(q, 'imagem', None):
                return False
            texto = (q.texto or '')
            import re as _re
            return bool(_re.search(r'\[(?:FIGURA|IMAGEM|GR[AÁ]FICO|TABELA|MAPA):', texto, _re.I))
        # Backward-compat: alias antigo
        if problema == 'com_imagem':
            return bool(getattr(q, 'imagem', None))
        if problema == 'com_texto_apoio':
            # Heuristica: enunciado com separador "---" (colocado pela Vision entre
            # texto de apoio e enunciado) OU muito longo (> 500 chars indica apoio)
            texto = (q.texto or '')
            return '---' in texto or len(texto) > 500
        alvo = PROBLEMA_MAP.get(problema)
        if not alvo:
            return True
        flags = set(detectar_flags(q, alts))
        return bool(flags & alvo)

    # Se tem filtro por problema, precisamos iterar até achar match.
    # (Detectar_flags requer alternativas → não dá pra filtrar no ORM.)
    q = None
    total_restantes = 0
    if problema:
        for cand in qs.iterator(chunk_size=100):
            alts_c = list(cand.alternativa_set.all().order_by('id'))
            if _passa_filtro(cand, alts_c):
                total_restantes += 1
                if q is None:
                    q = cand
                    q._alts_cache = alts_c
                    q._flags_cache = detectar_flags(cand, alts_c)
        if not q:
            return JsonResponse({'ok': True, 'vazio': True, 'total_restantes': 0})
    else:
        q = qs.first()
        total_restantes = qs.count()
        if not q:
            return JsonResponse({'ok': True, 'vazio': True, 'total_restantes': 0})
        alts_c = list(q.alternativa_set.all().order_by('id'))
        q._alts_cache = alts_c
        q._flags_cache = detectar_flags(q, alts_c)

    alts = [
        {'id': a.id, 'texto': a.texto, 'correta': a.correta}
        for a in q._alts_cache
    ]
    flags_com_label = [
        {'flag': f, 'label': label_flag(f), 'grave': f in FLAGS_GRAVES}
        for f in q._flags_cache
    ]

    return JsonResponse({
        'ok': True,
        'total_restantes': total_restantes,
        'questao': {
            'id':                  q.id,
            'texto':               q.texto,
            'imagem':              q.imagem.url if q.imagem else '',
            'assunto':             q.assunto or '',
            'banca':               q.banca or '',
            'ano':                 q.ano,
            'categoria':           q.categoria.nome,
            'gerada_por_ia':       q.gerada_por_ia,
            'justificativa':       q.justificativa or '',
            'motivo_rejeicao':     q.motivo_rejeicao or '',
            'tentativas_correcao': q.tentativas_correcao,
            'alternativas':        alts,
            'flags':               flags_com_label,
        },
    })


@login_required(login_url='account_login')
@user_passes_test(lambda u: u.is_staff)
@require_POST
def api_revisao_bulk_approve(request):
    """
    Aprovação em lote de questões pendentes que atendem critérios seguros.

    Body (JSON):
      cat_id: filtrar por categoria (opcional)
      apenas_com_justif: default True (só aprova quem já tem justificativa)
      apenas_ia:         default True
      limite:            default 50, máximo 200 (segurança)

    Retorna { ok, aprovadas, total_candidatas, ids_aprovadas: [...] }
    """
    import json as _json
    from ..models import Questao
    try:
        body = _json.loads(request.body or '{}')
    except Exception:
        body = {}

    cat_id            = body.get('cat_id')
    apenas_com_justif = body.get('apenas_com_justif', True)
    apenas_ia         = body.get('apenas_ia', True)
    try:
        limite = min(200, max(1, int(body.get('limite', 50))))
    except (TypeError, ValueError):
        limite = 50

    qs = Questao.objects.filter(revisada=False, rejeitada_definitiva=False)
    if apenas_ia:
        qs = qs.filter(gerada_por_ia=True)
    if apenas_com_justif:
        qs = qs.exclude(justificativa__isnull=True).exclude(justificativa__exact='')
    if cat_id:
        qs = qs.filter(categoria_id=int(cat_id))

    # Exclui questões sem alternativa correta (falha de dados)
    from django.db.models import Count, Q as _Q
    qs = qs.annotate(
        _n_corretas=Count('alternativa', filter=_Q(alternativa__correta=True))
    ).filter(_n_corretas__gte=1)

    total_candidatas = qs.count()
    ids = list(qs.values_list('id', flat=True)[:limite])

    if not ids:
        return JsonResponse({'ok': True, 'aprovadas': 0, 'total_candidatas': 0, 'ids_aprovadas': []})

    Questao.objects.filter(id__in=ids).update(
        revisada=True, motivo_rejeicao='', rejeitada_definitiva=False
    )

    return JsonResponse({
        'ok': True,
        'aprovadas': len(ids),
        'total_candidatas': total_candidatas,
        'ids_aprovadas': ids,
    })


@login_required(login_url='account_login')
@user_passes_test(lambda u: u.is_staff)
def api_revisao_por_id(request, questao_id):
    """
    Retorna uma questão específica por ID — mesmo se já for aprovada.
    Usado no painel admin pra buscar questões reportadas por usuários.
    """
    from ..models import Questao
    from ..auditoria import detectar_flags, label_flag, FLAGS_GRAVES

    try:
        q = Questao.objects.select_related('categoria').prefetch_related('alternativa_set').get(id=questao_id)
    except Questao.DoesNotExist:
        return JsonResponse({'ok': False, 'erro': 'não encontrada'}, status=404)

    alts_c = list(q.alternativa_set.all().order_by('id'))
    flags = detectar_flags(q, alts_c)

    return JsonResponse({
        'ok': True,
        'total_restantes': 0,  # busca direta não tem "restantes"
        'status_atual': 'aprovada' if q.revisada else ('rejeitada' if q.rejeitada_definitiva else 'pendente'),
        'questao': {
            'id':                  q.id,
            'texto':               q.texto,
            'assunto':             q.assunto or '',
            'banca':               q.banca or '',
            'ano':                 q.ano,
            'categoria':           q.categoria.nome,
            'gerada_por_ia':       q.gerada_por_ia,
            'revisada':            q.revisada,
            'rejeitada_definitiva': q.rejeitada_definitiva,
            'justificativa':       q.justificativa or '',
            'motivo_rejeicao':     q.motivo_rejeicao or '',
            'tentativas_correcao': q.tentativas_correcao,
            'alternativas': [
                {'id': a.id, 'texto': a.texto, 'correta': a.correta} for a in alts_c
            ],
            'flags': [
                {'flag': f, 'label': label_flag(f), 'grave': f in FLAGS_GRAVES}
                for f in flags
            ],
        },
    })


@login_required(login_url='account_login')
@user_passes_test(lambda u: u.is_staff)
def api_revisao_duplicatas(request, questao_id):
    """
    Retorna até 5 questões similares à questao_id — usa difflib.SequenceMatcher.
    Restringimos a busca à mesma categoria para performance (o(n) sobre a
    disciplina, não sobre o banco todo).
    """
    from difflib import SequenceMatcher
    from ..models import Questao

    try:
        q_ref = Questao.objects.select_related('categoria').get(id=questao_id)
    except Questao.DoesNotExist:
        return JsonResponse({'ok': False, 'erro': 'não encontrada'}, status=404)

    texto_ref = (q_ref.texto or '').strip().lower()
    if len(texto_ref) < 30:
        return JsonResponse({'ok': True, 'duplicatas': []})

    candidatas = (Questao.objects
                  .filter(categoria=q_ref.categoria)
                  .exclude(id=q_ref.id)
                  .only('id', 'texto', 'revisada', 'rejeitada_definitiva')
                  [:500])

    hits = []
    for c in candidatas:
        t = (c.texto or '').strip().lower()
        if len(t) < 30:
            continue
        # Ratio rápido — bailar se muito diferente pra evitar cálculo caro
        if abs(len(t) - len(texto_ref)) > len(texto_ref):
            continue
        ratio = SequenceMatcher(None, texto_ref, t).quick_ratio()
        if ratio < 0.70:
            continue
        ratio = SequenceMatcher(None, texto_ref, t).ratio()
        if ratio >= 0.75:
            hits.append({
                'id':       c.id,
                'similaridade': round(ratio * 100),
                'texto':    (c.texto or '')[:150],
                'status':   'aprovada' if c.revisada else ('rejeitada' if c.rejeitada_definitiva else 'pendente'),
            })

    hits.sort(key=lambda h: -h['similaridade'])
    return JsonResponse({'ok': True, 'duplicatas': hits[:5]})


# ══════════════════════════════════════════════════════════════════════════════
# SEARCH GLOBAL & PRÓXIMA AÇÃO
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# CHECKOUT MERCADO PAGO
# ══════════════════════════════════════════════════════════════════════════════

def iniciar_checkout_mp(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


def mp_webhook(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


def pagamento_sucesso(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


def pagamento_falha(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


def pagamento_pendente(*args, **kwargs):
    """DEPRECATED — app 100% gratuita. Redireciona pro dashboard."""
    from django.shortcuts import redirect
    return redirect('dashboard' if args and hasattr(args[0], 'user') and args[0].user.is_authenticated else 'home')


# ═══════════════════════════════════════════════════════════════════════════
# GUEST QUIZ MODE — demo sem cadastro (max 3 questoes por sessao)
# ═══════════════════════════════════════════════════════════════════════════
# Reduz atrito de conversao: concurseiro cetico testa antes de dar email.
# Session-only (sem BD), rate-limit implicito via limite de 3.

GUEST_QUIZ_LIMITE = 3


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN STATUS — dashboard do fundador
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# BLOG — posts institucionais / SEO
# ═══════════════════════════════════════════════════════════════════════════


