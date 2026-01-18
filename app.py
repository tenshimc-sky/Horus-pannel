from flask import abort, Flask, render_template, request, redirect, jsonify, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from mcrcon import MCRcon
from mcstatus import JavaServer
from datetime import datetime
import requests
import random
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "Horus_Panel_4866/*-_7455_GHUIdfg"

# --- CONFIG ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///admin_panel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Identifiants RCON
RCON_DATA = {'host': '91.197.6.25', 'pass': 'ghui59AHGH*/65qfg', 'port': 47098}

# Hiérarchie des grades (basée sur tes logs LuckPerms)
RANK_WEIGHTS = {
    'vanibels': 300,
    'gerant': 200, 'administrateur': 190, 'responsable': 180, 'haut-staff': 175,
    'developpeur': 170, 'graphiste': 160, 'builder': 150, 'creation': 140,
    'communication': 130, 's-modo': 130, 'operateur': 125, 'moderateur_prime': 122,
    'moderateur': 120, 'assistant_prime': 115, 'assistant': 110, 'staff': 105,
    'superstar': 50, 'divin_prime': 47, 'divin': 45, 'empereur_prime': 45,
    'empereur': 40, 'shogun_prime': 35, 'shogun': 30, 'bushi_prime': 25,
    'bushi': 20, 'daymio_prime': 15, 'daymio': 10, 'default_prime': 5, 'default': 0
}

# --- NOUVEAU MODÈLE ---
class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    staff_name = db.Column(db.String(50))
    action_type = db.Column(db.String(20)) # CMD, RANK, WARP, LOGIN
    details = db.Column(db.String(250))

# --- FONCTION POUR ENREGISTRER UN LOG ---
def add_log(action, details):
    new_log = Log(staff_name=current_user.username, action_type=action, details=details)
    db.session.add(new_log)
    db.session.commit()

# --- MODELES ---
# --- 1. D'abord tes modèles ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    rank = db.Column(db.String(50), default='default')
    is_approved = db.Column(db.Boolean, default=True)

# --- 2. Ensuite la fonction de création auto ---
def setup_initial_admin():
    with app.app_context():
        db.create_all()
        # On vérifie si Vanibels existe
        admin = db.session.execute(db.select(User).filter_by(username="Vanibels")).scalar_one_or_none()
        
        if not admin:
            print("(!) Création du compte Vanibels...")
            hashed_pw = generate_password_hash("ton_mot_de_passe", method='pbkdf2:sha256')
            
            new_admin = User(
                username="Vanibels",
                password=hashed_pw,
                rank="vanibels",
                is_approved=True
            )
            db.session.add(new_admin)
            db.session.commit()
            print("(v) Compte Vanibels prêt.")

# --- 3. Enfin l'appel (TOUJOURS après la classe User) ---
setup_initial_admin()
class AdminWarp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    coords = db.Column(db.String(100))
    world = db.Column(db.String(50), default='admin')

with app.app_context():
    db.create_all()
    # Création forcée de Vanibels
    if not User.query.filter_by(username="Vanibels").first():
        admin = User(username="Vanibels", password="G58BLxu8v9", is_approved=True, rank='gerant')
        db.session.add(admin)
        db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def send_discord_code(user_discord_id, code):
    token = "MTM4Njc0NzI2ODA5NDQ5Njg2OA.GUHgdL.UtXGamNWoN0XO98iU16hZlREzHmYS-D7MlXZ6w"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    
    chan_res = requests.post("https://discord.com/api/v10/users/@me/channels", 
                             json={"recipient_id": user_discord_id}, headers=headers)
    
    if chan_res.status_code == 200:
        channel_id = chan_res.json()['id']
        msg_data = {
            "content": f"🛡️ **[PANEL Horus]**\nVoici ton code de sécurité : `{code}`\nCe code expire dans 5 minutes."
        }
        requests.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", 
                      json=msg_data, headers=headers)
        
@app.before_request
def monitor_ip():
    if current_user.is_authenticated:
        # On stocke l'IP dans la session lors de la première connexion
        if 'last_ip' not in session:
            session['last_ip'] = request.remote_addr
        
        # Si l'IP change (même d'un chiffre), on déconnecte tout
        if session['last_ip'] != request.remote_addr:
            logout_user()
            session.clear()
            return redirect(url_for('login'))
        
@app.before_request
def check_ip_session():
    if current_user.is_authenticated:
        current_ip = request.remote_addr 
        if 'user_ip' not in session:
            session['user_ip'] = current_ip
        elif session['user_ip'] != current_ip:
            logout_user()
            session.clear()
            flash("Sécurité : Votre IP a changé. Reconnexion requise.")
            return redirect(url_for('login'))
        
