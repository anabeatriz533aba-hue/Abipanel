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

def extract_common_fields(data):
    """Yanıttan ortak alanları (tc, ad, soyad, telefon vb.) çıkar"""
    if not isinstance(data, dict):
        return {}
    
    common = {}
    # Temel kimlik bilgileri
    for field in ['tc', 'ad', 'soyad', 'dogumTarihi', 'dogumYeri', 'babaAdi', 'anneAdi', 
                  'cinsiyet', 'il', 'ilce', 'mahalle', 'sokak', 'kapiNo', 'daireNo', 'telefon']:
        if field in data and data[field]:
            common[field] = data[field]
    
    return common

def format_table_from_list(data_list, title=None):
    """Liste tipindeki verileri tabloya dönüştür"""
    if not data_list or not isinstance(data_list, list):
        return ""
    
    html = ""
    if title:
        html += f"<h4 style='color:#ffaa00; margin:15px 0 10px 0;'>{title}</h4>"
    
    # Tüm benzersiz anahtarları bul
    all_keys = set()
    for item in data_list:
        if isinstance(item, dict):
            for key in item.keys():
                if item[key] and str(item[key]).strip() and str(item[key]) != '-':
                    all_keys.add(key)
    
    if not all_keys:
        return html + "<p>Kayıt bulunamadı</p>"
    
    keys = sorted(list(all_keys))
    
    html += '<div style="overflow-x: auto; margin-bottom:20px;">'
    html += '<table class="result-table" style="width:100%; border-collapse:collapse;">'
    
    # Başlık
    html += '<tr>'
    for key in keys:
        display_key = key.replace('_', ' ').replace('adi', ' Adı').replace('soyadi', ' Soyadı').title()
        html += f'<th style="background:#050508; padding:10px; text-align:left; color:#fff; font-size:11px; border-bottom:1px solid rgba(255,255,255,0.05);">{display_key}</th>'
    html += '</tr>'
    
    # Veriler
    for item in data_list:
        if not isinstance(item, dict):
            continue
        html += '<tr>'
        for key in keys:
            value = item.get(key, '-')
            if isinstance(value, dict) or isinstance(value, list):
                value = json.dumps(value, ensure_ascii=False)[:50] + "..."
            elif value is None:
                value = '-'
            html += f'<td style="padding:8px 10px; border-bottom:1px solid rgba(255,255,255,0.02); color:#a0a0ab; font-size:12px;">{value}</td>'
        html += '</tr>'
    
    html += '</table></div>'
    return html

