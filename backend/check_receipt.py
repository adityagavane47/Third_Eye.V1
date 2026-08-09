import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

async def check_receipt():
    rpc_url = os.getenv("WEB3_RPC_URL", "https://sepolia.base.org")
    tx_hash = "0x9ceb7019282c8596acf12b897552d89ceea5b52478ced5203c3cb751fefdefc6"
    
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionReceipt", "params": [tx_hash]})
        res = r.json()
        print(f"Receipt: {res}")
        if "result" in res and res["result"]:
            status = res["result"].get("status")
            print(f"Status: {status} ({'Success' if status == '0x1' else 'Failed/Reverted'})")

if __name__ == "__main__":
    asyncio.run(check_receipt())
