from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/support/(?P<chat_id>\d+)/$', consumers.SupportChatConsumer.as_asgi()),
    re_path(r'ws/admin/dashboard/$', consumers.AdminDashboardConsumer.as_asgi()),
]