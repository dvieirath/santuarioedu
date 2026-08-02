from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from . import views

urlpatterns = [
    # Search global + próxima ação (usados no topbar/dashboard)
    path('api/search/',        views.api_search_global, name='api_search_global'),
    path('api/proxima-acao/',  views.api_proxima_acao,  name='api_proxima_acao'),

    path('', views.home, name='home'),
    path('materiais/', views.listar_materiais, name='listar_materiais'),
    path('estudar/', views.escolher_tema, name='escolher_tema'),
    path('quiz/', views.iniciar_quiz, name='iniciar_quiz'),
    path('quiz/<int:categoria_id>/', views.iniciar_quiz, name='iniciar_quiz_categoria'),
    path('api/editar-questao/<int:questao_id>/', views.api_editar_questao, name='api_editar_questao'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('plano-de-estudos/', views.plano_estudos, name='plano_estudos'),
    path('analytics/', views.analytics, name='analytics'),
    path('progresso-edital/', views.progresso_edital, name='progresso_edital'),
    path('relatorio-semanal/', views.relatorio_semanal, name='relatorio_semanal'),
    path('relatorio-semanal/enviar/', views.enviar_relatorio_email, name='enviar_relatorio_email'),
    path('cadastro/', views.cadastro, name='cadastro'),
    path('perfil/', views.perfil, name='perfil'),
    path('perfil/excluir/', views.excluir_conta, name='excluir_conta'),
    # Páginas legais (LGPD)
    path('legal/privacidade/', views.politica_privacidade, name='politica_privacidade'),
    path('legal/termos/',      views.termos_uso,            name='termos_uso'),
    path('faq/',               views.faq,                   name='faq'),
    path('cupom/aplicar/',     views.aplicar_cupom,         name='aplicar_cupom'),
    path('admin-metricas/',    views.metricas_negocio,      name='admin_metricas'),

    # Suporte
    path('suporte/',                 views.suporte_lista,       name='suporte_lista'),
    path('suporte/novo/',            views.suporte_novo,        name='suporte_novo'),
    path('suporte/<int:ticket_id>/', views.suporte_detalhe,     name='suporte_detalhe'),

    # Marcar questão pra revisar depois
    path('marcadas/',                              views.questoes_marcadas, name='questoes_marcadas'),
    path('api/marcar-questao/<int:questao_id>/',   views.api_marcar_questao, name='api_marcar_questao'),

    # Onboarding por concurso + trial PRO
    path('onboarding/',  views.onboarding_concurso, name='onboarding_concurso'),

    # Quiz público "qual concurso é pra você?"
    path('qual-concurso/', views.quiz_qual_concurso, name='quiz_qual_concurso'),

    # Card compartilhável + análise por subtema
    path('compartilhar/',     views.card_progresso,    name='card_progresso'),
    path('analise-subtemas/', views.analise_subtemas,  name='analise_subtemas'),

    # Revisão de questões (admin/staff)
    path('admin-revisao/',                          views.revisao_questoes_painel, name='admin_revisao'),
    path('api/admin/revisao/proxima/',              views.api_revisao_proxima,        name='api_revisao_proxima'),
    path('api/admin/revisao/bulk-approve/',         views.api_revisao_bulk_approve,   name='api_revisao_bulk_approve'),
    path('api/admin/revisao/duplicatas/<int:questao_id>/', views.api_revisao_duplicatas, name='api_revisao_duplicatas'),
    path('api/admin/revisao/por-id/<int:questao_id>/',      views.api_revisao_por_id,     name='api_revisao_por_id'),
    path('admin-revisao/acao/<int:questao_id>/',    views.api_revisar_acao,        name='api_revisar_acao'),
    # Simulado
    path('simulado/edital/', views.simulado_edital, name='simulado_edital'),
    path('simulado/iniciar/', views.iniciar_simulado, name='iniciar_simulado'),
    path('simulado/<int:simulado_id>/questao/<int:numero>/', views.simulado_questao, name='simulado_questao'),
    path('simulado/<int:simulado_id>/finalizar/', views.finalizar_simulado, name='finalizar_simulado'),
    path('simulado/<int:simulado_id>/resultado/', views.simulado_resultado, name='simulado_resultado'),
    # Caderno de erros, histórico, favoritas
    path('caderno-de-erros/', views.caderno_erros, name='caderno_erros'),
    path('historico-simulados/', views.historico_simulados, name='historico_simulados'),
    path('favoritas/', views.favoritas, name='favoritas'),
    path('api/favorita/<int:questao_id>/', views.toggle_favorita, name='toggle_favorita'),
    path('api/justificativa/<int:questao_id>/', views.api_justificativa_questao, name='api_justificativa_questao'),
    # Push notifications
    path('api/push/config/', views.push_config, name='push_config'),
    path('api/push/subscribe/', views.push_subscribe, name='push_subscribe'),
    path('api/push/unsubscribe/', views.push_unsubscribe, name='push_unsubscribe'),
    path('api/push/test/', views.push_test, name='push_test'),
    # Revisão inteligente
    path('revisao/', views.quiz_revisao, name='quiz_revisao'),
    path('revisao/<int:categoria_id>/', views.quiz_revisao, name='quiz_revisao_categoria'),
    # Sprint 5 — Conquistas, Anotações, CSV
    path('conquistas/', views.conquistas, name='conquistas'),
    path('api/anotacao/<int:questao_id>/', views.api_anotacao, name='api_anotacao'),
    path('admin-questoes/importar/', views.admin_importar_csv, name='admin_importar_csv'),
    path('admin-questoes/importar-ia/', views.admin_importar_ia, name='admin_importar_ia'),
    # Sprint 6 — Ranking, SRS, Sessão, Perfil Público
    path('ranking/', views.ranking, name='ranking'),
    path('revisao-srs/', views.revisao_srs, name='revisao_srs'),
    path('api/sessao/', views.api_sessao, name='api_sessao'),
    path('u/<str:username>/', views.perfil_publico, name='perfil_publico'),
    # Painel Admin de Questões
    path('admin-painel/',                                   views.admin_painel,         name='admin_painel'),
    path('admin-meta-progresso/',                           views.admin_meta_progresso, name='admin_meta_progresso'),
    path('admin-questoes/',                                 views.admin_questoes,        name='admin_questoes'),
    path('admin-questoes/criar/',                           views.admin_questao_criar,   name='admin_questao_criar'),
    path('admin-questoes/<int:questao_id>/editar/',         views.admin_questao_editar,  name='admin_questao_editar'),
    path('admin-questoes/<int:questao_id>/excluir/',        views.admin_questao_excluir, name='admin_questao_excluir'),
    path('api/admin/questao/<int:questao_id>/',             views.api_admin_questao,     name='api_admin_questao'),
    # Sprint 11 — Tutor IA, Flashcards, Análise Banca, Modo Desafio
    path('api/tutor-ia/',                        views.api_tutor_ia,            name='api_tutor_ia'),
    path('flashcards/',                          views.flashcards,              name='flashcards'),
    path('flashcards/estudar/',                  views.flashcard_estudar,       name='flashcard_estudar'),
    path('api/flashcard/<int:flashcard_id>/deletar/', views.api_flashcard_deletar, name='api_flashcard_deletar'),
    path('analise-banca/',                       views.analise_banca,           name='analise_banca'),
    path('modo-desafio/',                        views.modo_desafio,            name='modo_desafio'),
    # Sprint 12 — Resumos IA, Grupos, Notificações, Export, Revisão Inteligente
    path('resumos/',                             views.resumos_lista,           name='resumos_lista'),
    path('resumos/<int:categoria_id>/',          views.resumo_disciplina,       name='resumo_disciplina'),
    path('mapas/',                               views.mapas_lista,             name='mapas_lista'),
    path('mapas/<int:categoria_id>/',            views.mapa_mental,             name='mapa_mental'),
    # Materiais de apoio (agnostico de concurso)
    path('estatisticas/',                        views.estatisticas_incidencia, name='estatisticas_incidencia'),
    path('timelines/',                           views.timelines_lista,         name='timelines_lista'),
    path('timelines/<slug:slug>/',               views.timeline_lei_detalhe,    name='timeline_lei_detalhe'),
    path('comparativo/',                         views.comparativo_lista,       name='comparativo_lista'),
    path('comparativo/<int:categoria_id>/',      views.comparativo_categoria,   name='comparativo_categoria'),
    path('glossario/',                           views.glossario_lista,         name='glossario_lista'),
    path('glossario/gerar/<int:categoria_id>/',  views.glossario_gerar_categoria, name='glossario_gerar_categoria'),
    path('grupos/',                              views.grupos_lista,            name='grupos_lista'),
    path('grupos/<int:grupo_id>/',               views.grupo_detalhe_v2,        name='grupo_detalhe'),
    path('grupos/<int:grupo_id>/sair/',          views.sair_grupo,              name='sair_grupo'),
    path('notificacoes/',                        views.central_notificacoes,    name='central_notificacoes'),
    path('api/notificacoes/count/',              views.api_notificacoes_count,     name='api_notificacoes_count'),
    path('api/notificacoes/recentes/',           views.api_notificacoes_recentes,  name='api_notificacoes_recentes'),
    path('api/notificacoes/<int:notif_id>/lida/', views.api_notificacao_lida,      name='api_notificacao_lida'),
    path('exportar/historico.csv',               views.exportar_historico_csv,  name='exportar_historico_csv'),
    path('certificado/',                         views.certificado_progresso,   name='certificado_progresso'),
    # Sprint 13 — Simulado Personalizado, Metas, Comentários, Assuntos, Admin Stats
    path('simulado/personalizado/',              views.simulado_personalizado,  name='simulado_personalizado'),
    path('metas/',                               views.metas_avancadas,         name='metas_avancadas'),
    path('api/comentarios/<int:questao_id>/',    views.api_comentarios,         name='api_comentarios'),
    path('api/comentario/<int:comentario_id>/upvote/',  views.api_comentario_upvote,  name='api_comentario_upvote'),
    path('api/comentario/<int:comentario_id>/deletar/', views.api_comentario_deletar, name='api_comentario_deletar'),
    path('assuntos/',                            views.estudar_por_assunto,     name='estudar_por_assunto'),
    path('assuntos/<path:assunto>/',             views.quiz_por_assunto,        name='quiz_por_assunto'),
    path('admin-stats/',                         views.admin_stats,             name='admin_stats'),
    # Sprint 14 — Ranking Global, Favoritas, Análise Erros, Pomodoro, Feed Grupo
    path('favoritas/estudar/',                   views.quiz_favoritas,          name='quiz_favoritas'),
    path('analise-erros/',                       views.analise_erros,           name='analise_erros'),
    # grupo_detalhe_v2 substitui a rota original da Sprint 12
    path('grupos/<int:grupo_id>/v2/',            views.grupo_detalhe_v2,        name='grupo_detalhe_v2'),
    # Sprint 15 — Questão do Dia, Revisão Simulado, Plano IA, Dificuldade, Card
    path('questao-do-dia/',                      views.questao_do_dia,          name='questao_do_dia'),
    path('simulado/<int:simulado_id>/revisao/',  views.simulado_revisao,        name='simulado_revisao'),
    path('plano-ia/',                            views.plano_estudos_ia,        name='plano_estudos_ia'),
    path('api/avaliar/<int:questao_id>/',        views.api_avaliar_questao,     name='api_avaliar_questao'),
    path('conquistas/<str:codigo>/card/',        views.conquista_card,          name='conquista_card'),
    # Sprint 16 — XP & Níveis, Relatório PDF, Metas Visual, Comparativo
    path('xp/',                                  views.painel_xp,               name='painel_xp'),
    path('api/xp/',                              views.api_meu_xp,              name='api_meu_xp'),
    path('relatorio-pdf/',                       views.relatorio_pdf,           name='relatorio_pdf'),
    path('metas-semanais/',                      views.metas_semanais,          name='metas_semanais'),
    path('performance-comparativa/',             views.performance_comparativa, name='performance_comparativa'),
    # Sprint 17 — Mapa de Conhecimento Visual
    path('mapa/',                                views.mapa_conhecimento,        name='mapa_conhecimento'),
    # Sprint 18 — Plano de Estudos Dinâmico
    path('plano-dinamico/',                      views.plano_dinamico,           name='plano_dinamico'),
    # Sprint 19 — Notificações
    path('notificacoes/preferencias/',           views.preferencias_notificacao, name='preferencias_notificacao'),
    # Sprint 20 — Tutor IA Personalizado
    path('api/explicar/',                        views.api_explicar_questao,     name='api_explicar_questao'),
    path('api/explicacao/<int:explicacao_id>/feedback/', views.api_feedback_explicacao, name='api_feedback_explicacao'),
    # Sprint 21 — Análise Preditiva de Banca
    path('api/insight-banca/',                   views.api_insight_banca,        name='api_insight_banca'),
    # Sprint 22 — Simulado Preditivo
    path('simulado/preditivo/',                         views.simulado_preditivo,            name='simulado_preditivo'),
    path('simulado/<int:simulado_id>/relatorio-ia/',    views.relatorio_simulado_ia,          name='relatorio_simulado_ia'),
    path('api/simulado/<int:simulado_id>/relatorio-ia/', views.api_gerar_relatorio_simulado,  name='api_gerar_relatorio_simulado'),
    # Sprint 23 — Geração de Questões IA + Predição de Tópicos
    path('admin-questoes/gerar-ia/',   views.admin_gerar_questoes_ia, name='admin_gerar_questoes_ia'),
    path('previsao-topicos/',          views.previsao_topicos,        name='previsao_topicos'),
    # Sprint 24 — Modo Prova Real + Laudo
    path('prova-real/',                          views.modo_prova_real,    name='modo_prova_real'),
    path('simulado/<int:simulado_id>/laudo/',    views.laudo_desempenho,   name='laudo_desempenho'),
    # Sprint 25 — Duelo em Tempo Real
    path('duelo/',                               views.duelo_home,         name='duelo_home'),
    path('duelo/criar/',                         views.duelo_criar,        name='duelo_criar'),
    path('duelo/sala/<str:codigo>/',             views.duelo_sala,         name='duelo_sala'),
    path('duelo/<int:duelo_id>/jogar/',          views.duelo_jogar,        name='duelo_jogar'),
    path('duelo/<int:duelo_id>/resultado/',      views.duelo_resultado,    name='duelo_resultado'),
    path('api/duelo/entrar/',                    views.api_duelo_entrar,   name='api_duelo_entrar'),
    path('api/duelo/<int:duelo_id>/responder/',  views.api_duelo_responder,name='api_duelo_responder'),
    path('api/duelo/<int:duelo_id>/status/',     views.api_duelo_status,   name='api_duelo_status'),
    # Sprint 26 — Simulado Coletivo
    path('coletivo/',                                   views.coletivo_home,          name='coletivo_home'),
    path('coletivo/criar/',                             views.coletivo_criar,         name='coletivo_criar'),
    path('coletivo/sala/<str:codigo>/',                 views.coletivo_sala,          name='coletivo_sala'),
    path('coletivo/<int:sala_id>/jogar/',               views.coletivo_jogar,         name='coletivo_jogar'),
    path('coletivo/<int:sala_id>/resultado/',           views.coletivo_resultado,     name='coletivo_resultado'),
    path('api/coletivo/<int:sala_id>/iniciar/',         views.coletivo_iniciar,       name='coletivo_iniciar'),
    path('api/coletivo/<int:sala_id>/responder/',       views.api_coletivo_responder, name='api_coletivo_responder'),
    path('api/coletivo/<int:sala_id>/status/',          views.api_coletivo_status,    name='api_coletivo_status'),
    # Sprint 28 — Monetização
    path('planos/',                     views.planos,            name='planos'),
    path('minha-assinatura/',           views.minha_assinatura,  name='minha_assinatura'),
    path('assinatura/cancelar/',        views.cancelar_assinatura, name='cancelar_assinatura'),
    path('api/cupom/',                  views.aplicar_cupom,     name='aplicar_cupom'),
    path('api/upgrade/',                views.simular_upgrade,   name='simular_upgrade'),
    path('api/meu-plano/',              views.api_meu_plano,     name='api_meu_plano'),
    # Checkout Mercado Pago
    path('api/checkout/mp/',            views.iniciar_checkout_mp,             name='iniciar_checkout_mp'),
    path('pagamento/webhook/',          csrf_exempt(views.mp_webhook),         name='mp_webhook'),
    path('pagamento/sucesso/',          views.pagamento_sucesso,               name='pagamento_sucesso'),
    path('pagamento/falha/',            views.pagamento_falha,                 name='pagamento_falha'),
    path('pagamento/pendente/',         views.pagamento_pendente,              name='pagamento_pendente'),
    # Painel de Sistema (superuser only)
    path('admin-sistema/',                                views.admin_sistema,              name='admin_sistema'),
    path('api/admin/log/criar/',                          views.api_admin_log_criar,        name='api_admin_log_criar'),
    path('api/admin/log/<int:log_id>/deletar/',           views.api_admin_log_deletar,      name='api_admin_log_deletar'),
    path('api/admin/logs/limpar/',                        views.api_admin_logs_limpar,      name='api_admin_logs_limpar'),
    path('api/admin/usuario/<int:user_id>/toggle-staff/', views.api_admin_toggle_staff,     name='api_admin_toggle_staff'),
    path('api/admin/questoes/busca/',                     views.api_admin_questao_busca,    name='api_admin_questao_busca'),
    path('api/admin/questao/<int:questao_id>/salvar/',    views.api_admin_questao_salvar,   name='api_admin_questao_salvar'),
]
