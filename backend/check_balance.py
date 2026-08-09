import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

async def check_balance():
    rpc_url = os.getenv("WEB3_RPC_URL", "https://sepolia.base.org")
    address = "0xeDfa9415D1c9614631FBbC1Fba490dDF2411e1Db"
    
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [address, "latest"]})
        res = r.json()
        if "result" in res:
            balance_wei = int(res["result"], 16)
            print(f"Balance of {address}: {balance_wei / 1e18} ETH")
        else:
            print(f"Error: {res}")

if __name__ == "__main__":
    asyncio.run(check_balance())
