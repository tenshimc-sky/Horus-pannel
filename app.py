from flask import abort, Flask, render_template, request, redirect, jsonify, url_for, flash, session, send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from mcstatus import JavaServer
from datetime import datetime
from mcrcon import MCRcon
import os

import config

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL missing")

if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

RCON_DATA = config.RCON_DATA
RANK_WEIGHTS = config.RANK_WEIGHTS

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    staff_name = db.Column(db.String(50))
    action_type = db.Column(db.String(20)) 
    details = db.Column(db.String(250))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    rank = db.Column(db.String(50), default='default')
    is_approved = db.Column(db.Boolean, default=True)

class AdminWarp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    coords = db.Column(db.String(100))
    world = db.Column(db.String(50), default='admin')

def add_log(action, details):
    name = current_user.username if current_user.is_authenticated else "Système"
    new_log = Log(staff_name=name, action_type=action, details=details)
    db.session.add(new_log)
    db.session.commit()

def send_rcon(cmd):
    try:
        port_rcon = int(RCON_DATA['port'])
        with MCRcon(RCON_DATA['host'], RCON_DATA['pass'], port=port_rcon, timeout=5) as mcr:
            return mcr.command(cmd)
    except Exception as e:
        print(f"DEBUG RCON ERROR: {e}") 
        return "§cErreur: Serveur Inaccessible"

def setup_initial_admin():
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(username=config.PANEL_ADMIN['pseudo']).first()
        
        if not admin:
            print("(!) Création du compte Administrateur...")
            hashed_pw = generate_password_hash(config.PANEL_ADMIN['password'])
            
            new_admin = User(
                username=config.PANEL_ADMIN['pseudo'],
                password=hashed_pw,
                rank="gerant",
                is_approved=True
            )
            db.session.add(new_admin)
            db.session.commit()
            print(f"(v) Compte {config.PANEL_ADMIN['pseudo']} prêt.")

setup_initial_admin()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.before_request
def security_check():
    if current_user.is_authenticated:
        current_ip = request.remote_addr
        if 'user_ip' not in session:
            session['user_ip'] = current_ip
            session['last_ip'] = current_ip
        if session.get('user_ip') != current_ip:
            logout_user()
            session.clear()
            flash("Sécurité : Votre IP a changé. Reconnexion requise.")
            return redirect(url_for('login'))
        
