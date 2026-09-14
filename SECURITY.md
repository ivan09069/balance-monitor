# Authentication hardening

A unique random `API_KEY` of at least 32 characters is required. Built-in defaults
have been removed. Missing or short configuration returns 503 on protected routes;
invalid credentials return 401. Requests are limited to 16 KiB. Provision new
credentials in the server environment before rollout and rotate any old default.

The public health route is informational. This does not certify the pricing,
wallet attribution, signal profitability, or live trading behavior of this service.

Offline test: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_auth.py`.

`/trade-alert` also requires authentication. Configure the executor with the corresponding `BALANCE_MONITOR_KEY`.
