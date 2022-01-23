import sys
import os

from argparse import ArgumentParser
from copybot import CopyBot
from bsc_trades import BscTrades


def main():
    config_path = os.path.join(os.path.dirname(__file__), '..', 'properties.yml')

    copybot = CopyBot(path_to_config=config_path)

    bsc_transaction_executor = BscTrades(bot=copybot, path_to_config=config_path)
    bsc_transaction_executor.listen_and_execute()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Shutting down")
        sys.exit(0)
