from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from .models import (Categoria, Questao, Alternativa, RespostaUsuario,
                     LogSistema,
                     ResumoIA, MapaMental, TimelineLei, ComparativoBanca,
                     TermoGlossario)


# ── Branding do Admin ──────────────────────────────────────────────────────
admin.site.site_header = 'SantuarioEdu · Painel Administrativo'
admin.site.site_title  = 'SantuarioEdu Admin'
admin.site.index_title = 'Bem-vindo ao painel'
admin.site.empty_value_display = '—'


class AlternativaInline(admin.TabularInline):
    model = Alternativa
    extra = 4


class TemImagemFilter(admin.SimpleListFilter):
    """Filtro admin: questao tem imagem anexada?"""
    title = 'Tem imagem'
    parameter_name = 'tem_imagem'

    def lookups(self, request, model_admin):
        return (
            ('sim', 'Com imagem'),
            ('nao', 'Sem imagem'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'sim':
            return queryset.exclude(imagem='').exclude(imagem__isnull=True)
        if self.value() == 'nao':
            return queryset.filter(imagem='') | queryset.filter(imagem__isnull=True)
        return queryset


@admin.register(Questao)
class QuestaoAdmin(admin.ModelAdmin):
    inlines = [AlternativaInline]
    list_display = ('preview', 'categoria', 'tipo', 'banca', 'badge_imagem', 'badge_status', 'tentativas_correcao')
    list_filter = ('revisada', 'gerada_por_ia', 'rejeitada_definitiva', 'categoria', 'tipo', 'banca', TemImagemFilter)
    search_fields = ('texto', 'assunto', 'justificativa', 'motivo_rejeicao')
    list_per_page = 30
    actions = [
        'aprovar_revisao',
        'aprovar_se_valida',
        'reprovar_com_feedback_padrao',
        'marcar_rejeitada_definitiva',
        'reprocessar_agora',
        'reclassificar_por_tema_bulk',
    ]
    readonly_fields = ('tentativas_correcao',)

    fieldsets = (
        ('Conteúdo', {
            'fields': ('categoria', 'texto', 'imagem', 'tipo', 'assunto', 'justificativa'),
        }),
        ('Metadados', {
            'fields': ('banca', 'ano'),
        }),
        ('Status & Revisão', {
            'fields': ('revisada', 'gerada_por_ia', 'motivo_rejeicao',
                       'tentativas_correcao', 'rejeitada_definitiva'),
            'description': (
                '<ul>'
                '<li><strong>revisada=True</strong> → Aprovada, visível aos usuários.</li>'
                '<li><strong>motivo_rejeicao preenchido</strong> → entra na fila de correção pela IA.</li>'
                '<li><strong>rejeitada_definitiva=True</strong> → descartada de vez.</li>'
                '</ul>'
                'Após preencher motivo_rejeicao, rode: <code>python manage.py corrigir_rejeitadas</code>'
            ),
        }),
    )

    def preview(self, obj):
        return (obj.texto[:90] + '...') if len(obj.texto) > 90 else obj.texto
    preview.short_description = 'Enunciado'

    def badge_imagem(self, obj):
        from django.utils.safestring import mark_safe
        if obj.imagem:
            return mark_safe(
                '<span style="background:#dcfce7;color:#166534;padding:2px 8px;'
                'border-radius:8px;font-weight:bold;font-size:11px;">&#128247; sim</span>'
            )
        return mark_safe('<span style="color:#9ca3af;font-size:11px;">&mdash;</span>')
    badge_imagem.short_description = 'Imagem'

    def badge_status(self, obj):
        status = obj.status_revisao
        cores = {
            'aprovada':    ('#dcfce7', '#166534', '✓ aprovada'),
            'pendente':    ('#fef3c7', '#92400e', '⏳ pendente'),
            'em_correcao': ('#dbeafe', '#1e40af', '🤖 em correção'),
            'rejeitada':   ('#fee2e2', '#991b1b', '✗ rejeitada'),
        }
        bg, cor, rotulo = cores.get(status, ('#f3f4f6', '#374151', status))
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:8px;font-weight:bold;font-size:11px;">{}</span>',
            bg, cor, rotulo
        )
    badge_status.short_description = 'Status'

    # ── Actions ────────────────────────────────────────────────────────────
    @admin.action(description='✓ Aprovar (marcar como revisada)')
    def aprovar_revisao(self, request, queryset):
        n = queryset.update(revisada=True, motivo_rejeicao='', rejeitada_definitiva=False)
        self.message_user(request, f'{n} questão(ões) aprovada(s) e liberada(s) aos usuários.', messages.SUCCESS)

    @admin.action(description='🔍 Aprovar apenas se integridade OK (ME=1 correta / CE=2 alt)')
    def aprovar_se_valida(self, request, queryset):
        """Bulk approve com validacao — pula defeituosas."""
        from django.db.models import Count, Q
        ids_me = list(queryset.filter(tipo='ME')
            .annotate(n_corr=Count('alternativa', filter=Q(alternativa__correta=True)))
            .filter(n_corr=1).values_list('id', flat=True))
        ids_ce = list(queryset.filter(tipo='CE')
            .annotate(n_alt=Count('alternativa'))
            .filter(n_alt=2).values_list('id', flat=True))
        ids_ok = ids_me + ids_ce
        n = queryset.filter(id__in=ids_ok).update(revisada=True)
        n_skip = queryset.count() - n
        self.message_user(
            request,
            f'{n} aprovada(s). {n_skip} puladas por integridade defeituosa.',
            messages.SUCCESS if n_skip == 0 else messages.WARNING,
        )

    @admin.action(description='🔄 Reclassificar por tema (keywords Python)')
    def reclassificar_por_tema_bulk(self, request, queryset):
        """Roda logica de reclassificacao por keywords do comando."""
        from .management.commands.reclassificar_por_tema import (
            classificar_por_keywords, _match_categoria
        )
        from .models import Categoria

        reclass = 0
        for q in queryset:
            tema, score = classificar_por_keywords(q.texto)
            if not tema or score < 2:
                continue
            cats = _match_categoria(tema)
            if not cats:
                continue
            q.categoria = cats[0]
            q.save(update_fields=['categoria'])
            reclass += 1
        self.message_user(
            request, f'{reclass} questão(ões) reclassificada(s) por tema.',
            messages.SUCCESS,
        )

    @admin.action(description='✗ Reprovar (usa motivo padrão se vazio)')
    def reprovar_com_feedback_padrao(self, request, queryset):
        motivo_padrao = (
            'Reprovada pelo revisor humano sem motivo específico. '
            'Por favor, refaça a questão garantindo: (1) clareza no enunciado, '
            '(2) gabarito correto com base legal/teórica precisa, '
            '(3) alternativas distintas e não-triviais, (4) justificativa completa.'
        )
        atualizadas = 0
        for q in queryset:
            if not q.motivo_rejeicao:
                q.motivo_rejeicao = motivo_padrao
            q.revisada = False
            q.save(update_fields=['motivo_rejeicao', 'revisada'])
            atualizadas += 1
        self.message_user(
            request,
            f'{atualizadas} questão(ões) marcada(s) para correção pela IA. '
            f'Rode "python manage.py corrigir_rejeitadas" para processar.',
            messages.WARNING,
        )

    @admin.action(description='⛔ Rejeitar DEFINITIVAMENTE (não reprocessa)')
    def marcar_rejeitada_definitiva(self, request, queryset):
        n = queryset.update(rejeitada_definitiva=True, revisada=False)
        self.message_user(request, f'{n} questão(ões) marcada(s) como rejeitada definitiva.', messages.ERROR)

    @admin.action(description='🤖 Reprocessar agora pela IA (correção imediata)')
    def reprocessar_agora(self, request, queryset):
        from django.core.management import call_command
        ids = list(queryset.filter(motivo_rejeicao__gt='').values_list('id', flat=True))
        if not ids:
            self.message_user(request,
                              'Nenhuma questão selecionada tem motivo_rejeicao preenchido.',
                              messages.WARNING)
            return
        try:
            call_command('corrigir_rejeitadas', ids=','.join(map(str, ids)))
            self.message_user(request, f'{len(ids)} questão(ões) reprocessada(s) pela IA.', messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f'Erro ao reprocessar: {e}', messages.ERROR)


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('caminho_display', 'nivel_display', 'qtd_questoes_direto',
                    'qtd_questoes_subarvore', 'qtd_revisadas')
    search_fields = ('nome',)
    list_filter = ('parent',)
    autocomplete_fields = ('parent',)  # Combobox com busca em vez de dropdown gigante
    fields = ('nome', 'parent')

    def caminho_display(self, obj):
        """Mostra 'Ciencias > Biologia > Taxonomia' com indent visual."""
        prof = obj.profundidade
        indent = '&nbsp;' * (prof * 4)
        prefixo = '↳ ' if prof > 0 else ''
        return format_html('{}<strong>{}{}</strong>', indent, prefixo, obj.nome)
    caminho_display.short_description = 'Categoria'
    caminho_display.admin_order_field = 'nome'

    def nivel_display(self, obj):
        """Nivel na arvore (0=raiz, 1=filho direto, ...)."""
        prof = obj.profundidade
        emoji = ['🌳', '🌿', '🍃', '·'][min(prof, 3)]
        return format_html('{} nivel {}', emoji, prof)
    nivel_display.short_description = 'Nivel'

    def qtd_questoes_direto(self, obj):
        """Questoes diretamente nesta categoria (sem contar filhos)."""
        return obj.questao_set.count()
    qtd_questoes_direto.short_description = 'Diretas'

    def qtd_questoes_subarvore(self, obj):
        """Questoes desta categoria + todas as sub-categorias descendentes."""
        ids = obj.subarvore_ids()
        return Questao.objects.filter(categoria_id__in=ids).count()
    qtd_questoes_subarvore.short_description = 'Total (subarvore)'

    def qtd_revisadas(self, obj):
        """Questoes revisadas / total desta categoria (somente diretas)."""
        rev = obj.questao_set.filter(revisada=True).count()
        total = obj.questao_set.count()
        cor = '#16a34a' if total > 0 and rev == total else '#f59e0b' if rev else '#dc2626'
        return format_html('<span style="color:{};font-weight:bold;">{}/{}</span>', cor, rev, total)
    qtd_revisadas.short_description = 'Revisadas'

    def get_queryset(self, request):
        """Ordena por hierarquia (raiz primeiro, filhos abaixo do pai)."""
        return super().get_queryset(request).select_related('parent')


admin.site.register(RespostaUsuario)


# CupomDesconto, UsoCupom, PlanoUsuario, PagamentoMP:
# Admins removidos — app agora 100% gratuita.
# Models mantidos pra evitar migration destrutiva no BD prod.


@admin.register(LogSistema)
class LogSistemaAdmin(admin.ModelAdmin):
    list_display = ('criado_em', 'nivel', 'origem', 'preview_msg', 'usuario')
    list_filter = ('nivel', 'origem')
    search_fields = ('mensagem', 'detalhe', 'usuario__username')
    readonly_fields = ('criado_em', 'nivel', 'origem', 'mensagem', 'detalhe', 'usuario')
    date_hierarchy = 'criado_em'

    def preview_msg(self, obj):
        return obj.mensagem[:80] + ('…' if len(obj.mensagem) > 80 else '')
    preview_msg.short_description = 'Mensagem'


# ─── Admin do Sistema de Suporte ───────────────────────────────────────
from .models import TicketSuporte, RespostaTicket, QuestaoMarcada, ConcursoPreferido


class RespostaTicketInline(admin.TabularInline):
    model = RespostaTicket
    extra = 1
    fields = ('autor', 'mensagem', 'eh_staff', 'criado_em')
    readonly_fields = ('criado_em',)


@admin.register(TicketSuporte)
class TicketSuporteAdmin(admin.ModelAdmin):
    list_display = ('id', 'badge_status', 'badge_prioridade', 'assunto_short',
                    'usuario', 'categoria', 'criado_em')
    list_filter = ('status', 'prioridade', 'categoria')
    search_fields = ('assunto', 'mensagem', 'usuario__username', 'usuario__email')
    list_per_page = 30
    date_hierarchy = 'criado_em'
    readonly_fields = ('usuario', 'criado_em', 'atualizado_em', 'url_origem')
    inlines = [RespostaTicketInline]
    actions = ['marcar_respondido', 'marcar_fechado', 'definir_prioridade_alta']

    fieldsets = (
        ('Identificação', {
            'fields': ('usuario', 'categoria', 'assunto', 'mensagem'),
        }),
        ('Contato', {
            'fields': ('email_contato', 'url_origem'),
        }),
        ('Status', {
            'fields': ('status', 'prioridade', 'criado_em', 'atualizado_em', 'fechado_em'),
        }),
    )

    def assunto_short(self, obj):
        return obj.assunto[:60] + ('…' if len(obj.assunto) > 60 else '')
    assunto_short.short_description = 'Assunto'

    def badge_status(self, obj):
        cores = {
            'aberto':     ('#fef3c7', '#92400e'),
            'respondido': ('#dcfce7', '#166534'),
            'aguardando': ('#dbeafe', '#1e40af'),
            'fechado':    ('#f3f4f6', '#374151'),
        }
        bg, cor = cores.get(obj.status, ('#f3f4f6', '#374151'))
        return format_html('<span style="background:{};color:{};padding:2px 8px;border-radius:8px;font-weight:bold;font-size:11px;">{}</span>',
                           bg, cor, obj.get_status_display())
    badge_status.short_description = 'Status'

    def badge_prioridade(self, obj):
        cores = {
            'baixa':   '#94a3b8',
            'media':   '#0ea5e9',
            'alta':    '#f59e0b',
            'urgente': '#dc2626',
        }
        cor = cores.get(obj.prioridade, '#94a3b8')
        return format_html('<span style="color:{};font-weight:bold;font-size:11px;">●</span> {}',
                           cor, obj.get_prioridade_display())
    badge_prioridade.short_description = 'Prioridade'

    @admin.action(description='Marcar como Respondido')
    def marcar_respondido(self, request, queryset):
        n = queryset.update(status='respondido')
        self.message_user(request, f'{n} ticket(s) marcado(s) como respondido.', messages.SUCCESS)

    @admin.action(description='Fechar tickets')
    def marcar_fechado(self, request, queryset):
        from django.utils import timezone as _tz
        n = queryset.update(status='fechado', fechado_em=_tz.now())
        self.message_user(request, f'{n} ticket(s) fechado(s).', messages.SUCCESS)

    @admin.action(description='Definir prioridade Alta')
    def definir_prioridade_alta(self, request, queryset):
        n = queryset.update(prioridade='alta')
        self.message_user(request, f'{n} ticket(s) priorizado(s).', messages.WARNING)


@admin.register(RespostaTicket)
class RespostaTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'autor', 'eh_staff', 'criado_em')
    list_filter = ('eh_staff',)
    search_fields = ('mensagem', 'autor__username', 'ticket__assunto')
    readonly_fields = ('criado_em',)


