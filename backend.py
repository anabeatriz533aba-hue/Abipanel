# -*- coding: utf-8 -*-
import os
import time
import re
import requests
import hashlib
import secrets
import json
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config['JSON_AS_ASCII'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ========== MONGODB BAĞLANTISI ==========
MONGO_URI = "mongodb+srv://kolsuzpabg_db_user:XlJTC52PiTQMOPhN@cluster0.dfpnfxq.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
db = client["efendi_panel"]
users_collection = db["users"]
queries_collection = db["queries"]
packages_collection = db["packages"]

# Varsayılan paketleri oluştur
if packages_collection.count_documents({}) == 0:
    packages_collection.insert_many([
        {"name": "Aylık VIP", "price": 500, "days": 30, "role": "vip"},
        {"name": "3 Aylık VIP", "price": 800, "days": 90, "role": "vip"},
        {"name": "Yıllık VIP", "price": 2500, "days": 365, "role": "vip"},
        {"name": "Sınırsız VIP", "price": 3000, "days": None, "role": "vip_sınırsız"}
    ])

# Kurucu hesabı oluştur (ilk çalıştırmada)
if users_collection.count_documents({"role": "kurucu"}) == 0:
    hashed_password = hashlib.sha256("uykumvar".encode()).hexdigest()
    users_collection.insert_one({
        "email": "babalar@gmail.com",
        "password": hashed_password,
        "role": "kurucu",
        "active": True,
        "created_at": datetime.now(),
        "created_by": "system",
        "package": None,
        "expires": None,
        "note": "Kurucu hesap"
    })

# ========== DEKORATÖRLER ==========
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def kurucu_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session or session.get('role') != 'kurucu':
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def vip_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'email' not in session:
            return redirect(url_for('login_page'))
        
        user = users_collection.find_one({"email": session['email']})
        if not user or not user.get('active', False):
            session.clear()
            return redirect(url_for('login_page'))
        
        # Süre kontrolü
        if user.get('expires') and user['expires'] < datetime.now():
            users_collection.update_one(
                {"email": session['email']},
                {"$set": {"active": False}}
            )
            session.clear()
            return redirect(url_for('login_page'))
        
        if user.get('role') not in ['vip', 'vip_sınırsız', 'kurucu']:
            return redirect(url_for('home'))
        
        return f(*args, **kwargs)
    return decorated_function

# ========== YARDIMCI FONKSİYONLAR ==========
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_password(password, hashed):
    return hash_password(password) == hashed

def get_current_user():
    if 'email' in session:
        return users_collection.find_one({"email": session['email']})
    return None

def fix_turkish_chars(text):
    """Türkçe karakterleri düzelt"""
    if not text:
        return text
    if isinstance(text, str):
        replacements = {
            'Ä°': 'İ', 'Ä±': 'ı', 'Ã¼': 'ü', 'Ã§': 'ç', 'Ã¶': 'ö', 
            'ÃŸ': 'ş', 'ÄŸ': 'ğ', 'Ãœ': 'Ü', 'Ä': 'İ', 'Å': 'Ş',
            'Ã‡': 'Ç', 'Ã–': 'Ö', 'Äž': 'Ğ'
        }
        for wrong, correct in replacements.items():
            text = text.replace(wrong, correct)
    return text

def fix_dict_turkish_chars(obj):
    """Dict içindeki tüm Türkçe karakterleri düzelt"""
    if isinstance(obj, dict):
        return {k: fix_dict_turkish_chars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fix_dict_turkish_chars(item) for item in obj]
    elif isinstance(obj, str):
        return fix_turkish_chars(obj)
    else:
        return obj

# ========== ANA SAYFA ==========
INDEX_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
    <title>Efendi Panel</title>
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
        body.menu-open::before {
            background: rgba(0, 0, 0, 0.7);
            backdrop-filter: blur(5px);
        }
        
        /* Menü Butonu Konumu (Sol Üst) */
        .menu-toggle {
            position: fixed;
            top: 20px;
            left: 20px;
            width: 50px;
            height: 50px;
            background: #0a0c12;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            color: white;
            cursor: pointer;
            z-index: 1001;
            box-shadow: 0 10px 25px rgba(0,0,0,0.6);
            transition: 0.2s;
        }
        .menu-toggle:hover {
            background: #141a24;
            border-color: #2a6df4;
            transform: scale(1.05);
        }
        
        /* Yan Menü (Soldan Açılır) - Mobil Uyumlu */
        .side-menu {
            position: fixed;
            top: 0;
            left: -85%;
            width: 85%;
            max-width: 380px;
            height: 100vh;
            background: #0a0c12;
            border-right: 1px solid rgba(255,255,255,0.05);
            box-shadow: 15px 0 50px rgba(0,0,0,0.9);
            z-index: 1002;
            transition: left 0.3s ease;
            display: flex;
            flex-direction: column;
            color: white;
            overflow-y: auto;
        }
        
        @media (min-width: 768px) {
            .side-menu {
                left: -400px;
                width: 380px;
            }
        }
        
        .side-menu.open { left: 0; }
        
        .profile-section {
            padding: 25px 20px;
            background: #05070a;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .profile-avatar {
            width: 60px;
            height: 60px;
            border-radius: 20px;
            overflow: hidden;
            border: 2px solid rgba(255,255,255,0.2);
        }
        .profile-avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .profile-name {
            font-size: 18px;
            font-weight: 600;
            color: white;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .blue-tick { color: #3b82f6; font-size: 18px; }
        .online-status {
            display: flex;
            align-items: center;
            gap: 6px;
            background: rgba(0,0,0,0.6);
            border-left: 3px solid #2ecc71;
            padding: 4px 10px;
            border-radius: 30px;
            font-size: 12px;
            color: #d0f0d0;
            width: fit-content;
            margin-top: 5px;
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
            padding: 15px;
            overflow-y: auto;
        }
        
        /* Yeni Çözümler kategorisi için özel renk */
        .category-block.new-solutions .category-header {
            background: linear-gradient(135deg, #f97316, #ef4444);
            color: white;
        }
        .category-block.new-solutions .category-header i {
            color: white;
        }
        
        .category-block {
            margin-bottom: 12px;
            border-radius: 16px;
            background: rgba(20,25,35,0.4);
        }
        .category-header {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 15px;
            background: #11161f;
            border-radius: 14px;
            font-weight: 600;
            font-size: 14px;
            color: #f0f5ff;
            cursor: pointer;
        }
        .category-header i { color: #5f9eff; width: 22px; font-size: 16px; }
        .category-header .arrow {
            margin-left: auto;
            transition: transform 0.3s;
            color: #8aabff;
            font-size: 14px;
        }
        .query-list {
            list-style: none;
            margin: 5px 0 5px 10px;
            padding-left: 15px;
            border-left: 2px solid rgba(70,130,255,0.25);
            display: none;
        }
        .query-list.open { display: block; }
        .query-item {
            padding: 10px 12px;
            margin: 5px 0;
            background: #0f141e;
            border-radius: 12px;
            color: #e0eaff;
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            transition: 0.15s;
            font-size: 13px;
        }
        .query-item i { color: #72b0ff; width: 20px; font-size: 14px; }
        .query-item:hover {
            background: #1b2435;
            transform: translateX(4px);
        }
        
        .logout-section {
            padding: 20px;
            border-top: 1px solid rgba(255,255,255,0.05);
            margin-top: auto;
        }
        .logout-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            width: 100%;
            padding: 14px;
            background: #ef4444;
            color: white;
            border: none;
            border-radius: 30px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.2s;
            text-decoration: none;
        }
        .logout-btn:hover {
            background: #dc2626;
            transform: scale(1.02);
        }
        .logout-btn i { font-size: 18px; }
        
        .content {
            position: relative;
            z-index: 1;
            padding: 20px;
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }
        .welcome-box {
            background: rgba(0,0,0,0.5);
            backdrop-filter: blur(10px);
            border-radius: 30px;
            padding: 30px 25px;
            max-width: 500px;
            width: 100%;
            border: 1px solid rgba(255,255,255,0.1);
            margin-top: 40px;
        }
        .welcome-box h1 {
            font-size: 36px;
            margin-bottom: 15px;
            background: linear-gradient(135deg, #fff, #94a3b8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        @media (max-width: 480px) {
            .welcome-box h1 { font-size: 28px; }
        }
        .stats {
            display: flex;
            gap: 15px;
            margin-top: 25px;
            flex-wrap: wrap;
        }
        .stat-item {
            background: rgba(59,130,246,0.2);
            border: 1px solid #3b82f6;
            border-radius: 20px;
            padding: 12px 20px;
            text-align: center;
            flex: 1;
            min-width: 100px;
        }
        .stat-value { font-size: 22px; font-weight: 700; color: #3b82f6; }
        .stat-label { font-size: 12px; }
        
        .admin-link {
            background: #ef4444;
            color: white;
            padding: 6px 14px;
            border-radius: 30px;
            text-decoration: none;
            font-size: 13px;
            margin-left: 10px;
            display: inline-block;
        }
        .admin-link:hover {
            background: #dc2626;
        }
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
            <!-- YENİ ÇÖZÜMLER - En üstte ve renkli -->
            <div class="category-block new-solutions">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-fire"></i> 🔥 YENİ ÇÖZÜMLER
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('papara_no', 'papara_no')"><i class="fas fa-money-bill"></i> Papara Sorgula (Papara No ile)</li>
                    <li class="query-item" onclick="goToQuery('papara_ad', 'papara_ad')"><i class="fas fa-user"></i> Papara Sorgula (Ad Soyad ile)</li>
                    <li class="query-item" onclick="goToQuery('vergi_isim', 'vergi_isim')"><i class="fas fa-building"></i> Vergi Sorgula (İsim ile)</li>
                    <li class="query-item" onclick="goToQuery('vergi_no', 'vergi_no')"><i class="fas fa-file-invoice"></i> Vergi Sorgula (Vergi No ile)</li>
                    <li class="query-item" onclick="goToQuery('vergi_detay', 'vergi_detay')"><i class="fas fa-search-location"></i> Vergi Sorgula (İlçe / Vergi Dairesi)</li>
                    <li class="query-item" onclick="goToQuery('serino_tc', 'serino_tc')"><i class="fas fa-id-card"></i> Seri No Sorgula (TC ile)</li>
                    <li class="query-item" onclick="goToQuery('serino_ad', 'serino_ad')"><i class="fas fa-user-tag"></i> Seri No Sorgula (Ad ile)</li>
                    <li class="query-item" onclick="goToQuery('serino_adsoyad', 'serino_adsoyad')"><i class="fas fa-user-check"></i> Seri No Sorgula (Ad Soyad ile)</li>
                    <li class="query-item" onclick="goToQuery('serino_seri', 'serino_seri')"><i class="fas fa-barcode"></i> Seri No Sorgula (Seri No ile)</li>
                </ul>
            </div>

            <!-- Papara İşlemleri Kategorisi -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-money-bill-wave"></i> 📱 Papara İşlemleri
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('papara_no', 'papara_no')"><i class="fas fa-search"></i> Papara No ile Sorgula</li>
                    <li class="query-item" onclick="goToQuery('papara_ad', 'papara_ad')"><i class="fas fa-user"></i> Papara Ad Soyad ile Sorgula</li>
                </ul>
            </div>

            <!-- Vergi Dairesi Sorguları Kategorisi -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-landmark"></i> 🏛️ Vergi Dairesi Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('vergi_isim', 'vergi_isim')"><i class="fas fa-user-tie"></i> Vergi İsim ile Sorgula</li>
                    <li class="query-item" onclick="goToQuery('vergi_no', 'vergi_no')"><i class="fas fa-file-invoice"></i> Vergi Numarası ile Sorgula</li>
                    <li class="query-item" onclick="goToQuery('vergi_detay', 'vergi_detay')"><i class="fas fa-map-marker-alt"></i> Vergi İlçe / Daire ile Sorgula</li>
                </ul>
            </div>

            <!-- Kimlik Seri No Sorguları Kategorisi -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-id-card"></i> 🆔 Kimlik Seri No Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('serino_tc', 'serino_tc')"><i class="fas fa-id-card"></i> Seri No (TC ile)</li>
                    <li class="query-item" onclick="goToQuery('serino_ad', 'serino_ad')"><i class="fas fa-user"></i> Seri No (Ad ile)</li>
                    <li class="query-item" onclick="goToQuery('serino_adsoyad', 'serino_adsoyad')"><i class="fas fa-user-check"></i> Seri No (Ad Soyad ile)</li>
                    <li class="query-item" onclick="goToQuery('serino_seri', 'serino_seri')"><i class="fas fa-barcode"></i> Seri No (Seri No ile)</li>
                </ul>
            </div>

            <!-- Kişi Çözümleri Kategorisi (Ad+İl vb.) -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-user-cog"></i> 👤 Kişi Çözümleri
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('adsoyadpro', 'adsoyadpro')"><i class="fas fa-map-pin"></i> Ad+Soyad+İl Sorgula (Kapsamlı)</li>
                    <li class="query-item" onclick="goToQuery('ailepro', 'ailepro')"><i class="fas fa-users"></i> TC ile Aile Sorgula (Detaylı)</li>
                    <li class="query-item" onclick="goToQuery('adres', 'adres')"><i class="fas fa-home"></i> TC ile Adres Sorgula</li>
                    <li class="query-item" onclick="goToQuery('iban', 'iban')"><i class="fas fa-university"></i> IBAN Sorgula</li>
                    <li class="query-item" onclick="goToQuery('operator', 'operator')"><i class="fas fa-signal"></i> Güncel Operatör Sorgula</li>
                </ul>
            </div>

            <!-- MEVCUT KATEGORİLER (Aynen kalıyor) -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-id-card"></i> Kimlik Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('isegiris', 'ad')"><i class="fas fa-briefcase"></i> İşe Giriş Sorgula</li>
                    <li class="query-item" onclick="goToQuery('ikametgah', 'ad')"><i class="fas fa-home"></i> İkametgah Sorgula</li>
                    <li class="query-item" onclick="goToQuery('ailebirey', 'ad')"><i class="fas fa-users"></i> Aile Bireyi Sorgula</li>
                    <li class="query-item" onclick="goToQuery('medenicinsiyet', 'ad')"><i class="fas fa-venus-mars"></i> Medeni Hal / Cinsiyet Sorgula</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-id-card"></i> TC Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('tc-isegiris', 'tc')"><i class="fas fa-briefcase"></i> TC ile İşe Giriş Sorgula</li>
                    <li class="query-item" onclick="goToQuery('tc-ikametgah', 'tc')"><i class="fas fa-home"></i> TC ile İkametgah Sorgula</li>
                    <li class="query-item" onclick="goToQuery('tc-ailebirey', 'tc')"><i class="fas fa-users"></i> TC ile Aile Bireyi Sorgula</li>
                    <li class="query-item" onclick="goToQuery('tc-medenicinsiyet', 'tc')"><i class="fas fa-venus-mars"></i> TC ile Medeni Hal / Cinsiyet Sorgula</li>
                    <li class="query-item" onclick="goToQuery('tc', 'tc')"><i class="fas fa-search"></i> TC ile Detaylı Sorgula</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-phone-alt"></i> GSM Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('gsm', 'gsm')"><i class="fas fa-phone"></i> Telefon Numarası Sorgula</li>
                    <li class="query-item" onclick="goToQuery('gsm2', 'gsm')"><i class="fas fa-phone"></i> Telefon Numarası Sorgula (Alternatif)</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-car"></i> Plaka Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('plaka', 'plaka')"><i class="fas fa-car"></i> Plaka Sorgula</li>
                    <li class="query-item" onclick="goToQuery('plaka_adsoyad', 'plaka_adsoyad')"><i class="fas fa-user"></i> Plaka Ad Soyad ile Sorgula</li>
                    <li class="query-item" onclick="goToQuery('plaka_ad', 'plaka_ad')"><i class="fas fa-user"></i> Plaka Ad ile Sorgula</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-users"></i> Aile Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('aile', 'tc')"><i class="fas fa-users"></i> Aile Sorgula (TC ile)</li>
                    <li class="query-item" onclick="goToQuery('sulale', 'tc')"><i class="fas fa-tree"></i> Sülale Sorgula (TC ile)</li>
                    <li class="query-item" onclick="goToQuery('hane', 'tc')"><i class="fas fa-home"></i> Hane Sorgula (TC ile)</li>
                    <li class="query-item" onclick="goToQuery('isyeri', 'tc')"><i class="fas fa-briefcase"></i> İşyeri Sorgula (TC ile)</li>
                </ul>
            </div>
            
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-user"></i> Ad Soyad Sorguları
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('query', 'ad')"><i class="fas fa-search"></i> Genel Sorgula</li>
                    <li class="query-item" onclick="goToQuery('ad', 'ad')"><i class="fas fa-search"></i> Ad Soyad ile Sorgula</li>
                </ul>
            </div>
        </div>
        
        <div class="logout-section">
            <a href="/logout" class="logout-btn">
                <i class="fas fa-sign-out-alt"></i> Çıkış Yap
            </a>
        </div>
    </div>
    
    <div class="content">
        <div class="welcome-box">
            <h1>Efendi Panel</h1>
            <p>Hoş geldiniz, <strong>{{ session.email if session.email else 'Misafir' }}</strong>!<br>Yetkiniz: <span style="color: #3b82f6;">{{ session.role if session.role else 'Misafir' }}</span>
            {% if session.role == 'kurucu' %}
            <a href="/admin" class="admin-link"><i class="fas fa-cog"></i> Admin</a>
            {% endif %}
            </p>
            
            {% if session.role in ['vip', 'vip_sınırsız', 'kurucu'] %}
            <div class="stats">
                <div class="stat-item"><div class="stat-value">30+</div><div class="stat-label">API</div></div>
                <div class="stat-item"><div class="stat-value">60s</div><div class="stat-label">Timeout</div></div>
            </div>
            <p style="margin-top:20px;">🔥 Yeni çözümler eklendi!</p>
            {% else %}
            <p style="margin-top:20px; color:#fbbf24;">🔒 Sorgu için kurucu ile iletişime geçin</p>
            {% endif %}
        </div>
    </div>
    
    <script>
        const menuToggle = document.getElementById('menuToggle');
        const sideMenu = document.getElementById('sideMenu');
        
        function toggleMenu() {
            sideMenu.classList.toggle('open');
            document.body.classList.toggle('menu-open');
        }
        
        menuToggle.onclick = (e) => {
            e.stopPropagation();
            toggleMenu();
        };
        
        document.addEventListener('click', (e) => {
            if (sideMenu.classList.contains('open') && 
                !sideMenu.contains(e.target) && 
                !menuToggle.contains(e.target)) {
                sideMenu.classList.remove('open');
                document.body.classList.remove('menu-open');
            }
        });
        
        sideMenu.addEventListener('click', (e) => {
            e.stopPropagation();
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
    <title>Efendi Panel · giriş</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:'Inter',sans-serif; }
        body {
            min-height:100vh;
            background:url('https://i.ibb.co/Ldc4b2YF/file-00000000f190720cb7f53c717d6f458d.png') no-repeat center center fixed;
            background-size:cover;
            display:flex;
            align-items:center;
            justify-content:center;
            padding:20px;
        }
        body::before {
            content:'';
            position:fixed;
            top:0; left:0; width:100%; height:100%;
            background:rgba(0,0,0,0.5);
            backdrop-filter:blur(12px);
            z-index:0;
        }
        .login-box {
            position:relative;
            z-index:1;
            width:100%;
            max-width:420px;
            background:rgba(10,15,25,0.8);
            border-radius:32px;
            padding:40px 25px;
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
            <h1>Efendi Panel</h1>
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
    <title>Efendi Panel · kayıt</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; font-family:'Inter',sans-serif; }
        body {
            min-height:100vh;
            background:url('https://i.ibb.co/Ldc4b2YF/file-00000000f190720cb7f53c717d6f458d.png') no-repeat center center fixed;
            background-size:cover;
            display:flex;
            align-items:center;
            justify-content:center;
            padding:20px;
        }
        body::before {
            content:'';
            position:fixed;
            top:0; left:0; width:100%; height:100%;
            background:rgba(0,0,0,0.5);
            backdrop-filter:blur(12px);
            z-index:0;
        }
        .register-box {
            position:relative;
            z-index:1;
            width:100%;
            max-width:420px;
            background:rgba(10,15,25,0.8);
            border-radius:32px;
            padding:40px 25px;
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
            font-size:24px;
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

# ========== SORGU SAYFASI ==========
QUERY_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
    <title>Efendi Panel · sorgu</title>
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
            padding:12px 20px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            position:sticky;
            top:0;
            z-index:100;
        }
        .nav-brand {
            display:flex;
            align-items:center;
            gap:10px;
        }
        .nav-brand i { font-size:24px; color:#3b82f6; }
        .nav-brand span { font-size:18px; font-weight:600; }
        .nav-links {
            display:flex;
            gap:10px;
            align-items:center;
        }
        .nav-link {
            color:#d1d9e8;
            text-decoration:none;
            padding:6px 12px;
            border-radius:30px;
            transition:0.2s;
            font-size:14px;
        }
        .nav-link:hover { background:rgba(255,255,255,0.05); color:white; }
        .nav-link.active { background:#3b82f6; color:white; }
        .user-info {
            display:flex;
            align-items:center;
            gap:10px;
            background:rgba(255,255,255,0.03);
            padding:5px 10px 5px 15px;
            border-radius:40px;
            font-size:13px;
        }
        .role-badge {
            background:#fbbf24;
            color:black;
            padding:3px 8px;
            border-radius:30px;
            font-size:11px;
            font-weight:600;
        }
        .role-badge.vip { background:#8b5cf6; color:white; }
        .role-badge.kurucu { background:#ef4444; color:white; }
        .container {
            max-width:1400px;
            margin:20px auto;
            padding:0 15px;
        }
        .query-box {
            background:#11161f;
            border-radius:24px;
            padding:20px;
            border:1px solid rgba(255,255,255,0.03);
            margin-bottom:20px;
        }
        .query-title { margin-bottom:15px; }
        .query-title h2 { color:#3b82f6; font-size:20px; }
        .param-group { margin-bottom:15px; }
        .param-group label {
            display:block;
            color:#94a3b8;
            margin-bottom:5px;
            font-size:14px;
        }
        .param-group input {
            width:100%;
            padding:12px 15px;
            background:#1e293b;
            border:1px solid rgba(255,255,255,0.05);
            border-radius:16px;
            color:white;
            font-size:15px;
            outline:none;
        }
        .param-group input:focus { border-color:#3b82f6; }
        .search-btn {
            background:#3b82f6;
            color:white;
            border:none;
            padding:14px 20px;
            border-radius:30px;
            font-size:16px;
            font-weight:600;
            cursor:pointer;
            transition:0.2s;
            width:100%;
        }
        .search-btn:hover { background:#2563eb; }
        .timeout-warning {
            background:rgba(245,158,11,0.1);
            border:1px solid #f59e0b;
            border-radius:20px;
            padding:12px 15px;
            margin:15px 0;
            display:flex;
            align-items:center;
            gap:10px;
            color:#fbbf24;
            font-size:14px;
        }
        .result-box {
            background:#11161f;
            border-radius:24px;
            padding:15px;
            border:1px solid rgba(255,255,255,0.03);
            overflow-x:auto;
        }
        .result-table {
            width:100%;
            border-collapse:collapse;
            font-size:12px;
        }
        .result-table th {
            background:#1e293b;
            color:white;
            padding:8px;
            text-align:left;
            position:sticky;
            top:0;
            font-size:12px;
        }
        .result-table td {
            padding:6px 8px;
            border-bottom:1px solid rgba(255,255,255,0.05);
            color:#cbd5e1;
            white-space: nowrap;
            font-size:12px;
        }
        .result-table tr:hover { background:rgba(59,130,246,0.1); }
        .loading {
            text-align:center;
            padding:30px;
            color:#3b82f6;
        }
        .error-box {
            background:rgba(239,68,68,0.1);
            border:1px solid #ef4444;
            border-radius:20px;
            padding:20px;
            text-align:center;
            color:#fca5a5;
        }
        .record-count {
            background:#1e293b;
            padding:6px 12px;
            border-radius:20px;
            margin-bottom:15px;
            display:inline-block;
            font-size:13px;
        }
        
        @media (max-width: 480px) {
            .navbar { padding:10px; }
            .nav-brand span { display:none; }
            .user-info span:not(.role-badge) { display:none; }
            .query-title h2 { font-size:18px; }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
</head>
<body>
    <div class="navbar">
        <div class="nav-brand">
            <i class="fas fa-crown"></i>
            <span>Efendi Panel</span>
        </div>
        <div class="nav-links">
            <a href="/" class="nav-link"><i class="fas fa-home"></i></a>
            {% if session.role == 'kurucu' %}
            <a href="/admin" class="nav-link"><i class="fas fa-cog"></i></a>
            {% endif %}
            <div class="user-info">
                <i class="far fa-user-circle"></i> <span>{{ session.email.split('@')[0] }}</span>
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
            {% elif type == 'plaka_adsoyad' %}
            <div class="param-group">
                <label>Ad</label>
                <input type="text" id="ad" placeholder="Ad">
            </div>
            <div class="param-group">
                <label>Soyad</label>
                <input type="text" id="soyad" placeholder="Soyad">
            </div>
            {% elif type == 'plaka_ad' %}
            <div class="param-group">
                <label>Ad</label>
                <input type="text" id="ad" placeholder="Ad">
            </div>
            {% elif type == 'papara_no' %}
            <div class="param-group">
                <label>Papara Numarası</label>
                <input type="text" id="papara_no" placeholder="Papara No">
            </div>
            {% elif type == 'papara_ad' %}
            <div class="param-group">
                <label>Ad</label>
                <input type="text" id="ad" placeholder="Ad">
            </div>
            <div class="param-group">
                <label>Soyad</label>
                <input type="text" id="soyad" placeholder="Soyad">
            </div>
            {% elif type == 'vergi_isim' %}
            <div class="param-group">
                <label>İsim</label>
                <input type="text" id="isim" placeholder="İsim">
            </div>
            {% elif type == 'vergi_no' %}
            <div class="param-group">
                <label>Vergi Numarası</label>
                <input type="text" id="vergi_no" placeholder="Vergi No">
            </div>
            {% elif type == 'vergi_detay' %}
            <div class="param-group">
                <label>İlçe</label>
                <input type="text" id="ilce" placeholder="İlçe">
            </div>
            <div class="param-group">
                <label>Vergi Dairesi</label>
                <input type="text" id="vergi_dairesi" placeholder="Vergi Dairesi">
            </div>
            {% elif type == 'serino_tc' %}
            <div class="param-group">
                <label>TC Kimlik No</label>
                <input type="text" id="tc" placeholder="11 haneli TC" maxlength="11">
            </div>
            {% elif type == 'serino_ad' %}
            <div class="param-group">
                <label>Ad</label>
                <input type="text" id="ad" placeholder="Ad">
            </div>
            {% elif type == 'serino_adsoyad' %}
            <div class="param-group">
                <label>Ad</label>
                <input type="text" id="ad" placeholder="Ad">
            </div>
            <div class="param-group">
                <label>Soyad</label>
                <input type="text" id="soyad" placeholder="Soyad">
            </div>
            {% elif type == 'serino_seri' %}
            <div class="param-group">
                <label>Seri No</label>
                <input type="text" id="seri_no" placeholder="Örn: A30T00779">
            </div>
            {% elif type == 'adsoyadpro' %}
            <div class="param-group">
                <label>Ad</label>
                <input type="text" id="ad" placeholder="Ad">
            </div>
            <div class="param-group">
                <label>Soyad</label>
                <input type="text" id="soyad" placeholder="Soyad">
            </div>
            <div class="param-group">
                <label>İl (opsiyonel)</label>
                <input type="text" id="il" placeholder="İl">
            </div>
            {% elif type == 'ailepro' %}
            <div class="param-group">
                <label>TC Kimlik No</label>
                <input type="text" id="tc" placeholder="11 haneli TC" maxlength="11">
            </div>
            {% elif type == 'adres' %}
            <div class="param-group">
                <label>TC Kimlik No</label>
                <input type="text" id="tc" placeholder="11 haneli TC" maxlength="11">
            </div>
            {% elif type == 'iban' %}
            <div class="param-group">
                <label>IBAN</label>
                <input type="text" id="iban" placeholder="TR ile başlayan IBAN">
            </div>
            {% elif type == 'operator' %}
            <div class="param-group">
                <label>Telefon Numarası</label>
                <input type="text" id="telefon" placeholder="5xxxxxxxxx">
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
            
            // Parametreleri topla
            if (type === 'tc' || type === 'ailepro' || type === 'adres' || endpoint === 'ailepro' || endpoint === 'adres' || endpoint === 'serino_tc') {
                const tc = document.getElementById('tc')?.value || document.getElementById('tc')?.value;
                if (!tc || tc.length !== 11) { alert('11 haneli TC giriniz'); return; }
                params.tc = tc;
            } 
            else if (type === 'gsm' || endpoint === 'operator') {
                const gsm = document.getElementById('gsm')?.value || document.getElementById('telefon')?.value;
                if (!gsm) { alert('GSM giriniz'); return; }
                params.gsm = gsm;
                if (endpoint === 'operator') params.telefon = gsm;
            } 
            else if (type === 'plaka') {
                const plaka = document.getElementById('plaka').value;
                if (!plaka) { alert('Plaka giriniz'); return; }
                params.plaka = plaka;
            }
            else if (type === 'plaka_adsoyad') {
                const ad = document.getElementById('ad').value;
                const soyad = document.getElementById('soyad').value;
                if (!ad || !soyad) { alert('Ad ve soyad giriniz'); return; }
                params.ad = ad;
                params.soyad = soyad;
            }
            else if (type === 'plaka_ad') {
                const ad = document.getElementById('ad').value;
                if (!ad) { alert('Ad giriniz'); return; }
                params.ad = ad;
            }
            else if (type === 'papara_no') {
                const papara_no = document.getElementById('papara_no').value;
                if (!papara_no) { alert('Papara numarası giriniz'); return; }
                params.paparano = papara_no;
            }
            else if (type === 'papara_ad') {
                const ad = document.getElementById('ad').value;
                const soyad = document.getElementById('soyad').value;
                if (!ad || !soyad) { alert('Ad ve soyad giriniz'); return; }
                params.ad = ad;
                params.soyad = soyad;
            }
            else if (type === 'vergi_isim') {
                const isim = document.getElementById('isim').value;
                if (!isim) { alert('İsim giriniz'); return; }
                params.isim = isim;
            }
            else if (type === 'vergi_no') {
                const vergi_no = document.getElementById('vergi_no').value;
                if (!vergi_no) { alert('Vergi numarası giriniz'); return; }
                params.vergi_no = vergi_no;
            }
            else if (type === 'vergi_detay') {
                const ilce = document.getElementById('ilce').value;
                const vergi_dairesi = document.getElementById('vergi_dairesi').value;
                if (!ilce && !vergi_dairesi) { alert('İlçe veya vergi dairesi giriniz'); return; }
                if (ilce) params.ilce = ilce;
                if (vergi_dairesi) params.vergi_dairesi = vergi_dairesi;
            }
            else if (type === 'serino_ad') {
                const ad = document.getElementById('ad').value;
                if (!ad) { alert('Ad giriniz'); return; }
                params.ad = ad;
            }
            else if (type === 'serino_adsoyad') {
                const ad = document.getElementById('ad').value;
                const soyad = document.getElementById('soyad').value;
                if (!ad || !soyad) { alert('Ad ve soyad giriniz'); return; }
                params.ad = ad;
                params.soyad = soyad;
            }
            else if (type === 'serino_seri') {
                const seri_no = document.getElementById('seri_no').value;
                if (!seri_no) { alert('Seri no giriniz'); return; }
                params.seri_no = seri_no;
            }
            else if (type === 'adsoyadpro') {
                const ad = document.getElementById('ad').value;
                const soyad = document.getElementById('soyad').value;
                if (!ad || !soyad) { alert('Ad ve soyad giriniz'); return; }
                params.ad = ad;
                params.soyad = soyad;
                const il = document.getElementById('il')?.value;
                if (il) params.il = il;
            }
            else if (type === 'iban') {
                const iban = document.getElementById('iban').value;
                if (!iban) { alert('IBAN giriniz'); return; }
                params.iban = iban;
            }
            else {
                const name = document.getElementById('name')?.value;
                const surname = document.getElementById('surname')?.value;
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
                        if (record && typeof record === 'object') {
                            Object.keys(record).forEach(key => {
                                if (record[key] && record[key] !== '') allKeys.add(key);
                            });
                        }
                    });
                    
                    const headers = Array.from(allKeys);
                    
                    html += '<div style="overflow-x: auto;"><table class="result-table"><tr>';
                    headers.forEach(key => {
                        html += `<th>${key}</th>`;
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
                    const record = data.data;
                    html += '<table class="result-table"><tr>';
                    for (let key in record) {
                        if (record[key] && record[key] !== '') {
                            html += `<th>${key}</th>`;
                        }
                    }
                    html += '</tr><tr>';
                    for (let key in record) {
                        if (record[key] && record[key] !== '') {
                            html += `<td>${record[key]}</td>`;
                        }
                    }
                    html += '</tr></table>';
                    
                } else if (data.success && data.sonuclar && data.sonuclar.length > 0) {
                    html += `<div class="record-count">📊 Toplam ${data.sonuc_sayisi || data.sonuclar.length} kayıt</div>`;
                    
                    const allKeys = new Set();
                    data.sonuclar.forEach(record => {
                        if (record && typeof record === 'object') {
                            Object.keys(record).forEach(key => {
                                if (record[key] && record[key] !== '') allKeys.add(key);
                            });
                        }
                    });
                    
                    const headers = Array.from(allKeys);
                    
                    html += '<div style="overflow-x: auto;"><table class="result-table"><tr>';
                    headers.forEach(key => {
                        html += `<th>${key}</th>`;
                    });
                    html += '</tr>';
                    
                    data.sonuclar.forEach(record => {
                        html += '<tr>';
                        headers.forEach(key => {
                            html += `<td>${record[key] || '-'}</td>`;
                        });
                        html += '</tr>';
                    });
                    html += '</table></div>';
                    
                } else if (data.status === true && data.data) {
                    const record = data.data;
                    html += '<table class="result-table"><tr>';
                    for (let key in record) {
                        if (record[key] && record[key] !== '') {
                            html += `<th>${key}</th>`;
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
                    html = `<div class="error-box"><h3>Hata</h3><p>${data.error || data.message || 'Kayıt bulunamadı'}</p></div>`;
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

# ========== ADMIN SAYFASI ==========
ADMIN_PAGE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
    <title>Efendi Panel · admin</title>
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
            padding:12px 20px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            position:sticky;
            top:0;
            z-index:100;
        }
        .nav-brand {
            display:flex;
            align-items:center;
            gap:10px;
        }
        .nav-brand i { font-size:24px; color:#3b82f6; }
        .nav-brand span { font-size:18px; font-weight:600; }
        .nav-links {
            display:flex;
            gap:10px;
            align-items:center;
        }
        .nav-link {
            color:#d1d9e8;
            text-decoration:none;
            padding:6px 12px;
            border-radius:30px;
            transition:0.2s;
            font-size:14px;
        }
        .nav-link:hover { background:rgba(255,255,255,0.05); color:white; }
        .nav-link.active { background:#3b82f6; color:white; }
        .user-info {
            display:flex;
            align-items:center;
            gap:10px;
            background:rgba(255,255,255,0.03);
            padding:5px 10px 5px 15px;
            border-radius:40px;
            font-size:13px;
        }
        .role-badge.kurucu { background:#ef4444; color:white; padding:3px 8px; border-radius:30px; font-size:11px; }
        .container {
            max-width:1400px;
            margin:20px auto;
            padding:0 15px;
        }
        .admin-header {
            margin-bottom:20px;
        }
        .admin-header h1 {
            font-size:28px;
            color:#3b82f6;
        }
        .admin-tabs {
            display:flex;
            gap:5px;
            margin-bottom:20px;
            border-bottom:1px solid rgba(255,255,255,0.1);
            padding-bottom:10px;
            overflow-x:auto;
            white-space:nowrap;
        }
        .tab-btn {
            background:transparent;
            border:none;
            color:#94a3b8;
            padding:8px 15px;
            cursor:pointer;
            font-size:14px;
            border-radius:30px;
            transition:0.2s;
        }
        .tab-btn:hover {
            background:rgba(59,130,246,0.1);
            color:#3b82f6;
        }
        .tab-btn.active {
            background:#3b82f6;
            color:white;
        }
        .tab-content {
            display:none;
        }
        .tab-content.active {
            display:block;
        }
        .add-user-form {
            background:#11161f;
            border-radius:24px;
            padding:20px;
            margin-bottom:20px;
            border:1px solid rgba(255,255,255,0.03);
        }
        .form-grid {
            display:grid;
            grid-template-columns:1fr;
            gap:15px;
        }
        @media (min-width: 768px) {
            .form-grid {
                grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
            }
        }
        .form-group {
            margin-bottom:10px;
        }
        .form-group label {
            display:block;
            color:#94a3b8;
            margin-bottom:5px;
            font-size:13px;
        }
        .form-group input, .form-group select {
            width:100%;
            padding:10px 12px;
            background:#1e293b;
            border:1px solid rgba(255,255,255,0.05);
            border-radius:12px;
            color:white;
            font-size:14px;
            outline:none;
        }
        .form-group input:focus, .form-group select:focus {
            border-color:#3b82f6;
        }
        .btn {
            background:#3b82f6;
            color:white;
            border:none;
            padding:10px 20px;
            border-radius:30px;
            cursor:pointer;
            font-size:14px;
            font-weight:600;
            transition:0.2s;
        }
        .btn:hover {
            background:#2563eb;
        }
        .btn-danger {
            background:#ef4444;
        }
        .btn-danger:hover {
            background:#dc2626;
        }
        .btn-success {
            background:#10b981;
        }
        .btn-success:hover {
            background:#059669;
        }
        .users-table {
            width:100%;
            border-collapse:collapse;
            background:#11161f;
            border-radius:20px;
            overflow-x:auto;
            display:block;
            font-size:12px;
        }
        .users-table th {
            background:#1e293b;
            padding:10px;
            text-align:left;
            color:white;
            font-size:12px;
        }
        .users-table td {
            padding:8px 10px;
            border-bottom:1px solid rgba(255,255,255,0.05);
            color:#cbd5e1;
        }
        .users-table tr:hover {
            background:rgba(59,130,246,0.1);
        }
        .badge {
            padding:3px 6px;
            border-radius:15px;
            font-size:10px;
            font-weight:600;
            display:inline-block;
        }
        .badge.vip { background:#8b5cf6; color:white; }
        .badge.kurucu { background:#ef4444; color:white; }
        .badge.free { background:#64748b; color:white; }
        .badge.active { background:#10b981; color:white; }
        .badge.inactive { background:#ef4444; color:white; }
        .action-btn {
            background:transparent;
            border:none;
            color:#3b82f6;
            cursor:pointer;
            margin:0 3px;
            font-size:14px;
        }
        .action-btn:hover {
            color:#2563eb;
        }
        .action-btn.delete {
            color:#ef4444;
        }
        .search-box {
            margin-bottom:15px;
        }
        .search-box input {
            width:100%;
            padding:10px 15px;
            background:#1e293b;
            border:1px solid rgba(255,255,255,0.05);
            border-radius:30px;
            color:white;
            font-size:14px;
        }
        .message {
            padding:12px 15px;
            border-radius:20px;
            margin-bottom:15px;
            display:none;
            font-size:14px;
        }
        .message.success {
            background:rgba(16,185,129,0.2);
            border:1px solid #10b981;
            color:#a7f3d0;
            display:block;
        }
        .message.error {
            background:rgba(239,68,68,0.2);
            border:1px solid #ef4444;
            color:#fca5a5;
            display:block;
        }
        .stats-grid {
            display:grid;
            grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
            gap:15px;
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
</head>
<body>
    <div class="navbar">
        <div class="nav-brand">
            <i class="fas fa-crown"></i>
            <span>Admin</span>
        </div>
        <div class="nav-links">
            <a href="/" class="nav-link"><i class="fas fa-home"></i></a>
            <a href="/sorgu" class="nav-link"><i class="fas fa-search"></i></a>
            <a href="/admin" class="nav-link active"><i class="fas fa-cog"></i></a>
            <div class="user-info">
                <i class="far fa-user-circle"></i> <span>{{ session.email.split('@')[0] }}</span>
                <span class="role-badge kurucu">kurucu</span>
                <a href="/logout" style="color:#ef4444;"><i class="fas fa-sign-out-alt"></i></a>
            </div>
        </div>
    </div>
    
    <div class="container">
        <div class="admin-header">
            <h1>🔧 Admin Paneli</h1>
        </div>
        
        <div id="message" class="message {% if message_type %}{{ message_type }}{% endif %}">
            {{ message|safe }}
        </div>
        
        <div class="admin-tabs">
            <button class="tab-btn active" onclick="showTab('users')">👥 Kullanıcılar</button>
            <button class="tab-btn" onclick="showTab('add')">➕ Kullanıcı Ekle</button>
            <button class="tab-btn" onclick="showTab('packages')">📦 Paketler</button>
            <button class="tab-btn" onclick="showTab('stats')">📊 İstatistikler</button>
        </div>
        
        <!-- Kullanıcı Listesi Tab -->
        <div id="tab-users" class="tab-content active">
            <div class="search-box">
                <input type="text" id="userSearch" placeholder="🔍 E-posta ile ara..." onkeyup="searchUsers()">
            </div>
            
            <div style="overflow-x: auto;">
                <table class="users-table">
                    <thead>
                        <tr>
                            <th>E-posta</th>
                            <th>Rol</th>
                            <th>Durum</th>
                            <th>İşlemler</th>
                        </tr>
                    </thead>
                    <tbody id="usersTableBody">
                        {% for user in users %}
                        <tr class="user-row" data-email="{{ user.email|lower }}">
                            <td>{{ user.email }}</td>
                            <td>
                                <span class="badge {% if user.role == 'vip' %}vip{% elif user.role == 'kurucu' %}kurucu{% else %}free{% endif %}">
                                    {{ user.role }}
                                </span>
                            </td>
                            <td>
                                <span class="badge {% if user.active %}active{% else %}inactive{% endif %}">
                                    {{ 'Aktif' if user.active else 'Pasif' }}
                                </span>
                            </td>
                            <td>
                                <button class="action-btn" onclick="toggleUserStatus('{{ user.email }}')" title="Durum değiştir">
                                    <i class="fas {% if user.active %}fa-toggle-on{% else %}fa-toggle-off{% endif %}"></i>
                                </button>
                                <button class="action-btn delete" onclick="deleteUser('{{ user.email }}')" title="Sil">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Kullanıcı Ekle Tab -->
        <div id="tab-add" class="tab-content">
            <div class="add-user-form">
                <h3 style="margin-bottom:15px; color:#3b82f6; font-size:18px;">➕ Yeni Kullanıcı Ekle</h3>
                
                <form method="POST" action="/admin/add_user">
                    <div class="form-grid">
                        <div class="form-group">
                            <label>E-posta</label>
                            <input type="email" name="email" required>
                        </div>
                        <div class="form-group">
                            <label>Şifre</label>
                            <input type="text" name="password" required value="{{ secrets.token_hex(4) }}">
                        </div>
                        <div class="form-group">
                            <label>Rol</label>
                            <select name="role" id="roleSelect" onchange="togglePackage()">
                                <option value="free">Free</option>
                                <option value="vip">VIP</option>
                                <option value="vip_sınırsız">VIP Sınırsız</option>
                                <option value="kurucu">Kurucu</option>
                            </select>
                        </div>
                        <div class="form-group" id="packageGroup">
                            <label>Paket</label>
                            <select name="package">
                                <option value="">Paket seçin</option>
                                {% for p in packages %}
                                <option value="{{ p.name }}">{{ p.name }} - {{ p.price }}₺</option>
                                {% endfor %}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Not</label>
                            <input type="text" name="note" placeholder="İsteğe bağlı">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success">Kullanıcı Ekle</button>
                </form>
            </div>
        </div>
        
        <!-- Paketler Tab -->
        <div id="tab-packages" class="tab-content">
            <div class="add-user-form">
                <h3 style="margin-bottom:15px; color:#3b82f6; font-size:18px;">📦 Mevcut Paketler</h3>
                
                <div style="overflow-x: auto;">
                    <table class="users-table">
                        <thead>
                            <tr>
                                <th>Paket Adı</th>
                                <th>Fiyat</th>
                                <th>Süre</th>
                                <th>Rol</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for p in packages %}
                            <tr>
                                <td>{{ p.name }}</td>
                                <td>{{ p.price }}₺</td>
                                <td>{{ p.days if p.days else 'Sınırsız' }}</td>
                                <td>{{ p.role }}</td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <!-- İstatistikler Tab -->
        <div id="tab-stats" class="tab-content">
            <div class="add-user-form">
                <h3 style="margin-bottom:15px; color:#3b82f6; font-size:18px;">📊 İstatistikler</h3>
                
                <div class="stats-grid">
                    <div style="background:#1e293b; padding:15px; border-radius:16px; text-align:center;">
                        <div style="font-size:28px; color:#3b82f6;">{{ stats.total_users }}</div>
                        <div style="color:#94a3b8; font-size:13px;">Toplam Kullanıcı</div>
                    </div>
                    <div style="background:#1e293b; padding:15px; border-radius:16px; text-align:center;">
                        <div style="font-size:28px; color:#8b5cf6;">{{ stats.vip_users }}</div>
                        <div style="color:#94a3b8; font-size:13px;">VIP Kullanıcı</div>
                    </div>
                    <div style="background:#1e293b; padding:15px; border-radius:16px; text-align:center;">
                        <div style="font-size:28px; color:#10b981;">{{ stats.active_users }}</div>
                        <div style="color:#94a3b8; font-size:13px;">Aktif Kullanıcı</div>
                    </div>
                    <div style="background:#1e293b; padding:15px; border-radius:16px; text-align:center;">
                        <div style="font-size:28px; color:#fbbf24;">{{ stats.total_queries }}</div>
                        <div style="color:#94a3b8; font-size:13px;">Toplam Sorgu</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function showTab(tabName) {
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            document.querySelector(`.tab-btn[onclick="showTab('${tabName}')"]`).classList.add('active');
            document.getElementById(`tab-${tabName}`).classList.add('active');
        }
        
        function togglePackage() {
            const role = document.getElementById('roleSelect').value;
            const packageGroup = document.getElementById('packageGroup');
            packageGroup.style.display = role === 'vip' ? 'block' : 'none';
        }
        
        function searchUsers() {
            const search = document.getElementById('userSearch').value.toLowerCase();
            const rows = document.querySelectorAll('.user-row');
            rows.forEach(row => {
                const email = row.dataset.email;
                row.style.display = email.includes(search) ? '' : 'none';
            });
        }
        
        function toggleUserStatus(email) {
            if (confirm('Kullanıcı durumunu değiştirmek istediğinize emin misiniz?')) {
                window.location.href = `/admin/toggle_user/${encodeURIComponent(email)}`;
            }
        }
        
        function deleteUser(email) {
            if (confirm('Bu kullanıcıyı silmek istediğinize emin misiniz?')) {
                window.location.href = `/admin/delete_user/${encodeURIComponent(email)}`;
            }
        }
        
        togglePackage();
    </script>
</body>
</html>
"""

# ========== YENİ API FONKSİYONLARI ==========

def fetch_adsoyadpro(ad, soyad, il=None):
    """Ad+Soyad+İl ile kapsamlı sorgu"""
    try:
        url = f"https://punisherapi.alwaysdata.net/apiservices/adsoyadpro.php?ad={ad}&soyad={soyad}"
        if il:
            url += f"&il={il}"
        
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('success') and data.get('results'):
            return {'success': True, 'records': data['results'], 'count': len(data['results'])}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_ailepro(tc):
    """TC ile aile sorgula (detaylı)"""
    try:
        url = f"https://punisherapi.alwaysdata.net/apiservices/ailepro.php?tc={tc}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('success') and data.get('results'):
            return {'success': True, 'records': data['results'], 'count': len(data['results'])}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_adres(tc):
    """TC ile adres sorgula"""
    try:
        url = f"https://punisherapi.alwaysdata.net/apiservices/adres.php?tc={tc}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('success') and data.get('results'):
            return {'success': True, 'records': data['results'], 'count': len(data['results'])}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_iban(iban):
    """IBAN sorgula"""
    try:
        url = f"https://punisherapi.alwaysdata.net/apiservices/iban.php?iban={iban}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('status') and data.get('data'):
            return {'success': True, 'data': data['data']}
        return {'success': False, 'error': data.get('message', 'Kayıt bulunamadı')}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_operator(telefon):
    """Güncel operatör sorgula"""
    try:
        url = f"https://punisherapi.alwaysdata.net/apiservices/gncloperator.php?numara={telefon}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('status') and data.get('data'):
            return {'success': True, 'data': data['data']}
        return {'success': False, 'error': data.get('message', 'Kayıt bulunamadı')}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_plaka_adsoyad(ad, soyad):
    """Ad Soyad ile plaka sorgula"""
    try:
        url = f"https://plaka-3ytw.onrender.com/f3api/adsoyadplaka?ad={ad}&soyad={soyad}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('success') and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': len(data['sonuclar'])}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_plaka_ad(ad):
    """Ad ile plaka sorgula"""
    try:
        url = f"https://plaka-3ytw.onrender.com/f3api/adsoyadplaka?ad={ad}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('success') and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': len(data['sonuclar'])}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_papara_no(paparano):
    """Papara no ile sorgula"""
    try:
        url = f"https://paparadata-hh3v.onrender.com/f3system/api/papara?paparano={paparano}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('sonuc_sayisi', 0) > 0 and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': data['sonuc_sayisi']}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_papara_ad(ad, soyad=None):
    """Ad veya Ad Soyad ile papara sorgula"""
    try:
        if soyad:
            url = f"https://paparadata-hh3v.onrender.com/f3system/api/papara?ad={ad}&soyad={soyad}"
        else:
            url = f"https://paparadata-hh3v.onrender.com/f3system/api/papara?ad={ad}"
        
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('sonuc_sayisi', 0) > 0 and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': data['sonuc_sayisi']}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_vergi_isim(isim):
    """İsim ile vergi sorgula"""
    try:
        url = f"https://vergidata-ezqa.onrender.com/f3system/api/vergi?isim={isim}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('bulunan', 0) > 0 and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': data['bulunan']}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_vergi_no(vergi_no):
    """Vergi no ile sorgula"""
    try:
        url = f"https://vergidata-ezqa.onrender.com/f3system/api/vergi?vergi_no={vergi_no}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('bulunan', 0) > 0 and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': data['bulunan']}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_vergi_detay(ilce=None, vergi_dairesi=None):
    """İlçe veya vergi dairesi ile sorgula"""
    try:
        url = "https://vergidata-ezqa.onrender.com/f3system/api/vergi?"
        params = []
        if ilce:
            params.append(f"ilce={ilce}")
        if vergi_dairesi:
            params.append(f"vergi_dairesi={vergi_dairesi}")
        url += "&".join(params)
        
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('bulunan', 0) > 0 and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': data['bulunan']}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_serino_tc(tc):
    """TC ile seri no sorgula"""
    try:
        url = f"https://serinodata-eo6k.onrender.com/serino?tc={tc}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('bulunan', 0) > 0 and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': data['bulunan']}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_serino_ad(ad):
    """Ad ile seri no sorgula"""
    try:
        url = f"https://serinodata-eo6k.onrender.com/serino?ad={ad}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('bulunan', 0) > 0 and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': data['bulunan']}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_serino_adsoyad(ad, soyad):
    """Ad soyad ile seri no sorgula"""
    try:
        url = f"https://serinodata-eo6k.onrender.com/serino?ad={ad}&soyad={soyad}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('bulunan', 0) > 0 and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': data['bulunan']}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def fetch_serino_seri(seri_no):
    """Seri no ile sorgula"""
    try:
        url = f"https://serinodata-eo6k.onrender.com/serino?seri_no={seri_no}"
        response = requests.get(url, timeout=30)
        data = response.json()
        data = fix_dict_turkish_chars(data)
        
        if data.get('bulunan', 0) > 0 and data.get('sonuclar'):
            return {'success': True, 'records': data['sonuclar'], 'count': data['bulunan']}
        return {'success': False, 'error': 'Kayıt bulunamadı'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

# ========== API ENDPOINT'LERİ ==========
@app.route('/api/<endpoint>')
@vip_required
def api_endpoint(endpoint):
    """API endpoint'leri"""
    
    # Parametreleri al ve sorguyu kaydet
    user = get_current_user()
    
    # YENİ API'LER
    if endpoint == 'adsoyadpro':
        ad = request.args.get('ad', '')
        soyad = request.args.get('soyad', '')
        il = request.args.get('il', '')
        if not ad or not soyad:
            return jsonify({'success': False, 'error': 'Ad ve soyad girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_adsoyadpro(ad, soyad, il)
        return jsonify(result)
    
    elif endpoint == 'ailepro':
        tc = request.args.get('tc', '')
        if not tc or len(tc) != 11:
            return jsonify({'success': False, 'error': 'Geçerli TC girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_ailepro(tc)
        return jsonify(result)
    
    elif endpoint == 'adres':
        tc = request.args.get('tc', '')
        if not tc or len(tc) != 11:
            return jsonify({'success': False, 'error': 'Geçerli TC girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_adres(tc)
        return jsonify(result)
    
    elif endpoint == 'iban':
        iban = request.args.get('iban', '')
        if not iban:
            return jsonify({'success': False, 'error': 'IBAN girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_iban(iban)
        return jsonify(result)
    
    elif endpoint == 'operator':
        telefon = request.args.get('telefon', '') or request.args.get('gsm', '')
        if not telefon:
            return jsonify({'success': False, 'error': 'Telefon numarası girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_operator(telefon)
        return jsonify(result)
    
    elif endpoint == 'plaka_adsoyad':
        ad = request.args.get('ad', '')
        soyad = request.args.get('soyad', '')
        if not ad or not soyad:
            return jsonify({'success': False, 'error': 'Ad ve soyad girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_plaka_adsoyad(ad, soyad)
        return jsonify(result)
    
    elif endpoint == 'plaka_ad':
        ad = request.args.get('ad', '')
        if not ad:
            return jsonify({'success': False, 'error': 'Ad girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_plaka_ad(ad)
        return jsonify(result)
    
    elif endpoint == 'papara_no':
        paparano = request.args.get('paparano', '')
        if not paparano:
            return jsonify({'success': False, 'error': 'Papara numarası girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_papara_no(paparano)
        return jsonify(result)
    
    elif endpoint == 'papara_ad':
        ad = request.args.get('ad', '')
        soyad = request.args.get('soyad', '')
        if not ad:
            return jsonify({'success': False, 'error': 'Ad girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_papara_ad(ad, soyad)
        return jsonify(result)
    
    elif endpoint == 'vergi_isim':
        isim = request.args.get('isim', '')
        if not isim:
            return jsonify({'success': False, 'error': 'İsim girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_vergi_isim(isim)
        return jsonify(result)
    
    elif endpoint == 'vergi_no':
        vergi_no = request.args.get('vergi_no', '')
        if not vergi_no:
            return jsonify({'success': False, 'error': 'Vergi numarası girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_vergi_no(vergi_no)
        return jsonify(result)
    
    elif endpoint == 'vergi_detay':
        ilce = request.args.get('ilce', '')
        vergi_dairesi = request.args.get('vergi_dairesi', '')
        if not ilce and not vergi_dairesi:
            return jsonify({'success': False, 'error': 'İlçe veya vergi dairesi girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_vergi_detay(ilce, vergi_dairesi)
        return jsonify(result)
    
    elif endpoint == 'serino_tc':
        tc = request.args.get('tc', '')
        if not tc or len(tc) != 11:
            return jsonify({'success': False, 'error': 'Geçerli TC girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_serino_tc(tc)
        return jsonify(result)
    
    elif endpoint == 'serino_ad':
        ad = request.args.get('ad', '')
        if not ad:
            return jsonify({'success': False, 'error': 'Ad girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_serino_ad(ad)
        return jsonify(result)
    
    elif endpoint == 'serino_adsoyad':
        ad = request.args.get('ad', '')
        soyad = request.args.get('soyad', '')
        if not ad or not soyad:
            return jsonify({'success': False, 'error': 'Ad ve soyad girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_serino_adsoyad(ad, soyad)
        return jsonify(result)
    
    elif endpoint == 'serino_seri':
        seri_no = request.args.get('seri_no', '')
        if not seri_no:
            return jsonify({'success': False, 'error': 'Seri no girin'})
        
        if user:
            queries_collection.insert_one({
                "user": user['email'],
                "endpoint": endpoint,
                "params": request.args.to_dict(),
                "timestamp": datetime.now()
            })
        
        result = fetch_serino_seri(seri_no)
        return jsonify(result)
    
    # MEVCUT API'LER
    elif endpoint in ['tc-isegiris', 'tc-ikametgah', 'tc-ailebirey', 'tc-medenicinsiyet', 'tc', 'aile', 'sulale', 'hane', 'isyeri', 'tc2']:
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
    
    # Sorguyu kaydet
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": endpoint,
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
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
    """Tüm kayıtları ayıkla"""
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
        
        user = users_collection.find_one({"email": email})
        
        if user and check_password(password, user['password']):
            if not user.get('active', True):
                return render_template_string(LOGIN_PAGE, error="Hesabınız pasif durumda")
            
            # Süre kontrolü
            if user.get('expires') and user['expires'] < datetime.now():
                users_collection.update_one(
                    {"email": email},
                    {"$set": {"active": False}}
                )
                return render_template_string(LOGIN_PAGE, error="Süreniz dolmuş")
            
            session['email'] = email
            session['role'] = user['role']
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
        
        if users_collection.find_one({"email": email}):
            return render_template_string(REGISTER_PAGE, error="Bu e-posta zaten kayıtlı")
        
        users_collection.insert_one({
            "email": email,
            "password": hash_password(password),
            "role": "free",
            "active": True,
            "created_at": datetime.now(),
            "created_by": "self",
            "package": None,
            "expires": None,
            "note": "Ücretsiz kayıt"
        })
        
        return render_template_string(REGISTER_PAGE, success="Kayıt başarılı! Giriş yapabilirsiniz.")
    
    return render_template_string(REGISTER_PAGE)

@app.route('/market')
@login_required
def market_page():
    return redirect(url_for('home'))

@app.route('/sorgu')
@vip_required
def query_page():
    endpoint = request.args.get('endpoint', 'isegiris')
    query_type = request.args.get('type', 'ad')
    return render_template_string(QUERY_PAGE, session=session, endpoint=endpoint, type=query_type)

# ========== ADMIN ROUTE'LARI ==========
@app.route('/admin')
@kurucu_required
def admin_page():
    users = list(users_collection.find({}).sort("created_at", -1))
    packages = list(packages_collection.find({}))
    
    # İstatistikler
    stats = {
        "total_users": users_collection.count_documents({}),
        "vip_users": users_collection.count_documents({"role": {"$in": ["vip", "vip_sınırsız"]}}),
        "active_users": users_collection.count_documents({"active": True}),
        "total_queries": queries_collection.count_documents({})
    }
    
    return render_template_string(ADMIN_PAGE, session=session, users=users, packages=packages, stats=stats, secrets=secrets)

@app.route('/admin/add_user', methods=['POST'])
@kurucu_required
def add_user():
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', 'free')
    package = request.form.get('package', '')
    note = request.form.get('note', '')
    
    if users_collection.find_one({"email": email}):
        return redirect('/admin?message=Bu e-posta zaten kayıtlı&type=error')
    
    expires = None
    if role == 'vip' and package:
        pkg = packages_collection.find_one({"name": package})
        if pkg and pkg.get('days'):
            expires = datetime.now() + timedelta(days=pkg['days'])
    
    users_collection.insert_one({
        "email": email,
        "password": hash_password(password),
        "role": role,
        "active": True,
        "created_at": datetime.now(),
        "created_by": session['email'],
        "package": package,
        "expires": expires,
        "note": note
    })
    
    return redirect('/admin?message=Kullanıcı eklendi&type=success')

@app.route('/admin/toggle_user/<path:email>')
@kurucu_required
def toggle_user(email):
    user = users_collection.find_one({"email": email})
    if user:
        users_collection.update_one(
            {"email": email},
            {"$set": {"active": not user.get('active', True)}}
        )
    return redirect('/admin?message=Durum güncellendi&type=success')

@app.route('/admin/delete_user/<path:email>')
@kurucu_required
def delete_user(email):
    if email == session['email']:
        return redirect('/admin?message=Kendi hesabını silemezsin&type=error')
    
    users_collection.delete_one({"email": email})
    queries_collection.delete_many({"user": email})
    return redirect('/admin?message=Kullanıcı silindi&type=success')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ========== MAIN ==========
if __name__ == '__main__':
    print("="*60)
    print("🚀 Efendi Panel başlatılıyor...")
    print("="*60)
    print("\n📋 KURUCU: babalar@gmail.com / uykumvar")
    print("📋 MONGODB: Bağlı")
    print("📱 MOBİL UYUMLU: Menü %85 genişlik, çıkış butonu eklendi")
    print("🔥 YENİ: 20+ yeni API eklendi (Papara, Vergi, Seri No, Plaka, IBAN, Operatör)")
    print("\n🌐 http://localhost:5000")
    print("="*60)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)
