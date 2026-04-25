from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
import json
import os
import time
import hashlib
import random
import threading
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ==================== SUPABASE SETUP ====================
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# Check if Supabase is configured
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)

if SUPABASE_ENABLED:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("[✓] Supabase connected")
    except Exception as e:
        print(f"[!] Supabase error: {e}")
        SUPABASE_ENABLED = False
else:
    print("[!] Supabase not configured - tokens will not persist")

# ==================== ADMIN SECRET ====================
ADMIN_SECRET = os.environ.get('ADMIN_SECRET', 'admin123')

# ==================== TOKEN CHECKER ====================
def check_token(token):
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me"
    }
    
    try:
        r = requests.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=15)
        
        if r.status_code == 200:
            user_data = r.json()
            premium_type = user_data.get("premium_type", 0)
            
            if premium_type == 2:
                nitro = "Nitro Premium"
            elif premium_type == 1:
                nitro = "Nitro Classic"
            else:
                nitro = "No Nitro"
            
            return {
                "valid": True,
                "username": user_data.get("username", "Unknown"),
                "global_name": user_data.get("global_name", ""),
                "email": user_data.get("email", ""),
                "verified": user_data.get("verified", False),
                "nitro": nitro,
                "premium_type": premium_type,
                "boosts": 0,
                "user_id": user_data.get("id")
            }
        elif r.status_code == 401:
            return {"valid": False, "error": "Invalid Token"}
        elif r.status_code == 403:
            return {"valid": False, "error": "Locked Account"}
        else:
            return {"valid": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"valid": False, "error": str(e)[:50]}

# ==================== USER STORAGE (In-memory fallback) ====================
# Simple in-memory storage (resets on restart)
user_tokens_memory = {}

def get_user_tokens(username):
    if SUPABASE_ENABLED:
        try:
            response = supabase.table('tokens').select('*').eq('username', username).execute()
            return response.data if response.data else []
        except:
            return user_tokens_memory.get(username, [])
    else:
        return user_tokens_memory.get(username, [])

def add_user_token(username, token, token_info):
    if SUPABASE_ENABLED:
        try:
            supabase.table('tokens').insert({
                'username': username,
                'token': token,
                'added_at': datetime.now().isoformat(),
                'is_valid': True,
                'nitro_type': token_info.get('nitro', 'No Nitro'),
                'boosts_available': token_info.get('boosts', 0),
                'username_discord': token_info.get('username', 'Unknown')
            }).execute()
            return True
        except:
            pass
    
    if username not in user_tokens_memory:
        user_tokens_memory[username] = []
    user_tokens_memory[username].append(token)
    return True

def delete_user_token(username, token):
    if SUPABASE_ENABLED:
        try:
            supabase.table('tokens').delete().eq('username', username).eq('token', token).execute()
            return True
        except:
            pass
    
    if username in user_tokens_memory:
        user_tokens_memory[username] = [t for t in user_tokens_memory[username] if t != token]
    return True

# ==================== ROUTES ====================
@app.route('/')
def dashboard():
    user = request.args.get('user', 'default')
    return render_template('dashboard.html', user=user)

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

@app.route('/api/admin/verify', methods=['GET'])
def admin_verify():
    secret = request.args.get('secret', '')
    return jsonify({"authorized": secret == ADMIN_SECRET})

@app.route('/api/admin/all_data', methods=['GET'])
def admin_all_data():
    secret = request.args.get('secret', '')
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    users = {}
    if SUPABASE_ENABLED:
        try:
            response = supabase.table('tokens').select('*').execute()
            for token_data in response.data or []:
                username = token_data['username']
                if username not in users:
                    users[username] = {'tokens': [], 'valid': 0, 'invalid': 0}
                users[username]['tokens'].append(token_data)
        except:
            pass
    else:
        for username, tokens in user_tokens_memory.items():
            users[username] = {'tokens': tokens, 'valid': 0, 'invalid': 0}
    
    return jsonify({
        'users': [{'username': k, 'token_count': len(v['tokens'])} for k, v in users.items()],
        'total_tokens': sum(len(v['tokens']) for v in users.values())
    })

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    username = request.args.get('user', 'default')
    tokens = get_user_tokens(username)
    
    results = []
    for token in tokens:
        if isinstance(token, dict):
            token = token.get('token', '')
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
    
    if info.get('valid'):
        add_user_token(username, token, info)
        return jsonify({"status": "ok", "username": info.get('username')})
    else:
        return jsonify({"status": "invalid", "error": info.get('error')})

@app.route('/api/tokens/remove', methods=['POST'])
def remove_token():
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '')
    
    delete_user_token(username, token)
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
        if token:
            info = check_token(token)
            if info.get('valid'):
                add_user_token(username, token, info)
                added += 1
    
    return jsonify({"status": "ok", "tokens_added": added})

@app.route('/api/boost/start', methods=['POST'])
def start_boost():
    data = request.json
    username = data.get('user', 'default')
    invite = data.get('invite', '').strip()
    target = int(data.get('target_boosts', 1))
    
    if "discord.gg/" in invite:
        invite = invite.split("discord.gg/")[-1].split("/")[0]
    
    tokens = get_user_tokens(username)
    
    valid_tokens = []
    for token in tokens:
        if isinstance(token, dict):
            token = token.get('token', '')
        info = check_token(token)
        if info.get('valid'):
            valid_tokens.append({'token': token, 'username': info.get('username')})
    
    if not valid_tokens:
        return jsonify({"error": "No valid tokens"})
    
    return jsonify({"status": "started", "message": f"Boost started with {len(valid_tokens)} tokens"})

@app.route('/health')
def health():
    return jsonify({"status": "alive", "time": datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n🚀 Dashboard running on port {port}")
    app.run(host='0.0.0.0', port=port)
