from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from riego.views import CsrfRefreshLogoutView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuentas/logout/', CsrfRefreshLogoutView.as_view(), name='logout'),
    path('cuentas/', include('django.contrib.auth.urls')),
    path('', include('riego.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
