from flask import render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models.database import get_db_connection
from utils.decorators import admin_required, permission_required, PERMISSIONS
import mysql.connector
import json
import uuid
import math
from flask import send_from_directory
from io import StringIO 
import csv
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from config import Config

def configure_admin_routes(app):
    
    # Função auxiliar para verificar arquivos permitidos
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

        # Função auxiliar para gerar nome único para arquivos PDF
    def gerar_nome_arquivo(nome_original, vaga_nome=""):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_base = secure_filename(nome_original)
        nome_arquivo = f"{timestamp}_{vaga_nome[:20]}_{nome_base}" if vaga_nome else f"{timestamp}_{nome_base}"
        return nome_arquivo
    
    # Função para criar pasta de uploads se não existir
    def criar_pasta_uploads():
        pasta_curriculos = os.path.join(app.root_path, 'static', 'uploads', 'curriculos')
        pasta_mensal = os.path.join(pasta_curriculos, datetime.now().strftime("%Y_%m"))
        
        if not os.path.exists(pasta_mensal):
            os.makedirs(pasta_mensal, exist_ok=True)
        
        return pasta_mensal
    
    @app.route('/fix-admin')
    def fix_admin():
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 1. Gera o hash da senha "123"
            senha_hash = generate_password_hash("admin") 
            
            # 2. Verifica se o usuário já existe para evitar erro de duplicidade
            cursor.execute("SELECT id_funcionario FROM funcionarios WHERE email = 'admin@gamechip.com'")
            if cursor.fetchone():
                # Se já existe, apenas atualiza a senha
                cursor.execute(f"""
                    UPDATE funcionarios 
                    SET senha = '{senha_hash}', ativo = 1, cargo = 'admin'
                    WHERE email = 'admin@gmail.com'
                """)
                msg = "Usuário admin@gamechip.com já existia. Senha resetada para 123."
            else:
                # Se não existe, cria do zero (COM ASPAS NA SENHA)
                cursor.execute(f"""
                    INSERT INTO funcionarios (nome, email, senha, cargo, ativo) 
                    VALUES ('Admin Supremo', 'admin@gmail.com', '{senha_hash}', 'admin', 1)
                """)
                msg = "Usuário admin@gmail.com criado com sucesso! Senha: admin"
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return f"<h1>Sucesso!</h1> <p>{msg}</p> <a href='/admin/login'>Ir para Login</a>"
            
        except Exception as e:
            return f"<h1>Erro:</h1> {e}"
    
    # Função para verificar se é LinkedIn válido
    def validar_linkedin(url):
        if not url:
            return True
        url = url.lower().strip()
        return url.startswith(('https://linkedin.com/', 'http://linkedin.com/', 
                             'https://www.linkedin.com/', 'http://www.linkedin.com/'))
    
    # Função para listar vagas únicas para filtros
    def obter_vagas_unicas():
        try:
            conn = get_db_connection()
            if not conn:
                return []
            
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT vaga FROM concorrentes WHERE vaga IS NOT NULL AND vaga != '' ORDER BY vaga")
            vagas = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            return vagas
        except:
            return []
        
    # Context processor para injetar user_cargo em todos os templates
    @app.context_processor
    def inject_user_cargo():
        return dict(user_cargo=session.get('admin_cargo', '').lower())

    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            senha = request.form.get('senha', '')
            if not email or not senha:
                flash('❌ Preencha todos os campos.', 'error')
                return render_template('admin/login.html')
            try:
                conn = get_db_connection()
                if not conn:
                    flash('Erro ao conectar ao banco de dados.', 'error')
                    return render_template('admin/login.html')
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM funcionarios WHERE email = %s AND ativo = TRUE", (email,))
                admin = cursor.fetchone()
                if admin and check_password_hash(admin['senha'], senha):
                    session['admin_id'] = admin['id_funcionario']
                    session['admin_nome'] = admin['nome']
                    session['admin_cargo'] = admin['cargo']
                    cursor.execute("UPDATE funcionarios SET ultimo_login = NOW() WHERE id_funcionario = %s", (admin['id_funcionario'],))
                    conn.commit()
                    flash(f'🎉 Bem-vindo, {admin["nome"]}!', 'success')
                    return redirect(url_for('admin_dashboard'))
                else:
                    flash('❌ Credenciais inválidas.', 'error')
            except mysql.connector.Error as err:
                flash(f'Erro ao fazer login: {err}', 'error')
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()
        return render_template('admin/login.html')

    @app.route('/admin/logout')
    def admin_logout():
        session.pop('admin_id', None)
        session.pop('admin_nome', None)
        session.pop('admin_cargo', None)
        flash('👋 Logout realizado com sucesso!', 'info')
        return redirect(url_for('admin_login'))

    @app.route('/admin/dashboard')
    @admin_required
    def admin_dashboard():
        user_cargo = session.get('admin_cargo', '').lower()
        
        total_clientes = 0
        total_produtos = 0
        pedidos_hoje = 0
        receita_hoje = 0
        diagnosticos_pendentes = 0
        estoque_baixo = []
        pedidos_recentes = []
        diagnosticos_recentes = []
        
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('admin/dashboard.html', 
                                     total_clientes=total_clientes,
                                     total_produtos=total_produtos,
                                     pedidos_hoje=pedidos_hoje,
                                     receita_hoje=receita_hoje,
                                     diagnosticos_pendentes=diagnosticos_pendentes,
                                     estoque_baixo=estoque_baixo,
                                     pedidos_recentes=pedidos_recentes,
                                     diagnosticos_recentes=diagnosticos_recentes,
                                     user_cargo=user_cargo)
            
            cursor = conn.cursor(dictionary=True)
            
            # Consulta para total de produtos (todos os cargos podem ver)
            cursor.execute("SELECT COUNT(*) as total FROM produto WHERE ativo = TRUE")
            total_produtos = cursor.fetchone()['total']
            
            # Consulta para total de clientes (admin, gerente, vendedor)
            if user_cargo in ['admin', 'gerente', 'vendedor']:
                cursor.execute("SELECT COUNT(*) as total FROM clientes WHERE ativo = TRUE")
                total_clientes = cursor.fetchone()['total']
            
            # Consulta para pedidos de hoje (admin, gerente, vendedor)
            if user_cargo in ['admin', 'gerente', 'vendedor']:
                # 🔥 CORREÇÃO: Usando NOT IN para excluir cancelado/pendente da contagem de pedidos finalizados
                cursor.execute("SELECT COUNT(*) as total FROM pedidos WHERE DATE(data_pedido) = CURDATE() AND status NOT IN ('cancelado', 'pendente')")
                pedidos_hoje = cursor.fetchone()['total']
            
            # Consulta para receita de hoje (admin, gerente, vendedor)
            if user_cargo in ['admin', 'gerente', 'vendedor']:
                # 🔥 CORREÇÃO: Usando NOT IN para receita finalizada
                cursor.execute("SELECT SUM(total) as total FROM pedidos WHERE DATE(data_pedido) = CURDATE() AND status NOT IN ('cancelado', 'pendente')")
                receita_result = cursor.fetchone()
                receita_hoje = receita_result['total'] or 0
            
            # Consulta para diagnósticos pendentes (admin, gerente, suporte)
            if user_cargo in ['admin', 'gerente', 'suporte']:
                try:
                    cursor.execute("SELECT COUNT(*) as total FROM diagnosticos WHERE status = 'recebido' OR status = 'em_analise'")
                    diagnosticos_pendentes = cursor.fetchone()['total']
                except mysql.connector.Error:
                    diagnosticos_pendentes = 0
            
            # Consulta para estoque baixo (admin, gerente, vendedor)
            if user_cargo in ['admin', 'gerente', 'vendedor']:
                try:
                    cursor.execute("SELECT * FROM produto WHERE estoque <= 5 AND ativo = TRUE ORDER BY estoque ASC LIMIT 5")
                    estoque_baixo = cursor.fetchall()
                except mysql.connector.Error:
                    estoque_baixo = []
            
            # Consulta para pedidos recentes (admin, gerente, vendedor)
            if user_cargo in ['admin', 'gerente', 'vendedor']:
                try:
                    # 🔥 CORREÇÃO: Usando NOT IN para pedidos finalizados
                    cursor.execute("SELECT p.*, c.nome as cliente_nome FROM pedidos p JOIN clientes c ON p.id_cliente = c.id_cliente WHERE p.status NOT IN ('cancelado', 'pendente') ORDER BY p.data_pedido DESC LIMIT 5")
                    pedidos_recentes = cursor.fetchall()
                except mysql.connector.Error:
                    pedidos_recentes = []
            
            # Consulta para diagnósticos recentes (admin, gerente, suporte)
            if user_cargo in ['admin', 'gerente', 'suporte']:
                try:
                    cursor.execute("SELECT * FROM diagnosticos ORDER BY data_entrada DESC LIMIT 5")
                    diagnosticos_recentes = cursor.fetchall()
                except mysql.connector.Error:
                    diagnosticos_recentes = []
            
            return render_template('admin/dashboard.html', 
                                 total_clientes=total_clientes,
                                 total_produtos=total_produtos,
                                 pedidos_hoje=pedidos_hoje,
                                 receita_hoje=receita_hoje,
                                 diagnosticos_pendentes=diagnosticos_pendentes,
                                 estoque_baixo=estoque_baixo,
                                 pedidos_recentes=pedidos_recentes,
                                 diagnosticos_recentes=diagnosticos_recentes,
                                 user_cargo=user_cargo)
                                 
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar dashboard: {err}', 'error')
            return render_template('admin/dashboard.html', 
                                 total_clientes=total_clientes,
                                 total_produtos=total_produtos,
                                 pedidos_hoje=pedidos_hoje,
                                 receita_hoje=receita_hoje,
                                 diagnosticos_pendentes=diagnosticos_pendentes,
                                 estoque_baixo=estoque_baixo,
                                 pedidos_recentes=pedidos_recentes,
                                 diagnosticos_recentes=diagnosticos_recentes,
                                 user_cargo=user_cargo)
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    # PRODUTOS - Admin, Gerente e Vendedor (apenas visualização)
    @app.route('/admin/produtos')
    @permission_required(['admin', 'gerente', 'vendedor'])
    def admin_produtos():
        user_cargo = session.get('admin_cargo', '').lower()
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('admin/produtos.html', produtos=[], user_cargo=user_cargo)
            cursor = conn.cursor(dictionary=True)
            categoria = request.args.get('categoria')
            busca = request.args.get('busca')
            query = "SELECT * FROM produto WHERE 1=1"
            params = []
            if categoria:
                query += " AND categoria = %s"
                params.append(categoria)
            if busca:
                query += " AND (nome LIKE %s OR marca LIKE %s)"
                params.extend([f"%{busca}%", f"%{busca}%"])
            query += " ORDER BY data_cadastro DESC"
            cursor.execute(query, params)
            produtos = cursor.fetchall()
            cursor.execute("SELECT DISTINCT categoria FROM produto ORDER BY categoria")
            categorias = [row['categoria'] for row in cursor.fetchall()]
            return render_template('admin/produtos.html', produtos=produtos, categorias=categorias, user_cargo=user_cargo)
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar produtos: {err}', 'error')
            return render_template('admin/produtos.html', produtos=[], user_cargo=user_cargo)
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/admin/produto/novo', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente'])
    def admin_novo_produto():
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            marca = request.form.get('marca', '').strip()
            preco = request.form.get('preco', '0').replace(',', '.')
            descricao = request.form.get('descricao', '').strip()
            estoque = request.form.get('estoque', '0')
            categoria = request.form.get('categoria', '').strip()
            peso = request.form.get('peso', '0').replace(',', '.')
            dimensoes = request.form.get('dimensoes', '').strip()
            destaque = request.form.get('destaque') == 'on'
            
            if not all([nome, marca, preco, categoria]):
                flash('❌ Preencha todos os campos obrigatórios.', 'error')
                return render_template('admin/produto_form.html')
            
            try:
                conn = get_db_connection()
                if not conn:
                    flash('Erro ao conectar ao banco de dados.', 'error')
                    return render_template('admin/produto_form.html')
                
                cursor = conn.cursor()
                
                imagens = []
                if 'imagens' in request.files:
                    files = request.files.getlist('imagens')
                    for file in files:
                        if file and allowed_file(file.filename):
                            filename = secure_filename(file.filename)
                            from uuid import uuid4
                            unique_filename = f"{uuid4().hex}_{filename}"
                            filepath = os.path.join(Config.UPLOAD_FOLDER, unique_filename)
                            os.makedirs(os.path.dirname(filepath), exist_ok=True)
                            file.save(filepath)
                            imagens.append(unique_filename)
                
                cursor.execute("""
                    INSERT INTO produto (nome, marca, preco, descricao, estoque, categoria, imagens, peso, dimensoes, destaque)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (nome, marca, float(preco), descricao, int(estoque), categoria, json.dumps(imagens) if imagens else None,
                      float(peso) if peso else 0, dimensoes, destaque))
                
                conn.commit()
                
                if session.get('admin_id'):
                    try:
                        cursor.execute("""
                            INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                            VALUES (%s, 'CADASTRO', 'PRODUTOS', %s)
                        """, (session['admin_id'], f'Produto cadastrado: {nome}'))
                        conn.commit()
                    except mysql.connector.Error:
                        pass
                
                flash('✅ Produto cadastrado com sucesso!', 'success')
                return redirect(url_for('admin_produtos'))
            
            except mysql.connector.Error as err:
                flash(f'Erro ao cadastrar produto: {err}', 'error')
            
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()
        
        return render_template('admin/produto_form.html')

    # CLIENTES - Admin, Gerente e Vendedor (apenas visualização)
    @app.route('/admin/clientes')
    @permission_required(['admin', 'gerente', 'vendedor'])
    def admin_clientes():
        user_cargo = session.get('admin_cargo', '').lower()
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('admin/clientes.html', clientes=[], user_cargo=user_cargo)
            cursor = conn.cursor(dictionary=True)
            busca = request.args.get('busca')
            query = "SELECT * FROM clientes WHERE 1=1"
            params = []
            if busca:
                query += " AND (nome LIKE %s OR email LIKE %s OR cpf LIKE %s)"
                params.extend([f"%{busca}%", f"%{busca}%", f"%{busca}%"])
            query += " ORDER BY data_cadastro DESC"
            cursor.execute(query, params)
            clientes = cursor.fetchall()
            return render_template('admin/clientes.html', clientes=clientes, user_cargo=user_cargo)
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar clientes: {err}', 'error')
            return render_template('admin/clientes.html', clientes=[], user_cargo=user_cargo)
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    # FUNCIONÁRIOS - Apenas Admin
    @app.route('/admin/funcionarios')
    @permission_required(['admin'])
    def admin_funcionarios():
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('admin/funcionarios.html', funcionarios=[])
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM funcionarios ORDER BY data_cadastro DESC")
            funcionarios = cursor.fetchall()
            return render_template('admin/funcionarios.html', funcionarios=funcionarios)
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar funcionários: {err}', 'error')
            return render_template('admin/funcionarios.html', funcionarios=[])
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    # OFERTAS - Admin e Gerente
    @app.route('/admin/ofertas')
    @permission_required(['admin', 'gerente'])
    def admin_ofertas():
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT o.id_oferta, o.desconto, o.preco_original, o.preco_com_desconto,
                       o.validade, o.ativa, p.nome AS nome_produto
                FROM ofertas o
                JOIN produto p ON o.id_produto = p.id_produto
                ORDER BY o.validade DESC
            """)
            ofertas = cursor.fetchall()
            cursor.close()
            conn.close()
            return render_template('admin/ofertas.html', ofertas=ofertas)
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar ofertas: {err}', 'error')
            return render_template('admin/ofertas.html', ofertas=[])

    @app.route('/admin/concorrentes')
    @permission_required(['admin', 'gerente'])
    def admin_concorrentes():
        try:
            # Import necessário para calcular o total de páginas (ceil)
            import math 
            
            # Obter parâmetros de filtro
            vaga_filtro = request.args.get('vaga', '')
            status_filtro = request.args.get('status', '')
            data_inicio = request.args.get('data_inicio', '')
            data_fim = request.args.get('data_fim', '')
            page = request.args.get('page', 1, type=int)
            per_page = 20  # Itens por página
            
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('admin/concorrentes.html', 
                                    concorrentes=[], 
                                    vagas_unicas=obter_vagas_unicas(),
                                    vaga_filtro=vaga_filtro,
                                    status_filtro=status_filtro,
                                    data_inicio=data_inicio,
                                    data_fim=data_fim,
                                    total_candidatos=0,
                                    contadores={})
            
            cursor = conn.cursor(dictionary=True)
            
            # Construir query com filtros
            query = "SELECT * FROM concorrentes WHERE 1=1"
            params = []
            
            if vaga_filtro:
                query += " AND vaga = %s"
                params.append(vaga_filtro)
            
            if status_filtro:
                query += " AND status = %s"
                params.append(status_filtro)
            
            if data_inicio:
                query += " AND DATE(data_candidatura) >= %s"
                params.append(data_inicio)
            
            if data_fim:
                query += " AND DATE(data_candidatura) <= %s"
                params.append(data_fim)
            
            query += " ORDER BY data_candidatura DESC, data_cadastro DESC"
            
            # Executar query para obter TODOS os concorrentes (para contagem e paginação manual)
            cursor.execute(query, params)
            todos_concorrentes = cursor.fetchall()
            
            # Paginação manual (simples)
            total = len(todos_concorrentes)
            inicio = (page - 1) * per_page
            fim = inicio + per_page
            concorrentes = todos_concorrentes[inicio:fim]
            
            # Cálculo do total de páginas (CORREÇÃO para uso no template)
            total_paginas = math.ceil(total / per_page) if total > 0 else 1
            
            # Calcular estatísticas
            contadores = {
                'pendente': sum(1 for c in todos_concorrentes if c['status'] == 'pendente'),
                'contatado': sum(1 for c in todos_concorrentes if c['status'] == 'contatado'),
                'contratado': sum(1 for c in todos_concorrentes if c['status'] == 'contratado'),
                'com_linkedin': sum(1 for c in todos_concorrentes if c.get('linkedin_url')),
            }
            
            # Obter vagas únicas para filtro
            cursor.execute("SELECT DISTINCT vaga FROM concorrentes WHERE vaga IS NOT NULL AND vaga != '' ORDER BY vaga")
            vagas_unicas = [row['vaga'] for row in cursor.fetchall()]
            
            return render_template('admin/concorrentes.html', 
                                concorrentes=concorrentes,
                                vagas_unicas=vagas_unicas,
                                vaga_filtro=vaga_filtro,
                                status_filtro=status_filtro,
                                data_inicio=data_inicio,
                                data_fim=data_fim,
                                total_candidatos=total,
                                contadores=contadores,
                                # Estrutura de paginação corrigida
                                pagination={
                                    'page': page,
                                    'per_page': per_page,
                                    'total': total,
                                    'pages': total_paginas, # CHAVE PRINCIPAL CORRIGIDA
                                    'has_prev': page > 1,
                                    'has_next': page < total_paginas,
                                    'prev_num': page - 1,
                                    'next_num': page + 1
                                })
            
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar concorrentes: {err}', 'error')
            return render_template('admin/concorrentes.html', 
                                concorrentes=[], 
                                vagas_unicas=[],
                                vaga_filtro='',
                                status_filtro='',
                                data_inicio='',
                                data_fim='',
                                total_candidatos=0,
                                contadores={})
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
                
    @app.route('/admin/concorrentes/exportar')
    @permission_required(['admin', 'gerente'])
    def admin_exportar_candidatos():
        # Obter parâmetros de filtro
        vaga_filtro = request.args.get('vaga', '')
        status_filtro = request.args.get('status', '')
        data_inicio = request.args.get('data_inicio', '')
        data_fim = request.args.get('data_fim', '')
        
        conn = None
        cursor = None

        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados para exportação.', 'error')
                return redirect(url_for('admin_concorrentes'))
            
            cursor = conn.cursor(dictionary=True)
            
            # 1. Construir query com filtros (Igual à rota admin_concorrentes)
            query = "SELECT nome, email, telefone, empresa, cargo, vaga, interesse, linkedin_url, status, data_candidatura, data_cadastro, observacoes FROM concorrentes WHERE 1=1"
            params = []
            
            if vaga_filtro:
                query += " AND vaga = %s"
                params.append(vaga_filtro)
            
            if status_filtro:
                query += " AND status = %s"
                params.append(status_filtro)
            
            if data_inicio:
                query += " AND DATE(data_candidatura) >= %s"
                params.append(data_inicio)
            
            if data_fim:
                query += " AND DATE(data_candidatura) <= %s"
                params.append(data_fim)
            
            query += " ORDER BY data_candidatura DESC, data_cadastro DESC"
            
            # 2. Executar a query
            cursor.execute(query, params)
            candidatos = cursor.fetchall()

            if not candidatos:
                flash('❌ Nenhum candidato encontrado para exportar com os filtros selecionados.', 'error')
                return redirect(url_for('admin_concorrentes'))

            # 3. Preparar a resposta como CSV
            from io import StringIO
            import csv

            si = StringIO()
            cw = csv.writer(si, delimiter=';') # Usando ';' para melhor compatibilidade com Excel no Brasil
            
            # Cabeçalho
            headers = ['Nome', 'Email', 'Telefone', 'Empresa', 'Cargo', 'Vaga', 'Interesse', 'LinkedIn', 'Status', 'Data Candidatura', 'Data Cadastro', 'Observações']
            cw.writerow(headers)

            # Dados
            for c in candidatos:
                data_candidatura = c.get('data_candidatura').strftime('%d/%m/%Y %H:%M') if c.get('data_candidatura') else ''
                data_cadastro = c.get('data_cadastro').strftime('%d/%m/%Y %H:%M') if c.get('data_cadastro') else ''
                
                row = [
                    c.get('nome', ''),
                    c.get('email', ''),
                    c.get('telefone', ''),
                    c.get('empresa', ''),
                    c.get('cargo', ''),
                    c.get('vaga', ''),
                    c.get('interesse', ''),
                    c.get('linkedin_url', ''),
                    c.get('status', '').title(),
                    data_candidatura,
                    data_cadastro,
                    c.get('observacoes', '')
                ]
                cw.writerow(row)

            # 4. Enviar o arquivo
            output = si.getvalue()
            
            response = app.response_class(
                output,
                mimetype='text/csv',
                headers={
                    "Content-Disposition": f"attachment;filename=candidatos_export_{datetime.now().strftime('%Y%m%d')}.csv"
                }
            )
            return response

        except mysql.connector.Error as err:
            flash(f'Erro no banco de dados durante a exportação: {err}', 'error')
            return redirect(url_for('admin_concorrentes'))
        except Exception as e:
            flash(f'Erro inesperado na exportação: {str(e)}', 'error')
            return redirect(url_for('admin_concorrentes'))
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
                
    @app.route('/admin/vagas', methods=['GET'])
    @permission_required(['admin', 'gerente'])
    def admin_gerenciar_vagas():
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_dashboard'))

            cursor = conn.cursor(dictionary=True)
            
            status_filtro = request.args.get('status', '')
            
            query = "SELECT * FROM vagas WHERE 1=1"
            params = []
            
            if status_filtro:
                query += " AND status = %s"
                params.append(status_filtro)
                
            # CORREÇÃO APLICADA AQUI: Mudando 'data_criacao' para 'data_publicacao'
            query += " ORDER BY status ASC, data_publicacao DESC" 
            
            cursor.execute(query, params)
            vagas = cursor.fetchall()
            
            cursor.execute("SELECT status, COUNT(*) as total FROM vagas GROUP BY status")
            contadores = {item['status']: item['total'] for item in cursor.fetchall()}
            contadores['total'] = sum(contadores.values())
            
            return render_template('admin/vagas.html', 
                                    vagas=vagas, 
                                    contadores=contadores,
                                    status_filtro=status_filtro)

        except mysql.connector.Error as err:
            flash(f'Erro ao carregar vagas: {err}', 'error')
            return redirect(url_for('admin_dashboard'))
        finally:
            if conn and conn.is_connected():
                conn.close()

    @app.route('/admin/vaga/nova', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente'])
    def admin_nova_vaga():
        if request.method == 'POST':
            conn = None
            try:
                conn = get_db_connection()
                if not conn:
                    flash('Erro ao conectar ao banco de dados.', 'error')
                    return redirect(url_for('admin_gerenciar_vagas'))
                
                titulo = request.form['titulo']
                descricao = request.form['descricao']
                requisitos = request.form['requisitos']
                area = request.form['area']
                localizacao = request.form['localizacao']
                status = request.form['status']
                data_fechamento = request.form.get('data_fechamento') or None

                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO vagas (titulo, descricao, requisitos, area, localizacao, status, data_fechamento)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (titulo, descricao, requisitos, area, localizacao, status, data_fechamento))
                conn.commit()
                
                # Log da ação
                if session.get('admin_id'):
                    try:
                        cursor.execute("""
                            INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                            VALUES (%s, 'CRIACAO', 'VAGAS', %s)
                        """, (session['admin_id'], f'Vaga criada: {titulo}'))
                        conn.commit()
                    except mysql.connector.Error:
                        pass

                flash(f'✅ Vaga "{titulo}" criada com sucesso!', 'success')
                return redirect(url_for('admin_gerenciar_vagas'))

            except mysql.connector.Error as err:
                flash(f'Erro ao criar vaga: {err}', 'error')
                return render_template('admin/vaga_form.html', vaga=request.form)
            finally:
                if conn and conn.is_connected():
                    conn.close()

        return render_template('admin/vaga_form.html', vaga=None)


    @app.route('/admin/vaga/editar/<int:id_vaga>', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente'])
    def admin_editar_vaga(id_vaga):
        conn = None
        vaga = None
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_gerenciar_vagas'))
                
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM vagas WHERE id_vaga = %s", (id_vaga,))
            vaga = cursor.fetchone()

            if not vaga:
                flash('Vaga não encontrada.', 'error')
                return redirect(url_for('admin_gerenciar_vagas'))

            if request.method == 'POST':
                titulo = request.form['titulo']
                descricao = request.form['descricao']
                requisitos = request.form['requisitos']
                area = request.form['area']
                localizacao = request.form['localizacao']
                status = request.form['status']
                data_fechamento = request.form.get('data_fechamento') or None

                cursor.execute("""
                    UPDATE vagas SET 
                        titulo = %s, descricao = %s, requisitos = %s, area = %s, 
                        localizacao = %s, status = %s, data_fechamento = %s
                    WHERE id_vaga = %s
                """, (titulo, descricao, requisitos, area, localizacao, status, data_fechamento, id_vaga))
                conn.commit()
                
                # Log da ação
                if session.get('admin_id'):
                    try:
                        cursor.execute("""
                            INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                            VALUES (%s, 'EDICAO', 'VAGAS', %s)
                        """, (session['admin_id'], f'Vaga editada: {titulo} (ID: {id_vaga})'))
                        conn.commit()
                    except mysql.connector.Error:
                        pass

                flash(f'✅ Vaga "{titulo}" atualizada com sucesso!', 'success')
                return redirect(url_for('admin_gerenciar_vagas'))
                
            # Para o GET, se for para visualizar, o 'modo' deve ser passado
            modo = request.args.get('modo')
            return render_template('admin/vaga_form.html', vaga=vaga, modo=modo)

        except mysql.connector.Error as err:
            flash(f'Erro: {err}', 'error')
            # Retorna o template de edição em caso de erro no POST
            if request.method == 'POST':
                return render_template('admin/vaga_form.html', vaga=request.form)
            return redirect(url_for('admin_gerenciar_vagas'))
        finally:
            if conn and conn.is_connected():
                conn.close()


    @app.route('/admin/vaga/excluir/<int:id_vaga>', methods=['POST'])
    @permission_required(['admin', 'gerente'])
    def admin_excluir_vaga(id_vaga):
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_gerenciar_vagas'))

            cursor = conn.cursor()
            
            # 1. Recuperar o título para o log
            cursor.execute("SELECT titulo FROM vagas WHERE id_vaga = %s", (id_vaga,))
            vaga = cursor.fetchone()
            if not vaga:
                flash('Vaga não encontrada para exclusão.', 'error')
                return redirect(url_for('admin_gerenciar_vagas'))
            titulo = vaga[0]
            
            # 2. Excluir a vaga
            cursor.execute("DELETE FROM vagas WHERE id_vaga = %s", (id_vaga,))
            conn.commit()
            
            # 3. Log da ação
            if session.get('admin_id'):
                try:
                    cursor.execute("""
                        INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                        VALUES (%s, 'EXCLUSAO', 'VAGAS', %s)
                    """, (session['admin_id'], f'Vaga excluída: {titulo} (ID: {id_vaga})'))
                    conn.commit()
                except mysql.connector.Error:
                    pass

            flash(f'🗑️ Vaga "{titulo}" excluída com sucesso!', 'success')
            return redirect(url_for('admin_gerenciar_vagas'))

        except mysql.connector.Error as err:
            flash(f'Erro ao excluir vaga: {err}', 'error')
            return redirect(url_for('admin_gerenciar_vagas'))
        finally:
            if conn and conn.is_connected():
                conn.close()

    @app.route('/admin/documentacao')
    @admin_required
    def documentation():
        return render_template('admin/documentation.html')
    
    # CONTATOS - Admin e Gerente
    @app.route('/admin/contatos')
    @permission_required(['admin', 'gerente', 'suporte'])
    def admin_contatos():
        """
        Lista todas as mensagens de contato (tabela 'suporte').
        """
        contatos = []
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('admin/contatos.html', contatos=[])
            
            cursor = conn.cursor(dictionary=True)
            # Ordena pelos pendentes primeiro e depois pela data de envio
            cursor.execute("SELECT * FROM suporte ORDER BY status = 'pendente' DESC, data_envio DESC")
            contatos = cursor.fetchall()
            
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar contatos: {err}', 'error')
        
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
                
        # Esta linha foi o ponto de falha que disparou o erro ao tentar renderizar
        return render_template('admin/contatos.html', contatos=contatos)
    
    @app.route('/admin/contato/excluir/<int:id_suporte>', methods=['POST'])
    @permission_required(['admin', 'gerente', 'suporte'])
    def admin_excluir_contato(id_suporte):
        """
        Exclui uma mensagem de contato (suporte) do banco de dados.
        A rota espera um método POST conforme definido no 'contatos.html'.
        """
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_contatos'))
            
            cursor = conn.cursor()
            
            # 1. Recuperar dados para a mensagem de sucesso
            cursor.execute("SELECT nome FROM suporte WHERE id_suporte = %s", (id_suporte,))
            contato_info = cursor.fetchone()
            
            if not contato_info:
                flash('❌ Mensagem de contato não encontrada.', 'error')
                return redirect(url_for('admin_contatos'))
                
            nome_contato = contato_info[0]
            
            # 2. Excluir a mensagem
            cursor.execute("DELETE FROM suporte WHERE id_suporte = %s", (id_suporte,))
            conn.commit()
            
            # 3. Log da ação (bloco omitido por brevidade, mas deve ser implementado)
            
            flash(f'🗑️ Mensagem de {nome_contato} excluída com sucesso!', 'success')
            
        except mysql.connector.Error as err:
            flash(f'Erro ao excluir mensagem de contato: {err}', 'error')
        
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
        
        # Redireciona para a lista de contatos após a exclusão
        return redirect(url_for('admin_contatos'))

    # DIAGNÓSTICOS - Admin, Gerente e Suporte
    @app.route('/admin/diagnosticos')
    @permission_required(['admin', 'gerente', 'suporte'])
    def admin_diagnosticos():
        user_cargo = session.get('admin_cargo', '').lower()
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('admin/diagnosticos.html', diagnosticos=[], user_cargo=user_cargo)
            cursor = conn.cursor(dictionary=True)
            status = request.args.get('status')
            query = "SELECT d.*, f.nome as tecnico_nome FROM diagnosticos d LEFT JOIN funcionarios f ON d.tecnico_responsavel = f.id_funcionario WHERE 1=1"
            params = []
            if status:
                query += " AND d.status = %s"
                params.append(status)
            query += " ORDER BY d.data_entrada DESC"
            cursor.execute(query, params)
            diagnosticos = cursor.fetchall()
            return render_template('admin/diagnosticos.html', diagnosticos=diagnosticos, user_cargo=user_cargo)
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar diagnósticos: {err}', 'error')
            return render_template('admin/diagnosticos.html', diagnosticos=[], user_cargo=user_cargo)
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/admin/concorrente/visualizar/<int:id_concorrente>')
    @permission_required(['admin', 'gerente'])
    def admin_visualizar_concorrente(id_concorrente):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_concorrentes'))
            
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM concorrentes WHERE id_concorrente = %s", (id_concorrente,))
            concorrente = cursor.fetchone()
            
            if not concorrente:
                flash('❌ Candidato não encontrado.', 'error')
                return redirect(url_for('admin_concorrentes'))
            
            return render_template('admin/concorrente_form.html', 
                                 concorrente=concorrente, 
                                 modo='visualizar')
        
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar candidato: {err}', 'error')
            return redirect(url_for('admin_concorrentes'))
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

                

    # RELATÓRIOS - Admin, Gerente e Vendedor (apenas visualização)
    @app.route('/admin/relatorios')
    @permission_required(['admin', 'gerente', 'vendedor'])
    def admin_relatorios():
        user_cargo = session.get('admin_cargo', '').lower()
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('admin/relatorios.html', user_cargo=user_cargo)
            cursor = conn.cursor(dictionary=True)
            
            # Tentar buscar relatórios mensais
            try:
                cursor.execute("SELECT * FROM view_relatorios_mensais LIMIT 12")
                relatorios_mensais = cursor.fetchall()
            except mysql.connector.Error:
                relatorios_mensais = []
            
            # Tentar buscar produtos mais vendidos
            try:
                cursor.execute("SELECT * FROM view_produtos_mais_vendidos LIMIT 10")
                produtos_mais_vendidos = cursor.fetchall()
            except mysql.connector.Error:
                produtos_mais_vendidos = []
            
            # Tentar buscar clientes ativos
            try:
                cursor.execute("SELECT * FROM view_clientes_ativos LIMIT 10")
                clientes_ativos = cursor.fetchall()
            except mysql.connector.Error:
                clientes_ativos = []
            
            # Tentar buscar estoque crítico
            try:
                cursor.execute("SELECT * FROM view_estoque_critico")
                estoque_critico = cursor.fetchall()
            except mysql.connector.Error:
                estoque_critico = []
            
            return render_template('admin/relatorios.html', 
                                 relatorios_mensais=relatorios_mensais,
                                 produtos_mais_vendidos=produtos_mais_vendidos, 
                                 clientes_ativos=clientes_ativos, 
                                 estoque_critico=estoque_critico,
                                 user_cargo=user_cargo)
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar relatórios: {err}', 'error')
            return render_template('admin/relatorios.html', user_cargo=user_cargo)
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    # COMBOS - Admin e Gerente
    @app.route('/admin/combos')
    @permission_required(['admin', 'gerente'])
    def admin_listar_combos():
        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('admin/combos.html', combos=[])
            
            cursor = conn.cursor(dictionary=True)
            
            # Verificar se a tabela combos existe
            cursor.execute("""
                SELECT COUNT(*) as existe
                FROM information_schema.tables 
                WHERE table_schema = DATABASE() 
                AND table_name = 'combos'
            """)
            tabela_existe = cursor.fetchone()['existe'] > 0
            
            combos_list = []
            
            if tabela_existe:
                # Buscar todos os combos
                cursor.execute("SELECT * FROM combos ORDER BY data_criacao DESC")
                combos = cursor.fetchall()
                
                # Converter para lista de dicionários
                for combo in combos:
                    combos_list.append({
                        'id_combo': combo['id_combo'],
                        'nome': combo.get('nome', 'Sem nome'),
                        'descricao': combo.get('descricao', ''),
                        'marca': combo.get('marca', ''),
                        'categoria': combo.get('categoria', ''),
                        'estoque': combo.get('estoque', 0),
                        'preco': float(combo.get('preco', 0)),
                        'ativo': bool(combo.get('ativo', True)),
                        'destaque': bool(combo.get('destaque', False)),
                        'imagem': combo.get('imagem'),
                        'data_criacao': combo.get('data_criacao')
                    })
            
            if not combos_list:
                flash('Nenhum combo cadastrado ainda.', 'info')
            
            return render_template('admin/combos.html', combos=combos_list)
            
        except Exception as e:
            print(f"ERRO: {str(e)}")
            flash(f'Erro ao carregar combos: {str(e)}', 'error')
            return render_template('admin/combos.html', combos=[])
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/admin/ofertas/nova', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente'])
    def admin_nova_oferta():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Buscar produtos ativos
        cursor.execute("SELECT id_produto, nome, preco FROM produto WHERE ativo = TRUE ORDER BY nome ASC")
        produtos = cursor.fetchall()

        if request.method == 'POST':
            id_produto = request.form.get('id_produto')
            desconto = float(request.form.get('desconto', 0))
            validade = request.form.get('validade')

            # Buscar preço original do produto
            cursor.execute("SELECT preco FROM produto WHERE id_produto = %s", (id_produto,))
            produto = cursor.fetchone()
            if not produto:
                flash('Produto não encontrado.', 'error')
                return redirect(url_for('admin_nova_oferta'))

            preco_original = float(produto['preco'])
            preco_com_desconto = preco_original - (preco_original * (desconto / 100))

            # Inserir oferta
            cursor.execute("""
                INSERT INTO ofertas (id_produto, desconto, preco_original, preco_com_desconto, validade, ativa)
                VALUES (%s, %s, %s, %s, %s, TRUE)
            """, (id_produto, desconto, preco_original, preco_com_desconto, validade))
            conn.commit()

            cursor.close()
            conn.close()
            flash('🎉 Oferta criada com sucesso!', 'success')
            return redirect(url_for('admin_ofertas'))

        cursor.close()
        conn.close()
        return render_template('admin/nova_oferta.html', produtos=produtos)

    @app.route('/admin/oferta/editar/<int:id_oferta>', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente'])
    def admin_editar_oferta(id_oferta):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_ofertas'))
            
            cursor = conn.cursor(dictionary=True)
            
            if request.method == 'POST':
                id_produto = request.form.get('id_produto')
                desconto = float(request.form.get('desconto', 0))
                validade = request.form.get('validade')
                ativa = request.form.get('ativa') == 'on'
                
                # Buscar preço original do produto
                cursor.execute("SELECT preco FROM produto WHERE id_produto = %s", (id_produto,))
                produto = cursor.fetchone()
                if not produto:
                    flash('Produto não encontrado.', 'error')
                    return redirect(url_for('admin_editar_oferta', id_oferta=id_oferta))
                
                preco_original = float(produto['preco'])
                preco_com_desconto = preco_original - (preco_original * (desconto / 100))
                
                # Atualizar oferta
                cursor.execute("""
                    UPDATE ofertas 
                    SET id_produto = %s, desconto = %s, preco_original = %s, 
                        preco_com_desconto = %s, validade = %s, ativa = %s
                    WHERE id_oferta = %s
                """, (id_produto, desconto, preco_original, preco_com_desconto, validade, ativa, id_oferta))
                conn.commit()
                
                # Log
                if session.get('admin_id'):
                    try:
                        cursor.execute("""
                            INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                            VALUES (%s, 'EDICAO', 'OFERTAS', %s)
                        """, (session['admin_id'], f'Oferta editada: ID {id_oferta}'))
                        conn.commit()
                    except mysql.connector.Error:
                        pass
                
                flash('✅ Oferta atualizada com sucesso!', 'success')
                return redirect(url_for('admin_ofertas'))
            
            else:
                # GET - carregar dados da oferta
                cursor.execute("""
                    SELECT o.*, p.nome as nome_produto 
                    FROM ofertas o
                    JOIN produto p ON o.id_produto = p.id_produto
                    WHERE o.id_oferta = %s
                """, (id_oferta,))
                oferta = cursor.fetchone()
                
                if not oferta:
                    flash('❌ Oferta não encontrada.', 'error')
                    return redirect(url_for('admin_ofertas'))
                
                # Buscar produtos ativos
                cursor.execute("SELECT id_produto, nome, preco FROM produto WHERE ativo = TRUE ORDER BY nome ASC")
                produtos = cursor.fetchall()
                
                return render_template('admin/editar_oferta.html', oferta=oferta, produtos=produtos)
        
        except mysql.connector.Error as err:
            flash(f'Erro ao editar oferta: {err}', 'error')
            return redirect(url_for('admin_ofertas'))
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/admin/oferta/excluir/<int:id_oferta>', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente'])
    def admin_excluir_oferta(id_oferta):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_ofertas'))
            
            cursor = conn.cursor(dictionary=True)
            
            # Buscar nome do produto para o log
            cursor.execute("""
                SELECT p.nome 
                FROM ofertas o
                JOIN produto p ON o.id_produto = p.id_produto
                WHERE o.id_oferta = %s
            """, (id_oferta,))
            oferta = cursor.fetchone()
            
            if not oferta:
                flash('❌ Oferta não encontrada.', 'error')
                return redirect(url_for('admin_ofertas'))
            
            nome_produto = oferta['nome']
            
            # Excluir oferta
            cursor.execute("DELETE FROM ofertas WHERE id_oferta = %s", (id_oferta,))
            conn.commit()
            
            # Log
            if session.get('admin_id'):
                try:
                    cursor.execute("""
                        INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                        VALUES (%s, 'EXCLUSAO', 'OFERTAS', %s)
                    """, (session['admin_id'], f'Oferta excluída: {nome_produto} (ID: {id_oferta})'))
                    conn.commit()
                except mysql.connector.Error:
                    pass
            
            flash(f'🗑️ Oferta de {nome_produto} excluída com sucesso!', 'success')
        
        except mysql.connector.Error as err:
            flash(f'Erro ao excluir oferta: {err}', 'error')
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
        
        return redirect(url_for('admin_ofertas'))

    @app.route('/admin/produto/editar/<int:id_produto>', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente'])
    def admin_editar_produto(id_produto):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_produtos'))
            
            cursor = conn.cursor(dictionary=True)
            
            if request.method == 'POST':
                nome = request.form.get('nome', '').strip()
                marca = request.form.get('marca', '').strip()
                preco = request.form.get('preco', '0').replace(',', '.')
                descricao = request.form.get('descricao', '').strip()
                estoque = request.form.get('estoque', '0')
                categoria = request.form.get('categoria', '').strip()
                peso = request.form.get('peso', '0').replace(',', '.')
                dimensoes = request.form.get('dimensoes', '').strip()
                destaque = request.form.get('destaque') == 'on'
                ativo = request.form.get('ativo') == 'on'
                
                cursor.execute("SELECT imagens FROM produto WHERE id_produto = %s", (id_produto,))
                produto_atual = cursor.fetchone()
                imagens = json.loads(produto_atual['imagens']) if produto_atual['imagens'] else []
                
                if 'imagens' in request.files:
                    files = request.files.getlist('imagens')
                    for file in files:
                        if file and allowed_file(file.filename):
                            filename = secure_filename(file.filename)
                            from uuid import uuid4
                            unique_filename = f"{uuid4().hex}_{filename}"
                            filepath = os.path.join(Config.UPLOAD_FOLDER, unique_filename)
                            os.makedirs(os.path.dirname(filepath), exist_ok=True)
                            file.save(filepath)
                            imagens.append(unique_filename)
                
                imagens_remover = request.form.getlist('imagens_remover')
                imagens = [img for img in imagens if img not in imagens_remover]
                
                cursor.execute("""
                    UPDATE produto SET nome = %s, marca = %s, preco = %s, descricao = %s, estoque = %s, categoria = %s, 
                    imagens = %s, peso = %s, dimensoes = %s, destaque = %s, ativo = %s WHERE id_produto = %s
                """, (nome, marca, float(preco), descricao, int(estoque), categoria, json.dumps(imagens) if imagens else None,
                      float(peso) if peso else 0, dimensoes, destaque, ativo, id_produto))
                
                conn.commit()
                
                if session.get('admin_id'):
                    try:
                        cursor.execute("""
                            INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                            VALUES (%s, 'EDICAO', 'PRODUTOS', %s)
                        """, (session['admin_id'], f'Produto editado: {nome} (ID: {id_produto})'))
                        conn.commit()
                    except mysql.connector.Error:
                        pass
                
                flash('✅ Produto atualizado com sucesso!', 'success')
                return redirect(url_for('admin_produtos'))
            
            else:
                cursor.execute("SELECT * FROM produto WHERE id_produto = %s", (id_produto,))
                produto = cursor.fetchone()
                
                if not produto:
                    flash('❌ Produto não encontrado.', 'error')
                    return redirect(url_for('admin_produtos'))
                
                # Processar imagens para exibição
                if produto.get('imagens'):
                    try:
                        produto['imagens'] = json.loads(produto['imagens'])
                    except:
                        produto['imagens'] = []
                
                return render_template('admin/produto_form.html', produto=produto)
        
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar produto: {err}', 'error')
            return redirect(url_for('admin_produtos'))
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/admin/cliente/<int:id_cliente>')
    @permission_required(['admin', 'gerente', 'vendedor'])
    def admin_detalhes_cliente(id_cliente):
        user_cargo = session.get('admin_cargo', '').lower()
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_clientes'))
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM clientes WHERE id_cliente = %s", (id_cliente,))
            cliente = cursor.fetchone()
            if not cliente:
                flash('❌ Cliente não encontrado.', 'error')
                return redirect(url_for('admin_clientes'))
            cursor.execute("SELECT * FROM pedidos WHERE id_cliente = %s ORDER BY data_pedido DESC", (id_cliente,))
            pedidos = cursor.fetchall()
            cursor.execute("SELECT * FROM enderecos WHERE id_cliente = %s ORDER BY principal DESC", (id_cliente,))
            enderecos = cursor.fetchall()
            return render_template('admin/cliente_detalhes.html', cliente=cliente, pedidos=pedidos, enderecos=enderecos, user_cargo=user_cargo)
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar dados do cliente: {err}', 'error')
            return redirect(url_for('admin_clientes'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/admin/contato/<int:id_suporte>', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente', 'suporte'])
    def admin_detalhes_contato(id_suporte):
        """
        Exibe detalhes da mensagem e permite a atualização do status e observações.
        """
        conn = None
        cursor = None
        
        if request.method == 'POST':
            # Lógica de Atualização (similar ao seu snippet 'contato_detalhes.html' que usa POST)
            status = request.form.get('status')
            observacoes = request.form.get('observacoes')
            
            try:
                conn = get_db_connection()
                if not conn:
                    flash('Erro de conexão ao atualizar.', 'error')
                    return redirect(url_for('admin_detalhes_contato', id_suporte=id_suporte))
                    
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE suporte SET status = %s, observacoes = %s WHERE id_suporte = %s
                """, (status, observacoes, id_suporte))
                conn.commit()
                
                # Log da ação (omito o bloco completo por brevidade, mas deve existir)
                
                flash('✅ Mensagem de contato atualizada com sucesso!', 'success')
                return redirect(url_for('admin_detalhes_contato', id_suporte=id_suporte))
                
            except mysql.connector.Error as err:
                flash(f'Erro ao atualizar: {err}', 'error')
                
            finally:
                if cursor:
                    cursor.close()
                if conn and conn.is_connected():
                    conn.close()
            
        # Lógica GET: Carregar detalhes
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_contatos'))
            
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM suporte WHERE id_suporte = %s", (id_suporte,))
            contato = cursor.fetchone()
            
            if not contato:
                flash('❌ Mensagem de contato não encontrada.', 'error')
                return redirect(url_for('admin_contatos'))
                
            return render_template('admin/contato_detalhes.html', contato=contato)
            
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar detalhes do contato: {err}', 'error')
            return redirect(url_for('admin_contatos'))
            
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    @app.route('/admin/diagnostico/<int:id_diagnostico>', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente', 'suporte'])
    def admin_detalhes_diagnostico(id_diagnostico):
        user_cargo = session.get('admin_cargo', '').lower()
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_diagnosticos'))
            cursor = conn.cursor(dictionary=True)
            if request.method == 'POST':
                status = request.form.get('status')
                relatorio_final = request.form.get('relatorio_final', '').strip()
                pecas_defeito = request.form.get('pecas_defeito', '').strip()
                orcamento = request.form.get('orcamento', '0').replace(',', '.')
                observacoes = request.form.get('observacoes', '').strip()
                cursor.execute("""
                    UPDATE diagnosticos SET status = %s, relatorio_final = %s, pecas_defeito = %s, 
                    orcamento = %s, observacoes = %s, tecnico_responsavel = %s WHERE id_diagnostico = %s
                """, (status, relatorio_final, pecas_defeito, float(orcamento) if orcamento else 0, observacoes, session['admin_id'], id_diagnostico))
                if status == 'concluido':
                    cursor.execute("UPDATE diagnosticos SET data_conclusao = NOW() WHERE id_diagnostico = %s", (id_diagnostico,))
                conn.commit()
                flash('✅ Diagnóstico atualizado com sucesso!', 'success')
                return redirect(url_for('admin_diagnosticos'))
            else:
                cursor.execute("""
                    SELECT d.*, f.nome as tecnico_nome FROM diagnosticos d 
                    LEFT JOIN funcionarios f ON d.tecnico_responsavel = f.id_funcionario WHERE d.id_diagnostico = %s
                """, (id_diagnostico,))
                diagnostico = cursor.fetchone()
                if not diagnostico:
                    flash('❌ Diagnóstico não encontrado.', 'error')
                    return redirect(url_for('admin_diagnosticos'))
                return render_template('admin/diagnostico_detalhes.html', diagnostico=diagnostico, user_cargo=user_cargo)
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar diagnóstico: {err}', 'error')
            return redirect(url_for('admin_diagnosticos'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    

    

    @app.route('/admin/concorrente/excluir/<int:id_concorrente>', methods=['POST'])
    @permission_required(['admin', 'gerente'])
    def admin_excluir_concorrente(id_concorrente):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_concorrentes'))
            
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT nome FROM concorrentes WHERE id_concorrente = %s", (id_concorrente,))
            concorrente = cursor.fetchone()
            
            if not concorrente:
                flash('❌ Concorrente não encontrado.', 'error')
                return redirect(url_for('admin_concorrentes'))
            
            cursor.execute("DELETE FROM concorrentes WHERE id_concorrente = %s", (id_concorrente,))
            conn.commit()
            
            # Log da ação
            if session.get('admin_id'):
                try:
                    cursor.execute("""
                        INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                        VALUES (%s, 'EXCLUSAO', 'CONCORRENTES', %s)
                    """, (session['admin_id'], f'Concorrente excluído: {concorrente["nome"]} (ID: {id_concorrente})'))
                    conn.commit()
                except mysql.connector.Error:
                    pass
            
            flash(f'🗑️ Concorrente {concorrente["nome"]} excluído com sucesso!', 'success')
        
        except mysql.connector.Error as err:
            flash(f'Erro ao excluir concorrente: {err}', 'error')
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
        
        return redirect(url_for('admin_concorrentes'))

    @app.route('/admin/concorrente/<int:id_concorrente>')
    @permission_required(['admin', 'gerente'])
    def admin_detalhes_concorrente(id_concorrente):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_concorrentes'))
            
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM concorrentes WHERE id_concorrente = %s", (id_concorrente,))
            concorrente = cursor.fetchone()
            
            if not concorrente:
                flash('❌ Concorrente não encontrado.', 'error')
                return redirect(url_for('admin_concorrentes'))
            
            return render_template('admin/concorrente_detalhes.html', concorrente=concorrente)
        
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar concorrente: {err}', 'error')
            return redirect(url_for('admin_concorrentes'))
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/admin/funcionario/novo', methods=['GET', 'POST'])
    @permission_required(['admin'])
    def admin_novo_funcionario():
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip().lower()
            senha = request.form.get('senha', '')
            cargo = request.form.get('cargo', 'vendedor')
            if not all([nome, email, senha]):
                flash('❌ Preencha todos os campos.', 'error')
                return render_template('admin/funcionario_form.html')
            if len(senha) < 6:
                flash('❌ A senha deve ter no mínimo 6 caracteres.', 'error')
                return render_template('admin/funcionario_form.html')
            try:
                conn = get_db_connection()
                if not conn:
                    flash('Erro ao conectar ao banco de dados.', 'error')
                    return render_template('admin/funcionario_form.html')
                cursor = conn.cursor()
                cursor.execute("SELECT id_funcionario FROM funcionarios WHERE email = %s", (email,))
                if cursor.fetchone():
                    flash('❌ Este e-mail já está cadastrado.', 'error')
                    return render_template('admin/funcionario_form.html')
                senha_hash = generate_password_hash(senha)
                cursor.execute("INSERT INTO funcionarios (nome, email, senha, cargo) VALUES (%s, %s, %s, %s)", (nome, email, senha_hash, cargo))
                conn.commit()
                if session.get('admin_id'):
                    try:
                        cursor.execute("INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao) VALUES (%s, 'CADASTRO', 'FUNCIONARIOS', %s)",
                                      (session['admin_id'], f'Funcionário cadastrado: {nome}'))
                        conn.commit()
                    except mysql.connector.Error:
                        pass
                flash('✅ Funcionário cadastrado com sucesso!', 'success')
                return redirect(url_for('admin_funcionarios'))
            except mysql.connector.Error as err:
                flash(f'Erro ao cadastrar funcionário: {err}', 'error')
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()
        return render_template('admin/funcionario_form.html')

    @app.route('/admin/funcionario/editar/<int:id_funcionario>', methods=['GET', 'POST'])
    @permission_required(['admin'])
    def admin_editar_funcionario(id_funcionario):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_funcionarios'))
            cursor = conn.cursor(dictionary=True)
            if request.method == 'POST':
                nome = request.form.get('nome', '').strip()
                email = request.form.get('email', '').strip().lower()
                cargo = request.form.get('cargo', 'vendedor')
                ativo = request.form.get('ativo') == 'on'
                nova_senha = request.form.get('nova_senha', '').strip()
                if not all([nome, email]):
                    flash('❌ Preencha todos os campos obrigatórios.', 'error')
                    return redirect(url_for('admin_editar_funcionario', id_funcionario=id_funcionario))
                cursor.execute("SELECT id_funcionario FROM funcionarios WHERE email = %s AND id_funcionario != %s", (email, id_funcionario))
                if cursor.fetchone():
                    flash('❌ Este e-mail já está cadastrado em outro funcionário.', 'error')
                    return redirect(url_for('admin_editar_funcionario', id_funcionario=id_funcionario))
                if nova_senha:
                    if len(nova_senha) < 6:
                        flash('❌ A senha deve ter no mínimo 6 caracteres.', 'error')
                        return redirect(url_for('admin_editar_funcionario', id_funcionario=id_funcionario))
                    senha_hash = generate_password_hash(nova_senha)
                    cursor.execute("UPDATE funcionarios SET nome = %s, email = %s, cargo = %s, ativo = %s, senha = %s WHERE id_funcionario = %s",
                                  (nome, email, cargo, ativo, senha_hash, id_funcionario))
                else:
                    cursor.execute("UPDATE funcionarios SET nome = %s, email = %s, cargo = %s, ativo = %s WHERE id_funcionario = %s",
                                  (nome, email, cargo, ativo, id_funcionario))
                conn.commit()
                if session.get('admin_id'):
                    try:
                        cursor.execute("INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao) VALUES (%s, 'EDICAO', 'FUNCIONARIOS', %s)",
                                      (session['admin_id'], f'Funcionário editado: {nome} (ID: {id_funcionario})'))
                        conn.commit()
                    except mysql.connector.Error:
                        pass
                flash('✅ Funcionário atualizado com sucesso!', 'success')
                return redirect(url_for('admin_funcionarios'))
            else:
                cursor.execute("SELECT * FROM funcionarios WHERE id_funcionario = %s", (id_funcionario,))
                funcionario = cursor.fetchone()
                if not funcionario:
                    flash('❌ Funcionário não encontrado.', 'error')
                    return redirect(url_for('admin_funcionarios'))
                return render_template('admin/funcionario_form.html', funcionario=funcionario, editando=True)
        except mysql.connector.Error as err:
            flash(f'Erro ao editar funcionário: {err}', 'error')
            return redirect(url_for('admin_funcionarios'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/admin/funcionario/excluir/<int:id_funcionario>', methods=['POST'])
    @permission_required(['admin'])
    def admin_excluir_funcionario(id_funcionario):
        if id_funcionario == session.get('admin_id'):
            flash('❌ Você não pode excluir sua própria conta.', 'error')
            return redirect(url_for('admin_funcionarios'))
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_funcionarios'))
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT nome FROM funcionarios WHERE id_funcionario = %s", (id_funcionario,))
            funcionario = cursor.fetchone()
            if not funcionario:
                flash('❌ Funcionário não encontrado.', 'error')
                return redirect(url_for('admin_funcionarios'))
            nome_funcionario = funcionario['nome']
            cursor.execute("DELETE FROM funcionarios WHERE id_funcionario = %s", (id_funcionario,))
            conn.commit()
            if session.get('admin_id'):
                try:
                    cursor.execute("INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao) VALUES (%s, 'EXCLUSAO', 'FUNCIONARIOS', %s)",
                                  (session['admin_id'], f'Funcionário excluído: {nome_funcionario} (ID: {id_funcionario})'))
                    conn.commit()
                except mysql.connector.Error:
                    pass
            flash(f'🗑️ Funcionário {nome_funcionario} excluído com sucesso!', 'success')
        except mysql.connector.Error as err:
            flash(f'Erro ao excluir funcionário: {err}', 'error')
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
        return redirect(url_for('admin_funcionarios'))

    @app.route('/admin/funcionario/alternar-status/<int:id_funcionario>', methods=['POST'])
    @permission_required(['admin'])
    def admin_alternar_status_funcionario(id_funcionario):
        if id_funcionario == session.get('admin_id'):
            flash('❌ Você não pode desativar sua própria conta.', 'error')
            return redirect(url_for('admin_funcionarios'))
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_funcionarios'))
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT nome, ativo FROM funcionarios WHERE id_funcionario = %s", (id_funcionario,))
            funcionario = cursor.fetchone()
            if not funcionario:
                flash('❌ Funcionário não encontrado.', 'error')
                return redirect(url_for('admin_funcionarios'))
            novo_status = not funcionario['ativo']
            cursor.execute("UPDATE funcionarios SET ativo = %s WHERE id_funcionario = %s", (novo_status, id_funcionario))
            conn.commit()
            acao = 'ativado' if novo_status else 'desativado'
            if session.get('admin_id'):
                try:
                    cursor.execute("INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao) VALUES (%s, 'ALTERACAO', 'FUNCIONARIOS', %s)",
                                  (session['admin_id'], f'Funcionário {acao}: {funcionario["nome"]} (ID: {id_funcionario})'))
                    conn.commit()
                except mysql.connector.Error:
                    pass
            status_msg = '✅ ativado' if novo_status else '🚫 desativado'
            flash(f'Funcionário {funcionario["nome"]} foi {status_msg} com sucesso!', 'success')
        except mysql.connector.Error as err:
            flash(f'Erro ao alterar status: {err}', 'error')
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
        return redirect(url_for('admin_funcionarios'))
    
    @app.route('/admin/concorrente/download-curriculo/<filename>')
    @permission_required(['admin', 'gerente'])
    def download_curriculo(filename):
        try:
            # Buscar o arquivo na pasta de curriculos
            pasta_base = os.path.join(app.root_path, 'static', 'uploads', 'curriculos')
            
            # Procurar o arquivo em todas as subpastas
            for root, dirs, files in os.walk(pasta_base):
                if filename in files:
                    return send_from_directory(root, filename, as_attachment=True)
            
            flash('❌ Arquivo não encontrado.', 'error')
            return redirect(url_for('admin_concorrentes'))
            
        except Exception as e:
            flash(f'Erro ao baixar arquivo: {str(e)}', 'error')
            return redirect(url_for('admin_concorrentes'))
        
    @app.route('/admin/concorrente/editar/<int:id_concorrente>', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente'])
    def admin_editar_concorrente(id_concorrente):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_concorrentes'))
            
            cursor = conn.cursor(dictionary=True)
            
            if request.method == 'POST':
                nome = request.form.get('nome', '').strip()
                email = request.form.get('email', '').strip()
                telefone = request.form.get('telefone', '').strip()
                empresa = request.form.get('empresa', '').strip()
                cargo = request.form.get('cargo', '').strip()
                vaga = request.form.get('vaga', '').strip()
                interesse = request.form.get('interesse', '').strip()
                linkedin_url = request.form.get('linkedin_url', '').strip()
                mensagem = request.form.get('mensagem', '').strip()
                status = request.form.get('status', 'pendente')
                observacoes = request.form.get('observacoes', '').strip()
                
                # Validar LinkedIn
                if linkedin_url and not validar_linkedin(linkedin_url):
                    flash('❌ O link do LinkedIn deve começar com linkedin.com', 'error')
                    cursor.execute("SELECT * FROM concorrentes WHERE id_concorrente = %s", (id_concorrente,))
                    concorrente = cursor.fetchone()
                    return render_template('admin/concorrente_form.html', concorrente=concorrente)
                
                cursor.execute("""
                    UPDATE concorrentes 
                    SET nome = %s, email = %s, telefone = %s, empresa = %s, cargo = %s, 
                        vaga = %s, interesse = %s, linkedin_url = %s, mensagem = %s, 
                        status = %s, observacoes = %s
                    WHERE id_concorrente = %s
                """, (nome, email, telefone, empresa, cargo, vaga, interesse, 
                      linkedin_url, mensagem, status, observacoes, id_concorrente))
                
                conn.commit()
                
                # Log da ação
                if session.get('admin_id'):
                    try:
                        cursor.execute("""
                            INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                            VALUES (%s, 'EDICAO', 'CONCORRENTES', %s)
                        """, (session['admin_id'], f'Candidato editado: {nome} (ID: {id_concorrente})'))
                        conn.commit()
                    except mysql.connector.Error:
                        pass
                
                flash('✅ Candidato atualizado com sucesso!', 'success')
                return redirect(url_for('admin_concorrentes'))
            
            else:
                cursor.execute("SELECT * FROM concorrentes WHERE id_concorrente = %s", (id_concorrente,))
                concorrente = cursor.fetchone()
                
                if not concorrente:
                    flash('❌ Candidato não encontrado.', 'error')
                    return redirect(url_for('admin_concorrentes'))
                
                return render_template('admin/concorrente_form.html', concorrente=concorrente)
        
        except mysql.connector.Error as err:
            flash(f'Erro ao editar candidato: {err}', 'error')
            return redirect(url_for('admin_concorrentes'))
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/admin/concorrente/novo', methods=['GET', 'POST'])
    @permission_required(['admin', 'gerente'])
    def admin_novo_concorrente():
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            telefone = request.form.get('telefone', '').strip()
            empresa = request.form.get('empresa', '').strip()
            cargo = request.form.get('cargo', '').strip()
            vaga = request.form.get('vaga', '').strip()
            interesse = request.form.get('interesse', '').strip()
            linkedin_url = request.form.get('linkedin_url', '').strip()
            mensagem = request.form.get('mensagem', '').strip()
            status = request.form.get('status', 'pendente')
            observacoes = request.form.get('observacoes', '').strip()
            
            if not all([nome, email, empresa]):
                flash('❌ Preencha todos os campos obrigatórios.', 'error')
                return render_template('admin/concorrente_form.html')
            
            # Validar LinkedIn
            if linkedin_url and not validar_linkedin(linkedin_url):
                flash('❌ O link do LinkedIn deve começar com linkedin.com', 'error')
                return render_template('admin/concorrente_form.html')
            
            try:
                conn = get_db_connection()
                if not conn:
                    flash('Erro ao conectar ao banco de dados.', 'error')
                    return render_template('admin/concorrente_form.html')
                
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO concorrentes 
                    (nome, email, telefone, empresa, cargo, vaga, interesse, 
                     linkedin_url, mensagem, status, observacoes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (nome, email, telefone, empresa, cargo, vaga, interesse, 
                      linkedin_url, mensagem, status, observacoes))
                
                conn.commit()
                
                # Log da ação
                if session.get('admin_id'):
                    try:
                        cursor.execute("""
                            INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                            VALUES (%s, 'CADASTRO', 'CONCORRENTES', %s)
                        """, (session['admin_id'], f'Candidato cadastrado manualmente: {nome}'))
                        conn.commit()
                    except mysql.connector.Error:
                        pass
                
                flash('✅ Candidato cadastrado com sucesso!', 'success')
                return redirect(url_for('admin_concorrentes'))
            
            except mysql.connector.Error as err:
                flash(f'Erro ao cadastrar candidato: {err}', 'error')
            
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()
        
        return render_template('admin/concorrente_form.html')
    
    @app.route('/admin/concorrente/atualizar-status/<int:id_concorrente>', methods=['POST'])
    @permission_required(['admin', 'gerente'])
    def admin_atualizar_status(id_concorrente):
        try:
            status = request.form.get('status', 'pendente')
            
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('admin_concorrentes'))
            
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE concorrentes 
                SET status = %s 
                WHERE id_concorrente = %s
            """, (status, id_concorrente))
            
            conn.commit()
            
            # Log da ação
            if session.get('admin_id'):
                try:
                    cursor.execute("SELECT nome FROM concorrentes WHERE id_concorrente = %s", (id_concorrente,))
                    nome = cursor.fetchone()[0]
                    cursor.execute("""
                        INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
                        VALUES (%s, 'EDICAO', 'CONCORRENTES', %s)
                    """, (session['admin_id'], f'Status alterado para {status}: {nome}'))
                    conn.commit()
                except mysql.connector.Error:
                    pass
            
            flash(f'✅ Status atualizado para {status}!', 'success')
            
        except mysql.connector.Error as err:
            flash(f'Erro ao atualizar status: {err}', 'error')
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
        
        return redirect(request.referrer or url_for('admin_concorrentes'))