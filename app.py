# -*- coding: utf-8 -*-
"""
FundFlow Stable - Application web autonome
Fonctionne avec Python standard seulement: pas besoin de Flask, Django, SQLAlchemy ou pip.
Lancement: python app.py
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import socket
import sqlite3
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(APP_DIR))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / os.environ.get("DB_FILE", "fundflow_stable.db")
LOG_PATH = DATA_DIR / "fundflow_erreur.log"
APP_NAME = "FundFlow"
DEFAULT_LOGO = ""
SESSION_STORE: Dict[str, int] = {}
DEPARTMENTS = ["Achats", "Finance", "Logistique", "Ressources Humaines", "Operations", "Informatique", "Direction"]
JOB_TITLES = [
    "Déclarant",
    "Déclarant chargé des opérations",
    "Secrétaire",
    "Attaché aux finances",
    "Chef d’agence",
    "DRH",
    "Directeur Général",
    "Chauffeur",
    "Logisticien",
    "Comptable",
    "Caissier",
    "Responsable des opérations",
    "Superviseur",
    "Autre"
]
ROLES = {
    "agent": "Agent",
    "chauffeur": "Chauffeur",
    "department": "Chef / Evaluateur de département",
    "finance": "Finance",
    "logistique": "Logistique",
    "admin": "Administrateur",
}


MENU_ITEMS = {
    "home": ("⌂", "Accueil", "/"),
    "dashboard": ("▦", "Tableau de bord", "/dashboard"),
    "new_request": ("＋", "Nouvelle demande", "/requests/new"),
    "vehicle_reports": ("▤", "Rapports véhicules", "/vehicle/reports"),
    "vehicle_positions": ("⌖", "Positions véhicules", "/vehicle/positions"),
    "moods": ("◉", "Humeurs 24h", "/moods"),
    "appearance": ("◐", "Mon apparence", "/appearance"),
    "profile": ("●", "Profil", "/profile"),
    "users": ("♟", "Utilisateurs", "/users"),
    "settings": ("⚙", "Paramètres", "/settings"),
    "logout": ("↪", "Déconnexion", "/logout"),
}
DEFAULT_MENU_ORDER = [
    "home", "dashboard", "new_request", "vehicle_reports", "vehicle_positions",
    "moods", "appearance", "profile", "users", "settings", "logout"
]
PAGE_COLOR_FIELDS = {
    "home": "home_bg_color",
    "dashboard": "dashboard_bg_color",
    "requests": "requests_bg_color",
    "vehicles": "vehicles_bg_color",
    "moods": "moods_bg_color",
    "profile": "profile_bg_color",
    "admin": "admin_bg_color",
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_error(msg: str) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n[{now_str()}] {msg}\n")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def execute(sql: str, params: Tuple = ()) -> sqlite3.Cursor:
    conn = db()
    cur = conn.execute(sql, params)
    conn.commit()
    conn.close()
    return cur


def query_one(sql: str, params: Tuple = ()) -> Optional[sqlite3.Row]:
    conn = db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def query_all(sql: str, params: Tuple = ()) -> list[sqlite3.Row]:
    conn = db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _digest = stored.split("$", 1)
        return secrets.compare_digest(hash_password(password, salt), stored)
    except Exception:
        return False


def init_db() -> None:
    conn = db()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'agent',
            department TEXT NOT NULL DEFAULT 'Operations',
            job_title TEXT DEFAULT '',
            photo_data TEXT DEFAULT '',
            last_lat TEXT DEFAULT '',
            last_lon TEXT DEFAULT '',
            last_location_at TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            request_type TEXT NOT NULL,
            amount TEXT DEFAULT '',
            description TEXT NOT NULL,
            requester_id INTEGER NOT NULL,
            evaluator_department TEXT NOT NULL,
            status TEXT NOT NULL,
            department_decision TEXT DEFAULT '',
            department_comment TEXT DEFAULT '',
            finance_budget_status TEXT DEFAULT '',
            finance_comment TEXT DEFAULT '',
            admin_decision TEXT DEFAULT '',
            admin_comment TEXT DEFAULT '',
            archived INTEGER DEFAULT 0,
            closed_at TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(requester_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS vehicle_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chauffeur_id INTEGER NOT NULL,
            vehicle_plate TEXT NOT NULL,
            report_type TEXT NOT NULL,
            kilometrage TEXT DEFAULT '',
            fuel_level TEXT DEFAULT '',
            description TEXT NOT NULL,
            lat TEXT DEFAULT '',
            lon TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Envoyé à Logistique',
            logistic_comment TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(chauffeur_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS moods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS password_reset_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            email TEXT NOT NULL,
            message TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'En attente',
            created_at TEXT NOT NULL,
            processed_at TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );


        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER PRIMARY KEY,
            home_bg_color TEXT NOT NULL DEFAULT '#eef4ff',
            dashboard_bg_color TEXT NOT NULL DEFAULT '#f4f6fb',
            requests_bg_color TEXT NOT NULL DEFAULT '#f7f7fb',
            vehicles_bg_color TEXT NOT NULL DEFAULT '#f2f8f7',
            moods_bg_color TEXT NOT NULL DEFAULT '#fff8f0',
            profile_bg_color TEXT NOT NULL DEFAULT '#f6f3ff',
            admin_bg_color TEXT NOT NULL DEFAULT '#f4f6fb',
            personal_background TEXT DEFAULT '',
            background_opacity TEXT NOT NULL DEFAULT '0.16',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )

    # Migration douce pour les anciennes bases déjà créées.
    cols = [row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()]
    if "job_title" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN job_title TEXT DEFAULT ''")

    conn.commit()
    conn.close()

    default_settings = {
        "company_logo": DEFAULT_LOGO,
        "homepage_badge": "Gestion interne simple, rapide et traçable",
        "homepage_title": "Pilotez vos demandes et validations en toute confiance",
        "homepage_subtitle": "FundFlow centralise les demandes financières, matérielles et opérationnelles, de la soumission jusqu’à la clôture.",
        "homepage_message": "Une plateforme professionnelle pour les agents, départements, finances, logistique et direction.",
        "homepage_primary_cta": "Accéder à mon espace",
        "homepage_secondary_cta": "Créer un compte",
        "homepage_hero_image": "",
        "menu_order": ",".join(DEFAULT_MENU_ORDER),
        "sidebar_position": "left",
    }
    for key, value in default_settings.items():
        if not query_one("SELECT key FROM settings WHERE key=?", (key,)):
            execute("INSERT INTO settings(key, value) VALUES(?, ?)", (key, value))
    seed_users()


def seed_users() -> None:
    seed = [
        ("Administrateur", "admin@fundflow.local", "admin123", "admin", "Direction", "Directeur Général"),
        ("Agent Test", "agent@fundflow.local", "agent123", "agent", "Operations", "Déclarant"),
        ("Chauffeur Test", "chauffeur@fundflow.local", "chauffeur123", "chauffeur", "Logistique", "Chauffeur"),
        ("Chef Achats", "chef@fundflow.local", "chef123", "department", "Achats", "Chef d’agence"),
        ("Finance", "finance@fundflow.local", "finance123", "finance", "Finance", "Attaché aux finances"),
        ("Logistique", "logistique@fundflow.local", "logistique123", "logistique", "Logistique", "Logisticien"),
    ]
    for name, email, pwd, role, dep, job_title in seed:
        existing = query_one("SELECT id, job_title FROM users WHERE email=?", (email,))
        if not existing:
            execute(
                "INSERT INTO users(name,email,password_hash,role,department,job_title,created_at) VALUES(?,?,?,?,?,?,?)",
                (name, email, hash_password(pwd), role, dep, job_title, now_str()),
            )
        elif not existing["job_title"]:
            execute("UPDATE users SET job_title=? WHERE id=?", (job_title, existing["id"]))


def get_setting(key: str, default: str = "") -> str:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row and row["value"] is not None else default


def set_setting(key: str, value: str) -> None:
    execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))


def get_logo() -> str:
    return get_setting("company_logo", DEFAULT_LOGO)


def safe_color(value: str, fallback: str = "#f4f6fb") -> str:
    value = (value or "").strip()
    if len(value) == 7 and value.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in value[1:]):
        return value.lower()
    return fallback


def valid_image_data(value: str) -> str:
    value = (value or "").strip()
    return value if value.startswith("data:image/") else ""


def page_key_from_title(title: str) -> str:
    t = (title or "").lower()
    if "accueil" in t:
        return "home"
    if "tableau" in t:
        return "dashboard"
    if "demande" in t:
        return "requests"
    if "rapport" in t or "position" in t or "véhicule" in t:
        return "vehicles"
    if "humeur" in t:
        return "moods"
    if "profil" in t or "apparence" in t:
        return "profile"
    if "paramètre" in t or "utilisateur" in t or "autorisé" in t:
        return "admin"
    if "connexion" in t or "mot de passe" in t or "créer un compte" in t:
        return "login"
    return "dashboard"


def get_user_preferences(user_id: int) -> sqlite3.Row:
    row = query_one("SELECT * FROM user_preferences WHERE user_id=?", (user_id,))
    if not row:
        stamp = now_str()
        execute(
            """INSERT INTO user_preferences(
                user_id, home_bg_color, dashboard_bg_color, requests_bg_color,
                vehicles_bg_color, moods_bg_color, profile_bg_color, admin_bg_color,
                personal_background, background_opacity, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, "#eef4ff", "#f4f6fb", "#f7f7fb", "#f2f8f7", "#fff8f0", "#f6f3ff", "#f4f6fb", "", "0.16", stamp, stamp),
        )
        row = query_one("SELECT * FROM user_preferences WHERE user_id=?", (user_id,))
    return row


def page_background_for(user: Optional[sqlite3.Row], page_key: str) -> tuple[str, str, str]:
    if not user:
        return ("#eef4ff" if page_key in ("home", "login") else "#f4f6fb", "", "0.16")
    prefs = get_user_preferences(int(user["id"]))
    field = PAGE_COLOR_FIELDS.get(page_key, "dashboard_bg_color")
    color = safe_color(prefs[field], "#f4f6fb")
    image = valid_image_data(prefs["personal_background"])
    opacity = prefs["background_opacity"] if prefs["background_opacity"] in ("0.08", "0.12", "0.16", "0.22", "0.30", "0.40") else "0.16"
    return color, image, opacity


def get_menu_order() -> list[str]:
    raw = get_setting("menu_order", ",".join(DEFAULT_MENU_ORDER))
    requested = [item.strip() for item in raw.split(",") if item.strip() in MENU_ITEMS]
    ordered = []
    for item in requested + DEFAULT_MENU_ORDER:
        if item not in ordered:
            ordered.append(item)
    return ordered


def esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def status_badge(status: str) -> str:
    cls = "badge"
    s = status.lower()
    if "refus" in s or "rejet" in s:
        cls += " red"
    elif "clôt" in s or "libéré" in s or "archive" in s:
        cls += " green"
    elif "finance" in s:
        cls += " blue"
    elif "admin" in s:
        cls += " purple"
    return f'<span class="{cls}">{esc(status)}</span>'


def user_avatar(user: sqlite3.Row, size: int = 42) -> str:
    if user and user["photo_data"]:
        return f'<img class="avatar" style="width:{size}px;height:{size}px" src="{esc(user["photo_data"])}" alt="photo">'
    initials = "".join([p[:1].upper() for p in (user["name"] if user else "U").split()[:2]]) or "U"
    return f'<div class="avatar initials" style="width:{size}px;height:{size}px">{esc(initials)}</div>'


