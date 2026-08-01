from django.db import models
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError


def _validar_tamanho_imagem(f):
    """Limite: 5 MB por imagem (protege contra abuso e OOM em request)."""
    max_mb = 5
    if f and f.size > max_mb * 1024 * 1024:
        raise ValidationError(f'Imagem excede {max_mb} MB (upload de {f.size // 1024 // 1024} MB)')


def _validar_tamanho_arquivo(f):
    """Limite: 20 MB por arquivo de material de estudo."""
    max_mb = 20
    if f and f.size > max_mb * 1024 * 1024:
        raise ValidationError(f'Arquivo excede {max_mb} MB')


VALIDADORES_IMAGEM = [
    FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif', 'webp']),
    _validar_tamanho_imagem,
]

VALIDADORES_MATERIAL = [
    FileExtensionValidator(allowed_extensions=['pdf', 'doc', 'docx', 'txt', 'md']),
    _validar_tamanho_arquivo,
]


class Categoria(models.Model):
    """Categoria hierarquica de conteudo. Ex: Ciencias > Biologia > Taxonomia.

    O campo parent auto-referencial permite arvore de profundidade arbitraria.
    Questao.categoria pode apontar pra qualquer nivel (folha ou intermediario).
    """
    nome = models.CharField(max_length=100)
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='filhos',
        help_text='Categoria pai. Deixe vazio pra raiz (ex: Ciencias, Direito).',
    )

    class Meta:
        ordering = ['nome']
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        # Nome unico dentro do mesmo pai — permite "Taxonomia" em Biologia E em Geologia
        constraints = [
            models.UniqueConstraint(
                fields=['parent', 'nome'],
                name='unique_categoria_por_parent',
            ),
        ]

    def __str__(self):
        return self.caminho

    @property
    def caminho(self) -> str:
        """Ex: 'Ciencias > Biologia > Taxonomia'. Percorre ate a raiz."""
        partes = [self.nome]
        no = self.parent
        # Guard contra ciclo — max 10 niveis
        for _ in range(10):
            if not no:
                break
            partes.append(no.nome)
            no = no.parent
        return ' > '.join(reversed(partes))

    @property
    def profundidade(self) -> int:
        """0 pra raiz, 1 pra filho direto, etc."""
        n = 0
        no = self.parent
        for _ in range(10):
            if not no:
                break
            n += 1
            no = no.parent
        return n

    @property
    def raiz(self) -> 'Categoria':
        """Retorna a categoria raiz desta arvore (ela mesma se ja for raiz)."""
        no = self
        for _ in range(10):
            if not no.parent:
                return no
            no = no.parent
        return no

    def descendentes_ids(self) -> list:
        """IDs de todas as sub-categorias recursivamente (nao inclui self).
        Usado pra filtrar questoes de toda uma subarvore."""
        ids = []
        pilha = list(self.filhos.all())
        while pilha:
            cat = pilha.pop()
            ids.append(cat.id)
            pilha.extend(list(cat.filhos.all()))
        return ids

    def subarvore_ids(self) -> list:
        """IDs de self + todos descendentes. Usado pra queries tipo
        Questao.objects.filter(categoria_id__in=raiz.subarvore_ids())."""
        return [self.id] + self.descendentes_ids()

class Questao(models.Model):
    TIPO_CHOICES = [
        ('ME', 'Múltipla Escolha'),
        ('CE', 'Certo ou Errado'),
    ]
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE)
    texto = models.TextField()
    imagem = models.ImageField(upload_to='questoes/', blank=True, null=True,
                                validators=VALIDADORES_IMAGEM)
    tipo = models.CharField(max_length=2, choices=TIPO_CHOICES, default='ME')
    justificativa = models.TextField(blank=True, null=True)
    assunto = models.CharField(max_length=255, blank=True, null=True)
    revisada = models.BooleanField(default=False)
    banca = models.CharField(max_length=60, blank=True, null=True)
    ano = models.PositiveSmallIntegerField(blank=True, null=True)
    gerada_por_ia = models.BooleanField(default=False)  # Sprint 23

    # ── Ciclo de revisão humana ──
    motivo_rejeicao = models.TextField(blank=True, default='',
        help_text='Quando preenchido, a questão entra na fila de re-geração pela IA.')
    tentativas_correcao = models.PositiveSmallIntegerField(default=0,
        help_text='Quantas vezes a IA já tentou corrigir esta questão.')
    rejeitada_definitiva = models.BooleanField(default=False,
        help_text='Esgotou tentativas de correção — não será mais reprocessada.')

    @property
    def status_revisao(self):
        """Retorna: aprovada | em_correcao | pendente | rejeitada"""
        if self.revisada:
            return 'aprovada'
        if self.rejeitada_definitiva:
            return 'rejeitada'
        if self.motivo_rejeicao:
            return 'em_correcao'
        return 'pendente'

    def __str__(self):
        return self.texto

class Alternativa(models.Model):
    questao = models.ForeignKey(Questao, on_delete=models.CASCADE)
    texto = models.TextField()
    correta = models.BooleanField(default=False)

    def __str__(self):
        return self.texto

