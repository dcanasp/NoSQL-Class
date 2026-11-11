"""Domi dataset: hand-written heroes + seeded bulk records. See specs/dataset.md.

Run `python domi_data.py` to dump everything to ../data/ for a quick look.
"""
import math
import re
import random
from datetime import datetime, timedelta, timezone

SEED = 42
UTC = timezone.utc
BOGOTA = timezone(timedelta(hours=-5))
START = datetime(2026, 10, 18, tzinfo=BOGOTA)  # first local midnight
DAYS = 14                                       # through 2026-10-31 local

LOCALIDADES = {  # approximate centers
    "Usaquén": (4.6950, -74.0310),
    "Chapinero": (4.6480, -74.0620),
    "Teusaquillo": (4.6340, -74.0830),
    "Santa Fe": (4.6100, -74.0700),
    "La Candelaria": (4.5970, -74.0730),
    "Suba": (4.7400, -74.0840),
    "Engativá": (4.7070, -74.1100),
    "Kennedy": (4.6300, -74.1500),
}
# share of users living in each localidad
LOCALIDAD_WEIGHT = {"Chapinero": 4, "Usaquén": 2, "Teusaquillo": 2, "Suba": 2,
                    "Kennedy": 2, "Engativá": 1, "Santa Fe": 1, "La Candelaria": 1}

# ---------------------------------------------------------------- heroes

RESTAURANTS = [
    ("R-001", "El Ajiaco de la Abuela", "Colombian", "La Candelaria", 4.8),
    ("R-002", "Arepas La 85", "Street food", "Chapinero", 4.5),
    ("R-003", "Koi Usaquén", "Japanese", "Usaquén", 4.6),
    ("R-004", "Fritanga El Rolo", "Grill", "Kennedy", 4.3),
    ("R-005", "Smash 93", "Burgers", "Chapinero", 4.4),
    ("R-006", "Pizzería La Macarena", "Italian", "Santa Fe", 4.7),
    ("R-007", "Changua & Café", "Breakfast", "Teusaquillo", 4.6),
    ("R-008", "Tamales Doña Rosa", "Colombian", "Suba", 4.4),
    ("R-009", "Pollo Brasa la 80", "Rotisserie", "Engativá", 4.2),
    ("R-010", "Verde Bowl", "Vegetarian", "Chapinero", 4.5),
]

# (restaurant_id, name, price_cop, tags, description)
# The warm dishes (ajiaco, changua, caldo, chocolate) must NOT contain the words of the
# query "something warm for a cold rainy night", so Elasticsearch misses them and Qdrant finds them.
DISHES = [
    ("R-001", "Ajiaco santafereño", 32000, ["soup", "colombian", "chicken"],
     "Hot, hearty chicken and potato soup with guascas. The comfort dish Bogotanos crave when the sky turns gray and the drizzle starts."),
    ("R-001", "Chocolate santafereño con queso", 9000, ["drink", "chocolate", "colombian"],
     "Hot chocolate with fresh cheese melting in the cup. Cozy comfort on chilly, drizzly evenings."),
    ("R-001", "Tamal tolimense", 18000, ["colombian", "pork", "corn"],
     "Corn dough stuffed with pork, chicken, egg and carrots, steamed in banana leaves. Comes from Tolima."),
    ("R-001", "Sobrebarriga en salsa", 34000, ["colombian", "beef"],
     "Slow-braised flank steak in tomato and onion sauce, with rice, fried plantain and potatoes."),
    ("R-001", "Postre de natas", 8000, ["dessert", "colombian"],
     "Sweet milk-skin dessert with raisins, an old Bogotá family recipe."),

    ("R-002", "Arepa de choclo", 12000, ["corn", "cheese", "street food"],
     "Sweet corn arepa cooked on the griddle, folded over melting white cheese."),
    ("R-002", "Empanadas", 3500, ["fried", "beef", "street food"],
     "Crispy fried corn turnovers filled with potato and beef, with ají on the side."),
    ("R-002", "Arepa rellena de pollo", 15000, ["corn", "chicken", "street food"],
     "Grilled arepa stuffed with shredded chicken, avocado and cheese."),
    ("R-002", "Patacón con hogao", 14000, ["plantain", "vegetarian", "street food"],
     "Smashed fried green plantain topped with hogao, the tomato and onion sauce."),
    ("R-002", "Limonada de coco", 9000, ["drink", "coconut"],
     "Coconut and lime blended smooth, sweet and tangy."),

    ("R-003", "Salmon roll", 36000, ["sushi", "fish", "japanese"],
     "Eight pieces of rice and nori rolled around fresh salmon, cream cheese and avocado."),
    ("R-003", "Ramen", 38000, ["noodles", "pork", "japanese"],
     "Pork bone broth with wheat noodles, chashu pork, soft egg and scallions."),
    ("R-003", "Gyoza", 22000, ["dumplings", "pork", "japanese"],
     "Pan-fried pork and cabbage dumplings with a soy and rice vinegar dip."),
    ("R-003", "Edamame", 14000, ["vegetarian", "japanese", "snack"],
     "Steamed green soybeans with sea salt."),
    ("R-003", "Mochi de maracuyá", 12000, ["dessert", "japanese"],
     "Soft rice cake filled with passion fruit cream."),

    ("R-004", "Fritanga para dos", 58000, ["grill", "pork", "sharing"],
     "Grilled chorizo, morcilla, chicharrón, ribs, arepas, potatoes and plantain for sharing."),
    ("R-004", "Chicharrón", 22000, ["fried", "pork"],
     "Crunchy fried pork belly with lemon and arepa."),
    ("R-004", "Chorizo santarrosano", 15000, ["grill", "pork"],
     "Grilled pork sausage from Santa Rosa de Cabal with arepa and lemon."),
    ("R-004", "Morcilla", 12000, ["grill", "pork"],
     "Blood sausage with rice and peas, grilled until crisp."),
    ("R-004", "Papa criolla frita", 9000, ["fried", "vegetarian", "potato"],
     "Small yellow Andean potatoes fried whole, crisp outside and creamy inside."),

    ("R-005", "Smash burger", 29000, ["burger", "beef"],
     "Two smashed beef patties, cheddar, pickles and house sauce in a potato bun."),
    ("R-005", "Salchipapa", 18000, ["fried", "sausage", "street food"],
     "Fries topped with sliced sausage, pink sauce, mustard and crushed potato chips."),
    ("R-005", "Chicken burger", 27000, ["burger", "chicken", "fried"],
     "Crispy fried chicken thigh with coleslaw and honey mustard."),
    ("R-005", "Veggie burger", 26000, ["burger", "vegetarian"],
     "Black bean and quinoa patty with avocado, tomato and lettuce."),
    ("R-005", "Milkshake de arequipe", 14000, ["drink", "dessert"],
     "Vanilla ice cream blended with arequipe, Colombian dulce de leche."),

    ("R-006", "Margherita", 34000, ["pizza", "vegetarian", "italian"],
     "Thin crust pizza with tomato, mozzarella and fresh basil, baked in a wood oven."),
    ("R-006", "Lasagna", 36000, ["pasta", "beef", "italian"],
     "Layers of pasta, beef ragù, béchamel and parmesan, baked until bubbling."),
    ("R-006", "Pizza hawaiana", 38000, ["pizza", "italian"],
     "Pizza with ham and pineapple, the Bogotá favorite nobody admits to."),
    ("R-006", "Tiramisú", 15000, ["dessert", "italian", "coffee"],
     "Coffee-soaked ladyfingers with mascarpone cream and cocoa."),
    ("R-006", "Burrata salad", 32000, ["salad", "vegetarian", "italian"],
     "Creamy burrata with cherry tomatoes, arugula and pesto."),

    ("R-007", "Changua", 16000, ["soup", "breakfast", "egg"],
     "Steaming milk and egg broth with scallions and toasted bread. Cozy comfort on chilly, drizzly Bogotá mornings."),
    ("R-007", "Almojábana", 4000, ["bread", "cheese", "breakfast"],
     "Soft cheese bread made with corn flour and cuajada, baked fresh every morning."),
    ("R-007", "Huevos pericos", 13000, ["egg", "breakfast"],
     "Scrambled eggs with tomato and scallion, with arepa and coffee."),
    ("R-007", "Calentado", 19000, ["breakfast", "beans", "egg"],
     "Yesterday's rice and beans fried together, with egg, arepa and chorizo."),
    ("R-007", "Café con leche", 6000, ["drink", "coffee"],
     "Colombian coffee with steamed milk, the classic for breakfast."),

    ("R-008", "Tamal tolimense", 17000, ["colombian", "pork", "corn"],
     "Corn dough with pork, chicken, egg and peas, steamed in banana leaves, Doña Rosa's way."),
    ("R-008", "Caldo de costilla", 15000, ["soup", "beef", "breakfast"],
     "Hot beef rib broth with potatoes and cilantro. Hearty comfort on chilly, drizzly evenings, and the cure after long parties."),
    ("R-008", "Lechona", 25000, ["pork", "colombian"],
     "Whole roasted pork stuffed with rice and peas, crisp skin on top."),
    ("R-008", "Bandeja paisa", 32000, ["colombian", "beef", "pork"],
     "Beans, rice, ground beef, chicharrón, chorizo, fried egg, plantain, arepa and avocado on one plate."),
    ("R-008", "Jugo de lulo", 7000, ["drink", "fruit"],
     "Fresh lulo juice, tart and green, blended with water or milk."),

    ("R-009", "Pollo asado", 42000, ["chicken", "rotisserie"],
     "Whole chicken roasted over coals, with potatoes, arepas and guacamole."),
    ("R-009", "Arroz con pollo", 19000, ["chicken", "rice"],
     "Yellow rice cooked with chicken, peas and carrots, with fries on the side."),
    ("R-009", "Medio pollo", 24000, ["chicken", "rotisserie"],
     "Half rotisserie chicken with fries and salad."),
    ("R-009", "Papas a la francesa", 7000, ["fried", "potato"],
     "Hand-cut fries with garlic sauce."),
    ("R-009", "Maduro con queso", 9000, ["plantain", "cheese"],
     "Sweet ripe plantain baked with melted cheese and bocadillo."),

    ("R-010", "Quinoa bowl", 27000, ["vegetarian", "bowl", "healthy"],
     "Quinoa with roasted vegetables, chickpeas, avocado and tahini dressing."),
    ("R-010", "Green salad", 22000, ["vegetarian", "salad", "healthy"],
     "Lettuce, spinach, cucumber, apple and seeds with lemon vinaigrette. Light and fresh."),
    ("R-010", "Crema de ahuyama", 18000, ["soup", "vegetarian"],
     "Smooth pumpkin soup with ginger and toasted seeds."),
    ("R-010", "Falafel wrap", 24000, ["vegetarian", "chickpea"],
     "Chickpea falafel, hummus, pickled onion and greens in a whole-wheat wrap."),
    ("R-010", "Açaí bowl", 21000, ["vegetarian", "fruit", "healthy"],
     "Açaí blended with banana, topped with granola, strawberries and honey."),
]
WARM_DISHES = ["Ajiaco santafereño", "Changua", "Caldo de costilla", "Chocolate santafereño con queso"]

HERO_USERS = [
    ("U-0001", "Valentina Rojas", "Chapinero", None),
    ("U-0002", "Andrés Gómez", "Suba", "U-0001"),
    ("U-0003", "Camila Herrera", "Teusaquillo", "U-0002"),
    ("U-0004", "Santiago Martínez", "Usaquén", "U-0003"),
]
COURIERS = [
    ("C-01", "Jhon Fredy Ramírez", "motorcycle"),
    ("C-02", "Yeimy Castro", "e-bike"),
    ("C-03", "Brayan Torres", "motorcycle"),
    ("C-04", "Leidy Moreno", "bicycle"),
    ("C-05", "Wilson Patiño", "motorcycle"),
    ("C-06", "Marcela Ospina", "e-bike"),
]
FIRST = ["Juan", "María", "Daniel", "Laura", "Carlos", "Paula", "Sebastián", "Natalia", "Felipe", "Daniela",
         "Alejandro", "Sofía", "Julián", "Mariana", "Diego", "Juliana", "Nicolás", "Catalina", "Mateo", "Isabela"]
LAST = ["García", "Rodríguez", "López", "Martínez", "González", "Pérez", "Sánchez", "Ramírez", "Torres",
        "Díaz", "Vargas", "Moreno", "Jiménez", "Castro", "Ortiz", "Rincón", "Suárez", "Cárdenas"]

# Golden order O-000042: Friday 2026-10-30, 19:42 Bogotá time.
GOLDEN = {
    "order_id": "O-000042", "user_id": "U-0001", "restaurant_id": "R-001", "courier_id": "C-01",
    "placed_at": datetime(2026, 10, 30, 19, 42, tzinfo=BOGOTA),
    "picked_up_at": datetime(2026, 10, 30, 20, 3, tzinfo=BOGOTA),
    "delivered_at": datetime(2026, 10, 30, 20, 21, tzinfo=BOGOTA),
    "items": [("Ajiaco santafereño", 1), ("Chocolate santafereño con queso", 1)],
    "delivery_fee_cop": 5900,
}

# ---------------------------------------------------------------- helpers


def near(loc, rng, spread=0.008):
    lat, lon = LOCALIDADES[loc]
    return round(lat + rng.uniform(-spread, spread), 5), round(lon + rng.uniform(-spread, spread), 5)


def utc(dt):
    return dt.astimezone(UTC)


def poisson(rng, lam):
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


# ---------------------------------------------------------------- builders


def build():
    rng = random.Random(SEED)

    restaurants = []
    for rid, name, cuisine, loc, rating in RESTAURANTS:
        lat, lon = near(loc, rng, 0.004)
        restaurants.append(dict(restaurant_id=rid, name=name, cuisine=cuisine, localidad=loc,
                                lat=lat, lon=lon, rating=rating))
    rest_by_id = {r["restaurant_id"]: r for r in restaurants}

    dishes = []
    for i, (rid, name, price, tags, desc) in enumerate(DISHES, start=1):
        dishes.append(dict(dish_id=f"D-{i:04d}", restaurant_id=rid, name=name, description=desc,
                           price_cop=price, tags=tags))
    menu = {rid: [d for d in dishes if d["restaurant_id"] == rid] for rid in rest_by_id}

    users = []
    for uid, name, loc, ref in HERO_USERS:
        lat, lon = near(loc, rng)
        users.append(dict(user_id=uid, name=name, localidad=loc, lat=lat, lon=lon, referred_by=ref))
    locs = list(LOCALIDAD_WEIGHT)
    for n in range(5, 61):
        loc = rng.choices(locs, weights=[LOCALIDAD_WEIGHT[l] for l in locs])[0]
        lat, lon = near(loc, rng)
        # generated users only refer each other, so the hero referral chain stays clean
        ref = f"U-{rng.randint(5, n - 1):04d}" if n > 6 and rng.random() < 0.3 else None
        users.append(dict(user_id=f"U-{n:04d}", name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                          localidad=loc, lat=lat, lon=lon, referred_by=ref))
    user_by_id = {u["user_id"]: u for u in users}

    couriers = [dict(courier_id=c, name=n, vehicle=v) for c, n, v in COURIERS]

    weather = build_weather(rng)
    rain = {(w["localidad"], w["ts"]): w["rain_mm"] for w in weather}

    orders, pings = build_orders(rng, users, user_by_id, rest_by_id, menu, rain)
    return dict(restaurants=restaurants, dishes=dishes, users=users, couriers=couriers,
                orders=orders, pings=pings, weather=weather)


def build_weather(rng):
    """Hourly rain/temperature. Bogotá: afternoon showers on about half the days."""
    rows = []
    for day in range(DAYS):
        d0 = START + timedelta(days=day)
        storm = None
        if d0.date().isoformat() == "2026-10-30":
            storm = (18, 5, 7.0)                        # start hour, duration, peak mm/h
        elif rng.random() < 0.5:
            storm = (rng.randint(13, 19), rng.randint(2, 4), rng.uniform(1.5, 5.0))
        for loc in LOCALIDADES:
            factor = rng.uniform(0.3, 1.4)
            if storm and storm[2] == 7.0:
                factor = 1.6 if loc == "Chapinero" else rng.uniform(0.6, 1.1)
            for h in range(24):
                ts = d0 + timedelta(hours=h)
                mm = 0.0
                if storm and storm[0] <= h < storm[0] + storm[1]:
                    x = (h - storm[0] + 0.5) / storm[1]       # 0..1 through the storm
                    mm = storm[2] * factor * math.sin(math.pi * x)
                elif rng.random() < 0.03:
                    mm = rng.uniform(0.1, 0.8)                 # drizzle
                temp = 14 + 5 * math.sin(math.pi * (h - 8) / 12) - (2.5 if mm > 1 else 0) + rng.uniform(-0.7, 0.7)
                rows.append(dict(localidad=loc, ts=utc(ts), rain_mm=round(max(mm, 0), 1), temp_c=round(temp, 1)))
    return rows


# expected orders per hour of day, city-wide, before rain (lunch + dinner peaks)
HOURLY = [0.1, 0.05, 0, 0, 0, 0.05, 0.3, 0.6, 0.7, 0.5, 0.6, 1.4, 2.4, 2.0, 0.9, 0.6, 0.6, 0.9,
          1.8, 2.6, 2.3, 1.2, 0.6, 0.3]
SOUP_PLACES = {"R-001": 3, "R-007": 2, "R-008": 2, "R-003": 1.5}


def build_orders(rng, users, user_by_id, rest_by_id, menu, rain):
    by_loc = {}
    for u in users:
        by_loc.setdefault(u["localidad"], []).append(u)
    total_w = sum(len(v) for v in by_loc.values())

    raw = []
    for day in range(DAYS):
        for h in range(24):
            hour = START + timedelta(days=day, hours=h)
            for loc, people in by_loc.items():
                mm = rain.get((loc, utc(hour)), 0)
                lam = HOURLY[h] * 1.3 * len(people) / total_w * (1 + 0.9 * min(mm, 10))
                for _ in range(poisson(rng, lam)):
                    placed = hour + timedelta(seconds=rng.randint(0, 3599))
                    raw.append((placed, loc, mm))

    raw.sort()
    busy = {c: [] for c, _, _ in COURIERS}
    busy["C-01"].append((GOLDEN["placed_at"], GOLDEN["delivered_at"] + timedelta(minutes=5)))
    orders, pings = [], []

    for placed, loc, mm in raw:
        people = by_loc[loc]
        weights = [1.6 if u["user_id"] == "U-0001" else 1 for u in people]
        user = rng.choices(people, weights=weights)[0]
        rids = list(rest_by_id)
        rw = [SOUP_PLACES.get(r, 1) * (1 + mm) if mm > 1 else 1 for r in rids]
        rest = rest_by_id[rng.choices(rids, weights=rw)[0]]
        dishes = menu[rest["restaurant_id"]]
        picked = rng.sample(dishes, rng.choice([1, 1, 2, 2, 3]))
        soup = [d for d in dishes if "soup" in d["tags"]]
        if mm > 1 and soup and soup[0] not in picked and rng.random() < 0.8:
            picked[0] = soup[0]
        items = [dict(dish_id=d["dish_id"], name=d["name"], qty=rng.choice([1, 1, 1, 2]),
                      unit_price_cop=d["price_cop"]) for d in picked]
        pickup = placed + timedelta(minutes=rng.randint(10, 22))
        delivered = pickup + timedelta(minutes=rng.randint(12, 25))
        courier = next((c for c in busy if all(e <= pickup or s >= delivered for s, e in busy[c])),
                       rng.choice(list(busy)[2:]))
        busy[courier].append((pickup, delivered))
        orders.append(dict(user_id=user["user_id"], restaurant_id=rest["restaurant_id"], courier_id=courier,
                           items=items, delivery_fee_cop=rng.choice([3900, 4900, 5900, 6900]),
                           placed_at=placed, picked_up_at=pickup, delivered_at=delivered))

    # numbering: chronological, skipping 42, which belongs to the golden order
    numbers = (n for n in range(1, 10**6) if n != 42)
    for o in orders:
        o["order_id"] = f"O-{next(numbers):06d}"
    g = GOLDEN
    dish_by_name = {d["name"]: d for d in menu["R-001"]}
    orders.append(dict(order_id=g["order_id"], user_id=g["user_id"], restaurant_id=g["restaurant_id"],
                       courier_id=g["courier_id"], delivery_fee_cop=g["delivery_fee_cop"],
                       items=[dict(dish_id=dish_by_name[n]["dish_id"], name=n, qty=q,
                                   unit_price_cop=dish_by_name[n]["price_cop"]) for n, q in g["items"]],
                       placed_at=g["placed_at"], picked_up_at=g["picked_up_at"], delivered_at=g["delivered_at"]))

    for o in orders:
        o["total_cop"] = sum(i["qty"] * i["unit_price_cop"] for i in o["items"]) + o["delivery_fee_cop"]
        rest, user = rest_by_id[o["restaurant_id"]], user_by_id[o["user_id"]]
        o["localidad"] = user["localidad"]
        pings += route(rng, o, (rest["lat"], rest["lon"]), (user["lat"], user["lon"]))
        for k in ("placed_at", "picked_up_at", "delivered_at"):
            o[k] = utc(o[k])
    orders.sort(key=lambda o: o["order_id"])
    return orders, pings


