from django.apps import AppConfig


class QuizConfig(AppConfig):
    name = 'quiz'

    def ready(self):
        # Conecta os signal handlers de auditoria de segurança
        from . import signals_audit  # noqa: F401
        # Conecta os signal handlers de emails transacionais (welcome, etc)
        from . import signals  # noqa: F401