class RespostaUsuario(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    questao = models.ForeignKey(Questao, on_delete=models.CASCADE)
    acertou = models.BooleanField()
    data = models.DateTimeField(auto_now_add=True)

class MaterialEstudo(models.Model):
    titulo = models.CharField(max_length=200)
    descricao = models.TextField(blank=True, null=True)
    arquivo = models.FileField(upload_to='materiais/', validators=VALIDADORES_MATERIAL)
    data_upload = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.titulo
class Perfil(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE)
    foto = models.ImageField(upload_to='perfil/', blank=True, null=True,
                              validators=VALIDADORES_IMAGEM)
    bio = models.TextField(blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)

    # ── Conformidade legal (LGPD + CDC) ──────────────────────────────────
    aceite_termos = models.BooleanField(default=False,
        help_text='Usuário leu e aceitou explicitamente os Termos de Uso?')
    aceite_termos_em = models.DateTimeField(null=True, blank=True)
    aceite_termos_ip = models.GenericIPAddressField(null=True, blank=True,
        help_text='IP no momento do aceite — evidência judicial.')

    aceita_marketing = models.BooleanField(default=False,
        help_text='Opt-in para receber e-mails de marketing/dicas (LGPD).')
    aceita_marketing_em = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Perfil de {self.usuario.username}'


class Simulado(models.Model):
    DURACAO_SEGUNDOS = 5 * 3600  # fallback quando duracao_segundos nao populado
    TOTAL_QUESTOES = 50

    MODO_NORMAL     = 'normal'
    MODO_PROVA_REAL = 'prova_real'
    MODO_CHOICES = [
        ('normal',     'Normal'),
        ('prova_real', 'Prova Real'),
    ]

    usuario     = models.ForeignKey(User, on_delete=models.CASCADE)
    iniciado_em = models.DateTimeField(auto_now_add=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    finalizado  = models.BooleanField(default=False)
    modo        = models.CharField(max_length=20, choices=MODO_CHOICES,
                                   default='normal')  # Sprint 24
    # Duracao configuravel por simulado (antes: hardcoded 5h ignorando request.session).
    # Null = usa fallback DURACAO_SEGUNDOS (5h) — pra retrocompatibilidade com
    # simulados criados antes da migration 0043.
    duracao_segundos = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Duracao em segundos. Se null, usa Simulado.DURACAO_SEGUNDOS (5h).',
    )

    def segundos_restantes(self):
        from django.utils import timezone
        if self.finalizado:
            return 0
        duracao = self.duracao_segundos or self.DURACAO_SEGUNDOS
        decorrido = (timezone.now() - self.iniciado_em).total_seconds()
        return max(0, duracao - int(decorrido))

    def __str__(self):
        return f'Simulado de {self.usuario.username} em {self.iniciado_em:%d/%m/%Y %H:%M}'


class RespostaSimulado(models.Model):
    simulado = models.ForeignKey(Simulado, on_delete=models.CASCADE, related_name='respostas')
    questao = models.ForeignKey(Questao, on_delete=models.CASCADE)
    alternativa_escolhida = models.ForeignKey(
        'Alternativa', null=True, blank=True, on_delete=models.SET_NULL
    )
    acertou = models.BooleanField(null=True, blank=True)
    ordem = models.PositiveIntegerField()

    class Meta:
        ordering = ['ordem']
        unique_together = ['simulado', 'questao']


class QuestaoFavorita(models.Model):
    usuario  = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favoritas')
    questao  = models.ForeignKey(Questao, on_delete=models.CASCADE, related_name='favoritada_por')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['usuario', 'questao']
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.usuario.username} ♥ Q#{self.questao.id}'


class Conquista(models.Model):
    CODIGOS = [
        ('primeiro_acerto', '🥇 Primeiro Acerto'),
        ('streak_7',        '🔥 Semana em Chamas'),
        ('streak_30',       '🌟 Mês Dedicado'),
        ('centenario',      '💯 Centenário'),
        ('quinhentos',      '🚀 500 Questões'),
        ('atirador',        '🎯 Atirador de Elite'),
        ('enciclopedia',    '📚 Enciclopédia'),
        ('simuladista',     '🏅 Simuladista'),
    ]
    usuario        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conquistas')
    codigo         = models.CharField(max_length=50, choices=CODIGOS)
    desbloqueado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['usuario', 'codigo']
        ordering = ['-desbloqueado_em']

    def __str__(self):
        return f'{self.usuario.username} — {self.get_codigo_display()}'


class AnotacaoUsuario(models.Model):
    usuario     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='anotacoes')
    questao     = models.ForeignKey(Questao, on_delete=models.CASCADE, related_name='anotacoes')
    texto       = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['usuario', 'questao']

    def __str__(self):
        return f'Nota de {self.usuario.username} em Q#{self.questao.id}'


class MetaEstudo(models.Model):
    usuario          = models.OneToOneField(User, on_delete=models.CASCADE, related_name='meta')
    questoes_por_dia = models.PositiveIntegerField(default=20)
    streak_atual     = models.PositiveIntegerField(default=0)
    streak_maximo    = models.PositiveIntegerField(default=0)
    ultimo_estudo    = models.DateField(null=True, blank=True)
    total_dias       = models.PositiveIntegerField(default=0)

    def atualizar_streak(self):
        from django.utils import timezone
        hoje = timezone.localdate()
        if self.ultimo_estudo is None:
            self.streak_atual = 1
            self.total_dias   = 1
        elif self.ultimo_estudo == hoje:
            return  # já foi computado hoje
        elif (hoje - self.ultimo_estudo).days == 1:
            self.streak_atual += 1
            self.total_dias   += 1
        else:
            self.streak_atual = 1
            self.total_dias  += 1
        self.streak_maximo = max(self.streak_maximo, self.streak_atual)
        self.ultimo_estudo = hoje
        self.save(update_fields=['streak_atual', 'streak_maximo', 'ultimo_estudo', 'total_dias'])

    def __str__(self):
        return f'Meta de {self.usuario.username}'


