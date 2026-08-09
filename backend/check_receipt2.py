import asyncio
import httpx

async def check():
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            "https://sepolia.base.org",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getTransactionReceipt",
                "params": ["0xd3785fa129fccf7e7ace2275f4a70864044834d1e89017a8c1e339e35d503620"]
            }
        )
        data = res.json()
        print(data)

if __name__ == "__main__":
    asyncio.run(check())
