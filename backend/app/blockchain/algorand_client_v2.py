from typing import Any, Dict, Optional

from algosdk import account, mnemonic
from algosdk.transaction import AssetTransferTxn
from algosdk.transaction import PaymentTxn
from algosdk.transaction import wait_for_confirmation as _wait_for_confirmation
from algosdk.v2client import algod

ALGOD_ADDRESS = "https://testnet-api.algonode.cloud"
ALGOD_TOKEN = ""


class AlgorandClient:
    def __init__(self, mnemonic_phrase: str):
        self.private_key = mnemonic.to_private_key(mnemonic_phrase)
        self.address = account.address_from_private_key(self.private_key)
        self.algod = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)

    def send_payment(self, receiver: str, amount: int):
        params = self.algod.suggested_params()

        txn = PaymentTxn(
            sender=self.address,
            sp=params,
            receiver=receiver,
            amt=amount,
        )

        signed_txn = txn.sign(self.private_key)
        tx_id = self.algod.send_transaction(signed_txn)

        return tx_id

    # Sends Algorand Standard Asset (ASA), e.g. USDC
    # amount must be in base units (already converted)
    def send_asset(
        self,
        receiver: str,
        amount: int,
        asset_id: int,
        note: Optional[bytes] = None,
    ) -> str:
        params = self.algod.suggested_params()

        txn = AssetTransferTxn(
            sender=self.address,
            sp=params,
            receiver=receiver,
            amt=amount,
            index=asset_id,
            note=note if note is not None else b"",
        )

        signed_txn = txn.sign(self.private_key)
        tx_id = self.algod.send_transaction(signed_txn)

        return tx_id

    def wait_for_confirmation(self, tx_id: str, wait_rounds: int = 0) -> Dict[str, Any]:
        """Block until algod reports confirmation (or timeout / rejection)."""
        return _wait_for_confirmation(self.algod, tx_id, wait_rounds)

