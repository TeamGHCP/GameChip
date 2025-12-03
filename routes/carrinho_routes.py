from flask import render_template, request, flash, redirect, url_for, session, jsonify
from models.database import get_db_connection
from utils.decorators import login_required
from utils.qrcode_generator import gerar_qrcode_pix
import mysql.connector
import json
import random
from datetime import datetime, timedelta  # Adicionado no topo

def configure_carrinho_routes(app):
    
    @app.route('/carrinho')
    def carrinho():
        carrinho_items = session.get('carrinho', [])
        total_itens = sum(item['quantidade'] for item in carrinho_items)
        total_preco = sum(item['preco'] * item['quantidade'] for item in carrinho_items)
        return render_template('carrinho.html', produtos_carrinho=carrinho_items, total_itens=total_itens, total_preco=total_preco, total_geral=total_preco)

    @app.route('/adicionar-carrinho/<int:id_produto>', methods=['POST'])
    def adicionar_carrinho(id_produto):
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('listar_produtos'))
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM produto WHERE id_produto = %s AND ativo = TRUE", (id_produto,))
            produto = cursor.fetchone()
            if not produto:
                flash('❌ Produto não encontrado.', 'error')
                return redirect(url_for('listar_produtos'))
            if 'carrinho' not in session:
                session['carrinho'] = []
            carrinho = session['carrinho']
            produto_no_carrinho = next((item for item in carrinho if item['id_produto'] == id_produto), None)
            quantidade = int(request.form.get('quantidade', 1))
            
            imagens_produto = []
            if produto.get('imagens'):
                try:
                    imagens_produto = json.loads(produto['imagens'])
                except:
                    imagens_produto = []
            elif produto.get('imagem'):
                imagens_produto = [produto['imagem']]
            
            if produto_no_carrinho:
                produto_no_carrinho['quantidade'] += quantidade
            else:
                carrinho.append({
                    'id_produto': produto['id_produto'],
                    'nome': produto['nome'],
                    'preco': float(produto['preco']),
                    'quantidade': quantidade,
                    'imagens': imagens_produto,
                    'categoria': produto['categoria']
                })
            session['carrinho'] = carrinho
            session.modified = True
            flash(f'✅ {produto["nome"]} adicionado ao carrinho!', 'success')
            return redirect(url_for('listar_produtos'))
        except mysql.connector.Error as err:
            flash(f'Erro ao adicionar produto ao carrinho: {err}', 'error')
            return redirect(url_for('listar_produtos'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/remover-carrinho/<int:id_produto>', methods=['POST'])
    def remover_carrinho(id_produto):
        if 'carrinho' in session:
            carrinho = session['carrinho']
            session['carrinho'] = [item for item in carrinho if item['id_produto'] != id_produto]
            session.modified = True
            flash('🗑️ Produto removido do carrinho!', 'success')
        return redirect(url_for('carrinho'))

    @app.route('/atualizar-carrinho', methods=['POST'])
    def atualizar_carrinho():
        if 'carrinho' in session:
            carrinho = session['carrinho']
            carrinho_dict = {item['id_produto']: item for item in carrinho}
            carrinho_atualizado = []
            for key, value in request.form.items():
                if key.startswith('quantidade_'):
                    try:
                        id_produto = int(key.split('_')[1])
                        nova_quantidade = int(value)
                        if id_produto in carrinho_dict:
                            item = carrinho_dict[id_produto]
                            if nova_quantidade > 0:
                                item['quantidade'] = nova_quantidade
                                carrinho_atualizado.append(item)
                    except ValueError:
                        continue
            session['carrinho'] = carrinho_atualizado
            session.modified = True
            flash('✅ Carrinho atualizado!', 'success')
        return redirect(url_for('carrinho'))

    @app.route('/limpar-carrinho', methods=['POST'])
    def limpar_carrinho():
        session.pop('carrinho', None)
        flash('🗑️ Carrinho limpo!', 'success')
        return redirect(url_for('carrinho'))

    @app.route('/gerar-pix/<float:valor>')
    def gerar_pix(valor):
        qr_base64, copia_cola = gerar_qrcode_pix(valor)
        return render_template('gerar_pix.html', valor=valor, qr_base64=qr_base64, copia_cola=copia_cola)
    
    @app.route('/processar-checkout', methods=['POST'])
    @login_required
    def processar_checkout():
        """Processa o checkout e redireciona para a página de pagamento apropriada"""
        try:
            # Dados do formulário
            nome = request.form.get('nome')
            email = request.form.get('email')
            endereco = request.form.get('endereco')
            pagamento = request.form.get('pagamento')
            total_geral = float(request.form.get('total_geral', 0))
            
            produtos_carrinho = session.get('carrinho', [])
            
            if not produtos_carrinho:
                return jsonify({'status': 'error', 'message': 'Carrinho vazio'}), 400
            
            # Verificar estoque
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            for item in produtos_carrinho:
                cursor.execute("SELECT estoque FROM produto WHERE id_produto = %s", (item['id_produto'],))
                produto_db = cursor.fetchone()
                if produto_db and produto_db['estoque'] < item['quantidade']:
                    return jsonify({
                        'status': 'error', 
                        'message': f'Estoque insuficiente para {item["nome"]}'
                    }), 400
            
            # Criar pedido
            cursor.execute("""
                INSERT INTO pedidos (id_cliente, total, forma_pagamento, status, data_pedido)
                VALUES (%s, %s, %s, %s, NOW())
            """, (session['usuario_id'], total_geral, pagamento, 'pendente'))
            pedido_id = cursor.lastrowid
            
            # Adicionar itens ao pedido
            for item in produtos_carrinho:
                cursor.execute("""
                    INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_unitario)
                    VALUES (%s, %s, %s, %s)
                """, (pedido_id, item['id_produto'], item['quantidade'], item['preco']))
                
                # Atualizar estoque
                cursor.execute("""
                    UPDATE produto SET estoque = estoque - %s WHERE id_produto = %s
                """, (item['quantidade'], item['id_produto']))
            
            # Registrar pagamento
            cursor.execute("""
                INSERT INTO pagamentos (nome, email, endereco, metodo, valor, id_pedido)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (nome, email, endereco, pagamento, total_geral, pedido_id))
            
            conn.commit()
            
            # Salvar pedido_id na sessão para usar nas páginas de pagamento
            session['ultimo_pedido_id'] = pedido_id
            session['ultimo_pagamento'] = pagamento
            session.modified = True
            
            # Se for PIX, limpar carrinho imediatamente
            if pagamento == 'pix':
                session.pop('carrinho', None)
            
            return jsonify({
                'status': 'success',
                'pedido_id': pedido_id,
                'message': 'Pedido criado com sucesso'
            })
            
        except Exception as e:
            if 'conn' in locals() and conn.is_connected():
                conn.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/pagamento-cartao')
    @login_required
    def pagamento_cartao():
        """Página de pagamento com cartão"""
        pedido_id = request.args.get('pedido_id', session.get('ultimo_pedido_id'))
        
        if not pedido_id:
            flash('❌ Pedido não encontrado.', 'error')
            return redirect(url_for('carrinho'))
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Buscar dados do pedido
            cursor.execute("""
                SELECT p.*, GROUP_CONCAT(prod.nome SEPARATOR ', ') as produtos
                FROM pedidos p
                LEFT JOIN itens_pedido ip ON p.id_pedido = ip.id_pedido
                LEFT JOIN produto prod ON ip.id_produto = prod.id_produto
                WHERE p.id_pedido = %s AND p.id_cliente = %s
                GROUP BY p.id_pedido
            """, (pedido_id, session['usuario_id']))
            
            pedido = cursor.fetchone()
            
            if not pedido:
                flash('Pedido não encontrado.', 'error')
                return redirect(url_for('carrinho'))
            
            # Buscar itens do carrinho da sessão (ou do pedido)
            produtos_carrinho = session.get('carrinho', [])
            
            return render_template('pagamento-cartao.html',
                                pedido_id=pedido_id,
                                total_geral=pedido['total'],
                                produtos_carrinho=produtos_carrinho)
                                
        except Exception as e:
            flash(f'Erro: {str(e)}', 'error')
            return redirect(url_for('carrinho'))
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/pagamento-boleto')  # CORREÇÃO: nome da rota corrigido
    @login_required
    def pagamento_boleto():  # CORREÇÃO: nome da função alterado
        """Página de geração de boleto"""
        pedido_id = request.args.get('pedido_id', session.get('ultimo_pedido_id'))
        
        if not pedido_id:
            flash('❌ Pedido não encontrado.', 'error')
            return redirect(url_for('carrinho'))
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Buscar dados do pedido
            cursor.execute("SELECT * FROM pedidos WHERE id_pedido = %s AND id_cliente = %s", 
                        (pedido_id, session['usuario_id']))
            
            pedido = cursor.fetchone()
            
            if not pedido:
                flash('Pedido não encontrado.', 'error')
                return redirect(url_for('carrinho'))
            
            # Buscar itens do carrinho da sessão
            produtos_carrinho = session.get('carrinho', [])
            
            # Gerar número de boleto fictício
            boleto_numero = ''.join([str(random.randint(0, 9)) for _ in range(48)])
            
            # Calcular data de vencimento (3 dias úteis)
            vencimento = datetime.now() + timedelta(days=3)
            
            return render_template('pagamento-boleto.html',  # CORREÇÃO: nome do template
                                pedido_id=pedido_id,
                                total_geral=pedido['total'],
                                boleto_numero=boleto_numero,
                                vencimento=vencimento.strftime('%d/%m/%Y'),
                                produtos_carrinho=produtos_carrinho)
                                
        except Exception as e:
            flash(f'Erro: {str(e)}', 'error')
            return redirect(url_for('carrinho'))
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/processar-cartao', methods=['POST'])
    @login_required
    def processar_cartao():
        """Processa pagamento com cartão (simulação)"""
        try:
            pedido_id = request.form.get('pedido_id')
            
            if not pedido_id:
                return jsonify({'status': 'error', 'message': 'Pedido não informado'}), 400
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Atualizar status do pedido para "aprovado"
            cursor.execute("""
                UPDATE pedidos 
                SET status = 'aprovado' 
                WHERE id_pedido = %s AND id_cliente = %s
            """, (pedido_id, session['usuario_id']))
            
            conn.commit()
            
            # Limpar carrinho da sessão
            session.pop('carrinho', None)
            session.modified = True
            
            return jsonify({
                'status': 'success',
                'message': 'Pagamento com cartão aprovado!',
                'redirect': url_for('pagamento_sucesso', metodo='cartao', pedido_id=pedido_id)
            })
            
        except Exception as e:
            if 'conn' in locals() and conn.is_connected():
                conn.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

            # ADICIONE ESTAS ROTAS AQUI - antes da rota /finalizar-carrinho

    # Substitua sua rota /processar-boleto por esta (mudei o status)
    @app.route('/processar-boleto', methods=['POST'])
    @login_required
    def processar_boleto():
        """Processa pagamento com boleto (simulação: limpa carrinho e define status)"""
        try:
            pedido_id = request.form.get('pedido_id')
            
            if not pedido_id:
                return jsonify({'status': 'error', 'message': 'Pedido não informado'}), 400
            
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # O pagamento por boleto NÃO é aprovado na hora. Define status para "aguardando pagamento".
            cursor.execute("""
                UPDATE pedidos 
                SET status = 'aguardando pagamento' 
                WHERE id_pedido = %s AND id_cliente = %s
            """, (pedido_id, session['usuario_id']))
            
            conn.commit()
            
            # Limpar carrinho da sessão
            session.pop('carrinho', None)
            session.modified = True
            
            return jsonify({
                'status': 'success',
                'message': 'Boleto gerado com sucesso!',
                # Redireciona para a página de sucesso, informando que o método foi boleto
                'redirect': url_for('pagamento-sucesso', metodo='boleto', pedido_id=pedido_id)
            })
            
        except Exception as e:
            if 'conn' in locals() and conn.is_connected():
                conn.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/pagamento-sucesso')
    @login_required
    def pagamento_sucesso():
        """Página de confirmação de pagamento bem-sucedido"""
        try:
            pedido_id = request.args.get('pedido_id')
            metodo = request.args.get('metodo', 'cartao')
            
            if not pedido_id:
                flash('❌ Pedido não encontrado.', 'error')
                return redirect(url_for('carrinho'))
            
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Buscar dados do pedido
            cursor.execute("""
                SELECT p.*, DATE_FORMAT(p.data_pedido, '%d/%m/%Y %H:%i') as data_formatada
                FROM pedidos p
                WHERE p.id_pedido = %s AND p.id_cliente = %s
            """, (pedido_id, session['usuario_id']))
            
            pedido = cursor.fetchone()
            
            if not pedido:
                flash('Pedido não encontrado.', 'error')
                return redirect(url_for('carrinho'))
            
            # Formatar valor
            valor_total = f"{pedido['total']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            
            # Gerar número de boleto fictício se for boleto
            boleto_numero = None
            if metodo == 'boleto':
                boleto_numero = ''.join([str(random.randint(0, 9)) for _ in range(48)])
                boleto_numero = f"{boleto_numero[:5]}.{boleto_numero[5:10]} {boleto_numero[10:15]}.{boleto_numero[15:20]} {boleto_numero[20:25]}.{boleto_numero[25:30]} {boleto_numero[30:31]} {boleto_numero[31:]}"
            
            # Altere o return da função pagamento_sucesso() para:
            return render_template('pagamento-sucesso.html',
                pedido_id=pedido_id,
                metodo=metodo,
                valor_total=valor_total,
                data_pedido=pedido['data_formatada'],  # ← AQUI! Já formatado
                boleto_numero=boleto_numero)
                                
        except Exception as e:
            flash(f'Erro: {str(e)}', 'error')
            return redirect(url_for('carrinho'))
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/finalizar-carrinho', methods=['GET', 'POST'])
    def finalizar_carrinho():
        if 'usuario_id' not in session:
            flash('⚠️ Faça login para finalizar sua compra.', 'warning')
            return redirect(url_for('login', next=url_for('finalizar_carrinho')))

        produtos_carrinho = session.get('carrinho', [])
        
        if not produtos_carrinho:
            flash('⚠️ Seu carrinho está vazio.', 'warning')
            return redirect(url_for('carrinho'))

        for produto in produtos_carrinho:
            if 'imagem' in produto and ('imagens' not in produto or not produto['imagens']):
                produto['imagens'] = [produto['imagem']]
            if 'imagens' not in produto:
                produto['imagens'] = []
        
        total_geral = sum(item['preco'] * item['quantidade'] for item in produtos_carrinho)

        # Se for POST (quando o usuário envia o formulário pelo fluxo antigo)
        if request.method == 'POST':
            nome = request.form.get('nome')
            email = request.form.get('email')
            endereco = request.form.get('endereco')
            pagamento = request.form.get('pagamento')

            if not pagamento:
                flash('⚠️ Selecione um método de pagamento.', 'warning')
                return redirect(url_for('finalizar_carrinho'))

            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)

                # Verificar estoque de todos os produtos
                for item in produtos_carrinho:
                    cursor.execute("SELECT nome, estoque FROM produto WHERE id_produto = %s", (item['id_produto'],))
                    produto_db = cursor.fetchone()
                    if not produto_db:
                        flash(f"❌ Produto '{item['nome']}' não encontrado.", 'error')
                        return redirect(url_for('carrinho'))
                    if produto_db['estoque'] < item['quantidade']:
                        flash(f"⚠️ Estoque insuficiente de '{produto_db['nome']}'.", 'warning')
                        return redirect(url_for('carrinho'))

                # Criar pedido
                cursor.execute("""
                    INSERT INTO pedidos (id_cliente, total, forma_pagamento, status, data_pedido)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (session['usuario_id'], total_geral, pagamento, 'pendente'))
                pedido_id = cursor.lastrowid

                # Adicionar itens ao pedido e atualizar estoque
                for item in produtos_carrinho:
                    cursor.execute("""
                        INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_unitario)
                        VALUES (%s, %s, %s, %s)
                    """, (pedido_id, item['id_produto'], item['quantidade'], item['preco']))
                    cursor.execute("""
                        UPDATE produto SET estoque = estoque - %s WHERE id_produto = %s
                    """, (item['quantidade'], item['id_produto']))

                # Registrar pagamento - AQUI ESTÁ A CORREÇÃO!
                cursor.execute("""
                    INSERT INTO pagamentos (nome, email, endereco, metodo, valor, id_pedido)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (nome, email, endereco, pagamento, total_geral, pedido_id))

                conn.commit()

                # Limpar carrinho da sessão
                session.pop('carrinho', None)
                session.modified = True

                # Processar diferentes métodos de pagamento (fluxo antigo)
                if pagamento == 'pix':
                    qr_base64, copia_cola = gerar_qrcode_pix(total_geral)
                    return render_template(
                        'compra-sucedida.html',
                        valor=total_geral,
                        qr_base64=qr_base64,
                        copia_cola=copia_cola,
                        pedido_id=pedido_id,
                        metodo_pagamento='pix'
                    )
                elif pagamento == 'cartao':
                    session['ultimo_pedido_id'] = pedido_id
                    return redirect(url_for('pagamento_cartao', pedido_id=pedido_id))
                elif pagamento == 'boleto':
                    session['ultimo_pedido_id'] = pedido_id
                    return redirect(url_for('pagamento_boleto', pedido_id=pedido_id))
                else:
                    return render_template(
                        'compra-sucedida.html',
                        valor=total_geral,
                        pedido_id=pedido_id,
                        metodo_pagamento=pagamento
                    )
                    
            except mysql.connector.Error as err:
                if 'conn' in locals() and conn.is_connected():
                    conn.rollback()
                flash(f'❌ Erro ao finalizar compra: {err}', 'error')
                return redirect(url_for('carrinho'))
            finally:
                if 'conn' in locals() and conn and conn.is_connected():
                    cursor.close()
                    conn.close()

        # Para GET, apenas mostra o formulário
        return render_template('finalizar-carrinho.html',
                            produtos_carrinho=produtos_carrinho,
                            total_geral=total_geral)
    @app.route('/confirmar-pagamento', methods=['POST'])
    @login_required
    def confirmar_pagamento():
        """Confirma o pagamento e atualiza o status do pedido"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT id_pedido 
                FROM pedidos 
                WHERE id_cliente = %s 
                AND status = 'pendente' 
                ORDER BY id_pedido DESC 
                LIMIT 1
            """, (session['usuario_id'],))
            
            pedido = cursor.fetchone()
            
            if pedido:
                id_pedido = pedido['id_pedido']
                
                cursor.execute("""
                    UPDATE pedidos 
                    SET status = 'concluido' 
                    WHERE id_pedido = %s
                """, (id_pedido,))
                
                conn.commit()
                
                session['pagamento_confirmado'] = True
                session.modified = True
                
                return jsonify({
                    'status': 'success', 
                    'message': 'Pagamento confirmado!',
                    'pedido_id': id_pedido
                })
            else:
                return jsonify({
                    'status': 'error', 
                    'message': 'Nenhum pedido pendente encontrado.'
                })
            
        except Exception as err:
            print(f"Erro ao confirmar pagamento: {err}")
            if 'conn' in locals() and conn.is_connected():
                conn.rollback()
            return jsonify({'status': 'error', 'message': str(err)})
        finally:
            if 'conn' in locals() and conn and conn.is_connected():
                cursor.close()
                conn.close()
                
    @app.route('/compra-sucedida')
    def compra_sucedida():
        return render_template('compra-sucedida.html')
        
    @app.route('/meus-pedidos')
    @login_required
    def meus_pedidos():
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT * FROM pedidos 
                WHERE id_cliente = %s 
                ORDER BY data_pedido DESC
            """, (session['usuario_id'],))
            
            pedidos = cursor.fetchall()
            
            for pedido in pedidos:
                cursor.execute("SELECT COUNT(*) as qtd FROM itens_pedido WHERE id_pedido = %s", (pedido['id_pedido'],))
                pedido['qtd_itens'] = cursor.fetchone()['qtd']
            
            return render_template('meus_pedidos.html', pedidos=pedidos)
            
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar pedidos: {err}', 'error')
            return redirect(url_for('minha_conta'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/meus-pedidos/<int:id_pedido>')
    @login_required
    def detalhes_pedido(id_pedido):
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT p.*, e.rua, e.numero, e.bairro, e.cidade, e.estado, e.cep, e.destinatario
                FROM pedidos p
                LEFT JOIN enderecos e ON p.id_endereco = e.id_endereco
                WHERE p.id_pedido = %s AND p.id_cliente = %s
            """, (id_pedido, session['usuario_id']))
            
            pedido = cursor.fetchone()
            
            if not pedido:
                flash('Pedido não encontrado.', 'error')
                return redirect(url_for('meus_pedidos'))
            
            cursor.execute("""
                SELECT ip.*, p.nome, p.imagem, p.imagens, p.marca
                FROM itens_pedido ip
                JOIN produto p ON ip.id_produto = p.id_produto
                WHERE ip.id_pedido = %s
            """, (id_pedido,))
            
            itens = cursor.fetchall()
            
            for item in itens:
                if item.get('imagens'):
                    try:
                        imgs = json.loads(item['imagens'])
                        item['imagem_principal'] = imgs[0] if imgs else item['imagem']
                    except:
                        item['imagem_principal'] = item['imagem']
                else:
                    item['imagem_principal'] = item['imagem']

            return render_template('detalhes_pedido.html', pedido=pedido, itens=itens)
            
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar detalhes: {err}', 'error')
            return redirect(url_for('meus_pedidos'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()