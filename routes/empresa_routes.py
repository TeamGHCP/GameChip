from flask import render_template, request, redirect, url_for, session, flash, jsonify
from models.database import get_db_connection
from utils.decorators import login_required
import json
import mysql.connector
from datetime import datetime

def configure_empresa_routes(app):
    
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
            
            # Buscar produtos disponíveis para adicionar
            cursor.execute("""
                SELECT p.id_produto, p.nome, p.marca, p.preco, p.categoria
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
            
            # Buscar avaliações da empresa
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
            
            # Calcular média de avaliações
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
        """Página pública de detalhes da empresa"""
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('inicio'))
            
            cursor = conn.cursor(dictionary=True)
            
            # Buscar dados da empresa
            cursor.execute("""
                SELECT * FROM empresas 
                WHERE id_empresa = %s AND tipo_empresa IN ('vendedor', 'ambos')
            """, (id_empresa,))
            
            empresa = cursor.fetchone()
            
            if not empresa:
                flash('Empresa não encontrada.', 'error')
                return redirect(url_for('inicio'))
            
            # Buscar produtos da empresa
            cursor.execute("""
                SELECT p.*, pe.preco_empresa, pe.estoque_empresa
                FROM produtos_empresa pe
                JOIN produto p ON pe.id_produto = p.id_produto
                WHERE pe.id_empresa = %s AND pe.ativo = TRUE AND p.ativo = TRUE
                ORDER BY p.nome
            """, (id_empresa,))
            
            produtos = cursor.fetchall()
            
            # Processar imagens
            for produto in produtos:
                if produto.get('imagens'):
                    try:
                        produto['imagens'] = json.loads(produto['imagens'])
                    except:
                        produto['imagens'] = []
            
            # Buscar avaliações da empresa
            cursor.execute("""
                SELECT ae.*, COALESCE(c.nome, 'Usuário') as avaliador_nome
                FROM avaliacoes_empresas ae
                LEFT JOIN clientes c ON ae.id_cliente = c.id_cliente
                WHERE ae.id_empresa_avaliada = %s AND ae.aprovado = TRUE
                ORDER BY ae.data_avaliacao DESC
                LIMIT 20
            """, (id_empresa,))
            
            avaliacoes = cursor.fetchall()
            
            # Calcular média de avaliações
            cursor.execute("""
                SELECT AVG(nota) as media_notas, COUNT(*) as total_avaliacoes
                FROM avaliacoes_empresas
                WHERE id_empresa_avaliada = %s AND aprovado = TRUE
            """, (id_empresa,))
            
            media_avaliacoes = cursor.fetchone()
            
            # Verificar se usuário pode avaliar (se comprou da empresa)
            pode_avaliar = False
            if session.get('usuario_id'):
                # CORREÇÃO REALIZADA AQUI: Mudado de pedido_itens para itens_pedido
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
            # Mostra o erro detalhado se houver
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
            
            # Buscar produtos que ainda não foram adicionados pela empresa
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
            
            # Processar imagens
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
            
            # Verificar se produto já foi adicionado
            cursor.execute("""
                SELECT id_produto_empresa FROM produtos_empresa 
                WHERE id_empresa = %s AND id_produto = %s
            """, (session['empresa_id'], id_produto))
            
            if cursor.fetchone():
                flash('⚠️ Este produto já foi adicionado à sua loja.', 'warning')
                return redirect(url_for('painel_empresa'))
            
            # Inserir produto na loja da empresa
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
            
            # Verificar se o produto pertence à empresa
            cursor.execute("""
                SELECT id_produto_empresa FROM produtos_empresa 
                WHERE id_produto_empresa = %s AND id_empresa = %s
            """, (id_produto_empresa, session['empresa_id']))
            
            if not cursor.fetchone():
                flash('❌ Produto não encontrado.', 'error')
                return redirect(url_for('painel_empresa'))
            
            # Remover produto
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
            
            cursor = conn.cursor()
            
            # Atualizar produto
            cursor.execute("""
                UPDATE produtos_empresa 
                SET preco_empresa = %s, estoque_empresa = %s, ativo = %s
                WHERE id_produto_empresa = %s AND id_empresa = %s
            """, (preco_empresa, estoque_empresa, ativo, id_produto_empresa, session['empresa_id']))
            
            conn.commit()
            
            return jsonify({'success': True, 'message': 'Produto atualizado com sucesso!'})
        
        except mysql.connector.Error as err:
            return jsonify({'success': False, 'error': str(err)}), 500
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    # Adicione esta nova rota dentro da função configure_auth_routes(app):

    @app.route('/seguir_loja/<int:id_empresa>', methods=['POST'])
    @login_required
    def seguir_loja(id_empresa):
        """
        Permite ao cliente seguir ou deixar de seguir uma empresa (loja).
        
        A URL deve ser acessada via POST (preferencialmente de um botão/formulário) 
        para evitar que um simples clique em um link mude o estado.
        """
        # Verifica se o usuário logado é um cliente (não uma empresa)
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
            
            # 1. Verificar se a empresa existe
            cursor.execute("SELECT id_empresa, nome_fantasia FROM empresas WHERE id_empresa = %s", (id_empresa,))
            empresa = cursor.fetchone()
            if not empresa:
                flash('❌ Loja não encontrada.', 'error')
                return redirect(url_for('inicio'))
            
            # 2. Verificar se o cliente JÁ está seguindo a loja
            cursor.execute("""
                SELECT id_seguidor FROM seguidores 
                WHERE id_cliente = %s AND id_empresa = %s
            """, (cliente_id, id_empresa))
            
            esta_seguindo = cursor.fetchone()
            
            if esta_seguindo:
                # 3. Se estiver seguindo, DEIXA DE SEGUIR (DELETE)
                cursor.execute("""
                    DELETE FROM seguidores 
                    WHERE id_seguidor = %s
                """, (esta_seguindo[0],))
                mensagem = f'💔 Você deixou de seguir a loja "{empresa[1]}".'
                
            else:
                # 4. Se NÃO estiver seguindo, PASSA A SEGUIR (INSERT)
                # O 'data_seguimento' pode ser a data atual (datetime.now())
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
        
        # Redireciona para a página anterior, ou para a página da loja/início
        return redirect(request.referrer or url_for('inicio'))