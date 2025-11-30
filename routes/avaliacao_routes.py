from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from models.database import get_db_connection
from utils.decorators import login_required
import json
import mysql.connector

avaliacao_bp = Blueprint('avaliacao', __name__)

def verificar_pagamento_banco(id_cliente):
    """Verifica se existe PELO MENOS UM pedido pago (aprovado/concluido/etc)"""
    try:
        if session.get('pagamento_confirmado'):
            return True
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id_pedido 
            FROM pedidos 
            WHERE id_cliente = %s 
            AND status IN ('aprovado', 'enviado', 'entregue', 'concluido')
            LIMIT 1
        """, (id_cliente,))
        
        pedido = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if pedido:
            session['pagamento_confirmado'] = True
            return True
        return False
    except Exception as e:
        print(f"Erro ao verificar pagamento: {e}")
        return False

def buscar_produto_por_id(id_produto):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM produto WHERE id_produto = %s AND ativo = TRUE", (id_produto,))
    produto = cursor.fetchone()
    if produto and produto.get('imagens'):
        try:
            produto['imagens'] = json.loads(produto['imagens'])
        except:
            produto['imagens'] = []
    cursor.close()
    conn.close()
    return produto

@avaliacao_bp.route('/produto/<int:id_produto>/avaliar', methods=['GET', 'POST'])
@login_required
def criar_avaliacao(id_produto):
    if 'empresa_id' not in session:
        if not verificar_pagamento_banco(session['usuario_id']):
            flash('❌ Você precisa ter um pedido pago/aprovado para avaliar os produtos', 'error')
            return redirect(url_for('avaliacao.minhas_avaliacoes_pendentes'))
    
    produto = buscar_produto_por_id(id_produto)
    if not produto:
        flash('Produto não encontrado', 'error')
        return redirect(url_for('listar_produtos'))
    
    if request.method == 'POST':
        nota = request.form.get('nota', type=int)
        titulo = request.form.get('titulo', '').strip()
        comentario = request.form.get('comentario', '').strip()
        
        if not nota or nota < 1 or nota > 5 or not comentario:
            flash('Preencha os campos obrigatórios', 'error')
            return render_template('avaliacoes.html', produto=produto)
        
        if len(comentario) < 10:
            flash('O comentário deve ter pelo menos 10 caracteres', 'error')
            return render_template('avaliacoes.html', produto=produto)
        
        return redirect(url_for('avaliar_produto', id_produto=id_produto), code=307)
    
    return render_template('avaliacoes.html', produto=produto)

@avaliacao_bp.route('/minhas-avaliacoes-pendentes')
@login_required
def minhas_avaliacoes_pendentes():
    if 'empresa_id' in session:
        flash('❌ Exclusivo para clientes.', 'error')
        return redirect(url_for('painel_empresa'))
    
    if not verificar_pagamento_banco(session['usuario_id']):
        flash('❌ Confirme o pagamento de um pedido para liberar a avaliação.', 'error')
        return redirect(url_for('listar_produtos'))
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Use DISTINCT para evitar duplicatas se o usuario comprou o mesmo item 2x
        cursor.execute("""
            SELECT DISTINCT p.id_produto, p.nome, p.marca, p.categoria, p.imagens
            FROM itens_pedido ip
            JOIN pedidos pd ON ip.id_pedido = pd.id_pedido
            JOIN produto p ON ip.id_produto = p.id_produto
            WHERE pd.id_cliente = %s 
            AND pd.status IN ('aprovado', 'enviado', 'entregue', 'concluido') 
            AND p.id_produto NOT IN (
                SELECT id_produto FROM avaliacoes WHERE id_cliente = %s
            )
            ORDER BY p.nome
            LIMIT 20
        """, (session['usuario_id'], session['usuario_id']))
        
        produtos = cursor.fetchall()
        
        for produto in produtos:
            if produto.get('imagens'):
                try:
                    produto['imagens'] = json.loads(produto['imagens'])
                except:
                    produto['imagens'] = []
        
        cursor.close()
        conn.close()
        
        if not produtos:
            flash('ℹ️ Você já avaliou todos os seus produtos comprados!', 'info')
            return redirect(url_for('listar_produtos'))
        
        return render_template('avaliacoes-pendentes.html', produtos=produtos)
                             
    except Exception as e:
        print(f"❌ Erro: {e}")
        flash('Erro ao carregar produtos', 'error')
        return redirect(url_for('listar_produtos'))