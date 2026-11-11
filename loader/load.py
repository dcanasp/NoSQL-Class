"""Fills every database with the Domi dataset and keeps checking.

Restarting a database container wipes it (no persistent storage). Every 20 s this script checks
each engine and reloads any that came back empty. So restarting a container is the reset button.
"""
import json
import os
import time
import traceback

import httpx

from domi_data import build, check

DATA = build()
check(DATA)
REST = {r["restaurant_id"]: r for r in DATA["restaurants"]}

H = os.environ.get
REDIS_HOST, MONGO_URL = H("REDIS_HOST", "redis"), H("MONGO_URL", "mongodb://mongo:27017")
SCYLLA_HOST, NEO4J_URL = H("SCYLLA_HOST", "scylla"), H("NEO4J_URL", "bolt://neo4j:7687")
NEO4J_AUTH = ("neo4j", H("NEO4J_PASSWORD", "domi-neo4j"))
INFLUX_URL, ELASTIC_URL, QDRANT_URL = (H("INFLUX_URL", "http://influx:8181"),
                                       H("ELASTIC_URL", "http://elastic:9200"), H("QDRANT_URL", "http://qdrant:6333"))
http = httpx.Client(timeout=60)


# ---------------------------------------------------------------- Redis

def redis_client():
    import redis
    return redis.Redis(host=REDIS_HOST, decode_responses=True)


def redis_loaded():
    return redis_client().exists("user:U-0001")


def redis_load():
    r = redis_client()
    p = r.pipeline()
    for u in DATA["users"]:
        p.hset(f"user:{u['user_id']}", mapping={"name": u["name"], "localidad": u["localidad"]})
    p.zadd("ranking:restaurants:rating", {x["restaurant_id"]: x["rating"] for x in DATA["restaurants"]})
    p.execute()


# ---------------------------------------------------------------- MongoDB

def mongo_db():
    from pymongo import MongoClient
    return MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000).domi


def mongo_loaded():
    return mongo_db().orders.estimated_document_count() > 0


def mongo_load():
    db = mongo_db()
    db.restaurants.drop()
    db.orders.drop()
    db.restaurants.insert_many([
        {"_id": r["restaurant_id"], **{k: v for k, v in r.items() if k != "restaurant_id"},
         "menu": [d for d in DATA["dishes"] if d["restaurant_id"] == r["restaurant_id"]]}
        for r in DATA["restaurants"]])
    db.orders.insert_many([
        {"_id": o["order_id"], "user_id": o["user_id"], "restaurant_id": o["restaurant_id"],
         "courier_id": o["courier_id"], "items": o["items"], "delivery_fee_cop": o["delivery_fee_cop"],
         "total_cop": o["total_cop"], "placed_at": o["placed_at"], "delivered_at": o["delivered_at"]}
        for o in DATA["orders"]])


# ---------------------------------------------------------------- ScyllaDB

def scylla_session():
    from cassandra.cluster import Cluster
    return Cluster([SCYLLA_HOST]).connect()


def scylla_loaded():
    s = scylla_session()
    try:
        return s.execute("SELECT user_id FROM domi.orders_by_user LIMIT 1").one() is not None
    except Exception:
        return False
    finally:
        s.cluster.shutdown()


def scylla_load():
    from cassandra.concurrent import execute_concurrent_with_args
    s = scylla_session()
    s.execute("CREATE KEYSPACE IF NOT EXISTS domi WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}")
    s.set_keyspace("domi")
    s.execute("""CREATE TABLE IF NOT EXISTS courier_pings_by_day (
        courier_id text, day date, ts timestamp, lat double, lon double,
        PRIMARY KEY ((courier_id, day), ts)) WITH CLUSTERING ORDER BY (ts DESC)""")
    s.execute("""CREATE TABLE IF NOT EXISTS orders_by_user (
        user_id text, placed_at timestamp, order_id text, restaurant_name text, total_cop int,
        PRIMARY KEY ((user_id), placed_at, order_id)) WITH CLUSTERING ORDER BY (placed_at DESC, order_id ASC)""")
    ping = s.prepare("INSERT INTO courier_pings_by_day (courier_id, day, ts, lat, lon) VALUES (?, ?, ?, ?, ?)")
    execute_concurrent_with_args(s, ping, [
        (p["courier_id"], p["day"], p["ts"], p["lat"], p["lon"]) for p in DATA["pings"]], concurrency=100)
    order = s.prepare("INSERT INTO orders_by_user (user_id, placed_at, order_id, restaurant_name, total_cop) VALUES (?, ?, ?, ?, ?)")
    execute_concurrent_with_args(s, order, [
        (o["user_id"], o["placed_at"], o["order_id"], REST[o["restaurant_id"]]["name"], o["total_cop"])
        for o in DATA["orders"]], concurrency=100)
    s.cluster.shutdown()


