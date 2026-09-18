import os

from psycopg_pool import ConnectionPool


def get_pool():
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    user = os.environ.get("PGUSER", "postgres")
    password = os.environ.get("PGPASSWORD", "dev")
    dbname = os.environ.get("PGDATABASE", "postgres")
    
    conninfo = f"host={host} port={port} user={user} password={password} dbname={dbname}"
    pool = ConnectionPool(conninfo)
    
    return pool

pool = get_pool()
    