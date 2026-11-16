"""
Importa provas da Fundação Cesgranrio a partir dos PDFs oficiais, sem IA.

Entrada: a pasta gerada por
    python scripts/baixar_provas_concursos/baixar_provas.py cesgranrio <slug> --pasta BB_23 --conferencia 2
que contém o manifesto, um caderno de cada prova, uma segunda versão do caderno
para conferência e os gabaritos.

Só entra no banco a questão que passa por tudo isto:
  - lida sem problema (cinco alternativas, sem figura na área, sem fórmula com
    expoente ou índice, destaque identificado quando o enunciado fala em destaque);
  - não anulada no gabarito oficial (o definitivo, quando existe);
  - conferida na segunda versão do caderno: mesmo enunciado, mesmas alternativas
    e a MESMA resposta, lida de outro PDF e de outra coluna do gabarito.

O que entra, entra PENDENTE (revisada=False): a liberação para o aluno continua
sendo uma decisão de revisão. O que fica de fora vai para o relatório, com o
motivo e o texto lido, para conferência manual.

Uso:
    python manage.py importar_cesgranrio provas_pdf/materia_prima/BB_23 --ano 2023
    python manage.py importar_cesgranrio provas_pdf/materia_prima/BB_23 --ano 2023 --aplicar
"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz import cesgranrio
from quiz.models import Alternativa, Categoria, Questao, TextoApoio
from quiz.preparacao import _norm_ascii
from quiz.trilha_bb import DISCIPLINAS, EDITAL


def categorias_por_disciplina():
    """{nome da disciplina no gabarito (normalizado): Categoria} pela trilha BB.

    Levanta CommandError se a árvore da trilha ainda não foi criada.
    """
    mapa = {}
    for dados in DISCIPLINAS.values():
        no = None
        for nome in dados["caminho"]:
            alvo = _norm_ascii(nome)
            no = next((c for c in Categoria.objects.filter(parent=no)
                       if _norm_ascii(c.nome) == alvo), None)
            if no is None:
                raise CommandError(
                    f'Categoria "{" > ".join(dados["caminho"])}" não existe. '
                    'Rode antes: python manage.py seed_trilha_bb --aplicar'
                )
        mapa[cesgranrio.normalizar(dados["nome_edital"])] = no
    return mapa


def avaliar(questoes, conferencia):
    """Decide o destino de cada questão. Devolve [(questao, motivos)]; sem motivos = entra."""
    resultado = []
    for questao in questoes:
        motivos = list(questao.problemas)
        if not motivos and conferencia is not None:
            situacao = conferencia.get(questao.numero, "sem par")
            if situacao != "conferida":
                motivos.append(f"conferência com a segunda versão do caderno: {situacao}")
        resultado.append((questao, motivos))
    return resultado


def separar_titulo(texto_apoio):
    """(título, corpo) do texto de apoio: o primeiro parágrafo é título quando é
    curto e não é um parágrafo numerado."""
    partes = texto_apoio.split(chr(10) + chr(10), 1)
    if len(partes) == 2 and len(partes[0]) <= 150 and not partes[0].startswith('['):
        return partes[0].strip(), partes[1].strip()
    return '', texto_apoio.strip()


def obter_texto_apoio(texto_apoio, fonte, aplicar, cache):
    """Devolve o TextoApoio correspondente, criando se preciso. Na simulação,
    devolve um objeto não salvo (só para calcular o hash da questão)."""
    titulo, corpo = separar_titulo(texto_apoio)
    chave = TextoApoio.hash_de(corpo)
    if chave in cache:
        return cache[chave]
    objeto = TextoApoio.objects.filter(texto_hash=chave).first()
    if objeto is None:
        objeto = TextoApoio(titulo=titulo[:255], texto=corpo, fonte=fonte[:255], texto_hash=chave)
        if aplicar:
            objeto.save()
    cache[chave] = objeto
    return objeto


def gravar(avaliadas, categorias, banca, ano, aplicar, fonte=''):
    """Grava as questões aprovadas na avaliação. Devolve a lista de registros do relatório.

    O texto de apoio vira um registro próprio, ligado às questões; o enunciado
    guarda só a pergunta.
    """
    registros = []
    textos = {}
    for questao, motivos in avaliadas:
        registro = {
            "numero": questao.numero,
            "disciplina": questao.disciplina,
            "gabarito": questao.correta,
            "avisos": questao.avisos,
            "situacao": "retida" if motivos else "importada",
            "motivos": motivos,
            "id": None,
        }
        if motivos:
            registro["lido"] = {
                "enunciado": questao.enunciado,
                "alternativas": questao.alternativas,
                "texto_solto": questao.texto_solto,
            }
            registros.append(registro)
            continue

        categoria = categorias.get(questao.disciplina)
        if categoria is None:
            registro.update(situacao="retida", motivos=[f'disciplina sem categoria: "{questao.disciplina}"'])
            registros.append(registro)
            continue

        texto = questao.enunciado
        apoio = None
        if questao.texto_apoio:
            apoio = obter_texto_apoio(
                questao.texto_apoio, f'{fonte}, {questao.disciplina.title()}', aplicar, textos)
        existente = Questao.objects.filter(texto_hash=Questao.calcular_hash(texto, apoio)).first()
        if existente is not None:
            registro.update(situacao="duplicada", id=existente.id)
            registros.append(registro)
            continue

        if aplicar:
            nova = Questao.objects.create(
                categoria=categoria, texto=texto, tipo="ME", banca=banca, ano=ano,
                revisada=False, gerada_por_ia=False, texto_apoio=apoio,
            )
            Alternativa.objects.bulk_create([
                Alternativa(questao=nova, texto=texto_alt, correta=(letra == questao.correta))
                for letra, texto_alt in questao.alternativas
            ])
            registro["id"] = nova.id
            registro["texto_apoio_id"] = apoio.id if apoio else None
        registros.append(registro)
    return registros


class Command(BaseCommand):
    help = "Importa provas da Cesgranrio (PDF oficial, com conferência entre versões do caderno)"

    def add_arguments(self, parser):
        parser.add_argument("pasta", help="Pasta com manifesto_cesgranrio.json e os PDFs")
        parser.add_argument("--ano", type=int, required=True, help="Ano de aplicação da prova")
        parser.add_argument("--aplicar", action="store_true",
                            help="Grava no banco. Sem esta opção, só simula e gera o relatório.")
        parser.add_argument("--sem_conferencia", action="store_true",
                            help="Aceita prova sem segunda versão do caderno (não recomendado)")
        parser.add_argument("--relatorio", default="",
                            help="Arquivo JSON do relatório (padrão: output/importacao_cesgranrio_<pasta>_<data>/)")

    def handle(self, *args, **opts):
        pasta = Path(opts["pasta"])
        manifesto_path = pasta / "manifesto_cesgranrio.json"
        if not manifesto_path.exists():
            raise CommandError(f"Manifesto não encontrado: {manifesto_path}")
        manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
        categorias = categorias_por_disciplina()

        self.stdout.write("Montando vocabulário a partir do banco...")
        vocabulario = cesgranrio.vocabulario_de(Questao.objects.values_list("texto", flat=True).iterator())
        vocabulario |= cesgranrio.vocabulario_de(Alternativa.objects.values_list("texto", flat=True).iterator())

        relatorio = {
            "pasta": str(pasta), "ano": opts["ano"], "banca": EDITAL["banca"],
            "aplicado": bool(opts["aplicar"]), "gerado_em": datetime.now().isoformat(timespec="seconds"),
            "provas": [],
        }
        totais = Counter()
        motivos_gerais = Counter()
        por_disciplina = Counter()

        with transaction.atomic():
            for item in manifesto:
                gabarito_pdf = item.get("gabarito_definitivo") or item.get("gabarito_preliminar")
                if not gabarito_pdf:
                    raise CommandError(f'{item["chave"]}: sem gabarito no manifesto')
                versoes = cesgranrio.ler_gabarito(cesgranrio.texto_do_pdf(gabarito_pdf))
                versao = item["versao_caderno"]
                if versao not in versoes:
                    raise CommandError(f'{item["chave"]}: gabarito não traz a versão {versao} do caderno')
                questoes = cesgranrio.montar_questoes(
                    cesgranrio.extrair_paginas(item["caderno"]), versoes[versao], vocabulario)

                conferencia = None
                if item.get("caderno_conferencia"):
                    outra = cesgranrio.montar_questoes(
                        cesgranrio.extrair_paginas(item["caderno_conferencia"]),
                        versoes[item["versao_conferencia"]], vocabulario)
                    conferencia = cesgranrio.conferir_versoes(questoes, outra)
                elif not opts["sem_conferencia"]:
                    raise CommandError(
                        f'{item["chave"]}: sem segunda versão do caderno para conferência. '
                        'Baixe com --conferencia 2 ou use --sem_conferencia.'
                    )

                fonte = f'{EDITAL["orgao"]} {opts["ano"]}, {item["titulo"]}'
                registros = gravar(avaliar(questoes, conferencia), categorias,
                                   EDITAL["banca"], opts["ano"], opts["aplicar"], fonte=fonte)
                contagem = Counter(r["situacao"] for r in registros)
                totais.update(contagem)
                for registro in registros:
                    motivos_gerais.update(registro["motivos"])
                    if registro["situacao"] == "importada":
                        por_disciplina[registro["disciplina"]] += 1
                relatorio["provas"].append({
                    "chave": item["chave"], "titulo": item["titulo"],
                    "gabarito": "definitivo" if item.get("gabarito_definitivo") else "preliminar",
                    "versao_caderno": versao, "versao_conferencia": item.get("versao_conferencia"),
                    "contagem": dict(contagem), "questoes": registros,
                })
                self.stdout.write(
                    f'  {item["chave"]:<12} {len(registros)} questões: '
                    f'{contagem["importada"]} entram, {contagem["retida"]} retidas, '
                    f'{contagem["duplicada"]} já existiam'
                )

        relatorio["totais"] = dict(totais)
        relatorio["motivos"] = dict(motivos_gerais)
        relatorio["importadas_por_disciplina"] = dict(por_disciplina)
        destino = Path(opts["relatorio"]) if opts["relatorio"] else (
            Path(settings.BASE_DIR) / "output"
            / f'importacao_cesgranrio_{pasta.name}_{datetime.now():%Y%m%d_%H%M%S}' / "relatorio.json"
        )
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=1), encoding="utf-8")

        self.stdout.write("")
        verbo = "Importadas (pendentes de revisão)" if opts["aplicar"] else "Entrariam"
        self.stdout.write(self.style.SUCCESS(f'{verbo}: {totais["importada"]}'))
        self.stdout.write(f'Retidas para conferência manual: {totais["retida"]}')
        self.stdout.write(f'Já existiam no banco: {totais["duplicada"]}')
        if por_disciplina:
            self.stdout.write("\nPor disciplina:")
            for nome, n in por_disciplina.most_common():
                self.stdout.write(f"  {n:>4}  {nome}")
        if motivos_gerais:
            self.stdout.write("\nMotivos de retenção:")
            for motivo, n in motivos_gerais.most_common():
                self.stdout.write(f"  {n:>4}  {motivo}")
        self.stdout.write(f"\nRelatório: {destino}")
        if not opts["aplicar"]:
            self.stdout.write(self.style.WARNING("Simulação: nada foi gravado. Use --aplicar para importar."))
