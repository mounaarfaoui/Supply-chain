from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.http import JsonResponse
from django.shortcuts import redirect, render

from .models import Actor, ActorAction, Game, OrderSubmission, Turn

import secrets
import random
import statistics


ROLE_ORDER = ["client", "detaillant", "grossiste", "distributeur", "usine"]
SUPPLY_CHAIN_ROLES = ["detaillant", "grossiste", "distributeur", "usine"]


def generate_room_code(length=6):
    """Generate a short shareable room code."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_unique_room_code():
    """Generate a room code that is unique in the Game table."""
    for _ in range(20):
        code = generate_room_code()
        if not Game.objects.filter(room_code=code).exists():
            return code
    return f"ROOM{secrets.token_hex(3).upper()}"


def get_or_create_game():
    """Get active game or create new one."""
    game = Game.objects.filter(status="active").first()
    if not game:
        game = Game.objects.create(
            status="active",
            room_code=generate_unique_room_code(),
            current_turn=0,
            total_turns=52,
        )
        init_game(game)
    elif not game.room_code:
        game.room_code = generate_unique_room_code()
        game.save(update_fields=["room_code"])
    return game


def init_game(game):
    """Initialize all actors."""
    Actor.objects.filter(game=game).delete()

    for role in ROLE_ORDER:
        Actor.objects.create(
            game=game,
            role=role,
            stock=0 if role == "client" else 15,
            backlog=0,
            total_cost=0,
            incoming_step_1=0,
            incoming_step_2=0,
            last_order=5,
        )


def get_ordered_actors(game):
    """Return actors in the desired supply-chain order."""
    role_order = {role: idx for idx, role in enumerate(ROLE_ORDER)}
    actors = list(Actor.objects.filter(game=game))
    return sorted(actors, key=lambda actor: role_order.get(actor.role, 999))


def get_supply_chain_actors(game):
    """Return only the 4 supply-chain actors (excluding client)."""
    actors = [actor for actor in get_ordered_actors(game) if actor.role in SUPPLY_CHAIN_ROLES]
    return actors


def ensure_role_groups():
    """Create role groups if they don't exist."""
    for role in ROLE_ORDER:
        Group.objects.get_or_create(name=role)


def get_user_role(user):
    """Resolve actor role from Django groups."""
    if not user.is_authenticated:
        return None

    groups = set(user.groups.values_list("name", flat=True))
    for role in ROLE_ORDER:
        if role in groups:
            return role
    return None


def get_actor_for_role(game, role):
    """Return the actor matching one role in the active game."""
    if not role:
        return None
    return Actor.objects.filter(game=game, role=role).first()


def find_user_for_identifier(identifier):
    """Find a user by username or email, ignoring case."""
    normalized = (identifier or "").strip()
    if not normalized:
        return None

    user = User.objects.filter(username__iexact=normalized).first()
    if user:
        return user
    return User.objects.filter(email__iexact=normalized).first()


def get_demand(turn_number):
    """Generate variable customer demand with phase-based trend + randomness."""
    if turn_number <= 4:
        base = 5
        noise = random.randint(-1, 1)
    elif turn_number <= 10:
        base = 8
        noise = random.randint(-2, 2)
    else:
        base = 5
        noise = random.randint(-2, 2)
    return max(0, base + noise)


def order_noise(role):
    """Role-specific random variation in orders."""
    amplitudes = {
        "detaillant": 2,
        "grossiste": 3,
        "distributeur": 4,
        "usine": 3,
    }
    amplitude = amplitudes.get(role, 2)
    return random.randint(-amplitude, amplitude)


def get_retailer_forecast(game, window=4):
    """Forecast retailer demand using a moving average of recent customer demand."""
    recent_turns = list(Turn.objects.filter(game=game).order_by("-turn_number")[:window])
    if not recent_turns:
        return {"forecast": 5, "history": [], "method": "moyenne mobile", "window": 0}

    recent_turns.reverse()
    demands = [turn.customer_demand for turn in recent_turns]
    forecast = int(round(statistics.mean(demands)))
    forecast = max(0, min(get_actor_policy("client")["max_order"], forecast))

    return {
        "forecast": forecast,
        "method": "moyenne mobile",
        "window": len(recent_turns),
        "history": [
            {
                "turn": turn.turn_number,
                "demand": turn.customer_demand,
            }
            for turn in recent_turns
        ],
    }


