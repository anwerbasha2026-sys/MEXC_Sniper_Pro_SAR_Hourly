MEXC Sniper Pro — SAR Hourly — API connection fix

Fixes included:
- Synchronizes local CCXT time difference with MEXC before loading markets.
- Enables CCXT adjustForTimeDifference and sets recvWindow to 10 seconds.
- Gives clearer guidance for common MEXC signature, timestamp, permission, and IP whitelist errors.
- Keeps Spot-only market selection and the existing hourly SAR strategy.

Install dependencies in Windows terminal:
  py -m pip install --upgrade ccxt customtkinter

Run:
  py MEXC_Sniper_Pro_SAR_High_Risk.py

First test with Demo mode. If the same error remains, verify API key and Secret Key,
account-read permission, IP whitelist, and Windows Date & time > Set time automatically > Sync now.
Never share your Secret Key. Do not enable withdrawal permission for the bot.

Validation performed: Python syntax compilation only. No live MEXC API request or live trade was executed here.
