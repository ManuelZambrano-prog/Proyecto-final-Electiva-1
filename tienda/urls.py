from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('kit/<slug:slug>/', views.detalle_kit, name='detalle_kit'),
    path('checkout/', views.checkout, name='checkout'),
    path('confirmacion/<str:codigo>/', views.confirmacion, name='confirmacion'),
    path('simulador/', views.simulador, name='simulador'),
    path('como-funciona/', views.como_funciona, name='como_funciona'),
]