# ---------------------------------------------------------------- Neo4j

def neo4j_driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(NEO4J_URL, auth=NEO4J_AUTH)


def neo4j_loaded():
    with neo4j_driver() as d:
        recs, _, _ = d.execute_query("MATCH (u:User {user_id:'U-0001'}) RETURN count(u) AS n")
        return recs[0]["n"] > 0


def neo4j_load():
    q = [
        ("CREATE CONSTRAINT IF NOT EXISTS FOR (x:User) REQUIRE x.user_id IS UNIQUE", {}),
        ("CREATE CONSTRAINT IF NOT EXISTS FOR (x:Order) REQUIRE x.order_id IS UNIQUE", {}),
        ("CREATE CONSTRAINT IF NOT EXISTS FOR (x:Dish) REQUIRE x.dish_id IS UNIQUE", {}),
        ("UNWIND $rows AS r MERGE (x:User {user_id: r.user_id}) SET x.name = r.name, x.localidad = r.localidad",
         {"rows": DATA["users"]}),
        ("UNWIND $rows AS r MATCH (a:User {user_id: r.referred_by}), (b:User {user_id: r.user_id}) MERGE (a)-[:REFERRED]->(b)",
         {"rows": [u for u in DATA["users"] if u["referred_by"]]}),
        ("UNWIND $rows AS r MERGE (x:Restaurant {restaurant_id: r.restaurant_id}) "
         "SET x.name = r.name, x.cuisine = r.cuisine, x.localidad = r.localidad, x.rating = r.rating",
         {"rows": DATA["restaurants"]}),
        ("UNWIND $rows AS r MERGE (x:Dish {dish_id: r.dish_id}) SET x.name = r.name, x.price_cop = r.price_cop "
         "WITH x, r MATCH (rest:Restaurant {restaurant_id: r.restaurant_id}) MERGE (rest)-[:SERVES]->(x)",
         {"rows": DATA["dishes"]}),
        ("UNWIND $rows AS r MERGE (x:Courier {courier_id: r.courier_id}) SET x.name = r.name, x.vehicle = r.vehicle",
         {"rows": DATA["couriers"]}),
        ("UNWIND $rows AS r MERGE (o:Order {order_id: r.order_id}) SET o.total_cop = r.total_cop, o.placed_at = r.placed_at "
         "WITH o, r MATCH (u:User {user_id: r.user_id}), (c:Courier {courier_id: r.courier_id}) "
         "MERGE (u)-[:PLACED]->(o) MERGE (c)-[:DELIVERED]->(o) "
         "WITH o, r UNWIND r.items AS i MATCH (d:Dish {dish_id: i.dish_id}) MERGE (o)-[c:CONTAINS]->(d) SET c.qty = i.qty",
         {"rows": [{**o, "placed_at": o["placed_at"].isoformat()} for o in DATA["orders"]]}),
    ]
    with neo4j_driver() as d:
        for cypher, params in q:
            d.execute_query(cypher, params)


# ---------------------------------------------------------------- InfluxDB 3

def lp_tag(v):
    return v.replace(" ", r"\ ").replace(",", r"\,")


def influx_loaded():
    r = http.post(f"{INFLUX_URL}/api/v3/query_sql", json={"db": "domi", "q": "SELECT count(*) AS n FROM orders"})
    return r.status_code == 200 and r.json()[0]["n"] > 0


def influx_load():
    lines = [f"orders,localidad={lp_tag(o['localidad'])},restaurant_id={o['restaurant_id']} "
             f"total_cop={o['total_cop']}i {int(o['placed_at'].timestamp())}" for o in DATA["orders"]]
    lines += [f"weather,localidad={lp_tag(w['localidad'])} rain_mm={w['rain_mm']},temp_c={w['temp_c']} "
              f"{int(w['ts'].timestamp())}" for w in DATA["weather"]]
    r = http.post(f"{INFLUX_URL}/api/v3/write_lp", params={"db": "domi", "precision": "second"},
                  content="\n".join(lines).encode())
    r.raise_for_status()