@admin.register(QuestaoMarcada)
class QuestaoMarcadaAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'questao', 'motivo', 'criado_em')
    search_fields = ('usuario__username', 'motivo')
    list_filter = ('criado_em',)


@admin.register(ConcursoPreferido)
class ConcursoPreferidoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'concurso', 'data_prova_esperada', 'horas_por_dia', 'atualizado_em')
    list_filter = ('concurso',)
    search_fields = ('usuario__username',)


# ─── Materiais de apoio ──────────────────────────────────────────────────────

@admin.register(ResumoIA)
class ResumoIAAdmin(admin.ModelAdmin):
    list_display = ('categoria', 'preview_conteudo', 'gerado_em')
    search_fields = ('categoria__nome', 'conteudo')
    readonly_fields = ('gerado_em',)

    def preview_conteudo(self, obj):
        return (obj.conteudo[:80] + '...') if len(obj.conteudo) > 80 else obj.conteudo
    preview_conteudo.short_description = 'Prévia'


@admin.register(MapaMental)
class MapaMentalAdmin(admin.ModelAdmin):
    list_display = ('categoria', 'gerado_em')
    search_fields = ('categoria__nome',)
    readonly_fields = ('gerado_em',)


@admin.register(TimelineLei)
class TimelineLeiAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'ano_original', 'qtd_mudancas', 'gerado_em')
    search_fields = ('titulo', 'resumo')
    filter_horizontal = ('categorias',)
    prepopulated_fields = {'slug': ('titulo',)}
    readonly_fields = ('gerado_em',)
    fieldsets = (
        (None, {
            'fields': ('titulo', 'slug', 'ano_original', 'categorias'),
            'description': (
                'Preencha apenas <strong>título</strong> + <strong>ano_original</strong>. '
                'Deixe <em>resumo</em> e <em>mudanças_json</em> vazios — a IA popula '
                'automaticamente na primeira visita a <code>/timelines/&lt;slug&gt;/</code>. '
                'Para forçar regeneração, adicione <code>?regenerar=1</code> na URL.'
            ),
        }),
        ('Conteúdo (populado por IA)', {
            'fields': ('resumo', 'mudancas_json', 'gerado_em'),
            'classes': ('collapse',),
        }),
    )

    def qtd_mudancas(self, obj):
        return len(obj.mudancas_json or [])
    qtd_mudancas.short_description = 'Mudanças'


