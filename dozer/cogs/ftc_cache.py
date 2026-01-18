"""Database tables for FTC Events caching."""
import asyncpg
from dozer.db import DatabaseTable, Pool


class FTCCacheGeneric(DatabaseTable):
    """Generic cache table for all FTC Events API responses."""
    __tablename__ = 'ftc_cache_generic'
    __uniques__ = ['cache_key']
    __versions__ = []

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
                cache_key text PRIMARY KEY,
                season int NOT NULL,
                cache_data jsonb NOT NULL,
                last_updated timestamp NOT NULL DEFAULT NOW()
            )
            """)
            # Create an index on last_updated for efficient cache expiry queries
            await conn.execute(f"""
            CREATE INDEX idx_{cls.__tablename__}_last_updated 
            ON {cls.__tablename__}(last_updated)
            """)
