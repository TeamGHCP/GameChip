# ==============================================================================
# ARQUIVO: routes/empresa_routes.py
# ==============================================================================
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from models.database import get_db_connection
from utils.decorators import login_required
import json
import mysql.connector
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from config import Config
from uuid import uuid4
from werkzeug.security import generate_password_hash, check_password_hash

def configure_empresa_routes(app):
    
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

    # ==========================================================================
    # 1. AUTENTICAÇÃO
    # ==========================================================================
    @app.route('/cadastro-empresa', methods=['POST'], endpoint='empresa_cadastro')
    def cadastro_empresa():
        conn = None
        try:
            # Captura dados
            razao_social = request.form.get('razao_social')
            nome_fantasia = request.form.get('nome_fantasia')
            cnpj = request.form.get('cnpj')
            email = request.form.get('email')
            telefone = request.form.get('telefone')
            tipo_empresa = request.form.get('tipo_empresa')
            endereco = request.form.get('endereco')
            senha = request.form.get('senha')
            confirmar_senha = request.form.get('confirmar_senha')

            if senha != confirmar_senha:
                flash('As senhas não conferem.', 'error')
                return redirect(url_for('login_empresa_view'))

            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT id_empresa FROM empresas WHERE email = %s OR cnpj = %s", (email, cnpj))
            if cursor.fetchone():
                flash('Email ou CNPJ já cadastrados.', 'warning')
                return redirect(url_for('login_empresa_view'))

            senha_hash = generate_password_hash(senha)

            cursor.execute("""
                INSERT INTO empresas (razao_social, nome_fantasia, cnpj, email, telefone, tipo_empresa, endereco, senha, ativo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
            """, (razao_social, nome_fantasia, cnpj, email, telefone, tipo_empresa, endereco, senha_hash))
            
            conn.commit()
            flash('Cadastro realizado! Faça login.', 'success')
            return redirect(url_for('login_empresa_view'))

        except Exception as e:
            flash(f'Erro no cadastro: {str(e)}', 'error')
            return redirect(url_for('login_empresa_view'))
        finally:
            if conn: conn.close()

    @app.route('/login-empresa-auth', methods=['POST'], endpoint='empresa_login')
    def login_empresa():
        conn = None
        try:
            email = request.form.get('email')
            senha = request.form.get('senha')

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("SELECT * FROM empresas WHERE email = %s", (email,))
            empresa = cursor.fetchone()

            if empresa and check_password_hash(empresa['senha'], senha):
                session['empresa_id'] = empresa['id_empresa']
                session['empresa_nome'] = empresa['nome_fantasia'] or empresa['razao_social']
                session['tipo_usuario'] = 'empresa'
                
                flash(f"Bem-vindo, {session['empresa_nome']}!", 'success')
                return redirect(url_for('painel_empresa'))
            else:
                flash('Email ou senha incorretos.', 'error')
                return redirect(url_for('login_empresa_view'))

        except Exception as e:
            flash(f'Erro no login: {str(e)}', 'error')
            return redirect(url_for('login_empresa_view'))
        finally:
            if conn: conn.close()

    @app.route('/area-empresa')
    def login_empresa_view():
        form_type = request.args.get('form', 'login') 
        return render_template('login_empresa.html', form_type=form_type)

    # ==========================================================================
    # 2. PAINEL DE CONTROLE (COM LÓGICA DE TIPO)
    # ==========================================================================
    @app.route('/painel-empresa')
    @login_required
    def painel_empresa():
        if 'empresa_id' not in session: return redirect(url_for('login_empresa_view'))
        
        conn = None
        try:
            conn = get_db_connection()
            if not conn: return redirect(url_for('inicio'))
            cursor = conn.cursor(dictionary=True)
            
            empresa_id = session['empresa_id']
            cursor.execute("SELECT * FROM empresas WHERE id_empresa = %s", (empresa_id,))
            empresa = cursor.fetchone()
            
            if not empresa: return redirect(url_for('inicio'))

            # Variáveis padrão (vazias caso o tipo não permita)
            produtos_empresa = []
            produtos_disponiveis = []
            stats = {'total_vendas': 0, 'receita_total': 0}
            pedidos_compra = [] # Para quem é comprador
            avaliacoes = []
            media_avaliacoes = {'media_notas': 0, 'total_avaliacoes': 0}

            # LÓGICA VENDEDOR (Vendedor ou Ambos)
            if empresa['tipo_empresa'] in ['vendedor', 'ambos']:
                cursor.execute("""
                    SELECT pe.*, p.nome, p.marca, p.categoria, p.imagens
                    FROM produtos_empresa pe
                    JOIN produto p ON pe.id_produto = p.id_produto
                    WHERE pe.id_empresa = %s ORDER BY pe.data_cadastro DESC
                """, (empresa_id,))
                produtos_empresa = cursor.fetchall()
                
                for p in produtos_empresa:
                    if p.get('imagens'):
                        try: p['imagens'] = json.loads(p['imagens'])
                        except: p['imagens'] = []

                cursor.execute("""
                    SELECT p.id_produto, p.nome, p.marca, p.preco, p.estoque, p.categoria
                    FROM produto p 
                    WHERE p.ativo = TRUE 
                    AND p.id_produto NOT IN (
                        SELECT pe.id_produto FROM produtos_empresa pe 
                        WHERE pe.id_empresa = %s
                    ) ORDER BY p.nome LIMIT 100
                """, (empresa_id,))
                produtos_disponiveis = cursor.fetchall()
                
                cursor.execute("""
                    SELECT COUNT(*) as total_vendas, COALESCE(SUM(total), 0) as receita_total
                    FROM pedidos WHERE id_empresa_compradora = %s AND status != 'cancelado'
                """, (empresa_id,)) # Ajuste aqui se sua lógica de venda for diferente (itens_pedido)
                stats = cursor.fetchone()
                
                cursor.execute("""
                    SELECT ae.*, COALESCE(c.nome, 'Usuário') as avaliador_nome
                    FROM avaliacoes_empresas ae
                    LEFT JOIN clientes c ON ae.id_cliente = c.id_cliente
                    WHERE ae.id_empresa_avaliada = %s AND ae.aprovado = TRUE
                    ORDER BY ae.data_avaliacao DESC LIMIT 5
                """, (empresa_id,))
                avaliacoes = cursor.fetchall()
                
                cursor.execute("""
                    SELECT AVG(nota) as media_notas, COUNT(*) as total_avaliacoes 
                    FROM avaliacoes_empresas WHERE id_empresa_avaliada = %s AND aprovado = TRUE
                """, (empresa_id,))
                media_avaliacoes = cursor.fetchone()

            # LÓGICA COMPRADOR (Comprador ou Ambos)
            if empresa['tipo_empresa'] in ['comprador', 'ambos']:
                # Busca histórico de compras feitas por esta empresa
                cursor.execute("""
                    SELECT p.*, e.nome_fantasia as vendedor_nome, p.status
                    FROM pedidos p
                    LEFT JOIN empresas e ON p.id_empresa_compradora = e.id_empresa 
                    WHERE p.id_empresa_compradora = %s 
                    ORDER BY p.data_pedido DESC
                """, (empresa_id,))
                # OBS: A query acima assume que id_empresa_compradora é quem comprou. 
                # Ajuste se sua tabela pedidos usar outro campo.
                pedidos_compra = cursor.fetchall()

            return render_template('painel_empresa.html', 
                                 empresa=empresa,
                                 produtos_empresa=produtos_empresa,
                                 produtos_disponiveis=produtos_disponiveis,
                                 stats=stats,
                                 avaliacoes=avaliacoes,
                                 media_avaliacoes=media_avaliacoes,
                                 pedidos_compra=pedidos_compra) # Passando compras
        
        except Exception as e:
            flash(f'Erro no painel: {e}', 'error')
            return redirect(url_for('inicio'))
        finally:
            if conn: conn.close()

    # ==========================================================================
    # 3. GESTÃO DE PRODUTOS
    # ==========================================================================
    @app.route('/empresa/cadastrar-novo-produto', methods=['POST'])
    @login_required
    def cadastrar_novo_produto_empresa():
        if 'empresa_id' not in session: return redirect(url_for('login_empresa_view'))
        
        # Bloqueio backend extra
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT tipo_empresa FROM empresas WHERE id_empresa=%s", (session['empresa_id'],))
        emp = cursor.fetchone()
        if emp and emp['tipo_empresa'] == 'comprador':
            conn.close()
            flash('Sua conta é apenas de comprador.', 'error')
            return redirect(url_for('painel_empresa'))

        try:
            nome = request.form.get('nome')
            marca = request.form.get('marca')
            categoria = request.form.get('categoria')
            descricao = request.form.get('descricao')
            preco = float(request.form.get('preco', 0))
            estoque = int(request.form.get('estoque', 0))
            
            imagens = []
            if 'imagens' in request.files:
                for f in request.files.getlist('imagens'):
                    if f and allowed_file(f.filename):
                        fname = secure_filename(f.filename)
                        uid = f"{uuid4().hex}_{fname}"
                        path = os.path.join(Config.UPLOAD_FOLDER, uid)
                        f.save(path)
                        imagens.append(uid)

            cursor.execute("INSERT INTO produto (nome, marca, preco, descricao, estoque, categoria, imagens, ativo) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)", 
                         (nome, marca, preco, descricao, estoque, categoria, json.dumps(imagens)))
            new_id = cursor.lastrowid
            
            cursor.execute("INSERT INTO produtos_empresa (id_empresa, id_produto, preco_empresa, estoque_empresa, ativo) VALUES (%s, %s, %s, %s, 1)", 
                         (session['empresa_id'], new_id, preco, estoque))
            
            conn.commit()
            flash('✅ Produto criado!', 'success')
        except Exception as e:
            flash(f'Erro: {e}', 'error')
        finally:
            if conn: conn.close()
        return redirect(url_for('painel_empresa'))

    @app.route('/empresa/adicionar-produto', methods=['POST'])
    @login_required
    def adicionar_produto_empresa():
        if 'empresa_id' not in session: return redirect(url_for('login_empresa_view'))
        try:
            id_prod = request.form.get('id_produto')
            preco = request.form.get('preco_empresa')
            estoque = request.form.get('estoque_empresa')
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id_produto_empresa FROM produtos_empresa WHERE id_empresa=%s AND id_produto=%s", (session['empresa_id'], id_prod))
            if cursor.fetchone():
                flash('Produto já existe!', 'warning')
            else:
                cursor.execute("INSERT INTO produtos_empresa (id_empresa, id_produto, preco_empresa, estoque_empresa, ativo) VALUES (%s, %s, %s, %s, 1)", 
                             (session['empresa_id'], id_prod, preco, estoque))
                conn.commit()
                flash('✅ Adicionado!', 'success')
            conn.close()
        except Exception as e:
            flash(f'Erro: {e}', 'error')
        return redirect(url_for('painel_empresa'))

    @app.route('/empresa/atualizar-produto/<int:id_produto_empresa>', methods=['POST'])
    @login_required
    def atualizar_produto_empresa(id_produto_empresa):
        if 'empresa_id' not in session: return jsonify({'error': 'Unauthorized'}), 403
        data = request.get_json()
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE produtos_empresa SET preco_empresa=%s, estoque_empresa=%s, ativo=%s WHERE id_produto_empresa=%s AND id_empresa=%s", 
                         (data['preco_empresa'], data['estoque_empresa'], data['ativo'], id_produto_empresa, session['empresa_id']))
            conn.commit()
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
        finally:
            if conn: conn.close()

    @app.route('/empresa/remover-produto/<int:id_produto_empresa>', methods=['POST'])
    @login_required
    def remover_produto_empresa(id_produto_empresa):
        if 'empresa_id' not in session: return redirect(url_for('login_empresa_view'))
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM produtos_empresa WHERE id_produto_empresa=%s AND id_empresa=%s", (id_produto_empresa, session['empresa_id']))
            conn.commit()
            conn.close()
            flash('Removido.', 'success')
        except: flash('Erro ao remover.', 'error')
        return redirect(url_for('painel_empresa'))

    @app.route('/api/produtos-disponiveis')
    @login_required
    def api_produtos_disponiveis():
        if 'empresa_id' not in session: return jsonify([]), 403
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id_produto, nome, marca, preco, estoque, categoria FROM produto WHERE ativo = 1 AND id_produto NOT IN (SELECT id_produto FROM produtos_empresa WHERE id_empresa = %s) ORDER BY nome", (session['empresa_id'],))
        data = cursor.fetchall()
        conn.close()
        return jsonify(data)

    # ==========================================================================
    # 4. GESTÃO DE PEDIDOS (VENDAS)
    # ==========================================================================
    @app.route('/empresa/pedidos')
    @login_required
    def gerenciar_pedidos_empresa():
        if 'empresa_id' not in session: return redirect(url_for('login_empresa_view'))
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Nota: Ajuste a query conforme a lógica real de quem VENDEU (aqui assumo id_empresa_compradora ou similar, mas geralmente vendedor é via produtos_empresa)
        # Se for um marketplace onde a empresa é o vendedor, a query seria diferente.
        # Mantendo simples:
        cursor.execute("SELECT * FROM pedidos ORDER BY data_pedido DESC LIMIT 50")
        pedidos = cursor.fetchall()
        conn.close()
        return render_template('empresa_pedidos.html', pedidos=pedidos)

    @app.route('/empresa/pedido/<int:id_pedido>/status', methods=['POST'])
    @login_required
    def atualizar_status_pedido(id_pedido):
        if 'empresa_id' not in session: return redirect(url_for('login_empresa_view'))
        status = request.form.get('status')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE pedidos SET status = %s WHERE id_pedido = %s", (status, id_pedido))
        conn.commit()
        conn.close()
        flash(f'Pedido atualizado para {status}', 'success')
        return redirect(url_for('gerenciar_pedidos_empresa'))

    # ==========================================================================
    # 5. PERFIL PÚBLICO & AVALIAÇÕES (LÓGICA PODE_COMPRAR)
    # ==========================================================================
    @app.route('/lojas')
    def listar_lojas():
        conn = None
        try:
            conn = get_db_connection()
            if not conn: return render_template('erro.html', erro="DB Error")
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT e.id_empresa, e.nome_fantasia, e.razao_social, e.data_cadastro, e.tema_escuro,
                (SELECT AVG(nota) FROM avaliacoes_empresas WHERE id_empresa_avaliada = e.id_empresa AND aprovado=1) as avaliacao,
                (SELECT COUNT(*) FROM avaliacoes_empresas WHERE id_empresa_avaliada = e.id_empresa AND aprovado=1) as total_avaliacoes,
                (SELECT COUNT(*) FROM produtos_empresa WHERE id_empresa = e.id_empresa) as total_produtos
                FROM empresas e WHERE e.tipo_empresa IN ('vendedor', 'ambos') AND e.ativo = 1
            """)
            empresas_db = cursor.fetchall()
            
            empresas_fmt = []
            for emp in empresas_db:
                empresas_fmt.append({
                    'id_empresa': emp['id_empresa'],
                    'nome': emp['nome_fantasia'] or emp['razao_social'],
                    'logo': (emp['nome_fantasia'] or emp['razao_social'])[0].upper(),
                    'categoria': 'Tecnologia',
                    'avaliacao': float(emp['avaliacao'] or 0),
                    'total_avaliacoes': emp['total_avaliacoes'],
                    'total_produtos': emp['total_produtos'],
                    'tempo_mercado': f"{datetime.now().year - emp['data_cadastro'].year} anos",
                    'features': ['Entrega Garantida', 'Suporte']
                })
            
            usuario_comprou = []
            if 'usuario_id' in session:
                cursor.execute("SELECT DISTINCT id_empresa_compradora FROM pedidos WHERE id_cliente = %s AND status = 'entregue'", (session['usuario_id'],))
                usuario_comprou = [row['id_empresa_compradora'] for row in cursor.fetchall()]

            return render_template('empresas_vendedoras.html', empresas=empresas_fmt, usuario_comprou_em_lojas=usuario_comprou)
        finally:
            if conn: conn.close()

    @app.route('/empresa/<int:id_empresa>')
    def detalhes_empresa_publica(id_empresa):
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM empresas WHERE id_empresa = %s", (id_empresa,))
            empresa = cursor.fetchone()
            if not empresa: return redirect(url_for('listar_lojas'))
            
            cursor.execute("SELECT p.*, pe.preco_empresa, pe.estoque_empresa FROM produtos_empresa pe JOIN produto p ON pe.id_produto = p.id_produto WHERE pe.id_empresa = %s AND pe.ativo = 1", (id_empresa,))
            produtos = cursor.fetchall()
            for p in produtos:
                if p.get('imagens'):
                    try: p['imagens'] = json.loads(p['imagens'])
                    except: p['imagens'] = []

            cursor.execute("SELECT ae.*, c.nome as avaliador_nome FROM avaliacoes_empresas ae LEFT JOIN clientes c ON ae.id_cliente = c.id_cliente WHERE ae.id_empresa_avaliada = %s AND ae.aprovado = 1 ORDER BY ae.data_avaliacao DESC LIMIT 30", (id_empresa,))
            avaliacoes = cursor.fetchall()
            
            cursor.execute("SELECT AVG(nota) as media_notas, COUNT(*) as total_avaliacoes FROM avaliacoes_empresas WHERE id_empresa_avaliada = %s AND aprovado = 1", (id_empresa,))
            media_avaliacoes = cursor.fetchone()
            
            pode_avaliar = False
            pode_comprar = False # Variável nova para controlar o botão
            motivo = "nao_logado"
            
            # --- Lógica de Permissão de COMPRA ---
            if 'usuario_id' in session:
                # Cliente pessoa física pode comprar
                pode_comprar = True
                
                # Check avaliação
                cursor.execute("SELECT id_avaliacao FROM avaliacoes_empresas WHERE id_empresa_avaliada=%s AND id_cliente=%s", (id_empresa, session['usuario_id']))
                if cursor.fetchone(): motivo = "ja_avaliou"
                else: pode_avaliar = True
            
            elif 'empresa_id' in session:
                meu_id = session['empresa_id']
                cursor.execute("SELECT tipo_empresa FROM empresas WHERE id_empresa=%s", (meu_id,))
                eu = cursor.fetchone()
                
                if meu_id == id_empresa:
                    motivo = "voce_e_a_empresa"
                    pode_comprar = False # Não pode comprar de si mesmo
                elif eu and eu['tipo_empresa'] in ['comprador', 'ambos']:
                    pode_comprar = True # Empresa compradora pode comprar
                else:
                    pode_comprar = False # Empresa VENDEDORA pura não pode comprar
            else:
                # Visitante não logado vê botão mas será redirecionado
                pode_comprar = True 

            return render_template('empresa_detalhes_publica.html', 
                                 empresa=empresa, 
                                 produtos=produtos, 
                                 avaliacoes=avaliacoes, 
                                 media_avaliacoes=media_avaliacoes, 
                                 pode_avaliar=pode_avaliar, 
                                 pode_comprar=pode_comprar, # Passando pro template
                                 motivo_bloqueio=motivo)
        finally:
            if conn: conn.close()

    @app.route('/avaliar_empresa/<int:id_empresa>', methods=['POST'], endpoint='empresa_avaliar')
    @login_required
    def avaliar_empresa(id_empresa):
        if 'empresa_id' in session and session['empresa_id'] == id_empresa:
            flash('Auto-avaliação proibida.', 'error')
            return redirect(url_for('detalhes_empresa_publica', id_empresa=id_empresa))
        
        nota = request.form.get('nota', type=int)
        comentario = request.form.get('comentario')
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO avaliacoes_empresas (id_empresa_avaliada, id_cliente, nota, comentario, aprovado) VALUES (%s,%s,%s,%s,1)", 
                         (id_empresa, session.get('usuario_id'), nota, comentario))
            conn.commit()
            conn.close()
            flash('Avaliação enviada!', 'success')
        except Exception as e:
            flash(f'Erro: {e}', 'error')
        return redirect(url_for('detalhes_empresa_publica', id_empresa=id_empresa))

    @app.route('/seguir_loja/<int:id_empresa>', methods=['POST'])
    @login_required
    def seguir_loja(id_empresa):
        if 'usuario_id' not in session: return redirect(url_for('login'))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM seguidores WHERE id_cliente=%s AND id_empresa=%s", (session['usuario_id'], id_empresa))
        if cursor.fetchone():
            cursor.execute("DELETE FROM seguidores WHERE id_cliente=%s AND id_empresa=%s", (session['usuario_id'], id_empresa))
            flash('Deixou de seguir.', 'info')
        else:
            cursor.execute("INSERT INTO seguidores (id_cliente, id_empresa) VALUES (%s,%s)", (session['usuario_id'], id_empresa))
            flash('Seguindo!', 'success')
        conn.commit()
        conn.close()
        return redirect(request.referrer)

    # ==========================================================================
    # 6. DADOS & CONFIG
    # ==========================================================================
    @app.route('/empresa/atualizar_dados', methods=['POST'])
    @login_required
    def atualizar_dados_empresa():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE empresas SET nome_fantasia=%s, razao_social=%s, email=%s, telefone=%s WHERE id_empresa=%s",
                     (request.form['nome_fantasia'], request.form['razao_social'], request.form['email'], request.form['telefone'], session['empresa_id']))
        conn.commit()
        conn.close()
        flash('Atualizado.', 'success')
        return redirect(url_for('painel_empresa'))

    @app.route('/empresa/alterar_tipo', methods=['POST'])
    @login_required
    def alterar_tipo_empresa():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE empresas SET tipo_empresa=%s WHERE id_empresa=%s", (request.form['tipo_empresa'], session['empresa_id']))
        conn.commit()
        conn.close()
        flash('Tipo de empresa alterado.', 'success')
        return redirect(url_for('painel_empresa'))

    @app.route('/empresa/alterar_senha', methods=['POST'])
    @login_required
    def alterar_senha_empresa():
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT senha FROM empresas WHERE id_empresa=%s", (session['empresa_id'],))
        emp = cursor.fetchone()
        if check_password_hash(emp['senha'], request.form['senha_atual']):
            if request.form['nova_senha'] == request.form['confirmar_senha']:
                cursor.execute("UPDATE empresas SET senha=%s WHERE id_empresa=%s", (generate_password_hash(request.form['nova_senha']), session['empresa_id']))
                conn.commit()
                flash('Senha alterada', 'success')
            else: flash('Senhas não conferem', 'error')
        else: flash('Senha atual errada', 'error')
        conn.close()
        return redirect(url_for('painel_empresa'))

    @app.route('/empresa/atualizar_preferencias', methods=['POST'])
    @login_required
    def atualizar_preferencias_empresa():
        tema = 1 if request.form.get('tema_escuro') == 'on' else 0
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE empresas SET tema_escuro=%s WHERE id_empresa=%s", (tema, session['empresa_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('painel_empresa'))

    # ==========================================================================
    # 7. GESTÃO DE VAGAS
    # ==========================================================================
    @app.route('/empresa/vagas')
    @login_required
    def gerenciar_vagas():
        if 'empresa_id' not in session: return redirect(url_for('login_empresa_view'))
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM vagas ORDER BY data_publicacao DESC") 
        vagas = cursor.fetchall()
        conn.close()
        return render_template('empresa_vagas.html', vagas=vagas)

    @app.route('/empresa/criar-vaga', methods=['POST'])
    @login_required
    def criar_vaga():
        try:
            titulo = request.form.get('titulo')
            descricao = request.form.get('descricao')
            slug = secure_filename(titulo.lower().replace(' ', '-')) + f"-{uuid4().hex[:4]}"
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO vagas (titulo, slug, descricao, requisitos, tipo, status) VALUES (%s, %s, %s, 'Requisitos padrão', 'CLT', 'aberta')", (titulo, slug, descricao))
            conn.commit()
            conn.close()
            flash('Vaga publicada!', 'success')
        except Exception as e:
            flash(f'Erro: {e}', 'error')
        return redirect(url_for('gerenciar_vagas'))