class RevisaoEspacada(models.Model):
    """Algoritmo SM-2 simplificado para revisão espaçada de questões."""
    usuario          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='revisoes')
    questao          = models.ForeignKey(Questao, on_delete=models.CASCADE, related_name='revisoes')
    proxima_revisao  = models.DateField()
    intervalo_dias   = models.PositiveIntegerField(default=1)
    fator_facilidade = models.FloatField(default=2.5)   # SM-2 EF, 1.3 – 2.5
    repeticoes       = models.PositiveIntegerField(default=0)
    ultima_resposta  = models.BooleanField(null=True, blank=True)  # True=acertou

    class Meta:
        unique_together = ['usuario', 'questao']
        ordering = ['proxima_revisao']

    def atualizar(self, acertou: bool):
        """Atualiza intervalo conforme SM-2. Chame após o usuário responder."""
        from django.utils import timezone
        hoje = timezone.localdate()
        self.ultima_resposta = acertou
        if acertou:
            self.repeticoes += 1
            if self.repeticoes == 1:
                self.intervalo_dias = 1
            elif self.repeticoes == 2:
                self.intervalo_dias = 6
            else:
                self.intervalo_dias = round(self.intervalo_dias * self.fator_facilidade)
            # Ajusta fator de facilidade (q=4 para resposta correta)
            q = 4
            self.fator_facilidade = max(1.3, self.fator_facilidade + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        else:
            # Errou: reinicia sequência
            self.repeticoes = 0
            self.intervalo_dias = 1
            q = 2
            self.fator_facilidade = max(1.3, self.fator_facilidade + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        self.proxima_revisao = hoje + __import__('datetime').timedelta(days=self.intervalo_dias)
        self.save()

    def __str__(self):
        return f'SRS {self.usuario.username} Q#{self.questao_id} → {self.proxima_revisao}'


class SessaoEstudo(models.Model):
    """Registra tempo de cada sessão de estudo do usuário."""
    usuario       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessoes')
    iniciada_em   = models.DateTimeField(auto_now_add=True)
    duracao_seg   = models.PositiveIntegerField(default=0)   # preenchido no encerramento
    questoes_resp = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-iniciada_em']

    def __str__(self):
        return f'Sessão {self.usuario.username} {self.iniciada_em:%d/%m/%Y %H:%M}'


class PushSubscription(models.Model):
    """Armazena subscription de Web Push por usuário/dispositivo."""
    usuario    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subs')
    endpoint   = models.TextField(unique=True)
    p256dh     = models.TextField()
    auth       = models.TextField()
    criada_em  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criada_em']

    def __str__(self):
        return f'Push {self.usuario.username} @ {self.endpoint[:40]}…'


# ─── SPRINT 11B — FLASHCARDS ─────────────────────────────────────────────────

class Flashcard(models.Model):
    """Cartão de memorização com frente (pergunta) e verso (resposta)."""
    usuario    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flashcards')
    categoria  = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='flashcards')
    frente     = models.TextField(help_text='Pergunta ou conceito')
    verso      = models.TextField(help_text='Resposta ou explicação')
    criado_em  = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    # Dificuldade percebida pelo usuário após revisar: 1=fácil, 2=médio, 3=difícil
    dificuldade = models.PositiveSmallIntegerField(default=2)
    vezes_visto = models.PositiveIntegerField(default=0)
    proxima_revisao = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['proxima_revisao', '-criado_em']

    def __str__(self):
        return f'Flash #{self.id} — {self.frente[:60]}'

    def registrar_revisao(self, dificuldade: int):
        """Atualiza dificuldade e agenda próxima revisão (intervalo simples)."""
        from django.utils import timezone
        import datetime
        self.dificuldade = dificuldade
        self.vezes_visto += 1
        dias = {1: 7, 2: 3, 3: 1}.get(dificuldade, 3)
        self.proxima_revisao = timezone.localdate() + datetime.timedelta(days=dias)
        self.save(update_fields=['dificuldade', 'vezes_visto', 'proxima_revisao', 'atualizado_em'])


# ─── SPRINT 11E — MODO DESAFIO ───────────────────────────────────────────────

class DesafioResultado(models.Model):
    """Registra resultado de cada partida do Modo Desafio."""
    usuario    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='desafios')
    pontos     = models.PositiveIntegerField(default=0)
    total      = models.PositiveIntegerField(default=10)
    acertos    = models.PositiveIntegerField(default=0)
    tempo_medio_seg = models.FloatField(default=0)   # tempo médio por questão
    realizado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-pontos', '-realizado_em']

    def __str__(self):
        return f'{self.usuario.username} — {self.pontos}pts ({self.realizado_em:%d/%m/%Y})'


# ─── SPRINT 12A — RESUMOS POR IA ─────────────────────────────────────────────

class ResumoIA(models.Model):
    """Resumo de disciplina gerado pelo Gemini e cacheado no banco."""
    categoria   = models.OneToOneField(Categoria, on_delete=models.CASCADE,
                                       related_name='resumo_ia')
    conteudo    = models.TextField()
    gerado_em   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Resumo IA — {self.categoria.nome}'


class MapaMental(models.Model):
    """Mapa mental (Mermaid mindmap syntax) por categoria, gerado pela IA."""
    categoria   = models.OneToOneField(Categoria, on_delete=models.CASCADE,
                                       related_name='mapa_mental')
    mermaid     = models.TextField(help_text='Codigo mermaid mindmap (root -> ramos)')
    gerado_em   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Mapa mental — {self.categoria.nome}'


class TimelineLei(models.Model):
    """Timeline de alteracoes historicas de uma lei relevante para concursos.
    Ex: CTB (Lei 9.503/97), Lei de Drogas, CF/88.  Nao especifico a PRF."""
    titulo         = models.CharField(max_length=200,
        help_text='Ex: "CTB — Lei 9.503/1997"')
    slug           = models.SlugField(max_length=140, unique=True, blank=True)
    ano_original   = models.PositiveSmallIntegerField()
    resumo         = models.TextField(blank=True, default='',
        help_text='Deixe vazio no cadastro — IA popula no primeiro acesso')
    # Lista JSON: [{ano, lei_alteradora, descricao, artigos_afetados}]
    mudancas_json  = models.JSONField(default=list, blank=True)
    categorias     = models.ManyToManyField(Categoria, blank=True,
                                            related_name='timelines')
    gerado_em      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['titulo']
        verbose_name = 'Timeline de Lei'
        verbose_name_plural = 'Timelines de Leis'

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.titulo)[:140]
        super().save(*args, **kwargs)


class ComparativoBanca(models.Model):
    """Como uma banca especifica aborda um tema.  Uma linha por (categoria, banca)."""
    categoria      = models.ForeignKey(Categoria, on_delete=models.CASCADE,
                                       related_name='comparativos')
    banca          = models.CharField(max_length=60)
    estilo         = models.TextField(
        help_text='Como essa banca costuma abordar este tema')
    dificuldade    = models.CharField(max_length=20, blank=True,
        help_text='baixa | media | alta')
    pegadinhas     = models.TextField(blank=True,
        help_text='Pegadinhas tipicas usadas por esta banca no tema')
    formato        = models.CharField(max_length=60, blank=True,
        help_text='Ex: "CE dominante", "ME 5-alt com texto de apoio"')
    gerado_em      = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('categoria', 'banca')]
        ordering = ['categoria__nome', 'banca']
        verbose_name = 'Comparativo por Banca'
        verbose_name_plural = 'Comparativos por Banca'

    def __str__(self):
        return f'{self.categoria.nome} · {self.banca}'


