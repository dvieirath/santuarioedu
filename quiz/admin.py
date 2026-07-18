from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path, reverse
from django.utils.html import format_html
from .models import (Categoria, Questao, Alternativa, RespostaUsuario,
                     CupomDesconto, UsoCupom,
                     PlanoUsuario, LogSistema, PagamentoMP)


# ── Branding do Admin ──────────────────────────────────────────────────────
admin.site.site_header = 'SantuarioEdu · Painel Administrativo'
admin.site.site_title  = 'SantuarioEdu Admin'
admin.site.index_title = 'Bem-vindo ao painel'
admin.site.empty_value_display = '—'


class AlternativaInline(admin.TabularInline):
    model = Alternativa
    extra = 4


@admin.register(Questao)
class QuestaoAdmin(admin.ModelAdmin):
    inlines = [AlternativaInline]
    list_display = ('preview', 'categoria', 'tipo', 'banca', 'badge_status', 'tentativas_correcao')
    list_filter = ('revisada', 'gerada_por_ia', 'rejeitada_definitiva', 'categoria', 'tipo', 'banca')
    search_fields = ('texto', 'assunto', 'justificativa', 'motivo_rejeicao')
    list_per_page = 30
    actions = [
        'aprovar_revisao',
        'reprovar_com_feedback_padrao',
        'marcar_rejeitada_definitiva',
        'reprocessar_agora',
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
    list_display = ('nome', 'qtd_questoes', 'qtd_revisadas')
    search_fields = ('nome',)

    def qtd_questoes(self, obj):
        return obj.questao_set.count()
    qtd_questoes.short_description = 'Total'

    def qtd_revisadas(self, obj):
        rev = obj.questao_set.filter(revisada=True).count()
        total = obj.questao_set.count()
        cor = '#16a34a' if total > 0 and rev == total else '#f59e0b' if rev else '#dc2626'
        return format_html('<span style="color:{};font-weight:bold;">{}/{}</span>', cor, rev, total)
    qtd_revisadas.short_description = 'Revisadas'


admin.site.register(RespostaUsuario)


@admin.register(CupomDesconto)
class CupomDescontoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'plano_alvo', 'dias', 'usos_feitos', 'usos_max', 'ativo', 'badge_disponivel')
    list_filter = ('ativo', 'plano_alvo')
    search_fields = ('codigo',)
    readonly_fields = ('usos_feitos',)

    def badge_disponivel(self, obj):
        if obj.disponivel:
            return format_html('<span style="background:#dcfce7;color:#166534;padding:2px 8px;border-radius:8px;font-weight:bold;font-size:11px;">disponível</span>')
        return format_html('<span style="background:#fee2e2;color:#991b1b;padding:2px 8px;border-radius:8px;font-weight:bold;font-size:11px;">esgotado</span>')
    badge_disponivel.short_description = 'Status'


@admin.register(UsoCupom)
class UsoCupomAdmin(admin.ModelAdmin):
    list_display = ('cupom', 'usuario', 'aplicado_em', 'ip_origem')
    list_filter = ('cupom',)
    search_fields = ('cupom__codigo', 'usuario__username')
    readonly_fields = ('cupom', 'usuario', 'aplicado_em', 'ip_origem')


@admin.register(PlanoUsuario)
class PlanoUsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'plano', 'ativo', 'expira_em', 'atualizado_em')
    list_filter = ('plano', 'ativo')
    search_fields = ('usuario__username',)


@admin.register(PagamentoMP)
class PagamentoMPAdmin(admin.ModelAdmin):
    list_display = ('criado_em', 'usuario', 'plano_alvo', 'valor_reais', 'status', 'payment_id')
    list_filter = ('status', 'plano_alvo')
    search_fields = ('usuario__username', 'payment_id', 'preference_id')
    readonly_fields = ('preference_id', 'payment_id', 'payload_raw', 'criado_em', 'atualizado_em')
    date_hierarchy = 'criado_em'

    def valor_reais(self, obj):
        return f'R$ {obj.valor_centavos / 100:.2f}'
    valor_reais.short_description = 'Valor'


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
