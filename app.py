from flask import Flask
from config import Config
import os

# Importação das rotas
from routes.main_routes import configure_main_routes
from routes.auth_routes import configure_auth_routes
from routes.empresa_routes import configure_empresa_routes
from routes.admin_routes import configure_admin_routes
from routes.produto_routes import configure_produto_routes
from routes.carrinho_routes import configure_carrinho_routes
from routes.avaliacao_routes import avaliacao_bp

# Importação de utilitários
from utils.helpers import from_json_filter

def create_app():
    # Cria a instância do Flask definindo pastas de template e estáticos
    app = Flask(__name__, template_folder="view", static_folder="static")
    app.config.from_object(Config)
    
    # Filtros do Jinja
    app.jinja_env.filters['from_json'] = from_json_filter
    
    # --- REGISTRO DAS ROTAS PRINCIPAIS ---
    configure_main_routes(app)
    configure_auth_routes(app)
    configure_empresa_routes(app)
    configure_admin_routes(app)
    configure_produto_routes(app)
    configure_carrinho_routes(app)
    
    # --- REGISTRO DO BLUEPRINT DE AVALIAÇÕES ---
    # Isso cria automaticamente a rota /minhas-avaliacoes-pendentes definida no blueprint
    app.register_blueprint(avaliacao_bp)

    # Cria pasta de uploads se não existir
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    
    return app

# Cria a variável 'app' globalmente chamando a fábrica
# Isso permite que servidores WSGI (como Gunicorn) encontrem o app
app = create_app()

if __name__ == '__main__':
    # Importações de banco de dados aqui para evitar ciclo
    from models.database import criar_tabelas_necessarias, criar_admin_padrao
    
    print("=" * 60)
    print("🚀 Loja GHCP - Sistema Iniciado")
    print("=" * 60)
    
    with app.app_context():
        criar_tabelas_necessarias()
        criar_admin_padrao()   
    
    print("✅ Servidor Flask rodando!")
    print(f"🌐 Site: http://localhost:5000")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)