
import json
import requests

class AbiCache:
    def __init__(self, chain_endpoint, chain_package=None):
        self.chain_endpoint = chain_endpoint
        self.cache = {}

    def read_abi(self, contract):
        if contract not in self.cache:
            url = f"{self.chain_endpoint}/v1/chain/get_abi"
            resp = requests.post(url, json={"account_name": contract})
            if resp.ok:
                self.cache[contract] = resp.json()["abi"]
            else:
                raise Exception(f"Failed to fetch ABI for {contract}")
        return self.cache[contract]

    def sign_and_push(self, cleos, keys, trx):
        return cleos.push_transaction(trx, keys, broadcast=True)