def get_actor_policy(role):
    """Decision parameters per role."""
    policies = {
        "client": {
            "max_order": 60,
        },
        "detaillant": {
            "target_stock": 10,
            "reserve_stock": 1,
            "smoothing": 0.65,
            "max_order": 30,
        },
        "grossiste": {
            "target_stock": 12,
            "reserve_stock": 2,
            "smoothing": 0.60,
            "max_order": 35,
        },
        "distributeur": {
            "target_stock": 14,
            "reserve_stock": 3,
            "smoothing": 0.55,
            "max_order": 40,
        },
        "usine": {
            "target_stock": 16,
            "reserve_stock": 4,
            "smoothing": 0.55,
            "max_order": 45,
            "max_production": 45,
        },
    }
    return policies.get(role, policies["grossiste"])


def decide_shipment(actor, demand):
    """Actor decides how much to ship to downstream."""
    policy = get_actor_policy(actor.role)
    total_demand = actor.backlog + demand
    if total_demand <= 0:
        return 0

    reserve_stock = policy["reserve_stock"]
    max_without_breaking_reserve = max(0, actor.stock - reserve_stock)
    service_target = int(round(total_demand * 0.9))
    shipment = min(total_demand, max(service_target, max_without_breaking_reserve))
    return max(0, min(shipment, actor.stock))


def decide_order(actor, perceived_demand):
    """Actor decides how much to order from upstream."""
    policy = get_actor_policy(actor.role)
    inventory_position = actor.stock + actor.incoming_step_1 + actor.incoming_step_2 - actor.backlog
    smoothing = policy["smoothing"]
    demand_signal = smoothing * perceived_demand + (1 - smoothing) * actor.last_order
    desired = demand_signal + (policy["target_stock"] - inventory_position) + order_noise(actor.role)
    return max(0, min(policy["max_order"], int(round(desired))))


def decide_factory_production(factory, upstream_order):
    """Factory decides production quantity based on orders and inventory state."""
    policy = get_actor_policy("usine")
    inventory_position = (
        factory.stock + factory.incoming_step_1 + factory.incoming_step_2 - factory.backlog
    )
    smoothing = policy["smoothing"]
    demand_signal = smoothing * upstream_order + (1 - smoothing) * factory.last_order
    desired = demand_signal + (policy["target_stock"] - inventory_position) + order_noise("usine")
    return max(0, min(policy["max_production"], int(round(desired))))


def get_lagged_orders(game, turn_number, delay=2):
    """Return downstream orders seen by upstream after an information delay."""
    observed_turn = turn_number - delay
    default_orders = {
        "detaillant": 5,
        "grossiste": 5,
        "distributeur": 5,
    }
    if observed_turn <= 0:
        return default_orders

    lagged = default_orders.copy()
    actions = ActorAction.objects.filter(turn__game=game, turn__turn_number=observed_turn)
    for action in actions:
        role = action.actor.role
        if role in lagged:
            lagged[role] = action.order_quantity
    return lagged


def simulate_turn(game, manual_orders=None):
    """Execute one complete turn of the simulation."""
    turn_number = game.current_turn + 1
    if manual_orders and "client" in manual_orders:
        customer_demand = max(0, min(get_actor_policy("client")["max_order"], int(manual_orders["client"])))
    else:
        customer_demand = get_demand(turn_number)

    turn = Turn.objects.create(
        game=game,
        turn_number=turn_number,
        customer_demand=customer_demand,
    )

    actors = get_supply_chain_actors(game)

    client_actor = Actor.objects.filter(game=game, role="client").first()
    if client_actor:
        client_actor.last_order = customer_demand
        client_actor.save(update_fields=["last_order"])

    for actor in actors:
        actor.stock += actor.incoming_step_1
        actor.incoming_step_1 = actor.incoming_step_2
        actor.incoming_step_2 = 0

    shipments = []
    lagged_orders = get_lagged_orders(game, turn_number, delay=2)
    demands = [
        customer_demand,
        lagged_orders["detaillant"],
        lagged_orders["grossiste"],
        lagged_orders["distributeur"],
    ]

    factory_production_qty = 0

    for i, actor in enumerate(actors):
        demand = demands[i]
        total_demand = actor.backlog + demand

        stock_before = actor.stock
        backlog_before = actor.backlog

        shipped = decide_shipment(actor, demand)
        actor.stock -= shipped
        actor.backlog = max(0, total_demand - shipped)

        shipments.append(shipped)

        manual_order = None
        if manual_orders and actor.role in manual_orders:
            manual_order = manual_orders[actor.role]

        if i < 3:
            if manual_order is None:
                order_qty = decide_order(actor, demand)
            else:
                max_order = get_actor_policy(actor.role)["max_order"]
                order_qty = max(0, min(max_order, int(manual_order)))
            actor.last_order = order_qty
        else:
            if manual_order is None:
                factory_production_qty = decide_factory_production(actor, demands[i])
            else:
                max_production = get_actor_policy("usine")["max_production"]
                factory_production_qty = max(0, min(max_production, int(manual_order)))
            order_qty = factory_production_qty
            actor.last_order = factory_production_qty

        inventory_cost = max(0, actor.stock) * 0.5
        backlog_cost = actor.backlog * 2
        cost_incurred = inventory_cost + backlog_cost
        actor.total_cost += cost_incurred

        ActorAction.objects.create(
            turn=turn,
            actor=actor,
            order_quantity=order_qty,
            shipped_quantity=shipped,
            stock_before=stock_before,
            stock_after=actor.stock,
            backlog_before=backlog_before,
            backlog_after=actor.backlog,
            cost_incurred=cost_incurred,
        )
        actor.save()

    for i in range(len(actors) - 1):
        actors[i].incoming_step_2 += shipments[i + 1]

    actors[3].incoming_step_2 += factory_production_qty

    for actor in actors:
        actor.save()

    game.current_turn = turn_number
    if turn_number >= game.total_turns:
        game.status = "ended"
    game.save()

    return turn


