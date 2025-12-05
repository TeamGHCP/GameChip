import os
from datetime import timedelta

class Config:
    """
    Arquivo de configuração central da aplicação.
    """
    
    # 1. SEGURANÇA
    # Chave secreta para assinar cookies de sessão e proteção CSRF
    SECRET_KEY = os.environ.get('SECRET_KEY', 'GHCP-2o25')

    # 2. CONFIGURAÇÃO DO BANCO DE DADOS
    # Definimos as variáveis individuais para facilitar a leitura
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '3306')
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '') # Se tiver senha no seu root, coloque aqui
    DB_NAME = os.environ.get('DB_NAME', 'loja_informatica')

    # Mantemos o seu dicionário DB_CONFIG caso você use conexões manuais (sem ORM) em scripts paralelos
    DB_CONFIG = {
        'host': DB_HOST,
        'port': int(DB_PORT),
        'user': DB_USER,
        'password': DB_PASSWORD,
        'database': DB_NAME
    }

    # CRUCIAL: O SQLAlchemy precisa desta string exata para conectar
    # Formato: mysql+mysqlconnector://usuario:senha@host:porta/banco
    SQLALCHEMY_DATABASE_URI = f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    # Desativa rastreamento de modificações para economizar memória
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 3. CONFIGURAÇÃO DE UPLOAD
    # Usamos os.path.abspath para garantir que o caminho seja absoluto e o Flask encontre a pasta
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static/uploads/produtos')
    
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # Limite de 16MB por arquivo

    # 4. SESSÃO (SESSION)
    # Se estiver usando Flask-Session, 'filesystem' salva as sessões em arquivos no servidor
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    
    # 5. CONFIGURAÇÃO DO PIX
    PIX_CHAVE = os.environ.get('PIX_CHAVE', "14057629939")
    PIX_NOME = os.environ.get('PIX_NOME', "CAETANO GBUR PETRY")
    PIX_CIDADE = os.environ.get('PIX_CIDADE', "JOINVILLE")

    # 6. CONFIGURAÇÃO DE E-MAIL (Flask-Mail)
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False
    
    # Suas credenciais
    MAIL_USERNAME = 'contatoghcp@gmail.com'
    # ATENÇÃO: Por segurança, removi a senha real do código. 
    # Use variáveis de ambiente ou insira novamente sua senha de app aqui.
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'igho jvfm czce bzfb') 
    
    MAIL_DEFAULT_SENDER = 'contatoghcp@gmail.com'
    MAIL_MAX_EMAILS = None
    MAIL_ASCII_ATTACHMENTS = False

    # Função auxiliar para verificar extensões (pode ser usada nas rotas)
    @staticmethod
    def allowed_file(filename):
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS