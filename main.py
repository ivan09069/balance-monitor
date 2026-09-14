#!/usr/bin/env python3
"""
Balance Monitor Service - WITH AUTHENTICATION
"""
import os
import asyncio
import aiohttp
import json
import logging
import functools
import hashlib
import hmac
from datetime import datetime, timezone
from flask import Flask, request, jsonify
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger("BalanceMonitor")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16384

API_KEY = os.environ.get("API_KEY", "")

def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        key = request.headers.get('X-API-Key', '')
        if len(API_KEY) < 32:
            return jsonify({"error": "API authentication not configured"}), 503
        def matches(value):
            return hmac.compare_digest(hashlib.sha256(value.encode()).digest(), hashlib.sha256(API_KEY.encode()).digest())
        bearer = auth[7:] if auth.startswith('Bearer ') else ''
        if matches(bearer) or matches(key):
            return f(*args, **kwargs)
        return jsonify({"error": "Unauthorized"}), 401
    return decorated

APIS = {
    "eth": "https://api.etherscan.io/api?module=account&action=balance&address={}&tag=latest",
    "base": "https://api.basescan.org/api?module=account&action=balance&address={}&tag=latest",
    "arb": "https://api.arbiscan.io/api?module=account&action=balance&address={}&tag=latest",
    "poly": "https://api.polygonscan.com/api?module=account&action=balance&address={}&tag=latest",
}

wallets = {}
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
        log.error(f"Balance check failed: {e}")
    return None

async def monitor_loop():
    global monitoring
    log.info("Monitor loop started")
    while monitoring:
        async with aiohttp.ClientSession() as session:
            for addr, info in wallets.items():
                bal = await check_balance(session, info["chain"], addr)
                if bal is not None:
                    prev = info.get("last_balance", 0)
                    if prev != bal:
                        change = bal - prev
                        log.info(f"{info.get('label', addr[:10])}: {prev:.6f} -> {bal:.6f}")
                        balance_history.append({"address": addr, "chain": info["chain"], "previous": prev, "current": bal, "change": change, "timestamp": datetime.now(timezone.utc).isoformat()})
                        if abs(change) > info.get("alert_threshold", 0.01):
                            alerts.append({"type": "balance_change", "address": addr, "change": change, "timestamp": datetime.now(timezone.utc).isoformat()})
                    wallets[addr]["last_balance"] = bal
        await asyncio.sleep(30)

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
@require_auth
def manage_wallets():
    if request.method == 'POST':
        data = request.json
        addr = data["address"].lower()
        wallets[addr] = {"chain": data.get("chain", "eth"), "label": data.get("label", ""), "alert_threshold": data.get("threshold", 0.01), "last_balance": 0}
        return jsonify({"status": "added", "address": addr})
    return jsonify({"wallets": wallets})

@app.route('/balances', methods=['GET'])
@require_auth
def get_balances():
    return jsonify({"balances": {a: w.get("last_balance", 0) for a, w in wallets.items()}})

@app.route('/history', methods=['GET'])
@require_auth
def get_history():
    return jsonify({"history": balance_history[-100:]})

@app.route('/alerts', methods=['GET'])
@require_auth
def get_alerts():
    return jsonify({"alerts": alerts[-50:]})

@app.route('/trade-alert', methods=['POST'])
@require_auth
def trade_alert():
    """Receive authenticated trade notifications from Trade Executor."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    log.info("Authenticated trade alert received")
    alerts.append({
        "type": "trade_executed",
        "trade": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return jsonify({"status": "received"})

@app.route('/start', methods=['POST'])
@require_auth
def start():
    global monitoring
    if not monitoring:
        thread = threading.Thread(target=start_monitor, daemon=True)
        thread.start()
        return jsonify({"status": "started"})
    return jsonify({"status": "already running"})

@app.route('/stop', methods=['POST'])
@require_auth
def stop():
    global monitoring
    monitoring = False
    return jsonify({"status": "stopped"})

if __name__ == "__main__":
    thread = threading.Thread(target=start_monitor, daemon=True)
    thread.start()
    port = int(os.environ.get("PORT", 10000))
    log.info(f"Balance Monitor (AUTH ENABLED) starting on port {port}")
    app.run(host="0.0.0.0", port=port)
