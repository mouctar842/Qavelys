from django.urls import path
from .views import Action, Detail, Listing, Lookups

urlpatterns = [path('lookups/', Lookups.as_view()), path('<str:resource>/', Listing.as_view()), path('<str:resource>/<uuid:pk>/', Detail.as_view()), path('<str:resource>/<uuid:pk>/<str:action>/', Action.as_view())]
