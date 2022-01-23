
class TradeOrder:
    def __init__(self, order_type: str, token_symbol: str, contract_address: str, token_decimals: int):
        self.order_type = order_type
        self.token_symbol = token_symbol
        self.contract_address = contract_address
        self.token_decimals = token_decimals