@admin.register(ComparativoBanca)
class ComparativoBancaAdmin(admin.ModelAdmin):
    list_display = ('categoria', 'banca', 'dificuldade', 'formato', 'gerado_em')
    list_filter = ('banca', 'dificuldade', 'categoria')
    search_fields = ('categoria__nome', 'banca', 'estilo', 'pegadinhas')
    readonly_fields = ('gerado_em',)


@admin.register(TermoGlossario)
class TermoGlossarioAdmin(admin.ModelAdmin):
    list_display = ('termo', 'preview_def', 'lista_categorias', 'gerado_em')
    list_filter = ('categorias',)
    search_fields = ('termo', 'definicao', 'exemplo_uso')
    filter_horizontal = ('categorias',)
    prepopulated_fields = {'slug': ('termo',)}
    readonly_fields = ('gerado_em',)

    def preview_def(self, obj):
        return (obj.definicao[:60] + '...') if len(obj.definicao) > 60 else obj.definicao
    preview_def.short_description = 'Definição'

    def lista_categorias(self, obj):
        cats = obj.categorias.all()[:3]
        return ', '.join(c.nome for c in cats) + ('...' if obj.categorias.count() > 3 else '')
    lista_categorias.short_description = 'Categorias'


# ─── Blog ───────────────────────────────────────────────────────────
from .models import PostBlog

@admin.register(PostBlog)
class PostBlogAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'publicado', 'publicado_em', 'autor', 'tags')
    list_filter = ('publicado', 'publicado_em', 'autor')
    search_fields = ('titulo', 'corpo', 'tags')
    prepopulated_fields = {'slug': ('titulo',)}
    date_hierarchy = 'publicado_em'
    actions = ['publicar_agora', 'despublicar']

    fieldsets = (
        ('Conteúdo', {'fields': ('titulo', 'slug', 'resumo', 'corpo', 'imagem_capa')}),
        ('Metadados', {'fields': ('autor', 'tags', 'concursos_relacionados')}),
        ('Publicação', {'fields': ('publicado', 'publicado_em')}),
    )

    @admin.action(description='Publicar agora')
    def publicar_agora(self, request, queryset):
        from django.utils import timezone
        n = queryset.update(publicado=True, publicado_em=timezone.now())
        self.message_user(request, f'{n} post(s) publicados.')

    @admin.action(description='Despublicar')
    def despublicar(self, request, queryset):
        n = queryset.update(publicado=False)
        self.message_user(request, f'{n} despublicado(s).')