@app.route('/')
@login_required
def dashboard():
    try:
        server = JavaServer.lookup("beta.tenshimc.fr", timeout=2)
        status = server.status()
        server_info = {
            "online": True, 
            "players_online": status.players.online, 
            "players_max": status.players.max, 
            "version": status.version.name
        }
        players = [p.name for p in status.players.sample] if status.players.sample else []
    except Exception as e:
        print(f"Erreur Statut Serveur: {e}")
        server_info = {"online": False, "players_online": 0, "players_max": -1, "version": "N/A"}
        players = []

    warps = AdminWarp.query.all()
    staff_list = User.query.filter(User.username != "Vanibels", User.is_approved == True).all()
    pending_list = User.query.filter_by(is_approved=False).all()
    
    return render_template('dashboard.html', 
                           server=server_info, 
                           staff_members=staff_list, 
                           pending=pending_list, 
                           ranks=list(RANK_WEIGHTS.keys()), 
                           warps=warps)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            if user.is_approved:
                login_user(user)
                add_log("AUTH", "Connexion réussie")
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
            hashed_pw = generate_password_hash(password)
            new_user = User(
                username=username, 
                password=hashed_pw,
                is_approved=False
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
    msg = request.form.get('message', '').strip()
    is_button = request.form.get('is_button') == 'true'
    if not msg: 
        return jsonify({"status": "empty"})
    user_rank = current_user.rank.lower()
    if user_rank in ["s-modo", "developpeur"] and not is_button:
        return jsonify({"user": "SYSTÈME", "msg": msg, "res": "❌ Erreur: Commandes manuelles interdites pour ton rang."})
    forbidden_cmds = ["/stop", "/op", "/deop", "*/stop", "*/op", "*/deop", "/lp", "/luckperms", "*/lp", "*/luckperms"]
    if user_rank == "responsable":
        for forbidden in forbidden_cmds:
            if msg.lower().startswith(forbidden):
                return jsonify({"user": "SYSTÈME", "msg": msg, "res": "❌ Erreur: Commande interdite pour les Responsables."})
    allowed_ranks = ["s-modo", "developpeur", "responsable", "vanibels", "gerant", "administrateur"]
    if user_rank not in allowed_ranks:
        return jsonify({"user": "SYSTÈME", "msg": msg, "res": "❌ Erreur: Commande interdite pour ton rang."})

    try:
        if msg.startswith('*/'):
            command = msg[2:]
            res = send_rcon(command)
            add_log("CONSOLE", f"ROOT: {command}")
            return jsonify({"type": "cmd", "user": "CONSOLE", "msg": command, "res": res})
        elif msg.startswith('/'):
            command_raw = msg[1:]
            sudo_command = f"sudo {current_user.username} {command_raw}"
            res = send_rcon(sudo_command)
            add_log("CONSOLE", f"SUDO: {msg}")
            return jsonify({"type": "sudo", "user": current_user.username, "msg": msg, "res": res})
        else:
            display_rank = "gérant" if user_rank == "vanibels" else current_user.rank
            command = f'say §b[{display_rank.upper()}] §f{current_user.username}§7: {msg}'
            send_rcon(command)
            add_log("CONSOLE", f"CHAT: {msg}")
            return jsonify({"type": "say", "user": current_user.username, "msg": msg})
    except Exception as e:
        return jsonify({"user": "SYSTÈME", "res": f"❌ Erreur RCON: {str(e)}"})

@app.route('/rank_action', methods=['POST'])
@login_required
def rank_action():
    target = request.form.get('target')
    new_rank = request.form.get('rank')
    my_weight = RANK_WEIGHTS.get(current_user.rank, 0)
    target_weight = RANK_WEIGHTS.get(new_rank, 0)
    if my_weight <= target_weight and current_user.username != "Vanibels":
        return jsonify({"response": "§cTu ne peux pas rank au dessus de toi ou égal."})
    if new_rank in ['gerant', 'administrateur'] and current_user.username != "Vanibels":
        return jsonify({"response": "§cAction réservée au Fondateur."})
    res = send_rcon(f"lp user {target} parent set {new_rank}")
    add_log("RANK", f"A mis {target} au grade {new_rank}")
    return jsonify({"response": res})

@app.route('/logout')
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('login'))

@app.route('/approve/<int:uid>')
@login_required
def approve(uid):
    if current_user.rank.lower() in ['vanibels', 'gerant', 'administrateur', 'responsable']:
        u = db.session.get(User, uid)
        if u:
            u.is_approved = True
            db.session.commit()
            add_log("APPROVE", f"A approuvé le compte de {u.username}")
    return redirect(url_for('dashboard'))

@app.route('/logs_view')
@login_required
def logs_view():
    all_logs = Log.query.order_by(Log.id.desc()).limit(50).all()
    return render_template('logs_view.html', logs=all_logs)

@app.route('/delete_user/<int:uid>')
@login_required
def delete_user(uid):
    if current_user.rank.lower() in ['vanibels', 'gerant', 'administrateur', 'responsable']:
        u = db.session.get(User, uid)
        if u and u.username.lower() != "vanibels":
            username_deleted = u.username
            db.session.delete(u)
            db.session.commit()
            add_log("USER_DEL", f"A supprimé le compte de {username_deleted}")
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
        clean_coords = f"{x.strip()} {y.strip()} {z.strip()}"
        new_warp = AdminWarp(name=name, coords=clean_coords, world=world)
        db.session.add(new_warp)
        db.session.commit()
        add_log("WARP_ADD", f"A créé le warp {name}")
    return redirect(url_for('dashboard'))

