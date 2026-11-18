from django.urls import path
from .views import PriceHistoryView, ResourceAction, ResourceDetail, ResourceList, UnitsView
from .partner_views import Activity, AddProfile

urlpatterns = [
    path('partners/<uuid:pk>/profiles/', AddProfile.as_view()),
    path('partners/<uuid:pk>/activity/', Activity.as_view()),
    path('units/', UnitsView.as_view()),
    path('products/<uuid:pk>/price-history/', PriceHistoryView.as_view()),
    path('<str:resource>/', ResourceList.as_view()),
    path('<str:resource>/<uuid:pk>/', ResourceDetail.as_view()),
    path('<str:resource>/<uuid:pk>/<str:action>/', ResourceAction.as_view()),
]
