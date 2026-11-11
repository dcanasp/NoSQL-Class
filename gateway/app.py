"""Domi lab gateway. Dumb on purpose: the body is the native query, sent as-is to the engine.

POST /redis    HGETALL user:U-0001
POST /mongo    orders.find({_id: "O-000042"})
POST /scylla   SELECT * FROM domi.orders_by_user WHERE user_id='U-0001'
POST /neo4j    MATCH (u:User {user_id:'U-0001'}) RETURN u
POST /influx   SELECT ... (SQL)  or  weather,localidad=Suba,author=nick rain_mm=3 (line protocol)
POST /elastic  GET /dishes/_search            <- first line: METHOD /path, the rest: JSON body
POST /qdrant   POST /collections/dishes/points/query
GET  /health   (no auth)
"""
import json
import os
import re
import shlex
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

H = os.environ.get
CLASS_CODE = H("CLASS_CODE", "domi")
REDIS_HOST, MONGO_URL = H("REDIS_HOST", "redis"), H("MONGO_URL", "mongodb://mongo:27017")
SCYLLA_HOST, NEO4J_URL = H("SCYLLA_HOST", "scylla"), H("NEO4J_URL", "bolt://neo4j:7687")
NEO4J_AUTH = ("neo4j", H("NEO4J_PASSWORD", "domi-neo4j"))
INFLUX_URL, ELASTIC_URL, QDRANT_URL = (H("INFLUX_URL", "http://influx:8181"),
                                       H("ELASTIC_URL", "http://elastic:9200"), H("QDRANT_URL", "http://qdrant:6333"))
TIMEOUT = 10
MAX_ROWS = 500

app = FastAPI(title="Domi NoSQL lab")
http = httpx.Client(timeout=TIMEOUT)


def blocked(what):
    raise HTTPException(403, f"🚫 {what} is disabled in this lab")


def to_json(x):
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if hasattr(o, "isoformat"):
            return o.isoformat()
        return str(o)
    return Response(json.dumps(x, ensure_ascii=False, default=default), media_type="application/json")


async def query_of(request: Request):
    if request.headers.get("authorization", "") != f"Bearer {CLASS_CODE}":
        raise HTTPException(401, "Ask the instructor for the class code")
    return (await request.body()).decode("utf-8").strip()


# ---------------------------------------------------------------- Redis

REDIS_BLOCKED = set("DEL UNLINK GETDEL HDEL ZREM SREM LPOP RPOP EXPIRE PERSIST FLUSHDB FLUSHALL RENAME KEYS "
                    "EVAL CONFIG SHUTDOWN".split())
_redis = None


def redis_client():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.Redis(host=REDIS_HOST, decode_responses=True, socket_timeout=TIMEOUT)
    return _redis


def run_redis(q):
    parts = shlex.split(q)
    if not parts:
        raise HTTPException(400, "Empty command")
    if parts[0].upper() in REDIS_BLOCKED:
        blocked(parts[0].upper())
    return redis_client().execute_command(*parts)


# ---------------------------------------------------------------- MongoDB
# Shell-style: <collection>.<method>(<args>), args in relaxed JSON (unquoted keys are fine).

MONGO_BLOCKED = {"deleteone", "deletemany", "findoneanddelete", "remove", "drop", "dropindex", "dropindexes",
                 "dropdatabase", "renamecollection"}
MONGO_METHODS = {"find", "findone", "aggregate", "countdocuments", "distinct", "insertone", "insertmany",
                 "updateone", "updatemany"}
_mongo = None


def mongo_db():
    global _mongo
    if _mongo is None:
        from pymongo import MongoClient
        _mongo = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000, socketTimeoutMS=TIMEOUT * 1000).domi
    return _mongo