def format_nested_data(data, parent_key=""):
    """İç içe geçmiş verileri tablolaştır"""
    if not isinstance(data, dict):
        return str(data) if data else "-"
    
    html = ""
    
    # Önce ortak alanları göster (ama tabloda gösterme)
    common_fields = extract_common_fields(data)
    
    # Diğer alanları işle
    for key, value in data.items():
        if key in common_fields or key.startswith('_') or not value:
            continue
            
        display_key = key.replace('_', ' ').replace('adi', ' Adı').replace('soyadi', ' Soyadı').title()
        
        if isinstance(value, list) and len(value) > 0:
            # Liste varsa tablo yap
            html += format_table_from_list(value, display_key)
        elif isinstance(value, dict):
            # İç içe dict varsa alt başlık aç
            html += f"<h4 style='color:#3b82f6; margin:15px 0 10px 0; font-size:14px;'>{display_key}</h4>"
            html += '<div style="background:#0a0a12; padding:15px; border-radius:12px; margin-bottom:15px;">'
            for k, v in value.items():
                if v:
                    display_subkey = k.replace('_', ' ').replace('adi', ' Adı').replace('soyadi', ' Soyadı').title()
                    html += f'<div style="display:flex; margin-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.02); padding-bottom:5px;">'
                    html += f'<span style="width:150px; color:#a0a0ab; font-size:12px;">{display_subkey}:</span>'
                    html += f'<span style="color:#fff; font-size:12px;">{v}</span>'
                    html += '</div>'
            html += '</div>'
        else:
            # Normal alanları tablo olmadan göster
            if not html.startswith('<div'):
                html += '<div style="background:#0a0a12; padding:15px; border-radius:12px; margin-bottom:15px;">'
            
            if value:
                html += f'<div style="display:flex; margin-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.02); padding-bottom:5px;">'
                html += f'<span style="width:150px; color:#a0a0ab; font-size:12px;">{display_key}:</span>'
                html += f'<span style="color:#fff; font-size:12px;">{value}</span>'
                html += '</div>'
    
    if html and not html.startswith('<h4') and not html.startswith('<div'):
        html = '<div style="background:#0a0a12; padding:15px; border-radius:12px; margin-bottom:15px;">' + html + '</div>'
    
    return html

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
            background: #050508;
            position: relative;
        }
        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background: url('https://i.ibb.co/Ldc4b2YF/file-00000000f190720cb7f53c717d6f458d.png') no-repeat center center fixed;
            background-size: cover;
            opacity: 0.15;
            z-index: 0;
        }
        
        /* Menü Butonu Konumu (Sol Üst) */
        .menu-toggle {
            position: fixed;
            top: 20px;
            left: 20px;
            width: 50px;
            height: 50px;
            background: #0d0d15;
            border: 1px solid rgba(255,255,255,0.05);
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
        
        /* Yan Menü (Soldan Açılır) - Mobilde Daha Dar */
        .side-menu {
            position: fixed;
            top: 0;
            left: -90%;
            width: 90%;
            max-width: 280px;
            height: 100vh;
            background: #0d0d15;
            border-right: 1px solid rgba(255,255,255,0.02);
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
                left: -300px;
                width: 280px;
            }
        }
        
        .side-menu.open { left: 0; }
        
        .profile-section {
            padding: 20px 15px;
            background: #050508;
            border-bottom: 1px solid rgba(255,255,255,0.02);
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .profile-avatar {
            width: 42px;
            height: 42px;
            border-radius: 8px;
            overflow: hidden;
        }
        .profile-avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .profile-info {
            flex: 1;
        }
        .profile-name {
            font-size: 15px;
            font-weight: 600;
            color: white;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .blue-tick { color: #3b82f6; font-size: 13px; }
        .online-status {
            display: flex;
            align-items: center;
            gap: 5px;
            margin-top: 3px;
            font-size: 9px;
            color: #a0a0ab;
            letter-spacing: 1px;
            font-weight: 500;
        }
        .online-dot {
            width: 6px;
            height: 6px;
            background: #2ecc71;
            border-radius: 50%;
            box-shadow: 0 0 8px #2ecc71;
        }
        
        .menu-categories {
            flex: 1;
            padding: 12px 10px;
            overflow-y: auto;
        }
        
        /* Yeni Çözümler kategorisi için parlama efekti - DAHA BELİRGİN */
        .category-block.new-solutions .category-header {
            color: #ffaa00 !important;
            text-transform: uppercase;
            font-weight: 900;
            letter-spacing: 2px;
            text-shadow: 0 0 20px #ffaa00, 0 0 40px rgba(255,170,0,0.5);
            background: transparent !important;
            font-size: 12px;
        }
        .category-block.new-solutions .category-header i {
            color: #ffaa00;
            text-shadow: 0 0 15px #ffaa00;
        }
        
        .category-block {
            margin-bottom: 10px;
            background: transparent;
        }
        .category-header {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 5px;
            background: transparent;
            border-radius: 0;
            font-weight: 800;
            font-size: 11px;
            letter-spacing: 2.5px;
            color: #606070;
            cursor: pointer;
            text-transform: uppercase;
            border-bottom: 1px solid rgba(255,255,255,0.03);
        }
        .category-header i { 
            color: #606070; 
            width: 18px; 
            font-size: 12px;
            opacity: 0.8;
        }
        .category-header .arrow {
            margin-left: auto;
            transition: transform 0.3s;
            color: #606070;
            font-size: 9px;
            opacity: 0.7;
        }
        .query-list {
            list-style: none;
            margin: 5px 0 8px 8px;
            padding-left: 10px;
            border-left: 1px solid rgba(255,255,255,0.05);
            display: none;
        }
        .query-list.open { display: block; }
        .query-item {
            padding: 8px 10px;
            margin: 3px 0;
            background: transparent;
            border-radius: 6px;
            color: #b0b0c0;
            display: flex;
            align-items: center;
            gap: 10px;
            cursor: pointer;
            transition: all 0.15s;
            font-size: 12px;
            font-weight: 500;
            border-left: 2px solid transparent;
        }
        .query-item i { 
            color: #606070; 
            width: 16px; 
            font-size: 12px;
            opacity: 0.8;
            transition: all 0.15s;
        }
        .query-item:hover {
            background: rgba(59,130,246,0.08);
            color: #fff;
            transform: translateX(4px);
            border-left: 2px solid #3b82f6;
        }
        .query-item:hover i {
            opacity: 1;
            color: #3b82f6;
            transform: scale(1.1);
        }
        
        .logout-section {
            padding: 12px 15px;
            border-top: 1px solid rgba(255,255,255,0.02);
            margin-top: auto;
        }
        .logout-btn {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            width: 100%;
            padding: 12px;
            background: rgba(239,68,68,0.1);
            color: #ef4444;
            border: 1px solid rgba(239,68,68,0.2);
            border-radius: 30px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: 0.2s;
            text-decoration: none;
            letter-spacing: 1px;
        }
        .logout-btn:hover {
            background: #ef4444;
            color: white;
            border-color: #ef4444;
            transform: scale(1.02);
        }
        .logout-btn i { font-size: 14px; }
        
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
            background: rgba(13,13,21,0.8);
            backdrop-filter: blur(10px);
            border-radius: 30px;
            padding: 30px 25px;
            max-width: 500px;
            width: 100%;
            border: 1px solid rgba(255,255,255,0.02);
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
            background: rgba(59,130,246,0.1);
            border: 1px solid rgba(59,130,246,0.2);
            border-radius: 20px;
            padding: 12px 20px;
            text-align: center;
            flex: 1;
            min-width: 100px;
        }
        .stat-value { font-size: 22px; font-weight: 700; color: #3b82f6; }
        .stat-label { font-size: 12px; color: #a0a0ab; font-weight: 500; }
        
        .admin-link {
            background: rgba(239,68,68,0.1);
            color: #ef4444;
            padding: 4px 12px;
            border-radius: 30px;
            text-decoration: none;
            font-size: 12px;
            margin-left: 10px;
            display: inline-block;
            border: 1px solid rgba(239,68,68,0.2);
            font-weight: 600;
        }
        .admin-link:hover {
            background: #ef4444;
            color: white;
        }
        
        /* Mobilde yazılar daha belirgin */
        @media (max-width: 480px) {
            .category-header {
                font-size: 11px;
                letter-spacing: 2px;
            }
            .query-item {
                font-size: 12px;
                padding: 8px 10px;
            }
            .profile-name {
                font-size: 14px;
            }
            .online-status {
                font-size: 9px;
            }
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
                    <span class="online-dot"></span> ÇEVRİM İÇİ
                </div>
            </div>
        </div>
        
        <div class="menu-categories">
            <!-- PREMİUM ÇÖZÜMLER - Parlama efektli -->
            <div class="category-block new-solutions">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-fire"></i> PREMİUM ÇÖZÜMLER
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('nufus_sorgu', 'tc')"><i class="fas fa-id-card"></i> Nüfus Sorgula</li>
                    <li class="query-item" onclick="goToQuery('asi_kayitlari', 'tc')"><i class="fas fa-syringe"></i> Aşı Kayıtları</li>
                    <li class="query-item" onclick="goToQuery('rontgen_listesi', 'tc')"><i class="fas fa-x-ray"></i> Röntgen Listesi</li>
                    <li class="query-item" onclick="goToQuery('recete_gecmisi', 'tc')"><i class="fas fa-prescription"></i> Reçete Geçmişi</li>
                </ul>
            </div>

            <!-- SAĞLIK SORGULARI -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-heartbeat"></i> SAĞLIK SORGULARI
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('asi_kayitlari', 'tc')"><i class="fas fa-syringe"></i> Aşı Kayıtları</li>
                    <li class="query-item" onclick="goToQuery('rontgen_listesi', 'tc')"><i class="fas fa-x-ray"></i> Röntgen Listesi</li>
                    <li class="query-item" onclick="goToQuery('kronik_hastalik', 'tc')"><i class="fas fa-notes-medical"></i> Kronik Hastalık</li>
                    <li class="query-item" onclick="goToQuery('hasta_yatis_gecmisi', 'tc')"><i class="fas fa-hospital"></i> Hasta Yatış Geçmişi</li>
                </ul>
            </div>

            <!-- ADLİ SİCİL VE PASAPORT -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-gavel"></i> ADLİ İŞLEMLER
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('adli_sicil', 'tc')"><i class="fas fa-file-signature"></i> Adli Sicil Kaydı</li>
                    <li class="query-item" onclick="goToQuery('pasaport_sorgu', 'tc')"><i class="fas fa-passport"></i> Pasaport Sorgula</li>
                    <li class="query-item" onclick="goToQuery('noter_islem', 'tc')"><i class="fas fa-stamp"></i> Noter İşlemleri</li>
                </ul>
            </div>

            <!-- VERGİ VE TAPU -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-coins"></i> MALİ İŞLEMLER
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('vergi_borc', 'tc')"><i class="fas fa-file-invoice-dollar"></i> Vergi Borç Sorgula</li>
                    <li class="query-item" onclick="goToQuery('tapu_gayrimenkul', 'tc')"><i class="fas fa-home"></i> Tapu Gayrimenkul</li>
                    <li class="query-item" onclick="goToQuery('kredi_risk_raporu', 'tc')"><i class="fas fa-chart-line"></i> Kredi Risk Raporu</li>
                    <li class="query-item" onclick="goToQuery('dijital_banka', 'tc')"><i class="fas fa-university"></i> Dijital Banka Müşteri</li>
                </ul>
            </div>

            <!-- FATURA SORGULARI -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-file-invoice"></i> FATURA SORGULARI
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('su_fatura', 'tc')"><i class="fas fa-water"></i> Su Faturası</li>
                    <li class="query-item" onclick="goToQuery('elektrik_fatura', 'tc')"><i class="fas fa-bolt"></i> Elektrik Faturası</li>
                </ul>
            </div>

            <!-- ULAŞIM VE SEYAHAT -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-plane"></i> ULAŞIM & SEYAHAT
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('otel_rezervasyon', 'tc')"><i class="fas fa-hotel"></i> Otel Rezervasyon</li>
                    <li class="query-item" onclick="goToQuery('istanbulkart_bakiye', 'tc')"><i class="fas fa-bus"></i> İstanbulkart Bakiye</li>
                    <li class="query-item" onclick="goToQuery('ucak_bilet', 'tc')"><i class="fas fa-fighter-jet"></i> Uçak Bileti</li>
                    <li class="query-item" onclick="goToQuery('seyahat_hareket', 'tc')"><i class="fas fa-route"></i> Seyahat Hareket</li>
                    <li class="query-item" onclick="goToQuery('sehirlerarasi_ceza', 'tc')"><i class="fas fa-traffic-light"></i> Şehirlerarası Ceza</li>
                </ul>
            </div>

            <!-- DİĞER SORGULAR -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-ellipsis-h"></i> DİĞER SORGULAR
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('askerlik_durum', 'tc')"><i class="fas fa-shield-alt"></i> Askerlik Durumu</li>
                    <li class="query-item" onclick="goToQuery('spor_federasyon', 'tc')"><i class="fas fa-futbol"></i> Spor Federasyon Kaydı</li>
                    <li class="query-item" onclick="goToQuery('kutuphane_uye', 'tc')"><i class="fas fa-book"></i> Kütüphane Üyelik</li>
                    <li class="query-item" onclick="goToQuery('meb_mezuniyet', 'tc')"><i class="fas fa-graduation-cap"></i> MEB Mezuniyet</li>
                    <li class="query-item" onclick="goToQuery('ticaret_sikayet', 'tc')"><i class="fas fa-exclamation-triangle"></i> Ticaret Şikayet Kaydı</li>
                    <li class="query-item" onclick="goToQuery('ormancilik_avci', 'tc')"><i class="fas fa-tree"></i> Avcı Lisans</li>
                </ul>
            </div>

            <!-- Papara İşlemleri Kategorisi -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-money-bill-wave"></i> PAPARA İŞLEMLERİ
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
                    <i class="fas fa-landmark"></i> VERGİ DAİRESİ
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
                    <i class="fas fa-id-card"></i> SERİ NO SORGULA
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('serino_tc', 'serino_tc')"><i class="fas fa-id-card"></i> Seri No (TC ile)</li>
                    <li class="query-item" onclick="goToQuery('serino_ad', 'serino_ad')"><i class="fas fa-user"></i> Seri No (Ad ile)</li>
                    <li class="query-item" onclick="goToQuery('serino_adsoyad', 'serino_adsoyad')"><i class="fas fa-user-check"></i> Seri No (Ad Soyad ile)</li>
                    <li class="query-item" onclick="goToQuery('serino_seri', 'serino_seri')"><i class="fas fa-barcode"></i> Seri No (Seri No ile)</li>
                </ul>
            </div>

            <!-- Kişi Çözümleri Kategorisi -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-user-cog"></i> KİŞİ ÇÖZÜMLERİ
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('adsoyadpro', 'adsoyadpro')"><i class="fas fa-map-pin"></i> Ad+Soyad+İl Sorgula</li>
                    <li class="query-item" onclick="goToQuery('ailepro', 'ailepro')"><i class="fas fa-users"></i> TC ile Aile Sorgula</li>
                    <li class="query-item" onclick="goToQuery('adres', 'adres')"><i class="fas fa-home"></i> TC ile Adres Sorgula</li>
                    <li class="query-item" onclick="goToQuery('iban', 'iban')"><i class="fas fa-university"></i> IBAN Sorgula</li>
                    <li class="query-item" onclick="goToQuery('operator', 'operator')"><i class="fas fa-signal"></i> Güncel Operatör Sorgula</li>
                </ul>
            </div>

            <!-- Kimlik Sorguları -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-id-card"></i> KİMLİK SORGULA
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('isegiris', 'ad')"><i class="fas fa-briefcase"></i> İşe Giriş Sorgula</li>
                    <li class="query-item" onclick="goToQuery('ikametgah', 'ad')"><i class="fas fa-home"></i> İkametgah Sorgula</li>
                    <li class="query-item" onclick="goToQuery('ailebirey', 'ad')"><i class="fas fa-users"></i> Aile Bireyi Sorgula</li>
                    <li class="query-item" onclick="goToQuery('medenicinsiyet', 'ad')"><i class="fas fa-venus-mars"></i> Medeni Hal / Cinsiyet</li>
                </ul>
            </div>
            
            <!-- TC Sorguları -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-id-card"></i> TC SORGULARI
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('tc-isegiris', 'tc')"><i class="fas fa-briefcase"></i> TC ile İşe Giriş</li>
                    <li class="query-item" onclick="goToQuery('tc-ikametgah', 'tc')"><i class="fas fa-home"></i> TC ile İkametgah</li>
                    <li class="query-item" onclick="goToQuery('tc-ailebirey', 'tc')"><i class="fas fa-users"></i> TC ile Aile Bireyi</li>
                    <li class="query-item" onclick="goToQuery('tc-medenicinsiyet', 'tc')"><i class="fas fa-venus-mars"></i> TC ile Medeni Hal</li>
                    <li class="query-item" onclick="goToQuery('tc', 'tc')"><i class="fas fa-search"></i> TC ile Detaylı Sorgula</li>
                </ul>
            </div>
            
            <!-- GSM Sorguları -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-phone-alt"></i> GSM SORGULARI
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('gsm', 'gsm')"><i class="fas fa-phone"></i> Telefon Numarası Sorgula</li>
                    <li class="query-item" onclick="goToQuery('gsm2', 'gsm')"><i class="fas fa-phone"></i> Telefon Sorgula (Alternatif)</li>
                </ul>
            </div>
            
            <!-- Plaka Sorguları -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-car"></i> PLAKA SORGULARI
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('plaka', 'plaka')"><i class="fas fa-car"></i> Plaka Sorgula</li>
                    <li class="query-item" onclick="goToQuery('plaka_adsoyad', 'plaka_adsoyad')"><i class="fas fa-user"></i> Plaka Ad Soyad ile</li>
                    <li class="query-item" onclick="goToQuery('plaka_ad', 'plaka_ad')"><i class="fas fa-user"></i> Plaka Ad ile</li>
                </ul>
            </div>
            
            <!-- Aile Sorguları -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-users"></i> AİLE SORGULARI
                    <i class="fas fa-chevron-down arrow"></i>
                </div>
                <ul class="query-list">
                    <li class="query-item" onclick="goToQuery('aile', 'tc')"><i class="fas fa-users"></i> Aile Sorgula (TC ile)</li>
                    <li class="query-item" onclick="goToQuery('sulale', 'tc')"><i class="fas fa-tree"></i> Sülale Sorgula (TC ile)</li>
                    <li class="query-item" onclick="goToQuery('hane', 'tc')"><i class="fas fa-home"></i> Hane Sorgula (TC ile)</li>
                    <li class="query-item" onclick="goToQuery('isyeri', 'tc')"><i class="fas fa-briefcase"></i> İşyeri Sorgula (TC ile)</li>
                </ul>
            </div>
            
            <!-- Ad Soyad Sorguları -->
            <div class="category-block">
                <div class="category-header" onclick="toggleCategory(this)">
                    <i class="fas fa-user"></i> AD SOYAD SORGULA
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
                <i class="fas fa-sign-out-alt"></i> ÇIKIŞ YAP
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
                <div class="stat-item"><div class="stat-value">40+</div><div class="stat-label">API</div></div>
                <div class="stat-item"><div class="stat-value">60s</div><div class="stat-label">Timeout</div></div>
            </div>
            <p style="margin-top:20px; color:#ffaa00; text-shadow:0 0 15px #ffaa00; font-weight:600; letter-spacing:1px;">🔥 YENİ NÜFUS, SAĞLIK VE ADLİ API'LER EKLENDİ!</p>
            {% else %}
            <p style="margin-top:20px; color:#fbbf24; font-weight:600;">🔒 Sorgu için kurucu ile iletişime geçin</p>
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
            background:#050508;
            display:flex;
            align-items:center;
            justify-content:center;
            padding:20px;
            position:relative;
        }
        body::before {
            content:'';
            position:fixed;
            top:0; left:0; width:100%; height:100%;
            background:url('https://i.ibb.co/Ldc4b2YF/file-00000000f190720cb7f53c717d6f458d.png') no-repeat center center fixed;
            background-size:cover;
            opacity:0.1;
            z-index:0;
        }
        .login-box {
            position:relative;
            z-index:1;
            width:100%;
            max-width:420px;
            background:#0d0d15;
            border-radius:32px;
            padding:40px 25px;
            border:1px solid rgba(255,255,255,0.02);
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
            background:#050508;
            border:1px solid rgba(255,255,255,0.05);
            border-radius:18px;
            color:white;
            font-size:16px;
            outline:none;
        }
        .form-group input:focus { border-color:#3b82f6; }
        .login-btn {
            width:100%;
            padding:18px;
            background:#3b82f6;
            border:none;
            border-radius:24px;
            color:white;
            font-size:18px;
            font-weight:600;
            cursor:pointer;
            transition:0.2s;
        }
        .login-btn:hover { transform:scale(1.02); background:#2563eb; }
        .register-link {
            text-align:center;
            margin-top:28px;
            color:#a0a0ab;
        }
        .register-link a { color:#3b82f6; text-decoration:none; }
        .error {
            background:rgba(239,68,68,0.1);
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
            background:#050508;
            display:flex;
            align-items:center;
            justify-content:center;
            padding:20px;
            position:relative;
        }
        body::before {
            content:'';
            position:fixed;
            top:0; left:0; width:100%; height:100%;
            background:url('https://i.ibb.co/Ldc4b2YF/file-00000000f190720cb7f53c717d6f458d.png') no-repeat center center fixed;
            background-size:cover;
            opacity:0.1;
            z-index:0;
        }
        .register-box {
            position:relative;
            z-index:1;
            width:100%;
            max-width:420px;
            background:#0d0d15;
            border-radius:32px;
            padding:40px 25px;
            border:1px solid rgba(255,255,255,0.02);
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
            background:#050508;
            border:1px solid rgba(255,255,255,0.05);
            border-radius:18px;
            color:white;
            font-size:16px;
            outline:none;
        }
        .form-group input:focus { border-color:#10b981; }
        .register-btn {
            width:100%;
            padding:18px;
            background:#10b981;
            border:none;
            border-radius:24px;
            color:white;
            font-size:18px;
            font-weight:600;
            cursor:pointer;
            transition:0.2s;
        }
        .register-btn:hover { transform:scale(1.02); background:#059669; }
        .login-link {
            text-align:center;
            margin-top:28px;
            color:#a0a0ab;
        }
        .login-link a { color:#10b981; text-decoration:none; }
        .error {
            background:rgba(239,68,68,0.1);
            border:1px solid #ef4444;
            border-radius:18px;
            padding:14px;
            color:#fca5a5;
            margin-bottom:20px;
        }
        .success {
            background:rgba(16,185,129,0.1);
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
            background:#050508;
            min-height:100vh;
            color:white;
        }
        .navbar {
            background:#0d0d15;
            border-bottom:1px solid rgba(255,255,255,0.02);
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
            color:#a0a0ab;
            text-decoration:none;
            padding:6px 12px;
            border-radius:30px;
            transition:0.2s;
            font-size:14px;
        }
        .nav-link:hover { background:rgba(255,255,255,0.03); color:white; }
        .nav-link.active { background:#3b82f6; color:white; }
        .user-info {
            display:flex;
            align-items:center;
            gap:10px;
            background:rgba(255,255,255,0.02);
            padding:5px 10px 5px 15px;
            border-radius:40px;
            font-size:13px;
            border:1px solid rgba(255,255,255,0.02);
        }
        .role-badge {
            background:rgba(251,191,36,0.1);
            color:#fbbf24;
            padding:3px 8px;
            border-radius:30px;
            font-size:11px;
            font-weight:600;
            border:1px solid rgba(251,191,36,0.2);
        }
        .role-badge.vip { background:rgba(139,92,246,0.1); color:#8b5cf6; border-color:rgba(139,92,246,0.2); }
        .role-badge.kurucu { background:rgba(239,68,68,0.1); color:#ef4444; border-color:rgba(239,68,68,0.2); }
        .container {
            max-width:1400px;
            margin:20px auto;
            padding:0 15px;
        }
        .query-box {
            background:#0d0d15;
            border-radius:24px;
            padding:20px;
            border:1px solid rgba(255,255,255,0.02);
            margin-bottom:20px;
        }
        .query-title { margin-bottom:15px; }
        .query-title h2 { color:#3b82f6; font-size:20px; }
        .param-group { margin-bottom:15px; }
        .param-group label {
            display:block;
            color:#a0a0ab;
            margin-bottom:5px;
            font-size:14px;
        }
        .param-group input {
            width:100%;
            padding:12px 15px;
            background:#050508;
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
            border:1px solid rgba(245,158,11,0.2);
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
            background:#0d0d15;
            border-radius:24px;
            padding:15px;
            border:1px solid rgba(255,255,255,0.02);
            overflow-x:auto;
        }
        .result-table {
            width:100%;
            border-collapse:collapse;
            font-size:12px;
        }
        .result-table th {
            background:#050508;
            color:white;
            padding:8px;
            text-align:left;
            position:sticky;
            top:0;
            font-size:12px;
            border-bottom:1px solid rgba(255,255,255,0.05);
        }
        .result-table td {
            padding:6px 8px;
            border-bottom:1px solid rgba(255,255,255,0.02);
            color:#a0a0ab;
            white-space: nowrap;
            font-size:12px;
        }
        .result-table tr:hover { background:rgba(59,130,246,0.05); }
        .loading {
            text-align:center;
            padding:30px;
            color:#3b82f6;
        }
        .error-box {
            background:rgba(239,68,68,0.1);
            border:1px solid rgba(239,68,68,0.2);
            border-radius:20px;
            padding:20px;
            text-align:center;
            color:#fca5a5;
        }
        .record-count {
            background:#050508;
            padding:6px 12px;
            border-radius:20px;
            margin-bottom:15px;
            display:inline-block;
            font-size:13px;
            color:#a0a0ab;
            border:1px solid rgba(255,255,255,0.02);
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
            
            <div class="param-group">
                <label>TC Kimlik No</label>
                <input type="text" id="tc" placeholder="11 haneli TC" maxlength="11">
            </div>
            
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
            const tc = document.getElementById('tc')?.value;
            if (!tc || tc.length !== 11) { 
                alert('11 haneli TC giriniz'); 
                return; 
            }
            
            const url = `/api/${endpoint}?tc=${tc}`;
            
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
                
                if (data.error) {
                    html = `<div class="error-box"><h3>Hata</h3><p>${data.error}</p></div>`;
                } else {
                    // Ortak alanları göster
                    html += '<div style="background:#0a0a12; padding:15px; border-radius:12px; margin-bottom:20px;">';
                    html += '<h4 style="color:#3b82f6; margin-bottom:15px;">👤 KİŞİ BİLGİLERİ</h4>';
                    html += '<div style="display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:10px;">';
                    
                    const commonFields = [
                        {key:'tc', label:'TC'}, {key:'ad', label:'Ad'}, {key:'soyad', label:'Soyad'},
                        {key:'dogumTarihi', label:'Doğum Tarihi'}, {key:'dogumYeri', label:'Doğum Yeri'},
                        {key:'babaAdi', label:'Baba Adı'}, {key:'anneAdi', label:'Anne Adı'},
                        {key:'cinsiyet', label:'Cinsiyet'}, {key:'il', label:'İl'}, {key:'ilce', label:'İlçe'},
                        {key:'mahalle', label:'Mahalle'}, {key:'sokak', label:'Sokak'},
                        {key:'kapiNo', label:'Kapı No'}, {key:'daireNo', label:'Daire No'},
                        {key:'telefon', label:'Telefon'}
                    ];
                    
                    commonFields.forEach(field => {
                        if (data[field.key] && data[field.key] !== '-') {
                            html += `<div><span style="color:#a0a0ab; font-size:11px;">${field.label}:</span> <span style="color:#fff; font-size:13px; font-weight:500;">${data[field.key]}</span></div>`;
                        }
                    });
                    
                    html += '</div></div>';
                    
                    // Diğer alanları işle
                    for (let key in data) {
                        if (commonFields.some(f => f.key === key) || key.startsWith('_') || !data[key]) continue;
                        
                        const displayKey = key.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').replace(/adi/g, ' Adı').replace(/soyadi/g, ' Soyadı').toUpperCase();
                        
                        if (Array.isArray(data[key]) && data[key].length > 0) {
                            // Array ise tablo yap
                            html += `<h4 style="color:#ffaa00; margin:20px 0 10px 0;">📋 ${displayKey}</h4>`;
                            
                            // Tablo başlıklarını bul
                            const allKeys = new Set();
                            data[key].forEach(item => {
                                if (typeof item === 'object') {
                                    Object.keys(item).forEach(k => {
                                        if (item[k] && item[k] !== '-') allKeys.add(k);
                                    });
                                }
                            });
                            
                            if (allKeys.size > 0) {
                                const headers = Array.from(allKeys);
                                html += '<div style="overflow-x: auto;"><table class="result-table">';
                                html += '<tr>';
                                headers.forEach(h => {
                                    const hDisplay = h.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').toUpperCase();
                                    html += `<th style="background:#050508; padding:8px;">${hDisplay}</th>`;
                                });
                                html += '</tr>';
                                
                                data[key].forEach(item => {
                                    if (typeof item === 'object') {
                                        html += '<tr>';
                                        headers.forEach(h => {
                                            let value = item[h] || '-';
                                            if (typeof value === 'object') value = JSON.stringify(value);
                                            html += `<td style="padding:8px;">${value}</td>`;
                                        });
                                        html += '</tr>';
                                    }
                                });
                                html += '</table></div>';
                            }
                        } else if (typeof data[key] === 'object' && data[key] !== null) {
                            // Nesne ise iç içe göster
                            html += `<h4 style="color:#ffaa00; margin:20px 0 10px 0;">📌 ${displayKey}</h4>`;
                            html += '<div style="background:#0a0a12; padding:15px; border-radius:12px;">';
                            
                            const obj = data[key];
                            for (let k in obj) {
                                if (obj[k] && obj[k] !== '-') {
                                    const kDisplay = k.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').toUpperCase();
                                    html += `<div style="display:flex; margin-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.02); padding-bottom:5px;">`;
                                    html += `<span style="width:150px; color:#a0a0ab; font-size:11px;">${kDisplay}:</span>`;
                                    html += `<span style="color:#fff; font-size:12px;">${obj[k]}</span>`;
                                    html += '</div>';
                                }
                            }
                            html += '</div>';
                        } else {
                            // Tekil değer
                            html += `<div style="background:#0a0a12; padding:15px; border-radius:12px; margin-bottom:10px;">`;
                            html += `<div style="display:flex;"><span style="width:150px; color:#a0a0ab; font-size:11px;">${displayKey}:</span>`;
                            html += `<span style="color:#fff; font-size:12px;">${data[key]}</span></div>`;
                            html += '</div>';
                        }
                    }
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

# ========== YENİ API FONKSİYONLARI ==========

BASE_URL = "https://panelapi-vu8c.onrender.com/api/v1"

def fetch_panel_api(endpoint, tc):
    """Panel API'den veri çek"""
    try:
        url = f"{BASE_URL}/{endpoint}?tc={tc}"
        response = requests.get(url, timeout=30)
        data = response.json()
        return fix_dict_turkish_chars(data)
    except Exception as e:
        return {"error": str(e)}

# YENİ API'LER
@app.route('/api/nufus_sorgu')
@vip_required
def api_nufus_sorgu():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "nufus_sorgu",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("nufus/sorgu", tc))

@app.route('/api/asi_kayitlari')
@vip_required
def api_asi_kayitlari():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "asi_kayitlari",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("saglik/asi-kayitlari", tc))

@app.route('/api/rontgen_listesi')
@vip_required
def api_rontgen_listesi():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "rontgen_listesi",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("saglik/rontgen-listesi", tc))

@app.route('/api/recete_gecmisi')
@vip_required
def api_recete_gecmisi():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "recete_gecmisi",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("eczane/recete-gecmisi", tc))

@app.route('/api/adli_sicil')
@vip_required
def api_adli_sicil():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "adli_sicil",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("adli-sicil/kayit", tc))

@app.route('/api/pasaport_sorgu')
@vip_required
def api_pasaport_sorgu():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "pasaport_sorgu",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("pasaport/sorgu", tc))

@app.route('/api/kronik_hastalik')
@vip_required
def api_kronik_hastalik():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "kronik_hastalik",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("saglik/kronik-hastalik", tc))

@app.route('/api/vergi_borc')
@vip_required
def api_vergi_borc():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "vergi_borc",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("vergi/borc-sorgu", tc))

@app.route('/api/tapu_gayrimenkul')
@vip_required
def api_tapu_gayrimenkul():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "tapu_gayrimenkul",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("tapu/gayrimenkul", tc))

@app.route('/api/askerlik_durum')
@vip_required
def api_askerlik_durum():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "askerlik_durum",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("askerlik/durum", tc))

@app.route('/api/su_fatura')
@vip_required
def api_su_fatura():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "su_fatura",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("ibb/su-fatura", tc))

@app.route('/api/elektrik_fatura')
@vip_required
def api_elektrik_fatura():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "elektrik_fatura",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("elektrik/fatura", tc))

@app.route('/api/otel_rezervasyon')
@vip_required
def api_otel_rezervasyon():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "otel_rezervasyon",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("turizm/otel-rezervasyon", tc))

@app.route('/api/istanbulkart_bakiye')
@vip_required
def api_istanbulkart_bakiye():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "istanbulkart_bakiye",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("ulasim/istanbulkart-bakiye", tc))

@app.route('/api/spor_federasyon')
@vip_required
def api_spor_federasyon():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "spor_federasyon",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("spor/federasyon/kayit", tc))

@app.route('/api/kutuphane_uye')
@vip_required
def api_kutuphane_uye():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "kutuphane_uye",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("kutuphane/uye-durum", tc))

