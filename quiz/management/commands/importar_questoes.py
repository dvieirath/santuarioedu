import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from quiz.models import Questao, Alternativa, Categoria

class Command(BaseCommand):
    help = 'Importa questões de um arquivo JSON'

    def add_arguments(self, parser):
        parser.add_argument('arquivo_json', type=str, help='Caminho para o arquivo JSON com as questões')

    def handle(self, *args, **kwargs):
        arquivo_path = kwargs['arquivo_json']

        if not os.path.exists(arquivo_path):
            self.stdout.write(self.style.ERROR(f'Arquivo não encontrado: {arquivo_path}'))
            return

        with open(arquivo_path, 'r', encoding='utf-8') as f:
            try:
                dados = json.load(f)
            except json.JSONDecodeError:
                self.stdout.write(self.style.ERROR('Erro ao ler o arquivo JSON. Verifique a formatação.'))
                return

        count_questoes = 0
        count_ignoradas = 0
        
        self.stdout.write("Iniciando importação... Isso pode levar alguns segundos.")

        # Usar transaction.atomic para acelerar inserções em massa
        with transaction.atomic():
            for item in dados:
                categoria_nome = item.get('categoria')
                texto_questao = item.get('texto')
                tipo = item.get('tipo', 'ME')
                justificativa = item.get('justificativa', None) # Novo campo
                alternativas = item.get('alternativas', [])
                resposta_ce = item.get('resposta_ce')

                if not categoria_nome or not texto_questao:
                    continue

                # Evitar duplicatas (verifica se já existe questão com mesmo texto)
                if Questao.objects.filter(texto=texto_questao).exists():
                    count_ignoradas += 1
                    continue

                categoria, created = Categoria.objects.get_or_create(nome=categoria_nome)

                questao = Questao.objects.create(
                    categoria=categoria,
                    texto=texto_questao,
                    tipo=tipo,
                    justificativa=justificativa # Salva a justificativa
                )

                if tipo == 'CE':
                    if resposta_ce:
                        e_correto = resposta_ce.lower() in ['c', 'certo', 'true']
                        Alternativa.objects.create(questao=questao, texto="Certo", correta=e_correto)
                        Alternativa.objects.create(questao=questao, texto="Errado", correta=not e_correto)
                elif alternativas:
                    for alt in alternativas:
                        Alternativa.objects.create(
                            questao=questao,
                            texto=alt['texto'],
                            correta=alt['correta']
                        )
                
                count_questoes += 1
                if count_questoes % 100 == 0:
                    self.stdout.write(f"Processadas: {count_questoes}...")

        self.stdout.write(self.style.SUCCESS(f'Concluído! {count_questoes} novas questões importadas.'))
        if count_ignoradas > 0:
            self.stdout.write(self.style.WARNING(f'{count_ignoradas} questões ignoradas por já existirem.'))
