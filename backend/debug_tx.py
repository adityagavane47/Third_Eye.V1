import os
import asyncio
import httpx
from eth_account import Account
from eth_abi import encode as abi_encode
from eth_utils import keccak
from dotenv import load_dotenv

load_dotenv()

async def debug_tx():
    rpc_url = os.getenv("WEB3_RPC_URL", "https://sepolia.base.org")
    priv_key = os.getenv("OPERATOR_PRIVATE_KEY")
    contract_addr = os.getenv("GUARDIAN_CONTRACT_ADDRESS")
    account = Account.from_key(priv_key)
    
    print(f"RPC: {rpc_url}")
    print(f"Contract: {contract_addr}")
    print(f"From: {account.address}")

    async with httpx.AsyncClient(timeout=30) as client:
        async def rpc(method, params):
            r = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            res = r.json()
            if "error" in res:
                print(f"RPC Error [{method}]: {res['error']}")
            return res

        # 1. Check code at contract address
        r_code = await rpc("eth_getCode", [contract_addr, "latest"])
        print(f"Contract code length: {len(r_code.get('result', '0x'))}")

        # 2. Build blacklist call
        fn_sig = b"blacklistWallet(address,uint256,string)"
        selector = keccak(fn_sig)[:4]
        wallet_address = "0x1234567890123456789012345678901234567890"
        risk_uint = int(0.9 * 1000)
        encoded_args = abi_encode(["address", "uint256", "string"], [wallet_address, risk_uint, "Test Debug"])
        calldata = "0x" + selector.hex() + encoded_args.hex()

        # 3. Get tx params
        res_nonce = await rpc("eth_getTransactionCount", [account.address, "latest"])
        nonce = int(res_nonce["result"], 16)
        
        res_gas = await rpc("eth_gasPrice", [])
        gas_price = int(res_gas["result"], 16)
        
        res_chain = await rpc("eth_chainId", [])
        chain_id = int(res_chain["result"], 16)

        tx = {
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 200000,
            "to": contract_addr,
            "value": 0,
            "data": calldata,
            "chainId": chain_id
        }

        # 4. Try eth_call first to simulate
        sim_res = await rpc("eth_call", [{"to": contract_addr, "data": calldata, "from": account.address}, "latest"])
        print(f"eth_call Simulation: {sim_res}")

        # 5. Send tx
        signed = account.sign_transaction(tx)
        raw_tx_hex = signed.rawTransaction.hex()
        if not raw_tx_hex.startswith("0x"):
            raw_tx_hex = "0x" + raw_tx_hex
        send_res = await rpc("eth_sendRawTransaction", [raw_tx_hex])
        print(f"Send tx: {send_res}")

if __name__ == "__main__":
    asyncio.run(debug_tx())
