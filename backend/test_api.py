import httpx
import asyncio

async def test():
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            "http://127.0.0.1:8000/api/shield/blacklist",
            json={
                "wallet_address": "0x9999999999999999999999999999999999999999",
                "risk_score": 0.99,
                "reason": "Test"
            }
        )
        print(f"Status: {res.status_code}")
        print(f"Response: {res.json()}")

if __name__ == "__main__":
    asyncio.run(test())