def run_mongo(q):
    import json5
    m = re.fullmatch(r"(?:db\.)?(\w+)\.(\w+)\((.*)\)\s*;?", q, re.S)
    if not m:
        raise HTTPException(400, 'Write it like: orders.find({_id: "O-000042"})')
    coll, method, args = m.group(1), m.group(2), m.group(3)
    if method.lower() in MONGO_BLOCKED or coll.lower().startswith("drop"):
        blocked(method)
    if re.search(r"['\"]?\$(out|merge)\b", args):
        blocked("$out / $merge")
    if method.lower() not in MONGO_METHODS:
        raise HTTPException(400, f"{method} is not available in this lab. Try find, aggregate, insertOne, updateOne.")
    try:
        a = json5.loads(f"[{args}]")
    except ValueError as e:
        raise HTTPException(400, f"Could not read the arguments: {e}")
    c = mongo_db()[coll]
    mt = method.lower()
    if mt == "find":
        return list(c.find(*a).max_time_ms(TIMEOUT * 1000).limit(MAX_ROWS))
    if mt == "findone":
        return c.find_one(*a)
    if mt == "aggregate":
        return list(c.aggregate(*a, maxTimeMS=TIMEOUT * 1000))[:MAX_ROWS]
    if mt == "countdocuments":
        return c.count_documents(*(a or [{}]))
    if mt == "distinct":
        return c.distinct(*a)
    if mt == "insertone":
        return {"inserted_id": c.insert_one(*a).inserted_id}
    if mt == "insertmany":
        return {"inserted_ids": c.insert_many(*a).inserted_ids}
    r = getattr(c, {"updateone": "update_one", "updatemany": "update_many"}[mt])(*a)
    return {"matched": r.matched_count, "modified": r.modified_count}


# ---------------------------------------------------------------- ScyllaDB

SCYLLA_BLOCKED = re.compile(r"\b(DELETE|TRUNCATE|DROP|ALTER\s+KEYSPACE|GRANT|REVOKE)\b", re.I)
_scylla, _scylla_lock = None, threading.Lock()


def scylla_session():
    global _scylla
    with _scylla_lock:
        if _scylla is None:
            from cassandra.cluster import Cluster
            from cassandra.query import dict_factory
            s = Cluster([SCYLLA_HOST]).connect()
            s.row_factory = dict_factory
            _scylla = s
    return _scylla


def run_scylla(q):
    m = SCYLLA_BLOCKED.search(q)
    if m:
        blocked(m.group(1).upper())
    from cassandra import InvalidRequest
    try:
        f = scylla_session().execute_async(q.rstrip(";"), timeout=TIMEOUT)
        rows = f.result()
    except InvalidRequest as e:
        raise HTTPException(400, e.message if hasattr(e, "message") else str(e))
    out = list(rows)[:MAX_ROWS]
    warnings = f.warnings or []
    return {"rows": out, "warnings": warnings} if warnings else out


# ---------------------------------------------------------------- Neo4j

NEO4J_BLOCKED = re.compile(r"\b(DELETE|DROP|LOAD\s+CSV|CALL\s+dbms\.|CALL\s+apoc\.)", re.I)
_neo4j = None


def run_neo4j(q):
    global _neo4j
    m = NEO4J_BLOCKED.search(q)
    if m:
        blocked(m.group(1).upper().rstrip("."))
    from neo4j import GraphDatabase, Query
    from neo4j.exceptions import ClientError
    if _neo4j is None:
        _neo4j = GraphDatabase.driver(NEO4J_URL, auth=NEO4J_AUTH)
    try:
        with _neo4j.session() as s:
            res = s.run(Query(q, timeout=TIMEOUT))
            return [r.data() for r in res][:MAX_ROWS]
    except ClientError as e:
        raise HTTPException(400, e.message)


# ---------------------------------------------------------------- InfluxDB 3

INFLUX_SQL_WORDS = re.compile(r"^\s*(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|SHOW|SET|COPY|EXPLAIN)\b", re.I)