def auth_portal(request):
    """Entry page for role-based login/signup."""
    ensure_role_groups()
    game = get_or_create_game()

    role_infos = []
    role_labels = dict(Actor.ROLE_CHOICES)
    for role in ROLE_ORDER:
        role_infos.append(
            {
                "role": role,
                "label": role_labels.get(role, role),
            }
        )

    return render(request, "game/auth_portal.html", {"role_infos": role_infos, "game": game})


def signup_role(request, role):
    """Create a user account assigned to one actor role."""
    ensure_role_groups()
    if role not in ROLE_ORDER:
        messages.error(request, "Role invalide.")
        return redirect("auth_portal")

    actor_label = dict(Actor.ROLE_CHOICES).get(role, role)
    error = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "").strip()

        if not email or not password:
            error = "Email et mot de passe obligatoires."
        else:
            existing_user = find_user_for_identifier(email)

            if existing_user is None:
                user = User.objects.create_user(username=email, email=email, password=password)
                user.groups.clear()
                user.groups.add(Group.objects.get(name=role))
                login(request, user)
                messages.success(request, f"Compte cree pour {actor_label}.")
                return redirect("home")

            authenticated_user = authenticate(request, username=existing_user.username, password=password)
            if authenticated_user is None:
                error = "Creation impossible. Veuillez verifier votre email et votre mot de passe."
            else:
                authenticated_user.groups.add(Group.objects.get(name=role))
                login(request, authenticated_user)
                messages.success(request, f"Connexion effectuee pour {actor_label}.")
                return redirect("home")

    return render(request, "game/signup.html", {"actor": actor_label, "role": role, "error": error})


def login_role(request, role):
    """Authenticate a user for one actor role."""
    ensure_role_groups()
    if role not in ROLE_ORDER:
        messages.error(request, "Role invalide.")
        return redirect("auth_portal")

    actor_label = dict(Actor.ROLE_CHOICES).get(role, role)
    error = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "").strip()
        user = find_user_for_identifier(email)

        if not email or not password:
            error = "Email et mot de passe obligatoires."
        elif user is None:
            error = "Aucun compte trouve pour cet email."
        else:
            user = authenticate(request, username=user.username, password=password)

            if user is None:
                error = "Mot de passe incorrect."
            elif not user.groups.filter(name=role).exists():
                error = f"Ce compte n'appartient pas au role {actor_label}."
            else:
                login(request, user)
                messages.success(request, f"Connecte en tant que {actor_label}.")
                return redirect("home")

    return render(request, "game/login.html", {"actor": actor_label, "error": error})


def logout_view(request):
    """End user session."""
    logout(request)
    messages.info(request, "Vous etes deconnecte.")
    return redirect("auth_portal")


