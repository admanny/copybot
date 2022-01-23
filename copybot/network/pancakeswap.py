import functools
import logging
import os
import time

from web3 import Web3
from web3.contract import ContractFunction
from web3.types import Any, Wei, ChecksumAddress, TxParams, Nonce, HexBytes
from typing import Union, Optional
from utils import utils
from utils.exceptions import InsufficientBalance
from eth_typing import AnyAddress
from eth_utils import is_same_address


logger = logging.getLogger(__name__)


class Pancakeswap:
    def __init__(self, address: Union[str, AnyAddress], private_key: str, provider: str = None, 
        web3: Web3 = None, version:int = 2, max_slippage: float = 0.1) -> None:

        self.address: AnyAddress = utils.str_to_addr(address) if isinstance(address, str) else address
        self.private_key = private_key
        self.version = version
        self.max_slippage = max_slippage

        if web3:
            self.w3 = web3
        else:
            self.provider = provider or os.environ["PROVIDER"]
            self.w3 = Web3(Web3.HTTPProvider(self.provider, request_kwargs={"timeout": 60}))
        
        self.last_nonce: Nonce = self.w3.eth.get_transaction_count(self.address)

        
        self.factory_address_v2 = utils.str_to_addr('0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73')
        self.router_address_v2  = utils.str_to_addr('0x10ED43C718714eb63d5aA57B78B54704E256024E')

        self.factory = utils.load_contract("factory", self.factory_address_v2, self.w3, "pancakeswap")
        self.router = utils.load_contract("router02", self.router_address_v2, self.w3, "pancakeswap")
    
        self.max_approval_hex = f"0x{64 * 'f'}"
        self.max_approval_int = int(self.max_approval_hex, 16)
        self.max_approval_check_hex = f"0x{15 * '0'}{49 * 'f'}"
        self.max_approval_check_int = int(self.max_approval_check_hex, 16)


    def _build_and_send_approval(self, function: ContractFunction) -> HexBytes:
        params = {
            "from": utils.addr_to_str(self.address),
            "value": Wei(0),
            "gas": Wei(250000),
            "nonce": max(
                self.last_nonce, self.w3.eth.getTransactionCount(self.address)
            ),
        } 

        transaction = function.buildTransaction(params)
        
        signed_txn = self.w3.eth.account.sign_transaction(
            transaction, private_key=self.private_key
        )
        
        try:
            return self.w3.eth.sendRawTransaction(signed_txn.rawTransaction)
        finally:
            logger.debug(f"nonce: {params['nonce']}")
            self.last_nonce = Nonce(params["nonce"] + 1)


    def _eth_to_token_swap_input(self,gwei, my_address, my_pk, output_token: AnyAddress, qty: Wei, recipient: Optional[AnyAddress]) -> HexBytes:
        eth_balance = self.get_eth_balance()
        if qty > eth_balance:
            raise InsufficientBalance(eth_balance, qty)

        if recipient is None:
            recipient = self.address
        
        amount_out_min = int( (1 - self.max_slippage) * self.get_eth_token_input_price(output_token, qty) )
        
        return self._build_and_send_tx(gwei, my_address, my_pk,
            self.router.functions.swapExactETHForTokens(
                amount_out_min,
                [self.get_weth_address(), output_token],
                recipient,
                self._deadline(),
            ),
            self._get_tx_params(value=qty, gwei=gwei,my_address=my_address),
        )


    def _token_to_eth_swap_input(self, gwei, my_address, my_pk, input_token: AnyAddress, qty: int, recipient: Optional[AnyAddress]) -> HexBytes:
        input_balance = self.get_token_balance(input_token)
        if qty > input_balance:
            raise InsufficientBalance(input_balance, qty)

        if recipient is None:
            recipient = self.address
        amount_out_min = int( (1 - self.max_slippage) * self.get_token_eth_input_price(input_token, qty) )
        
        return self._build_and_send_tx(gwei, my_address,my_pk,
            self.router.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                qty,
                amount_out_min,
                [input_token, self.get_weth_address()],
                recipient,
                self._deadline(),
            )
        )


    def _token_to_token_swap_input(self, gwei, my_address, my_pk, input_token: AnyAddress,
        qty: int, output_token: AnyAddress, recipient: Optional[AnyAddress],) -> HexBytes:

        if recipient is None:
            recipient = self.address

        min_tokens_bought = int( (1 - self.max_slippage) * self.get_token_token_input_price(input_token, output_token, qty) )
        
        return self._build_and_send_tx(gwei, my_address,my_pk,
            self.router.functions.swapExactTokensForTokens(
                qty,
                min_tokens_bought,
                [input_token, self.get_weth_address(), output_token],
                recipient,
                self._deadline(),
            ),
        )


    def _build_and_send_tx(self, gwei, my_address, my_pk, function: ContractFunction, tx_params: Optional[TxParams] = None) -> HexBytes:
        if not tx_params:
            tx_params = self._get_tx_params(gwei,my_address)
        
        transaction = function.buildTransaction(tx_params)
        signed_txn = self.w3.eth.account.sign_transaction(
            transaction, private_key=my_pk
        )
        try:
            return self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        finally:
            logger.debug(f"nonce: {tx_params['nonce']}")
            self.last_nonce = Nonce(tx_params["nonce"] + 1)


    def _get_tx_params(self, gwei, my_address, value: Wei = Wei(0), gas: Wei = Wei(250000)) -> TxParams:
        return {
            "from": my_address,
            "value": value,
            "gas": gas,
            "gasPrice":gwei,
            "nonce": max(
                self.last_nonce, self.w3.eth.get_transaction_count(self.address)
            ),
        }


    def _deadline(self) -> int:
        return int(time.time()) + 10 * 60


    def _is_approved(self, token: AnyAddress) -> bool:
        utils.validate_address(token)
        contract_addr = self.router_address_v2
        
        amount = (
            utils.load_contract("erc20", token, self.w3, "pancakeswap")
            .functions.allowance(self.address, contract_addr)
            .call()
        )
        
        if amount >= self.max_approval_check_int:
            return True
        else:
            return False


    def get_eth_balance(self) -> Wei:
        return self.w3.eth.get_balance(self.address)
    

    @functools.lru_cache()
    def get_weth_address(self) -> ChecksumAddress:
        address = Web3.toChecksumAddress('0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c')
        
        return address


    def get_token_balance(self, token: AnyAddress) -> int:
        utils.validate_address(token)
        if utils.addr_to_str(token) == utils.ETH_ADDRESS:
            return self.get_eth_balance()
        
        erc20 = utils.load_contract("erc20", token, self.w3, "pancakeswap")
        balance: int = erc20.functions.balanceOf(self.address).call()
        
        return balance


    def get_eth_token_input_price(self, token: AnyAddress, qty: int) -> int:
        price = self.router.functions.getAmountsOut(
            qty, 
            [self.get_weth_address(), token]
        ).call()[-1]
        
        return price


    def get_token_eth_input_price(self, token: AnyAddress, qty: int) -> int:
        price = self.router.functions.getAmountsOut(
            qty, 
            [token, self.get_weth_address()]
        ).call()[-1]

        return price


    def get_token_token_input_price(self, token0: AnyAddress, token1: AnyAddress, qty: int) -> int:
        if is_same_address(token0, self.get_weth_address()):
            return int(self.get_eth_token_input_price(token1, qty))
        elif is_same_address(token1, self.get_weth_address()):
            return int(self.get_token_eth_input_price(token0, qty))

        price: int = self.router.functions.getAmountsOut(
            qty, [token0, self.get_weth_address(), token1]
        ).call()[-1]

        return price


    @utils.check_approval
    def make_trade(self, input_token: AnyAddress, output_token: AnyAddress, qty: Union[int, Wei],
        gwei, my_address, my_pk, recipient: AnyAddress = None,) -> HexBytes:

        if input_token == utils.ETH_ADDRESS:
            return self._eth_to_token_swap_input(gwei, my_address, my_pk, output_token, Wei(qty), recipient)
        else:
            balance = self.get_token_balance(input_token)
            if balance < qty:
                raise InsufficientBalance(balance, qty)
            
            if output_token == utils.ETH_ADDRESS:
                return self._token_to_eth_swap_input(gwei, my_address, my_pk, input_token, qty, recipient)
            else:
                return self._token_to_token_swap_input(gwei, my_address, my_pk, input_token, qty, output_token, recipient)


    def approve(self, token: AnyAddress, max_approval: Optional[int] = None) -> None:
        max_approval = self.max_approval_int if not max_approval else max_approval
        
        contract_addr = (
            self.router_address_v2
        )

        function = utils.load_contract("erc20", token, self.w3, "pancakeswap").functions.approve(
            contract_addr, max_approval
        )

        logger.info(f"Approving {utils.addr_to_str(token)}...")
        
        tx = self._build_and_send_approval(function)
        self.w3.eth.wait_for_transaction_receipt(tx, timeout=6000)

        time.sleep(1)