class TermoGlossario(models.Model):
    """Termo tecnico com definicao curta para consulta rapida.
    Usado tanto em pagina propria quanto em tooltips nas questoes."""
    termo          = models.CharField(max_length=120, unique=True)
    slug           = models.SlugField(max_length=140, unique=True, blank=True)
    definicao      = models.TextField(help_text='Definicao curta e clara')
    exemplo_uso    = models.TextField(blank=True,
        help_text='Como o termo aparece em contexto de prova')
    categorias     = models.ManyToManyField(Categoria, blank=True,
                                            related_name='termos_glossario',
                                            help_text='Disciplinas onde o termo se aplica')
    gerado_em      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['termo']
        verbose_name = 'Termo do Glossario'
        verbose_name_plural = 'Termos do Glossario'

    def __str__(self):
        return self.termo

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.termo)[:140]
        super().save(*args, **kwargs)


# ─── SPRINT 12B — GRUPOS DE ESTUDO ───────────────────────────────────────────

import secrets as _secrets

class GrupoEstudo(models.Model):
    nome        = models.CharField(max_length=100)
    descricao   = models.TextField(blank=True)
    criador     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='grupos_criados')
    codigo      = models.CharField(max_length=8, unique=True, default='')
    criado_em   = models.DateTimeField(auto_now_add=True)
    publico     = models.BooleanField(default=False)

    class Meta:
        ordering = ['-criado_em']

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = _secrets.token_urlsafe(5)[:8].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Grupo "{self.nome}" [{self.codigo}]'


class MembroGrupo(models.Model):
    PAPEL_CHOICES = [('admin', 'Admin'), ('membro', 'Membro')]
    grupo   = models.ForeignKey(GrupoEstudo, on_delete=models.CASCADE, related_name='membros')
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='grupos')
    papel   = models.CharField(max_length=10, choices=PAPEL_CHOICES, default='membro')
    entrou_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['grupo', 'usuario']
        ordering = ['entrou_em']

    def __str__(self):
        return f'{self.usuario.username} em {self.grupo.nome}'


# ─── SPRINT 12C — NOTIFICAÇÕES IN-APP ────────────────────────────────────────

class Notificacao(models.Model):
    TIPOS = [
        ('conquista',   '🏆 Conquista'),
        ('streak',      '🔥 Streak'),
        ('srs',         '🧠 Revisão SRS'),
        ('grupo',       '👥 Grupo'),
        ('sistema',     '📢 Sistema'),
    ]
    usuario    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notificacoes')
    tipo       = models.CharField(max_length=20, choices=TIPOS, default='sistema')
    titulo     = models.CharField(max_length=120)
    mensagem   = models.TextField(blank=True)
    lida       = models.BooleanField(default=False)
    link       = models.CharField(max_length=200, blank=True)
    criada_em  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criada_em']

    def __str__(self):
        return f'[{self.tipo}] {self.titulo} → {self.usuario.username}'

    @classmethod
    def criar(cls, usuario, tipo, titulo, mensagem='', link=''):
        return cls.objects.create(
            usuario=usuario, tipo=tipo,
            titulo=titulo, mensagem=mensagem, link=link
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINT 13
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 13B — METAS AVANÇADAS ────────────────────────────────────────────────────

class MetaAvancada(models.Model):
    """Metas semanais e mensais configuráveis pelo usuário."""
    PERIODO_CHOICES = [('semanal', 'Semanal'), ('mensal', 'Mensal')]

    usuario          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='metas_avancadas')
    periodo          = models.CharField(max_length=10, choices=PERIODO_CHOICES, default='semanal')
    questoes_alvo    = models.PositiveIntegerField(default=50)
    aproveitamento_alvo = models.PositiveSmallIntegerField(default=70)  # %
    inicio           = models.DateField()
    fim              = models.DateField()
    ativa            = models.BooleanField(default=True)

    class Meta:
        ordering = ['-inicio']

    def __str__(self):
        return f'{self.usuario.username} — meta {self.periodo} {self.inicio}'

    def calcular_progresso(self):
        """Retorna dict com questoes_feitas, pct_questoes, acertos, pct_aproveitamento."""
        from quiz.models import RespostaUsuario
        r = RespostaUsuario.objects.filter(
            usuario=self.usuario,
            data__date__gte=self.inicio,
            data__date__lte=self.fim,
        )
        total   = r.count()
        acertos = r.filter(acertou=True).count()
        pct_q   = min(100, round(total / self.questoes_alvo * 100)) if self.questoes_alvo else 0
        pct_a   = round(acertos / total * 100) if total else 0
        return {
            'total': total,
            'acertos': acertos,
            'pct_questoes': pct_q,
            'pct_aproveitamento': pct_a,
            'meta_atingida': total >= self.questoes_alvo and pct_a >= self.aproveitamento_alvo,
        }


# ─── 13C — COMENTÁRIOS EM QUESTÕES ───────────────────────────────────────────

class ComentarioQuestao(models.Model):
    usuario    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comentarios')
    questao    = models.ForeignKey(Questao, on_delete=models.CASCADE, related_name='comentarios')
    texto      = models.TextField()
    criado_em  = models.DateTimeField(auto_now_add=True)
    upvotes    = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-upvotes', '-criado_em']

    def __str__(self):
        return f'Comentário de {self.usuario.username} em Q#{self.questao_id}'


class UpvoteComentario(models.Model):
    usuario    = models.ForeignKey(User, on_delete=models.CASCADE)
    comentario = models.ForeignKey(ComentarioQuestao, on_delete=models.CASCADE, related_name='votos')
    criado_em  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['usuario', 'comentario']


# ═══════════════════════════════════════════════════════════════════════════════
# SPRINT 15
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 15A — QUESTÃO DO DIA ─────────────────────────────────────────────────────

class QuestaoDodia(models.Model):
    """Registra a conclusão do desafio diário (1 questão extremamente difícil)."""
    usuario    = models.ForeignKey(User, on_delete=models.CASCADE, related_name='questoes_do_dia')
    data       = models.DateField()
    concluido  = models.BooleanField(default=False)
    acertos    = models.PositiveSmallIntegerField(default=0)
    total      = models.PositiveSmallIntegerField(default=1)
    pontuacao  = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ['usuario', 'data']
        ordering = ['-data']

    def __str__(self):
        return f'{self.usuario.username} — dia {self.data} — {self.acertos}/{self.total}'


