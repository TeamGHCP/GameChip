from flask import render_template, flash, session, redirect, url_for, request, jsonify
from models.database import get_db_connection
from utils.decorators import login_required
import json
import mysql.connector
from datetime import datetime
from utils.helpers import calcular_tempo_mercado # 🔥 ADICIONADO

def configure_main_routes(app):
    
    @app.route('/')
    def inicio():
        # ... (código anterior mantido)
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('index.html', produtos_destaque=[])
            
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT p.* FROM produto p 
                WHERE p.ativo = TRUE 
                ORDER BY p.destaque DESC, p.data_cadastro DESC 
                LIMIT 8
            """)
            produtos_base = cursor.fetchall()
            
            cursor.execute("""
                SELECT o.*, p.nome, p.descricao, p.categoria, p.marca, p.imagens
                FROM ofertas o
                JOIN produto p ON o.id_produto = p.id_produto
                WHERE o.ativa = TRUE 
                AND (o.validade IS NULL OR o.validade >= CURDATE())
                AND p.ativo = TRUE
                ORDER BY o.desconto DESC
                LIMIT 6
            """)
            ofertas = cursor.fetchall()
            
            produtos_destaque = []
            
            for oferta in ofertas:
                produto_com_oferta = {
                    'id_produto': oferta['id_produto'],
                    'nome': oferta['nome'],
                    'descricao': oferta['descricao'],
                    'categoria': oferta['categoria'],
                    'marca': oferta['marca'],
                    'preco': oferta['preco_original'],
                    'preco_com_desconto': oferta['preco_com_desconto'],
                    'desconto': oferta['desconto'],
                    'tem_oferta': True,
                    'imagens': oferta['imagens']
                }
                produtos_destaque.append(produto_com_oferta)
            
            produtos_base_ids = [p['id_produto'] for p in produtos_destaque]
            for produto in produtos_base:
                if produto['id_produto'] not in produtos_base_ids and len(produtos_destaque) < 8:
                    produto_base = {
                        'id_produto': produto['id_produto'],
                        'nome': produto['nome'],
                        'descricao': produto['descricao'],
                        'categoria': produto['categoria'],
                        'marca': produto['marca'],
                        'preco': produto['preco'],
                        'preco_com_desconto': produto['preco'],
                        'desconto': 0,
                        'tem_oferta': False,
                        'imagens': produto['imagens']
                    }
                    produtos_destaque.append(produto_base)
            
            return render_template('index.html', produtos_destaque=produtos_destaque)
            
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar produtos: {err}', 'error')
            return render_template('index.html', produtos_destaque=[])
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/empresas-vendedoras')
    def empresas_vendedoras():
        # ... (código anterior mantido)
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return render_template('empresas_vendedoras.html', empresas=[])
            
            cursor = conn.cursor(dictionary=True)
            
            # Verificar se o usuário já comprou em alguma loja
            usuario_comprou_em_lojas = []
            if 'usuario_id' in session:
                cursor.execute("""
                    SELECT DISTINCT e.id_empresa
                    FROM pedidos p
                    JOIN itens_pedido ip ON p.id_pedido = ip.id_pedido
                    JOIN produtos_empresa pe ON ip.id_produto = pe.id_produto
                    JOIN empresas e ON pe.id_empresa = e.id_empresa
                    WHERE p.id_cliente = %s AND p.status IN ('concluido', 'entregue')
                """, (session['usuario_id'],))
                usuario_comprou_em_lojas = [row['id_empresa'] for row in cursor.fetchall()]
            
            # Buscar empresas vendedoras com estatísticas
            cursor.execute("""
                SELECT 
                    e.id_empresa,
                    e.nome_fantasia,
                    e.razao_social,
                    e.cnpj,
                    e.email,
                    e.telefone,
                    e.tipo_empresa,
                    e.endereco,
                    e.data_cadastro,
                    COUNT(DISTINCT pe.id_produto) as total_produtos,
                    COALESCE(AVG(ae.nota), 0) as media_avaliacoes,
                    COUNT(DISTINCT ae.id_avaliacao) as total_avaliacoes,
                    COUNT(DISTINCT p.id_pedido) as total_vendas
                FROM empresas e
                LEFT JOIN produtos_empresa pe ON e.id_empresa = pe.id_empresa AND pe.ativo = TRUE
                LEFT JOIN avaliacoes_empresas ae ON e.id_empresa = ae.id_empresa_avaliada AND ae.aprovado = TRUE
                LEFT JOIN (
                    SELECT DISTINCT pe2.id_empresa, p2.id_pedido
                    FROM pedidos p2
                    JOIN itens_pedido ip ON p2.id_pedido = ip.id_pedido
                    JOIN produtos_empresa pe2 ON ip.id_produto = pe2.id_produto
                    WHERE p2.status IN ('concluido', 'entregue')
                ) p ON e.id_empresa = p.id_empresa
                WHERE e.tipo_empresa IN ('vendedor', 'ambos') AND e.ativo = TRUE
                GROUP BY e.id_empresa
                ORDER BY media_avaliacoes DESC, total_produtos DESC
            """)
            
            empresas_db = cursor.fetchall()
            
            # Processar dados das empresas corretamente
            empresas_processadas = []
            for empresa in empresas_db:
                nome_exibicao = empresa['nome_fantasia'] or empresa['razao_social']
                
                # 🔥 CORREÇÃO: Usar função auxiliar para tempo de mercado
                tempo_mercado = calcular_tempo_mercado(empresa['data_cadastro']) 
                
                # Garantir que os valores não sejam None
                media_avaliacoes = empresa['media_avaliacoes'] or 0
                total_produtos = empresa['total_produtos'] or 0
                total_vendas = empresa['total_vendas'] or 0
                total_avaliacoes = empresa['total_avaliacoes'] or 0
                
                empresas_processadas.append({
                    'id': empresa['id_empresa'],
                    'nome': nome_exibicao,
                    'categoria': 'Tecnologia',
                    'descricao': f"CNPJ: {empresa['cnpj']} | Telefone: {empresa['telefone'] or 'Não informado'}",
                    'logo': nome_exibicao[0].upper() if nome_exibicao else 'E',
                    'avaliacao': round(float(media_avaliacoes), 1),
                    'total_avaliacoes': total_avaliacoes,
                    'total_produtos': total_produtos,
                    'total_vendas': total_vendas,
                    'tempo_mercado': tempo_mercado, # ✅ VALOR CORRIGIDO
                    'features': ["🚚 Entrega Rápida", "💳 Parcelamento", "🛡️ Garantia"],
                    'pode_avaliar': empresa['id_empresa'] in usuario_comprou_em_lojas if 'usuario_id' in session else False
                })
            
            return render_template('empresas_vendedoras.html', 
                                 empresas=empresas_processadas,
                                 usuario_comprou_em_lojas=usuario_comprou_em_lojas)
        
        except mysql.connector.Error as err:
            flash(f'Erro ao carregar empresas: {err}', 'error')
            return render_template('empresas_vendedoras.html', empresas=[])
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    # Rotas de informações e páginas estáticas
    @app.route('/sobre')
    def sobre_nos():
        return render_template('sobre.html')

    @app.route('/contato', methods=['GET', 'POST'])
    def contato():
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            telefone = request.form.get('telefone', '').strip()
            assunto = request.form.get('assunto', '').strip()
            mensagem = request.form.get('mensagem', '').strip()
            
            if not all([nome, email, assunto, mensagem]):
                flash('❌ Por favor, preencha todos os campos obrigatórios.', 'error')
                return render_template('contato.html')
            
            try:
                conn = get_db_connection()
                if not conn:
                    flash('Erro ao conectar ao banco de dados.', 'error')
                    return render_template('contato.html')
                
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO suporte (nome, email, mensagem, status)
                    VALUES (%s, %s, %s, %s)
                """, (nome, email, f"ASSUNTO: {assunto}\nTELEFONE: {telefone}\nMENSAGEM: {mensagem}", "pendente"))
                
                conn.commit()
                
                flash('✅ Mensagem enviada com sucesso! Entraremos em contato em breve.', 'success')
                return redirect(url_for('contato_sucesso'))
                
            except mysql.connector.Error as err:
                flash(f'❌ Erro ao enviar mensagem: {err}', 'error')
                return render_template('contato.html')
            
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

        return render_template('contato.html')

    @app.route('/contato-sucesso')
    def contato_sucesso():
        return render_template('contato_sucesso.html')

    @app.route('/faq')
    def faq():
        return render_template('faq.html')

    @app.route('/termos')
    def termos():
        return render_template('termos.html')

    @app.route('/privacidade')
    def privacidade():
        return render_template('privacidade.html')

    @app.route('/cookies')
    def cookies():
        return render_template('cookies.html')

    @app.route('/prazos')
    def prazos():
        return render_template('prazos.html')

    @app.route('/formas-pagamento')
    def formas_pagamento():
        return render_template('formas_pagamento.html')

    @app.route('/trocas')
    def trocas():
        return render_template('trocas.html')

    @app.route('/central-ativacao')
    def central_ativacao():
        return render_template('central-ativacao.html')

    @app.route('/condicoes')
    def condicoes():
        return render_template('condicoes.html')

    @app.route('/monte-seu-pc')
    def monte_seu_pc():
        return render_template('monte_seu_pc.html')

    @app.route('/assistencia')
    def assistencia():
        return render_template('assistencia.html')

    @app.route('/blog')
    def blog():
        return render_template('blog.html')

    @app.route('/newsletter')
    def newsletter():
        return render_template('newsletter.html')

    @app.route('/central-garantia')
    def garantia():
        return render_template('central-garantia.html', titulo="Central de Garantia")

    @app.route('/trabalhe-conosco', methods=['GET', 'POST'])
    def trabalhe_conosco():
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            telefone = request.form.get('telefone', '').strip()
            formacao = request.form.get('formacao', '').strip()
            conhecimento = request.form.get('conhecimento', '').strip()
            ingles = request.form.get('ingles', '').strip()
            seguranca = request.form.get('seguranca', '').strip()
            
            if not all([nome, email, formacao, conhecimento, ingles, seguranca]):
                flash('❌ Por favor, preencha todos os campos obrigatórios.', 'error')
                return render_template('trabalhe_conosco.html')
            
            try:
                conn = get_db_connection()
                if not conn:
                    flash('Erro ao conectar ao banco de dados.', 'error')
                    return render_template('trabalhe_conosco.html')
                
                cursor = conn.cursor()
                
                mensagem_completa = f"""
                FORMAÇÃO: {formacao}
                CONHECIMENTO PRÁTICO: {conhecimento}
                INGLÊS: {ingles}
                SEGURANÇA DA INFORMAÇÃO: {seguranca}
                TELEFONE: {telefone if telefone else 'Não informado'}
                """
                
                cursor.execute("""
                    INSERT INTO concorrentes (nome, email, telefone, empresa, cargo, interesse, mensagem, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (nome, email, telefone, "Candidato GHCP", "Candidato", "Trabalhe Conosco", mensagem_completa, "pendente"))
                
                conn.commit()
                
                flash('✅ Seus dados foram enviados com sucesso! Entraremos em contato em breve.', 'success')
                return redirect(url_for('trabalhe_conosco_sucesso'))
                
            except mysql.connector.Error as err:
                flash(f'❌ Erro ao enviar dados: {err}', 'error')
                return render_template('trabalhe_conosco.html')
            
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

        return render_template('trabalhe_conosco.html')

    @app.route('/trabalhe-conosco-sucesso')
    def trabalhe_conosco_sucesso():
        return render_template('trabalhe_conosco_sucesso.html')

    # Rotas de suporte
    @app.route("/suporte", methods=["GET", "POST"])
    def suporte():
        if request.method == "POST":
            nome = request.form.get("nome")
            email = request.form.get("email")
            mensagem = request.form.get("mensagem")
            if not (nome and email and mensagem):
                flash("Preencha todos os campos corretamente.", "warning")
                return render_template("suporte.html", titulo="Suporte")
            conn = None
            cursor = None
            try:
                conn = get_db_connection()
                if conn is None:
                    flash("Não foi possível conectar ao banco de dados.", "danger")
                    return render_template("suporte.html", titulo="Suporte")
                cursor = conn.cursor()
                sql = "INSERT INTO suporte (nome, email, mensagem) VALUES (%s, %s, %s)"
                cursor.execute(sql, (nome, email, mensagem))
                conn.commit()
                flash("Mensagem enviada com sucesso!", "success")
                return redirect(url_for("suporte_sucesso"))
            except mysql.connector.Error as err:
                print(f"[ERRO MySQL] Falha ao inserir dados de suporte: {err}")
                if conn:
                    conn.rollback()
                flash("Ocorreu um erro ao enviar sua mensagem. Tente novamente.", "danger")
                return render_template("suporte.html", titulo="Suporte")
            finally:
                if cursor:
                    cursor.close()
                if conn and conn.is_connected():
                    conn.close()
        return render_template("suporte.html", titulo="Suporte")

    @app.route("/msg-suporte")
    def suporte_sucesso():
        return render_template("msg-suporte.html", titulo="Mensagem Enviada")

    @app.route('/msg-suporte')
    def mensagem_suporte():
        return render_template('msg-suporte.html')

    # Rotas de diagnóstico
    @app.route('/diagnostico', methods=['GET', 'POST'])
    def diagnostico():
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip().lower()
            telefone = request.form.get('telefone', '').strip()
            tipo_equipamento = request.form.get('tipo_equipamento', '').strip()
            marca = request.form.get('marca', '').strip()
            modelo = request.form.get('modelo', '').strip()
            problema = request.form.get('problema', '').strip()
            sintomas = request.form.get('sintomas', '').strip()
            if not all([nome, email, tipo_equipamento, problema]):
                flash('❌ Preencha todos os campos obrigatórios.', 'error')
                return render_template('diagnostico.html')
            try:
                conn = get_db_connection()
                if not conn:
                    flash('Erro ao conectar ao banco de dados.', 'error')
                    return render_template('diagnostico.html')
                cursor = conn.cursor()
                id_cliente = None
                if session.get('usuario_id'):
                    cursor.execute("SELECT id_cliente FROM clientes WHERE id_cliente = %s", (session['usuario_id'],))
                    if cursor.fetchone():
                        id_cliente = session['usuario_id']
                cursor.execute("""
                    INSERT INTO diagnosticos (id_cliente, nome_cliente, email, telefone, tipo_equipamento, marca, modelo, problema, sintomas)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (id_cliente, nome, email, telefone, tipo_equipamento, marca, modelo, problema, sintomas))
                conn.commit()
                flash('✅ Diagnóstico solicitado com sucesso! Entraremos em contato em breve.', 'success')
                return redirect(url_for('inicio'))
            except mysql.connector.Error as err:
                flash(f'Erro ao solicitar diagnóstico: {err}', 'error')
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()
        return render_template('diagnostico.html')

    # Rotas de pagamento
    @app.route('/pix')
    def pix():
        return render_template('pix.html')

    @app.route('/boleto')
    def boleto():
        return render_template('boleto.html')

    @app.route('/cartoes')
    def cartoes():
        return render_template('cartoes.html')

    # Rotas de API
    @app.route('/api/avaliacoes-empresa/<int:id_empresa>')
    def api_avaliacoes_empresa(id_empresa):
        try:
            conn = get_db_connection()
            if not conn:
                return jsonify([])
            
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT ae.*, 
                       COALESCE(c.nome, e.nome_fantasia, e.razao_social) as avaliador_nome
                FROM avaliacoes_empresas ae
                LEFT JOIN clientes c ON ae.id_cliente = c.id_cliente
                LEFT JOIN empresas e ON ae.id_empresa_avaliadora = e.id_empresa
                WHERE ae.id_empresa_avaliada = %s AND ae.aprovado = TRUE
                ORDER BY ae.data_avaliacao DESC
                LIMIT 10
            """, (id_empresa,))
            
            avaliacoes = cursor.fetchall()
            
            return jsonify(avaliacoes)
        
        except mysql.connector.Error:
            return jsonify([])
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    @app.route('/avaliar-empresa/<int:id_empresa>', methods=['POST'])
    @login_required
    def avaliar_empresa(id_empresa):
        nota = request.form.get('nota', type=int)
        titulo = request.form.get('titulo', '').strip()
        comentario = request.form.get('comentario', '').strip()
        
        if not nota or nota < 1 or nota > 5:
            flash('❌ Nota inválida. Deve ser entre 1 e 5.', 'error')
            return redirect(request.referrer or url_for('inicio'))
        
        if not comentario:
            flash('❌ Por favor, escreva um comentário.', 'error')
            return redirect(request.referrer or url_for('inicio'))
        
        try:
            conn = get_db_connection()
            if not conn:
                flash('Erro ao conectar ao banco de dados.', 'error')
                return redirect(request.referrer or url_for('inicio'))
            
            cursor = conn.cursor()
            
            if 'usuario_id' in session:
                cursor.execute("""
                    SELECT id_avaliacao FROM avaliacoes_empresas 
                    WHERE id_cliente = %s AND id_empresa_avaliada = %s
                """, (session['usuario_id'], id_empresa))
                
                if cursor.fetchone():
                    flash('⚠️ Você já avaliou esta empresa.', 'warning')
                    return redirect(request.referrer or url_for('inicio'))
                
                cursor.execute("""
                    INSERT INTO avaliacoes_empresas (id_empresa_avaliada, id_cliente, nota, titulo, comentario)
                    VALUES (%s, %s, %s, %s, %s)
                """, (id_empresa, session['usuario_id'], nota, titulo, comentario))
            
            elif 'empresa_id' in session:
                if session['empresa_id'] == id_empresa:
                    flash('❌ Você não pode avaliar sua própria empresa.', 'error')
                    return redirect(request.referrer or url_for('inicio'))
                
                cursor.execute("""
                    SELECT id_avaliacao FROM avaliacoes_empresas 
                    WHERE id_empresa_avaliadora = %s AND id_empresa_avaliada = %s
                """, (session['empresa_id'], id_empresa))
                
                if cursor.fetchone():
                    flash('⚠️ Sua empresa já avaliou esta empresa.', 'warning')
                    return redirect(request.referrer or url_for('inicio'))
                
                cursor.execute("""
                    INSERT INTO avaliacoes_empresas (id_empresa_avaliada, id_empresa_avaliadora, nota, titulo, comentario)
                    VALUES (%s, %s, %s, %s, %s)
                """, (id_empresa, session['empresa_id'], nota, titulo, comentario))
            
            conn.commit()
            flash('✅ Avaliação enviada com sucesso!', 'success')
        
        except mysql.connector.Error as err:
            flash(f'Erro ao enviar avaliação: {err}', 'error')
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
        
        return redirect(request.referrer or url_for('inicio'))