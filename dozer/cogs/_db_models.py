"""Shared database models used by multiple cogs"""

from .. import db
from ..db import Pool


class MemberRole(db.DatabaseTable):
    """Holds info on member roles used for timeouts"""
    __tablename__ = 'member_roles'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            member_role bigint null
            )""")

    def __init__(self, guild_id: int, member_role: int = None):
        super().__init__()
        self.guild_id = guild_id
        self.member_role = member_role

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = MemberRole(member_role=result.get("member_role"), guild_id=result.get("guild_id"))
            result_list.append(obj)
        return result_list


class GuildNewMember(db.DatabaseTable):
    """Holds new member info"""
    __tablename__ = 'new_members'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            channel_id bigint NOT NULL,
            role_id bigint NOT NULL,
            message varchar NOT NULL
            )""")

    def __init__(self, guild_id: int, channel_id: int, role_id: int, message: str, require_team: bool):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.role_id = role_id
        self.message = message
        self.require_team = require_team

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildNewMember(guild_id=result.get("guild_id"), channel_id=result.get("channel_id"),
                                 role_id=result.get("role_id"), message=result.get("message"),
                                 require_team=result.get("require_team"))
            result_list.append(obj)
        return result_list

    async def version_1(self):
        """DB migration v1"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            ALTER TABLE {self.__tablename__} ADD require_team bool NOT NULL DEFAULT false;
            """)

    __versions__ = [version_1]


class FTCCacheTable(db.DatabaseTable):
    """Generic cache table for all FTC Events API responses using native PostgreSQL."""
    __tablename__ = 'ftc_api_cache'
    __uniques__ = ['cache_key']
    __versions__ = []

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
                cache_key text PRIMARY KEY,
                cache_type text NOT NULL,
                cache_data jsonb NOT NULL,
                season int,
                last_updated timestamp NOT NULL DEFAULT NOW()
            )
            """)
            # Create an index on cache_type and last_updated for efficient queries
            await conn.execute(f"""
            CREATE INDEX idx_{cls.__tablename__}_type ON {cls.__tablename__}(cache_type)
            """)
            await conn.execute(f"""
            CREATE INDEX idx_{cls.__tablename__}_updated ON {cls.__tablename__}(last_updated)
            """)


class WordFilter(db.DatabaseTable):
    """Object for each filter"""
    __tablename__ = 'word_filters'
    __uniques__ = 'filter_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            filter_id serial PRIMARY KEY NOT NULL,
            enabled boolean default true NOT NULL,
            guild_id bigint NOT NULL,
            friendly_name varchar null,
            pattern varchar NOT NULL
            )""")

    def __init__(self, guild_id: int, friendly_name: str, pattern: str, enabled: bool = True, filter_id: int = None):
        super().__init__()
        self.filter_id = filter_id
        self.guild_id = guild_id
        self.enabled = enabled
        self.friendly_name = friendly_name
        self.pattern = pattern

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = WordFilter(guild_id=result.get("guild_id"), friendly_name=result.get("friendly_name"),
                             pattern=result.get("pattern"), enabled=result.get("enabled"),
                             filter_id=result.get("filter_id"))
            result_list.append(obj)
        return result_list


class WordFilterSetting(db.DatabaseTable):
    """Each filter-related setting"""
    __tablename__ = 'word_filter_settings'
    __uniques__ = 'id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id serial PRIMARY KEY NOT NULL,
            setting_type varchar NOT NULL,
            guild_id bigint NOT NULL,
            value varchar NOT NULL
            )""")

    def __init__(self, guild_id: int, setting_type: str, value: str):
        super().__init__()
        self.guild_id = guild_id
        self.setting_type = setting_type
        self.value = value

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = WordFilterSetting(guild_id=result.get("guild_id"), setting_type=result.get("setting_type"),
                                    value=result.get('value'))
            result_list.append(obj)
        return result_list


class WordFilterRoleWhitelist(db.DatabaseTable):
    """Object for each whitelisted role"""
    __tablename__ = 'word_filter_role_whitelist'
    __uniques__ = 'role_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint NOT NULL,
            role_id bigint PRIMARY KEY NOT NULL 
            )""")

    def __init__(self, guild_id: int, role_id: int):
        super().__init__()
        self.role_id = role_id
        self.guild_id = guild_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = WordFilterRoleWhitelist(guild_id=result.get("guild_id"), role_id=result.get("role_id"))
            result_list.append(obj)
        return result_list
