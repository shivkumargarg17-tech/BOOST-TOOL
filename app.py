from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import time
import hashlib
import random
from datetime import datetime

app = Flask(__name__)

# ==================== STORAGE SETUP ====================
DATA_FILE = "/tmp/tokens.json"
BOOST_HISTORY_FILE = "/tmp/boost_history.json"

def init_storage():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w') as f:
            json.dump({}, f)
    if not os.path.exists(BOOST_HISTORY_FILE):
        with open(BOOST_HISTORY_FILE, 'w') as f:
            json.dump([], f)

init_storage()

def load_tokens():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_tokens(tokens):
    with open(DATA_FILE, 'w') as f:
        json.dump(tokens, f, indent=2)

def get_user_tokens(username):
    tokens = load_tokens()
    return tokens.get(username, [])

def save_user_token(username, token, token_info):
    tokens = load_tokens()
    if username not in tokens:
        tokens[username] = []
    
    for existing in tokens[username]:
        if existing.get('token') == token:
            return False
    
    tokens[username].append({
        'token': token,
        'username_discord': token_info.get('username'),
        'nitro': token_info.get('nitro'),
        'boosts': token_info.get('boosts'),
        'added_at': datetime.now().isoformat()
    })
    save_tokens(tokens)
    return True

def remove_user_token(username, token):
    tokens = load_tokens()
    if username in tokens:
        tokens[username] = [t for t in tokens[username] if t.get('token') != token]
        save_tokens(tokens)
        return True
    return False

def save_boost_history(username, invite, target, applied):
    history = []
    if os.path.exists(BOOST_HISTORY_FILE):
        with open(BOOST_HISTORY_FILE, 'r') as f:
            history = json.load(f)
    
    history.append({
        'username': username,
        'invite': invite,
        'target': target,
        'applied': applied,
        'time': datetime.now().isoformat()
    })
    
    with open(BOOST_HISTORY_FILE, 'w') as f:
        json.dump(history[-50:], f, indent=2)

# ==================== TOKEN CHECKER ====================
def check_token(token):
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        r = requests.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=10)
        if r.status_code != 200:
            return {"valid": False, "error": f"Status {r.status_code}"}
        
        user_data = r.json()
        
        r_subs = requests.get("https://discord.com/api/v9/users/@me/billing/subscriptions", headers=headers, timeout=10)
        subscriptions = r_subs.json() if r_subs.status_code == 200 else []
        
        nitro = "No Nitro"
        for sub in subscriptions:
            sku = str(sub.get("sku_id", ""))
            if "521846918637420545" in sku:
                nitro = "Nitro Premium"
            elif "511651871736201216" in sku:
                nitro = "Nitro Basic"
        
        r_boosts = requests.get("https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers, timeout=10)
        boosts = 0
        if r_boosts.status_code == 200:
            boosts = sum(1 for s in r_boosts.json() if s.get("cooldown_ends_at") is None)
        
        return {
            "valid": True,
            "username": user_data.get("username", "Unknown"),
            "nitro": nitro,
            "boosts": boosts,
            "user_id": user_data.get("id")
        }
    except Exception as e:
        return {"valid": False, "error": str(e)[:50]}

# ==================== ROUTES ====================
@app.route('/')
def dashboard():
    user = request.args.get('user', 'default')
    return render_template('dashboard.html', user=user)

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    username = request.args.get('user', 'default')
    user_tokens = get_user_tokens(username)
    
    results = []
    for token_data in user_tokens:
        token = token_data['token']
        info = check_token(token)
        results.append({
            "token": token[:20] + "..." if len(token) > 20 else token,
            "full_token": token,
            **info
        })
    
    return jsonify(results)

@app.route('/api/tokens/add', methods=['POST'])
def add_token():
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '').strip()
    
    if not token:
        return jsonify({"error": "No token"})
    
    info = check_token(token)
    
    if not info.get('valid'):
        return jsonify({"status": "invalid", "error": info.get('error', 'Invalid token')})
    
    saved = save_user_token(username, token, info)
    
    if saved:
        print(f"[✓] {username} added token: {info.get('username')}")
        return jsonify({"status": "ok", "username": info.get('username')})
    else:
        return jsonify({"status": "exists"})

@app.route('/api/tokens/remove', methods=['POST'])
def remove_token():
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '')
    
    remove_user_token(username, token)
    return jsonify({"status": "ok"})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    username = request.form.get('user', 'default')
    file = request.files.get('file')
    
    if not file:
        return jsonify({"error": "No file"})
    
    content = file.read().decode('utf-8')
    
    if content.strip().startswith('['):
        tokens_data = json.loads(content)
        tokens = tokens_data if isinstance(tokens_data, list) else []
    else:
        tokens = [line.strip() for line in content.split('\n') if line.strip()]
    
    added = 0
    for token in tokens:
        if not token:
            continue
        info = check_token(token)
        if info.get('valid'):
            if save_user_token(username, token, info):
                added += 1
    
    return jsonify({"status": "ok", "tokens_added": added})