@app.route('/teleport_warp/<int:id>')
@login_required
def teleport_warp(id):
    warp = db.session.get(AdminWarp, id)
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
    target_user = db.session.get(User, target_id)
    if not target_user:
        return jsonify({"status": "error", "msg": "Utilisateur introuvable."}), 404
    if target_user.id == current_user.id:
        return jsonify({"status": "error", "msg": "Tu ne peux pas modifier ton propre grade !"}), 403
    current_power = RANK_WEIGHTS.get(current_user.rank, 0)
    target_power = RANK_WEIGHTS.get(new_rank, 0)
    target_current_power = RANK_WEIGHTS.get(target_user.rank, 0)
    if current_user.username.lower() != "vanibels":
        if target_power >= current_power:
            return jsonify({"status": "error", "msg": f"Tu n'as pas la permission de nommer un {new_rank.upper()}."}), 403
        if target_current_power >= current_power:
            return jsonify({"status": "error", "msg": "Tu ne peux pas modifier le grade d'un supérieur ou d'un égal."}), 403
    old_rank = target_user.rank
    target_user.rank = new_rank
    db.session.commit()
    add_log("STAFF_RANK", f"A changé le rang de {target_user.username} ({old_rank} -> {new_rank})")
    return jsonify({"status": "success"})

@app.route('/remove_staff/<int:uid>')
@login_required
def remove_staff(uid):
    user_to_del = db.session.get(User, uid)
    if not user_to_del: 
        return redirect(url_for('dashboard'))
    my_power = RANK_WEIGHTS.get(current_user.rank, 0)
    target_power = RANK_WEIGHTS.get(user_to_del.rank, 0)
    is_admin = current_user.username == "Vanibels" or current_user.rank.lower() == "gerant"
    can_delete = (my_power > target_power and my_power >= 90) or is_admin
    if can_delete:
        if user_to_del.username != config.PANEL_ADMIN['pseudo']:
            add_log("STAFF_DEL", f"A supprimé l'accès de {user_to_del.username}")
            db.session.delete(user_to_del)
            db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/delete_warp/<int:id>')
@login_required
def delete_warp(id):
    warp = db.session.get(AdminWarp, id)
    if warp:
        db.session.delete(warp)
        db.session.commit()
        add_log("WARP_DEL", f"A supprimé le warp {warp.name}")
    return redirect(url_for('dashboard'))

@app.route('/get_logs')
@login_required
def get_logs():
    allowed = ['vanibels', 'gerant', 'administrateur', 'responsable']
    if current_user.rank.lower() not in allowed:
        return jsonify([])
        
    logs = Log.query.order_by(Log.timestamp.desc()).limit(100).all()
    return jsonify([{
        "time": l.timestamp.strftime("%d/%m %H:%M"),
        "user": l.staff_name,
        "type": l.action_type,
        "info": l.details 
    } for l in logs])

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        new_username = request.form.get('username')
        new_password = request.form.get('password')
        if new_username and new_username != current_user.username:
            exists = User.query.filter_by(username=new_username).first()
            if exists:
                flash("⚠️ Ce pseudo est déjà utilisé.")
                return redirect(url_for('profile'))
            current_user.username = new_username
        if new_password:
            current_user.password = generate_password_hash(new_password)
        db.session.commit()
        add_log("PROFILE", "A mis à jour ses identifiants")
        flash("✅ Profil mis à jour avec succès !")
        return redirect(url_for('profile'))
    return render_template('profile.html')

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html')

@app.route('/download_db')
@login_required
def download_db():
    return "Gone", 410

if __name__ == '__main__':
    app.config.update(
        TEMPLATES_AUTO_RELOAD=True,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SECRET_KEY=config.SECRET_KEY
    )
    setup_initial_admin()
    app.run(debug=False, host='0.0.0.0', port=5000)
