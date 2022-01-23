import pyetherbalance
import sys
import traceback 
import requests
import os

from network.pancakeswap import Pancakeswap
from models.trade_order import TradeOrder
from web3 import Web3, types
from utils import utils
from utils.config import Configuration
from web3.gas_strategies.time_based import fast_gas_price_strategy


logger = utils.create_logger(__name__)


class CopyBot:
    def __init__(self, path_to_config):
        self.path_to_config = path_to_config
        self.__load_config(path_to_config)

        self.bsc_wallet_checker = pyetherbalance.PyEtherBalance(self.config.get('chain_url'))


    def __load_config(self, config):
        config_parser = Configuration(os.path.abspath(config))
        
        self.config = dict(config_parser.get_config()['copybot'])


    def put_token_in_wallet_checker(self, token_name, token_address, token_decimals):
        """
        Function that adds incoming token to bsc_wallet_checker
        """
        token_details = {
                'symbol': token_name.upper(), 
                'address': token_address,
                'decimals': token_decimals,
                'name': token_name.upper()
            }
        
        self.bsc_wallet_checker.add_token(token_name.upper(), token_details)


    def get_token_balance_in_wallet(self, my_address, token_name, token_address, token_decimals):
        """
        Using the pyetherbalance library, check a wallet address for a 
        particular token's balance.
        """
        if token_name == 'BNB':
            balance = self.bsc_wallet_checker.get_eth_balance(my_address).get('balance')
            return float(balance)
    
        if token_name not in self.bsc_wallet_checker.erc20_tokens:
            self.put_token_in_wallet_checker(token_name=token_name, token_address=token_address, token_decimals=token_decimals)

        balance = self.bsc_wallet_checker.get_token_balance(token_name.upper(), my_address).get('balance')

        return float(balance)


    def process_trade_order(self, trade_order: TradeOrder) -> bool:
        logger.debug('Received trade order to execute')
        
        if trade_order.order_type == 'BUY':
            return self.exec_trade(trade_order.order_type, trade_order.contract_address, self.config.get('main_coin'), self.config.get('main_coin_contract_address'),
                            self.config.get('my_address'), self.config.get('my_pk'), float(self.config.get('max_slippage')), self.config.get('chain_url'),
                            int(self.config.get('maxgwei')), 18)
        
        else:
            return self.exec_trade(trade_order.order_type, self.config.get('main_coin_contract_address'), trade_order.token_symbol, trade_order.contract_address, 
                            self.config.get('my_address'), self.config.get('my_pk'), float(self.config.get('max_slippage')), self.config.get('chain_url'),
                            int(self.config.get('maxgwei')), trade_order.token_decimals)


    def exec_trade(self, order_type, buytoken_address, sell_token_name, selltoken_address, my_address, pk, max_slippage, chain_url, maxgwei, selldecimals: int, amount=None) -> bool:
        """
        Executes a trade on the Pancakeswap
        """
        self.__load_config(self.path_to_config)
        
        check_min_amount = bool(int(self.config.get('check_min_amount')))

        if not amount:
            amount = float(self.config.get('buy_amount_usd'))

        try:
            w3 = Web3(Web3.HTTPProvider(chain_url))
            w3.eth.setGasPriceStrategy(fast_gas_price_strategy)

            sell_token = w3.toChecksumAddress(selltoken_address)
            buy_token = w3.toChecksumAddress(buytoken_address)

            gwei = types.Wei(Web3.toWei(int(maxgwei), "gwei"))

            pancakeswap = Pancakeswap(my_address, pk, web3=Web3(w3.HTTPProvider(chain_url)), version=2, max_slippage=max_slippage)


            total_bnb_in_wallet = self.get_token_balance_in_wallet(my_address, self.config.get('main_coin'), self.config.get('main_coin_contract_address'), 18)

            # Check that we have enough BNB in wallet
            if check_min_amount and total_bnb_in_wallet < float(self.config.get('min_amount_to_keep')):
                logger.warning(f"Amount of BNB in wallet is below pre-configured threshold: {self.config.get('min_amount_to_keep')}")
                return False

            if order_type == 'BUY':
                current_bnb_price = float((requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDC').json())['price'])
                token_amount = ( amount / current_bnb_price)

                if check_min_amount and (total_bnb_in_wallet - token_amount) < float(self.config.get('min_amount_to_keep')):
                    logger.warning(f"Amount of BNB in wallet after BUY transaction would be below pre-configured threshold: {self.config.get('min_amount_to_keep')}")
                    return False

            else:
                token_amount = self.get_token_balance_in_wallet(my_address, sell_token_name, selltoken_address, selldecimals)
                trade_amount = int(token_amount)

                if check_min_amount and (token_amount / 10 ** selldecimals) <= 0:
                    logger.warning(f"You have 0 tokens to sell for {sell_token_name}")
                    return False
            
            trade_amount = token_amount * 10 ** selldecimals
            trade_amount = int((token_amount / 1.000001) * 10 ** selldecimals)

            if len(str(trade_amount)) > 4:
                trade_amount = int(str(trade_amount)[:-4] + '0000')
            if trade_amount < 0:
                trade_amount = int(1)

            logger.info(f'Executing the following {order_type} trade/swap for: {sell_token} - {buy_token} - {trade_amount} - {gwei} - {my_address} - PRIVATE_KEY - {my_address}')

            if bool(int(self.config.get('execute_orders'))):
                # Executes trade
                pancakeswap.make_trade(sell_token, buy_token, trade_amount, gwei, my_address, pk, my_address)
                
                logger.info(f"Trade successfully sent to pancakeswap to execute. Review your wallet's token transfers!")
                return True
            
            else:
                logger.info("Did not execute trade, 'execute_orders' property set to 0.")
                return True

        except Exception as e:
            logger.error(f"An error occurred: {traceback.format_exception(sys.exc_info())}")
            logger.error(f"Terminating app...")
            
            sys.exit()
