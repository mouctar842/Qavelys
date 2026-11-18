from django.urls import path
from .views import ActivitiesView, ActivityAction, LeadAction, LeadDetail, LeadHistory, LeadsView, Lookups

urlpatterns = [
    path('leads/', LeadsView.as_view()), path('leads/<uuid:pk>/', LeadDetail.as_view()),
    path('leads/<uuid:pk>/history/', LeadHistory.as_view()), path('leads/<uuid:pk>/<str:action>/', LeadAction.as_view()),
    path('activities/', ActivitiesView.as_view()), path('activities/<uuid:pk>/<str:action>/', ActivityAction.as_view()),
    path('lookups/', Lookups.as_view()),
]