def build_sidebar(user: sqlite3.Row, logo_html: str) -> str:
    links = []
    for key in get_menu_order():
        if key in ("users", "settings") and user["role"] != "admin":
            continue
        if key == "vehicle_positions" and user["role"] not in ("chauffeur", "logistique", "admin"):
            continue
        icon, label, href = MENU_ITEMS[key]
        css = "nav-link logout-link" if key == "logout" else "nav-link"
        links.append(f'<a class="{css}" href="{href}"><span class="nav-icon">{icon}</span><span>{esc(label)}</span></a>')
    return f"""
    <aside class="sidebar">
        <div class="brand">{logo_html}<div><strong>{APP_NAME}</strong><small>Gestion des demandes</small></div></div>
        <nav class="nav-list">{''.join(links)}</nav>
    </aside>
    """
TRACKING_CODE = r"""
<!-- DÉBUT CODE DE SUIVI -->
<script defer src="https://analytique.gestionflux.fun/script.js" data-website-id="87dff970-c5dc-4495-8a21-00ff4926a9a7"></script>
<!-- FIN CODE DE SUIVI -->
"""
def layout(title: str, body: str, user: Optional[sqlite3.Row] = None, extra_head: str = "", page_key: str = "") -> str:
    page_key = page_key or page_key_from_title(title)
    logo = get_logo()
    logo_html = f'<img src="{esc(logo)}" class="login-logo" alt="Logo">' if logo else '<div class="brand-mark">F</div>'
    nav = build_sidebar(user, logo_html) if user else ""
    top = ""
    if user:
        top = f"""
        <header class="topbar">
            <div><span class="eyebrow">Espace de travail</span><h1>{esc(title)}</h1><p>{esc(ROLES.get(user['role'], user['role']))} — {esc(user['job_title'] or 'Fonction non définie')} — {esc(user['department'])}</p></div>
            <div class="userbox">{user_avatar(user)}<span><strong>{esc(user['name'])}</strong><small>{esc(user['email'])}</small></span></div>
        </header>
        """
    page_color, personal_image, opacity = page_background_for(user, page_key)
    bg_image_css = f'url("{esc(personal_image)}")' if personal_image else "none"
    sidebar_position = get_setting("sidebar_position", "left")
    body_classes = [f"page-{page_key}"]
    if user:
        body_classes.append("has-sidebar")
        if sidebar_position == "right":
            body_classes.append("sidebar-right")
    main_class = "content" if user else ("public-page" if page_key == "home" else "auth-page")
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0f766e">
<title>{esc(title)} — {APP_NAME}</title>
<style>{CSS}</style>
{extra_head}
{TRACKING_CODE}
<script defer src="https://analytique.gestionflux.fun/script.js" data-website-id="87dff970-c5dc-4495-8a21-00ff4926a9a7"></script>
</head>
<body class="{' '.join(body_classes)}" style="--page-bg:{page_color};--personal-bg-image:{bg_image_css};--personal-bg-opacity:{opacity}">
<div class="personal-bg-layer" aria-hidden="true"></div>
{nav}
<main class="{main_class}">
{top}
{body}
</main>
</body>
</html>"""


CSS = r"""
:root{--bg:#f4f6fb;--card:rgba(255,255,255,.94);--text:#0f172a;--muted:#64748b;--primary:#0f766e;--primary2:#115e59;--accent:#2563eb;--line:#e2e8f0;--green:#15803d;--red:#dc2626;--blue:#2563eb;--purple:#7c3aed;--orange:#ea580c;--sidebar:#0f172a;--radius:18px;--shadow:0 12px 32px rgba(15,23,42,.08)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;min-height:100vh;background:var(--page-bg,var(--bg));font-family:Inter,"Segoe UI",Roboto,Arial,sans-serif;color:var(--text);line-height:1.55;position:relative}.personal-bg-layer{position:fixed;inset:0;z-index:-2;background-image:var(--personal-bg-image,none);background-position:center;background-size:cover;background-repeat:no-repeat;opacity:var(--personal-bg-opacity,.16)}body:after{content:"";position:fixed;inset:0;z-index:-1;background:linear-gradient(135deg,rgba(255,255,255,.78),rgba(241,245,249,.62));pointer-events:none}a{color:var(--primary);text-decoration:none}h1,h2,h3{line-height:1.2}h2{margin-top:0}.eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;font-weight:800;color:var(--primary)}
.auth-page{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:28px}.auth-card{background:rgba(255,255,255,.96);border:1px solid rgba(226,232,240,.9);border-radius:24px;box-shadow:0 24px 70px rgba(15,23,42,.16);padding:30px;width:100%;max-width:480px;backdrop-filter:blur(12px)}.center{text-align:center}.brand-mark{width:56px;height:56px;border-radius:18px;background:linear-gradient(135deg,#0f766e,#2563eb);display:flex;align-items:center;justify-content:center;color:#fff;font-size:28px;font-weight:800;box-shadow:0 12px 28px rgba(15,118,110,.28)}.login-logo{max-width:100px;max-height:72px;object-fit:contain;border-radius:14px}.auth-card .brand-mark,.auth-card .login-logo{margin:0 auto 12px}.muted{color:var(--muted)}
.login-shell{width:min(1080px,100%);display:grid;grid-template-columns:1.05fr .95fr;border-radius:30px;overflow:hidden;box-shadow:0 30px 90px rgba(15,23,42,.18);border:1px solid rgba(255,255,255,.7);background:rgba(255,255,255,.86);backdrop-filter:blur(18px)}.login-showcase{padding:52px;background:linear-gradient(145deg,#0f172a,#0f766e);color:#fff;display:flex;flex-direction:column;justify-content:space-between;min-height:650px;position:relative;overflow:hidden}.login-showcase:after{content:"";position:absolute;width:360px;height:360px;border-radius:50%;right:-120px;top:-100px;background:rgba(255,255,255,.1)}.login-showcase h1{font-size:44px;margin:18px 0}.login-showcase p{color:#dbeafe;font-size:18px}.showcase-points{display:grid;gap:13px}.showcase-point{display:flex;gap:12px;align-items:center;padding:12px 14px;border:1px solid rgba(255,255,255,.14);border-radius:14px;background:rgba(255,255,255,.07)}.showcase-point span{width:30px;height:30px;border-radius:10px;background:rgba(255,255,255,.15);display:grid;place-items:center}.login-panel{padding:46px;background:rgba(255,255,255,.96);display:flex;align-items:center}.login-panel-inner{width:100%;max-width:430px;margin:auto}.login-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:center;margin-top:18px}.theme-toggle{position:fixed;right:22px;bottom:22px;z-index:30;width:48px;height:48px;border-radius:50%;padding:0;font-size:20px;box-shadow:var(--shadow)}.login-customizer{position:fixed;right:22px;bottom:82px;z-index:29;width:min(340px,calc(100vw - 44px));background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 22px 60px rgba(15,23,42,.2);display:none}.login-customizer.open{display:block}.login-customizer h3{margin:0 0 10px}.mini-preview{width:100%;height:95px;border-radius:14px;object-fit:cover;border:1px solid var(--line);background:#f8fafc}
.sidebar{position:fixed;left:0;top:0;bottom:0;width:280px;background:linear-gradient(180deg,var(--sidebar),#162033);color:#fff;padding:20px 16px;overflow:auto;z-index:20;box-shadow:8px 0 28px rgba(15,23,42,.12)}.sidebar-right .sidebar{left:auto;right:0;box-shadow:-8px 0 28px rgba(15,23,42,.12)}.brand{display:flex;gap:12px;align-items:center;margin:0 4px 24px;padding-bottom:18px;border-bottom:1px solid rgba(255,255,255,.1)}.brand .brand-mark{width:44px;height:44px;font-size:22px;box-shadow:none}.brand small{display:block;color:#94a3b8}.nav-list{display:flex;flex-direction:column;gap:5px}.nav-link{display:flex!important;align-items:center;gap:12px;color:#dbe4f0!important;padding:12px 13px;border-radius:13px;transition:.18s ease}.nav-link:hover{background:rgba(255,255,255,.1);color:#fff!important;transform:translateX(2px)}.nav-icon{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;background:rgba(255,255,255,.09);font-weight:900}.logout-link{margin-top:14px;border-top:1px solid rgba(255,255,255,.1);padding-top:16px}.content{margin-left:280px;padding:28px;min-height:100vh}.sidebar-right .content{margin-left:0;margin-right:280px}.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;gap:16px;padding:4px 2px}.topbar h1{margin:3px 0 5px;font-size:30px}.topbar p{margin:0;color:var(--muted)}.userbox{display:flex;align-items:center;gap:11px;background:rgba(255,255,255,.9);border:1px solid var(--line);border-radius:999px;padding:8px 14px;box-shadow:0 8px 22px rgba(15,23,42,.06)}.userbox span{display:flex;flex-direction:column}.userbox small{color:var(--muted)}.avatar{border-radius:50%;object-fit:cover;border:2px solid #fff;box-shadow:0 0 0 1px var(--line)}.initials{display:inline-flex;align-items:center;justify-content:center;background:#dbeafe;color:#1e40af;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:18px}.card{background:var(--card);border:1px solid rgba(226,232,240,.9);border-radius:var(--radius);padding:20px;box-shadow:var(--shadow);backdrop-filter:blur(10px)}.card:hover{box-shadow:0 16px 38px rgba(15,23,42,.10)}.span-3{grid-column:span 3}.span-4{grid-column:span 4}.span-5{grid-column:span 5}.span-6{grid-column:span 6}.span-7{grid-column:span 7}.span-8{grid-column:span 8}.span-12{grid-column:span 12}.metric{font-size:34px;font-weight:850;margin:8px 0}.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.space{display:flex;justify-content:space-between;gap:12px;align-items:center}.btn,button{border:0;background:var(--primary);color:#fff;padding:11px 16px;border-radius:12px;font-weight:750;cursor:pointer;display:inline-block;transition:.18s ease}.btn:hover,button:hover{background:var(--primary2);transform:translateY(-1px)}.btn.secondary{background:#eef2ff;color:#243b6b}.btn.danger{background:var(--red)}.btn.green{background:var(--green)}.btn.orange{background:var(--orange)}input,select,textarea{width:100%;padding:12px 13px;border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.95);font:inherit;color:var(--text);outline:none}input:focus,select:focus,textarea:focus{border-color:var(--primary);box-shadow:0 0 0 3px rgba(15,118,110,.12)}input[type=color]{height:48px;padding:5px}label{font-weight:750;margin:12px 0 6px;display:block}textarea{min-height:120px;resize:vertical}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;border-bottom:1px solid var(--line);padding:12px;vertical-align:top}.table th{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}.badge{display:inline-block;background:#f3f4f6;color:#374151;padding:5px 9px;border-radius:999px;font-size:12px;font-weight:800}.badge.green{background:#dcfce7;color:#166534}.badge.red{background:#fee2e2;color:#991b1b}.badge.blue{background:#dbeafe;color:#1e40af}.badge.purple{background:#ede9fe;color:#5b21b6}.notice{background:#eff6ff;border-left:4px solid var(--primary);padding:13px 15px;border-radius:12px;margin-bottom:16px}.error{background:#fef2f2;border-left:4px solid var(--red);padding:12px 14px;border-radius:12px;margin-bottom:14px}.success{background:#ecfdf5;border-left:4px solid var(--green);padding:12px 14px;border-radius:12px;margin-bottom:14px}.timeline{border-left:3px solid var(--line);padding-left:16px}.timeline div{margin:0 0 14px;position:relative}.timeline div:before{content:"";position:absolute;left:-24px;top:4px;width:13px;height:13px;background:var(--primary);border-radius:50%;border:3px solid #fff}.mood{display:flex;gap:12px;border-bottom:1px solid var(--line);padding:12px 0}.maplink{font-weight:700}
.public-page{min-height:100vh}.public-nav{height:82px;display:flex;align-items:center;justify-content:space-between;padding:0 max(24px,calc((100vw - 1180px)/2));background:rgba(255,255,255,.82);backdrop-filter:blur(14px);border-bottom:1px solid rgba(226,232,240,.8);position:sticky;top:0;z-index:25}.public-brand{display:flex;align-items:center;gap:12px;color:var(--text)}.public-brand .brand-mark{width:44px;height:44px;font-size:22px}.public-actions{display:flex;gap:10px}.hero{min-height:610px;display:grid;grid-template-columns:1.1fr .9fr;align-items:center;gap:44px;padding:74px max(24px,calc((100vw - 1180px)/2));background:linear-gradient(120deg,rgba(255,255,255,.92),rgba(226,232,240,.72));position:relative;overflow:hidden}.hero-copy{position:relative;z-index:2}.hero-badge{display:inline-flex;padding:8px 12px;border-radius:999px;background:#ccfbf1;color:#115e59;font-weight:800;font-size:13px}.hero h1{font-size:clamp(42px,5vw,70px);margin:18px 0;max-width:820px}.hero p{font-size:20px;color:#475569;max-width:720px}.hero-actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}.hero-visual{min-height:430px;border-radius:30px;background:linear-gradient(145deg,#0f172a,#0f766e);box-shadow:0 30px 80px rgba(15,23,42,.22);position:relative;overflow:hidden;background-size:cover;background-position:center}.hero-visual:after{content:"";position:absolute;inset:0;background:linear-gradient(145deg,rgba(15,23,42,.45),rgba(15,118,110,.28))}.hero-dashboard{position:absolute;z-index:2;inset:46px 32px 32px;background:rgba(255,255,255,.94);border-radius:22px;padding:20px;display:grid;grid-template-columns:repeat(2,1fr);gap:14px;transform:rotate(-2deg)}.hero-mini{background:#f8fafc;border:1px solid #e2e8f0;border-radius:16px;padding:16px}.hero-mini.wide{grid-column:span 2}.feature-section{padding:76px max(24px,calc((100vw - 1180px)/2));background:#fff}.section-head{text-align:center;max-width:760px;margin:0 auto 34px}.section-head h2{font-size:38px;margin:8px 0}.feature-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}.feature-card{padding:26px;border:1px solid var(--line);border-radius:20px;background:#fff;box-shadow:0 12px 30px rgba(15,23,42,.06)}.feature-icon{width:48px;height:48px;border-radius:15px;background:#ccfbf1;color:#115e59;display:grid;place-items:center;font-size:22px;font-weight:900}.workflow{padding:70px max(24px,calc((100vw - 1180px)/2));background:#f8fafc}.workflow-row{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}.workflow-step{background:#fff;border-radius:18px;border:1px solid var(--line);padding:22px}.workflow-step strong{display:block;font-size:28px;color:var(--primary);margin-bottom:6px}.site-footer{padding:28px max(24px,calc((100vw - 1180px)/2));background:#0f172a;color:#cbd5e1;display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap}
.appearance-preview{min-height:240px;border-radius:20px;background-color:var(--preview-color,#f4f6fb);background-image:var(--preview-image,none);background-size:cover;background-position:center;border:1px solid var(--line);display:grid;place-items:center;overflow:hidden}.appearance-preview span{background:rgba(255,255,255,.88);padding:14px 18px;border-radius:14px;font-weight:800}.color-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.sortable-list{list-style:none;padding:0;margin:10px 0;display:grid;gap:8px}.sortable-item{display:flex;align-items:center;gap:10px;padding:12px;border:1px solid var(--line);border-radius:12px;background:#fff;cursor:grab}.sortable-item.dragging{opacity:.45}.sort-actions{margin-left:auto;display:flex;gap:6px}.sort-actions button{padding:6px 9px;border-radius:8px}
@media(max-width:1000px){.login-shell{grid-template-columns:1fr;max-width:600px}.login-showcase{min-height:auto;padding:36px}.login-showcase h1{font-size:34px}.hero{grid-template-columns:1fr}.hero-visual{min-height:370px}.feature-grid,.workflow-row{grid-template-columns:repeat(2,1fr)}}
@media(max-width:900px){.sidebar,.sidebar-right .sidebar{position:static;width:auto}.content,.sidebar-right .content{margin-left:0;margin-right:0}.grid{grid-template-columns:1fr}.span-3,.span-4,.span-5,.span-6,.span-7,.span-8,.span-12{grid-column:span 1}.topbar{display:block}.userbox{margin-top:14px;width:max-content}.table{font-size:14px;display:block;overflow:auto}.table th:nth-child(4),.table td:nth-child(4){display:none}.public-nav{padding:0 18px}.public-actions .secondary{display:none}}
@media(max-width:650px){.auth-page{padding:14px}.login-panel{padding:28px 20px}.login-showcase{display:none}.feature-grid,.workflow-row,.color-grid{grid-template-columns:1fr}.hero{padding:52px 20px}.hero h1{font-size:40px}.hero-visual{min-height:330px}.hero-dashboard{inset:28px 18px 22px}.public-nav{height:70px}.public-brand strong{font-size:15px}.site-footer{display:block}}
"""


class FundFlowHandler(BaseHTTPRequestHandler):
    server_version = "FundFlowStable/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Console simple; les erreurs importantes sont écrites dans fundflow_erreur.log
        sys.stdout.write("[%s] %s\n" % (now_str(), fmt % args))

    def do_GET(self) -> None:
        try:
            self.route("GET")
        except Exception:
            self.handle_exception()

    def do_POST(self) -> None:
        try:
            self.route("POST")
        except Exception:
            self.handle_exception()

    def parse_body(self) -> Dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        data = urllib.parse.parse_qs(raw, keep_blank_values=True)
        return {k: v[-1] if v else "" for k, v in data.items()}

    def current_user(self) -> Optional[sqlite3.Row]:
        c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        sid = c.get("sid")
        if not sid:
            return None
        uid = SESSION_STORE.get(sid.value)
        if not uid:
            return None
        return query_one("SELECT * FROM users WHERE id=?", (uid,))

    def require_user(self) -> Optional[sqlite3.Row]:
        user = self.current_user()
        if not user:
            self.redirect("/login")
            return None
        return user

    def send_html(self, html_text: str, status: int = 200, headers: Optional[Dict[str, str]] = None) -> None:
        payload = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def handle_exception(self) -> None:
        tb = traceback.format_exc()
        log_error(tb)
        self.send_html(layout("Erreur", f"""
        <div class="auth-card">
            <h2>Erreur dans l’application</h2>
            <p>Un détail a été enregistré dans <strong>fundflow_erreur.log</strong>.</p>
            <pre style="white-space:pre-wrap;background:#111;color:#fff;padding:12px;border-radius:12px;max-height:360px;overflow:auto">{esc(tb)}</pre>
            <a class="btn" href="/dashboard">Retour</a>
        </div>
        """), 500)

    def route(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/health":
            self.send_json({"ok": True, "time": now_str()})
        elif path in ("/", "/home"):
            self.homepage()
        elif path == "/login":
            self.login(method)
        elif path == "/register":
            self.register(method)
        elif path == "/forgot-password":
            self.forgot_password(method)
        elif path == "/logout":
            self.logout()
        elif path == "/dashboard":
            self.dashboard()
        elif path == "/requests/new":
            self.new_request(method)
        elif path.startswith("/requests/"):
            parts = path.split("/")
            if len(parts) >= 3 and parts[2].isdigit():
                if len(parts) == 4 and parts[3] == "decision":
                    self.request_decision(int(parts[2]), method)
                else:
                    self.request_detail(int(parts[2]))
            else:
                self.not_found()
        elif path == "/vehicle/reports":
            self.vehicle_reports()
        elif path == "/vehicle/reports/new":
            self.vehicle_report_new(method)
        elif path.startswith("/vehicle/reports/"):
            parts = path.split("/")
            if len(parts) >= 4 and parts[3].isdigit():
                if len(parts) == 5 and parts[4] == "decision":
                    self.vehicle_report_decision(int(parts[3]), method)
                else:
                    self.vehicle_report_detail(int(parts[3]))
            else:
                self.not_found()
        elif path == "/vehicle/positions":
            self.vehicle_positions()
        elif path == "/api/chauffeur/location":
            self.update_location(method)
        elif path == "/moods":
            self.moods(method)
        elif path == "/appearance":
            self.appearance(method)
        elif path == "/profile":
            self.profile(method)
        elif path == "/settings":
            self.settings(method)
        elif path == "/users":
            self.users(method)
        else:
            self.not_found()

    def not_found(self) -> None:
        self.send_html(layout("Page introuvable", '<div class="card"><h2>Page introuvable</h2><a class="btn" href="/dashboard">Retour</a></div>', self.current_user()), 404)

    def homepage(self) -> None:
        user = self.current_user()
        logo = get_logo()
        logo_html = f'<img src="{esc(logo)}" class="login-logo" alt="Logo">' if logo else '<div class="brand-mark">F</div>'
        badge = get_setting("homepage_badge", "Gestion interne simple, rapide et traçable")
        title = get_setting("homepage_title", "Pilotez vos demandes et validations en toute confiance")
        subtitle = get_setting("homepage_subtitle", "FundFlow centralise les demandes financières, matérielles et opérationnelles, de la soumission jusqu’à la clôture.")
        message = get_setting("homepage_message", "Une plateforme professionnelle pour les agents, départements, finances, logistique et direction.")
        primary_label = get_setting("homepage_primary_cta", "Accéder à mon espace")
        secondary_label = get_setting("homepage_secondary_cta", "Créer un compte")
        hero_image = valid_image_data(get_setting("homepage_hero_image", ""))
        hero_style = f' style="background-image:url(\'{esc(hero_image)}\')"' if hero_image else ""
        primary_href = "/dashboard" if user else "/login"
        secondary_href = "/appearance" if user else "/register"
        secondary_text = "Personnaliser mon espace" if user else secondary_label
        public_actions = (
            '<a class="btn secondary" href="/dashboard">Tableau de bord</a><a class="btn" href="/logout">Déconnexion</a>'
            if user else
            '<a class="btn secondary" href="/login">Connexion</a><a class="btn" href="/register">Créer un compte</a>'
        )
        body = f"""
        <header class="public-nav">
            <a class="public-brand" href="/">{logo_html}<span><strong>{APP_NAME}</strong><br><small class="muted">Gestion des demandes</small></span></a>
            <div class="public-actions">{public_actions}</div>
        </header>
        <section class="hero">
            <div class="hero-copy">
                <span class="hero-badge">{esc(badge)}</span>
                <h1>{esc(title)}</h1>
                <p>{esc(subtitle)}</p>
                <p class="muted">{esc(message)}</p>
                <div class="hero-actions">
                    <a class="btn" href="{primary_href}">{esc(primary_label if not user else 'Ouvrir le tableau de bord')}</a>
                    <a class="btn secondary" href="{secondary_href}">{esc(secondary_text)}</a>
                </div>
            </div>
            <div class="hero-visual"{hero_style}>
                <div class="hero-dashboard">
                    <div class="hero-mini"><span class="muted">Demandes</span><div class="metric">128</div><small>Traçabilité complète</small></div>
                    <div class="hero-mini"><span class="muted">Validations</span><div class="metric">94%</div><small>Circuit maîtrisé</small></div>
                    <div class="hero-mini wide"><strong>Agent → Département → Finance → Direction</strong><p class="muted">Chaque étape est visible et documentée.</p></div>
                    <div class="hero-mini wide"><span class="badge green">Sécurisé</span> <span class="badge blue">Collaboratif</span> <span class="badge purple">Professionnel</span></div>
                </div>
            </div>
        </section>
        <section class="feature-section">
            <div class="section-head"><span class="eyebrow">Une plateforme complète</span><h2>Tout ce qu’il faut pour mieux décider</h2><p class="muted">Centralisez les opérations internes et réduisez les échanges dispersés.</p></div>
            <div class="feature-grid">
                <article class="feature-card"><div class="feature-icon">✓</div><h3>Demandes structurées</h3><p class="muted">Les agents soumettent des demandes claires avec département évaluateur et justification.</p></article>
                <article class="feature-card"><div class="feature-icon">↗</div><h3>Validation hiérarchique</h3><p class="muted">Chaque service intervient au bon moment, avec commentaires et décisions traçables.</p></article>
                <article class="feature-card"><div class="feature-icon">⌖</div><h3>Logistique et véhicules</h3><p class="muted">Rapports chauffeurs, positions et suivi logistique sont regroupés dans le même espace.</p></article>
            </div>
        </section>
        <section class="workflow">
            <div class="section-head"><span class="eyebrow">Circuit de traitement</span><h2>Un processus simple en quatre étapes</h2></div>
            <div class="workflow-row">
                <div class="workflow-step"><strong>01</strong><h3>Soumission</h3><p class="muted">L’agent explique son besoin.</p></div>
                <div class="workflow-step"><strong>02</strong><h3>Évaluation</h3><p class="muted">Le département analyse la demande.</p></div>
                <div class="workflow-step"><strong>03</strong><h3>Budget</h3><p class="muted">Finance vérifie la disponibilité.</p></div>
                <div class="workflow-step"><strong>04</strong><h3>Décision</h3><p class="muted">La direction approuve et clôture.</p></div>
            </div>
        </section>
        <footer class="site-footer"><strong>{APP_NAME}</strong><span>Gestion professionnelle des demandes internes.</span></footer>
        """
        self.send_html(layout("Accueil", body, None, page_key="home"))

    def login(self, method: str) -> None:
        error = ""
        if method == "POST":
            data = self.parse_body()
            email = data.get("email", "").strip().lower()
            pwd = data.get("password", "")
            user = query_one("SELECT * FROM users WHERE lower(email)=?", (email,))
            if user and verify_password(pwd, user["password_hash"]):
                sid = secrets.token_urlsafe(32)
                SESSION_STORE[sid] = int(user["id"])
                self.send_response(303)
                self.send_header("Location", "/dashboard")
                self.send_header("Set-Cookie", f"sid={sid}; HttpOnly; Path=/; SameSite=Lax")
                self.end_headers()
                return
            error = "Email ou mot de passe incorrect."
        logo = get_logo()
        logo_html = f'<img src="{esc(logo)}" class="login-logo" alt="Logo">' if logo else '<div class="brand-mark">F</div>'
        body = f"""
        <div class="login-shell">
            <section class="login-showcase">
                <div>
                    <a href="/" style="color:white;display:flex;align-items:center;gap:12px">{logo_html}<strong>{APP_NAME}</strong></a>
                    <h1>Gérez chaque demande avec clarté.</h1>
                    <p>Une expérience professionnelle pour les agents, les évaluateurs, la finance, la logistique et la direction.</p>
                </div>
                <div class="showcase-points">
                    <div class="showcase-point"><span>1</span> Circuit de validation structuré</div>
                    <div class="showcase-point"><span>2</span> Suivi en temps réel des décisions</div>
                    <div class="showcase-point"><span>3</span> Apparence privée et personnalisable</div>
                </div>
            </section>
            <section class="login-panel">
                <div class="login-panel-inner">
                    <span class="eyebrow">Bienvenue</span>
                    <h2>Connexion à votre espace</h2>
                    <p class="muted">Utilisez vos identifiants professionnels.</p>
                    {f'<div class="error">{esc(error)}</div>' if error else ''}
                    <form method="post">
                        <label>Email</label><input name="email" type="email" required placeholder="nom@entreprise.com" autocomplete="username">
                        <label>Mot de passe</label><input name="password" type="password" required placeholder="Votre mot de passe" autocomplete="current-password">
                        <button style="width:100%;margin-top:16px">Se connecter</button>
                    </form>
                    <div class="login-actions">
                        <a class="btn secondary" href="/register">Créer un compte</a>
                        <a class="btn secondary" href="/forgot-password">Mot de passe oublié</a>
                        <a class="btn secondary" href="/">Accueil</a>
                    </div>
                </div>
            </section>
        </div>
        <button type="button" class="theme-toggle" id="theme_toggle" title="Personnaliser cette page">◐</button>
        <aside class="login-customizer" id="login_customizer">
            <h3>Mon fond de connexion</h3>
            <p class="muted">Ces réglages restent uniquement dans ce navigateur.</p>
            <label>Couleur de fond</label><input type="color" id="login_bg_color" value="#eef4ff">
            <label>Ma photo privée</label><input type="file" id="login_bg_file" accept="image/*">
            <img id="login_bg_preview" class="mini-preview" alt="Aperçu">
            <div class="row" style="margin-top:12px"><button type="button" id="clear_login_bg" class="danger">Supprimer la photo</button><button type="button" id="close_customizer" class="secondary">Fermer</button></div>
        </aside>
        """
        self.send_html(layout("Connexion", body, None, login_customizer_js(), page_key="login"))

    def forgot_password(self, method: str) -> None:
        error = ""
        ok = ""
        if method == "POST":
            data = self.parse_body()
            email = data.get("email", "").strip().lower()
            message = data.get("message", "").strip()
            if not email:
                error = "Entre ton adresse email."
            else:
                u = query_one("SELECT id, name FROM users WHERE lower(email)=?", (email,))
                if u:
                    execute(
                        "INSERT INTO password_reset_requests(user_id,email,message,status,created_at) VALUES(?,?,?,?,?)",
                        (u["id"], email, message, "En attente", now_str()),
                    )
                    ok = "Demande envoyée. L’administrateur pourra réinitialiser ton mot de passe dans Utilisateurs."
                else:
                    # Réponse volontairement neutre pour éviter d’exposer les emails enregistrés.
                    ok = "Si cet email existe dans FundFlow, l’administrateur verra la demande de réinitialisation."
        body = f"""
        <div class="auth-card">
            <h1>Mot de passe oublié</h1>
            <p class="muted">Entre ton email. L’administrateur pourra vérifier la demande et définir un nouveau mot de passe.</p>
            {f'<div class="error">{esc(error)}</div>' if error else ''}
            {f'<div class="success">{esc(ok)}</div>' if ok else ''}
            <form method="post">
                <label>Email du compte</label><input name="email" type="email" required placeholder="agent@entreprise.com">
                <label>Message facultatif</label><textarea name="message" placeholder="Ex: J’ai oublié mon code, merci de le réinitialiser."></textarea>
                <button style="width:100%;margin-top:16px">Envoyer la demande</button>
            </form>
            <p class="center"><a href="/login">Retour à la connexion</a></p>
        </div>
        """
        self.send_html(layout("Mot de passe oublié", body))

    def register(self, method: str) -> None:
        error = ""
        ok = ""
        if method == "POST":
            data = self.parse_body()
            name = data.get("name", "").strip()
            email = data.get("email", "").strip().lower()
            pwd = data.get("password", "")
            role = data.get("role", "agent")
            department = data.get("department", "Operations")
            job_title = data.get("job_title", "").strip()
            if not job_title:
                job_title = "Chauffeur" if role == "chauffeur" else "Déclarant"
            if role not in ("agent", "chauffeur"):
                role = "agent"
            if not name or not email or not pwd:
                error = "Tous les champs obligatoires doivent être remplis."
            elif query_one("SELECT id FROM users WHERE lower(email)=?", (email,)):
                error = "Cet email existe déjà."
            else:
                execute(
                    "INSERT INTO users(name,email,password_hash,role,department,job_title,created_at) VALUES(?,?,?,?,?,?,?)",
                    (name, email, hash_password(pwd), role, department, job_title, now_str()),
                )
                ok = "Compte créé. Tu peux te connecter maintenant."
        dep_opts = "".join(f'<option value="{esc(d)}">{esc(d)}</option>' for d in DEPARTMENTS)
        job_options = "".join(f'<option value="{esc(j)}"></option>' for j in JOB_TITLES)
        role_opts = '<option value="agent">Agent</option><option value="chauffeur">Chauffeur</option>'
        body = f"""
        <div class="auth-card">
            <h1>Créer un compte</h1>
            <p class="muted">Un agent ou un chauffeur peut créer son compte. Les comptes Finance, Logistique et Admin sont gérés par l’administrateur.</p>
            {f'<div class="error">{esc(error)}</div>' if error else ''}
            {f'<div class="success">{esc(ok)}</div>' if ok else ''}
            <form method="post">
                <label>Nom complet</label><input name="name" required>
                <label>Email</label><input name="email" type="email" required>
                <label>Mot de passe</label><input name="password" type="password" required>
                <label>Type de compte</label><select name="role">{role_opts}</select>
                <label>Fonction</label><input name="job_title" list="job_titles" placeholder="Ex: Déclarant, Secrétaire, Chauffeur, DRH..." required>
                <datalist id="job_titles">{job_options}</datalist>
                <label>Département / Service</label><select name="department">{dep_opts}</select>
                <button style="width:100%;margin-top:16px">Créer le compte</button>
            </form>
            <p class="center"><a href="/login">Retour à la connexion</a></p>
        </div>
        """
        self.send_html(layout("Créer un compte", body))

    def logout(self) -> None:
        c = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        sid = c.get("sid")
        if sid:
            SESSION_STORE.pop(sid.value, None)
        self.send_response(303)
        self.send_header("Location", "/login")
        self.send_header("Set-Cookie", "sid=; Max-Age=0; Path=/")
        self.end_headers()

    def dashboard(self) -> None:
        user = self.require_user()
        if not user:
            return
        all_req_count = query_one("SELECT COUNT(*) c FROM requests")["c"]
        pending_dept = query_one("SELECT COUNT(*) c FROM requests WHERE status='En attente évaluation département'")["c"]
        pending_fin = query_one("SELECT COUNT(*) c FROM requests WHERE status='En attente avis Finance'")["c"]
        pending_admin = query_one("SELECT COUNT(*) c FROM requests WHERE status='En attente feu vert Admin'")["c"]
        vehicle_count = query_one("SELECT COUNT(*) c FROM vehicle_reports")["c"]
        role_note = self.role_note(user)
        reqs = self.visible_requests(user)
        reports = self.visible_vehicle_reports(user)
        rows = "".join(self.request_row(r) for r in reqs[:8]) or '<tr><td colspan="5" class="muted">Aucune demande visible.</td></tr>'
        report_rows = "".join(self.report_row(r) for r in reports[:8]) or '<tr><td colspan="5" class="muted">Aucun rapport véhicule visible.</td></tr>'
        body = f"""
        <div class="notice">{role_note}</div>
        <div class="grid">
            <div class="card span-3"><div class="muted">Toutes demandes</div><div class="metric">{all_req_count}</div></div>
            <div class="card span-3"><div class="muted">Département</div><div class="metric">{pending_dept}</div></div>
            <div class="card span-3"><div class="muted">Finance</div><div class="metric">{pending_fin}</div></div>
            <div class="card span-3"><div class="muted">Admin</div><div class="metric">{pending_admin}</div></div>
            <div class="card span-8">
                <div class="space"><h2>Demandes</h2><a class="btn" href="/requests/new">Créer une demande</a></div>
                <table class="table"><tr><th>N°</th><th>Titre</th><th>Agent</th><th>Étape</th><th>Action</th></tr>{rows}</table>
            </div>
            <div class="card span-4">
                <h2>Humeurs 24h</h2>
                {self.mood_list(limit=4)}
                <a class="btn secondary" href="/moods">Voir / publier</a>
            </div>
            <div class="card span-12">
                <div class="space"><h2>Rapports véhicules</h2><a class="btn" href="/vehicle/reports/new">Nouveau rapport</a></div>
                <p class="muted">Total rapports : {vehicle_count}</p>
                <table class="table"><tr><th>N°</th><th>Chauffeur</th><th>Véhicule</th><th>Statut</th><th>Action</th></tr>{report_rows}</table>
            </div>
        </div>
        """
        self.send_html(layout("Tableau de bord", body, user))

    def role_note(self, user: sqlite3.Row) -> str:
        if user["role"] == "agent":
            return "Circuit : Agent → Département évaluateur choisi → Finance → Administrateur → Libération/Clôture."
        if user["role"] == "department":
            return f"Tu évalues les demandes envoyées au département {user['department']}, puis tu transmets à Finance."
        if user["role"] == "finance":
            return "Finance donne l’avis budgétaire et renvoie l’information au département évaluateur et à l’administrateur."
        if user["role"] == "admin":
            return "L’administrateur donne le feu vert final, libère les fonds/matériels, archive et clôture la demande."
        if user["role"] == "chauffeur":
            return "Le chauffeur peut envoyer des rapports véhicule et partager sa position GPS/GPRS via le navigateur."
        if user["role"] == "logistique":
            return "La logistique reçoit les rapports véhicules et consulte les dernières positions GPS des chauffeurs."
        return "Bienvenue dans FundFlow."

    def visible_requests(self, user: sqlite3.Row) -> list[sqlite3.Row]:
        if user["role"] == "admin":
            return query_all("SELECT r.*, u.name requester_name FROM requests r JOIN users u ON u.id=r.requester_id ORDER BY r.id DESC")
        if user["role"] == "finance":
            return query_all("SELECT r.*, u.name requester_name FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.status IN ('En attente avis Finance','En attente feu vert Admin','Libérée et clôturée','Budget refusé') ORDER BY r.id DESC")
        if user["role"] == "department":
            return query_all("SELECT r.*, u.name requester_name FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.evaluator_department=? OR r.requester_id=? ORDER BY r.id DESC", (user["department"], user["id"]))
        return query_all("SELECT r.*, u.name requester_name FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.requester_id=? ORDER BY r.id DESC", (user["id"],))

    def request_row(self, r: sqlite3.Row) -> str:
        return f"<tr><td>#{r['id']}</td><td>{esc(r['title'])}<br><small>{esc(r['request_type'])} — {esc(r['evaluator_department'])}</small></td><td>{esc(r['requester_name'])}</td><td>{status_badge(r['status'])}</td><td><a class='btn secondary' href='/requests/{r['id']}'>Ouvrir</a></td></tr>"

    def new_request(self, method: str) -> None:
        user = self.require_user()
        if not user:
            return
        msg = ""
        if method == "POST":
            data = self.parse_body()
            title = data.get("title", "").strip()
            request_type = data.get("request_type", "Financier")
            amount = data.get("amount", "").strip()
            department = data.get("evaluator_department", "Achats")
            desc = data.get("description", "").strip()
            if title and desc:
                execute(
                    """INSERT INTO requests(title,request_type,amount,description,requester_id,evaluator_department,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (title, request_type, amount, desc, user["id"], department, "En attente évaluation département", now_str(), now_str()),
                )
                self.redirect("/dashboard")
                return
            msg = '<div class="error">Titre et description obligatoires.</div>'
        dep_opts = "".join(f'<option value="{esc(d)}">{esc(d)}</option>' for d in DEPARTMENTS if d != "Finance")
        body = f"""
        <div class="card">
            <h2>Créer une demande</h2>
            <p class="muted">L’agent choisit le département qui doit évaluer la demande avant l’étape Finance.</p>
            {msg}
            <form method="post">
                <label>Titre de la demande</label><input name="title" required>
                <label>Type</label><select name="request_type"><option>Financier</option><option>Matériel</option><option>Autre</option></select>
                <label>Montant estimatif, si financier</label><input name="amount" placeholder="Ex: 250 USD">
                <label>Département évaluateur</label><select name="evaluator_department">{dep_opts}</select>
                <label>Description / justification</label><textarea name="description" required></textarea>
                <button>Soumettre la demande</button>
            </form>
        </div>
        """
        self.send_html(layout("Nouvelle demande", body, user))

    def request_detail(self, rid: int) -> None:
        user = self.require_user()
        if not user:
            return
        r = query_one("SELECT r.*, u.name requester_name, u.email requester_email FROM requests r JOIN users u ON u.id=r.requester_id WHERE r.id=?", (rid,))
        if not r:
            self.not_found(); return
        actions = self.request_actions(user, r)
        timeline = f"""
        <div class="timeline">
            <div><strong>Création par l’agent</strong><br>{esc(r['created_at'])}<br>{esc(r['requester_name'])}</div>
            <div><strong>Département évaluateur</strong><br>{esc(r['evaluator_department'])}<br>{esc(r['department_decision'] or 'En attente')} {('— '+esc(r['department_comment']) if r['department_comment'] else '')}</div>
            <div><strong>Finance</strong><br>{esc(r['finance_budget_status'] or 'En attente')} {('— '+esc(r['finance_comment']) if r['finance_comment'] else '')}</div>
            <div><strong>Administrateur</strong><br>{esc(r['admin_decision'] or 'En attente')} {('— '+esc(r['admin_comment']) if r['admin_comment'] else '')}</div>
            <div><strong>Archivage / clôture</strong><br>{esc(r['closed_at'] or 'Non clôturée')}</div>
        </div>
        """
        body = f"""
        <div class="grid">
            <div class="card span-7">
                <div class="space"><h2>Demande #{r['id']}</h2>{status_badge(r['status'])}</div>
                <p><strong>Titre :</strong> {esc(r['title'])}</p>
                <p><strong>Agent :</strong> {esc(r['requester_name'])} — {esc(r['requester_email'])}</p>
                <p><strong>Type :</strong> {esc(r['request_type'])}</p>
                <p><strong>Montant :</strong> {esc(r['amount'])}</p>
                <p><strong>Département évaluateur :</strong> {esc(r['evaluator_department'])}</p>
                <p><strong>Description :</strong><br>{esc(r['description']).replace(chr(10), '<br>')}</p>
                {actions}
            </div>
            <div class="card span-5"><h2>Historique hiérarchique</h2>{timeline}</div>
        </div>
        """
        self.send_html(layout(f"Demande #{rid}", body, user))

    def request_actions(self, user: sqlite3.Row, r: sqlite3.Row) -> str:
        if user["role"] == "department" and r["status"] == "En attente évaluation département" and r["evaluator_department"] == user["department"]:
            return f"""
            <form method="post" action="/requests/{r['id']}/decision" class="card" style="background:#f8fafc">
                <h3>Décision du département</h3><label>Commentaire</label><textarea name="comment" required></textarea>
                <button name="action" value="department_approve" class="green">Approuver et transmettre à Finance</button>
                <button name="action" value="department_reject" class="danger">Refuser</button>
            </form>"""
        if user["role"] == "finance" and r["status"] == "En attente avis Finance":
            return f"""
            <form method="post" action="/requests/{r['id']}/decision" class="card" style="background:#f8fafc">
                <h3>Avis budgétaire Finance</h3><label>Commentaire budget</label><textarea name="comment" required></textarea>
                <button name="action" value="finance_ok" class="green">Budget disponible / Envoyer à Admin</button>
                <button name="action" value="finance_no" class="danger">Budget non disponible</button>
            </form>"""
        if user["role"] == "admin" and r["status"] == "En attente feu vert Admin":
            return f"""
            <form method="post" action="/requests/{r['id']}/decision" class="card" style="background:#f8fafc">
                <h3>Feu vert Administrateur</h3><label>Commentaire final</label><textarea name="comment" required></textarea>
                <button name="action" value="admin_release" class="green">Libérer les fonds / matériel et clôturer</button>
                <button name="action" value="admin_reject" class="danger">Refuser et clôturer</button>
            </form>"""
        return ""

    def request_decision(self, rid: int, method: str) -> None:
        user = self.require_user()
        if not user:
            return
        if method != "POST":
            self.redirect(f"/requests/{rid}"); return
        r = query_one("SELECT * FROM requests WHERE id=?", (rid,))
        if not r:
            self.not_found(); return
        data = self.parse_body()
        action = data.get("action", "")
        comment = data.get("comment", "").strip()
        if action == "department_approve" and user["role"] == "department" and r["evaluator_department"] == user["department"]:
            execute("UPDATE requests SET department_decision=?, department_comment=?, status=?, updated_at=? WHERE id=?", ("Approuvée par le département", comment, "En attente avis Finance", now_str(), rid))
        elif action == "department_reject" and user["role"] == "department" and r["evaluator_department"] == user["department"]:
            execute("UPDATE requests SET department_decision=?, department_comment=?, status=?, archived=1, closed_at=?, updated_at=? WHERE id=?", ("Refusée par le département", comment, "Refusée par le département", now_str(), now_str(), rid))
        elif action == "finance_ok" and user["role"] == "finance":
            execute("UPDATE requests SET finance_budget_status=?, finance_comment=?, status=?, updated_at=? WHERE id=?", ("Budget disponible", comment, "En attente feu vert Admin", now_str(), rid))
        elif action == "finance_no" and user["role"] == "finance":
            execute("UPDATE requests SET finance_budget_status=?, finance_comment=?, status=?, archived=1, closed_at=?, updated_at=? WHERE id=?", ("Budget non disponible", comment, "Budget refusé", now_str(), now_str(), rid))
        elif action == "admin_release" and user["role"] == "admin":
            execute("UPDATE requests SET admin_decision=?, admin_comment=?, status=?, archived=1, closed_at=?, updated_at=? WHERE id=?", ("Feu vert donné", comment, "Libérée et clôturée", now_str(), now_str(), rid))
        elif action == "admin_reject" and user["role"] == "admin":
            execute("UPDATE requests SET admin_decision=?, admin_comment=?, status=?, archived=1, closed_at=?, updated_at=? WHERE id=?", ("Refus final", comment, "Refusée et clôturée", now_str(), now_str(), rid))
        self.redirect(f"/requests/{rid}")

    def visible_vehicle_reports(self, user: sqlite3.Row) -> list[sqlite3.Row]:
        if user["role"] in ("admin", "logistique"):
            return query_all("SELECT vr.*, u.name chauffeur_name FROM vehicle_reports vr JOIN users u ON u.id=vr.chauffeur_id ORDER BY vr.id DESC")
        if user["role"] == "chauffeur":
            return query_all("SELECT vr.*, u.name chauffeur_name FROM vehicle_reports vr JOIN users u ON u.id=vr.chauffeur_id WHERE chauffeur_id=? ORDER BY vr.id DESC", (user["id"],))
        return []

    def report_row(self, r: sqlite3.Row) -> str:
        return f"<tr><td>#{r['id']}</td><td>{esc(r['chauffeur_name'])}</td><td>{esc(r['vehicle_plate'])}</td><td>{status_badge(r['status'])}</td><td><a class='btn secondary' href='/vehicle/reports/{r['id']}'>Ouvrir</a></td></tr>"

    def vehicle_reports(self) -> None:
        user = self.require_user()
        if not user: return
        reports = self.visible_vehicle_reports(user)
        rows = "".join(self.report_row(r) for r in reports) or '<tr><td colspan="5" class="muted">Aucun rapport.</td></tr>'
        body = f"""
        <div class="card">
            <div class="space"><h2>Rapports véhicules</h2><a class="btn" href="/vehicle/reports/new">Nouveau rapport</a></div>
            <table class="table"><tr><th>N°</th><th>Chauffeur</th><th>Véhicule</th><th>Statut</th><th>Action</th></tr>{rows}</table>
        </div>
        """
        self.send_html(layout("Rapports véhicules", body, user))

    def vehicle_report_new(self, method: str) -> None:
        user = self.require_user()
        if not user: return
        if user["role"] not in ("chauffeur", "admin"):
            self.send_html(layout("Non autorisé", '<div class="error">Seul un chauffeur peut créer un rapport véhicule.</div>', user), 403); return
        if method == "POST":
            data = self.parse_body()
            execute("""INSERT INTO vehicle_reports(chauffeur_id,vehicle_plate,report_type,kilometrage,fuel_level,description,lat,lon,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (user["id"], data.get("vehicle_plate",""), data.get("report_type",""), data.get("kilometrage",""), data.get("fuel_level",""), data.get("description",""), data.get("lat",""), data.get("lon",""), "Envoyé à Logistique", now_str(), now_str()))
            if data.get("lat") and data.get("lon"):
                execute("UPDATE users SET last_lat=?, last_lon=?, last_location_at=? WHERE id=?", (data.get("lat"), data.get("lon"), now_str(), user["id"]))
            self.redirect("/vehicle/reports"); return
        js = """
        <script>
        function getPos(){
          if(!navigator.geolocation){alert('Géolocalisation non disponible');return;}
          navigator.geolocation.getCurrentPosition(function(pos){
            document.getElementById('lat').value=pos.coords.latitude;
            document.getElementById('lon').value=pos.coords.longitude;
            document.getElementById('gpsmsg').innerText='Position capturée: '+pos.coords.latitude+', '+pos.coords.longitude;
          }, function(err){alert('Autorise la localisation dans le navigateur. Erreur: '+err.message);});
        }
        </script>"""
        body = """
        <div class="card">
            <h2>Nouveau rapport véhicule</h2>
            <p class="muted">Le rapport est envoyé au département Logistique. Tu peux ajouter la position GPS/GPRS avant l’envoi.</p>
            <form method="post">
                <label>Plaque / Code véhicule</label><input name="vehicle_plate" required>
                <label>Type de rapport</label><select name="report_type"><option>Départ mission</option><option>Retour mission</option><option>Panne</option><option>Accident</option><option>Carburant</option><option>Autre</option></select>
                <label>Kilométrage</label><input name="kilometrage">
                <label>Niveau carburant</label><input name="fuel_level" placeholder="Ex: 50%">
                <label>Description</label><textarea name="description" required></textarea>
                <input type="hidden" id="lat" name="lat"><input type="hidden" id="lon" name="lon">
                <p id="gpsmsg" class="muted">Aucune position capturée.</p>
                <button type="button" class="secondary" onclick="getPos()">Capturer ma position GPS/GPRS</button>
                <button>Envoyer à Logistique</button>
            </form>
        </div>"""
        self.send_html(layout("Nouveau rapport véhicule", body, user, js))

    def vehicle_report_detail(self, rid: int) -> None:
        user = self.require_user()
        if not user: return
        r = query_one("SELECT vr.*, u.name chauffeur_name, u.email chauffeur_email FROM vehicle_reports vr JOIN users u ON u.id=vr.chauffeur_id WHERE vr.id=?", (rid,))
        if not r: self.not_found(); return
        map_html = ""
        if r["lat"] and r["lon"]:
            q = urllib.parse.quote(f"{r['lat']},{r['lon']}")
            map_html = f'<p><a class="maplink" target="_blank" href="https://www.google.com/maps?q={q}">Voir la position sur Google Maps</a></p>'
        action = ""
        if user["role"] in ("logistique", "admin") and r["status"] != "Clôturé par Logistique":
            action = f"""
            <form method="post" action="/vehicle/reports/{rid}/decision" class="card" style="background:#f8fafc">
                <h3>Traitement Logistique</h3><label>Commentaire</label><textarea name="comment" required></textarea>
                <button class="green">Clôturer le rapport</button>
            </form>"""
        body = f"""
        <div class="card">
            <div class="space"><h2>Rapport véhicule #{r['id']}</h2>{status_badge(r['status'])}</div>
            <p><strong>Chauffeur :</strong> {esc(r['chauffeur_name'])} — {esc(r['chauffeur_email'])}</p>
            <p><strong>Véhicule :</strong> {esc(r['vehicle_plate'])}</p>
            <p><strong>Type :</strong> {esc(r['report_type'])}</p>
            <p><strong>Kilométrage :</strong> {esc(r['kilometrage'])}</p>
            <p><strong>Carburant :</strong> {esc(r['fuel_level'])}</p>
            <p><strong>Description :</strong><br>{esc(r['description']).replace(chr(10), '<br>')}</p>
            <p><strong>Position :</strong> {esc(r['lat'])}, {esc(r['lon'])}</p>{map_html}
            <p><strong>Commentaire Logistique :</strong> {esc(r['logistic_comment'])}</p>
            {action}
        </div>"""
        self.send_html(layout(f"Rapport #{rid}", body, user))

    def vehicle_report_decision(self, rid: int, method: str) -> None:
        user = self.require_user()
        if not user: return
        if method == "POST" and user["role"] in ("logistique", "admin"):
            data = self.parse_body()
            execute("UPDATE vehicle_reports SET status=?, logistic_comment=?, updated_at=? WHERE id=?", ("Clôturé par Logistique", data.get("comment",""), now_str(), rid))
        self.redirect(f"/vehicle/reports/{rid}")

    def update_location(self, method: str) -> None:
        user = self.require_user()
        if not user: return
        if method != "POST": self.send_json({"ok": False}, 405); return
        data = self.parse_body()
        lat = data.get("lat", "")
        lon = data.get("lon", "")
        execute("UPDATE users SET last_lat=?, last_lon=?, last_location_at=? WHERE id=?", (lat, lon, now_str(), user["id"]))
        self.send_json({"ok": True, "lat": lat, "lon": lon})

    def vehicle_positions(self) -> None:
        user = self.require_user()
        if not user: return
        if user["role"] not in ("logistique", "admin", "chauffeur"):
            self.send_html(layout("Positions", '<div class="error">Accès réservé à Logistique, Admin et Chauffeur.</div>', user), 403); return
        if user["role"] == "chauffeur":
            rows = query_all("SELECT * FROM users WHERE id=?", (user["id"],))
        else:
            rows = query_all("SELECT * FROM users WHERE role='chauffeur' ORDER BY name")
        tr = ""
        for u in rows:
            map_link = ""
            if u["last_lat"] and u["last_lon"]:
                q = urllib.parse.quote(f"{u['last_lat']},{u['last_lon']}")
                map_link = f'<a target="_blank" class="btn secondary" href="https://www.google.com/maps?q={q}">Carte</a>'
            tr += f"<tr><td>{user_avatar(u, 34)} {esc(u['name'])}</td><td>{esc(u['last_lat'])}</td><td>{esc(u['last_lon'])}</td><td>{esc(u['last_location_at'])}</td><td>{map_link}</td></tr>"
        js = """
        <script>
        function sharePosition(){
          if(!navigator.geolocation){alert('Géolocalisation non disponible');return;}
          navigator.geolocation.getCurrentPosition(function(pos){
            const body='lat='+encodeURIComponent(pos.coords.latitude)+'&lon='+encodeURIComponent(pos.coords.longitude);
            fetch('/api/chauffeur/location',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:body}).then(()=>location.reload());
          }, function(err){alert('Autorise la localisation. Erreur: '+err.message);});
        }
        </script>"""
        button = '<button onclick="sharePosition()">Partager / actualiser ma position</button>' if user["role"] == "chauffeur" else ""
        body = f"""
        <div class="card"><div class="space"><h2>Positions véhicules / chauffeurs</h2>{button}</div>
        <p class="muted">La position est visible si le chauffeur ouvre l’application et autorise la localisation.</p>
        <table class="table"><tr><th>Chauffeur</th><th>Latitude</th><th>Longitude</th><th>Dernière actualisation</th><th>Carte</th></tr>{tr or '<tr><td colspan="5">Aucune position.</td></tr>'}</table></div>"""
        self.send_html(layout("Positions véhicules", body, user, js))

    def moods(self, method: str) -> None:
        user = self.require_user()
        if not user: return
        if method == "POST":
            data = self.parse_body()
            text = data.get("text", "").strip()
            if text:
                expires = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
                execute("INSERT INTO moods(user_id,text,created_at,expires_at) VALUES(?,?,?,?)", (user["id"], text, now_str(), expires))
            self.redirect("/moods"); return
        body = f"""
        <div class="grid"><div class="card span-5"><h2>Poster mon humeur</h2>
        <form method="post"><label>Humeur du jour</label><textarea name="text" maxlength="500" required placeholder="Ex: Motivé aujourd’hui pour clôturer les dossiers..."></textarea><button>Publier pour 24h</button></form></div>
        <div class="card span-7"><h2>Humeurs visibles</h2>{self.mood_list(limit=50)}</div></div>"""
        self.send_html(layout("Humeurs 24h", body, user))

    def mood_list(self, limit: int = 10) -> str:
        rows = query_all("""SELECT m.*, u.name, u.photo_data FROM moods m JOIN users u ON u.id=m.user_id
                            WHERE datetime(m.expires_at) > datetime('now','localtime') ORDER BY m.id DESC LIMIT ?""", (limit,))
        if not rows:
            return '<p class="muted">Aucune humeur active.</p>'
        out = ""
        for m in rows:
            fake_user = {"name": m["name"], "photo_data": m["photo_data"]}
            # sqlite.Row-like access in user_avatar needs [] only; dict works.
            out += f"<div class='mood'>{user_avatar(fake_user, 38)}<div><strong>{esc(m['name'])}</strong><br>{esc(m['text'])}<br><small class='muted'>Expire: {esc(m['expires_at'])}</small></div></div>"
        return out

    def appearance(self, method: str) -> None:
        user = self.require_user()
        if not user:
            return
        prefs = get_user_preferences(int(user["id"]))
        msg = ""
        if method == "POST":
            data = self.parse_body()
            background = valid_image_data(data.get("personal_background", ""))
            if data.get("remove_background") == "yes":
                background = ""
            elif not background:
                background = valid_image_data(prefs["personal_background"])
            opacity = data.get("background_opacity", "0.16")
            if opacity not in ("0.08", "0.12", "0.16", "0.22", "0.30", "0.40"):
                opacity = "0.16"
            values = {
                "home_bg_color": safe_color(data.get("home_bg_color", ""), prefs["home_bg_color"]),
                "dashboard_bg_color": safe_color(data.get("dashboard_bg_color", ""), prefs["dashboard_bg_color"]),
                "requests_bg_color": safe_color(data.get("requests_bg_color", ""), prefs["requests_bg_color"]),
                "vehicles_bg_color": safe_color(data.get("vehicles_bg_color", ""), prefs["vehicles_bg_color"]),
                "moods_bg_color": safe_color(data.get("moods_bg_color", ""), prefs["moods_bg_color"]),
                "profile_bg_color": safe_color(data.get("profile_bg_color", ""), prefs["profile_bg_color"]),
                "admin_bg_color": safe_color(data.get("admin_bg_color", ""), prefs["admin_bg_color"]),
            }
            execute(
                """UPDATE user_preferences SET home_bg_color=?,dashboard_bg_color=?,requests_bg_color=?,vehicles_bg_color=?,moods_bg_color=?,profile_bg_color=?,admin_bg_color=?,personal_background=?,background_opacity=?,updated_at=? WHERE user_id=?""",
                (values["home_bg_color"], values["dashboard_bg_color"], values["requests_bg_color"], values["vehicles_bg_color"], values["moods_bg_color"], values["profile_bg_color"], values["admin_bg_color"], background, opacity, now_str(), user["id"]),
            )
            prefs = get_user_preferences(int(user["id"]))
            msg = '<div class="success">Votre apparence privée a été enregistrée. Les autres utilisateurs ne voient pas votre photo.</div>'
        js = file_to_base64_js("personal_bg_file", "personal_background", "personal_bg_preview") + appearance_preview_js()
        color_fields = [
            ("home_bg_color", "Accueil"),
            ("dashboard_bg_color", "Tableau de bord"),
            ("requests_bg_color", "Demandes"),
            ("vehicles_bg_color", "Véhicules"),
            ("moods_bg_color", "Humeurs"),
            ("profile_bg_color", "Profil / Apparence"),
            ("admin_bg_color", "Pages administratives"),
        ]
        color_inputs = "".join(
            f'<div><label>{esc(label)}</label><input class="page-color-input" type="color" name="{field}" value="{safe_color(prefs[field])}"></div>'
            for field, label in color_fields
        )
        preview_src = valid_image_data(prefs["personal_background"])
        body = f"""
        <div class="grid">
            <section class="card span-7">
                <h2>Mon apparence privée</h2>{msg}
                <p class="muted">Chaque couleur et la photo ci-dessous sont liées uniquement à votre compte. Elles ne modifient pas l’espace des autres utilisateurs.</p>
                <form method="post" id="appearance_form">
                    <h3>Couleurs de fond par page</h3>
                    <div class="color-grid">{color_inputs}</div>
                    <h3 style="margin-top:24px">Photo de fond personnelle</h3>
                    <label>Choisir une image de moins de 900 Ko</label>
                    <input id="personal_bg_file" type="file" accept="image/*">
                    <input type="hidden" id="personal_background" name="personal_background" value="{esc(preview_src)}">
                    <label>Visibilité de la photo</label>
                    <select name="background_opacity" id="background_opacity">
                        {''.join(f'<option value="{v}" {"selected" if prefs["background_opacity"]==v else ""}>{label}</option>' for v,label in [("0.08","Très légère"),("0.12","Légère"),("0.16","Normale"),("0.22","Visible"),("0.30","Forte"),("0.40","Très forte")])}
                    </select>
                    <label class="row"><input style="width:auto" type="checkbox" name="remove_background" value="yes"> Supprimer ma photo de fond</label>
                    <button>Enregistrer mon apparence</button>
                </form>
            </section>
            <aside class="card span-5">
                <h2>Aperçu</h2>
                <div class="appearance-preview" id="appearance_preview" style="--preview-color:{safe_color(prefs['profile_bg_color'])};--preview-image:{f'url(\'{esc(preview_src)}\')' if preview_src else 'none'}">
                    <span>Votre espace personnel</span>
                </div>
                <img id="personal_bg_preview" src="{esc(preview_src)}" style="display:none" alt="Aperçu image">
                <div class="notice" style="margin-top:16px"><strong>Confidentialité :</strong> l’image est enregistrée dans les préférences de votre compte et n’est injectée que lorsque vous êtes connecté.</div>
            </aside>
        </div>
        """
        self.send_html(layout("Mon apparence", body, user, js, page_key="profile"))

    def profile(self, method: str) -> None:
        user = self.require_user()
        if not user: return
        msg = ""
        if method == "POST":
            data = self.parse_body()
            name = data.get("name", "").strip() or user["name"]
            job_title = data.get("job_title", "").strip() or user["job_title"]
            photo = data.get("photo_data", "") or user["photo_data"]
            pwd = data.get("password", "")
            if pwd:
                execute("UPDATE users SET name=?, job_title=?, photo_data=?, password_hash=? WHERE id=?", (name, job_title, photo, hash_password(pwd), user["id"]))
            else:
                execute("UPDATE users SET name=?, job_title=?, photo_data=? WHERE id=?", (name, job_title, photo, user["id"]))
            SESSION_STORE.update({sid: uid for sid, uid in SESSION_STORE.items()})
            msg = '<div class="success">Profil mis à jour.</div>'
            user = query_one("SELECT * FROM users WHERE id=?", (user["id"],))
        js = file_to_base64_js("photo_file", "photo_data", "photo_preview")
        body = f"""
        <div class="card" style="max-width:760px">
            <h2>Mon profil</h2>{msg}
            <div class="row">{user_avatar(user, 80)}<div><strong>{esc(user['email'])}</strong><br><span class="muted">{esc(ROLES.get(user['role'],user['role']))} — {esc(user['job_title'] or 'Fonction non définie')} — {esc(user['department'])}</span></div></div>
            <form method="post">
                <label>Nom</label><input name="name" value="{esc(user['name'])}">
                <label>Fonction</label><input name="job_title" list="profile_job_titles" value="{esc(user['job_title'])}" placeholder="Ex: Déclarant chargé des opérations">
                <datalist id="profile_job_titles">{"".join(f'<option value="{esc(j)}"></option>' for j in JOB_TITLES)}</datalist>
                <label>Changer ma photo de profil</label><input id="photo_file" type="file" accept="image/*"><input type="hidden" id="photo_data" name="photo_data" value="{esc(user['photo_data'])}">
                <p><img id="photo_preview" src="{esc(user['photo_data'])}" style="max-width:120px;max-height:120px;border-radius:16px"></p>
                <label>Nouveau mot de passe, facultatif</label><input type="password" name="password">
                <button>Enregistrer</button>
            </form>
        </div>
        """
        self.send_html(layout("Profil", body, user, js))

    def settings(self, method: str) -> None:
        user = self.require_user()
        if not user:
            return
        if user["role"] != "admin":
            self.send_html(layout("Non autorisé", '<div class="error">Accès réservé à l’administrateur.</div>', user), 403)
            return
        msg = ""
        if method == "POST":
            data = self.parse_body()
            logo = valid_image_data(data.get("logo_data", "")) or get_logo()
            hero = valid_image_data(data.get("hero_image_data", "")) or valid_image_data(get_setting("homepage_hero_image", ""))
            if data.get("remove_hero_image") == "yes":
                hero = ""
            set_setting("company_logo", logo)
            set_setting("homepage_badge", data.get("homepage_badge", "").strip()[:120])
            set_setting("homepage_title", data.get("homepage_title", "").strip()[:180])
            set_setting("homepage_subtitle", data.get("homepage_subtitle", "").strip()[:400])
            set_setting("homepage_message", data.get("homepage_message", "").strip()[:400])
            set_setting("homepage_primary_cta", data.get("homepage_primary_cta", "").strip()[:80])
            set_setting("homepage_secondary_cta", data.get("homepage_secondary_cta", "").strip()[:80])
            set_setting("homepage_hero_image", hero)
            position = data.get("sidebar_position", "left")
            set_setting("sidebar_position", position if position in ("left", "right") else "left")
            submitted_order = [x for x in data.get("menu_order", "").split(",") if x in MENU_ITEMS]
            if submitted_order:
                set_setting("menu_order", ",".join(submitted_order))
            msg = '<div class="success">La page d’accueil, le menu et l’identité visuelle ont été mis à jour.</div>'
        logo = get_logo()
        hero = valid_image_data(get_setting("homepage_hero_image", ""))
        order = get_menu_order()
        sortable = "".join(
            f'<li class="sortable-item" draggable="true" data-key="{key}"><span class="nav-icon">{MENU_ITEMS[key][0]}</span><strong>{esc(MENU_ITEMS[key][1])}</strong><span class="sort-actions"><button type="button" class="move-up secondary">↑</button><button type="button" class="move-down secondary">↓</button></span></li>'
            for key in order
        )
        js = (
            file_to_base64_js("logo_file", "logo_data", "logo_preview")
            + file_to_base64_js("hero_image_file", "hero_image_data", "hero_image_preview")
            + menu_sort_js()
        )
        current_position = get_setting("sidebar_position", "left")
        body = f"""
        <div class="grid">
            <section class="card span-7">
                <h2>Page d’accueil professionnelle</h2>{msg}
                <p class="muted">Ces informations sont visibles par tous les visiteurs de la page d’accueil.</p>
                <form method="post" id="admin_settings_form">
                    <label>Logo de l’entreprise</label><input id="logo_file" type="file" accept="image/*"><input type="hidden" id="logo_data" name="logo_data" value="{esc(logo)}">
                    <p><img id="logo_preview" src="{esc(logo)}" style="max-width:180px;max-height:120px;border-radius:16px"></p>
                    <label>Petit message supérieur</label><input name="homepage_badge" value="{esc(get_setting('homepage_badge'))}">
                    <label>Grand titre</label><input name="homepage_title" value="{esc(get_setting('homepage_title'))}" required>
                    <label>Sous-titre</label><textarea name="homepage_subtitle" required>{esc(get_setting('homepage_subtitle'))}</textarea>
                    <label>Message complémentaire</label><textarea name="homepage_message">{esc(get_setting('homepage_message'))}</textarea>
                    <div class="color-grid"><div><label>Bouton principal</label><input name="homepage_primary_cta" value="{esc(get_setting('homepage_primary_cta'))}"></div><div><label>Bouton secondaire</label><input name="homepage_secondary_cta" value="{esc(get_setting('homepage_secondary_cta'))}"></div></div>
                    <label>Image principale de l’accueil</label><input id="hero_image_file" type="file" accept="image/*"><input type="hidden" id="hero_image_data" name="hero_image_data" value="{esc(hero)}">
                    <p><img id="hero_image_preview" src="{esc(hero)}" style="width:100%;max-height:220px;object-fit:cover;border-radius:16px"></p>
                    <label class="row"><input style="width:auto" type="checkbox" name="remove_hero_image" value="yes"> Supprimer l’image principale</label>
                    <h3>Disposition générale du menu</h3>
                    <label>Côté du menu</label><select name="sidebar_position"><option value="left" {"selected" if current_position=="left" else ""}>À gauche</option><option value="right" {"selected" if current_position=="right" else ""}>À droite</option></select>
                    <input type="hidden" id="menu_order" name="menu_order" value="{esc(','.join(order))}">
                    <ul class="sortable-list" id="sortable_menu">{sortable}</ul>
                    <button>Enregistrer tous les paramètres</button>
                    <a class="btn secondary" href="/" target="_blank">Voir la page d’accueil</a>
                </form>
            </section>
            <aside class="card span-5">
                <h2>Pouvoir administrateur</h2>
                <div class="notice">Vous pouvez déplacer les options avec la souris ou les flèches ↑ ↓. L’ordre s’applique à tous, mais les options réservées restent masquées selon les rôles.</div>
                <h3>Règles de confidentialité</h3>
                <p class="muted">L’administrateur modifie l’accueil public, le logo et la disposition. Il ne voit pas et ne choisit pas les images de fond privées des utilisateurs.</p>
                <h3>Conseil design</h3>
                <p class="muted">Utilisez une image horizontale, sobre et légère. Évitez les textes intégrés dans l’image pour préserver la lisibilité sur mobile.</p>
            </aside>
        </div>
        """
        self.send_html(layout("Paramètres", body, user, js, page_key="admin"))

    def users(self, method: str) -> None:
        user = self.require_user()
        if not user: return
        if user["role"] != "admin":
            self.send_html(layout("Non autorisé", '<div class="error">Accès réservé à l’administrateur.</div>', user), 403); return
        msg = ""
        if method == "POST":
            data = self.parse_body()
            action = data.get("action", "create_user")
            if action == "reset_password":
                target_id = data.get("user_id", "")
                new_password = data.get("new_password", "").strip()
                if not target_id.isdigit() or not new_password:
                    msg = '<div class="error">Sélectionne un utilisateur et entre le nouveau mot de passe.</div>'
                elif len(new_password) < 4:
                    msg = '<div class="error">Le nouveau mot de passe doit avoir au moins 4 caractères.</div>'
                else:
                    target = query_one("SELECT id, email, name FROM users WHERE id=?", (int(target_id),))
                    if target:
                        execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_password), int(target_id)))
                        execute(
                            "UPDATE password_reset_requests SET status='Traité', processed_at=? WHERE user_id=? AND status='En attente'",
                            (now_str(), int(target_id)),
                        )
                        msg = f'<div class="success">Mot de passe réinitialisé pour {esc(target["name"])}. Nouveau mot de passe : <strong>{esc(new_password)}</strong></div>'
                    else:
                        msg = '<div class="error">Utilisateur introuvable.</div>'
            elif data.get("email") and data.get("password"):
                try:
                    execute(
                        "INSERT INTO users(name,email,password_hash,role,department,job_title,created_at) VALUES(?,?,?,?,?,?,?)",
                        (
                            data.get("name","").strip(),
                            data.get("email","").lower().strip(),
                            hash_password(data.get("password","")),
                            data.get("role","agent"),
                            data.get("department","Operations"),
                            data.get("job_title","").strip(),
                            now_str()
                        )
                    )
                    msg = '<div class="success">Utilisateur créé.</div>'
                except sqlite3.IntegrityError:
                    msg = '<div class="error">Cet email existe déjà.</div>'

        role_opts = "".join(f'<option value="{esc(k)}">{esc(v)}</option>' for k,v in ROLES.items())
        dep_opts = "".join(f'<option value="{esc(d)}">{esc(d)}</option>' for d in DEPARTMENTS)
        job_options = "".join(f'<option value="{esc(j)}"></option>' for j in JOB_TITLES)

        rows = query_all("SELECT * FROM users ORDER BY id DESC")
        trs = ""
        user_select_opts = ""
        for u in rows:
            fonction = u["job_title"] or "Non définie"
            user_select_opts += f'<option value="{u["id"]}">{esc(u["name"])} — {esc(u["email"])} — {esc(fonction)}</option>'
            trs += (
                f"<tr>"
                f"<td>{user_avatar(u,34)} {esc(u['name'])}</td>"
                f"<td>{esc(u['email'])}</td>"
                f"<td>{esc(ROLES.get(u['role'],u['role']))}</td>"
                f"<td>{esc(fonction)}</td>"
                f"<td>{esc(u['department'])}</td>"
                f"</tr>"
            )

        reset_rows = query_all("""
            SELECT pr.*, u.name AS user_name
            FROM password_reset_requests pr
            LEFT JOIN users u ON u.id=pr.user_id
            ORDER BY pr.id DESC
            LIMIT 10
        """)
        reset_trs = "".join(
            f"<tr><td>{esc(r['email'])}</td><td>{esc(r['user_name'] or '-')}</td><td>{esc(r['message'])}</td><td>{esc(r['status'])}</td><td>{esc(r['created_at'])}</td></tr>"
            for r in reset_rows
        ) or '<tr><td colspan="5" class="muted">Aucune demande de réinitialisation.</td></tr>'

        body = f"""
        <div class="grid">
          <div class="card span-5">
            <h2>Créer un utilisateur interne</h2>{msg}
            <form method="post">
              <input type="hidden" name="action" value="create_user">
              <label>Nom</label><input name="name" required>
              <label>Email</label><input name="email" type="email" required>
              <label>Mot de passe</label><input name="password" required>
              <label>Rôle</label><select name="role">{role_opts}</select>
              <label>Fonction</label><input name="job_title" list="admin_job_titles" placeholder="Ex: DRH, Déclarant, Chef d’agence..." required>
              <datalist id="admin_job_titles">{job_options}</datalist>
              <label>Département</label><select name="department">{dep_opts}</select>
              <button>Créer</button>
            </form>
          </div>

          <div class="card span-7">
            <h2>Réinitialiser un mot de passe</h2>
            <p class="muted">Si un agent, chauffeur ou autre utilisateur oublie son code, l’administrateur choisit son compte et définit un nouveau mot de passe.</p>
            <form method="post">
              <input type="hidden" name="action" value="reset_password">
              <label>Utilisateur</label><select name="user_id" required>{user_select_opts}</select>
              <label>Nouveau mot de passe</label><input name="new_password" required placeholder="Ex: nouveau123">
              <button>Réinitialiser le mot de passe</button>
            </form>
          </div>

          <div class="card span-12">
            <h2>Demandes “mot de passe oublié”</h2>
            <table class="table"><tr><th>Email</th><th>Utilisateur</th><th>Message</th><th>Statut</th><th>Date</th></tr>{reset_trs}</table>
          </div>

          <div class="card span-12">
            <h2>Utilisateurs</h2>
            <table class="table"><tr><th>Nom</th><th>Email</th><th>Rôle</th><th>Fonction</th><th>Département</th></tr>{trs}</table>
          </div>
        </div>"""
        self.send_html(layout("Utilisateurs", body, user))


def login_customizer_js() -> str:
    return """
    <script>
    document.addEventListener('DOMContentLoaded', function(){
      const body=document.body, layer=document.querySelector('.personal-bg-layer');
      const panel=document.getElementById('login_customizer');
      const toggle=document.getElementById('theme_toggle');
      const close=document.getElementById('close_customizer');
      const color=document.getElementById('login_bg_color');
      const file=document.getElementById('login_bg_file');
      const preview=document.getElementById('login_bg_preview');
      const clear=document.getElementById('clear_login_bg');
      function apply(){
        const c=localStorage.getItem('fundflow_login_color') || '#eef4ff';
        const img=localStorage.getItem('fundflow_login_image') || '';
        body.style.setProperty('--page-bg',c); color.value=c;
        body.style.setProperty('--personal-bg-image',img ? 'url("'+img+'")' : 'none');
        body.style.setProperty('--personal-bg-opacity',img ? '0.32' : '0.16');
        preview.src=img || '';
      }
      toggle.addEventListener('click',()=>panel.classList.toggle('open'));
      close.addEventListener('click',()=>panel.classList.remove('open'));
      color.addEventListener('input',()=>{localStorage.setItem('fundflow_login_color',color.value);apply();});
      file.addEventListener('change',function(){
        const f=this.files[0]; if(!f) return;
        if(f.size>900000){alert('Choisis une image de moins de 900 Ko.');this.value='';return;}
        const reader=new FileReader(); reader.onload=e=>{localStorage.setItem('fundflow_login_image',e.target.result);apply();}; reader.readAsDataURL(f);
      });
      clear.addEventListener('click',()=>{localStorage.removeItem('fundflow_login_image');file.value='';apply();});
      apply();
    });
    </script>
    """


def appearance_preview_js() -> str:
    return """
    <script>
    document.addEventListener('DOMContentLoaded', function(){
      const preview=document.getElementById('appearance_preview');
      const hidden=document.getElementById('personal_background');
      const colors=document.querySelectorAll('.page-color-input');
      const opacity=document.getElementById('background_opacity');
      function refresh(){
        const profileColor=document.querySelector('[name="profile_bg_color"]');
        preview.style.setProperty('--preview-color',profileColor ? profileColor.value : '#f4f6fb');
        preview.style.setProperty('--preview-image',hidden.value ? 'linear-gradient(rgba(255,255,255,'+(1-parseFloat(opacity.value))+'),rgba(255,255,255,'+(1-parseFloat(opacity.value))+')),url("'+hidden.value+'")' : 'none');
      }
      colors.forEach(el=>el.addEventListener('input',refresh));
      opacity.addEventListener('change',refresh);
      const observer=new MutationObserver(refresh); observer.observe(hidden,{attributes:true,attributeFilter:['value']});
      document.getElementById('personal_bg_file').addEventListener('change',()=>setTimeout(refresh,100));
      refresh();
    });
    </script>
    """


def menu_sort_js() -> str:
    return """
    <script>
    document.addEventListener('DOMContentLoaded', function(){
      const list=document.getElementById('sortable_menu');
      const hidden=document.getElementById('menu_order');
      let dragged=null;
      function sync(){hidden.value=[...list.querySelectorAll('.sortable-item')].map(x=>x.dataset.key).join(',');}
      list.querySelectorAll('.sortable-item').forEach(item=>{
        item.addEventListener('dragstart',()=>{dragged=item;item.classList.add('dragging');});
        item.addEventListener('dragend',()=>{item.classList.remove('dragging');dragged=null;sync();});
        item.addEventListener('dragover',e=>{e.preventDefault();if(!dragged||dragged===item)return;const box=item.getBoundingClientRect();list.insertBefore(dragged,e.clientY<box.top+box.height/2?item:item.nextSibling);});
        item.querySelector('.move-up').addEventListener('click',()=>{if(item.previousElementSibling)list.insertBefore(item,item.previousElementSibling);sync();});
        item.querySelector('.move-down').addEventListener('click',()=>{if(item.nextElementSibling)list.insertBefore(item.nextElementSibling,item);sync();});
      });
      sync();
    });
    </script>
    """


def file_to_base64_js(file_id: str, hidden_id: str, preview_id: str) -> str:
    return f"""
    <script>
    document.addEventListener('DOMContentLoaded', function() {{
      const file=document.getElementById('{file_id}');
      const hidden=document.getElementById('{hidden_id}');
      const preview=document.getElementById('{preview_id}');
      if(file) {{
        file.addEventListener('change', function() {{
          const f=this.files[0]; if(!f) return;
          if(f.size > 900000) {{ alert('Image trop lourde. Choisis une image de moins de 900 Ko.'); this.value=''; return; }}
          const reader=new FileReader();
          reader.onload=function(e) {{ hidden.value=e.target.result; if(preview) preview.src=e.target.result; }};
          reader.readAsDataURL(f);
        }});
      }}
    }});
    </script>
    """


def find_free_port(start: int = 5000) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def run_server(open_browser: bool = True) -> None:
    init_db()
    raw_port = os.environ.get("PORT", "0") or "0"
    port = int(raw_port) if raw_port.isdigit() and int(raw_port) > 0 else find_free_port(5000)
    host = "0.0.0.0"
    public_url = os.environ.get("PUBLIC_URL", "").strip()
    url = public_url or f"http://127.0.0.1:{port}"
    server = ThreadingHTTPServer((host, port), FundFlowHandler)
    print("=" * 60)
    print("FUNDFLOW STABLE - SERVEUR DÉMARRÉ")
    print(f"Adresse : {url}")
    print(f"Port utilisé : {port}")
    print("Pour arrêter : CTRL + C")
    print("=" * 60)
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt demandé.")
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        run_server(open_browser=("--no-browser" not in sys.argv and not os.environ.get("PORT")))
    except Exception:
        tb = traceback.format_exc()
        log_error(tb)
        print(tb)
        try:
            if sys.stdin and sys.stdin.isatty():
                input("Appuie sur Entrée pour fermer...")
        except EOFError:
            pass

