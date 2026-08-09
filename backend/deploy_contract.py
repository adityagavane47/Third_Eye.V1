import os
import json
import asyncio
import httpx
from pathlib import Path
from eth_account import Account
import solcx
from dotenv import load_dotenv
from eth_abi import encode as abi_encode

load_dotenv()

# We need to compile Solidity 0.8.24
# First, install the compiler version if not available
SOLC_VERSION = "0.8.24"
try:
    solcx.set_solc_version(SOLC_VERSION)
except solcx.exceptions.SolcNotInstalled:
    print(f"Installing solc version {SOLC_VERSION}...")
    solcx.install_solc(SOLC_VERSION)
    solcx.set_solc_version(SOLC_VERSION)

async def deploy():
    rpc_url = os.getenv("WEB3_RPC_URL", "https://sepolia.base.org")
    priv_key = os.getenv("OPERATOR_PRIVATE_KEY")
    if not priv_key:
        print("ERROR: OPERATOR_PRIVATE_KEY is missing in .env")
        return
        
    account = Account.from_key(priv_key)
    print(f"Deployer account: {account.address}")
    
    # 1. Compile the contract
    print("Compiling contract...")
    contract_path = Path(__file__).parent.parent / "contracts" / "ThirdEyeGuardian.sol"
    node_modules = Path(__file__).parent.parent / "contracts" / "node_modules"
    
    # Map @openzeppelin to the node_modules folder where we installed it
    import_remappings = [
        f"@openzeppelin/={node_modules.resolve()}/@openzeppelin/"
    ]
    
    compiled = solcx.compile_files(
        [contract_path],
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
        import_remappings=import_remappings
    )
    
    # The key in the compiled output is "<filepath>:<ContractName>"
    contract_key = next((k for k in compiled.keys() if "ThirdEyeGuardian" in k and "ThirdEyeGuardian.sol" in k), None)
    if not contract_key:
        print("Available keys:", list(compiled.keys()))
        raise Exception("Could not find ThirdEyeGuardian in compiled output.")
        
    contract_interface = compiled[contract_key]
    bytecode = contract_interface["bin"]
    abi = contract_interface["abi"]
    
    # 2. Build the constructor deployment transaction
    print("Building deployment transaction...")
    # Constructor takes 'address initialOwner'
    constructor_args = abi_encode(["address"], [account.address])
    deployment_data = "0x" + bytecode + constructor_args.hex()
    
    async with httpx.AsyncClient(timeout=60) as client:
        async def rpc(method, params):
            r = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            res = r.json()
            if "error" in res:
                print(f"RPC Error [{method}]: {res['error']}")
                raise Exception(res['error'])
            return res["result"]

        # Get nonce, gas price, chain ID
        nonce = int(await rpc("eth_getTransactionCount", [account.address, "latest"]), 16)
        gas_price = int(await rpc("eth_gasPrice", []), 16)
        chain_id = int(await rpc("eth_chainId", []), 16)
        
        tx = {
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 3000000, # Deployment gas limit
            "value": 0,
            "data": deployment_data,
            "chainId": chain_id
        }
        
        # 3. Sign and Send
        print("Signing transaction...")
        signed = account.sign_transaction(tx)
        raw_tx_hex = signed.rawTransaction.hex()
        if not raw_tx_hex.startswith("0x"):
            raw_tx_hex = "0x" + raw_tx_hex
            
        print("Sending deployment transaction to Base Sepolia...")
        tx_hash = await rpc("eth_sendRawTransaction", [raw_tx_hex])
        print(f"Transaction hash: {tx_hash}")
        
        # 4. Wait for receipt to get the contract address
        print("Waiting for transaction confirmation...")
        for _ in range(30):
            await asyncio.sleep(2)
            res_receipt = await client.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionReceipt", "params": [tx_hash]})
            receipt_json = res_receipt.json()
            receipt = receipt_json.get("result")
            if receipt:
                if receipt.get("status") == "0x1":
                    contract_address = receipt["contractAddress"]
                    print(f"\n✅ ThirdEyeGuardian successfully deployed to: {contract_address}")
                    
                    # Update .env
                    env_file = Path(__file__).parent.parent / ".env"
                    content = env_file.read_text()
                    import re
                    content = re.sub(r'GUARDIAN_CONTRACT_ADDRESS=0x[a-fA-F0-9]{40}', f'GUARDIAN_CONTRACT_ADDRESS={contract_address}', content)
                    content = re.sub(r'VITE_GUARDIAN_CONTRACT_ADDRESS=0x[a-fA-F0-9]{40}', f'VITE_GUARDIAN_CONTRACT_ADDRESS={contract_address}', content)
                    env_file.write_text(content)
                    print("✅ Updated .env with new contract address.")
                    
                    return
                else:
                    print(f"❌ Transaction failed/reverted. Receipt: {receipt}")
                    return
        
        print("Timeout waiting for confirmation.")

if __name__ == "__main__":
    asyncio.run(deploy())
