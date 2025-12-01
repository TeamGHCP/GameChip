from flask import render_template, flash, session, redirect, url_for, request, jsonify
from models.database import get_db_connection
from utils.decorators import login_required
import os
import json
import mysql.connector
from datetime import datetime
from utils.helpers import calcular_tempo_mercado
from werkzeug.utils import secure_filename
import time

def configure_main_routes(app):
    
    @app.route('/')
    def inicio():
        # ... (código anterior mantido - não alterei esta parte)
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
        # ... (código anterior mantido - não alterei)
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
                    'tempo_mercado': tempo_mercado,
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

    # ROTA TRABALHE CONOSCO - REMOVIDA (substituída pela nova versão abaixo)
    # @app.route('/trabalhe-conosco', methods=['GET', 'POST'])  # REMOVA ESTA ROTA
    # def trabalhe_conosco():
    #     ... código antigo ...

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
    
    # ============================================================================
    # NOVAS ROTAS PARA TRABALHE CONOSCO (VAGAS) - adicionadas dentro de configure_main_routes
    # ============================================================================
    
    # Função auxiliar para upload de PDF
    def allowed_pdf_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['pdf']
    
    @app.route('/trabalhe-conosco')
    def trabalhe_conosco():
        """Página principal com lista de vagas (NOVA VERSÃO)"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Verificar se a tabela vagas existe
            cursor.execute("""
                SELECT COUNT(*) as existe
                FROM information_schema.tables 
                WHERE table_schema = DATABASE() 
                AND table_name = 'vagas'
            """)
            tabela_existe = cursor.fetchone()['existe'] > 0
            
            vagas_list = []
            
            if tabela_existe:
                # Buscar vagas ativas
                cursor.execute("""
                    SELECT * FROM vagas 
                    WHERE status = 'aberta' 
                    ORDER BY data_publicacao DESC
                """)
                vagas = cursor.fetchall()
                
                for vaga in vagas:
                    vagas_list.append({
                        'id_vaga': vaga['id_vaga'],
                        'titulo': vaga['titulo'],
                        'slug': vaga['slug'],
                        'descricao': vaga['descricao'],
                        'requisitos': vaga['requisitos'],
                        'tipo': vaga['tipo'],
                        'data_publicacao': vaga['data_publicacao']
                    })
            else:
                # Se não existir tabela, usar vagas fixas
                vagas_fixas = [
                    {
                        'id_vaga': 1,
                        'titulo': 'Estagiário(a) de Marketing Digital',
                        'slug': 'estagiario-marketing-digital',
                        'descricao': '<h3>Sobre a Vaga</h3><p>Estamos buscando um(a) estagiário(a) de Marketing Digital apaixonado(a) por tecnologia e inovação.</p><ul><li>Acompanhar campanhas de marketing digital</li><li>Criar conteúdo para redes sociais</li><li>Analisar métricas e resultados</li><li>Auxiliar na produção de materiais promocionais</li></ul>',
                        'requisitos': '<h3>Requisitos</h3><ul><li>Cursando Marketing, Publicidade, Administração ou áreas afins</li><li>Conhecimento em redes sociais</li><li>Boa comunicação escrita</li><li>Proatividade e vontade de aprender</li><li>Disponibilidade para estágio de 6h diárias</li></ul>',
                        'tipo': 'Estágio',
                        'data_publicacao': datetime.now()
                    },
                    {
                        'id_vaga': 2,
                        'titulo': 'Designer de Mídias Digitais (Freelancer/Estágio)',
                        'slug': 'designer-midias-digitais',
                        'descricao': '<h3>Sobre a Vaga</h3><p>Buscamos designer criativo para produção de conteúdo visual para redes sociais e materiais de marketing.</p><ul><li>Criar artes para Instagram, Facebook, TikTok</li><li>Desenvolver identidade visual para campanhas</li><li>Produzir materiais promocionais</li><li>Trabalhar com motion graphics (diferencial)</li></ul>',
                        'requisitos': '<h3>Requisitos</h3><ul><li>Conhecimento em Adobe Creative Suite (Photoshop, Illustrator)</li><li>Noções de design para mídias sociais</li><li>Criatividade e atenção aos detalhes</li><li>Portfólio de trabalhos anteriores</li><li>Disponibilidade para home office</li></ul>',
                        'tipo': 'Freelancer',
                        'data_publicacao': datetime.now()
                    },
                    {
                        'id_vaga': 3,
                        'titulo': 'Desenvolvedor(a) Web Front-End',
                        'slug': 'desenvolvedor-front-end',
                        'descricao': '<h3>Sobre a Vaga</h3><p>Desenvolver interfaces modernas e responsivas para nossos sistemas e e-commerce.</p><ul><li>Desenvolvimento de interfaces com HTML, CSS, JavaScript</li><li>Trabalhar com frameworks modernos (React, Vue.js)</li><li>Otimização de performance</li><li>Integração com APIs</li></ul>',
                        'requisitos': '<h3>Requisitos</h3><ul><li>Experiência com HTML5, CSS3, JavaScript</li><li>Conhecimento em React ou Vue.js</li><li>Versionamento com Git</li><li>Responsive design</li><li>Inglês técnico (leitura)</li></ul>',
                        'tipo': 'CLT',
                        'data_publicacao': datetime.now()
                    }
                ]
                vagas_list = vagas_fixas
            
            cursor.close()
            conn.close()
            
            return render_template('trabalhe_conosco.html', vagas=vagas_list)
            
        except Exception as e:
            print(f"Erro ao carregar vagas: {str(e)}")
            return render_template('trabalhe_conosco.html', vagas=[])
    
    @app.route('/vaga/<slug>')
    def detalhes_vaga(slug):
        """Página de detalhes de uma vaga específica"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            
            # Buscar vaga pelo slug
            cursor.execute("SELECT * FROM vagas WHERE slug = %s", (slug,))
            vaga = cursor.fetchone()
            
            if not vaga:
                flash('Vaga não encontrada.', 'error')
                return redirect(url_for('trabalhe_conosco'))
            
            cursor.close()
            conn.close()
            
            return render_template('detalhes_vaga.html', vaga=vaga)
            
        except Exception as e:
            print(f"Erro ao carregar vaga: {str(e)}")
            flash('Erro ao carregar detalhes da vaga.', 'error')
            return redirect(url_for('trabalhe_conosco'))
    
    @app.route('/candidatar-vaga/<int:id_vaga>', methods=['POST'])
    def candidatar_vaga(id_vaga):
        """Processar candidatura para uma vaga específica"""
        try:
            # Validar campos obrigatórios
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            telefone = request.form.get('telefone', '').strip()
            linkedin = request.form.get('linkedin', '').strip()
            mensagem = request.form.get('mensagem', '').strip()
            vaga_nome = request.form.get('vaga', '').strip()
            
            if not all([nome, email]):
                flash('❌ Preencha todos os campos obrigatórios.', 'error')
                return redirect(request.referrer or url_for('trabalhe_conosco'))
            
            # Validar LinkedIn
            if linkedin and not (linkedin.startswith(('https://linkedin.com/', 'http://linkedin.com/', 
                                                    'https://www.linkedin.com/', 'http://www.linkedin.com/'))):
                flash('❌ O link do LinkedIn deve começar com linkedin.com', 'error')
                return redirect(request.referrer or url_for('trabalhe_conosco'))
            
            # Processar upload do PDF
            if 'curriculo_pdf' not in request.files:
                flash('❌ É necessário enviar um currículo em PDF.', 'error')
                return redirect(request.referrer or url_for('trabalhe_conosco'))
            
            file = request.files['curriculo_pdf']
            
            if file.filename == '':
                flash('❌ Nenhum arquivo selecionado.', 'error')
                return redirect(request.referrer or url_for('trabalhe_conosco'))
            
            if not allowed_pdf_file(file.filename):
                flash('❌ Apenas arquivos PDF são permitidos.', 'error')
                return redirect(request.referrer or url_for('trabalhe_conosco'))
            
            # Gerar nome único para o arquivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_arquivo = secure_filename(f"{timestamp}_{vaga_nome[:20]}_{file.filename}")
            
            # Criar pasta para o mês atual
            pasta_mensal = os.path.join(app.root_path, 'static', 'uploads', 'curriculos', 
                                       datetime.now().strftime("%Y_%m"))
            os.makedirs(pasta_mensal, exist_ok=True)
            
            # Salvar arquivo
            filepath = os.path.join(pasta_mensal, nome_arquivo)
            file.save(filepath)
            
            # Salvar no banco de dados
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO concorrentes 
                (nome, email, telefone, vaga, linkedin_url, mensagem, arquivo_pdf, status, data_candidatura)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pendente', NOW())
            """, (nome, email, telefone, vaga_nome, linkedin, mensagem, nome_arquivo))
            
            conn.commit()
            
            cursor.close()
            conn.close()
            
            # Redirecionar para página de sucesso
            return redirect(url_for('candidatura_sucesso'))
            
        except Exception as e:
            print(f"Erro ao processar candidatura: {str(e)}")
            flash('❌ Erro ao processar sua candidatura. Tente novamente.', 'error')
            return redirect(request.referrer or url_for('trabalhe_conosco'))
    
    @app.route('/candidatura-espontanea')
    def candidatura_espontanea():
        """Página para candidatura espontânea"""
        return render_template('candidatura_espontanea.html')
    
    @app.route('/candidatura-sucesso')
    def candidatura_sucesso():
        """Página de confirmação de candidatura"""
        return render_template('trabalhe_conosco_sucesso.html')
    
    @app.route('/processar-candidatura-espontanea', methods=['POST'])
    def processar_candidatura_espontanea():
        """Processar candidatura espontânea"""
        try:
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip()
            telefone = request.form.get('telefone', '').strip()
            interesse = request.form.get('interesse', '').strip()
            linkedin = request.form.get('linkedin', '').strip()
            mensagem = request.form.get('mensagem', '').strip()
            
            if not all([nome, email, interesse]):
                flash('❌ Preencha todos os campos obrigatórios.', 'error')
                return redirect(url_for('candidatura_espontanea'))
            
            # Validar LinkedIn
            if linkedin and not (linkedin.startswith(('https://linkedin.com/', 'http://linkedin.com/', 
                                                    'https://www.linkedin.com/', 'http://www.linkedin.com/'))):
                flash('❌ O link do LinkedIn deve começar com linkedin.com', 'error')
                return redirect(url_for('candidatura_espontanea'))
            
            # Processar upload do PDF
            if 'curriculo_pdf' not in request.files:
                flash('❌ É necessário enviar um currículo em PDF.', 'error')
                return redirect(url_for('candidatura_espontanea'))
            
            file = request.files['curriculo_pdf']
            
            if file.filename == '':
                flash('❌ Nenhum arquivo selecionado.', 'error')
                return redirect(url_for('candidatura_espontanea'))
            
            if not allowed_pdf_file(file.filename):
                flash('❌ Apenas arquivos PDF são permitidos.', 'error')
                return redirect(url_for('candidatura_espontanea'))
            
            # Gerar nome único para o arquivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nome_arquivo = secure_filename(f"{timestamp}_espontanea_{file.filename}")
            
            # Criar pasta para o mês atual
            pasta_mensal = os.path.join(app.root_path, 'static', 'uploads', 'curriculos', 
                                       datetime.now().strftime("%Y_%m"))
            os.makedirs(pasta_mensal, exist_ok=True)
            
            # Salvar arquivo
            filepath = os.path.join(pasta_mensal, nome_arquivo)
            file.save(filepath)
            
            # Salvar no banco de dados
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO concorrentes 
                (nome, email, telefone, interesse, linkedin_url, mensagem, arquivo_pdf, status, data_candidatura)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pendente', NOW())
            """, (nome, email, telefone, interesse, linkedin, mensagem, nome_arquivo))
            
            conn.commit()
            
            cursor.close()
            conn.close()
            
            # Redirecionar para página de sucesso
            return redirect(url_for('candidatura_sucesso'))
            
        except Exception as e:
            print(f"Erro ao processar candidatura espontânea: {str(e)}")
            flash('❌ Erro ao processar sua candidatura. Tente novamente.', 'error')
            return redirect(url_for('candidatura_espontanea'))