# ─── 15D — DIFICULDADE PERCEBIDA ─────────────────────────────────────────────

class AvaliacaoQuestao(models.Model):
    """Avaliação de dificuldade percebida pelo usuário após responder a questão."""
    DIFICULDADE_CHOICES = [
        (1, 'Fácil'),
        (2, 'Médio'),
        (3, 'Difícil'),
    ]
    usuario      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='avaliacoes')
    questao      = models.ForeignKey(Questao, on_delete=models.CASCADE, related_name='avaliacoes')
    dificuldade  = models.PositiveSmallIntegerField(choices=DIFICULDADE_CHOICES)
    avaliado_em  = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['usuario', 'questao']
        ordering = ['-avaliado_em']

    def __str__(self):
        return f'{self.usuario.username} → Q#{self.questao_id}: {self.get_dificuldade_display()}'


# ─── SPRINT 16 — XP & NÍVEIS ─────────────────────────────────────────────────

class NivelUsuario(models.Model):
    """Progresso de XP e nível (rank) do usuário."""

    RANKS = [
        (1,  'Cadete'),
        (2,  'Aspirante'),
        (3,  'Inspetor'),
        (4,  'Delegado'),
        (5,  'Superintendente'),
        (6,  'Diretor PRF'),
    ]

    # XP necessário para cada nível (acumulado)
    XP_POR_NIVEL = [0, 0, 200, 500, 1000, 2000, 4000]

    usuario      = models.OneToOneField(User, on_delete=models.CASCADE, related_name='nivel')
    xp_total     = models.PositiveIntegerField(default=0)
    nivel        = models.PositiveSmallIntegerField(default=1)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Nível de Usuário'

    def __str__(self):
        return f'{self.usuario.username} — Nível {self.nivel} ({self.xp_total} XP)'

    @property
    def rank_nome(self):
        for num, nome in reversed(self.RANKS):
            if self.nivel >= num:
                return nome
        return 'Cadete'

    @property
    def xp_nivel_atual(self):
        """XP acumulado necessário para o nível atual."""
        return self.XP_POR_NIVEL[min(self.nivel, len(self.XP_POR_NIVEL) - 1)]

    @property
    def xp_proximo_nivel(self):
        """XP acumulado necessário para o próximo nível."""
        proximo = self.nivel + 1
        if proximo >= len(self.XP_POR_NIVEL):
            return None  # já no máximo
        return self.XP_POR_NIVEL[proximo]

    @property
    def xp_progresso(self):
        """XP relativo dentro do nível atual (0 → xp_proximo - xp_atual)."""
        proximo = self.xp_proximo_nivel
        if proximo is None:
            return self.xp_total
        return self.xp_total - self.xp_nivel_atual

    @property
    def xp_necessario(self):
        """Quantos XP faltam para subir de nível."""
        proximo = self.xp_proximo_nivel
        if proximo is None:
            return 0
        return proximo - self.xp_total

    @property
    def pct_nivel(self):
        """Porcentagem de progresso no nível atual (0–100)."""
        proximo = self.xp_proximo_nivel
        if proximo is None:
            return 100
        faixa = proximo - self.xp_nivel_atual
        if faixa <= 0:
            return 100
        return min(100, int(self.xp_progresso / faixa * 100))

    def adicionar_xp(self, quantidade):
        """Adiciona XP e verifica se subiu de nível. Retorna True se subiu."""
        self.xp_total += quantidade
        subiu = False
        while self.nivel < len(self.XP_POR_NIVEL) - 1:
            proximo_xp = self.XP_POR_NIVEL[self.nivel + 1]
            if self.xp_total >= proximo_xp:
                self.nivel += 1
                subiu = True
            else:
                break
        self.save()
        return subiu


# ─── SPRINT 18 — PLANO DE ESTUDOS DINÂMICO ───────────────────────────────────

