import os
import asyncio
import httpx
from eth_abi import encode as abi_encode
from eth_utils import keccak
from dotenv import load_dotenv

load_dotenv()

async def check_operator():
    rpc_url = os.getenv("WEB3_RPC_URL")
    contract_addr = os.getenv("GUARDIAN_CONTRACT_ADDRESS")
    operator_address = "0xeDfa9415D1c9614631FBbC1Fba490dDF2411e1Db"
    
    print(f"Using RPC: {rpc_url}")
    print(f"Using Contract: {contract_addr}")
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Check if contract exists
        r_code = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 0, "method": "eth_getCode", "params": [contract_addr, "latest"]})
        code = r_code.json().get("result", "0x")
        print(f"Contract code length: {len(code)}")
        if len(code) <= 2:
            print("WARNING: No contract found at this address!")
            return

        selector = keccak(b"Third EyeOperators(address)")[:4]
        data = "0x" + selector.hex() + abi_encode(["address"], [operator_address]).hex()
        
        r = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": contract_addr, "data": data}, "latest"]})
        res = r.json()
        if "result" in res:
            res_val = res["result"]
            if res_val == "0x":
                print(f"Result is 0x. {operator_address} is NOT an operator or function not found.")
            else:
                is_operator = int(res_val, 16) == 1
                print(f"Is {operator_address} an operator? {is_operator}")
        else:
            print(f"Error: {res}")

        # Check threshold
        selector_rs = keccak(b"riskThreshold()")[:4]
        r_rs = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 2, "method": "eth_call", "params": [{"to": contract_addr, "data": "0x" + selector_rs.hex()}, "latest"]})
        res_rs = r_rs.json()
        if "result" in res_rs and len(res_rs["result"]) > 2:
            threshold = int(res_rs["result"], 16)
            print(f"Risk Threshold: {threshold}")

if __name__ == "__main__":
    asyncio.run(check_operator())