@app.route('/api/hasta_yatis_gecmisi')
@vip_required
def api_hasta_yatis_gecmisi():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "hasta_yatis_gecmisi",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("saglik/hasta-yatis-gecmisi", tc))

@app.route('/api/dijital_banka')
@vip_required
def api_dijital_banka():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "dijital_banka",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("dijital/banka-musteri", tc))

@app.route('/api/kredi_risk_raporu')
@vip_required
def api_kredi_risk_raporu():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "kredi_risk_raporu",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("kredi/risk-raporu", tc))

@app.route('/api/meb_mezuniyet')
@vip_required
def api_meb_mezuniyet():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "meb_mezuniyet",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("meb/mezuniyet", tc))

@app.route('/api/ticaret_sikayet')
@vip_required
def api_ticaret_sikayet():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "ticaret_sikayet",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("ticaret/sikayet-kaydi", tc))

@app.route('/api/sehirlerarasi_ceza')
@vip_required
def api_sehirlerarasi_ceza():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "sehirlerarasi_ceza",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("cevre/sehirlerarasi-ceza", tc))

@app.route('/api/noter_islem')
@vip_required
def api_noter_islem():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "noter_islem",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("noter/gereceklesen-islem", tc))

@app.route('/api/ormancilik_avci')
@vip_required
def api_ormancilik_avci():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "ormancilik_avci",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("ormancilik/avci-lisans", tc))

