import asyncio

from enterprise_agent.db.mysql import init_db


async def main():
    """Initialize database tables"""
    print("Initializing database...")
    await init_db()
    print("Database tables created successfully!")


if __name__ == "__main__":
    asyncio.run(main())