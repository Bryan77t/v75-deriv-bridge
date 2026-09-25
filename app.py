
from flask import Flask, request, render_template_string, jsonify
import asyncio
import json
import websockets

app = Flask(__name__)

APP_ID = 1089
BOT_ACTIVE = True

HTML_MOBILE_APP = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>V75 SMC Bot Control</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: white; margin: 0; padding: 20px; }
        .card { background: #1e293b; padding: 20px; border-radius: 16px; margin-bottom: 16px; border: 1px solid #334155; }
        .status { font-size: 1.2rem; font-weight: bold; color: #4ade80; }
        .status.off { color: #f87171; }
        .btn { width: 100%; padding: 16px; border-radius: 12px; border: none; font-size: 1rem; font-weight: bold; cursor: pointer; margin-top: 10px; }
        .btn-toggle { background: #3b82f6; color: white; }
    </style>
</head>
<body>
    <div class="card">
        <h2>V75 SMC Engine</h2>
        <p>Bot Status: <span id="statusText" class="status">ACTIVE</span></p>
        <button class="btn btn-toggle" onclick="toggleBot()">Toggle On/Off</button>
    </div>
    <div class="card">
        <h3>Live Settings</h3>
        <p>Target Symbol: <b>Volatility 75 Index (R_75)</b></p>
        <p>Max Lot Cap: <b>1.50 Lots</b></p>
        <p>Slippage Guard: <b>2.0 Pips</b></p>
    </div>
    <script>
        function toggleBot() {
            fetch('/api/toggle', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                let st = document.getElementById('statusText');
                st.innerText = data.active ? "ACTIVE" : "PAUSED";
                st.className = data.active ? "status" : "status off";
            });
        }
    </script>
</body>
</html>
"""

async def execute_deriv_trade(payload):
    token = payload.get("token")
    action = payload.get("action").upper()
    symbol = payload.get("symbol", "R_75")
    amount = payload.get("volume", 0.02)
    sl = payload.get("sl")
    tp = payload.get("tp")

    ws_url = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"authorize": token}))
        auth_res = json.loads(await ws.recv())
        if "error" in auth_res:
            raise Exception(f"Auth error: {auth_res['error']['message']}")

        contract_type = "MULTUP" if action == "BUY" else "MULTDOWN"
        prop_req = {
            "proposal": 1,
            "amount": amount,
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "symbol": symbol
        }
        await ws.send(json.dumps(prop_req))
        prop_res = json.loads(await ws.recv())
        if "error" in prop_res:
            raise Exception(f"Proposal error: {prop_res['error']['message']}")

        buy_req = {
            "buy": prop_res["proposal"]["id"],
            "price": prop_res["proposal"]["ask_price"]
        }
        limit_order = {}
        if sl: limit_order["stop_loss"] = float(sl)
        if tp: limit_order["take_profit"] = float(tp)
        if limit_order: buy_req["limit_order"] = limit_order

        await ws.send(json.dumps(buy_req))
        buy_res = json.loads(await ws.recv())
        if "error" in buy_res:
            raise Exception(f"Buy error: {buy_res['error']['message']}")

        return buy_res

@app.route('/')
def home():
    return render_template_string(HTML_MOBILE_APP)

@app.route('/webhook/deriv', methods=['POST'])
def webhook():
    global BOT_ACTIVE
    if not BOT_ACTIVE:
        return jsonify({"status": "ignored", "reason": "Bot paused from mobile dashboard"}), 200

    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "Invalid payload"}), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(execute_deriv_trade(data))
        
        return jsonify({"status": "success", "deriv_response": result}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/toggle', methods=['POST'])
def toggle():
    global BOT_ACTIVE
    BOT_ACTIVE = not BOT_ACTIVE
    return jsonify({"active": BOT_ACTIVE})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
