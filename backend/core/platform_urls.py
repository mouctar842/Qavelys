from django.urls import path
from . import platform_views as views

urlpatterns = [path('overview/', views.Overview.as_view()), path('companies/', views.Companies.as_view()),
    path('users/', views.Users.as_view()), path('modules/', views.Modules.as_view()), path('audit/', views.Audit.as_view())]
for action in ('suspend', 'activate'):
    urlpatterns.append(path(f'companies/<uuid:pk>/{action}/', views.CompanyAction.as_view(), {'action': action}))
for action in ('deactivate', 'activate'):
    urlpatterns.append(path(f'users/<uuid:pk>/{action}/', views.UserAction.as_view(), {'action': action}))
