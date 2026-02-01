"""Shared database models used by multiple cogs"""

from .. import db


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
