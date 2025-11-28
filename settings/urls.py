from django.urls import path
from logic import views

app_name = 'logic'
urlpatterns = [
    path('', views.dashboard, name='home'),
    path('register', views.register, name='register'),
    path('login', views.login, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('resetbalance',views.resetbalance,name='resetbalance'),

    # API endpoints
    path('addcash/', views.addcash, name='addcash'),
    path('api/verify', views.verify_card, name='verify_card'),
    path('api/gethistory', views.gethistory, name='gethistory'),
    path('withdrawcash/', views.withdrawcash, name='withdrawcash'),
    path('refund/<int:order_id>/', views.refund, name='refund'),

    path('support/', views.user_support_chat, name='user_support'),
    path('admindashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admindashboard/chat/<int:chat_id>/', views.admin_chat_view, name='admin_chat'),
    path('admindashboard/close/<int:chat_id>/', views.close_chat, name='close_chat'),
]
