from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import time
import random
import threading
from datetime import datetime

app = Flask(__name__)

# ==================== STORAGE ====================
# Use /tmp for Render free tier (ephemeral but works)
DATA_DIR = "/tmp/discord_booster"
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

os.makedirs(DATA_DIR, exist_ok=True)

# Load/Save functions
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

# ==================== HEADERS (Anti-Detection) ====================
def get_headers(token=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me"
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
        
        # Check boosts
        random_delay()
        r_boosts = requests.get("https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers, timeout=10)
        boosts = 0
        if r_boosts.status_code == 200:
            boosts = sum(1 for s in r_boosts.json() if s.get("cooldown_ends_at") is None)
        
        # Check Nitro
        random_delay()
        r_subs = requests.get("https://discord.com/api/v9/users/@me/billing/subscriptions", headers=headers, timeout=10)
        nitro = "No Nitro"
        if r_subs.status_code == 200:
            for sub in r_subs.json():
                if "premium" in str(sub.get("sku_id", "")):
                    nitro = "Nitro Premium"
                    break
                elif "basic" in str(sub.get("sku_id", "")):
                    nitro = "Nitro Basic"
                    break
        
        return {
            "valid": True,
            "username": user_data.get("username", "Unknown"),
            "nitro": nitro,
            "boosts": boosts
        }
    except Exception as e:
        return {"valid": False, "error": str(e)[:50]}

# ==================== WORKING BOOST FUNCTIONS ====================
def join_server(token, invite_code):
    """Join a server using invite code"""
    try:
        headers = get_headers(token)
        
        # First resolve invite
        r = requests.get(f"https://discord.com/api/v9/invites/{invite_code}", headers=headers, timeout=10)
        if r.status_code != 200:
            return False, None
        
        guild_id = r.json().get("guild", {}).get("id")
        if not guild_id:
            return False, None
        
        random_delay()
        
        # Join
        r2 = requests.post(f"https://discord.com/api/v9/invites/{invite_code}", headers=headers, json={}, timeout=10)
        return r2.status_code == 200, guild_id
        
    except:
        return False, None

def apply_boost(token, guild_id):
    """Apply a single boost"""
    try:
        headers = get_headers(token)
        random_delay()
        
        r = requests.post(f"https://discord.com/api/v9/guilds/{guild_id}/premium/subscriptions", headers=headers, json={}, timeout=10)
        return r.status_code in [200, 201]
    except:
        return False

# ==================== ROUTES ====================
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
    
    # Check if token is valid
    info = check_token(token)
    if not info['valid']:
        return jsonify({"status": "invalid", "error": "Token is invalid"})
    
    # Save token
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
    
    # Clean invite code
    if "discord.gg/" in invite:
        invite = invite.split("discord.gg/")[-1].split("/")[0]
    
    # Get user's tokens
    tokens_data = load_tokens()
    user_tokens = tokens_data.get(user, [])
    
    if not user_tokens:
        return jsonify({"error": "No tokens found. Add tokens first!"})
    
    # Find valid tokens with boosts
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
    
    # Start boosting in background thread
    def do_boosting():
        results = []
        boosts_applied = 0
        
        for bt in boostable_tokens:
            if boosts_applied >= target_boosts:
                break
            
            # Join server
            success, guild_id = join_server(bt['token'], invite)
            if not success:
                results.append(f"{bt['username']}: Failed to join server")
                continue
            
            # Apply boosts
            boosts_to_apply = min(bt['boosts'], target_boosts - boosts_applied)
            applied = 0
            
            for i in range(boosts_to_apply):
                if apply_boost(bt['token'], guild_id):
                    applied += 1
                    boosts_applied += 1
                time.sleep(random.uniform(2, 4))  # Delay between boosts
            
            results.append(f"{bt['username']}: Applied {applied} boosts")
            time.sleep(random.uniform(2, 3))  # Delay between tokens
        
        # Save to history
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
    
    # Run in background
    thread = threading.Thread(target=do_boosting)
    thread.start()
    
    return jsonify({
        "status": "started", 
        "message": f"Boosting started! Using {len(boostable_tokens)} tokens with {total_available} boosts available."
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    user = request.args.get('user', 'default')
    history = load_history()
    user_history = [h for h in history if h.get('user') == user]
    return jsonify(user_history)

@app.route('/health')
def health():
    return jsonify({"status": "alive"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