class PlanoEstudoDinamico(models.Model):
    """
    Plano de estudos que se recalcula automaticamente com base no desempenho.
    A distribuição de horas por disciplina é ponderada pelo aproveitamento:
    pontos fracos recebem mais tempo, pontos fortes são mantidos.
    """
    usuario          = models.OneToOneField(User, on_delete=models.CASCADE,
                                            related_name='plano_dinamico')
    concurso_alvo    = models.CharField(max_length=120, default='PRF')
    data_prova       = models.DateField(null=True, blank=True)
    horas_por_dia    = models.PositiveSmallIntegerField(default=2)   # horas/dia disponíveis
    dias_por_semana  = models.PositiveSmallIntegerField(default=5)   # dias/semana de estudo
    # JSON: {str(cat_id): {nome, pct, horas_semana, status}}
    distribuicao     = models.JSONField(default=dict)
    distribuicao_ant = models.JSONField(default=dict)   # semana anterior (para diff)
    data_recalculo   = models.DateTimeField(null=True, blank=True)
    criado_em        = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Plano de Estudos Dinâmico'

    def __str__(self):
        return f'Plano de {self.usuario.username} — {self.concurso_alvo}'

    @property
    def horas_semana_total(self):
        return self.horas_por_dia * self.dias_por_semana

    @property
    def semanas_restantes(self):
        if not self.data_prova:
            return None
        from django.utils import timezone
        delta = (self.data_prova - timezone.localdate()).days
        return max(0, delta // 7)

    @property
    def recalculado_hoje(self):
        if not self.data_recalculo:
            return False
        from django.utils import timezone
        return self.data_recalculo.date() == timezone.localdate()


# ─── SPRINT 19 — NOTIFICAÇÕES ────────────────────────────────────────────────


class PreferenciasNotificacao(models.Model):
    """Preferências de notificação por usuário."""
    usuario          = models.OneToOneField(User, on_delete=models.CASCADE,
                                            related_name='pref_notif')
    lembrete_diario  = models.BooleanField(default=True)
    hora_lembrete    = models.TimeField(default='20:00')
    streak_em_risco  = models.BooleanField(default=True)
    novidades        = models.BooleanField(default=True)
    # Horário de pico aprendido automaticamente (hora que o usuário mais acessa)
    hora_pico        = models.PositiveSmallIntegerField(null=True, blank=True)  # 0-23
    atualizado_em    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Preferências de Notificação'

    def __str__(self):
        return f'Preferências de {self.usuario.username}'


# ─── SPRINT 20 — TUTOR IA PERSONALIZADO ──────────────────────────────────────

class ExplicacaoIA(models.Model):
    """
    Armazena explicações geradas pelo Tutor IA para questões erradas.
    Inclui feedback de utilidade para melhoria contínua dos prompts.
    """
    usuario         = models.ForeignKey(User, on_delete=models.CASCADE,
                                        related_name='explicacoes_ia')
    questao         = models.ForeignKey(Questao, on_delete=models.CASCADE,
                                        related_name='explicacoes_ia')
    alt_escolhida   = models.ForeignKey('Alternativa', null=True, blank=True,
                                        on_delete=models.SET_NULL,
                                        related_name='explicacoes_escolhida')
    texto           = models.TextField()
    util            = models.BooleanField(null=True, blank=True)  # True=👍 False=👎
    rank_no_momento = models.CharField(max_length=40, default='Cadete')
    criado_em       = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering  = ['-criado_em']
        # Uma explicação por (usuário × questão × alternativa_escolhida) por dia
        # — não unique_together para permitir nova tentativa no dia seguinte

    def __str__(self):
        return f'Explicação IA — {self.usuario.username} / Q#{self.questao_id}'


# ── Sprint 22 — Simulado Preditivo ───────────────────────────────────────────

class RelatorioSimuladoIA(models.Model):
    """Análise IA gerada após a conclusão de um simulado.
    Inclui nota predita, pontos fortes/fracos e recomendações táticas."""
    simulado     = models.OneToOneField(
        Simulado,
        on_delete=models.CASCADE,
        related_name='relatorio_ia',
    )
    texto        = models.TextField()
    nota_predita = models.FloatField(null=True, blank=True)   # 0-100
    criado_em    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f'Relatório IA — Simulado #{self.simulado_id}'

    @property
    def nota_predita_str(self):
        if self.nota_predita is None:
            return '—'
        return f'{self.nota_predita:.0f}%'


# ── Sprint 23 — Predição de Tópicos ──────────────────────────────────────────

class PrevisaoTopico(models.Model):
    """Cache de predição de tópicos prováveis para o próximo concurso PRF.
    Recalculado sob demanda (máx. 1x/dia por usuário)."""
    usuario       = models.ForeignKey(User, on_delete=models.CASCADE,
                                      related_name='previsoes_topico')
    categoria     = models.ForeignKey(Categoria, on_delete=models.CASCADE,
                                      related_name='previsoes')
    probabilidade = models.FloatField(default=0.0)   # 0-100
    justificativa = models.TextField(blank=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering            = ['-probabilidade']
        unique_together     = [('usuario', 'categoria')]

    def __str__(self):
        return f'{self.usuario.username} / {self.categoria.nome} — {self.probabilidade:.0f}%'


# ── Sprint 25 — Duelo em Tempo Real ──────────────────────────────────────────

import random, string

def _gerar_codigo():
    """Gera um código de sala de 6 caracteres alfanuméricos."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


class Duelo(models.Model):
    """
    Representa uma partida 1v1 entre dois usuários.
    Fluxo: criador cria a sala → adversário entra pelo código →
    ambos respondem as mesmas questões → resultado final.
    """
    STATUS = [
        ('aguardando', 'Aguardando oponente'),
        ('em_andamento', 'Em andamento'),
        ('finalizado', 'Finalizado'),
        ('cancelado', 'Cancelado'),
    ]

    codigo        = models.CharField(max_length=10, unique=True, default=_gerar_codigo)
    criador       = models.ForeignKey(User, on_delete=models.CASCADE,
                                      related_name='duelos_criados')
    adversario    = models.ForeignKey(User, null=True, blank=True,
                                      on_delete=models.SET_NULL,
                                      related_name='duelos_aceitos')
    categoria     = models.ForeignKey('Categoria', null=True, blank=True,
                                      on_delete=models.SET_NULL,
                                      related_name='duelos')
    questoes      = models.ManyToManyField('Questao', blank=True,
                                           related_name='duelos')
    n_questoes    = models.PositiveSmallIntegerField(default=10)
    tempo_por_q   = models.PositiveSmallIntegerField(default=30,
                                                     help_text='Segundos por questão')
    status        = models.CharField(max_length=20, choices=STATUS,
                                     default='aguardando')
    questao_atual = models.PositiveSmallIntegerField(default=0,
                                                     help_text='Índice 0-based')
    iniciado_em   = models.DateTimeField(null=True, blank=True)
    encerrado_em  = models.DateTimeField(null=True, blank=True)
    criado_em     = models.DateTimeField(auto_now_add=True)

    # Placar final (preenchido ao encerrar)
    pontos_criador    = models.PositiveSmallIntegerField(default=0)
    pontos_adversario = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f'Duelo #{self.codigo} — {self.criador} vs {self.adversario or "?"}'

    @property
    def questoes_lista(self):
        """Retorna queryset ordenado por pk para consistência."""
        return self.questoes.order_by('pk')


class RespostaDuelo(models.Model):
    """Registro da resposta de um participante a uma questão do duelo."""
    duelo         = models.ForeignKey(Duelo, on_delete=models.CASCADE,
                                      related_name='respostas')
    usuario       = models.ForeignKey(User, on_delete=models.CASCADE,
                                      related_name='respostas_duelo')
    questao       = models.ForeignKey('Questao', on_delete=models.CASCADE,
                                      related_name='respostas_duelo')
    alternativa   = models.ForeignKey('Alternativa', null=True, blank=True,
                                      on_delete=models.SET_NULL)
    acertou       = models.BooleanField(default=False)
    tempo_ms      = models.PositiveIntegerField(default=0,
                                                help_text='Tempo de resposta em ms')
    respondido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering            = ['respondido_em']
        unique_together     = [('duelo', 'usuario', 'questao')]

    def __str__(self):
        return f'Resp {self.usuario.username} — Q#{self.questao_id} duelo {self.duelo.codigo}'



# ── Sprint 26 — Simulado Coletivo ─────────────────────────────────────────────

def _gerar_codigo_coletivo():
    import random, string
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


class SimuladoColetivo(models.Model):
    STATUS = [
        ('aguardando',   'Aguardando participantes'),
        ('em_andamento', 'Em andamento'),
        ('finalizado',   'Finalizado'),
    ]

    codigo        = models.CharField(max_length=10, unique=True, default=_gerar_codigo_coletivo)
    criador       = models.ForeignKey(User, on_delete=models.CASCADE,
                                      related_name='coletivos_criados')
    categoria     = models.ForeignKey('Categoria', null=True, blank=True,
                                      on_delete=models.SET_NULL)
    questoes      = models.ManyToManyField('Questao', blank=True,
                                           related_name='coletivos')
    n_questoes    = models.PositiveSmallIntegerField(default=10)
    tempo_por_q   = models.PositiveSmallIntegerField(default=30)
    max_jogadores = models.PositiveSmallIntegerField(default=20)
    status        = models.CharField(max_length=20, choices=STATUS, default='aguardando')
    questao_atual = models.PositiveSmallIntegerField(default=0)
    iniciado_em   = models.DateTimeField(null=True, blank=True)
    encerrado_em  = models.DateTimeField(null=True, blank=True)
    criado_em     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']

    def __str__(self):
        return f'Coletivo #{self.codigo} por {self.criador}'

    @property
    def questoes_lista(self):
        return self.questoes.order_by('pk')


class ParticipanteColetivo(models.Model):
    """Jogador inscrito em um SimuladoColetivo."""
    simulado  = models.ForeignKey(SimuladoColetivo, on_delete=models.CASCADE,
                                  related_name='participantes')
    usuario   = models.ForeignKey(User, on_delete=models.CASCADE,
                                  related_name='participacoes_coletivo')
    pontos    = models.PositiveSmallIntegerField(default=0)
    entrou_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('simulado', 'usuario')]
        ordering        = ['-pontos', 'entrou_em']

    def __str__(self):
        return f'{self.usuario.username} em {self.simulado.codigo}'


class RespostaColetivo(models.Model):
    """Resposta de um participante a uma questão do simulado coletivo."""
    simulado    = models.ForeignKey(SimuladoColetivo, on_delete=models.CASCADE,
                                    related_name='respostas')
    usuario     = models.ForeignKey(User, on_delete=models.CASCADE,
                                    related_name='respostas_coletivo')
    questao     = models.ForeignKey('Questao', on_delete=models.CASCADE,
                                    related_name='respostas_coletivo')
    alternativa = models.ForeignKey('Alternativa', null=True, blank=True,
                                    on_delete=models.SET_NULL)
    acertou     = models.BooleanField(default=False)
    tempo_ms    = models.PositiveIntegerField(default=0)
    criado_em   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('simulado', 'usuario', 'questao')]
        ordering        = ['criado_em']



# ── Sprint 28 — Monetização ───────────────────────────────────────────────────

class PlanoUsuario(models.Model):
    """
    Assinatura do usuário.
    Planos: gratuito | pro | premium
    Em produção este modelo seria gerenciado pelo webhook do gateway de pagamento.
    """
    PLANOS = [
        ('gratuito', 'Gratuito'),
        ('pro',      'PRO'),
        ('premium',  'Premium'),
    ]

    usuario      = models.OneToOneField(User, on_delete=models.CASCADE,
                                        related_name='plano')
    plano        = models.CharField(max_length=20, choices=PLANOS, default='gratuito')
    ativo        = models.BooleanField(default=True)
    expira_em    = models.DateTimeField(null=True, blank=True,
                                        help_text='Null = sem expiração (plano gratuito vitalício)')
    stripe_sub_id = models.CharField(max_length=100, blank=True,
                                      help_text='ID da assinatura no Stripe (futuro)')
    cancelada_em = models.DateTimeField(null=True, blank=True,
        help_text='Quando o usuario clicou "cancelar". Mantem acesso ate expira_em.')
    criado_em    = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plano do Usuário'

    def __str__(self):
        return f'{self.usuario.username} — {self.get_plano_display()}'

    @property
    def is_pro(self):
        return self.plano in ('pro', 'premium') and self.ativo

    @property
    def is_premium(self):
        return self.plano == 'premium' and self.ativo

    @property
    def expirado(self):
        if not self.expira_em:
            return False
        from django.utils import timezone as _tz
        return _tz.now() > self.expira_em


class CupomDesconto(models.Model):
    """Cupom de desconto / acesso trial."""
    codigo      = models.CharField(max_length=30, unique=True)
    plano_alvo  = models.CharField(max_length=20, choices=PlanoUsuario.PLANOS,
                                   default='pro')
    dias        = models.PositiveSmallIntegerField(default=30,
                                                   help_text='Dias de acesso ao plano alvo')
    usos_max    = models.PositiveSmallIntegerField(default=1)
    usos_feitos = models.PositiveSmallIntegerField(default=0)
    ativo       = models.BooleanField(default=True)
    criado_em   = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Cupom {self.codigo} ({self.get_plano_alvo_display()} {self.dias}d)'

    @property
    def disponivel(self):
        return self.ativo and self.usos_feitos < self.usos_max


class PagamentoMP(models.Model):
    """Registro de pagamentos processados via Mercado Pago.

    Guardamos referência ao payment_id do MP para auditoria e para suporte
    ao usuário (histórico de transações, reembolso etc). O webhook do MP
    atualiza este registro conforme o status muda.
    """
    STATUS_CHOICES = [
        ('pending',   'Pendente'),
        ('approved',  'Aprovado'),
        ('rejected',  'Rejeitado'),
        ('cancelled', 'Cancelado'),
        ('refunded',  'Reembolsado'),
    ]

    usuario         = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pagamentos_mp')
    plano_alvo      = models.CharField(max_length=20, choices=PlanoUsuario.PLANOS)
    valor_centavos  = models.PositiveIntegerField(help_text='Valor em centavos (ex: 1490 = R$14,90)')
    preference_id   = models.CharField(max_length=100, blank=True, db_index=True,
                                       help_text='ID da preference criada no MP')
    payment_id      = models.CharField(max_length=100, blank=True, db_index=True,
                                       help_text='ID do payment quando aprovado')
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payload_raw     = models.JSONField(blank=True, null=True,
                                       help_text='Última resposta do MP (para debug)')
    criado_em       = models.DateTimeField(auto_now_add=True)
    atualizado_em   = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Pagamento Mercado Pago'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.usuario.username} — {self.get_plano_alvo_display()} · {self.status}'


# ─── LOG DO SISTEMA ────────────────────────────────────────────────────────────

class LogSistema(models.Model):
    """Registro de eventos e erros do sistema para o painel de administração."""
    NIVEL_CHOICES = [
        ('INFO',    'Informação'),
        ('AVISO',   'Aviso'),
        ('ERRO',    'Erro'),
        ('CRITICO', 'Crítico'),
    ]
    nivel     = models.CharField(max_length=10, choices=NIVEL_CHOICES, default='INFO')
    origem    = models.CharField(max_length=120, blank=True, default='sistema',
                                 help_text='Ex: importação, questão, auth, api')
    mensagem  = models.TextField()
    detalhe   = models.TextField(blank=True,
                                 help_text='Traceback, JSON de contexto, etc.')
    usuario   = models.ForeignKey(User, on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name='logs_sistema')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Log do Sistema'
        verbose_name_plural = 'Logs do Sistema'

    def __str__(self):
        return f'[{self.nivel}] {self.mensagem[:80]}'


# ─── CUPONS E INDICAÇÕES ───────────────────────────────────────────────────

class UsoCupom(models.Model):
    """Rastreia qual usuário aplicou qual cupom — evita reuso, audita."""
    cupom    = models.ForeignKey(CupomDesconto, on_delete=models.CASCADE,
                                 related_name='usos')
    usuario  = models.ForeignKey(User, on_delete=models.CASCADE,
                                 related_name='cupons_usados')
    aplicado_em = models.DateTimeField(auto_now_add=True)
    ip_origem = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        unique_together = [('cupom', 'usuario')]   # mesmo cupom só 1x por user
        ordering = ['-aplicado_em']

    def __str__(self):
        return f'{self.usuario.username} usou {self.cupom.codigo}'


# ─── SUPORTE AO USUÁRIO ────────────────────────────────────────────────────

class TicketSuporte(models.Model):
    """Sistema de suporte ao usuário — abre chamado, equipe responde."""
    CATEGORIAS = [
        ('bug',       '🐛 Bug ou erro técnico'),
        ('duvida',    '❓ Dúvida sobre a plataforma'),
        ('questao',   '📝 Erro em questão/gabarito'),
        ('pagamento', '💳 Pagamento ou plano'),
        ('sugestao',  '💡 Sugestão de melhoria'),
        ('outro',     'Outro assunto'),
    ]
    STATUS_CHOICES = [
        ('aberto',     'Aberto'),
        ('respondido', 'Respondido pelo suporte'),
        ('aguardando', 'Aguardando usuário'),
        ('fechado',    'Fechado'),
    ]
    PRIORIDADES = [
        ('baixa',  'Baixa'),
        ('media',  'Média'),
        ('alta',   'Alta'),
        ('urgente','Urgente'),
    ]

    usuario     = models.ForeignKey(User, on_delete=models.CASCADE,
                                    related_name='tickets')
    categoria   = models.CharField(max_length=20, choices=CATEGORIAS, default='duvida')
    assunto     = models.CharField(max_length=200)
    mensagem    = models.TextField()
    email_contato = models.EmailField(blank=True,
        help_text='Email alternativo para resposta (deixe vazio para usar email da conta)')
    url_origem  = models.URLField(blank=True, default='',
        help_text='Onde o usuário estava quando abriu o ticket')
    status      = models.CharField(max_length=15, choices=STATUS_CHOICES, default='aberto')
    prioridade  = models.CharField(max_length=10, choices=PRIORIDADES, default='media')
    criado_em   = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    fechado_em  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Ticket de Suporte'
        verbose_name_plural = 'Tickets de Suporte'

    def __str__(self):
        return f'#{self.id} · {self.assunto[:50]}'

    @property
    def aberto(self):
        return self.status in ('aberto', 'respondido', 'aguardando')


class RespostaTicket(models.Model):
    """Cada mensagem trocada num ticket de suporte."""
    ticket   = models.ForeignKey(TicketSuporte, on_delete=models.CASCADE,
                                 related_name='respostas')
    autor    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    mensagem = models.TextField()
    eh_staff = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['criado_em']

    def __str__(self):
        prefixo = '👤 STAFF' if self.eh_staff else '🙋 USER'
        return f'{prefixo} · {self.mensagem[:60]}'


# ─── BANDEIRA "REVISAR DEPOIS" ─────────────────────────────────────────────

class QuestaoMarcada(models.Model):
    """Usuário marca uma questão para revisar depois (diferente de favorita)."""
    usuario   = models.ForeignKey(User, on_delete=models.CASCADE,
                                  related_name='marcadas')
    questao   = models.ForeignKey(Questao, on_delete=models.CASCADE)
    motivo    = models.CharField(max_length=120, blank=True, default='',
        help_text='Por que marcou? (ex: "preciso revisar a justificativa")')
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('usuario', 'questao')]
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.usuario.username} marcou Q{self.questao_id}'


# ─── CONCURSO PREFERIDO (para onboarding personalizado) ────────────────────

class ConcursoPreferido(models.Model):
    """Concurso que o usuário está focando — define recomendações e UX."""
    CONCURSOS = [
        ('prf',   'PRF — Polícia Rodoviária Federal'),
        ('pf',    'PF — Polícia Federal'),
        ('inss',  'INSS — Técnico do Seguro Social'),
        ('enem',  'ENEM'),
        ('tjdf',  'TJ-DF — Tribunal de Justiça'),
        ('trf',   'TRF — Tribunais Regionais'),
        ('camara','Câmara/Senado'),
        ('estadual', 'Concurso Estadual'),
        ('municipal','Concurso Municipal'),
        ('outro', 'Outro'),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE,
                                   related_name='concurso_pref')
    concurso = models.CharField(max_length=20, choices=CONCURSOS)
    data_prova_esperada = models.DateField(null=True, blank=True,
        help_text='Quando você espera fazer a prova?')
    horas_por_dia = models.PositiveSmallIntegerField(default=2,
        help_text='Quantas horas/dia consegue estudar?')
    atualizado_em = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.usuario.username} → {self.get_concurso_display()}'

    @property
    def dias_para_prova(self):
        if not self.data_prova_esperada:
            return None
        from django.utils import timezone as _tz
        delta = self.data_prova_esperada - _tz.localdate()
        return max(0, delta.days)
