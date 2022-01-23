import time
import os

from utils import utils
from utils.config import Configuration
from copybot import CopyBot
from models.trade_order import TradeOrder
from bscscan import BscScan


logger = utils.create_logger(__name__)


class BscTrades:
    def __init__(self, bot: CopyBot, path_to_config):
        self.path_to_config = path_to_config
        self.config = self._load_config(path_to_config)
        
        # Dictionary to store transaction hashes we've already seen
        self.txn_seen = {} 
        
        # Dictionary should contain tokens waiting for us to SELL
        self.open_swaps = {} 

        self.address = self.config.get('listen_to_address')
        self.bot = bot

    def _load_config(self, config) -> dict:
        """
        Load section from properties file into a dictionary
        """
        config_parser = Configuration(os.path.abspath(config))
        return dict(config_parser.get_config()['bsc_trades'])

    def get_account_transactions(self, bsc: BscScan, address: str) -> list:
        """ 
        Call to the bscscan.com API to retrieve token 
        transfer events for a specific addresss
        """
        transactions = bsc.get_bep20_token_transfer_events_by_address(address=address, startblock=None, endblock=None, sort='desc')

        return transactions

    def get_unix_timediff_in_seconds(self, unix_timestamp: int) -> int:
        """ 
        Calculates the time difference in seconds between current 
        time and another unix timestamp.
        """
        now = int(time.time())
        timediff = now - unix_timestamp

        return int(timediff)

    def create_trade_order(self, order_type: str, transaction: dict) -> dict:
        """
        Function creates a TradeOrder object which will be passed
        along to our trade execution bot to action on.
        """
        order = TradeOrder(order_type, transaction.get('tokenSymbol'), 
                        transaction.get('contractAddress'), int(transaction.get('tokenDecimal'))
                )

        return order

    def _process_transactions(self, transactions: list):
        """
        Function iterates through all elements in the transactions list with 
        the goal of identifying actionable transactions to execute
        """
        check_freshness = bool(int(self.config.get('check_freshness')))

        for transaction in transactions:
            tran_type = None

            txn_hash = str(transaction.get('hash'))
            txn_timestamp = int(transaction.get('timeStamp'))
            txn_to = str(transaction.get('to'))
            
            symbol = str(transaction.get('tokenSymbol'))
            contract_address = str(transaction.get('contractAddress'))
            
            if txn_hash not in self.txn_seen:
                if  check_freshness and self.get_unix_timediff_in_seconds(txn_timestamp) > 60:
                    logger.info(f"Transaction={txn_hash} is older than 60 seconds")
                    
                    self.txn_seen[txn_hash] = True
                    continue

                if contract_address.upper() in self.token_blacklist:
                    logger.info(f"{txn_hash} involves a blacklisted token. Moving to next transaction.")

                    self.txn_seen[txn_hash] = True
                    continue 
                

                if txn_to.upper() == self.address.upper():
                    tran_type = 'BUY'
                else:
                    tran_type = 'SELL'

                if tran_type == 'SELL' and contract_address in self.open_swaps:
                    logger.debug(f"Found actionable {tran_type} transaction: {txn_hash}")

                    sell_percentage = int((int(transaction.get('value')) / self.open_swaps.get(contract_address)) * 100)
                    if sell_percentage >= 50:
                        if bool(int(self.config.get('send_sell_orders'))):
                            trade_order = self.create_trade_order(tran_type, transaction)
                            
                            is_success = self._send_order_to_execute(trade_order=trade_order)

                            if is_success: 
                                del self.open_swaps[contract_address]
                        else:
                            logger.debug(f"SELL orders are disabled. Review 'send_sell_orders' property.")    
                    else:
                        logger.info(f"SELL transaction, {txn_hash}, does not reach 50% value threshold. Not executing transaction.")
                    
                    self.txn_seen[txn_hash] = True

                elif tran_type == 'BUY' and contract_address not in self.open_swaps:
                    logger.debug(f"Found actionable {tran_type} transaction: {txn_hash}")

                    trade_order = self.create_trade_order(tran_type, transaction)

                    is_success = self._send_order_to_execute(trade_order=trade_order)

                    if is_success: 
                        self.open_swaps[contract_address] = int(transaction.get('value'))
                    
                    self.txn_seen[txn_hash] = True 
                
                else:
                    logger.debug(f"{txn_hash} does not meet trade/swap conditions. Moving to next transaction...")

                    self.txn_seen[txn_hash] = True
                    continue
            
            else:
                logger.debug(f"Already saw {txn_hash}")
                continue

    def _send_order_to_execute(self, trade_order: TradeOrder) -> bool:
        """
        Transfers trade orders to the trading bot to execute
        """
        send_flag = bool(int(self.config.get('send_trade_orders')))
        
        if send_flag:
            logger.debug(f"Sending {trade_order.order_type} order to trade bot for execution.")
            return self.bot.process_trade_order(trade_order=trade_order)
        else:
            logger.debug(f"Did not execute trade. 'send_trade_order' property set to {send_flag}")
            return False

    def listen_and_execute(self):
        """
        This method pulls the transaction made by a specific wallet address
        every 0.5 seconds. It then sends the list of transactions proccessed   
        """
        key = str(self.config.get('api_key'))
        bsc = BscScan(api_key=key)

        while True:
            try:
                logger.info(f"PROCESSING TRANSACTIONS from {self.address}")

                transactions = self.get_account_transactions(bsc, self.address)

                transactions = transactions[0:15]
                transactions.reverse()

                self._process_transactions(transactions)
                logger.debug("Sleeping...\n")

                time.sleep(0.5)
            except  Exception as e:
                logger.error(f"{e}")
                logger.info("Sleeping for 2.5 seconds then retrying...")
                time.sleep(2.5) 
            