from flask import render_template, request, flash, redirect, url_for, session, jsonify
from models.database import get_db_connection
from utils.decorators import login_required
from utils.qrcode_generator import gerar_qrcode_pix
import mysql.connector
import json
from datetime import datetime

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


    @app.route('/pagamento-cartao', methods=['GET', 'POST'])
    @login_required
    def pagamento_cartao():
        """Página dedicada para pagamento com cartão"""
        from datetime import datetime
        
        produtos_carrinho = session.get('carrinho', [])
        
        if not produtos_carrinho:
            flash('⚠️ Seu carrinho está vazio.', 'warning')
            return redirect(url_for('carrinho'))
        
        # Pegar dados da sessão
        dados_entrega = session.get('dados_entrega', {})
        if not dados_entrega:
            flash('⚠️ Complete os dados de entrega primeiro.', 'warning')
            return redirect(url_for('finalizar_carrinho'))
        
        total_geral = sum(item['preco'] * item['quantidade'] for item in produtos_carrinho)
        
        if request.method == 'POST':
            # Processar pagamento com cartão
            nome_titular = request.form.get('nome_titular')
            numero_cartao = request.form.get('numero_cartao')
            validade = request.form.get('validade')
            cvv = request.form.get('cvv')
            tipo_cartao = request.form.get('tipo_cartao')
            parcelas = request.form.get('parcelas', '1')
            
            print(f"🔍 DEBUG: Processando pagamento com cartão")
            
            # Validar dados do cartão
            if not all([nome_titular, numero_cartao, validade, cvv, tipo_cartao]):
                flash('❌ Preencha todos os dados do cartão.', 'error')
                return render_template('pagamento-cartao.html',
                                    produtos_carrinho=produtos_carrinho,
                                    total_geral=total_geral,
                                    dados_entrega=dados_entrega)
            
            # Validar número do cartão (simplificado)
            numero_limpo = ''.join(filter(str.isdigit, numero_cartao))
            if len(numero_limpo) < 13 or len(numero_limpo) > 19:
                flash('❌ Número do cartão inválido.', 'error')
                return render_template('pagamento-cartao.html',
                                    produtos_carrinho=produtos_carrinho,
                                    total_geral=total_geral,
                                    dados_entrega=dados_entrega)
            
            # Inicializar variáveis
            pedido_id = None
            conn = None
            cursor = None
            
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                
                # 1. Inserir pedido
                cursor.execute("""
                    INSERT INTO pedidos (id_cliente, total, forma_pagamento, status, data_pedido)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (session['usuario_id'], total_geral, 'cartao', 'aprovado'))
                
                pedido_id = cursor.lastrowid
                print(f"✅ DEBUG: Pedido #{pedido_id} criado")
                
                # 2. Inserir itens do pedido
                for item in produtos_carrinho:
                    cursor.execute("""
                        INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_unitario)
                        VALUES (%s, %s, %s, %s)
                    """, (pedido_id, item['id_produto'], item['quantidade'], item['preco']))
                    
                    # Atualizar estoque
                    cursor.execute("""
                        UPDATE produto SET estoque = estoque - %s 
                        WHERE id_produto = %s
                    """, (item['quantidade'], item['id_produto']))
                    print(f"  ✅ {item['nome']} - Estoque atualizado")
                
                # 3. Registrar pagamento na tabela pagamentos
                try:
                    cursor.execute("""
                        INSERT INTO pagamentos (nome, email, endereco, metodo, valor)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        dados_entrega.get('nome', ''),
                        dados_entrega.get('email', ''),
                        dados_entrega.get('endereco', ''),
                        'cartao',
                        total_geral
                    ))
                    print(f"✅ DEBUG: Pagamento registrado")
                except Exception as e:
                    print(f"⚠️ DEBUG: Não foi possível registrar pagamento: {e}")
                    # Continua mesmo sem registrar
                
                conn.commit()
                
                # 4. Limpar carrinho e salvar dados para página de sucesso
                session.pop('carrinho', None)
                session.pop('dados_entrega', None)
                
                # Converter parcelas para inteiro
                try:
                    parcelas_int = int(parcelas)
                except:
                    parcelas_int = 1
                
                session['pedido_confirmado'] = {
                    'id': pedido_id,
                    'total': total_geral,
                    'metodo': 'cartao',
                    'tipo_cartao': tipo_cartao,
                    'parcelas': parcelas_int,
                    'data': datetime.now().strftime("%d/%m/%Y %H:%M"),
                    'ultimos_digitos': numero_limpo[-4:],
                    'nome_titular': nome_titular
                }
                session.modified = True
                
                print(f"✅ DEBUG: Pagamento processado com sucesso! Redirecionando para compra-sucesso")
                
                # Redirecionar para página de sucesso
                return redirect(url_for('compra_sucesso'))
                
            except Exception as err:
                print(f"❌ DEBUG: Erro no pagamento: {err}")
                import traceback
                traceback.print_exc()  # Mostra o traceback completo
                
                if conn and conn.is_connected():
                    conn.rollback()
                    print(f"❌ DEBUG: Rollback realizado")
                
                flash(f'❌ Erro ao processar pagamento. Tente novamente.', 'error')
                return render_template('pagamento-cartao.html',
                                    produtos_carrinho=produtos_carrinho,
                                    total_geral=total_geral,
                                    dados_entrega=dados_entrega)
            finally:
                if cursor:
                    cursor.close()
                if conn and conn.is_connected():
                    conn.close()
                    print(f"✅ DEBUG: Conexão com banco fechada")
        
        # GET request: mostrar formulário de pagamento
        return render_template('pagamento-cartao.html',
                            produtos_carrinho=produtos_carrinho,
                            total_geral=total_geral,
                            dados_entrega=dados_entrega)
        
    @app.route('/compra-sucesso')
    @login_required
    def compra_sucesso():
        """Página de confirmação de compra bem-sucedida"""
        
        pedido_info = session.get('pedido_confirmado')
        
        if not pedido_info:
            flash('⚠️ Nenhum pedido recente encontrado.', 'info')
            return redirect(url_for('meus_pedidos'))
        
        # Garantir que todos os campos existam
        if 'data' not in pedido_info:
            from datetime import datetime
            pedido_info['data'] = datetime.now().strftime("%d/%m/%Y %H:%M")
        
        if 'parcelas' not in pedido_info:
            pedido_info['parcelas'] = 1
        
        if 'tipo_cartao' not in pedido_info:
            pedido_info['tipo_cartao'] = 'cartao'
        
        return render_template('compra-sucesso.html', pedido=pedido_info)




    @app.route('/finalizar-carrinho', methods=['GET', 'POST'])
    def finalizar_carrinho():
        """Página para finalizar a compra com dados de entrega"""
        
        print(f"\n🔍 DEBUG: Chegou na rota finalizar_carrinho")
        
        # Verificar se usuário está logado
        if 'usuario_id' not in session:
            flash('⚠️ Faça login para finalizar sua compra.', 'warning')
            print(f"🔍 DEBUG: usuario_id NÃO encontrado na sessão - Redirecionando para login")
            return redirect(url_for('login', next=url_for('finalizar_carrinho')))
        
        produtos_carrinho = session.get('carrinho', [])
        print(f"🔍 DEBUG: Produtos no carrinho = {len(produtos_carrinho)} itens")
        
        if not produtos_carrinho and request.method == 'GET':
            print(f"🔍 DEBUG: Carrinho vazio no GET - Redirecionando para carrinho")
            flash('🛒 Seu carrinho está vazio.', 'info')
            return redirect(url_for('carrinho'))
        
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
                flash('⚠️ Seu carrinho está vazio.', 'warning')
                return redirect(url_for('carrinho'))
            
            # Validar dados
            if not all([nome, email, endereco, pagamento]):
                flash('❌ Preencha todos os campos obrigatórios.', 'error')
                return render_template('finalizar-carrinho.html', 
                                    produtos_carrinho=produtos_carrinho,
                                    total_geral=total_geral)
            
            # Salvar dados na sessão para usar nas próximas etapas
            session['dados_entrega'] = {
                'nome': nome,
                'email': email,
                'endereco': endereco
            }
            session.modified = True
            
            # Redirecionar para a página de pagamento apropriada
            if pagamento == 'cartao':
                print(f"🔍 DEBUG: Redirecionando para pagamento com cartão")
                return redirect(url_for('pagamento_cartao'))
            elif pagamento == 'pix':
                print(f"🔍 DEBUG: Redirecionando para PIX")
                return redirect(url_for('gerar_pix', valor=total_geral))
            elif pagamento == 'boleto':
                print(f"🔍 DEBUG: Processando boleto")
                # Aqui você pode redirecionar para uma página de boleto
                # ou processar diretamente
                try:
                    # Processar boleto - adicione sua lógica aqui
                    flash('📄 Boleto gerado com sucesso!', 'success')
                    # Redirecionar para página de sucesso
                    return redirect(url_for('compra-sucesso', metodo='boleto'))
                except Exception as e:
                    flash(f'❌ Erro ao gerar boleto: {e}', 'error')
                    return redirect(url_for('carrinho'))
            else:
                flash('❌ Forma de pagamento inválida.', 'error')
                return redirect(url_for('carrinho'))
        
        # GET request: mostrar formulário de finalização
        print(f"🔍 DEBUG: Renderizando template finalizar-carrinho.html")
        
        # Preencher dados do usuário se disponíveis
        dados_usuario = {
            'nome': session.get('usuario_nome', ''),
            'email': session.get('usuario_email', '')
        }
        
        return render_template('finalizar-carrinho.html', 
                            produtos_carrinho=produtos_carrinho,
                            total_geral=total_geral,
                            dados_usuario=dados_usuario)

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