@login_required(login_url="auth_portal")
def home(request):
    """Private dashboard for the current player role."""
    game = get_or_create_game()
    current_role = get_user_role(request.user)
    if not current_role:
        messages.error(request, "Aucun role associe a votre compte.")
        return redirect("auth_portal")

    current_actor = get_actor_for_role(game, current_role)
    if not current_actor:
        messages.error(request, "Votre acteur n'est pas encore initialise dans la partie.")
        return redirect("auth_portal")

    retailer_forecast = get_retailer_forecast(game)

    turns = Turn.objects.filter(game=game).order_by("-turn_number")[:10]
    pending_turn = game.current_turn + 1
    pending_submission = OrderSubmission.objects.filter(
        game=game,
        turn_number=pending_turn,
        actor=current_actor,
    ).first()
    submitted_count = OrderSubmission.objects.filter(game=game, turn_number=pending_turn).count()

    latest_action = ActorAction.objects.filter(actor=current_actor).order_by("-turn__turn_number").first()
    current_actor.last_shipment_decision = latest_action.shipped_quantity if latest_action else 0
    current_actor.submitted_count = submitted_count
    current_actor.pending_submission = pending_submission
    current_actor.max_allowed = get_actor_policy(current_actor.role).get(
        "max_production",
        get_actor_policy(current_actor.role).get("max_order", 100),
    )
    if current_actor.role == "detaillant":
        current_actor.demand_forecast = retailer_forecast["forecast"]
        current_actor.demand_history = retailer_forecast["history"]
        current_actor.demand_forecast_method = retailer_forecast["method"]
        current_actor.demand_forecast_window = retailer_forecast["window"]

    progress_percent = (game.current_turn * 100 / game.total_turns) if game.total_turns else 0
    stats = {
        "total_cost": round(current_actor.total_cost, 2),
        "avg_stock": current_actor.stock,
        "total_backlog": current_actor.backlog,
    }

    return render(
        request,
        "game/home.html",
        {
            "game": game,
            "actor": current_actor,
            "current_role": current_role,
            "turns": list(reversed(turns)),
            "stats": stats,
            "progress_percent": progress_percent,
            "pending_turn": pending_turn,
            "pending_submission": pending_submission,
            "submitted_count": submitted_count,
            "total_roles": len(ROLE_ORDER),
            "remaining_players": max(0, len(ROLE_ORDER) - submitted_count),
        },
    )


@login_required(login_url="auth_portal")
def game_room(request):
    """Private room showing only the current player's submission state."""
    game = get_or_create_game()
    user_role = get_user_role(request.user)
    if not user_role:
        messages.error(request, "Aucun role associe a votre compte.")
        return redirect("auth_portal")

    role_labels = dict(Actor.ROLE_CHOICES)
    pending_turn = game.current_turn + 1
    submissions = OrderSubmission.objects.filter(game=game, turn_number=pending_turn).select_related("actor")
    own_submission = submissions.filter(actor__role=user_role).first()
    ready_count = submissions.count()
    current_actor = get_actor_for_role(game, user_role)

    return render(
        request,
        "game/game_room.html",
        {
            "game": game,
            "pending_turn": pending_turn,
            "current_role": user_role,
            "current_role_label": role_labels.get(user_role, user_role),
            "current_actor": current_actor,
            "own_submission": own_submission,
            "ready_count": ready_count,
            "total_roles": len(ROLE_ORDER),
            "remaining_players": max(0, len(ROLE_ORDER) - ready_count),
        },
    )


def dashboard(request):
    """Detailed statistics dashboard for the host only."""
    if not request.user.is_authenticated or not request.user.is_superuser:
        messages.info(request, "Le tableau de bord detaille est reserve a l'hote.")
        return redirect("home")

    game = get_or_create_game()
    actors = get_ordered_actors(game)

    actor_histories = {}
    for actor in actors:
        actions = ActorAction.objects.filter(actor=actor).order_by("turn__turn_number")
        actor_histories[actor.role] = {
            "name": actor.get_role_display(),
            "actions": actions,
            "total_cost": actor.total_cost,
        }

    turns = list(Turn.objects.filter(game=game).order_by("turn_number"))
    turn_labels = [turn.turn_number for turn in turns]
    customer_demands = [turn.customer_demand for turn in turns]

    role_names = {
        "detaillant": "Retailer",
        "grossiste": "Wholesaler",
        "distributeur": "Distributor",
        "usine": "Factory",
    }

    orders_by_role = {}
    stock_by_role = {}
    for role in SUPPLY_CHAIN_ROLES:
        role_actions = list(
            ActorAction.objects.filter(turn__game=game, actor__role=role).order_by("turn__turn_number")
        )
        orders_by_role[role] = [action.order_quantity for action in role_actions]
        stock_by_role[role] = [action.stock_after for action in role_actions]

    bullwhip_by_role = {}
    for role in SUPPLY_CHAIN_ROLES:
        series = []
        role_orders = orders_by_role.get(role, [])
        for idx, demand in enumerate(customer_demands):
            order_qty = role_orders[idx] if idx < len(role_orders) else 0
            ratio = (order_qty / demand) if demand > 0 else 0
            series.append(round(ratio, 2))
        bullwhip_by_role[role] = series

    dashboard_chart_data = {
        "turn_labels": turn_labels,
        "actor_names": role_names,
        "role_order": SUPPLY_CHAIN_ROLES,
        "costs": {actor.role: round(actor.total_cost, 2) for actor in actors},
        "stock_by_role": stock_by_role,
        "bullwhip_by_role": bullwhip_by_role,
    }

    return render(
        request,
        "game/dashboard.html",
        {
            "game": game,
            "actor_histories": actor_histories,
            "total_turns": range(1, game.current_turn + 1),
            "dashboard_chart_data": dashboard_chart_data,
        },
    )


