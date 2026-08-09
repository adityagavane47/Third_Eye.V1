import asyncio
import os
from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase

load_dotenv("../.env")

async def main():
    uri = os.getenv("NEO4J_URI")
    auth_str = os.getenv("NEO4J_AUTH", "")
    auth = tuple(auth_str.split("/")) if auth_str else None
    
    driver = AsyncGraphDatabase.driver(uri, auth=auth)
    
    async with driver.session() as session:
        # Match all attacker nodes and set their risk score to a random value between 0.86 and 0.99
        await session.run("""
            MATCH (w:Wallet {label: 'attacker'})
            SET w.risk_score = 0.86 + (rand() * 0.13)
        """)
        print("✅ Successfully randomized attacker risk scores.")
    
    await driver.close()

if __name__ == "__main__":
    asyncio.run(main())
