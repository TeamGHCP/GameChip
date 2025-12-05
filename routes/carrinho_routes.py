from flask import render_template, request, flash, redirect, url_for, session, jsonify, send_file, make_response
from models.database import get_db_connection
from utils.decorators import login_required
from utils.qrcode_generator import gerar_qrcode_pix
import mysql.connector
import json
from datetime import datetime, timedelta
import random
import io 
from barcode import Code128
from barcode.writer import ImageWriter
import base64
import time
import string


def gerar_imagem_codigo_barras(codigo_texto):
    """
    Gera uma imagem de código de barras a partir do texto
    Retorna: base64 da imagem
    """
    try:
        # Remover pontos e espaços para o código de barras real
        codigo_limpo = ''.join(filter(str.isdigit, codigo_texto))
        
        # Criar código de barras Code128 (padrão para boletos)
        code128 = Code128(codigo_limpo, writer=ImageWriter())
        
        # Salvar em buffer de memória
        buffer = io.BytesIO()
        code128.write(buffer)
        buffer.seek(0)
        
        # Converter para base64
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return f"data:image/png;base64,{img_base64}"
        
    except Exception as e:
        print(f"❌ ERRO ao gerar código de barras: {e}")
        # Fallback: imagem vazia
        return ""


def configure_carrinho_routes(app):
    
    @app.route('/carrinho')
    def carrinho():
        carrinho_items = session.get('carrinho', [])
        total_itens = sum(item['quantidade'] for item in carrinho_items)
        total_preco = sum(item['preco'] * item['quantidade'] for item in carrinho_items)
        return render_template('carrinho.html', produtos_carrinho=carrinho_items, total_itens=total_itens, total_preco=total_preco, total_geral=total_preco)

    @app.route('/adicionar-carrinho/<int:id_produto>', methods=['POST'])
    def adicionar_carrinho(id_produto):
        # Inicializa a variável conn como None para evitar erro no bloco 'finally'
        conn = None 
        
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(url_for('listar_produtos'))
            
            cursor = conn.cursor(dictionary=True)

            # ==================================================================
            # LÓGICA DE PERMISSÃO CORRIGIDA (BLOQUEIO APENAS PARA VENDEDOR PURO)
            # ==================================================================
            if 'empresa_id' in session:
                cursor.execute("SELECT tipo_empresa FROM empresas WHERE id_empresa = %s", (session['empresa_id'],))
                dados_empresa = cursor.fetchone()
                
                # Se a empresa for EXCLUSIVAMENTE vendedora, bloqueia a compra
                # Se for 'comprador' ou 'ambos', permite passar
                if dados_empresa and dados_empresa['tipo_empresa'] == 'vendedor':
                    flash('🚫 Conta de Vendedor: Você não tem permissão para comprar produtos. Altere seu perfil para "Ambos" ou "Comprador".', 'error')
                    return redirect(request.referrer or url_for('inicio'))
            # ==================================================================

            # Lógica padrão de buscar o produto
            cursor.execute("SELECT * FROM produto WHERE id_produto = %s AND ativo = TRUE", (id_produto,))
            produto = cursor.fetchone()
            
            if not produto:
                flash('❌ Produto não encontrado.', 'error')
                return redirect(url_for('listar_produtos'))
            
            # Inicializa o carrinho na sessão se não existir
            if 'carrinho' not in session:
                session['carrinho'] = []
            
            carrinho = session['carrinho']
            
            # Verifica se o produto já está no carrinho
            produto_no_carrinho = next((item for item in carrinho if item['id_produto'] == id_produto), None)
            
            # Pega a quantidade do formulário (padrão 1)
            quantidade = int(request.form.get('quantidade', 1))
            
            # Tratamento das imagens (JSON ou String)
            imagens_produto = []
            if produto.get('imagens'):
                try:
                    imagens_produto = json.loads(produto['imagens'])
                except:
                    imagens_produto = []
            elif produto.get('imagem'):
                imagens_produto = [produto['imagem']]
            
            # Adiciona ou atualiza o produto no carrinho
            if produto_no_carrinho:
                produto_no_carrinho['quantidade'] += quantidade
            else:
                carrinho.append({
                    'id_produto': produto['id_produto'],
                    'nome': produto['nome'],
                    'preco': float(produto['preco']),
                    'quantidade': quantidade,
                    'imagens': imagens_produto,
                    'imagem_principal': imagens_produto[0] if imagens_produto else '',
                    'categoria': produto['categoria']
                })
            
            # Salva o carrinho na sessão
            session['carrinho'] = carrinho
            session.modified = True
            
            flash(f'✅ {produto["nome"]} adicionado ao carrinho!', 'success')
            
            # Se a requisição veio de uma loja parceira, tenta voltar para ela
            if request.form.get('retorno') == 'loja_parceira' and request.form.get('id_empresa'):
                 return redirect(url_for('detalhes_empresa_publica', id_empresa=request.form.get('id_empresa')))
            
            return redirect(url_for('listar_produtos'))
        
        except mysql.connector.Error as err:
            flash(f'Erro ao adicionar produto ao carrinho: {err}', 'error')
            return redirect(url_for('listar_produtos'))
        
        except Exception as e:
            flash(f'Erro inesperado: {str(e)}', 'error')
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

    # ============ FUNÇÕES AUXILIARES PARA BOLETO ============
    
    def calcular_fator_vencimento(vencimento):
        """Calcula o fator de vencimento para boleto"""
        # Data base para boletos: 07/10/1997
        data_base = datetime(1997, 10, 7)
        diferenca = vencimento - data_base
        return f"{diferenca.days:04d}"

    def calcular_digito_verificador(codigo):
        """Calcula dígito verificador usando módulo 10"""
        # Remove posição do dígito verificador (posição 4)
        if len(codigo) >= 4:
            codigo_sem_dv = codigo[:4] + codigo[5:]
        else:
            codigo_sem_dv = codigo
        
        soma = 0
        peso = 2
        
        # Percorre de trás para frente
        for digito in reversed(codigo_sem_dv):
            resultado = int(digito) * peso
            if resultado > 9:
                resultado = sum(int(d) for d in str(resultado))
            soma += resultado
            peso = 3 if peso == 2 else 2
        
        resto = soma % 10
        if resto == 0:
            return "0"
        else:
            return str(10 - resto)

    def calcular_dv_modulo10(numero):
        """Calcula dígito verificador usando módulo 10 (para blocos)"""
        soma = 0
        peso = 2
        
        for digito in reversed(str(numero)):
            resultado = int(digito) * peso
            if resultado > 9:
                resultado = sum(int(d) for d in str(resultado))
            soma += resultado
            peso = 3 if peso == 2 else 2
        
        resto = soma % 10
        if resto == 0:
            return "0"
        else:
            return str(10 - resto)

    def gerar_codigo_barras_boleto(pedido_id, valor, vencimento):
        """Gera um código de barras fictício para o boleto"""
        try:
            # Formato: 341 (Banco Itaú) + 9 (Moeda Real) + fator vencimento + valor
            banco = "341"
            
            # Calcular fator de vencimento
            fator = calcular_fator_vencimento(vencimento)
            
            # Formatar valor (10 dígitos com zeros à esquerda)
            valor_centavos = int(valor * 100)
            valor_formatado = f"{valor_centavos:010d}"
            
            # Código do beneficiário (fictício)
            beneficiario = "1234567"
            
            # Carteira (fictício)
            carteira = "157"
            
            # Nosso número (usando pedido_id)
            nosso_numero = f"{pedido_id:08d}"
            
            # Constante para identificação
            constante = "0"
            
            # Montar código (43 dígitos sem DV)
            codigo_sem_dv = f"{banco}9{fator}{valor_formatado}{beneficiario}{carteira}{nosso_numero}{constante}"
            
            # Garantir 43 dígitos
            codigo_sem_dv = codigo_sem_dv.ljust(43, '0')
            
            # Calcular dígito verificador
            dv = calcular_digito_verificador(codigo_sem_dv)
            
            # Inserir DV na posição 4 (índice 3)
            codigo_completo = codigo_sem_dv[:4] + dv + codigo_sem_dv[4:]
            
            return codigo_completo[:44]  # Garantir 44 dígitos
            
        except Exception as e:
            print(f"❌ ERRO ao gerar código de barras: {e}")
            # Código de fallback
            return "34199844100000150000000012345671570000012345678"

    def formatar_linha_digitavel(codigo_barras):
        """Formata a linha digitável do boleto"""
        try:
            if len(codigo_barras) < 44:
                codigo_barras = codigo_barras.ljust(44, '0')
            
            # Extrair partes do código
            campo1 = codigo_barras[0:4] + codigo_barras[19:24]  # Banco + 5 primeiros do beneficiário
            campo2 = codigo_barras[24:34]  # Próximos 10 dígitos
            campo3 = codigo_barras[34:44]  # Últimos 10 dígitos
            campo4 = codigo_barras[4]  # DV geral
            campo5 = codigo_barras[5:19]  # Fator vencimento + valor
            
            # Calcular DVs dos campos
            dv1 = calcular_dv_modulo10(campo1)
            dv2 = calcular_dv_modulo10(campo2)
            dv3 = calcular_dv_modulo10(campo3)
            
            # Formatar
            linha = f"{campo1[:5]}.{campo1[5:]}{dv1} {campo2[:5]}.{campo2[5:]}{dv2} {campo3[:5]}.{campo3[5:]}{dv3} {campo4} {campo5}"
            
            return linha
            
        except Exception as e:
            print(f"❌ ERRO ao formatar linha digitável: {e}")
            return "34191.79001 01043.510047 91020.150008 8 84410000015000"

    # ============ ROTAS PRINCIPAIS ATUALIZADAS ============

    @app.route('/finalizar-carrinho', methods=['GET', 'POST'])
    def finalizar_carrinho():
        """Finalização da compra (checkout) - Compatível com Cliente e Empresa"""
        
        # 1. Identificar quem está logado
        usuario_id = session.get('usuario_id')
        empresa_id = session.get('empresa_id')
        
        # Se ninguém estiver logado
        if not usuario_id and not empresa_id:
            flash('Faça login para finalizar sua compra.', 'info')
            return redirect(url_for('login'))

        produtos_carrinho = session.get('carrinho', [])
        
        if not produtos_carrinho:
            flash('⚠️ Seu carrinho está vazio.', 'warning')
            return redirect(url_for('carrinho'))
        
        # Processar imagens para exibição
        for produto in produtos_carrinho:
            if 'imagens' not in produto or not produto['imagens']:
                produto['imagens'] = []
            produto['imagem_principal'] = produto['imagens'][0] if produto['imagens'] else ''
        
        total_geral = sum(item['preco'] * item['quantidade'] for item in produtos_carrinho)
        
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            if request.method == 'POST':
                # Obter dados do formulário
                endereco_id = request.form.get('endereco_id')
                forma_pagamento = request.form.get('pagamento')
                nome = request.form.get('nome')
                email = request.form.get('email')
                
                # Validação: Endereço só é obrigatório se for CLIENTE (Pessoa Física)
                if usuario_id and not endereco_id:
                    flash('❌ Selecione um endereço para entrega.', 'error')
                    return redirect(url_for('finalizar_carrinho'))
                
                if not forma_pagamento:
                    flash('❌ Selecione uma forma de pagamento.', 'error')
                    return redirect(url_for('finalizar_carrinho'))
                
                if not nome or not email:
                    flash('❌ Preencha todos os campos obrigatórios.', 'error')
                    return redirect(url_for('finalizar_carrinho'))
                
                # Validar forma de pagamento
                formas_validas = ['pix', 'cartao', 'boleto']
                if forma_pagamento not in formas_validas:
                    flash('❌ Forma de pagamento inválida.', 'error')
                    return redirect(url_for('finalizar_carrinho'))
                
                # Verificar estoque
                for item in produtos_carrinho:
                    cursor.execute("""
                        SELECT nome, estoque 
                        FROM produto 
                        WHERE id_produto = %s AND ativo = TRUE
                    """, (item['id_produto'],))
                    
                    produto_db = cursor.fetchone()
                    
                    if not produto_db:
                        flash(f"❌ Produto '{item['nome']}' não está mais disponível.", 'error')
                        return redirect(url_for('carrinho'))
                    
                    if produto_db['estoque'] < item['quantidade']:
                        flash(f"⚠️ Estoque insuficiente de '{produto_db['nome']}'.", 'warning')
                        return redirect(url_for('carrinho'))
                
                # --- CRIAÇÃO DO PEDIDO (USER vs EMPRESA) ---
                pedido_id = None
                
                if usuario_id:
                    # CLIENTE: Precisa validar endereço na tabela enderecos
                    cursor.execute("""
                        SELECT * FROM enderecos 
                        WHERE id_endereco = %s AND id_cliente = %s
                    """, (endereco_id, usuario_id))
                    
                    endereco = cursor.fetchone()
                    
                    if not endereco:
                        flash('❌ Endereço não encontrado.', 'error')
                        return redirect(url_for('finalizar_carrinho'))
                    
                    cursor.execute("""
                        INSERT INTO pedidos (id_cliente, id_endereco, total, forma_pagamento, status, data_pedido) 
                        VALUES (%s, %s, %s, %s, %s, NOW())
                    """, (usuario_id, endereco_id, total_geral, forma_pagamento, 'pendente'))

                elif empresa_id:
                    # EMPRESA: Não usa tabela enderecos de cliente, usa id_empresa_compradora
                    # ID_ENDERECO fica NULL (ou trate conforme seu banco)
                    cursor.execute("""
                        INSERT INTO pedidos (id_empresa_compradora, total, forma_pagamento, status, data_pedido) 
                        VALUES (%s, %s, %s, %s, NOW())
                    """, (empresa_id, total_geral, forma_pagamento, 'pendente'))

                pedido_id = cursor.lastrowid
                
                # Adicionar itens ao pedido
                for item in produtos_carrinho:
                    cursor.execute("""
                        INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_unitario) 
                        VALUES (%s, %s, %s, %s)
                    """, (pedido_id, item['id_produto'], item['quantidade'], item['preco']))
                    
                    # Atualizar estoque produto geral
                    cursor.execute("""
                        UPDATE produto 
                        SET estoque = estoque - %s 
                        WHERE id_produto = %s
                    """, (item['quantidade'], item['id_produto']))
                    
                    # Atualizar estoque se for produto de marketplace (tabela produtos_empresa)
                    cursor.execute("""
                        UPDATE produtos_empresa 
                        SET estoque_empresa = estoque_empresa - %s 
                        WHERE id_produto = %s
                    """, (item['quantidade'], item['id_produto']))
                
                # Registrar na tabela geral de pagamentos
                cursor.execute("""
                    INSERT INTO pagamentos (nome, email, metodo, valor) 
                    VALUES (%s, %s, %s, %s)
                """, (nome, email, forma_pagamento, total_geral))
                
                # Se for PIX, registrar também na tabela pagamentos_pix
                if forma_pagamento == 'pix':
                    # Primeiro gere o QR Code e código PIX
                    qr_base64, codigo_pix = gerar_qrcode_pix(total_geral)
                    
                    # Extraia o txid do código PIX (se necessário)
                    txid = f"GHCP{int(time.time())}{random.randint(1000, 9999)}"
                    
                    # OBS: id_cliente é passado (se for empresa, vai None/Null)
                    cursor.execute("""
                        INSERT INTO pagamentos_pix (
                            id_pedido,
                            id_cliente,
                            chave_pix,
                            nome_recebedor,
                            cidade_recebedor,
                            valor,
                            qr_code_base64,
                            codigo_copia_cola,
                            txid,
                            status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pendente')
                    """, (
                        pedido_id,
                        usuario_id, 
                        app.config.get('PIX_CHAVE', '14057629939'),
                        app.config.get('PIX_NOME', 'CAETANO GBUR PETRY'),
                        app.config.get('PIX_CIDADE', 'JOINVILLE'),
                        total_geral,
                        qr_base64,
                        codigo_pix,
                        txid
                    ))
                
                conn.commit()
                
                # Limpar carrinho da sessão
                session.pop('carrinho', None)
                session.modified = True
                
                # Redirecionar conforme método de pagamento
                if forma_pagamento == 'pix':
                    session['pedido_em_andamento'] = pedido_id
                    return redirect(url_for('pagamento_pix', pedido_id=pedido_id))
                elif forma_pagamento == 'cartao':
                    return redirect(url_for('pagamento_cartao', pedido_id=pedido_id))
                elif forma_pagamento == 'boleto':
                    return redirect(url_for('visualizar_boleto', pedido_id=pedido_id))
                
            # --- GET: Mostrar formulário ---
            
            enderecos = []
            usuario_data = {}

            if usuario_id:
                # Buscar endereços do cliente
                cursor.execute("""
                    SELECT * FROM enderecos 
                    WHERE id_cliente = %s 
                    ORDER BY principal DESC
                """, (usuario_id,))
                enderecos = cursor.fetchall()
                # Buscar dados do cliente
                cursor.execute("SELECT nome, email FROM clientes WHERE id_cliente = %s", (usuario_id,))
                usuario_data = cursor.fetchone()

            elif empresa_id:
                # Buscar dados da empresa para preencher o form
                cursor.execute("SELECT razao_social as nome, email, endereco FROM empresas WHERE id_empresa = %s", (empresa_id,))
                emp = cursor.fetchone()
                if emp:
                    usuario_data = emp
                    # Mock de endereço para o template não quebrar
                    enderecos = [{
                        'id_endereco': 'empresa_addr',
                        'rua': emp['endereco'],
                        'numero': 'S/N',
                        'bairro': '-',
                        'cidade': '-',
                        'estado': '-',
                        'cep': '-',
                        'destinatario': emp['nome']
                    }]
            
            return render_template('finalizar-carrinho.html',
                                produtos_carrinho=produtos_carrinho,
                                total_geral=total_geral,
                                enderecos=enderecos,
                                usuario=usuario_data,
                                is_empresa=(empresa_id is not None))
        
        except Exception as err:
            flash(f'Erro ao carregar dados: {err}', 'error')
            return redirect(url_for('carrinho'))
        finally:
            if 'conn' in locals() and conn and conn.is_connected():
                cursor.close()
                conn.close()

    # ============ ROTAS DE PAGAMENTO ============

    @app.route('/pagamento/pix/<int:pedido_id>')
    def pagamento_pix(pedido_id):
        """Página de pagamento via PIX"""
        
        # Verifica permissão
        if 'usuario_id' not in session and 'empresa_id' not in session:
            return redirect(url_for('login'))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Buscar dados COMPLETOS do pedido e PIX (Suporta Cliente ou Empresa)
            usuario_id = session.get('usuario_id')
            empresa_id = session.get('empresa_id')

            sql = """
                SELECT 
                    pp.*,
                    p.id_pedido,
                    p.id_cliente,
                    p.total as pedido_total,
                    p.data_pedido,
                    p.status as pedido_status,
                    p.forma_pagamento,
                    c.nome as cliente_nome,
                    c.email
                FROM pedidos p
                LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
                LEFT JOIN pagamentos_pix pp ON p.id_pedido = pp.id_pedido
                WHERE p.id_pedido = %s
            """
            params = [pedido_id]
            
            # Trava de segurança: só vê se for o dono
            if usuario_id:
                sql += " AND p.id_cliente = %s"
                params.append(usuario_id)
            elif empresa_id:
                sql += " AND p.id_empresa_compradora = %s"
                params.append(empresa_id)

            cursor.execute(sql, tuple(params))
            pedido_data = cursor.fetchone()
            
            if not pedido_data:
                flash('❌ Pedido não encontrado ou acesso negado.', 'error')
                return redirect(url_for('meus_pedidos'))
            
            valor = float(pedido_data.get('valor') or pedido_data['pedido_total'])
            
            # Se não tem registro PIX, criar
            if not pedido_data.get('id_pagamento_pix'):
                qr_base64, codigo_pix = gerar_qrcode_pix(valor)
                
                cursor.execute("""
                    INSERT INTO pagamentos_pix 
                    (id_pedido, id_cliente, valor, qr_code_base64, codigo_copia_cola, status)
                    VALUES (%s, %s, %s, %s, %s, 'pendente')
                """, (pedido_id, usuario_id, valor, qr_base64, codigo_pix))
                
                conn.commit()
                
                pedido_data['qr_code_base64'] = qr_base64
                pedido_data['codigo_copia_cola'] = codigo_pix
                pedido_data['id_pagamento_pix'] = cursor.lastrowid
            
            # Se tem PIX mas não tem QR Code, gerar
            elif not pedido_data.get('qr_code_base64'):
                qr_base64, codigo_pix = gerar_qrcode_pix(valor)
                
                cursor.execute("""
                    UPDATE pagamentos_pix 
                    SET qr_code_base64 = %s, 
                        codigo_copia_cola = %s,
                        data_geracao = NOW()
                    WHERE id_pagamento_pix = %s
                """, (qr_base64, codigo_pix, pedido_data['id_pagamento_pix']))
                
                conn.commit()
                
                pedido_data['qr_code_base64'] = qr_base64
                pedido_data['codigo_copia_cola'] = codigo_pix
            
            return render_template('pagamento_pix.html',
                                pedido=pedido_data,
                                qr_base64=pedido_data['qr_code_base64'],
                                copia_cola=pedido_data['codigo_copia_cola'],
                                valor=valor)
        
        except Exception as err:
            flash(f'Erro ao carregar dados do PIX: {str(err)}', 'error')
            return redirect(url_for('meus_pedidos'))
        finally:
            if 'conn' in locals() and conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/boleto/<int:pedido_id>')
    def visualizar_boleto(pedido_id):
        """Página para visualizar o boleto gerado"""
        if 'usuario_id' not in session and 'empresa_id' not in session:
            return redirect(url_for('login'))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Query híbrida para trazer dados de Cliente ou Empresa
            usuario_id = session.get('usuario_id')
            empresa_id = session.get('empresa_id')

            sql = """
                SELECT p.*, 
                       c.nome as cliente_nome, c.email as cliente_email,
                       e.nome_fantasia as emp_nome, e.email as emp_email, e.endereco as emp_endereco,
                       end_cli.rua, end_cli.numero, end_cli.bairro, end_cli.cidade, end_cli.estado, end_cli.cep, end_cli.destinatario
                FROM pedidos p
                LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
                LEFT JOIN empresas e ON p.id_empresa_compradora = e.id_empresa
                LEFT JOIN enderecos end_cli ON p.id_endereco = end_cli.id_endereco
                WHERE p.id_pedido = %s
            """
            cursor.execute(sql, (pedido_id,))
            pedido = cursor.fetchone()
            
            # Verificação de segurança
            acesso_permitido = False
            if usuario_id and pedido and pedido['id_cliente'] == usuario_id: acesso_permitido = True
            if empresa_id and pedido and pedido['id_empresa_compradora'] == empresa_id: acesso_permitido = True

            if not pedido or not acesso_permitido:
                flash('❌ Boleto não encontrado ou acesso negado.', 'error')
                return redirect(url_for('meus_pedidos'))
            
            # Definir quem é o sacado
            if pedido['id_cliente']:
                nome_sacado = pedido['destinatario'] or pedido['cliente_nome']
                email_sacado = pedido['cliente_email']
                endereco_sacado = f"{pedido.get('rua','')}, {pedido.get('numero','')} - {pedido.get('bairro','')}"
            else:
                nome_sacado = pedido['emp_nome']
                email_sacado = pedido['emp_email']
                endereco_sacado = pedido['emp_endereco']

            # Gerar dados do boleto
            vencimento = datetime.now() + timedelta(days=3)
            codigo_barras = gerar_codigo_barras_boleto(pedido_id, pedido['total'], vencimento)
            linha_digitavel = formatar_linha_digitavel(codigo_barras)
            
            # Gerar imagem do código de barras
            imagem_codigo_barras = gerar_imagem_codigo_barras(codigo_barras)
            
            # Buscar produtos do pedido
            cursor.execute("""
                SELECT p.nome, ip.quantidade, ip.preco_unitario
                FROM itens_pedido ip
                JOIN produto p ON ip.id_produto = p.id_produto
                WHERE ip.id_pedido = %s
            """, (pedido_id,))
            
            produtos = cursor.fetchall()
            
            # Preparar dados para o template
            boleto_data = {
                'id_pedido': pedido['id_pedido'],
                'codigo_barras': codigo_barras,
                'linha_digitavel': linha_digitavel,
                'valor': pedido['total'],
                'vencimento': vencimento,
                'data': pedido.get('data_pedido', datetime.now()),
                'data_emissao': pedido.get('data_pedido', datetime.now()).strftime('%d/%m/%Y'),
                'nome': nome_sacado,
                'cliente_nome': nome_sacado,
                'email': email_sacado,
                'endereco': endereco_sacado,
                'imagem_codigo_barras': imagem_codigo_barras
            }
            
            return render_template('visualizar-boleto.html',
                                boleto=boleto_data,
                                produtos=produtos)
            
        except Exception as err:
            print(f"❌ ERRO ao gerar boleto: {err}")
            flash('⚠️ Erro ao gerar boleto.', 'warning')
            return redirect(url_for('meus_pedidos'))
            
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
            if 'conn' in locals() and conn and conn.is_connected():
                conn.close()

    @app.route('/api/baixar-boleto/<int:pedido_id>')
    def baixar_boleto_pdf(pedido_id):
        """Gera HTML do boleto para impressão/salvar como PDF"""
        if 'usuario_id' not in session and 'empresa_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Mesma query híbrida do visualizar_boleto
            usuario_id = session.get('usuario_id')
            empresa_id = session.get('empresa_id')

            sql = """
                SELECT p.*, 
                       c.nome as cliente_nome, c.email as cliente_email,
                       e.nome_fantasia as emp_nome, e.email as emp_email, e.endereco as emp_endereco,
                       end_cli.rua, end_cli.numero, end_cli.bairro, end_cli.cidade, end_cli.cep, end_cli.destinatario
                FROM pedidos p
                LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
                LEFT JOIN empresas e ON p.id_empresa_compradora = e.id_empresa
                LEFT JOIN enderecos end_cli ON p.id_endereco = end_cli.id_endereco
                WHERE p.id_pedido = %s
            """
            cursor.execute(sql, (pedido_id,))
            pedido = cursor.fetchone()
            
            # Verificação de segurança
            acesso_permitido = False
            if usuario_id and pedido and pedido['id_cliente'] == usuario_id: acesso_permitido = True
            if empresa_id and pedido and pedido['id_empresa_compradora'] == empresa_id: acesso_permitido = True

            if not pedido or not acesso_permitido:
                return jsonify({'error': 'Boleto não encontrado'}), 404
            
            # Definir quem é o sacado
            if pedido['id_cliente']:
                nome_sacado = pedido['destinatario'] or pedido['cliente_nome']
                cliente_nome = pedido['cliente_nome']
            else:
                nome_sacado = pedido['emp_nome']
                cliente_nome = pedido['emp_nome']

            # Gerar dados do boleto
            vencimento = datetime.now() + timedelta(days=3)
            codigo_barras = gerar_codigo_barras_boleto(pedido_id, pedido['total'], vencimento)
            linha_digitavel = formatar_linha_digitavel(codigo_barras)
            
            # Gerar imagem do código de barras
            imagem_codigo_barras = gerar_imagem_codigo_barras(codigo_barras)
            
            # Buscar produtos do pedido
            cursor.execute("""
                SELECT p.nome, ip.quantidade, ip.preco_unitario
                FROM itens_pedido ip
                JOIN produto p ON ip.id_produto = p.id_produto
                WHERE ip.id_pedido = %s
            """, (pedido_id,))
            
            produtos = cursor.fetchall()
            
            # Preparar dados para o template
            boleto_data = {
                'id_pedido': pedido['id_pedido'],
                'codigo_barras': codigo_barras,
                'linha_digitavel': linha_digitavel,
                'valor': float(pedido['total']),
                'vencimento': vencimento,
                'vencimento_formatado': vencimento.strftime('%d/%m/%Y'),
                'data_emissao': pedido.get('data_pedido', datetime.now()).strftime('%d/%m/%Y'),
                'data_geracao': datetime.now().strftime('%d/%m/%Y %H:%M'),
                'nome': nome_sacado,
                'cliente_nome': cliente_nome,
                'imagem_codigo_barras': imagem_codigo_barras
            }
            
            # Renderizar template HTML específico para impressão
            html_content = render_template('boleto_impressao.html',
                                        boleto=boleto_data,
                                        produtos=produtos)
            
            # Retornar como HTML para o navegador salvar/imprimir
            response = make_response(html_content)
            response.headers['Content-Type'] = 'text/html'
            response.headers['Content-Disposition'] = f'attachment; filename="boleto_pedido_{pedido_id}.html"'
            
            return response
            
        except Exception as err:
            print(f"❌ ERRO ao gerar boleto para impressão: {err}")
            return jsonify({'error': str(err)}), 500
            
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
            if 'conn' in locals() and conn and conn.is_connected():
                conn.close()

    @app.route('/pagamento/cartao/<int:pedido_id>', methods=['GET', 'POST'])
    def pagamento_cartao(pedido_id):
        """Página para pagamento com cartão de crédito"""
        if 'usuario_id' not in session and 'empresa_id' not in session:
            return redirect(url_for('login'))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Query híbrida para verificar pedido (User ou Empresa)
            usuario_id = session.get('usuario_id')
            empresa_id = session.get('empresa_id')

            sql = """
                SELECT p.*, c.nome as cliente_nome, c.email
                FROM pedidos p
                LEFT JOIN clientes c ON p.id_cliente = c.id_cliente
                WHERE p.id_pedido = %s
            """
            cursor.execute(sql, (pedido_id,))
            pedido = cursor.fetchone()
            
            # Verificação de segurança
            acesso_permitido = False
            if usuario_id and pedido and pedido['id_cliente'] == usuario_id: acesso_permitido = True
            if empresa_id and pedido and pedido['id_empresa_compradora'] == empresa_id: acesso_permitido = True

            if not pedido or not acesso_permitido:
                flash('❌ Pedido não encontrado.', 'error')
                return redirect(url_for('meus_pedidos'))
            
            # Verificar se já foi pago
            if pedido['status'] == 'aprovado':
                flash('✅ Este pedido já foi pago.', 'success')
                return redirect(url_for('detalhes_pedido', pedido_id=pedido_id))
            
            # Buscar itens do pedido para mostrar no resumo
            cursor.execute("""
                SELECT ip.*, p.nome, p.marca
                FROM itens_pedido ip
                JOIN produto p ON ip.id_produto = p.id_produto
                WHERE ip.id_pedido = %s
            """, (pedido_id,))
            
            itens_pedido = cursor.fetchall()
            total_pedido = pedido['total']
            
            if request.method == 'POST':
                # Processar pagamento com cartão
                try:
                    # Dados do formulário
                    nome_titular = request.form.get('nome_titular')
                    numero_cartao = request.form.get('numero_cartao')
                    validade = request.form.get('validade')
                    cvv = request.form.get('cvv')
                    tipo_cartao = request.form.get('tipo_cartao')
                    parcelas = int(request.form.get('parcelas', 1))
                    
                    # Validações básicas
                    if not all([nome_titular, numero_cartao, validade, cvv, tipo_cartao]):
                        flash('❌ Preencha todos os campos do cartão.', 'error')
                        return redirect(url_for('pagamento_cartao', pedido_id=pedido_id))
                    
                    # Simulação de processamento do pagamento
                    import random
                    import string
                    
                    # Gerar código de transação
                    codigo_transacao = 'CART' + ''.join(random.choices(string.digits, k=10))
                    
                    # Detectar bandeira do cartão
                    numero_limpo = numero_cartao.replace(' ', '')
                    if numero_limpo.startswith('4'):
                        bandeira = 'Visa'
                    elif numero_limpo.startswith('5'):
                        bandeira = 'Mastercard'
                    elif numero_limpo.startswith('3'):
                        bandeira = 'American Express'
                    else:
                        bandeira = 'Outra'
                    
                    # Inserir na tabela de pagamentos com cartão (se a tabela existir)
                    # Primeiro verificar se a tabela existe
                    cursor.execute("SHOW TABLES LIKE 'pagamentos_cartao'")
                    tabela_existe = cursor.fetchone()
                    
                    if tabela_existe:
                        cursor.execute("""
                            INSERT INTO pagamentos_cartao (
                                id_pedido, id_cliente, valor,
                                numero_cartao, bandeira, parcelas,
                                status, codigo_transacao
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            pedido_id,
                            usuario_id, # Será NULL se for empresa
                            total_pedido,
                            numero_limpo[-4:],  # Salvar apenas últimos 4 dígitos
                            bandeira,
                            parcelas,
                            'aprovado',
                            codigo_transacao
                        ))
                    
                    # Atualizar status do pedido
                    cursor.execute("""
                        UPDATE pedidos 
                        SET status = 'aprovado' 
                        WHERE id_pedido = %s
                    """, (pedido_id,))
                    
                    # Registrar na tabela geral de pagamentos
                    nome_pagador = pedido['cliente_nome'] if pedido['cliente_nome'] else 'Empresa'
                    cursor.execute("""
                        INSERT INTO pagamentos (nome, email, metodo, valor)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        nome_pagador,
                        pedido.get('email', session.get('usuario_email')),
                        'cartao',
                        total_pedido
                    ))
                    
                    conn.commit()
                    
                    flash(f'✅ Pagamento aprovado! Código: {codigo_transacao}', 'success')
                    return redirect(url_for('compra_sucesso', pedido_id=pedido_id))
                    
                except Exception as err:
                    conn.rollback()
                    flash(f'❌ Erro ao processar pagamento: {err}', 'error')
                    return redirect(url_for('pagamento_cartao', pedido_id=pedido_id))
            
            # GET: mostrar formulário de pagamento
            return render_template('pagamento_cartao.html',
                                pedido_id=pedido_id,
                                itens_pedido=itens_pedido,
                                total_geral=total_pedido,
                                pedido=pedido)
            
        except Exception as err:
            flash(f'Erro ao carregar página de pagamento: {err}', 'error')
            return redirect(url_for('meus_pedidos'))
        finally:
            if 'conn' in locals() and conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/api/confirmar-pagamento/<int:pedido_id>', methods=['POST'])
    def confirmar_pagamento(pedido_id):
        """API para confirmar pagamento - VERSÃO FINAL"""
        # Validação User ou Empresa
        if 'usuario_id' not in session and 'empresa_id' not in session:
             return jsonify({'status': 'error', 'message': 'Não autorizado'}), 401

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Verificar pedido (User ou Empresa)
            usuario_id = session.get('usuario_id')
            empresa_id = session.get('empresa_id')

            sql = "SELECT * FROM pedidos WHERE id_pedido = %s"
            params = [pedido_id]

            if usuario_id:
                sql += " AND id_cliente = %s"
                params.append(usuario_id)
            elif empresa_id:
                sql += " AND id_empresa_compradora = %s"
                params.append(empresa_id)

            cursor.execute(sql, tuple(params))
            pedido = cursor.fetchone()
            
            if not pedido:
                return jsonify({'status': 'error', 'message': 'Pedido não encontrado'}), 404
            
            # Atualizar status
            cursor.execute("""
                UPDATE pedidos SET status = 'aprovado' 
                WHERE id_pedido = %s
            """, (pedido_id,))
            
            # Tenta atualizar PIX se existir
            try:
                cursor.execute("""
                    UPDATE pagamentos_pix SET status = 'pago' 
                    WHERE id_pedido = %s
                """, (pedido_id,))
            except:
                pass
            
            conn.commit()
            
            return jsonify({
                'status': 'success',
                'message': '✅ Pagamento confirmado!',
                'redirect': url_for('compra_sucesso', pedido_id=pedido_id)
            })
            
        except Exception as err:
            print(f"ERRO: {err}")
            return jsonify({'status': 'error', 'message': str(err)}), 500
        finally:
            if 'conn' in locals() and conn.is_connected():
                cursor.close()
                conn.close()
                
    @app.route('/compra-sucesso/<int:pedido_id>')
    def compra_sucesso(pedido_id):
        """Página de sucesso após compra"""
        if 'usuario_id' not in session and 'empresa_id' not in session:
            return redirect(url_for('login'))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            usuario_id = session.get('usuario_id')
            empresa_id = session.get('empresa_id')

            # Buscar pedido (User ou Empresa)
            sql = """
                SELECT p.*, e.* FROM pedidos p
                LEFT JOIN enderecos e ON p.id_endereco = e.id_endereco
                WHERE p.id_pedido = %s
            """
            params = [pedido_id]

            if usuario_id:
                sql += " AND p.id_cliente = %s"
                params.append(usuario_id)
            elif empresa_id:
                sql += " AND p.id_empresa_compradora = %s"
                params.append(empresa_id)

            cursor.execute(sql, tuple(params))
            pedido = cursor.fetchone()
            
            if not pedido:
                flash('❌ Pedido não encontrado.', 'error')
                return redirect(url_for('meus_pedidos'))
            
            # Buscar itens do pedido
            cursor.execute("""
                SELECT ip.*, pr.nome, pr.imagens
                FROM itens_pedido ip
                JOIN produto pr ON ip.id_produto = pr.id_produto
                WHERE ip.id_pedido = %s
            """, (pedido_id,))
            
            itens = cursor.fetchall()
            
            # Processar imagens dos itens
            for item in itens:
                if item.get('imagens'):
                    try:
                        imagens = json.loads(item['imagens'])
                        item['imagem_principal'] = imagens[0] if imagens else None
                    except:
                        item['imagem_principal'] = None
                else:
                    item['imagem_principal'] = None
            
            return render_template('compra-sucesso.html',
                                pedido=pedido,
                                itens=itens,
                                pedido_id=pedido_id)
        
        except Exception as err:
            flash(f'Erro ao carregar dados da compra: {err}', 'error')
            return redirect(url_for('meus_pedidos'))
        finally:
            if 'conn' in locals() and conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/meus-pedidos')
    def meus_pedidos():
        """Lista todos os pedidos do cliente OU empresa"""
        usuario_id = session.get('usuario_id')
        empresa_id = session.get('empresa_id')

        if not usuario_id and not empresa_id:
            return redirect(url_for('login'))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            sql = """
                SELECT p.*, COUNT(ip.id_item) as qtd_itens
                FROM pedidos p
                LEFT JOIN itens_pedido ip ON p.id_pedido = ip.id_pedido
                WHERE 1=1
            """
            params = []
            
            if usuario_id:
                sql += " AND p.id_cliente = %s"
                params.append(usuario_id)
            elif empresa_id:
                sql += " AND p.id_empresa_compradora = %s"
                params.append(empresa_id)

            sql += " GROUP BY p.id_pedido ORDER BY p.data_pedido DESC"

            cursor.execute(sql, tuple(params))
            
            pedidos = cursor.fetchall()
            
            return render_template('meus_pedidos.html', pedidos=pedidos)
        
        except Exception as err:
            flash(f'Erro ao carregar pedidos: {err}', 'error')
            return redirect(url_for('inicio'))
        finally:
            if 'conn' in locals() and conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/meus-pedidos/<int:id_pedido>')
    def detalhes_pedido(id_pedido):
        """Detalhes de um pedido específico"""
        usuario_id = session.get('usuario_id')
        empresa_id = session.get('empresa_id')

        if not usuario_id and not empresa_id:
            return redirect(url_for('login'))

        conn = None
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro de conexão ao buscar detalhes.', 'error')
                return redirect(url_for('meus_pedidos'))

            cursor = conn.cursor(dictionary=True)
            
            # Buscar pedido usando id_pedido (Híbrido)
            sql = """
                SELECT p.*, e.*, pp.status as status_pix
                FROM pedidos p
                LEFT JOIN enderecos e ON p.id_endereco = e.id_endereco
                LEFT JOIN pagamentos_pix pp ON p.id_pedido = pp.id_pedido
                WHERE p.id_pedido = %s
            """
            params = [id_pedido]

            if usuario_id:
                sql += " AND p.id_cliente = %s"
                params.append(usuario_id)
            elif empresa_id:
                sql += " AND p.id_empresa_compradora = %s"
                params.append(empresa_id)

            cursor.execute(sql, tuple(params))
            pedido = cursor.fetchone()
            
            if not pedido:
                flash('❌ Pedido não encontrado.', 'error')
                return redirect(url_for('meus_pedidos'))
            
            # Buscar itens do pedido
            cursor.execute("""
                SELECT ip.*, p.nome, p.marca, p.imagens
                FROM itens_pedido ip
                JOIN produto p ON ip.id_produto = p.id_produto
                WHERE ip.id_pedido = %s
            """, (id_pedido,))
            
            itens = cursor.fetchall()
            
            # Processar imagens
            for item in itens:
                if item.get('imagens'):
                    try:
                        imgs = json.loads(item['imagens'])
                        item['imagem_principal'] = imgs[0] if imgs else None
                    except:
                        item['imagem_principal'] = None
                else:
                    item['imagem_principal'] = None
            
            return render_template('detalhes_pedido.html', 
                                 pedido=pedido, 
                                 itens=itens)
        
        except Exception as err:
            flash(f'Erro ao carregar detalhes: {err}', 'error')
            return redirect(url_for('meus_pedidos'))
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()