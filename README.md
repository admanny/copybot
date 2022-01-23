# CopyBot
Automated bot that copies the swaps of a given account. Operates on the Binance Smart Chain network and uses Pancakeswap to facilitate swaps. The bot has limited functionality, checks, and error handling. 

This implementation represents the initial version created as part of a 24 hour hackathon.

**Note:** This was a hackathon project intended for learning the web3 library and cryptocurrency ecosystem. *Not intended for use with real money.*


## Usage
**Requires API key from https://bscscan.com**
### Running on local Ganache network
* Start local network using Ganache (Requires Node.js / npm installation)
```bash
npm install -g ganache-cli
ganache-cli --port 10999 --networkId 56 --fork https://bsc-dataseed.binance.org/
```
* Using the output addresses and keys populate the configuration values into properties.yml
* Find a address to listen to and copy their trades and populate 'listen_to_address' property.
* Execute `main.py`