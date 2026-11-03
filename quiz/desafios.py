"""Validação da partida com relógio e respostas controlados pelo servidor."""
from datetime import timedelta
from uuid import UUID

from django.http import JsonResponse
from django.utils import timezone

from .models import Alternativa, Questao, TentativaDesafio


def processar_acao(usuario, data):
    """Chamado dentro de transaction.atomic; bloqueia a partida até o commit.

    Retorna (resposta HTTP, tentativa). Uma resposta None autoriza finalizar.
    """
    if not isinstance(data, dict):
        return JsonResponse({'erro': 'Payload inválido'}, status=400), None
    try:
        tentativa_id = UUID(str(data.get('tentativa_id', '')))
    except (ValueError, TypeError):
        return JsonResponse({'erro': 'Partida inválida'}, status=400), None
    tentativa = TentativaDesafio.objects.select_for_update().filter(
        pk=tentativa_id, usuario=usuario).first()
    if not tentativa:
        return JsonResponse({'erro': 'Partida não encontrada'}, status=404), None
    acao = data.get('acao')
    if tentativa.resultado is not None:
        if acao == 'finalizar':
            return JsonResponse(tentativa.resultado), tentativa
        return JsonResponse({'erro': 'Partida encerrada'}, status=409), tentativa
    if timezone.now() - tentativa.criado_em > timedelta(hours=2):
        return JsonResponse({'erro': 'Partida expirada. Inicie outra.'}, status=409), tentativa
    if acao == 'finalizar':
        if len(tentativa.respostas) != len(tentativa.questoes_ids):
            return JsonResponse({'erro': 'Responda todas as questões.'}, status=409), tentativa
        return None, tentativa
    index = data.get('indice')
    if type(index) is not int or not 0 <= index < len(tentativa.questoes_ids):
        return JsonResponse({'erro': 'Índice inválido'}, status=400), tentativa
    if acao == 'responder' and index < len(tentativa.respostas):
        return JsonResponse(tentativa.respostas[index]['feedback']), tentativa
    if index != len(tentativa.respostas):
        return JsonResponse({'erro': 'Questão fora de ordem'}, status=409), tentativa
    if acao == 'abrir':
        questao = Questao.objects.select_related('categoria').filter(
            pk=tentativa.questoes_ids[index]).first()
        if questao is None:
            return JsonResponse({'erro': 'Questão indisponível. Inicie outra partida.'}, status=409), tentativa
        if tentativa.aberta_em is None:
            tentativa.aberta_em = timezone.now()
            tentativa.save(update_fields=['aberta_em'])
        restante = max(0, tentativa.segundos_por_questao -
                       (timezone.now() - tentativa.aberta_em).total_seconds())
        return JsonResponse({'restante': restante, 'questao': {
            'id': questao.pk, 'texto': questao.texto, 'tipo': questao.tipo,
            'categoria': questao.categoria.nome,
            'imagem_url': questao.imagem.url if questao.imagem else None,
            'alternativas': list(questao.alternativa_set.values('id', 'texto')),
        }}), tentativa
    if acao != 'responder' or tentativa.aberta_em is None:
        return JsonResponse({'erro': 'Abra a questão antes de responder.'}, status=400), tentativa
    questao_id = tentativa.questoes_ids[index]
    alt_id = data.get('alternativa_id')
    alternativa = None
    if alt_id is not None:
        if type(alt_id) is not int:
            return JsonResponse({'erro': 'Alternativa inválida'}, status=400), tentativa
        alternativa = Alternativa.objects.filter(pk=alt_id, questao_id=questao_id).first()
        if alternativa is None:
            return JsonResponse({'erro': 'Alternativa inválida'}, status=400), tentativa
    tempo = max(0, (timezone.now() - tentativa.aberta_em).total_seconds())
    expirou = tempo > tentativa.segundos_por_questao
    acertou = bool(alternativa and alternativa.correta and not expirou)
    bonus = max(0, round((tentativa.segundos_por_questao - tempo) /
                        tentativa.segundos_por_questao * 5)) if acertou else 0
    correta = Alternativa.objects.filter(questao_id=questao_id, correta=True).first()
    feedback = {'acertou': acertou, 'pontos': 10 + bonus if acertou else 0,
                'correta_id': correta.pk if correta else None, 'expirou': expirou}
    tentativa.respostas.append({
        'questao_id': questao_id,
        'alternativa_id': alternativa.pk if alternativa and not expirou else None,
        'tempo_seg': min(tempo, tentativa.segundos_por_questao),
        'feedback': feedback,
    })
    tentativa.aberta_em = None
    tentativa.save(update_fields=['respostas', 'aberta_em'])
    return JsonResponse(feedback), tentativa