def next_turn(request):
    """Store the current player's decision and advance when all roles have submitted."""
    game = get_or_create_game()
    current_role = get_user_role(request.user)

    if not current_role:
        messages.error(request, "Aucun role associe a votre compte.")
        return redirect("auth_portal")

    if request.method != "POST":
        messages.info(request, "Utilisez le formulaire pour saisir votre commande.")
        return redirect("home")

    if game.status != "active":
        messages.warning(request, "La partie est terminee. Lancez une nouvelle partie.")
        return redirect("home")

    current_actor = get_actor_for_role(game, current_role)
    if not current_actor:
        messages.error(request, "Votre acteur n'est pas disponible dans la partie.")
        return redirect("home")

    field_name = f"order_{current_role}"
    raw_value = request.POST.get(field_name, "").strip()

    if raw_value == "":
        messages.error(request, f"Valeur manquante pour {current_actor.get_role_display()}.")
        return redirect("home")

    try:
        qty = int(raw_value)
    except ValueError:
        messages.error(request, f"Valeur invalide pour {current_actor.get_role_display()} (entier requis).")
        return redirect("home")

    if qty < 0:
        messages.error(request, f"Valeur invalide pour {current_actor.get_role_display()} (>= 0).")
        return redirect("home")

    policy = get_actor_policy(current_role)
    max_allowed = policy.get("max_production", policy.get("max_order", 100))
    qty = min(qty, max_allowed)

    pending_turn = game.current_turn + 1
    OrderSubmission.objects.update_or_create(
        game=game,
        turn_number=pending_turn,
        actor=current_actor,
        defaults={
            "submitted_by": request.user,
            "order_quantity": qty,
        },
    )

    submissions = OrderSubmission.objects.filter(game=game, turn_number=pending_turn).select_related("actor")
    if submissions.count() == len(ROLE_ORDER):
        manual_orders = {submission.actor.role: submission.order_quantity for submission in submissions}
        simulate_turn(game, manual_orders=manual_orders)
        messages.success(request, "Toutes les decisions ont ete recues. Le tour a ete execute.")
    else:
        messages.success(request, "Votre decision a ete enregistree. En attente des autres joueurs.")
    return redirect("home")


def auto_simulate(request):
    """Disabled in manual-entry mode."""
    get_or_create_game()
    messages.info(
        request,
        "Le mode auto est desactive. Chaque acteur doit saisir sa commande a chaque tour.",
    )
    return redirect("home")


def reset_game(request):
    """Start a new game."""
    Game.objects.all().delete()
    get_or_create_game()
    messages.info(request, "Nouvelle partie initialisee.")
    return redirect("home")


def api_game_state(request):
    """API endpoint for game state."""
    game = get_or_create_game()
    user_role = get_user_role(request.user) if request.user.is_authenticated else None
    if request.user.is_authenticated and request.user.is_superuser:
        actors = Actor.objects.filter(game=game)
    elif user_role:
        actors = Actor.objects.filter(game=game, role=user_role)
    else:
        actors = Actor.objects.none()

    return JsonResponse(
        {
            "current_turn": game.current_turn,
            "total_turns": game.total_turns,
            "status": game.status,
            "role": user_role,
            "actors": [
                {
                    "role": a.role,
                    "stock": a.stock,
                    "backlog": a.backlog,
                    "total_cost": a.total_cost,
                }
                for a in actors
            ],
        }
    )
