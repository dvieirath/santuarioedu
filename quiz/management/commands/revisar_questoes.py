import time
import json
import google.generativeai as genai
from django.core.management.base import BaseCommand
from django.conf import settings
from quiz.models import Questao, Alternativa

class Command(BaseCommand):
    help = 'Revisa e corrige erros de português nas questões usando IA'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=10, help='Número de questões a revisar por execução')

    def handle(self, *args, **kwargs):
        limit = kwargs['limit']
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        
        if not api_key:
            self.stdout.write(self.style.ERROR('GEMINI_API_KEY não configurada.'))
            return

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-flash-latest')

        questoes = Questao.objects.filter(revisada=False)[:limit]
        
        if not questoes.exists():
            self.stdout.write(self.style.SUCCESS('Todas as questões já foram revisadas!'))
            return

        self.stdout.write(f"Iniciando revisão de {len(questoes)} questões...")

        for q in questoes:
            self.stdout.write(f"Revisando questão {q.id}...")
            
            alternativas = list(q.alternativa_set.all())
            alts_texto = [a.texto for a in alternativas]
            
            prompt = f"""
            Atue como um revisor de textos profissional.
            Corrija erros de ortografia, gramática e pontuação no texto da questão e das alternativas abaixo.
            Mantenha o sentido original e a terminologia técnica.
            
            Texto Original: "{q.texto}"
            Alternativas Originais: {json.dumps(alts_texto, ensure_ascii=False)}
            
            Retorne APENAS um JSON válido com o seguinte formato, sem markdown:
            {{
                "texto_corrigido": "...",
                "alternativas_corrigidas": ["...", "..."]
            }}
            """
            
            try:
                response = model.generate_content(prompt)
                texto_resposta = response.text.strip()
                
                # Limpar markdown se houver (```json ... ```)
                if texto_resposta.startswith('```'):
                    texto_resposta = texto_resposta.split('\n', 1)[1]
                    if texto_resposta.endswith('```'):
                        texto_resposta = texto_resposta.rsplit('\n', 1)[0]
                
                dados = json.loads(texto_resposta)
                
                # Atualizar Questão
                q.texto = dados['texto_corrigido']
                q.revisada = True
                q.save()
                
                # Atualizar Alternativas
                novas_alts = dados.get('alternativas_corrigidas', [])
                if len(novas_alts) == len(alternativas):
                    for i, alt in enumerate(alternativas):
                        alt.texto = novas_alts[i]
                        alt.save()
                else:
                    self.stdout.write(self.style.WARNING(f"  Q{q.id}: Número de alternativas corrigidas difere do original. Alternativas não atualizadas."))

                self.stdout.write(self.style.SUCCESS(f"  Q{q.id} revisada com sucesso."))
                
                # Respeitar Rate Limit (15 RPM = 1 a cada 4s)
                time.sleep(4.5) 

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Erro ao revisar Q{q.id}: {e}"))
                # Não marca como revisada para tentar de novo depois