def route(rng, order, a, b):
    """A ping every 30 s between pickup and delivery: north-south first, then east-west, with GPS noise."""
    t, end = order["picked_up_at"], order["delivered_at"]
    steps = int((end - t).total_seconds() // 30)
    out = []
    for i in range(steps + 1):
        f = i / steps
        lat = a[0] + (b[0] - a[0]) * min(1, f * 1.6)
        lon = a[1] + (b[1] - a[1]) * max(0, (f - 0.35) / 0.65)
        ts = t + timedelta(seconds=30 * i)
        out.append(dict(courier_id=order["courier_id"], ts=utc(ts), day=ts.astimezone(BOGOTA).date().isoformat(),
                        lat=round(lat + rng.uniform(-0.0003, 0.0003), 6),
                        lon=round(lon + rng.uniform(-0.0003, 0.0003), 6)))
    return out


def check(data):
    """The few facts the demos rely on."""
    golden = next(o for o in data["orders"] if o["order_id"] == "O-000042")
    assert golden["total_cop"] == 46900, golden
    banned = ["something", "warm", "for", "a", "cold", "rainy", "night"]  # every word of the query
    for d in data["dishes"]:
        if d["name"] in WARM_DISHES:
            text = f'{d["name"]} {d["description"]} {" ".join(d["tags"])}'.lower()
            words = set(re.findall(r"\w+", text))
            assert not words & set(banned), (d["name"], words & set(banned))
    ids = [o["order_id"] for o in data["orders"]]
    assert len(ids) == len(set(ids))


if __name__ == "__main__":
    import json
    import os
    from collections import Counter

    data = build()
    check(data)
    out = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(out, exist_ok=True)
    for k, v in data.items():
        with open(os.path.join(out, f"{k}.json"), "w", encoding="utf-8") as f:
            json.dump(v, f, ensure_ascii=False, indent=1, default=str)
    print({k: len(v) for k, v in data.items()})
    print("Valentina orders:", sum(o["user_id"] == "U-0001" for o in data["orders"]))
    eve = [o for o in data["orders"] if o["localidad"] == "Chapinero"
           and "2026-10-30T22" <= o["placed_at"].isoformat() < "2026-10-31T04"]
    print("Chapinero 2026-10-30 evening, per local hour:",
          sorted(Counter(o["placed_at"].astimezone(BOGOTA).hour for o in eve).items()))
    soups = {"rain": [0, 0], "dry": [0, 0]}
    rain = {(w["localidad"], w["ts"]): w["rain_mm"] for w in data["weather"]}
    for o in data["orders"]:
        hr = o["placed_at"].replace(minute=0, second=0)
        k = "rain" if rain.get((o["localidad"], hr), 0) > 1 else "dry"
        soups[k][0] += 1
        soups[k][1] += any("soup" in d["tags"] for i in o["items"] for d in data["dishes"] if d["dish_id"] == i["dish_id"])
    print("orders / with soup:", soups)
    c01 = [p for p in data["pings"] if p["courier_id"] == "C-01" and p["day"] == "2026-10-30"
           and "2026-10-31T01:03" <= p["ts"].isoformat() <= "2026-10-31T01:21:59"]
    print("golden route pings:", len(c01), "order ids in window: ok" if c01 else "")
