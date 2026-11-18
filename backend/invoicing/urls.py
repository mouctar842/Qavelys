from django.urls import path
from . import views
from . import payment_views as payments
from .pdf_views import FinancialPdf

urlpatterns = [path('lookups/', views.Lookups.as_view()), path('history/', views.History.as_view())]
urlpatterns += [path('payments/', payments.Payments.as_view()), path('payments/lookups/', payments.Lookups.as_view()), path('payments/allocations/<uuid:pk>/reverse/', payments.Reverse.as_view()), path('payments/<uuid:pk>/', payments.Detail.as_view()), path('payments/<uuid:pk>/invoices/', payments.PaymentInvoices.as_view()), path('payments/<uuid:pk>/history/', payments.History.as_view()), path('payments/<uuid:pk>/<str:action>/', payments.Action.as_view())]
for kind in ['invoices', 'credit-notes']:
    urlpatterns += [path(f'{kind}/<uuid:pk>/pdf/', FinancialPdf.as_view(), {'kind': kind})]
    urlpatterns += [path(f'{kind}/', views.DocumentList.as_view(), {'kind': kind}), path(f'{kind}/<uuid:pk>/', views.DocumentDetail.as_view(), {'kind': kind}), path(f'{kind}/<uuid:pk>/<str:action>/', views.DocumentAction.as_view(), {'kind': kind})]
