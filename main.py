#!/usr/bin/env python3
"""
Balance Monitor Service - 24/7 Multi-Chain Wallet Monitoring
Monitors wallets, alerts on changes, feeds data to trading bots
"""
import os
import asyncio
import aiohttp
import json
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger("BalanceMonitor")

app = Flask(__name__)

# RPC endpoints
RPCS = {
    "base": os.environ.get("BASE_RPC", "https://mainnet.base.org"),
    "eth": os.environ.get("ETH_RPC", "https://eth.llamarpc.com"),
    "arb": os.environ.get("ARB_RPC", "https://arb1.arbitrum.io/rpc"),
    "poly": os.environ.get("POLY_RPC", "https://polygon-rpc.com"),
}

# Explorer APIs for balance checks
APIS = {
    "eth": "https://api.etherscan.io/api?module=account&action=balance&address={}&tag=latest",
    "base": "https://api.basescan.org/api?module=account&action=balance&address={}&tag=latest",
    "arb": "https://api.arbiscan.io/api?module=account&action=balance&address={}&tag=latest",
    "poly": "https://api.polygonscan.com/api?module=account&action=balance&address={}&tag=latest",
}

# State
wallets = {}  # {address: {chain, label, last_balance, alerts}}
balance_history = []
alerts = []
monitoring = False

async def check_balance(session, chain, address):
    try:
        if chain not in APIS:
            return None
        async with session.get(APIS[chain].format(address), timeout=15) as r:
            data = await r.json()
            if data.get("status") == "1":
                return int(data["result"]) / 1e18
    except Exception as e:
        log.error(f"Balance check failed {chain}/{address[:10]}: {e}")
    return None

async def monitor_loop():
    global monitoring
    log.info("Starting balance monitor loop...")
    while monitoring:
        async with aiohttp.ClientSession() as session:
            for addr, info in wallets.items():
                bal = await check_balance(session, info["chain"], addr)
                if bal is not None:
                    prev = info.get("last_balance", 0)
                    if prev != bal:
                        change = bal - prev
                        log.info(f"{info.get('label', addr[:10])}: {prev:.6f} -> {bal:.6f} ({change:+.6f})")
                        balance_history.append({
                            "address": addr,
                            "chain": info["chain"],
                            "previous": prev,
                            "current": bal,
                            "change": change,
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        })
                        # Alert if significant change
                        if abs(change) > info.get("alert_threshold", 0.01):
                            alerts.append({
                                "type": "balance_change",
                                "address": addr,
                                "chain": info["chain"],
                                "change": change,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            })
                    wallets[addr]["last_balance"] = bal
        await asyncio.sleep(30)  # Check every 30 seconds

def start_monitor():
    global monitoring
    monitoring = True
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(monitor_loop())

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "service": "balance-monitor", "monitoring": monitoring, "wallets": len(wallets), "timestamp": datetime.now(timezone.utc).isoformat()})

@app.route('/wallets', methods=['GET', 'POST'])
def manage_wallets():
    if request.method == 'POST':
        data = request.json
        addr = data["address"].lower()
        wallets[addr] = {"chain": data.get("chain", "eth"), "label": data.get("label", ""), "alert_threshold": data.get("threshold", 0.01), "last_balance": 0}
        return jsonify({"status": "added", "address": addr})
    return jsonify({"wallets": wallets})

@app.route('/balances', methods=['GET'])
def get_balances():
    return jsonify({"balances": {a: w.get("last_balance", 0) for a, w in wallets.items()}})

@app.route('/history', methods=['GET'])
def get_history():
    return jsonify({"history": balance_history[-100:]})

@app.route('/alerts', methods=['GET'])
def get_alerts():
    return jsonify({"alerts": alerts[-50:]})

@app.route('/start', methods=['POST'])
def start():
    global monitoring
    if not monitoring:
        thread = threading.Thread(target=start_monitor, daemon=True)
        thread.start()
        return jsonify({"status": "started"})
    return jsonify({"status": "already running"})

@app.route('/stop', methods=['POST'])
def stop():
    global monitoring
    monitoring = False
    return jsonify({"status": "stopped"})

if __name__ == "__main__":
    # Auto-start monitoring
    thread = threading.Thread(target=start_monitor, daemon=True)
    thread.start()
    port = int(os.environ.get("PORT", 10000))
    log.info(f"Balance Monitor starting on port {port}")
    app.run(host="0.0.0.0", port=port)
