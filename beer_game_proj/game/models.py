from django.db import models
from django.contrib.auth.models import User

class Game(models.Model):
    """Track game state"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('ended', 'Ended'),
    ]
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    room_code = models.CharField(max_length=12, unique=True, null=True, blank=True)
    current_turn = models.IntegerField(default=0)
    total_turns = models.IntegerField(default=52)  # 52 weeks
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Game {self.id} - Turn {self.current_turn}/{self.total_turns}"


class Actor(models.Model):
    """Supply chain actors: Retailer, Distributor, Wholesaler, Factory"""
    ROLE_CHOICES = [
        ('client', 'Client'),
        ('detaillant', 'Retailer'),
        ('distributeur', 'Distributor'),
        ('grossiste', 'Wholesaler'),
        ('usine', 'Factory'),
    ]
    
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='actors')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    
    stock = models.IntegerField(default=15)
    backlog = models.IntegerField(default=0)
    total_cost = models.FloatField(default=0)
    
    # Shipments in transit (delays simulation)
    incoming_step_1 = models.IntegerField(default=0)  # Arrives next turn
    incoming_step_2 = models.IntegerField(default=0)  # Arrives in 2 turns
    
    # For order history
    last_order = models.IntegerField(default=4)
    
    def __str__(self):
        return f"{self.get_role_display()} - Game {self.game_id}"


class Turn(models.Model):
    """Track each turn of the game"""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='turns')
    turn_number = models.IntegerField()
    
    # Demand from customer (only for retailer)
    customer_demand = models.IntegerField(default=5)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['turn_number']
    
    def __str__(self):
        return f"Game {self.game_id} - Turn {self.turn_number}"


class ActorAction(models.Model):
    """Track what each actor ordered in each turn"""
    turn = models.ForeignKey(Turn, on_delete=models.CASCADE, related_name='actions')
    actor = models.ForeignKey(Actor, on_delete=models.CASCADE)
    
    order_quantity = models.IntegerField(default=0)
    shipped_quantity = models.IntegerField(default=0)
    stock_before = models.IntegerField(default=0)
    stock_after = models.IntegerField(default=0)
    backlog_before = models.IntegerField(default=0)
    backlog_after = models.IntegerField(default=0)
    cost_incurred = models.FloatField(default=0)
    
    def __str__(self):
        return f"{self.actor} - Turn {self.turn.turn_number}"


class OrderSubmission(models.Model):
    """Store each actor's manual order for a specific upcoming turn."""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='order_submissions')
    actor = models.ForeignKey(Actor, on_delete=models.CASCADE, related_name='order_submissions')
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order_submissions')
    turn_number = models.IntegerField()
    order_quantity = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['game', 'turn_number', 'actor'],
                name='unique_submission_per_actor_per_turn',
            )
        ]
        ordering = ['turn_number', 'actor__role']

    def __str__(self):
        return f"Submission G{self.game_id} T{self.turn_number} {self.actor.role}: {self.order_quantity}"