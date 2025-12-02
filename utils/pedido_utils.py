# utils/pedido_utils.py

import mysql.connector
from datetime import datetime
from flask import flash
from models.database import get_db_connection

# Variáveis globais/mock para status (idealmente viriam de um arquivo de configuração ou Enum)
STATUS_PEDIDO_PENDENTE = 'pendente'
STATUS_PEDIDO_CONCLUIDO = 'concluido'


def processar_compra_digital(id_cliente, itens_carrinho, metodo_pagamento, valor_total, conn=None):
    """
    Processa a finalização de uma compra, incluindo a criação do pedido,
    verificação e atualização de estoque, e limpeza do carrinho.

    Args:
        id_cliente (int): ID do cliente realizando a compra.
        itens_carrinho (list): Lista de dicionários contendo {'id_produto': X, 'quantidade': Y}.
        metodo_pagamento (str): O método de pagamento escolhido.
        valor_total (float): Valor total do pedido.
        conn (mysql.connector.connection, opcional): Conexão de banco de dados existente.

    Returns:
        tuple: (True/False para sucesso, ID do pedido ou Mensagem de erro)
    """
    
    # 1. Tentar obter ou usar a conexão existente
    if conn is None:
        conn_local = get_db_connection()
    else:
        conn_local = conn
        
    if not conn_local:
        return False, "Erro de conexão com o banco de dados."

    cursor = None
    try:
        cursor = conn_local.cursor()
        
        # 2. Iniciar Transação
        # Garante que todas as operações (criar pedido, itens, atualizar estoque)
        # sejam atômicas (ou todas sucedem, ou todas falham).
        conn_local.start_transaction()

        # 3. Criar o registro do Pedido principal
        sql_pedido = """
            INSERT INTO pedidos (id_cliente, data_pedido, valor_total, status, metodo_pagamento)
            VALUES (%s, NOW(), %s, %s, %s)
        """
        cursor.execute(sql_pedido, (id_cliente, valor_total, STATUS_PEDIDO_PENDENTE, metodo_pagamento))
        id_pedido = cursor.lastrowid
        
        if not id_pedido:
            raise Exception("Não foi possível criar o registro do pedido.")

        # 4. Processar Itens e Atualizar Estoque
        sql_item = """
            INSERT INTO itens_pedido (id_pedido, id_produto, quantidade, preco_unitario_pago)
            VALUES (%s, %s, %s, %s)
        """
        
        sql_estoque_check = "SELECT preco, estoque FROM produtos_empresa WHERE id_produto = %s"
        sql_estoque_update = "UPDATE produtos_empresa SET estoque = estoque - %s WHERE id_produto = %s"

        for item in itens_carrinho:
            produto_id = item['id_produto']
            quantidade = item['quantidade']
            
            # 4a. Verificar preço e estoque (Usando LOCKS em ambiente multi-usuário é ideal,
            # mas simplificamos aqui para um exemplo básico)
            cursor.execute(sql_estoque_check, (produto_id,))
            resultado_produto = cursor.fetchone()
            
            if not resultado_produto:
                raise Exception(f"Produto ID {produto_id} não encontrado ou inativo.")
            
            preco_unitario_pago, estoque_atual = resultado_produto
            
            if estoque_atual < quantidade:
                # Reverter transação se o estoque for insuficiente
                conn_local.rollback()
                return False, f"Estoque insuficiente para o produto ID {produto_id}."
            
            # 4b. Inserir Item do Pedido
            cursor.execute(sql_item, (id_pedido, produto_id, quantidade, preco_unitario_pago))
            
            # 4c. Atualizar Estoque
            cursor.execute(sql_estoque_update, (quantidade, produto_id))

        # 5. Limpar o Carrinho (Remover itens do carrinho do cliente no DB)
        sql_limpar_carrinho = "DELETE FROM carrinho WHERE id_cliente = %s"
        cursor.execute(sql_limpar_carrinho, (id_cliente,))

        # 6. Finalizar Transação
        conn_local.commit()
        
        return True, id_pedido

    except mysql.connector.Error as err:
        # 7. Rollback em caso de erro no DB
        if conn_local and conn_local.in_transaction:
            conn_local.rollback()
        # Logar o erro completo para debug, mas retornar mensagem amigável
        print(f"[ERRO PEDIDO UTILS] Falha ao processar compra: {err}")
        return False, f"Ocorreu um erro no banco de dados. Transação cancelada. ({err.msg})"
        
    except Exception as e:
        # 8. Rollback em caso de erro de lógica
        if conn_local and conn_local.in_transaction:
            conn_local.rollback()
        print(f"[ERRO PEDIDO UTILS] Erro de lógica: {str(e)}")
        return False, str(e)

    finally:
        # 9. Fechar recursos se a conexão foi aberta localmente
        if cursor:
            cursor.close()
        if conn is None and conn_local and conn_local.is_connected():
            conn_local.close()

# Exemplo de função auxiliar (opcional, mas comum)
def obter_detalhes_pedido(id_pedido):
    """
    Busca os detalhes de um pedido.
    """
    conn = get_db_connection()
    if not conn:
        return None
    
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM pedidos WHERE id_pedido = %s", (id_pedido,))
        pedido = cursor.fetchone()
        
        cursor.execute("""
            SELECT ip.*, p.nome 
            FROM itens_pedido ip 
            JOIN produto p ON ip.id_produto = p.id_produto 
            WHERE ip.id_pedido = %s
        """, (id_pedido,))
        itens = cursor.fetchall()
        
        if pedido:
            pedido['itens'] = itens
        
        return pedido
        
    except mysql.connector.Error as err:
        print(f"[ERRO PEDIDO UTILS] Falha ao buscar pedido: {err}")
        return None
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()