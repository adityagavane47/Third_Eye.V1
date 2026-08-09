import os
import asyncio
import httpx
from eth_account import Account
from eth_abi import encode as abi_encode
from eth_utils import keccak
from dotenv import load_dotenv

load_dotenv()

async def test_shield():
    wallet_address = "0x1234567890123456789012345678901234567890"
    risk_score = 0.9
    reason = "Test"
    
    rpc_url = os.getenv("WEB3_RPC_URL", "https://sepolia.base.org")
    priv_key = os.getenv("OPERATOR_PRIVATE_KEY")
    contract_addr = os.getenv("GUARDIAN_CONTRACT_ADDRESS", "0xd9145CCE52D386f254917e481eB44e9943F39138")

    if not priv_key:
        print("OPERATOR_PRIVATE_KEY not set")
        return

    try:
        fn_sig = b"blacklistWallet(address,uint256,string)"
        selector = keccak(fn_sig)[:4]
        risk_uint = int(risk_score * 1000)
        encoded_args = abi_encode(["address", "uint256", "string"], [wallet_address, risk_uint, reason])
        calldata = "0x" + selector.hex() + encoded_args.hex()

        account = Account.from_key(priv_key)
        print(f"Testing with account: {account.address}")

        async with httpx.AsyncClient(timeout=30) as client:
            async def rpc(method, params):
                r = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
                return r.json()

            res_nonce = await rpc("eth_getTransactionCount", [account.address, "latest"])
            print(f"Nonce response: {res_nonce}")
            nonce = int(res_nonce["result"], 16)
            
            res_gas = await rpc("eth_gasPrice", [])
            print(f"Gas price response: {res_gas}")
            gas_price = int(res_gas["result"], 16)
            
            res_chain = await rpc("eth_chainId", [])
            print(f"Chain ID response: {res_chain}")
            chain_id = int(res_chain["result"], 16)

            tx = {"nonce": nonce, "gasPrice": gas_price, "gas": 200000, "to": contract_addr, "value": 0, "data": calldata, "chainId": chain_id}
            signed = account.sign_transaction(tx)
            print("Transaction signed successfully")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_shield())