# ---------------------------------------------------------------- Elasticsearch

def elastic_loaded():
    return http.get(f"{ELASTIC_URL}/dishes/_count").json().get("count", 0) > 0


def elastic_load():
    http.delete(f"{ELASTIC_URL}/dishes")
    http.put(f"{ELASTIC_URL}/dishes", json={
        "settings": {"number_of_replicas": 0, "analysis": {"analyzer": {"default": {
            "type": "custom", "tokenizer": "standard", "filter": ["lowercase", "asciifolding"]}}}},
        "mappings": {"properties": {
            "dish_id": {"type": "keyword"}, "name": {"type": "text"}, "description": {"type": "text"},
            "tags": {"type": "text"}, "price_cop": {"type": "integer"}, "restaurant_name": {"type": "text"},
            "localidad": {"type": "keyword"}, "author": {"type": "keyword"}}},
    }).raise_for_status()
    body = ""
    for d in DATA["dishes"]:
        r = REST[d["restaurant_id"]]
        doc = {"dish_id": d["dish_id"], "name": d["name"], "description": d["description"], "tags": d["tags"],
               "price_cop": d["price_cop"], "restaurant_name": r["name"], "localidad": r["localidad"]}
        body += json.dumps({"index": {"_id": d["dish_id"]}}) + "\n" + json.dumps(doc) + "\n"
    http.post(f"{ELASTIC_URL}/dishes/_bulk?refresh=true", content=body.encode(),
              headers={"Content-Type": "application/x-ndjson"}).raise_for_status()


# ---------------------------------------------------------------- Qdrant

_model = None


def embed(texts):
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding("sentence-transformers/all-MiniLM-L6-v2", cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))
    return [v.tolist() for v in _model.embed(texts)]


def qdrant_loaded():
    r = http.get(f"{QDRANT_URL}/collections/dishes")
    return r.status_code == 200 and r.json()["result"]["points_count"] > 0


def qdrant_load():
    http.delete(f"{QDRANT_URL}/collections/dishes")
    http.put(f"{QDRANT_URL}/collections/dishes", json={"vectors": {"size": 384, "distance": "Cosine"}}).raise_for_status()
    dishes = DATA["dishes"]
    vectors = embed([f"{d['name']}. {d['description']} {', '.join(d['tags'])}" for d in dishes])
    points = [{"id": i, "vector": v, "payload": {
        "dish_id": d["dish_id"], "name": d["name"], "restaurant_name": REST[d["restaurant_id"]]["name"],
        "localidad": REST[d["restaurant_id"]]["localidad"], "price_cop": d["price_cop"], "tags": d["tags"]}}
        for i, (d, v) in enumerate(zip(dishes, vectors), start=1)]
    http.put(f"{QDRANT_URL}/collections/dishes/points?wait=true", json={"points": points}).raise_for_status()


# ---------------------------------------------------------------- loop

ENGINES = {
    "redis": (redis_loaded, redis_load), "mongo": (mongo_loaded, mongo_load),
    "scylla": (scylla_loaded, scylla_load), "neo4j": (neo4j_loaded, neo4j_load),
    "influx": (influx_loaded, influx_load), "elastic": (elastic_loaded, elastic_load),
    "qdrant": (qdrant_loaded, qdrant_load),
}

if __name__ == "__main__":
    print(f"Dataset: { {k: len(v) for k, v in DATA.items()} }", flush=True)
    status = {}
    while True:
        for name, (loaded, load) in ENGINES.items():
            try:
                if not loaded():
                    print(f"[{name}] empty, loading...", flush=True)
                    t = time.time()
                    load()
                    print(f"[{name}] loaded in {time.time() - t:.1f}s", flush=True)
                status[name] = "ok"
            except Exception as e:
                if status.get(name) != str(e):  # log each distinct failure once (engines start slowly)
                    print(f"[{name}] not ready: {e.__class__.__name__}: {str(e)[:200]}", flush=True)
                    if os.environ.get("DEBUG"):
                        traceback.print_exc()
                status[name] = str(e)
        time.sleep(20)
