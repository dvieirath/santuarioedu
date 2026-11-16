"""
Cria na árvore de categorias as disciplinas e os tópicos da trilha Banco do
Brasil, a partir de quiz/trilha_bb.py (edital 2022/001, Anexo III).

Só acrescenta: não move, não renomeia e não apaga nada. Pode rodar quantas
vezes quiser; o que já existe é reaproveitado (comparação sem acento e sem
diferença de maiúsculas, dentro do mesmo pai).

Uso:
    python manage.py seed_trilha_bb             # só mostra o que faria
    python manage.py seed_trilha_bb --aplicar   # cria o que falta
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from quiz.models import Categoria
from quiz.preparacao import _norm_ascii
from quiz.trilha_bb import CARGOS, DISCIPLINAS, EDITAL, itens_do_cargo


class Command(BaseCommand):
    help = 'Cria disciplinas e tópicos da trilha Banco do Brasil na árvore de categorias'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true',
                            help='Grava no banco. Sem esta opção, só simula.')

    def handle(self, *args, **opts):
        aplicar = opts['aplicar']
        self.criadas = []
        self.existentes = 0

        with transaction.atomic():
            for chave, disciplina in DISCIPLINAS.items():
                no = None
                caminho = []
                for nome in disciplina['caminho']:
                    caminho.append(nome)
                    no = self._obter(nome, no, caminho, aplicar)
                for _item, topico in disciplina['topicos']:
                    self._obter(topico, no, caminho + [topico], aplicar)

        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO(
            f'TRILHA BANCO DO BRASIL — edital {EDITAL["id"]} ({EDITAL["banca"]}, prova {EDITAL["ano_prova"]})'
        ))
        for slug, cargo in CARGOS.items():
            itens = itens_do_cargo(slug)
            self.stdout.write(
                f'  {slug:<6} {cargo["cargo"]}: {len(itens)} disciplinas, '
                f'{sum(i["questoes"] for i in itens)} questões, '
                f'{sum(i["pontos"] for i in itens):g} pontos'
            )
        self.stdout.write('')
        self.stdout.write(f'  Categorias já existentes ... {self.existentes}')
        rotulo = 'Criadas' if aplicar else 'A criar'
        self.stdout.write(f'  {rotulo} .................. {len(self.criadas)}')
        for caminho in self.criadas:
            self.stdout.write(f'    + {caminho}')

        self.stdout.write('')
        if aplicar:
            self.stdout.write(self.style.SUCCESS('Árvore da trilha aplicada.'))
        else:
            self.stdout.write(self.style.WARNING(
                'Simulação: nada foi gravado. Use --aplicar para criar.'
            ))

    def _obter(self, nome, parent, caminho, aplicar):
        """Devolve a categoria `nome` sob `parent`, criando se faltar.

        Na simulação, um nó que ainda não existe é representado por um objeto
        não salvo, para os filhos dele também aparecerem na lista "a criar".
        """
        existente = None
        if parent is None or parent.pk:
            alvo = _norm_ascii(nome)
            existente = next(
                (c for c in Categoria.objects.filter(parent=parent)
                 if _norm_ascii(c.nome) == alvo),
                None,
            )
        if existente:
            self.existentes += 1
            return existente

        self.criadas.append(' > '.join(caminho))
        if aplicar:
            return Categoria.objects.create(nome=nome, parent=parent)
        return Categoria(nome=nome, parent=parent)
