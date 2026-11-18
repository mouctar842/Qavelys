from django.urls import path
from .views import RulesView, RuleAction, RuleLookups, RequestsView, DecisionView
urlpatterns = [path('rules/', RulesView.as_view()), path('rules/<uuid:pk>/update/', RuleAction.as_view()), path('lookups/', RuleLookups.as_view()), path('requests/', RequestsView.as_view()), path('requests/<uuid:pk>/decide/', DecisionView.as_view())]
