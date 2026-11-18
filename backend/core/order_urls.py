from django.urls import path
from .order_views import OrdersView, OrderDetail, OrderAction, OrderLookups, OrderHistory
urlpatterns = [path('orders/', OrdersView.as_view()), path('orders/<uuid:pk>/', OrderDetail.as_view()), path('orders/<uuid:pk>/history/', OrderHistory.as_view()), path('orders/<uuid:pk>/<str:action>/', OrderAction.as_view()), path('lookups/', OrderLookups.as_view())]
