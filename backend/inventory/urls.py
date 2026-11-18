from django.urls import path
from . import views
from . import fulfillment_views as fulfillment

urlpatterns = []
for kind in ['deliveries', 'receipts']:
    urlpatterns += [path(f'{kind}/', fulfillment.DocumentList.as_view(), {'kind': kind}), path(f'{kind}/lookups/', fulfillment.DocumentLookups.as_view(), {'kind': kind}), path(f'{kind}/<uuid:pk>/', fulfillment.DocumentDetail.as_view(), {'kind': kind}), path(f'{kind}/<uuid:pk>/<str:action>/', fulfillment.DocumentAction.as_view(), {'kind': kind})]
urlpatterns += [path('lookups/', views.Lookups.as_view()), path('<slug:resource>/', views.ResourceList.as_view()), path('<slug:resource>/<uuid:pk>/', views.ResourceDetail.as_view()), path('<slug:resource>/<uuid:pk>/<str:action>/', views.ResourceAction.as_view())]
