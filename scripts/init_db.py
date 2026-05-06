import asyncio

# Import all models so they register with Base.metadata before create_all()
import enterprise_agent.models  # noqa: F401
from enterprise_agent.db.mysql import init_db


async def main():
    """Initialize database tables"""
    print("Initializing database...")
    await init_db()
    print("Database tables created successfully!")


if __name__ == "__main__":
    asyncio.run(main())