def send_rcon(cmd):
    try:
        with MCRcon(RCON_DATA['host'], RCON_DATA['pass'], port=RCON_DATA['port']) as mcr:
            return mcr.command(cmd)
    except: return "§cErreur: Serveur Inaccessible"

# --- ROUTES ---

@app.route('/')
@login_required
def dashboard():
    try:
        server = JavaServer.lookup("beta.tenshimc.fr:25565")
        status = server.status()
        server_info = {"online": True, "players_online": status.players.online, "players_max": status.players.max, "version" : status.version.name}
        players = [p.name for p in status.players.sample] if status.players.sample else []
    except:
        server_info = {"online": False, "players_online": 0, "players_max": -1}
        players = []
    warps = AdminWarp.query.all()
    staff_list = User.query.filter(User.username != "Vanibels", User.is_approved == True).all()
    pending_list = User.query.filter_by(is_approved=False).all()
    return render_template('dashboard.html',server=server_info, staff_members=staff_list, pending=pending_list, ranks=list(RANK_WEIGHTS.keys()), warps=warps)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            if user.is_approved:
                login_user(user)
                add_log("AUTH", f"Connexion réussie")
                return redirect(url_for('dashboard'))
            else:
                flash("🛡️ Accès Horus : Votre compte est en attente de validation.")
        else:
            flash("❌ Identifiants incorrects.") 
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not User.query.filter_by(username=username).first():
            hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User(
                username=username, 
                password=hashed_pw,
                is_approved=False # Doit être validé par Vanibels
            )
            db.session.add(new_user)
            db.session.commit()
            flash("✅ Demande envoyée au Panel Horus. En attente de validation.")
            return redirect(url_for('login'))
        else:
            flash("⚠️ Ce pseudo est déjà utilisé.")
    return render_template('register.html')

@app.route('/console_handler', methods=['POST'])
@login_required
def console_handler():
    msg = request.form.get('message').strip()
    is_button = request.form.get('is_button') == 'true'
    if not msg: return jsonify({"status": "empty"})
    # --- RESTRICTION SUPER-MODO ---
    if current_user.rank == "s-modo" and not is_button:
        return {"user": "SYSTÈME", "msg": msg, "res": "❌ Erreur: Ton rang ne te permet pas de taper des commandes manuelles. Utilise les boutons."}
    if current_user.rank == "developpeur" and not is_button:
        return {"user": "SYSTÈME", "msg": msg, "res": "❌ Erreur: Ton rang ne te permet pas de taper des commandes manuelles. Utilise les boutons."}
    # --- RESTRICTION RESPONSABLE ---
    forbidden_cmds = ["/stop", "/op", "/deop", "*/stop", "*/op", "*/deop", "/lp", "/luckperms", "*/lp", "*/luckperms"]
    if current_user.rank == "responsable":
        for forbidden in forbidden_cmds:
            if msg.lower().startswith(forbidden):
                return {"user": "SYSTÈME", "msg": msg, "res": "❌ Erreur: Commande interdite pour les Responsables."}
    if current_user.rank != "s-modo" and current_user.rank != "developpeur" and current_user.rank != "responsable" and current_user.rank != "vanibels" and current_user.rank != "gerant" and current_user.rank != "administrateur":
        return {"user": "SYSTÈME", "msg": msg, "res": "❌ Erreur: Commande interdite pour ton rang."}
    # --- TRAITEMENT DES COMMANDES ---
    if msg.startswith('*/'):
        command = msg[2:]
        res = send_rcon(command)
        add_log("CONSOLE", msg)
        return jsonify({"type": "cmd", "user": "CONSOLE", "msg": command, "res": res})
    elif msg.startswith('/'):
        command_raw = msg[1:]
        sudo_command = f"sudo {current_user.username} {command_raw}"
        res = send_rcon(sudo_command)
        add_log("CONSOLE", msg)
        return jsonify({"type": "sudo", "user": current_user.username, "msg": msg, "res": res})
    else:
        rank = current_user.rank
        if rank == "vanibels":
            rank = "gérant"
        command = f'say §b[{rank}] §f{current_user.username}§7: {msg}'
        send_rcon(command)
        add_log("CONSOLE", msg)
        return jsonify({"type": "say", "user": current_user.username, "msg": msg})

