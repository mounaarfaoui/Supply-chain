from django.contrib import admin
from .models import Game, Actor, Turn, ActorAction

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'current_turn', 'total_turns', 'created_at')
    list_filter = ('status',)
    search_fields = ('id',)

@admin.register(Actor)
class ActorAdmin(admin.ModelAdmin):
    list_display = ('role', 'game', 'stock', 'backlog', 'total_cost')
    list_filter = ('role', 'game')
    search_fields = ('role',)

@admin.register(Turn)
class TurnAdmin(admin.ModelAdmin):
    list_display = ('game', 'turn_number', 'customer_demand', 'created_at')
    list_filter = ('game',)
    search_fields = ('game__id',)

@admin.register(ActorAction)
class ActorActionAdmin(admin.ModelAdmin):
    list_display = ('actor', 'turn', 'order_quantity', 'shipped_quantity', 'cost_incurred')
    list_filter = ('actor', 'turn__game')
    search_fields = ('actor__role',)

