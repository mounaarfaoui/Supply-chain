from django.urls import path
from . import views

urlpatterns = [
    path('auth/', views.auth_portal, name='auth_portal'),
    path('login/<str:role>/', views.login_role, name='login_role'),
    path('signup/<str:role>/', views.signup_role, name='signup_role'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.auth_portal, name='entry'),
    path('home/', views.home, name='home'),
    path('room/', views.game_room, name='game_room'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('next/', views.next_turn, name='next_turn'),
    path('auto-simulate/', views.auto_simulate, name='auto_simulate'),
    path('reset/', views.reset_game, name='reset_game'),
    path('api/state/', views.api_game_state, name='api_state'),
]