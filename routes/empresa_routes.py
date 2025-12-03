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

def configure_empresa_routes(app):
    
    # Função auxiliar para verificar arquivos permitidos
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

    @app.route('/painel-empresa')
    @login_required
    def painel_empresa():
        if 'empresa_id' not in session:
            flash('⚠️ Acesso restrito para empresas.', 'warning')
            return redirect(url_for('login'))
        
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('inicio'))
            
            cursor = conn.cursor(dictionary=True)
            
            # Buscar dados da empresa
            cursor.execute("SELECT * FROM empresas WHERE id_empresa = %s", (session['empresa_id'],))
            empresa = cursor.fetchone()
            
            if not empresa:
                flash('Erro ao carregar dados da empresa.', 'error')
                return redirect(url_for('inicio'))
            
            # Buscar produtos da empresa
            cursor.execute("""
                SELECT pe.*, p.nome, p.marca, p.categoria, p.imagens
                FROM produtos_empresa pe
                JOIN produto p ON pe.id_produto = p.id_produto
                WHERE pe.id_empresa = %s
                ORDER BY pe.data_cadastro DESC
            """, (session['empresa_id'],))
            produtos_empresa = cursor.fetchall()
            
            # Processar imagens
            for produto in produtos_empresa:
                if produto.get('imagens'):
                    try:
                        produto['imagens'] = json.loads(produto['imagens'])
                    except:
                        produto['imagens'] = []
            
            # Buscar produtos disponíveis para adicionar (Catálogo Existente)
            cursor.execute("""
                SELECT p.id_produto, p.nome, p.marca, p.preco, p.estoque, p.categoria
                FROM produto p 
                WHERE p.ativo = TRUE 
                AND p.id_produto NOT IN (
                    SELECT pe.id_produto FROM produtos_empresa pe 
                    WHERE pe.id_empresa = %s AND pe.ativo = TRUE
                )
                ORDER BY p.nome
                LIMIT 50
            """, (session['empresa_id'],))
            produtos_disponiveis = cursor.fetchall()
            
            # Buscar estatísticas
            cursor.execute("""
                SELECT COUNT(*) as total_vendas, COALESCE(SUM(total), 0) as receita_total
                FROM pedidos WHERE id_cliente IN (
                    SELECT id_cliente FROM clientes WHERE email = %s
                )
            """, (empresa['email'],))
            stats = cursor.fetchone()
            
            # Buscar avaliações
            cursor.execute("""
                SELECT ae.*, COALESCE(c.nome, e.nome_fantasia, e.razao_social) as avaliador_nome
                FROM avaliacoes_empresas ae
                LEFT JOIN clientes c ON ae.id_cliente = c.id_cliente
                LEFT JOIN empresas e ON ae.id_empresa_avaliadora = e.id_empresa
                WHERE ae.id_empresa_avaliada = %s AND ae.aprovado = TRUE
                ORDER BY ae.data_avaliacao DESC
                LIMIT 10
            """, (session['empresa_id'],))
            avaliacoes = cursor.fetchall()
            
            # Calcular média
            cursor.execute("""
                SELECT AVG(nota) as media_notas, COUNT(*) as total_avaliacoes
                FROM avaliacoes_empresas
                WHERE id_empresa_avaliada = %s AND aprovado = TRUE
            """, (session['empresa_id'],))
            media_avaliacoes = cursor.fetchone()
            
            return render_template('painel_empresa.html', 
                                 empresa=empresa,
                                 produtos_empresa=produtos_empresa,
                                 produtos_disponiveis=produtos_disponiveis,
                                 stats=stats,
                                 avaliacoes=avaliacoes,
                                 media_avaliacoes=media_avaliacoes)
        
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar painel: {err}', 'error')
            return redirect(url_for('inicio'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/empresa/<int:id_empresa>')
    def detalhes_empresa_publica(id_empresa):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('inicio'))
            
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT * FROM empresas 
                WHERE id_empresa = %s AND tipo_empresa IN ('vendedor', 'ambos')
            """, (id_empresa,))
            
            empresa = cursor.fetchone()
            
            if not empresa:
                flash('Empresa não encontrada.', 'error')
                return redirect(url_for('inicio'))
            
            # Busca produtos vinculados
            cursor.execute("""
                SELECT p.*, pe.preco_empresa, pe.estoque_empresa
                FROM produtos_empresa pe
                JOIN produto p ON pe.id_produto = p.id_produto
                WHERE pe.id_empresa = %s AND pe.ativo = TRUE AND p.ativo = TRUE
                ORDER BY p.nome
            """, (id_empresa,))
            
            produtos = cursor.fetchall()
            
            for produto in produtos:
                if produto.get('imagens'):
                    try:
                        produto['imagens'] = json.loads(produto['imagens'])
                    except:
                        produto['imagens'] = []
            
            cursor.execute("""
                SELECT ae.*, COALESCE(c.nome, 'Usuário') as avaliador_nome
                FROM avaliacoes_empresas ae
                LEFT JOIN clientes c ON ae.id_cliente = c.id_cliente
                WHERE ae.id_empresa_avaliada = %s AND ae.aprovado = TRUE
                ORDER BY ae.data_avaliacao DESC
                LIMIT 20
            """, (id_empresa,))
            
            avaliacoes = cursor.fetchall()
            
            cursor.execute("""
                SELECT AVG(nota) as media_notas, COUNT(*) as total_avaliacoes
                FROM avaliacoes_empresas
                WHERE id_empresa_avaliada = %s AND aprovado = TRUE
            """, (id_empresa,))
            
            media_avaliacoes = cursor.fetchone()
            
            pode_avaliar = False
            if session.get('usuario_id'):
                cursor.execute("""
                    SELECT COUNT(*) as comprou 
                    FROM pedidos p
                    JOIN itens_pedido pi ON p.id_pedido = pi.id_pedido
                    JOIN produtos_empresa pe ON pi.id_produto = pe.id_produto
                    WHERE p.id_cliente = %s AND pe.id_empresa = %s
                    LIMIT 1
                """, (session['usuario_id'], id_empresa))
                
                comprou_result = cursor.fetchone()
                pode_avaliar = comprou_result and comprou_result['comprou'] > 0
            
            return render_template('empresa_detalhes_publica.html',
                             empresa=empresa,
                             produtos=produtos,
                             avaliacoes=avaliacoes,
                             media_avaliacoes=media_avaliacoes,
                             pode_avaliar=pode_avaliar)
    
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar dados da empresa: {err}', 'error')
            return redirect(url_for('inicio'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
   
    @app.route('/api/produtos-disponiveis')
    @login_required
    def api_produtos_disponiveis():
        if 'empresa_id' not in session:
            return jsonify({'error': 'Acesso não autorizado'}), 403
        
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify({'error': 'Erro de conexão'}), 500
            
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT p.id_produto, p.nome, p.marca, p.preco, p.estoque, p.categoria, p.imagens
                FROM produto p 
                WHERE p.ativo = TRUE 
                AND p.id_produto NOT IN (
                    SELECT pe.id_produto FROM produtos_empresa pe 
                    WHERE pe.id_empresa = %s AND pe.ativo = TRUE
                )
                ORDER BY p.nome
            """, (session['empresa_id'],))
            
            produtos = cursor.fetchall()
            
            for produto in produtos:
                if produto.get('imagens'):
                    try:
                        produto['imagens'] = json.loads(produto['imagens'])
                    except:
                        produto['imagens'] = []
            
            return jsonify(produtos)
        
        except mysql.connector.Error as err:
            return jsonify({'error': str(err)}), 500
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    # --- CORREÇÃO AQUI ---
    @app.route('/empresa/cadastrar-novo-produto', methods=['POST'])
    @login_required
    def cadastrar_novo_produto_empresa():
        if 'empresa_id' not in session:
            flash('❌ Acesso não autorizado.', 'error')
            return redirect(url_for('painel_empresa'))
        
        try:
            nome = request.form.get('nome', '').strip()
            marca = request.form.get('marca', '').strip()
            categoria = request.form.get('categoria', '').strip()
            descricao = request.form.get('descricao', '').strip()
            preco = request.form.get('preco', '0').replace(',', '.')
            estoque_inicial = int(request.form.get('estoque', '0')) # Convertendo para inteiro
            
            if not all([nome, marca, categoria, preco]):
                flash('❌ Preencha os campos obrigatórios.', 'error')
                return redirect(url_for('painel_empresa'))

            conn = get_db_connection()
            if not conn:
                flash('❌ Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('painel_empresa'))
            
            cursor = conn.cursor()

            imagens = []
            if 'imagens' in request.files:
                files = request.files.getlist('imagens')
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        unique_filename = f"{uuid4().hex}_{filename}"
                        filepath = os.path.join(Config.UPLOAD_FOLDER, unique_filename)
                        os.makedirs(os.path.dirname(filepath), exist_ok=True)
                        file.save(filepath)
                        imagens.append(unique_filename)
            
            # CORREÇÃO CRÍTICA: Passando estoque_inicial para o INSERT global também
            # Antes estava 0, o que fazia o produtos.html mostrar "Esgotado"
            cursor.execute("""
                INSERT INTO produto (nome, marca, preco, descricao, estoque, categoria, imagens, ativo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
            """, (nome, marca, float(preco), descricao, estoque_inicial, categoria, json.dumps(imagens) if imagens else None))
            
            novo_id_produto = cursor.lastrowid
            
            # Inserindo na tabela da empresa
            cursor.execute("""
                INSERT INTO produtos_empresa (id_empresa, id_produto, preco_empresa, estoque_empresa, ativo)
                VALUES (%s, %s, %s, %s, TRUE)
            """, (session['empresa_id'], novo_id_produto, float(preco), estoque_inicial))
            
            conn.commit()
            
            flash('✅ Produto criado e adicionado à sua loja com sucesso!', 'success')
            return redirect(url_for('painel_empresa'))
            
        except mysql.connector.Error as err:
            flash(f'❌ Erro ao cadastrar produto: {err}', 'error')
            return redirect(url_for('painel_empresa'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/empresa/adicionar-produto', methods=['POST'])
    @login_required
    def adicionar_produto_empresa():
        if 'empresa_id' not in session:
            flash('❌ Acesso não autorizado.', 'error')
            return redirect(url_for('painel_empresa'))
        
        try:
            id_produto = request.form.get('id_produto', type=int)
            preco_empresa = request.form.get('preco_empresa', type=float)
            estoque_empresa = request.form.get('estoque_empresa', type=int)
            ativo = request.form.get('ativo') == 'on'
            
            if not all([id_produto, preco_empresa is not None, estoque_empresa is not None]):
                flash('❌ Preencha todos os campos obrigatórios.', 'error')
                return redirect(url_for('painel_empresa'))
            
            conn = get_db_connection()
            if not conn:
                flash('❌ Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('painel_empresa'))
            
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id_produto_empresa FROM produtos_empresa 
                WHERE id_empresa = %s AND id_produto = %s
            """, (session['empresa_id'], id_produto))
            
            if cursor.fetchone():
                flash('⚠️ Este produto já foi adicionado à sua loja.', 'warning')
                return redirect(url_for('painel_empresa'))
            
            cursor.execute("""
                INSERT INTO produtos_empresa (id_empresa, id_produto, preco_empresa, estoque_empresa, ativo)
                VALUES (%s, %s, %s, %s, %s)
            """, (session['empresa_id'], id_produto, preco_empresa, estoque_empresa, ativo))
            
            conn.commit()
            
            flash('✅ Produto adicionado à sua loja com sucesso!', 'success')
            return redirect(url_for('painel_empresa'))
        
        except mysql.connector.Error as err:
            flash(f'❌ Erro ao adicionar produto: {err}', 'error')
            return redirect(url_for('painel_empresa'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/empresa/remover-produto/<int:id_produto_empresa>', methods=['POST'])
    @login_required
    def remover_produto_empresa(id_produto_empresa):
        if 'empresa_id' not in session:
            flash('❌ Acesso não autorizado.', 'error')
            return redirect(url_for('painel_empresa'))
        
        try:
            conn = get_db_connection()
            if not conn:
                flash('❌ Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('painel_empresa'))
            
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id_produto_empresa FROM produtos_empresa 
                WHERE id_produto_empresa = %s AND id_empresa = %s
            """, (id_produto_empresa, session['empresa_id']))
            
            if not cursor.fetchone():
                flash('❌ Produto não encontrado.', 'error')
                return redirect(url_for('painel_empresa'))
            
            cursor.execute("""
                DELETE FROM produtos_empresa 
                WHERE id_produto_empresa = %s AND id_empresa = %s
            """, (id_produto_empresa, session['empresa_id']))
            
            conn.commit()
            
            flash('🗑️ Produto removido da sua loja com sucesso!', 'success')
            return redirect(url_for('painel_empresa'))
        
        except mysql.connector.Error as err:
            flash(f'❌ Erro ao remover produto: {err}', 'error')
            return redirect(url_for('painel_empresa'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
                
    @app.route('/empresa/atualizar_dados', methods=['POST'])
    @login_required
    def atualizar_dados_empresa():
        if 'empresa_id' not in session:
            return redirect(url_for('login'))
            
        nome_fantasia = request.form.get('nome_fantasia')
        razao_social = request.form.get('razao_social')
        email = request.form.get('email')
        telefone = request.form.get('telefone')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE empresas 
                SET nome_fantasia = %s, razao_social = %s, email = %s, telefone = %s
                WHERE id_empresa = %s
            """, (nome_fantasia, razao_social, email, telefone, session['empresa_id']))
            conn.commit()
            
            session['empresa_nome'] = nome_fantasia or razao_social
            
            flash('✅ Dados atualizados com sucesso!', 'success')
        except Exception as e:
            flash(f'❌ Erro ao atualizar: {e}', 'error')
        finally:
            if conn: conn.close()
            
        return redirect(url_for('painel_empresa'))
    
    @app.route('/empresa/alterar_tipo', methods=['POST'])
    @login_required
    def alterar_tipo_empresa():
        if 'empresa_id' not in session:
            return redirect(url_for('login'))
            
        novo_tipo = request.form.get('tipo_empresa')
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE empresas SET tipo_empresa = %s WHERE id_empresa = %s", 
                         (novo_tipo, session['empresa_id']))
            conn.commit()
            session['empresa_tipo'] = novo_tipo
            flash('✅ Tipo de empresa atualizado!', 'success')
        except Exception as e:
            flash(f'❌ Erro: {e}', 'error')
        finally:
            if conn: conn.close()
            
        return redirect(url_for('painel_empresa'))
    
    @app.route('/empresa/alterar_senha', methods=['POST'])
    @login_required
    def alterar_senha_empresa():
        if 'empresa_id' not in session:
            return redirect(url_for('login'))
            
        senha_atual = request.form.get('senha_atual')
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')
        
        if nova_senha != confirmar_senha:
            flash('❌ As novas senhas não coincidem.', 'error')
            return redirect(url_for('painel_empresa'))
            
        from werkzeug.security import generate_password_hash, check_password_hash
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT senha FROM empresas WHERE id_empresa = %s", (session['empresa_id'],))
            empresa = cursor.fetchone()
            
            if not empresa or not check_password_hash(empresa['senha'], senha_atual):
                flash('❌ Senha atual incorreta.', 'error')
                return redirect(url_for('painel_empresa'))
                
            nova_hash = generate_password_hash(nova_senha)
            cursor.execute("UPDATE empresas SET senha = %s WHERE id_empresa = %s", 
                         (nova_hash, session['empresa_id']))
            conn.commit()
            
            flash('🔒 Senha alterada com sucesso!', 'success')
        except Exception as e:
            flash(f'❌ Erro ao alterar senha: {e}', 'error')
        finally:
            if conn: conn.close()
            
        return redirect(url_for('painel_empresa'))

    @app.route('/empresa/atualizar-produto/<int:id_produto_empresa>', methods=['POST'])
    @login_required
    def atualizar_produto_empresa(id_produto_empresa):
        if 'empresa_id' not in session:
            return jsonify({'success': False, 'error': 'Acesso não autorizado'}), 403
        
        try:
            data = request.get_json()
            preco_empresa = data.get('preco_empresa')
            estoque_empresa = data.get('estoque_empresa')
            ativo = data.get('ativo')
            
            conn = get_db_connection()
            if not conn:
                return jsonify({'success': False, 'error': 'Erro de conexão'}), 500
            
            cursor = conn.cursor(dictionary=True)
            
            # 1. Busca o ID do produto global vinculado a este produto da empresa
            cursor.execute("SELECT id_produto FROM produtos_empresa WHERE id_produto_empresa = %s AND id_empresa = %s", 
                          (id_produto_empresa, session['empresa_id']))
            resultado = cursor.fetchone()
            
            if not resultado:
                return jsonify({'success': False, 'error': 'Produto não encontrado'}), 404
                
            id_produto_global = resultado['id_produto']
            
            # 2. Atualiza a tabela da empresa (produtos_empresa)
            cursor.execute("""
                UPDATE produtos_empresa 
                SET preco_empresa = %s, estoque_empresa = %s, ativo = %s
                WHERE id_produto_empresa = %s AND id_empresa = %s
            """, (preco_empresa, estoque_empresa, ativo, id_produto_empresa, session['empresa_id']))
            
            # 3. ATUALIZAÇÃO CRÍTICA: Sincroniza com a tabela global (produto)
            # Isso garante que o site principal veja o novo estoque e preço
            cursor.execute("""
                UPDATE produto 
                SET estoque = %s, preco = %s, ativo = %s
                WHERE id_produto = %s
            """, (estoque_empresa, preco_empresa, ativo, id_produto_global))
            
            conn.commit()
            
            return jsonify({'success': True, 'message': 'Produto atualizado e sincronizado com sucesso!'})
        
        except mysql.connector.Error as err:
            return jsonify({'success': False, 'error': str(err)}), 500
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/seguir_loja/<int:id_empresa>', methods=['POST'])
    @login_required
    def seguir_loja(id_empresa):
        if 'usuario_id' not in session:
            flash('❌ Apenas clientes podem seguir lojas.', 'error')
            return redirect(url_for('inicio'))

        cliente_id = session['usuario_id']
        
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('inicio'))
            
            cursor = conn.cursor()
            
            cursor.execute("SELECT id_empresa, nome_fantasia FROM empresas WHERE id_empresa = %s", (id_empresa,))
            empresa = cursor.fetchone()
            if not empresa:
                flash('❌ Loja não encontrada.', 'error')
                return redirect(url_for('inicio'))
            
            cursor.execute("""
                SELECT id_seguidor FROM seguidores 
                WHERE id_cliente = %s AND id_empresa = %s
            """, (cliente_id, id_empresa))
            
            esta_seguindo = cursor.fetchone()
            
            if esta_seguindo:
                cursor.execute("""
                    DELETE FROM seguidores 
                    WHERE id_seguidor = %s
                """, (esta_seguindo[0],))
                mensagem = f'💔 Você deixou de seguir a loja "{empresa[1]}".'
                
            else:
                cursor.execute("""
                    INSERT INTO seguidores (id_cliente, id_empresa, data_seguimento)
                    VALUES (%s, %s, %s)
                """, (cliente_id, id_empresa, datetime.now()))
                mensagem = f'✅ Você agora está seguindo a loja "{empresa[1]}"! Fique de olho nas novidades.'
            
            conn.commit()
            flash(mensagem, 'success')
            
        except mysql.connector.Error as err:
            flash(f'Erro ao processar seguimento da loja: {err}', 'error')
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
        
        return redirect(request.referrer or url_for('inicio'))

    @app.route('/empresa/atualizar_preferencias', methods=['POST'])
    @login_required
    def atualizar_preferencias_empresa():
        if 'empresa_id' not in session:
            return redirect(url_for('login'))
        
        tema_escuro = request.form.get('tema_escuro') == 'on'
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Nota: Isso requer que a coluna tema_escuro exista na tabela empresas
            cursor.execute("UPDATE empresas SET tema_escuro = %s WHERE id_empresa = %s", 
                           (tema_escuro, session['empresa_id']))
            conn.commit()
            
            session['tema_escuro'] = tema_escuro 
            
            flash('✅ Preferências atualizadas!', 'success')
        except Exception as e:
            flash(f'❌ Erro ao salvar preferências: {e}', 'error')
        finally:
            if conn: conn.close()
            
        return redirect(url_for('painel_empresa'))