@app.route('/rank_action', methods=['POST'])
@login_required
def rank_action():
    target = request.form.get('target')
    new_rank = request.form.get('rank')
    my_weight = RANK_WEIGHTS.get(current_user.rank, 0)
    target_weight = RANK_WEIGHTS.get(new_rank, 0)
    if my_weight == RANK_WEIGHTS.get('S-MODO', 130) and new_rank == 'operateur':
        add_log("RANK", f"A essayé de mettre {target} au grade {new_rank}")
        return jsonify({"response": "§cAction interdite."})
    if new_rank in ['gerant', 'administrateur'] and current_user.username != "Vanibels":
        add_log("RANK", f"A essayé de mettre {target} au grade {new_rank}")
        return jsonify({"response": "§cAction interdite."})
    if target_weight >= my_weight and current_user.username != "Vanibels":
        add_log("RANK", f"A essayé de mettre {target} au grade {new_rank}")
        return jsonify({"response": "§cTu ne peux pas rank au dessus de toi."})
    res = send_rcon(f"lp user {target} parent set {new_rank}")
    add_log("RANK", f"A mis {target} au grade {new_rank}")
    return jsonify({"response": res})

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/approve/<int:uid>')
@login_required
def approve(uid):
    if current_user.rank in ['vanibels', 'gerant', 'administrateur', 'responsable']:
        u = User.query.get(uid)
        u.is_approved = True
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_user/<int:uid>')
@login_required
def delete_user(uid):
    if current_user.rank in ['vanibels', 'gerant', 'administrateur', 'responsable']:
        u = User.query.get(uid)
        if u and u.username != "Vanibels":
            db.session.delete(u)
            db.session.commit()
            add_log("USER_DEL", f"A refusé/supprimé le compte de {u.username}")
    return redirect(url_for('dashboard'))

@app.route('/add_warp', methods=['POST'])
@login_required
def add_warp():
    name = request.form.get('name')
    world = request.form.get('world')
    x = request.form.get('x')
    y = request.form.get('y')
    z = request.form.get('z')
    
    if name and x and y and z:
        new_warp = AdminWarp(name=name, coords=f"{x} {y} {z}",world=world)
        db.session.add(new_warp)
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/teleport_warp/<int:id>')
@login_required
def teleport_warp(id):
    warp = AdminWarp.query.get(id)
    if warp:
        clean_coords = warp.coords.replace(' ', ',')
        cmd = f"sudo {current_user.username} mvtp {current_user.username} e:{warp.world}:{clean_coords}"
        send_rcon(cmd)
        add_log("WARP_TP", f"TP vers warp {warp.name}")
    return redirect(url_for('dashboard'))

@app.route('/update_staff_rank', methods=['POST'])
@login_required
def update_staff_rank():
    target_id = request.form.get('user_id')
    new_rank = request.form.get('rank')
    target_user = User.query.get(target_id)
    if not target_user:
        return {"status": "error", "msg": "Utilisateur introuvable."}, 404
    if target_user.id == current_user.id:
        return {"status": "error", "msg": "Tu ne peux pas modifier ton propre grade !"}, 403
    current_power = RANK_WEIGHTS.get(current_user.rank, 0)
    target_power = RANK_WEIGHTS.get(new_rank, 0)
    if target_power >= current_power and current_user.username != "Vanibels":
        return {"status": "error", "msg": f"Tu n'as pas la permission de nommer un {new_rank.upper()}."}, 403
    target_current_power = RANK_WEIGHTS.get(target_user.rank, 0)
    if target_current_power >= current_power and current_user.username != "Vanibels":
        return {"status": "error", "msg": "Tu ne peux pas modifier le grade d'un supérieur ou d'un égal."}, 403
    target_user.rank = new_rank
    db.session.commit()
    return {"status": "success"}

@app.route('/remove_staff/<int:uid>')
@login_required
def remove_staff(uid):
    user_to_del = User.query.get(uid)
    if not user_to_del: return redirect(url_for('dashboard'))
    
    my_power = RANK_WEIGHTS.get(current_user.rank, 0)
    target_power = RANK_WEIGHTS.get(user_to_del.rank, 0)

    if (my_power > target_power and my_power >= RANK_WEIGHTS.get('responsable', 90)) or current_user.username == "Vanibels":
        if user_to_del.username != "Vanibels":
            add_log("STAFF_DEL", f"A supprimé l'accès de {user_to_del.username}")
            db.session.delete(user_to_del)
            db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_warp/<int:id>')
@login_required
def delete_warp(id):
    warp = AdminWarp.query.get(id)
    if warp:
        db.session.delete(warp)
        db.session.commit()
    return redirect(url_for('dashboard'))
@app.route('/get_logs')
@login_required
def get_logs():
    if current_user.rank not in ['vanibels', 'gerant', 'administrateur', 'responsable']:
        return jsonify([])
    
    logs = Log.query.order_by(Log.timestamp.desc()).limit(100).all()
    return jsonify([{
        "time": l.timestamp.strftime("%d/%m %H:%M"),
        "user": l.staff_name,
        "type": l.action_type,
        "info": l.details 
    } for l in logs])

if __name__ == '__main__':
    app.run(debug=True)