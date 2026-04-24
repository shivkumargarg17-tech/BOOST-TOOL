from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
import os
import time
import json
from datetime import datetime
from supabase import create_client, Client

app = Flask(__name__)
CORS(app)

# ==================== SUPABASE SETUP ====================
# Read from environment variables (Render will provide these)
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://mzzdgtteervzfrhakkbe.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# Validate key exists
if not SUPABASE_KEY:
    print("ERROR: SUPABASE_KEY environment variable not set!")
    print("Please add it in Render dashboard: Environment -> Environment Variables")
    # Don't crash, but log error
else:
    print(f"✓ Supabase configured with URL: {SUPABASE_URL}")

# Only create client if key exists
if SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    supabase = None
    print("⚠️ Supabase client not initialized - missing API key")

# ==================== TOKEN CHECKER ====================
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
        
        # Check boosts
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

# Helper to check if supabase is available
def db_available():
    if not supabase:
        return False
    return True

# ==================== ROUTES ====================
@app.route('/')
def dashboard():
    user = request.args.get('user', 'default')
    return render_template('dashboard.html', user=user)

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    if not db_available():
        return jsonify({"error": "Database not configured. Please set SUPABASE_KEY environment variable."})
    
    username = request.args.get('user', 'default')
    
    response = supabase.table('tokens').select('*').eq('username', username).execute()
    tokens = response.data if response.data else []
    
    results = []
    for token_data in tokens:
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
    if not db_available():
        return jsonify({"error": "Database not configured. Please set SUPABASE_KEY environment variable."})
    
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '').strip()
    
    if not token:
        return jsonify({"error": "No token"})
    
    # Check if token already exists
    existing = supabase.table('tokens').select('*').eq('username', username).eq('token', token).execute()
    if existing.data:
        return jsonify({"status": "exists"})
    
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
        
        return jsonify({"status": "ok", "username": info['username']})
    else:
        return jsonify({"status": "invalid", "error": info.get('error', 'Invalid token')})

@app.route('/api/tokens/remove', methods=['POST'])
def remove_token():
    if not db_available():
        return jsonify({"error": "Database not configured."})
    
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '')
    
    supabase.table('tokens').delete().eq('username', username).eq('token', token).execute()
    
    return jsonify({"status": "ok"})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if not db_available():
        return jsonify({"error": "Database not configured."})
    
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
        
        existing = supabase.table('tokens').select('*').eq('username', username).eq('token', token).execute()
        if existing.data:
            continue
        
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

@app.route('/api/history', methods=['GET'])
def get_history():
    if not db_available():
        return jsonify([])
    
    username = request.args.get('user', 'default')
    
    response = supabase.table('boost_history').select('*').eq('username', username).order('boosted_at', desc=True).execute()
    return jsonify(response.data if response.data else [])

@app.route('/api/admin/tokens', methods=['GET'])
def admin_tokens():
    if not db_available():
        return jsonify({"error": "Database not configured."})
    
    secret = request.args.get('secret', '')
    
    if secret != 'admin123':
        return jsonify({"error": "Unauthorized"})
    
    response = supabase.table('tokens').select('*').execute()
    return jsonify(response.data if response.data else [])

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    if not db_available():
        return jsonify({"error": "Database not configured."})
    
    secret = request.args.get('secret', '')
    
    if secret != 'admin123':
        return jsonify({"error": "Unauthorized"})
    
    response = supabase.table('tokens').select('*').execute()
    tokens = response.data if response.data else []
    
    users = {}
    for token in tokens:
        username = token['username']
        if username not in users:
            users[username] = []
        users[username].append(token)
    
    return jsonify({
        "total_tokens": len(tokens),
        "users": len(users),
        "per_user": {u: len(t) for u, t in users.items()}
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "alive",
        "time": datetime.now().isoformat(),
        "supabase_configured": bool(SUPABASE_KEY)
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