@app.route('/api/ucak_bilet')
@vip_required
def api_ucak_bilet():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "ucak_bilet",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("udhb/ucak-bilet", tc))

@app.route('/api/seyahat_hareket')
@vip_required
def api_seyahat_hareket():
    tc = request.args.get('tc', '')
    if not tc or len(tc) != 11:
        return jsonify({'error': 'Geçerli TC girin'})
    
    user = get_current_user()
    if user:
        queries_collection.insert_one({
            "user": user['email'],
            "endpoint": "seyahat_hareket",
            "params": request.args.to_dict(),
            "timestamp": datetime.now()
        })
    
    return jsonify(fetch_panel_api("mzk/seyahat-hareket", tc))

# MEVCUT API'LER (Korundu)
def fetch_adsoyadpro(ad, soyad, il=None):
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

# ========== MEVCUT API ENDPOINT'LERİ ==========
@app.route('/api/<endpoint>')
@vip_required
def api_endpoint_old(endpoint):
    """Eski API endpoint'leri"""
    
    user = get_current_user()
    
    # YENİ API'ler zaten ayrı route'lar üzerinden geliyor
    if endpoint in ['adsoyadpro', 'ailepro', 'adres', 'iban', 'operator', 
                    'plaka_adsoyad', 'plaka_ad', 'papara_no', 'papara_ad',
                    'vergi_isim', 'vergi_no', 'vergi_detay', 'serino_tc',
                    'serino_ad', 'serino_adsoyad', 'serino_seri']:
        
        # Parametreleri al
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
            return jsonify(fetch_ailepro(tc))
        
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
            return jsonify(fetch_adres(tc))
        
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
            return jsonify(fetch_iban(iban))
        
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
            return jsonify(fetch_operator(telefon))
        
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
            return jsonify(fetch_plaka_adsoyad(ad, soyad))
        
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
            return jsonify(fetch_plaka_ad(ad))
        
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
            return jsonify(fetch_papara_no(paparano))
        
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
            return jsonify(fetch_papara_ad(ad, soyad))
        
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
            return jsonify(fetch_vergi_isim(isim))
        
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
            return jsonify(fetch_vergi_no(vergi_no))
        
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
            return jsonify(fetch_vergi_detay(ilce, vergi_dairesi))
        
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
            return jsonify(fetch_serino_tc(tc))
        
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
            return jsonify(fetch_serino_ad(ad))
        
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
            return jsonify(fetch_serino_adsoyad(ad, soyad))
        
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
            return jsonify(fetch_serino_seri(seri_no))
    
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
    endpoint = request.args.get('endpoint', 'nufus_sorgu')
    query_type = request.args.get('type', 'tc')
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
    print("📱 MOBİL UYUMLU: Menü 280px, dark panel teması")
    print("🔥 YENİ: 25+ YENİ API EKLENDİ!")
    print("   • Nüfus Sorgulama")
    print("   • Aşı Kayıtları")
    print("   • Röntgen Listesi")
    print("   • Reçete Geçmişi")
    print("   • Adli Sicil")
    print("   • Pasaport Sorgulama")
    print("   • Vergi Borç")
    print("   • Tapu Gayrimenkul")
    print("   • Askerlik Durumu")
    print("   • Fatura Sorgulamaları")
    print("   • Ulaşım ve Seyahat")
    print("   • Ve daha fazlası...")
    print("\n🌐 http://localhost:5000")
    print("="*60)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)
