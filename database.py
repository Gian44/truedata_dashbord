import psycopg2
from psycopg2 import pool
from configparser import ConfigParser

class DatabaseManager:
    _connection_pool = None

    @classmethod
    def initialize(cls):
        config = ConfigParser()
        config.read('config.ini')
        cls._connection_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            host=config['postgresql']['host'],
            database=config['postgresql']['database'],
            user=config['postgresql']['user'],
            password=config['postgresql']['password']
        )

    @classmethod
    def get_connection(cls):
        if cls._connection_pool is None:
            cls.initialize()
        return cls._connection_pool.getconn()

    @classmethod
    def return_connection(cls, connection):
        if cls._connection_pool and connection:
            cls._connection_pool.putconn(connection)

    @classmethod
    def execute_query(cls, query, params=None):
        conn = cls.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                if query.strip().upper().startswith('SELECT'):
                    return cur.fetchall()
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cls.return_connection(conn)

    @classmethod
    def initialize_tables(cls):
        """Initialize a simple non-partitioned table"""
        create_table_query = """
            CREATE TABLE IF NOT EXISTS truedata_realtime (
                symbol VARCHAR(50) NOT NULL,
                ts TIMESTAMPTZ NOT NULL,
                ltp DECIMAL(15, 2),
                volume BIGINT,
                PRIMARY KEY (symbol, ts)
            );
            
            CREATE INDEX IF NOT EXISTS idx_truedata_symbol_ts ON truedata_realtime (symbol, ts);
        """
        cls.execute_query(create_table_query)