def run_influx(q):
    m = INFLUX_SQL_WORDS.match(q)
    if m:
        blocked(m.group(1).upper())
    if re.match(r"^\s*(SELECT|WITH)\b", q, re.I):
        r = http.post(f"{INFLUX_URL}/api/v3/query_sql", json={"db": "domi", "q": q, "format": "json"})
    else:  # line protocol write
        r = http.post(f"{INFLUX_URL}/api/v3/write_lp", params={"db": "domi", "precision": "auto"},
                      content=q.encode())
        if r.status_code < 300:
            return {"written": len([l for l in q.splitlines() if l.strip()])}
    if r.status_code >= 300:
        raise HTTPException(400, r.text)
    return r.json()


# ---------------------------------------------------------------- Elasticsearch & Qdrant (HTTP)
# Body: first line "METHOD /path", the rest is the JSON body (Kibana Dev Tools style).

def split_http(q):
    first, _, body = q.partition("\n")
    parts = first.split(None, 1)
    if len(parts) != 2:
        raise HTTPException(400, "First line must be: METHOD /path, e.g. GET /dishes/_search")
    method, path = parts[0].upper(), "/" + parts[1].strip().lstrip("/")
    return method, path, body.strip()


def forward(base, method, path, body):
    r = http.request(method, base + path, content=body.encode() or None,
                     headers={"Content-Type": "application/x-ndjson" if "_bulk" in path else "application/json"})
    try:
        data = r.json()
    except ValueError:
        data = r.text
    if r.status_code >= 400:
        raise HTTPException(r.status_code, data)
    return data


def run_elastic(q):
    method, path, body = split_http(q)
    if method == "DELETE":
        blocked("DELETE")
    for bad in ("_delete_by_query", "_close", "_cluster", "_snapshot", "_security"):
        if bad in path:
            blocked(bad)
    if method == "PUT" and "_settings" in path:
        blocked("PUT _settings")
    if "_bulk" in path and re.search(r'"delete"\s*:', body):
        blocked("DELETE")
    return forward(ELASTIC_URL, method, path, body)


def run_qdrant(q):
    method, path, body = split_http(q)
    if method == "DELETE":
        blocked("DELETE")
    for bad in ("/points/delete", "/points/payload/delete", "/points/payload/clear", "/points/vectors/delete",
                "snapshots", "/cluster"):
        if bad in path:
            blocked(bad.strip("/"))
    if method == "PATCH" and path.startswith("/collections"):
        blocked("PATCH on collections")
    return forward(QDRANT_URL, method, path, body)


# ---------------------------------------------------------------- routes

RUNNERS = {"redis": run_redis, "mongo": run_mongo, "scylla": run_scylla, "neo4j": run_neo4j,
           "influx": run_influx, "elastic": run_elastic, "qdrant": run_qdrant}


def make_route(name, runner):
    async def route(request: Request):
        q = await query_of(request)
        from starlette.concurrency import run_in_threadpool
        try:
            return to_json(await run_in_threadpool(runner, q))
        except HTTPException:
            raise
        except Exception as e:  # engine errors go back to the student as-is
            raise HTTPException(400, f"{e.__class__.__name__}: {e}")
    app.post(f"/{name}")(route)


for _n, _r in RUNNERS.items():
    make_route(_n, _r)


CHECKS = {
    "redis": lambda: redis_client().ping(),
    "mongo": lambda: mongo_db().command("ping"),
    "scylla": lambda: scylla_session().execute("SELECT now() FROM system.local"),
    "neo4j": lambda: run_neo4j("RETURN 1"),
    "influx": lambda: http.get(f"{INFLUX_URL}/health", timeout=3).raise_for_status(),
    "elastic": lambda: http.get(f"{ELASTIC_URL}/_cluster/health", timeout=3).raise_for_status(),
    "qdrant": lambda: http.get(f"{QDRANT_URL}/readyz", timeout=3).raise_for_status(),
}
_pool = ThreadPoolExecutor(8)


@app.get("/health")
def health():
    futures = {n: _pool.submit(f) for n, f in CHECKS.items()}
    out = {}
    for n, fut in futures.items():
        try:
            fut.result(timeout=5)
            out[n] = "up"
        except Exception:
            out[n] = "down"
    return out
