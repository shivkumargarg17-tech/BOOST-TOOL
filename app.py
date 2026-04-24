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

# ==================== ROTATING HEADERS (ANTI-DETECTION) ====================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

def get_headers(token=None):
    """Generate fresh headers for each request"""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Content-Type": "application/json",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-Debug-Options": "bugReporterEnabled",
        "X-Discord-Locale": "en-US",
        "X-Discord-Timezone": "America/New_York"
    }
    if token:
        headers["Authorization"] = token
    return headers

def random_delay(min_sec=1.5, max_sec=4.0):
    """Human-like random delay - CRITICAL for avoiding detection"""
    time.sleep(random.uniform(min_sec, max_sec))

# ==================== TOKEN CHECKER ====================
def check_token(token):
    """Verify token with stealth headers"""
    try:
        headers = get_headers(token)
        random_delay(0.5, 1.2)
        
        r = requests.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=15)
        
        if r.status_code != 200:
            return {"valid": False, "error": f"Status {r.status_code}"}
        
        user_data = r.json()
        
        # Check boosts
        random_delay(0.8, 1.5)
        r_boosts = requests.get("https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers, timeout=15)
        boosts = 0
        if r_boosts.status_code == 200:
            boosts = sum(1 for s in r_boosts.json() if s.get("cooldown_ends_at") is None)
        
        # Check Nitro
        random_delay(0.5, 1.0)
        r_subs = requests.get("https://discord.com/api/v9/users/@me/billing/subscriptions", headers=headers, timeout=15)
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

# ==================== STEALTH BOOST FUNCTIONS ====================
def join_server_stealth(token, invite_code):
    """
    Join server with full stealth - uses fresh headers and realistic delays
    Returns: (success, guild_id, error_message)
    """
    try:
        # Step 1: Resolve invite with fresh headers
        headers = get_headers(token)
        random_delay(1.0, 2.5)  # Human delay before resolve
        
        invite_resp = requests.get(f"https://discord.com/api/v9/invites/{invite_code}", headers=headers, timeout=15)
        
        if invite_resp.status_code == 404:
            return False, None, "Invalid invite code"
        
        if invite_resp.status_code == 429:
            return False, None, "Rate limited - wait and try again"
        
        if invite_resp.status_code != 200:
            return False, None, f"Invite resolve failed: {invite_resp.status_code}"
        
        invite_data = invite_resp.json()
        guild_id = invite_data.get("guild", {}).get("id")
        
        if not guild_id:
            return False, None, "Could not get guild ID"
        
        # Step 2: Random delay before joining
        random_delay(1.5, 3.0)
        
        # Step 3: Join the server with fresh headers
        join_headers = get_headers(token)
        join_resp = requests.post(
            f"https://discord.com/api/v9/invites/{invite_code}",
            headers=join_headers,
            json={},
            timeout=20
        )
        
        if join_resp.status_code == 200:
            return True, guild_id, None
        elif join_resp.status_code == 401:
            return False, None, "Token invalidated - Discord flagged this action"
        elif join_resp.status_code == 403:
            return False, None, "Cannot join - server may be full or invite expired"
        elif join_resp.status_code == 429:
            return False, None, "Rate limited - too many requests"
        else:
            return False, None, f"Join failed: {join_resp.status_code}"
            
    except Exception as e:
        return False, None, str(e)[:50]

def apply_boost_stealth(token, guild_id):
    """Apply a single boost with stealth"""
    try:
        headers = get_headers(token)
        random_delay(2.0, 4.0)  # Longer delay for boost action
        
        boost_resp = requests.post(
            f"https://discord.com/api/v9/guilds/{guild_id}/premium/subscriptions",
            headers=headers,
            json={},
            timeout=20
        )
        
        if boost_resp.status_code in [200, 201]:
            return True, None
        elif boost_resp.status_code == 401:
            return False, "Token invalidated during boost"
        elif boost_resp.status_code == 403:
            return False, "No boosts available on this account"
        elif boost_resp.status_code == 429:
            return False, "Rate limited - too many boost attempts"
        else:
            return False, f"Boost failed: {boost_resp.status_code}"
            
    except Exception as e:
        return False, str(e)[:50]

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
    
    # Clean invite code
    if "discord.gg/" in invite:
        invite = invite.split("discord.gg/")[-1].split("/")[0]
    if "discord.com/invite/" in invite:
        invite = invite.split("discord.com/invite/")[-1].split("/")[0]
    
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
    
    # Start boosting in background
    def do_boosting():
        results = []
        boosts_applied = 0
        
        for bt in boostable_tokens:
            if boosts_applied >= target_boosts:
                break
            
            # Join server with stealth
            success, guild_id, error = join_server_stealth(bt['token'], invite)
            
            if not success:
                results.append(f"❌ {bt['username']}: {error}")
                if "401" in error or "invalidated" in error.lower():
                    # Token was revoked - remove it from storage
                    tokens_data = load_tokens()
                    if user in tokens_data and bt['token'] in tokens_data[user]:
                        tokens_data[user].remove(bt['token'])
                        save_tokens(tokens_data)
                    results.append(f"⚠️ Token for {bt['username']} was revoked and removed")
                continue
            
            results.append(f"✅ {bt['username']}: Joined server")
            random_delay(2.0, 5.0)
            
            # Apply boosts
            boosts_to_apply = min(bt['boosts'], target_boosts - boosts_applied)
            applied = 0
            
            for i in range(boosts_to_apply):
                boost_success, boost_error = apply_boost_stealth(bt['token'], guild_id)
                
                if boost_success:
                    applied += 1
                    boosts_applied += 1
                    results.append(f"  ✨ Applied boost #{i+1}")
                else:
                    results.append(f"  ⚠️ Boost failed: {boost_error}")
                    if "invalidated" in str(boost_error).lower():
                        break
                
                random_delay(3.0, 6.0)  # Longer delay between boosts
            
            results.append(f"📊 {bt['username']}: Applied {applied}/{boosts_to_apply} boosts")
            random_delay(2.0, 4.0)
        
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
    
    thread = threading.Thread(target=do_boosting)
    thread.start()
    
    return jsonify({
        "status": "started",
        "message": f"Boosting started with {len(boostable_tokens)} tokens. Results will appear in history."
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
