# -*- coding: utf-8 -*-
import os
import time
import json
import re
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = "seyfetin_efendi_panel_secret_2026"
app.config['JSON_AS_ASCII'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ========== KULLANICI VERİTABANI ==========
USERS = {
    "babalar@gmail.com": {
        "password": "uykumvar",
        "role": "kurucu",
        "expires": None
    },
    "vipadamya@gmail.com": {
        "password": "viplerebak",
        "role": "vip",
        "expires": (datetime.now() + timedelta(days=30)).isoformat()
    }
}

FREE_USERS = {}

# ========== ANA SAYFA ==========
INDEX_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Seyfetin Efendi Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', sans-serif; }
        body {
            min-height: 100vh;
            background: url('https://i.ibb.co/Ldc4b2YF/file-00000000f190720cb7f53c717d6f458d.png') no-repeat center center fixed;
            background-size: cover;
            position: relative;
        }
        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(2px);
            z-index: 0;
        }
        
        .menu-toggle {
            position: fixed;
            top: 28px;
            right: 28px;
            width: 60px;
            height: 60px;
            background: #0a0c12;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 30px;
            color: white;
            cursor: pointer;
            z-index: 1001;
            box-shadow: 0 15px 35px rgba(0,0,0,0.6);
            transition: 0.2s;
        }
        .menu-toggle:hover {
            background: #141a24;
            border-color: #2a6df4;
            transform: scale(1.05);
        }
        
        .side-menu {
            position: fixed;
            top: 0;
            right: -400px;
            width: 380px;
            height: 100vh;
            background: #0b0d12;
            border-left: 1px solid rgba(255,255,255,0.05);
            box-shadow: -15px 0 50px rgba(0,0,0,0.9);
            z-index: 1002;
            transition: right 0.4s;
            display: flex;
            flex-direction: column;
            color: white;
            overflow-y: auto;
        }
        .side-menu.open { right: 0; }
        
        .profile-section {
            padding: 30px 20px;
            background: #05070a;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .profile-avatar {
            width: 70px;
            height: 70px;
            border-radius: 24px;
            overflow: hidden;
            border: 2px solid rgba(255,255,255,0.2);
        }
        .profile-avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .profile-name {
            font-size: 20px;
            font-weight: 600;
            color: white;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .blue-tick { color: #3b82f6; font-size: 20px; }
        .online-status {
            display: flex;
            align-items: center;
            gap: 6px;
            background: rgba(0,0,0,0.6);
            border-left: 3px solid #2ecc71;
            padding: 4px 12px;
            border-radius: 30px;
            font-size: 13px;
            color: #d0f0d0;
            width: fit-content;
        }
        .online-dot {
            width: 8px;
            height: 8px;
            background: #2ecc71;
            border-radius: 50%;
            box-shadow: 0 0 12px #2ecc71;
        }
        
        .menu-categories {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
        }
        .category-block {
            margin-bottom: 15px;
            border-radius: 18px;
            background: rgba(20,25,35,0.4);
        }
        .category-header {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 15px 18px;
            background: #11161f;
            border-radius: 16px;
            font-weight: 600;
            color: #f0f5ff;
            cursor: pointer;
        }
        .category-header i { color: #5f9eff; width: 26px; }
        .category-header .arrow {
            margin-left: auto;
            transition: transform 0.3s;
            color: #8aabff;
        }
        .query-list {
            list-style: none;
            margin: 6px 0 8px 12px;
            padding-left: 20px;
            border-left: 2px solid rgba(70,130,255,0.25);
            display: none;
        }
        .query-list.open { display: block; }
        .query-item {
            padding: 12px 16px;
            margin: 6px 0;
            background: #0f141e;
            border-radius: 14px;
            color: #e0eaff;
            display: flex;
            align-items: center;
            gap: 12px;
            cursor: pointer;
            transition: 0.15s;
        }
        .query-item i { color: #72b0ff; width: 22px; }
        .query-item:hover {
            background: #1b2435;
            border-color: #3b82f6;
            transform: translateX(4px);
        }
        
        .content {
            position: relative;
            z-index: 1;
            padding: 40px;
            color: white;
        }
        .welcome-box {
            background: rgba(0,0,0,0.5);
            backdrop-filter: blur(10px);
            border-radius: 40px;
            padding: 40px;
            max-width: 600px;
            border: 1px solid rgba(255,255,255,0.1);
            margin-top: 60px;
        }
        .welcome-box h1 {
            font-size: 48px;
            margin-bottom: 20px;
            background: linear-gradient(135deg, #fff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .stats {
            display: flex;
            gap: 20px;
            margin-top: 30px;
        }
        .stat-item {
            background: rgba(59,130,246,0.2);
            border: 1px solid #3b82f6;
            border-radius: 30px;
            padding: 15px 25px;
            text-align: center;
        }
        .stat-value { font-size: 28px; font-weight: 700; color: #3b82f6; }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
</head>
<body>
    <div class="menu-toggle" id="menuToggle">
        <i class="fas fa-bars"></i>
    </div>
    
    <div class="side-menu" id="sideMenu">
        <div class="profile-section">
            <div class="profile-avatar">
                <img src="https://i.ibb.co/CpSZFTbK/blank.jpg" alt="Profil">
            </div>
            <div class="profile-info">
                <div class="profile-name">
                    {{ session.email.split('@')[0] if session.email else 'Misafir' }}
                    <span class="blue-tick"><i class="fas fa-check-circle"></i></span>
                </div>
                <div class="online-status">
                    <span class="online-dot"></span> çevrim içi
                </div>
            </div>
        </div>
        
        <div class="menu-categories">
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-id-card"></i> 1️⃣ Kimlik Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('isegiris', 'ad')"><i class="fas fa-briefcase"></i> İşe Giriş (Ad Soyad)</li>
                    <li class="query-item" onclick="goToQuery('ikametgah', 'ad')"><i class="fas fa-home"></i> İkametgah (Ad Soyad)</li>
                    <li class="query-item" onclick="goToQuery('ailebirey', 'ad')"><i class="fas fa-users"></i> Aile/Birey (Ad Soyad)</li>
                    <li class="query-item" onclick="goToQuery('medenicinsiyet', 'ad')"><i class="fas fa-venus-mars"></i> Medeni/Cinsiyet (Ad Soyad)</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-id-card"></i> 2️⃣ TC Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('tc-isegiris', 'tc')"><i class="fas fa-briefcase"></i> TC İşe Giriş</li>
                    <li class="query-item" onclick="goToQuery('tc-ikametgah', 'tc')"><i class="fas fa-home"></i> TC İkametgah</li>
                    <li class="query-item" onclick="goToQuery('tc-ailebirey', 'tc')"><i class="fas fa-users"></i> TC Aile/Birey</li>
                    <li class="query-item" onclick="goToQuery('tc-medenicinsiyet', 'tc')"><i class="fas fa-venus-mars"></i> TC Medeni/Cinsiyet</li>
                    <li class="query-item" onclick="goToQuery('tc', 'tc')"><i class="fas fa-search"></i> TC Detaylı</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-phone-alt"></i> 3️⃣ GSM Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('gsm', 'gsm')"><i class="fas fa-phone"></i> GSM</li>
                    <li class="query-item" onclick="goToQuery('gsm2', 'gsm')"><i class="fas fa-phone"></i> GSM2</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-car"></i> 4️⃣ Plaka Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('plaka', 'plaka')"><i class="fas fa-car"></i> Plaka</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-users"></i> 5️⃣ Aile Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('aile', 'tc')"><i class="fas fa-users"></i> Aile</li>
                    <li class="query-item" onclick="goToQuery('sulale', 'tc')"><i class="fas fa-tree"></i> Sülale</li>
                    <li class="query-item" onclick="goToQuery('hane', 'tc')"><i class="fas fa-home"></i> Hane</li>
                    <li class="query-item" onclick="goToQuery('isyeri', 'tc')"><i class="fas fa-briefcase"></i> İşyeri</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-user"></i> 6️⃣ Ad Soyad Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('query', 'ad')"><i class="fas fa-search"></i> Query</li>
                    <li class="query-item" onclick="goToQuery('ad', 'ad')"><i class="fas fa-search"></i> Ad</li>
                </ul>
            </div>
        </div>
    </div>
    
    <div class="content">
        <div class="welcome-box">
            <h1>Seyfetin Efendi Panel</h1>
            <p>Hoş geldiniz, <strong>{{ session.email if session.email else 'Misafir' }}</strong>!<br>Yetkiniz: <span style="color: #3b82f6;">{{ session.role if session.role else 'Misafir' }}</span></p>
            
            {% if session.role in ['vip', 'kurucu'] %}
            <div class="stats">
                <div class="stat-item"><div class="stat-value">19+</div><div class="stat-label">API</div></div>
                <div class="stat-item"><div class="stat-value">60s</div><div class="stat-label">Timeout</div></div>
            </div>
            <p style="margin-top:20px;">Menüden sorgu seçin</p>
            {% else %}
            <p style="margin-top:20px; color:#fbbf24;">🔒 Sorgu için <a href="/market" style="color:#3b82f6;">VIP satın al</a></p>
            {% endif %}
        </div>
    </div>
    
    <script>
        document.getElementById('menuToggle').onclick = () => {
            document.getElementById('sideMenu').classList.toggle('open');
        };
        
        document.addEventListener('click', (e) => {
            const menu = document.getElementById('sideMenu');
            const toggle = document.getElementById('menuToggle');
            if (!menu.contains(e.target) && !toggle.contains(e.target)) {
                menu.classList.remove('open');
            }
        });
        
        function toggleCategory(header) {
            const list = header.nextElementSibling;
            const arrow = header.querySelector('.arrow');
            list.classList.toggle('open');
            arrow.style.transform = list.classList.contains('open') ? 'rotate(180deg)' : 'rotate(0deg)';
        }
        
        function goToQuery(endpoint, type) {
            window.location.href = `/sorgu?endpoint=${endpoint}&type=${type}`;
        }
    </script>
</body>
</html>
"""

# ========== GİRİŞ SAYFASI ==========
LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Seyfetin Efendi · giriş</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:'Inter',sans-serif; }
        body {
            min-height:100vh;
            background:url('https://i.ibb.co/Ldc4b2YF/file-00000000f190720cb7f53c717d6f458d.png') no-repeat center center fixed;
            background-size:cover;
            display:flex;
            align-items:center;
            justify-content:center;
        }
        body::before {
            content:'';
            position:fixed;
            top:0; left:0; width:100%; height:100%;
            background:rgba(0,0,0,0.6);
            backdrop-filter:blur(8px);
            z-index:0;
        }
        .login-box {
            position:relative;
            z-index:1;
            width:100%;
            max-width:420px;
            background:rgba(10,15,25,0.95);
            border-radius:32px;
            padding:40px 32px;
            border:1px solid rgba(255,255,255,0.05);
        }
        .logo {
            text-align:center;
            margin-bottom:32px;
        }
        .logo i {
            font-size:64px;
            color:#3b82f6;
            filter:drop-shadow(0 0 15px #3b82f6);
        }
        .logo h1 {
            color:white;
            font-size:32px;
            margin-top:12px;
        }
        .form-group { margin-bottom:20px; }
        .form-group input {
            width:100%;
            padding:16px 18px;
            background:rgba(20,28,40,0.8);
            border:1px solid rgba(255,255,255,0.08);
            border-radius:18px;
            color:white;
            font-size:16px;
            outline:none;
        }
        .form-group input:focus { border-color:#3b82f6; }
        .login-btn {
            width:100%;
            padding:18px;
            background:linear-gradient(135deg,#3b82f6,#2563eb);
            border:none;
            border-radius:24px;
            color:white;
            font-size:18px;
            font-weight:600;
            cursor:pointer;
            transition:0.2s;
        }
        .login-btn:hover { transform:scale(1.02); }
        .register-link {
            text-align:center;
            margin-top:28px;
            color:#8596a8;
        }
        .register-link a { color:#3b82f6; text-decoration:none; }
        .error {
            background:rgba(220,38,38,0.2);
            border:1px solid #ef4444;
            border-radius:18px;
            padding:14px;
            color:#fca5a5;
            margin-bottom:20px;
            text-align:center;
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
</head>
<body>
    <div class="login-box">
        <div class="logo">
            <i class="fas fa-crown"></i>
            <h1>Seyfetin Efendi</h1>
        </div>
        
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        
        <form method="POST">
            <div class="form-group">
                <input type="email" name="email" placeholder="E-posta" required>
            </div>
            <div class="form-group">
                <input type="password" name="password" placeholder="Şifre" required>
            </div>
            <button type="submit" class="login-btn">GİRİŞ YAP</button>
        </form>
        
        <div class="register-link">
            Hesabın yok mu? <a href="/register">Kayıt ol</a>
        </div>
    </div>
</body>
</html>
"""

# ========== KAYIT SAYFASI ==========
REGISTER_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Seyfetin Efendi · kayıt</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:'Inter',sans-serif; }
        body {
            min-height:100vh;
            background:url('https://i.ibb.co/Ldc4b2YF/file-00000000f190720cb7f53c717d6f458d.png') no-repeat center center fixed;
            background-size:cover;
            display:flex;
            align-items:center;
            justify-content:center;
        }
        body::before {
            content:'';
            position:fixed;
            top:0; left:0; width:100%; height:100%;
            background:rgba(0,0,0,0.6);
            backdrop-filter:blur(8px);
            z-index:0;
        }
        .register-box {
            position:relative;
            z-index:1;
            width:100%;
            max-width:420px;
            background:rgba(10,15,25,0.95);
            border-radius:32px;
            padding:40px 32px;
            border:1px solid rgba(255,255,255,0.05);
        }
        .logo {
            text-align:center;
            margin-bottom:32px;
        }
        .logo i {
            font-size:56px;
            color:#10b981;
            filter:drop-shadow(0 0 15px #10b981);
        }
        .logo h2 {
            color:white;
            font-size:28px;
            margin-top:12px;
        }
        .form-group { margin-bottom:20px; }
        .form-group input {
            width:100%;
            padding:16px 18px;
            background:rgba(20,28,40,0.8);
            border:1px solid rgba(255,255,255,0.08);
            border-radius:18px;
            color:white;
            font-size:16px;
            outline:none;
        }
        .form-group input:focus { border-color:#10b981; }
        .register-btn {
            width:100%;
            padding:18px;
            background:linear-gradient(135deg,#10b981,#059669);
            border:none;
            border-radius:24px;
            color:white;
            font-size:18px;
            font-weight:600;
            cursor:pointer;
            transition:0.2s;
        }
        .register-btn:hover { transform:scale(1.02); }
        .login-link {
            text-align:center;
            margin-top:28px;
            color:#8596a8;
        }
        .login-link a { color:#10b981; text-decoration:none; }
        .error {
            background:rgba(220,38,38,0.2);
            border:1px solid #ef4444;
            border-radius:18px;
            padding:14px;
            color:#fca5a5;
            margin-bottom:20px;
        }
        .success {
            background:rgba(16,185,129,0.2);
            border:1px solid #10b981;
            border-radius:18px;
            padding:14px;
            color:#a7f3d0;
            margin-bottom:20px;
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
</head>
<body>
    <div class="register-box">
        <div class="logo">
            <i class="fas fa-user-plus"></i>
            <h2>ücretsiz kayıt</h2>
        </div>
        
        {% if error %}<div class="error">{{ error }}</div>{% endif %}
        {% if success %}<div class="success">{{ success }}</div>{% endif %}
        
        <form method="POST">
            <div class="form-group">
                <input type="email" name="email" placeholder="E-posta" required>
            </div>
            <div class="form-group">
                <input type="password" name="password" placeholder="Şifre" required>
            </div>
            <div class="form-group">
                <input type="password" name="confirm_password" placeholder="Şifre Tekrar" required>
            </div>
            <button type="submit" class="register-btn">KAYIT OL</button>
        </form>
        
        <div class="login-link">
            Zaten hesabın var mı? <a href="/login">Giriş yap</a>
        </div>
    </div>
</body>
</html>
"""

# ========== MARKET SAYFASI ==========
MARKET_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Seyfetin Efendi · market</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:'Inter',sans-serif; }
        body {
            background:#0a0c12;
            min-height:100vh;
            color:white;
        }
        .navbar {
            background:rgba(0,0,0,0.8);
            backdrop-filter:blur(12px);
            border-bottom:1px solid rgba(255,255,255,0.05);
            padding:16px 32px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            position:sticky;
            top:0;
        }
        .nav-brand {
            display:flex;
            align-items:center;
            gap:12px;
        }
        .nav-brand i { font-size:28px; color:#3b82f6; }
        .nav-brand span { font-size:22px; font-weight:600; }
        .nav-links {
            display:flex;
            gap:20px;
            align-items:center;
        }
        .nav-link {
            color:#d1d9e8;
            text-decoration:none;
            padding:8px 16px;
            border-radius:30px;
            transition:0.2s;
        }
        .nav-link:hover { background:rgba(255,255,255,0.05); color:white; }
        .nav-link.active { background:#3b82f6; color:white; }
        .user-info {
            display:flex;
            align-items:center;
            gap:15px;
            background:rgba(255,255,255,0.03);
            padding:6px 16px 6px 20px;
            border-radius:40px;
        }
        .role-badge {
            background:#fbbf24;
            color:black;
            padding:4px 12px;
            border-radius:30px;
            font-size:13px;
            font-weight:600;
        }
        .role-badge.vip { background:#8b5cf6; color:white; }
        .role-badge.kurucu { background:#ef4444; color:white; }
        .container {
            max-width:1200px;
            margin:40px auto;
            padding:0 20px;
        }
        .market-header {
            text-align:center;
            margin-bottom:50px;
        }
        .market-header h1 {
            font-size:48px;
            background:linear-gradient(135deg,#fff,#94a3b8);
            -webkit-background-clip:text;
            -webkit-text-fill-color:transparent;
        }
        .pricing-grid {
            display:grid;
            grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
            gap:30px;
        }
        .pricing-card {
            background:rgba(20,25,35,0.7);
            backdrop-filter:blur(10px);
            border:1px solid rgba(255,255,255,0.05);
            border-radius:40px;
            padding:40px 30px;
            text-align:center;
            transition:0.3s;
        }
        .pricing-card:hover {
            transform:translateY(-10px);
            border-color:#3b82f6;
        }
        .plan-name { font-size:28px; font-weight:700; margin-bottom:10px; }
        .plan-price {
            font-size:42px;
            font-weight:800;
            margin:20px 0;
            color:#3b82f6;
        }
        .buy-btn {
            display:inline-block;
            width:100%;
            padding:16px;
            background:#3b82f6;
            color:white;
            text-decoration:none;
            border-radius:40px;
            font-weight:600;
            transition:0.2s;
        }
        .buy-btn:hover { background:#2563eb; }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
</head>
<body>
    <div class="navbar">
        <div class="nav-brand">
            <i class="fas fa-crown"></i>
            <span>Seyfetin Efendi</span>
        </div>
        <div class="nav-links">
            <a href="/" class="nav-link">Ana Sayfa</a>
            <a href="/market" class="nav-link active">Market</a>
            {% if session.role in ['vip','kurucu'] %}
            <a href="/sorgu" class="nav-link">Sorgu</a>
            {% endif %}
            <div class="user-info">
                <i class="far fa-user-circle"></i> {{ session.email }}
                <span class="role-badge {% if session.role=='vip' %}vip{% elif session.role=='kurucu' %}kurucu{% endif %}">{{ session.role }}</span>
                <a href="/logout" style="color:#ef4444;"><i class="fas fa-sign-out-alt"></i></a>
            </div>
        </div>
    </div>
    
    <div class="container">
        <div class="market-header">
            <h1>VIP PAKETLER</h1>
        </div>
        
        <div class="pricing-grid">
            <div class="pricing-card">
                <div class="plan-name">VIP Aylık</div>
                <div class="plan-price">500₺</div>
                <a href="https://t.me/Satisyetkili" target="_blank" class="buy-btn">SATIN AL</a>
            </div>
            <div class="pricing-card">
                <div class="plan-name">VIP 3 Ay</div>
                <div class="plan-price">800₺</div>
                <a href="https://t.me/Satisyetkili" target="_blank" class="buy-btn">SATIN AL</a>
            </div>
            <div class="pricing-card">
                <div class="plan-name">VIP Yıllık</div>
                <div class="plan-price">2500₺</div>
                <a href="https://t.me/Satisyetkili" target="_blank" class="buy-btn">SATIN AL</a>
            </div>
            <div class="pricing-card">
                <div class="plan-name">SINIRSIZ</div>
                <div class="plan-price">3000₺</div>
                <a href="https://t.me/Satisyetkili" target="_blank" class="buy-btn">SATIN AL</a>
            </div>
        </div>
    </div>
</body>
</html>
"""

# ========== SORGU SAYFASI ==========
QUERY_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Seyfetin Efendi · sorgu</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:'Inter',sans-serif; }
        body {
            background:#0a0c12;
            min-height:100vh;
            color:white;
        }
        .navbar {
            background:rgba(0,0,0,0.8);
            backdrop-filter:blur(12px);
            border-bottom:1px solid rgba(255,255,255,0.05);
            padding:16px 32px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            position:sticky;
            top:0;
        }
        .nav-brand {
            display:flex;
            align-items:center;
            gap:12px;
        }
        .nav-brand i { font-size:28px; color:#3b82f6; }
        .nav-brand span { font-size:22px; font-weight:600; }
        .nav-links {
            display:flex;
            gap:20px;
            align-items:center;
        }
        .nav-link {
            color:#d1d9e8;
            text-decoration:none;
            padding:8px 16px;
            border-radius:30px;
            transition:0.2s;
        }
        .nav-link:hover { background:rgba(255,255,255,0.05); color:white; }
        .nav-link.active { background:#3b82f6; color:white; }
        .user-info {
            display:flex;
            align-items:center;
            gap:15px;
            background:rgba(255,255,255,0.03);
            padding:6px 16px 6px 20px;
            border-radius:40px;
        }
        .role-badge {
            background:#fbbf24;
            color:black;
            padding:4px 12px;
            border-radius:30px;
            font-size:13px;
            font-weight:600;
        }
        .role-badge.vip { background:#8b5cf6; color:white; }
        .role-badge.kurucu { background:#ef4444; color:white; }
        .container {
            max-width:1400px;
            margin:30px auto;
            padding:0 20px;
        }
        .query-box {
            background:#11161f;
            border-radius:30px;
            padding:30px;
            border:1px solid rgba(255,255,255,0.03);
            margin-bottom:30px;
        }
        .query-title { margin-bottom:20px; }
        .query-title h2 { color:#3b82f6; }
        .param-group { margin-bottom:20px; }
        .param-group label {
            display:block;
            color:#94a3b8;
            margin-bottom:8px;
        }
        .param-group input {
            width:100%;
            padding:14px 18px;
            background:#1e293b;
            border:1px solid rgba(255,255,255,0.05);
            border-radius:20px;
            color:white;
            font-size:16px;
            outline:none;
        }
        .param-group input:focus { border-color:#3b82f6; }
        .search-btn {
            background:#3b82f6;
            color:white;
            border:none;
            padding:16px 30px;
            border-radius:40px;
            font-size:18px;
            font-weight:600;
            cursor:pointer;
            transition:0.2s;
            width:100%;
        }
        .search-btn:hover { background:#2563eb; }
        .timeout-warning {
            background:rgba(245,158,11,0.1);
            border:1px solid #f59e0b;
            border-radius:30px;
            padding:15px 25px;
            margin:20px 0;
            display:flex;
            align-items:center;
            gap:15px;
            color:#fbbf24;
        }
        .result-box {
            background:#11161f;
            border-radius:30px;
            padding:30px;
            border:1px solid rgba(255,255,255,0.03);
            overflow-x:auto;
        }
        .result-table {
            width:100%;
            border-collapse:collapse;
            font-size:13px;
        }
        .result-table th {
            background:#1e293b;
            color:white;
            padding:10px;
            text-align:left;
            position:sticky;
            top:0;
        }
        .result-table td {
            padding:8px 10px;
            border-bottom:1px solid rgba(255,255,255,0.05);
            color:#cbd5e1;
            white-space: nowrap;
        }
        .result-table tr:hover { background:rgba(59,130,246,0.1); }
        .loading {
            text-align:center;
            padding:50px;
            color:#3b82f6;
        }
        .error-box {
            background:rgba(239,68,68,0.1);
            border:1px solid #ef4444;
            border-radius:30px;
            padding:30px;
            text-align:center;
            color:#fca5a5;
        }
        .record-count {
            background:#1e293b;
            padding:8px 16px;
            border-radius:30px;
            margin-bottom:20px;
            display:inline-block;
            font-size:14px;
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
</head>
<body>
    <div class="navbar">
        <div class="nav-brand">
            <i class="fas fa-crown"></i>
            <span>Seyfetin Efendi</span>
        </div>
        <div class="nav-links">
            <a href="/" class="nav-link">Ana Sayfa</a>
            <a href="/market" class="nav-link">Market</a>
            <a href="/sorgu" class="nav-link active">Sorgu</a>
            <div class="user-info">
                <i class="far fa-user-circle"></i> {{ session.email }}
                <span class="role-badge {% if session.role=='vip' %}vip{% elif session.role=='kurucu' %}kurucu{% endif %}">{{ session.role }}</span>
                <a href="/logout" style="color:#ef4444;"><i class="fas fa-sign-out-alt"></i></a>
            </div>
        </div>
    </div>
    
    <div class="container">
        <div class="query-box">
            <div class="query-title">
                <h2>🔍 {{ endpoint }} sorgusu</h2>
            </div>
            
            {% if type == 'tc' %}
            <div class="param-group">
                <label>TC Kimlik No</label>
                <input type="text" id="tc" placeholder="11 haneli TC" maxlength="11">
            </div>
            {% elif type == 'gsm' %}
            <div class="param-group">
                <label>GSM Numarası</label>
                <input type="text" id="gsm" placeholder="5xxxxxxxxx">
            </div>
            {% elif type == 'plaka' %}
            <div class="param-group">
                <label>Plaka</label>
                <input type="text" id="plaka" placeholder="34ABC34" style="text-transform:uppercase">
            </div>
            {% else %}
            <div class="param-group">
                <label>Ad</label>
                <input type="text" id="name" placeholder="Ad">
            </div>
            <div class="param-group">
                <label>Soyad</label>
                <input type="text" id="surname" placeholder="Soyad">
            </div>
            {% endif %}
            
            <button class="search-btn" onclick="search()">SORGU YAP</button>
            
            <div id="timeout-warning" class="timeout-warning" style="display:none;">
                <i class="fas fa-hourglass-half"></i>
                <div><strong>Sorgu devam ediyor... <span id="timer">0</span> saniye</strong></div>
            </div>
        </div>
        
        <div id="result-box" class="result-box" style="display:none;">
            <div id="loading" class="loading" style="display:none;">
                <i class="fas fa-circle-notch fa-spin fa-3x"></i>
                <h3>Sorgu yapılıyor...</h3>
            </div>
            <div id="result-content"></div>
        </div>
    </div>
    
    <script>
        let timeoutTimer = null;
        const endpoint = "{{ endpoint }}";
        const type = "{{ type }}";
        
        function startTimeout() {
            document.getElementById('timeout-warning').style.display = 'flex';
            let seconds = 0;
            if (timeoutTimer) clearInterval(timeoutTimer);
            timeoutTimer = setInterval(() => {
                seconds++;
                document.getElementById('timer').textContent = seconds;
            }, 1000);
        }
        
        function stopTimeout() {
            if (timeoutTimer) clearInterval(timeoutTimer);
            document.getElementById('timeout-warning').style.display = 'none';
        }
        
        async function search() {
            let params = {};
            if (type === 'tc') {
                const tc = document.getElementById('tc').value;
                if (!tc || tc.length !== 11) { alert('11 haneli TC giriniz'); return; }
                params.tc = tc;
            } else if (type === 'gsm') {
                const gsm = document.getElementById('gsm').value;
                if (!gsm) { alert('GSM giriniz'); return; }
                params.gsm = gsm;
            } else if (type === 'plaka') {
                const plaka = document.getElementById('plaka').value;
                if (!plaka) { alert('Plaka giriniz'); return; }
                params.plaka = plaka;
            } else {
                const name = document.getElementById('name').value;
                const surname = document.getElementById('surname').value;
                if (!name || !surname) { alert('Ad ve soyad giriniz'); return; }
                params.name = name;
                params.surname = surname;
            }
            
            const queryString = new URLSearchParams(params).toString();
            const url = `/api/${endpoint}?${queryString}`;
            
            document.getElementById('result-box').style.display = 'block';
            document.getElementById('loading').style.display = 'block';
            document.getElementById('result-content').innerHTML = '';
            startTimeout();
            
            try {
                const response = await fetch(url);
                const data = await response.json();
                
                stopTimeout();
                document.getElementById('loading').style.display = 'none';
                
                let html = '';
                
                if (data.success && data.records && data.records.length > 0) {
                    html += `<div class="record-count">📊 Toplam ${data.count} kayıt</div>`;
                    
                    const allKeys = new Set();
                    data.records.forEach(record => {
                        Object.keys(record).forEach(key => {
                            if (record[key] && record[key] !== '') allKeys.add(key);
                        });
                    });
                    
                    const headers = Array.from(allKeys);
                    const headerMap = {
                        'tc': 'TC',
                        'ad': 'Ad',
                        'soyad': 'Soyad',
                        'ad_soyad': 'Ad Soyad',
                        'dogum_yeri': 'Doğum Yeri',
                        'dogum_tarihi': 'Doğum Tarihi',
                        'anne_adi': 'Anne',
                        'anne_tc': 'Anne TC',
                        'baba_adi': 'Baba',
                        'baba_tc': 'Baba TC',
                        'il': 'İl',
                        'ilce': 'İlçe',
                        'koy': 'Köy',
                        'mhrs_il': 'MHRS İl',
                        'mhrs_ilce': 'MHRS İlçe',
                        'ikametgah': 'İkametgah',
                        'aile_sira': 'Aile Sıra',
                        'birey_sira': 'Birey Sıra',
                        'medeni_durum': 'Medeni',
                        'cinsiyet': 'Cinsiyet',
                        'gsm': 'GSM',
                        'isyeri_unvani': 'İşyeri',
                        'ise_giris': 'İşe Giriş',
                        'sektor': 'Sektör'
                    };
                    
                    html += '<div style="overflow-x: auto;"><table class="result-table"><tr>';
                    headers.forEach(key => {
                        html += `<th>${headerMap[key] || key}</th>`;
                    });
                    html += '</tr>';
                    
                    data.records.forEach(record => {
                        html += '<tr>';
                        headers.forEach(key => {
                            html += `<td>${record[key] || '-'}</td>`;
                        });
                        html += '</tr>';
                    });
                    html += '</table></div>';
                    
                } else if (data.success && data.data) {
                    html += '<div class="record-count">📊 1 kayıt</div>';
                    const record = data.data;
                    
                    const headerMap = {
                        'tc': 'TC',
                        'ad': 'Ad',
                        'soyad': 'Soyad',
                        'ad_soyad': 'Ad Soyad',
                        'dogum_yeri': 'Doğum Yeri',
                        'dogum_tarihi': 'Doğum Tarihi',
                        'anne_adi': 'Anne',
                        'anne_tc': 'Anne TC',
                        'baba_adi': 'Baba',
                        'baba_tc': 'Baba TC',
                        'il': 'İl',
                        'ilce': 'İlçe',
                        'koy': 'Köy',
                        'mhrs_il': 'MHRS İl',
                        'mhrs_ilce': 'MHRS İlçe',
                        'ikametgah': 'İkametgah',
                        'aile_sira': 'Aile Sıra',
                        'birey_sira': 'Birey Sıra',
                        'medeni_durum': 'Medeni',
                        'cinsiyet': 'Cinsiyet',
                        'gsm': 'GSM',
                        'isyeri_unvani': 'İşyeri',
                        'ise_giris': 'İşe Giriş',
                        'sektor': 'Sektör'
                    };
                    
                    html += '<table class="result-table"><tr>';
                    for (let key in record) {
                        if (record[key] && record[key] !== '') {
                            html += `<th>${headerMap[key] || key}</th>`;
                        }
                    }
                    html += '</tr><tr>';
                    for (let key in record) {
                        if (record[key] && record[key] !== '') {
                            html += `<td>${record[key]}</td>`;
                        }
                    }
                    html += '</tr></table>';
                    
                } else {
                    html = `<div class="error-box"><h3>Hata</h3><p>${data.error || 'Kayıt bulunamadı'}</p></div>`;
                }
                
                document.getElementById('result-content').innerHTML = html;
                
            } catch (error) {
                stopTimeout();
                document.getElementById('loading').style.display = 'none';
                document.getElementById('result-content').innerHTML = `
                    <div class="error-box">
                        <h3>Bağlantı Hatası</h3>
                        <p>${error.message}</p>
                    </div>
                `;
            }
        }
    </script>
</body>
</html>
"""

# ========== API İSTEKLERİ ==========
def fetch_api(url):
    """API'ye istek at ve sonucu döndür"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=60)
                
                if response.status_code != 200:
                    if attempt < 2:
                        time.sleep(2)
                        continue
                
                if "Çok hızlı" in response.text:
                    if attempt < 2:
                        time.sleep(3)
                        continue
                
                return response.text
                
            except requests.exceptions.Timeout:
                if attempt == 2:
                    return None
                time.sleep(2)
        
        return None
        
    except:
        return None

def parse_records(text):
    """Tüm kayıtları ayıkla - GARANTİ VERSİYON"""
    if not text:
        return []
    
    records = []
    
    # 'KAYIT' kelimesini bölücü olarak kullan
    chunks = re.split(r'KAYIT\s*\d+', text, flags=re.IGNORECASE)
    
    for chunk in chunks:
        if 'TC' not in chunk:
            continue
            
        record = {}
        
        # TC
        tc_m = re.search(r'TC\s*:?\s*(\d{11})', chunk)
        if tc_m:
            record['tc'] = tc_m.group(1)
        else:
            continue
        
        # Ad Soyad
        ad_m = re.search(r'(?:ADI SOYADI|AD SOYAD|Ad Soyad)\s*:?\s*([^🎂👩👨📍🏥🏠🧬💍📞🏢📅🏷\n\r]+)', chunk, re.IGNORECASE)
        if ad_m:
            record['ad_soyad'] = ad_m.group(1).strip()
        
        # Doğum Tarihi
        dt_m = re.search(r'(\d{4}-\d{2}-\d{2})', chunk)
        if dt_m:
            record['dogum_tarihi'] = dt_m.group(1)
        
        # Anne
        anne_m = re.search(r'ANNE.*?:\s*([^/]+)\s*/\s*(\d{11})', chunk, re.IGNORECASE)
        if anne_m:
            record['anne'] = anne_m.group(1).strip()
        
        # Baba
        baba_m = re.search(r'BABA.*?:\s*([^/]+)\s*/\s*(\d{11})', chunk, re.IGNORECASE)
        if baba_m:
            record['baba'] = baba_m.group(1).strip()
        
        # İl/İlçe
        yer_m = re.search(r'İL/İLÇE/KÖY\s*:?\s*([^/]+)\s*/\s*([^/]+)', chunk, re.IGNORECASE)
        if yer_m:
            record['il'] = yer_m.group(1).strip()
            record['ilce'] = yer_m.group(2).strip()
        
        # İkametgah
        ikamet_m = re.search(r'İKAMETGAH\s*:?\s*(.+?)(?=🧬|💍|📞|🏢|📅|🏷|$)', chunk, re.IGNORECASE)
        if ikamet_m:
            ikamet = ikamet_m.group(1).strip()
            if ikamet and ikamet != '-':
                record['ikametgah'] = ikamet[:50]
        
        # GSM
        gsm_m = re.search(r'BIRINCIL GSM\s*:?\s*(\d+)', chunk, re.IGNORECASE)
        if gsm_m:
            record['gsm'] = gsm_m.group(1)
        
        # Medeni Durum/Cinsiyet
        medeni_m = re.search(r'MEDENI/CINSIYET\s*:?\s*([^/]+)\s*/\s*([^\n]+)', chunk, re.IGNORECASE)
        if medeni_m:
            record['medeni'] = medeni_m.group(1).strip()
            record['cinsiyet'] = medeni_m.group(2).strip()
        
        # İşe Giriş
        ise_m = re.search(r'İŞE GIRIŞ\s*:?\s*([^\n]+)', chunk, re.IGNORECASE)
        if ise_m:
            ise = ise_m.group(1).strip()
            if ise and ise != '-':
                record['ise_giris'] = ise
        
        records.append(record)
    
    return records

# ========== API ENDPOINT'LERİ ==========
@app.route('/api/<endpoint>')
def api_endpoint(endpoint):
    if 'email' not in session:
        return jsonify({'success': False, 'error': 'Giriş yapın'}), 401
    if session.get('role') not in ['vip', 'kurucu']:
        return jsonify({'success': False, 'error': 'Yetkiniz yok'}), 403
    
    # Parametreleri al
    if endpoint in ['tc-isegiris', 'tc-ikametgah', 'tc-ailebirey', 'tc-medenicinsiyet', 'tc', 'aile', 'sulale', 'hane', 'isyeri', 'tc2']:
        tc = request.args.get('tc', '')
        if not tc or len(tc) != 11:
            return jsonify({'success': False, 'error': 'Geçerli TC girin'})
        url = f"https://apilerimya.onrender.com/{endpoint}?tc={tc}&format=text"
        
    elif endpoint in ['gsm', 'gsm2']:
        gsm = request.args.get('gsm', '')
        if not gsm:
            return jsonify({'success': False, 'error': 'GSM girin'})
        url = f"https://apilerimya.onrender.com/{endpoint}?gsm={gsm}&format=text"
        
    elif endpoint == 'plaka':
        plaka = request.args.get('plaka', '')
        if not plaka:
            return jsonify({'success': False, 'error': 'Plaka girin'})
        url = f"https://apilerimya.onrender.com/{endpoint}?plaka={plaka}&format=text"
        
    else:
        name = request.args.get('name', '')
        surname = request.args.get('surname', '')
        if not name or not surname:
            return jsonify({'success': False, 'error': 'Ad ve soyad girin'})
        url = f"https://apilerimya.onrender.com/{endpoint}?name={name}&surname={surname}&format=text"
    
    # API'ye istek at
    text = fetch_api(url)
    if not text:
        return jsonify({'success': False, 'error': 'API yanıt vermedi'})
    
    # Parse et
    records = parse_records(text)
    
    if records:
        if len(records) == 1:
            return jsonify({'success': True, 'data': records[0], 'count': 1})
        else:
            return jsonify({'success': True, 'records': records, 'count': len(records)})
    else:
        return jsonify({'success': False, 'error': 'Kayıt bulunamadı'})

# ========== SAYFA ROUTE'LARI ==========
@app.route('/')
def home():
    if 'email' in session:
        return render_template_string(INDEX_PAGE, session=session)
    return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if email in USERS and USERS[email]['password'] == password:
            session['email'] = email
            session['role'] = USERS[email]['role']
            return redirect(url_for('home'))
        
        if email in FREE_USERS and FREE_USERS[email] == password:
            session['email'] = email
            session['role'] = 'free'
            return redirect(url_for('home'))
        
        return render_template_string(LOGIN_PAGE, error="Hatalı giriş")
    
    return render_template_string(LOGIN_PAGE)

@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()
        
        if not email or not password:
            return render_template_string(REGISTER_PAGE, error="E-posta ve şifre gerekli")
        
        if password != confirm:
            return render_template_string(REGISTER_PAGE, error="Şifreler eşleşmiyor")
        
        if email in USERS or email in FREE_USERS:
            return render_template_string(REGISTER_PAGE, error="Bu e-posta zaten kayıtlı")
        
        FREE_USERS[email] = password
        return render_template_string(REGISTER_PAGE, success="Kayıt başarılı! Giriş yapabilirsiniz.")
    
    return render_template_string(REGISTER_PAGE)

@app.route('/market')
def market_page():
    if 'email' not in session:
        return redirect(url_for('login_page'))
    return render_template_string(MARKET_PAGE, session=session)

@app.route('/sorgu')
def query_page():
    if 'email' not in session:
        return redirect(url_for('login_page'))
    if session.get('role') not in ['vip', 'kurucu']:
        return redirect(url_for('market_page'))
    
    endpoint = request.args.get('endpoint', 'isegiris')
    query_type = request.args.get('type', 'ad')
    return render_template_string(QUERY_PAGE, session=session, endpoint=endpoint, type=query_type)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ========== MAIN ==========
if __name__ == '__main__':
    print("="*60)
    print("🚀 Seyfetin Efendi Panel başlatılıyor...")
    print("="*60)
    print("\n📋 KURUCU: babalar@gmail.com / uykumvar")
    print("📋 VIP: vipadamya@gmail.com / viplerebak")
    print("\n🌐 http://localhost:5000")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
