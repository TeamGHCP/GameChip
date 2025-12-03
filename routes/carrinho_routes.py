from flask import render_template, request, flash, redirect, url_for, session, jsonify
from models.database import get_db_connection
from utils.decorators import login_required
from utils.qrcode_generator import gerar_qrcode_pix
import mysql.connector
import json

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

    @app.route('/finalizar-carrinho', methods=['GET', 'POST'])
    def finalizar_carrinho():
        # 🔍 DEBUG 1: Verificar sessão
        print(f"\n🔍 DEBUG SESSÃO COMPLETA:")
        for key, value in session.items():
            print(f"  {key}: {value}")
        
        print(f"\n🔍 DEBUG: Chegou na rota finalizar_carrinho")
        
        # Verificar se usuário está logado
        if 'usuario_id' not in session:
            flash('⚠️ Faça login para finalizar sua compra.', 'warning')
            print(f"🔍 DEBUG: usuario_id NÃO encontrado na sessão - Redirecionando para login")
            return redirect(url_for('login', next=url_for('finalizar_carrinho')))
        
        produtos_carrinho = session.get('carrinho', [])
        print(f"🔍 DEBUG: Produtos no carrinho = {len(produtos_carrinho)} itens")
        
        if not produtos_carrinho and request.method == 'GET':
            print(f"🔍 DEBUG: Carrinho vazio no GET - Mostrando carrinho vazio")
            return render_template('carrinho.html', produtos_carrinho=[], total_itens=0, total_preco=0)
        
        for produto in produtos_carrinho:
            if 'imagem' in produto and ('imagens' not in produto or not produto['imagens']):
                produto['imagens'] = [produto['imagem']]
            if 'imagens' not in produto:
                produto['imagens'] = []
        
        total_geral = sum(item['preco'] * item['quantidade'] for item in produtos_carrinho)
        session['chegou_finalizar-carrinho'] = True
        
        print(f"🔍 DEBUG: Total geral = R$ {total_geral:.2f}")
        
        if request.method == 'POST':
            nome = request.form.get('nome')
            email = request.form.get('email')
            endereco = request.form.get('endereco')
            pagamento = request.form.get('pagamento')
            
            print(f"🔍 DEBUG: Formulário recebido:")
            print(f"  Nome: {nome}")
            print(f"  Email: {email}")
            print(f"  Endereço: {endereco}")
            print(f"  Pagamento: {pagamento}")
            
            if not produtos_carrinho:
                flash('⚠️ Seu carrinho está vazio ou já foi processado.', 'warning')
                return redirect(url_for('carrinho'))
            
            try:
                conn = get_db_connection()
                if not conn:
                    flash('❌ Erro ao conectar ao banco de dados.', 'error')
                    return redirect(url_for('carrinho'))
                
                cursor = conn.cursor(dictionary=True)
                
                # 🔍 DEBUG 2: Verificar o ID do usuário
                usuario_id = session['usuario_id']
                print(f"\n🔍 DEBUG: Buscando cliente no banco:")
                print(f"  usuario_id da sessão: {usuario_id} (tipo: {type(usuario_id)})")
                print(f"  usuario_nome da sessão: {session.get('usuario_nome')}")
                
                # 🔍 DEBUG 3: Verificar se há clientes na tabela
                cursor.execute("SELECT COUNT(*) as total FROM clientes")
                total_clientes = cursor.fetchone()['total']
                print(f"🔍 DEBUG: Total de clientes na tabela: {total_clientes}")
                
                # 🔍 DEBUG 4: Verificar cliente específico
                cursor.execute("SELECT id_cliente, nome, email, ativo FROM clientes WHERE id_cliente = %s", (usuario_id,))
                cliente = cursor.fetchone()
                
                if not cliente:
                    print(f"❌ DEBUG: NENHUM cliente encontrado com id_cliente = {usuario_id}")
                    print(f"🔍 DEBUG: Verificando todos os clientes disponíveis...")
                    
                    cursor.execute("SELECT id_cliente, nome, email FROM clientes LIMIT 5")
                    todos_clientes = cursor.fetchall()
                    print(f"🔍 DEBUG: Primeiros 5 clientes no banco:")
                    for c in todos_clientes:
                        print(f"  ID: {c['id_cliente']}, Nome: {c['nome']}, Email: {c['email']}")
                    
                    flash('❌ Erro: Cadastro de cliente não encontrado. Entre em contato com o suporte.', 'error')
                    return redirect(url_for('carrinho'))
                
                print(f"✅ DEBUG: Cliente encontrado:")
                print(f"  ID: {cliente['id_cliente']}")
                print(f"  Nome: {cliente['nome']}")
                print(f"  Email: {cliente['email']}")
                print(f"  Ativo: {cliente['ativo']}")
                
                if not cliente['ativo']:
                    print(f"⚠️ DEBUG: Cliente está INATIVO")
                    flash('❌ Sua conta está desativada. Entre em contato com o suporte.', 'error')
                    return redirect(url_for('carrinho'))
                
                # Verificar estoque
                print(f"\n🔍 DEBUG: Verificando estoque...")
                for item in produtos_carrinho:
                    cursor.execute("SELECT nome, estoque FROM produto WHERE id_produto = %s", (item['id_produto'],))
                    produto_db = cursor.fetchone()
                    if not produto_db:
                        flash(f"❌ Produto '{item['nome']}' não encontrado.", 'error')
                        return redirect(url_for('carrinho'))
                    if produto_db['estoque'] < item['quantidade']:
                        flash(f"⚠️ Estoque insuficiente de '{produto_db['nome']}'.", 'warning')
                        return redirect(url_for('carrinho'))
                    print(f"  ✅ {produto_db['nome']}: {produto_db['estoque']} em estoque, precisa de {item['quantidade']}")
                
                # INSERIR PEDIDO
                print(f"\n🔍 DEBUG: Inserindo pedido...")
                cursor.execute("""
                    INSERT INTO pedidos (id_cliente, total, forma_pagamento, status, data_pedido)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (cliente['id_cliente'], total_geral, pagamento, 'pendente'))
                pedido_id = cursor.lastrowid
                print(f"✅ DEBUG: Pedido criado com ID: {pedido_id}")
                
                # Inserir itens do pedido
                print(f"🔍 DEBUG: Inserindo itens do pedido...")
                for item in produtos_carrinho:
                    cursor.execute("""
                        INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_unitario)
                        VALUES (%s, %s, %s, %s)
                    """, (pedido_id, item['id_produto'], item['quantidade'], item['preco']))
                    cursor.execute("""
                        UPDATE produto SET estoque = estoque - %s WHERE id_produto = %s
                    """, (item['quantidade'], item['id_produto']))
                    print(f"  ✅ {item['nome']}: {item['quantidade']}x R$ {item['preco']:.2f}")
                
                # Registrar pagamento
                cursor.execute("""
                    INSERT INTO pagamentos (nome, email, endereco, metodo, valor)
                    VALUES (%s, %s, %s, %s, %s)
                """, (nome, email, endereco, pagamento, total_geral))
                
                conn.commit()
                print(f"✅ DEBUG: Transação confirmada no banco")
                
                # Limpar carrinho
                session.pop('carrinho', None)
                session.modified = True
                print(f"✅ DEBUG: Carrinho limpo da sessão")
                
                if pagamento == 'pix':
                    qr_base64, copia_cola = gerar_qrcode_pix(total_geral)
                    return render_template('gerar_pix.html', valor=total_geral, qr_base64=qr_base64, copia_cola=copia_cola)
                else:
                    flash(f'🎉 Compra #{pedido_id} realizada com sucesso!', 'success')
                    print(f"✅ DEBUG: Redirecionando para meus_pedidos")
                    return redirect(url_for('meus_pedidos'))
                
            except mysql.connector.Error as err:
                print(f"❌ DEBUG: Erro MySQL: {err}")
                if 'conn' in locals() and conn.is_connected():
                    conn.rollback()
                    print(f"❌ DEBUG: Rollback realizado")
                flash(f'❌ Erro ao finalizar compra: {err}', 'error')
                return redirect(url_for('carrinho'))
            except Exception as err:
                print(f"❌ DEBUG: Erro geral: {err}")
                flash(f'❌ Erro inesperado: {err}', 'error')
                return redirect(url_for('carrinho'))
            finally:
                if 'conn' in locals() and conn and conn.is_connected():
                    cursor.close()
                    conn.close()
                    print(f"✅ DEBUG: Conexão com banco fechada")
        
        # GET request: mostrar formulário de finalização
        print(f"🔍 DEBUG: Renderizando template finalizar-carrinho.html")
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
            
            # 1. Buscar o ÚLTIMO pedido PENDENTE do cliente
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
                
                # 2. Atualizar status para 'concluido' (ou 'aprovado')
                cursor.execute("""
                    UPDATE pedidos 
                    SET status = 'concluido' 
                    WHERE id_pedido = %s
                """, (id_pedido,))
                
                conn.commit()
                
                # 3. Marcar na sessão que o pagamento foi confirmado
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
            
            # Busca TODOS os pedidos do cliente (não só os 5 últimos)
            cursor.execute("""
                SELECT * FROM pedidos 
                WHERE id_cliente = %s 
                ORDER BY data_pedido DESC
            """, (session['usuario_id'],))
            
            pedidos = cursor.fetchall()
            
            # Conta itens para exibir na tabela
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
            
            # Busca detalhes do pedido específico
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
            
            # Busca os produtos desse pedido
            cursor.execute("""
                SELECT ip.*, p.nome, p.imagem, p.imagens, p.marca
                FROM itens_pedido ip
                JOIN produto p ON ip.id_produto = p.id_produto
                WHERE ip.id_pedido = %s
            """, (id_pedido,))
            
            itens = cursor.fetchall()
            
            # Corrige imagens JSON
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