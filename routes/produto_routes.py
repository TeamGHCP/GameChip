from flask import render_template, request, flash, redirect, url_for, session
from models.database import get_db_connection
from utils.decorators import login_required
import json
import mysql.connector

def configure_produto_routes(app):
    
    def usuario_comprou_produto(usuario_id, produto_id):
        """Verifica se o usuário comprou o produto (Aceita Aprovado/Enviado/Entregue/Concluido)"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM itens_pedido ip
                JOIN pedidos p ON ip.id_pedido = p.id_pedido
                WHERE p.id_cliente = %s 
                AND ip.id_produto = %s 
                AND p.status IN ('aprovado', 'enviado', 'concluido', 'entregue')
            """, (usuario_id, produto_id))
            resultado = cursor.fetchone()
            return resultado is not None
        except mysql.connector.Error:
            return False
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    
    @app.route('/produtos')
    def listar_produtos():
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('produtos.html', produtos=[], categorias=[], marcas=[])
            
            cursor = conn.cursor(dictionary=True)
            categoria = request.args.get('categoria')
            marca = request.args.get('marca')
            busca = request.args.get('busca')
            
            query = "SELECT * FROM produto WHERE ativo = TRUE"
            params = []
            
            if categoria:
                query += " AND categoria = %s"
                params.append(categoria)
            if marca:
                query += " AND marca = %s"
                params.append(marca)
            if busca:
                query += " AND (nome LIKE %s OR descricao LIKE %s)"
                params.extend([f"%{busca}%", f"%{busca}%"])
            
            query += " ORDER BY data_cadastro DESC"
            
            cursor.execute(query, params)
            produtos = cursor.fetchall()
            
            for produto in produtos:
                if produto.get('imagens'):
                    try:
                        produto['imagens'] = json.loads(produto['imagens'])
                    except:
                        produto['imagens'] = []
            
            cursor.execute("SELECT DISTINCT categoria FROM produto WHERE ativo = TRUE ORDER BY categoria")
            categorias = [row['categoria'] for row in cursor.fetchall()]
            
            cursor.execute("SELECT DISTINCT marca FROM produto WHERE ativo = TRUE ORDER BY marca")
            marcas = [row['marca'] for row in cursor.fetchall()]
            
            return render_template('produtos.html', produtos=produtos, categorias=categorias, marcas=marcas)
        
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar produtos: {err}', 'error')
            return render_template('produtos.html', produtos=[], categorias=[], marcas=[])
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/produto/<int:id_produto>')
    def detalhes_produto(id_produto):
        try:
            conn = get_db_connection()
            if not conn:
                return redirect(url_for('listar_produtos'))
            
            cursor = conn.cursor(dictionary=True)
            
            # 1. Busca o Produto
            cursor.execute("SELECT * FROM produto WHERE id_produto = %s AND ativo = TRUE", (id_produto,))
            produto = cursor.fetchone()
            
            if not produto:
                flash('❌ Produto não encontrado.', 'error')
                return redirect(url_for('listar_produtos'))
            
            if produto.get('imagens'):
                try:
                    produto['imagens'] = json.loads(produto['imagens'])
                except:
                    produto['imagens'] = []
            
            # 2. Busca todas as avaliações
            cursor.execute("""
                SELECT a.*, c.nome as cliente_nome FROM avaliacoes a
                JOIN clientes c ON a.id_cliente = c.id_cliente
                WHERE a.id_produto = %s AND a.aprovado = TRUE ORDER BY a.data_avaliacao DESC
            """, (id_produto,))
            avaliacoes = cursor.fetchall()
            
            # 3. Estatísticas
            cursor.execute("""
                SELECT 
                    AVG(nota) as media,
                    COUNT(*) as total_avaliacoes,
                    SUM(CASE WHEN nota = 5 THEN 1 ELSE 0 END) as cinco_estrelas,
                    SUM(CASE WHEN nota = 4 THEN 1 ELSE 0 END) as quatro_estrelas,
                    SUM(CASE WHEN nota = 3 THEN 1 ELSE 0 END) as tres_estrelas,
                    SUM(CASE WHEN nota = 2 THEN 1 ELSE 0 END) as duas_estrelas,
                    SUM(CASE WHEN nota = 1 THEN 1 ELSE 0 END) as uma_estrela
                FROM avaliacoes 
                WHERE id_produto = %s AND aprovado = TRUE
            """, (id_produto,))
            
            media_avaliacoes = cursor.fetchone()
            if not media_avaliacoes:
                media_avaliacoes = {'media': 0, 'total_avaliacoes': 0, 'cinco_estrelas': 0, 'quatro_estrelas': 0, 'tres_estrelas': 0, 'duas_estrelas': 0, 'uma_estrela': 0}
            
            # 4. Verifica usuário logado
            comprou = False
            minha_avaliacao = None
            
            if 'usuario_id' in session:
                comprou = usuario_comprou_produto(session['usuario_id'], id_produto)
                cursor.execute("""
                    SELECT * FROM avaliacoes 
                    WHERE id_cliente = %s AND id_produto = %s
                """, (session['usuario_id'], id_produto))
                minha_avaliacao = cursor.fetchone()

            return render_template('produto_detalhes.html', 
                                produto=produto, 
                                avaliacoes=avaliacoes,
                                media_avaliacoes=media_avaliacoes,
                                comprou=comprou,
                                minha_avaliacao=minha_avaliacao)
        
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar produto: {err}', 'error')
            return redirect(url_for('listar_produtos'))
        
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/avaliar-produto/<int:id_produto>', methods=['POST'])
    @login_required
    def avaliar_produto(id_produto):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))

        if not usuario_comprou_produto(session['usuario_id'], id_produto):
            flash('❌ Você precisa comprar este produto para avaliar.', 'error')
            return redirect(url_for('detalhes_produto', id_produto=id_produto))
        
        nota = request.form.get('nota', type=int)
        titulo = request.form.get('titulo', '').strip()
        comentario = request.form.get('comentario', '').strip()
        
        if not nota or not comentario:
            flash('❌ Preencha a nota e o comentário.', 'error')
            return redirect(url_for('detalhes_produto', id_produto=id_produto))
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id_avaliacao FROM avaliacoes WHERE id_cliente = %s AND id_produto = %s", 
                         (session['usuario_id'], id_produto))
            existente = cursor.fetchone()
            
            if existente:
                cursor.execute("""
                    UPDATE avaliacoes 
                    SET nota = %s, titulo = %s, comentario = %s, data_avaliacao = NOW()
                    WHERE id_avaliacao = %s
                """, (nota, titulo, comentario, existente[0]))
                flash('✅ Avaliação atualizada com sucesso!', 'success')
            else:
                cursor.execute("""
                    INSERT INTO avaliacoes (id_cliente, id_produto, nota, titulo, comentario, tipo_avaliador, aprovado)
                    VALUES (%s, %s, %s, %s, %s, 'cliente', TRUE)
                """, (session['usuario_id'], id_produto, nota, titulo, comentario))
                flash('✅ Avaliação enviada com sucesso!', 'success')
            
            conn.commit()
        
        except mysql.connector.Error as err:
            flash(f'Erro ao avaliar: {err}', 'error')
        finally:
            if conn and conn.is_connected(): cursor.close(); conn.close()
        
        return redirect(url_for('detalhes_produto', id_produto=id_produto))

    @app.route('/excluir-avaliacao/<int:id_avaliacao>', methods=['POST'])
    @login_required
    def excluir_avaliacao(id_avaliacao):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM avaliacoes WHERE id_avaliacao = %s AND id_cliente = %s", 
                         (id_avaliacao, session['usuario_id']))
            conn.commit()
            
            if cursor.rowcount > 0:
                flash('🗑️ Avaliação excluída com sucesso.', 'success')
            else:
                flash('❌ Erro ao excluir ou permissão negada.', 'error')
                
        except mysql.connector.Error:
            flash('Erro ao excluir.', 'error')
        finally:
            if conn and conn.is_connected(): cursor.close(); conn.close()
            
        return redirect(request.referrer)

    # --- A CORREÇÃO ESTÁ AQUI EMBAIXO ---
    # Mudamos o nome da função de 'minhas_avaliacoes_pendentes' para 'redirecionar_avaliacoes_pendentes'
    # para não conflitar com a rota que já existe no avaliacao_routes.py
    @app.route('/minhas-avaliacoes-pendentes')
    @login_required
    def redirecionar_avaliacoes_pendentes():
        return redirect(url_for('avaliacao.minhas_avaliacoes_pendentes'))

    @app.route('/categorias')
    def categorias():
        try:
            conn = get_db_connection()
            if not conn: return render_template('categorias.html', categorias=[])
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT categoria, COUNT(*) as total_produtos FROM produto WHERE ativo = TRUE GROUP BY categoria ORDER BY categoria")
            categorias_lista = cursor.fetchall()
            return render_template('categorias.html', categorias=categorias_lista)
        except: return render_template('categorias.html', categorias=[])
        finally: 
            if conn and conn.is_connected(): cursor.close(); conn.close()

    @app.route('/marcas')
    def marcas():
        try:
            conn = get_db_connection()
            if not conn: return render_template('marcas.html', marcas=[])
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT marca, COUNT(*) as total_produtos FROM produto WHERE ativo = TRUE GROUP BY marca ORDER BY marca")
            marcas_lista = cursor.fetchall()
            return render_template('marcas.html', marcas=marcas_lista)
        except: return render_template('marcas.html', marcas=[])
        finally:
            if conn and conn.is_connected(): cursor.close(); conn.close()