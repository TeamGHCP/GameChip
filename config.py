import os
from datetime import timedelta

class Config:
    # ⚠️ RECOMENDAÇÃO DE SEGURANÇA: Usar variáveis de ambiente para chaves sensíveis
    SECRET_KEY = os.environ.get('SECRET_KEY', 'GHCP-2o25')
    
    # Database Configuration - Usar variáveis de ambiente em produção
    DB_CONFIG = {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'port': os.environ.get('DB_PORT', '3306'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', ''),
        'database': os.environ.get('DB_NAME', 'loja_informatica')
    }
    
    # Upload Configuration
    UPLOAD_FOLDER = 'static/uploads/produtos'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Session Configuration
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    
    # PIX Configuration
    PIX_CHAVE = os.environ.get('PIX_CHAVE', "14057629939")
    PIX_NOME = os.environ.get('PIX_NOME', "CAETANO GBUR PETRY")
    PIX_CIDADE = os.environ.get('PIX_CIDADE', "JOINVILLE")

    # CONFIGURAÇÕES DE EMAIL
    MAIL_SERVER = 'smtp.gmail.com'  # Para Gmail
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    MAIL_USERNAME = 'contatoghcp@gmail.com'  # Seu email
    MAIL_PASSWORD = ' igho jvfm czce bzfb'  # Senha de app (NÃO use a senha normal)
    MAIL_DEFAULT_SENDER = 'contatoghcp@gmail.com'
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False
    
    # Para Hotmail/Outlook use:
    # MAIL_SERVER = 'smtp.office365.com'
    # MAIL_PORT = 587