from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from quiz import views as quiz_views
from . import views as core_views
from .sitemaps import PaginasPublicasSitemap

SITEMAPS = {'paginas': PaginasPublicasSitemap}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    # Health + robots + sitemap (SEO)
    path('health/', core_views.health, name='health'),
    path('robots.txt', core_views.robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap, {'sitemaps': SITEMAPS}, name='django.contrib.sitemaps.views.sitemap'),
    # PWA — must be at root for full-site service-worker scope
    path('sw.js', quiz_views.pwa_sw, name='pwa_sw'),
    path('manifest.json', quiz_views.pwa_manifest, name='pwa_manifest'),
    path('offline/', quiz_views.pwa_offline, name='pwa_offline'),
    path('__reload__/', include('django_browser_reload.urls')),
    path('', include('quiz.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Handlers globais de erro (Django acha por nome em ROOT_URLCONF)
handler404 = 'prf_master.views.page_404'
handler500 = 'prf_master.views.page_500'
handler403 = 'prf_master.views.page_403'