@app.route('/api/boost/start', methods=['POST'])
def start_boost():
    data = request.json
    username = data.get('user', 'default')
    invite = data.get('invite', '').strip()
    
    if "discord.gg/" in invite:
        invite = invite.split("discord.gg/")[-1].split("/")[0]
    
    target = int(data.get('target_boosts', 1))
    user_tokens = get_user_tokens(username)
    
    if not user_tokens:
        return jsonify({"error": "No tokens found"})
    
    valid_tokens = []
    for token_data in user_tokens:
        info = check_token(token_data['token'])
        if info['valid'] and info['boosts'] > 0:
            valid_tokens.append(info)
    
    if not valid_tokens:
        return jsonify({"error": "No tokens with boosts available"})
    
    total_boosts = sum(t['boosts'] for t in valid_tokens)
    if total_boosts < target:
        return jsonify({"error": f"Need {target} boosts, have {total_boosts}"})
    
    save_boost_history(username, invite, target, min(target, total_boosts))
    
    return jsonify({
        "status": "started", 
        "message": f"Boost process started. You have {len(valid_tokens)} tokens with {total_boosts} boosts available."
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    username = request.args.get('user', 'default')
    history = []
    if os.path.exists(BOOST_HISTORY_FILE):
        with open(BOOST_HISTORY_FILE, 'r') as f:
            all_history = json.load(f)
            history = [h for h in all_history if h.get('username') == username]
    
    return jsonify(history)

# ==================== ADMIN PANEL - SEE ALL TOKENS ====================
# 🔐 CHANGE THIS TO YOUR OWN SECRET PASSWORD 🔐
ADMIN_SECRET = "mysecret123"

@app.route('/admin/tokens')
def admin_tokens():
    secret = request.args.get('secret', '')
    
    if secret != ADMIN_SECRET:
        return "Unauthorized. Use ?secret=mysecret123", 401
    
    tokens = load_tokens()
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin - All Tokens</title>
        <style>
            body { font-family: monospace; background: #0a0a1a; color: #fff; padding: 20px; }
            h1 { color: #5865f2; }
            .user { background: #1a1a2e; margin: 20px 0; padding: 15px; border-radius: 10px; }
            .user-name { color: #faa81a; font-size: 20px; margin-bottom: 10px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { text-align: left; padding: 8px; border-bottom: 1px solid #2a2a3e; }
            th { color: #5865f2; }
            .token { font-size: 11px; word-break: break-all; }
            .copy-btn { background: #5865f2; border: none; color: white; padding: 2px 8px; border-radius: 4px; cursor: pointer; }
            .copy-all { background: #23a55a; margin-bottom: 20px; padding: 10px 20px; font-size: 16px; }
        </style>
    </head>
    <body>
        <h1>🔐 Admin Panel - All Tokens</h1>
        <button class="copy-all" onclick="copyAllTokens()">📋 Copy All Tokens</button>
    """
    
    all_tokens_for_copy = []
    
    for username, user_tokens in tokens.items():
        all_tokens_for_copy.extend([t.get('token') for t in user_tokens])
        
        html += f"""
        <div class="user">
            <div class="user-name">👤 {username} ({len(user_tokens)} tokens)</div>
            <table>
                <tr>
                    <th>Discord Username</th>
                    <th>Nitro</th>
                    <th>Boosts</th>
                    <th>Token</th>
                    <th>Action</th>
                </tr>
        """
        for t in user_tokens:
            html += f"""
                <tr>
                    <td>{t.get('username_discord', 'Unknown')}</td>
                    <td>{t.get('nitro', 'No Nitro')}</td>
                    <td>{t.get('boosts', 0)}</td>
                    <td class="token">{t.get('token', '')[:50]}...</td>
                    <td><button class="copy-btn" onclick="copyToClipboard('{t.get('token', '')}')">Copy</button></td>
                </tr>
            """
        html += "</table></div>"
    
    html += f"""
        <script>
        function copyToClipboard(text) {{
            navigator.clipboard.writeText(text);
            alert('Token copied!');
        }}
        function copyAllTokens() {{
            let allTokens = {json.dumps(all_tokens_for_copy)};
            navigator.clipboard.writeText(allTokens.join('\\n'));
            alert(allTokens.length + ' tokens copied!');
        }}
        </script>
    </body>
    </html>
    """
    
    return html

@app.route('/admin/raw')
def admin_raw():
    secret = request.args.get('secret', '')
    
    if secret != ADMIN_SECRET:
        return {"error": "Unauthorized"}, 401
    
    return jsonify(load_tokens())

@app.route('/health')
def health():
    return jsonify({"status": "alive", "time": datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*60)
    print("🚀 Discord Boost Dashboard")
    print("="*60)
    print(f"\n🔐 ADMIN PANEL:")
    print(f"   https://your-url.onrender.com/admin/tokens?secret=mysecret123")
    print(f"\n📁 Raw JSON:")
    print(f"   https://your-url.onrender.com/admin/raw?secret=mysecret123")
    print("\n⚠️  To change your secret, edit ADMIN_SECRET in app.py")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port)
