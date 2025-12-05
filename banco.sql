-- ==============================================================================
-- ARQUIVO: banco_completo.sql
-- DESCRIÇÃO: Estrutura completa do banco loja_informatica (Corrigido)
-- ==============================================================================

-- 1. CONFIGURAÇÃO INICIAL
DROP DATABASE IF EXISTS loja_informatica;
CREATE DATABASE loja_informatica;
USE loja_informatica;

-- ==============================================================================
-- 2. CRIAÇÃO DE TABELAS (ORDEM DE DEPENDÊNCIA CORRIGIDA)
-- ==============================================================================

-- Tabela funcionarios
CREATE TABLE funcionarios (
    id_funcionario INT PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    senha VARCHAR(255) NOT NULL,
    cargo ENUM('admin', 'gerente', 'vendedor', 'suporte') DEFAULT 'vendedor',
    ativo BOOLEAN DEFAULT TRUE,
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultimo_login TIMESTAMP NULL,
    INDEX idx_email (email),
    INDEX idx_cargo (cargo)
);

-- Tabela produto
CREATE TABLE produto (
    id_produto INT PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(255) NOT NULL,
    marca VARCHAR(255) NOT NULL,
    preco DECIMAL(10, 2) NOT NULL,
    descricao TEXT,
    estoque INT DEFAULT 0,
    imagem VARCHAR(500),
    categoria VARCHAR(100),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    imagens JSON,
    destaque BOOLEAN DEFAULT FALSE,
    peso DECIMAL(8,2) DEFAULT 0,
    dimensoes VARCHAR(50),
    INDEX idx_nome (nome),
    INDEX idx_marca (marca),
    INDEX idx_categoria (categoria),
    INDEX idx_ativo (ativo),
    INDEX idx_preco (preco),
    INDEX idx_estoque (estoque)
);

-- Tabela clientes (Já com ultima_alteracao_senha)
CREATE TABLE clientes (
    id_cliente INT PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    senha VARCHAR(255) NOT NULL,
    ultima_alteracao_senha TIMESTAMP NULL DEFAULT NULL, -- Integrado aqui
    cpf VARCHAR(14) NOT NULL UNIQUE,
    telefone VARCHAR(20),
    endereco TEXT,
    data_nascimento DATE,
    genero ENUM('M', 'F', 'O') DEFAULT NULL,
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ultima_alteracao TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    ativo BOOLEAN DEFAULT TRUE,
    INDEX idx_nome (nome),
    INDEX idx_email (email),
    INDEX idx_cpf (cpf),
    INDEX idx_data_cadastro (data_cadastro)
);

-- Tabela empresas (Já com tema_escuro)
CREATE TABLE empresas (
    id_empresa INT PRIMARY KEY AUTO_INCREMENT,
    razao_social VARCHAR(255) NOT NULL,
    nome_fantasia VARCHAR(255),
    cnpj VARCHAR(18) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    senha VARCHAR(255) NOT NULL,
    telefone VARCHAR(20),
    tipo_empresa ENUM('comprador', 'vendedor', 'ambos') DEFAULT 'comprador',
    endereco TEXT,
    tema_escuro BOOLEAN DEFAULT FALSE, -- Integrado aqui
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ativo BOOLEAN DEFAULT TRUE,
    INDEX idx_cnpj (cnpj),
    INDEX idx_email (email)
);

-- Tabela concorrentes
CREATE TABLE concorrentes (
    id_concorrente INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    telefone VARCHAR(20),
    arquivo_pdf VARCHAR(255),
    linkedin_url VARCHAR(500),
    empresa VARCHAR(255) NOT NULL,
    vaga VARCHAR(255),
    cargo VARCHAR(100),
    interesse VARCHAR(100),
    mensagem TEXT,
    status ENUM('pendente', 'contatado', 'em_negociacao', 'contratado', 'recusado') DEFAULT 'pendente',
    observacoes TEXT,
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_candidatura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_nome (nome),
    INDEX idx_empresa (empresa),
    INDEX idx_status (status),
    INDEX idx_data_cadastro (data_cadastro)
);

-- Tabela vagas
CREATE TABLE vagas (
    id_vaga INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    descricao LONGTEXT NOT NULL,
    requisitos LONGTEXT NOT NULL,
    beneficios TEXT,
    tipo ENUM('CLT', 'PJ', 'Estágio', 'Freelancer') DEFAULT 'CLT',
    status ENUM('aberta', 'pausada', 'encerrada') DEFAULT 'aberta',
    data_publicacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_encerramento DATE,
    INDEX idx_status (status),
    INDEX idx_tipo (tipo)
);

-- Tabela enderecos
CREATE TABLE enderecos (
    id_endereco INT PRIMARY KEY AUTO_INCREMENT,
    id_cliente INT NOT NULL,
    tipo VARCHAR(50) NOT NULL DEFAULT 'Casa',
    destinatario VARCHAR(255) NOT NULL,
    cep VARCHAR(10) NOT NULL,
    estado VARCHAR(2) NOT NULL,
    cidade VARCHAR(100) NOT NULL,
    bairro VARCHAR(100) NOT NULL,
    rua VARCHAR(255) NOT NULL,
    numero VARCHAR(20) NOT NULL,
    complemento VARCHAR(255),
    principal BOOLEAN DEFAULT FALSE,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
    INDEX idx_cliente (id_cliente),
    INDEX idx_principal (id_cliente, principal)
);

-- Tabela pedidos (Corrigida com FK empresa e id_cliente NULLABLE)
CREATE TABLE pedidos (
    id_pedido INT PRIMARY KEY AUTO_INCREMENT,
    id_cliente INT NULL,
    id_empresa_compradora INT NULL, -- Integrado aqui
    id_endereco INT,
    data_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total DECIMAL(10, 2) NOT NULL,
    status ENUM('pendente', 'aprovado', 'enviado', 'entregue', 'cancelado', 'concluido') DEFAULT 'pendente',
    forma_pagamento VARCHAR(50),
    codigo_rastreio VARCHAR(100),
    observacoes TEXT,
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
    FOREIGN KEY (id_endereco) REFERENCES enderecos(id_endereco) ON DELETE SET NULL,
    FOREIGN KEY (id_empresa_compradora) REFERENCES empresas(id_empresa), -- FK Integrada
    INDEX idx_cliente (id_cliente),
    INDEX idx_status (status),
    INDEX idx_data (data_pedido)
);

-- Tabela itens_pedido
CREATE TABLE itens_pedido (
    id_item INT PRIMARY KEY AUTO_INCREMENT,
    id_pedido INT NOT NULL,
    id_produto INT NOT NULL,
    quantidade INT NOT NULL,
    preco_unitario DECIMAL(10, 2) NOT NULL,
    desconto DECIMAL(10, 2) DEFAULT 0,
    FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido) ON DELETE CASCADE,
    FOREIGN KEY (id_produto) REFERENCES produto(id_produto) ON DELETE CASCADE,
    INDEX idx_pedido (id_pedido),
    INDEX idx_produto (id_produto)
);

-- Tabela seguidores
CREATE TABLE seguidores (
    id_seguidor INT AUTO_INCREMENT PRIMARY KEY,
    id_cliente INT NOT NULL,
    id_empresa INT NOT NULL,
    data_seguimento DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_cliente_empresa (id_cliente, id_empresa),
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa) ON DELETE CASCADE
);

-- Tabela preferencias
CREATE TABLE preferencias (
    id_preferencia INT PRIMARY KEY AUTO_INCREMENT,
    id_cliente INT NOT NULL UNIQUE,
    email_notificacoes BOOLEAN DEFAULT TRUE,
    sms_notificacoes BOOLEAN DEFAULT FALSE,
    ofertas_personalizadas BOOLEAN DEFAULT TRUE,
    newsletter BOOLEAN DEFAULT TRUE,
    tema_escuro BOOLEAN DEFAULT FALSE,
    idioma VARCHAR(10) DEFAULT 'pt-BR',
    data_atualizacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE
);

-- Tabela avaliacoes
CREATE TABLE avaliacoes (
    id_avaliacao INT PRIMARY KEY AUTO_INCREMENT,
    id_cliente INT NOT NULL,
    id_produto INT NOT NULL,
    id_empresa INT NULL,
    nota INT CHECK (nota BETWEEN 1 AND 5),
    titulo VARCHAR(200),
    comentario TEXT,
    data_avaliacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    aprovado BOOLEAN DEFAULT TRUE,
    tipo_avaliador ENUM('cliente', 'empresa') DEFAULT 'cliente',
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
    FOREIGN KEY (id_produto) REFERENCES produto(id_produto) ON DELETE CASCADE,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa) ON DELETE CASCADE,
    UNIQUE KEY unique_avaliacao_cliente (id_cliente, id_produto),
    UNIQUE KEY unique_avaliacao_empresa (id_empresa, id_produto),
    INDEX idx_produto (id_produto),
    INDEX idx_nota (nota)
);

-- Tabela avaliacoes_empresas
CREATE TABLE avaliacoes_empresas (
    id_avaliacao INT PRIMARY KEY AUTO_INCREMENT,
    id_empresa_avaliada INT NOT NULL,
    id_cliente INT NULL,
    id_empresa_avaliadora INT NULL,
    nota INT NOT NULL CHECK (nota BETWEEN 1 AND 5),
    titulo VARCHAR(200),
    comentario TEXT,
    data_avaliacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    aprovado BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (id_empresa_avaliada) REFERENCES empresas(id_empresa) ON DELETE CASCADE,
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
    FOREIGN KEY (id_empresa_avaliadora) REFERENCES empresas(id_empresa) ON DELETE CASCADE,
    INDEX idx_empresa (id_empresa_avaliada),
    INDEX idx_nota (nota)
);

-- Tabela historico_senhas
CREATE TABLE historico_senhas (
    id_historico INT PRIMARY KEY AUTO_INCREMENT,
    id_cliente INT NOT NULL,
    senha_antiga VARCHAR(255) NOT NULL,
    data_alteracao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_alteracao VARCHAR(45),
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
    INDEX idx_cliente (id_cliente)
);

-- Tabela carrinho_abandonado
CREATE TABLE carrinho_abandonado (
    id_carrinho INT PRIMARY KEY AUTO_INCREMENT,
    id_cliente INT NOT NULL,
    id_produto INT NOT NULL,
    quantidade INT NOT NULL,
    data_adicao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente) ON DELETE CASCADE,
    FOREIGN KEY (id_produto) REFERENCES produto(id_produto) ON DELETE CASCADE
);

-- Tabela cupons
CREATE TABLE cupons (
    id_cupom INT PRIMARY KEY AUTO_INCREMENT,
    codigo VARCHAR(50) NOT NULL UNIQUE,
    desconto_percentual DECIMAL(5, 2),
    desconto_valor DECIMAL(10, 2),
    valor_minimo DECIMAL(10, 2) DEFAULT 0,
    data_inicio DATE,
    data_fim DATE,
    limite_uso INT DEFAULT NULL,
    vezes_usado INT DEFAULT 0,
    ativo BOOLEAN DEFAULT TRUE,
    INDEX idx_codigo (codigo)
);

-- Tabela ofertas
CREATE TABLE ofertas (
    id_oferta INT PRIMARY KEY AUTO_INCREMENT,
    id_produto INT NOT NULL,
    desconto DECIMAL(5, 2) NOT NULL,
    preco_original DECIMAL(10, 2) NOT NULL,
    preco_com_desconto DECIMAL(10, 2) NOT NULL,
    validade DATE,
    ativa BOOLEAN DEFAULT TRUE,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_produto) REFERENCES produto(id_produto) ON DELETE CASCADE,
    INDEX idx_produto (id_produto),
    INDEX idx_ativa (ativa),
    INDEX idx_validade (validade)
);

-- Tabela logs_sistema
CREATE TABLE logs_sistema (
    id_log INT PRIMARY KEY AUTO_INCREMENT,
    id_funcionario INT,
    acao VARCHAR(255) NOT NULL,
    modulo VARCHAR(100) NOT NULL,
    descricao TEXT,
    ip VARCHAR(45),
    data_log TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_funcionario) REFERENCES funcionarios(id_funcionario) ON DELETE SET NULL,
    INDEX idx_modulo (modulo),
    INDEX idx_data (data_log)
);

-- Tabela suporte
CREATE TABLE suporte (
    id_suporte INT PRIMARY KEY AUTO_INCREMENT,
    nome VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    mensagem TEXT NOT NULL,
    data_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('pendente', 'respondido', 'fechado') DEFAULT 'pendente',
    observacoes TEXT,
    INDEX idx_email (email),
    INDEX idx_status (status)
);

-- Tabela diagnosticos
CREATE TABLE diagnosticos (
    id_diagnostico INT PRIMARY KEY AUTO_INCREMENT,
    nome_cliente VARCHAR(255) NOT NULL,
    telefone VARCHAR(20),
    problema TEXT NOT NULL,
    data_entrada TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('recebido', 'em_analise', 'pronto', 'concluido') DEFAULT 'recebido',
    tecnico_responsavel INT,
    relatorio_final TEXT,
    pecas_defeito TEXT,
    orcamento DECIMAL(10, 2) DEFAULT 0,
    observacoes TEXT,
    data_conclusao TIMESTAMP NULL,
    FOREIGN KEY (tecnico_responsavel) REFERENCES funcionarios(id_funcionario) ON DELETE SET NULL
);

-- Tabela produtos_empresa
CREATE TABLE produtos_empresa (
    id_produto_empresa INT PRIMARY KEY AUTO_INCREMENT,
    id_empresa INT NOT NULL,
    id_produto INT NOT NULL,
    preco_empresa DECIMAL(10,2),
    estoque_empresa INT DEFAULT 0,
    ativo BOOLEAN DEFAULT TRUE,
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_empresa) REFERENCES empresas(id_empresa) ON DELETE CASCADE,
    FOREIGN KEY (id_produto) REFERENCES produto(id_produto) ON DELETE CASCADE,
    UNIQUE KEY unique_produto_empresa (id_empresa, id_produto)
);

-- Tabela pagamentos
CREATE TABLE pagamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100),
    email VARCHAR(100),
    endereco VARCHAR(255),
    metodo VARCHAR(20),
    valor DECIMAL(10,2),
    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela pagamentos_pix
CREATE TABLE IF NOT EXISTS pagamentos_pix (
    id_pagamento_pix INT AUTO_INCREMENT PRIMARY KEY,
    id_pedido INT NOT NULL,
    id_cliente INT NOT NULL,
    chave_pix VARCHAR(255),
    nome_recebedor VARCHAR(255),
    cidade_recebedor VARCHAR(255),
    valor DECIMAL(10, 2) NOT NULL,
    qr_code_base64 LONGTEXT,
    codigo_copia_cola TEXT,
    txid VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pendente',
    data_geracao DATETIME DEFAULT CURRENT_TIMESTAMP,
    data_pagamento DATETIME NULL,
    FOREIGN KEY (id_pedido) REFERENCES pedidos(id_pedido),
    FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente)
);

-- ==============================================================================
-- 3. VIEWS
-- ==============================================================================

CREATE VIEW view_vendas AS
SELECT 
    p.id_pedido,
    c.nome as cliente_nome,
    p.data_pedido,
    p.total,
    p.status,
    COUNT(ip.id_item) as total_itens
FROM pedidos p
JOIN clientes c ON p.id_cliente = c.id_cliente
LEFT JOIN itens_pedido ip ON p.id_pedido = ip.id_pedido
GROUP BY p.id_pedido;

CREATE VIEW view_produtos_mais_vendidos AS
SELECT 
    p.id_produto,
    p.nome,
    p.marca,
    p.categoria,
    COALESCE(SUM(ip.quantidade), 0) as total_vendido,
    COALESCE(SUM(ip.quantidade * ip.preco_unitario), 0) as receita_total
FROM produto p
LEFT JOIN itens_pedido ip ON p.id_produto = ip.id_produto
LEFT JOIN pedidos ped ON ip.id_pedido = ped.id_pedido AND ped.status != 'cancelado'
GROUP BY p.id_produto
ORDER BY total_vendido DESC;

CREATE VIEW view_clientes_ativos AS
SELECT 
    c.id_cliente,
    c.nome,
    c.email,
    COUNT(p.id_pedido) as total_pedidos,
    COALESCE(SUM(p.total), 0) as total_gasto,
    MAX(p.data_pedido) as ultima_compra
FROM clientes c
LEFT JOIN pedidos p ON c.id_cliente = p.id_cliente AND p.status != 'cancelado'
GROUP BY c.id_cliente
ORDER BY total_gasto DESC;

CREATE VIEW view_estoque_baixo AS
SELECT 
    id_produto,
    nome,
    marca,
    estoque,
    categoria
FROM produto
WHERE estoque <= 5 AND ativo = TRUE
ORDER BY estoque ASC;

CREATE VIEW view_relatorios_mensais AS
SELECT 
    YEAR(data_pedido) as ano,
    MONTH(data_pedido) as mes,
    COUNT(*) as total_pedidos,
    COALESCE(SUM(total), 0) as receita_total,
    COALESCE(AVG(total), 0) as ticket_medio,
    COUNT(DISTINCT id_cliente) as clientes_unicos,
    SUM(CASE WHEN status = 'cancelado' THEN 1 ELSE 0 END) as pedidos_cancelados
FROM pedidos
WHERE data_pedido IS NOT NULL
GROUP BY YEAR(data_pedido), MONTH(data_pedido)
ORDER BY ano DESC, mes DESC;

CREATE VIEW view_estoque_critico AS
SELECT 
    p.id_produto,
    p.nome,
    p.marca,
    p.categoria,
    p.estoque,
    p.preco,
    COALESCE(SUM(ip.quantidade), 0) as vendas_mes
FROM produto p
LEFT JOIN itens_pedido ip ON p.id_produto = ip.id_produto
LEFT JOIN pedidos ped ON ip.id_pedido = ped.id_pedido 
    AND ped.data_pedido >= DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY)
    AND ped.status != 'cancelado'
WHERE p.estoque <= 10 AND p.ativo = TRUE
GROUP BY p.id_produto
ORDER BY p.estoque ASC;

-- ==============================================================================
-- 4. TRIGGERS (MANTER DELIMITER PARA USO EM CLIENTES SQL)
-- ==============================================================================

DELIMITER //

CREATE TRIGGER after_cliente_senha_update
AFTER UPDATE ON clientes
FOR EACH ROW
BEGIN
    IF OLD.senha != NEW.senha THEN
        INSERT INTO historico_senhas (id_cliente, senha_antiga, ip_alteracao)
        VALUES (NEW.id_cliente, OLD.senha, '127.0.0.1');
    END IF;
END//

CREATE TRIGGER after_pedido_insert
AFTER INSERT ON itens_pedido
FOR EACH ROW
BEGIN
    UPDATE produto 
    SET estoque = estoque - NEW.quantidade 
    WHERE id_produto = NEW.id_produto;
END//

CREATE TRIGGER after_pedido_cancel
AFTER UPDATE ON pedidos
FOR EACH ROW
BEGIN
    IF NEW.status = 'cancelado' AND OLD.status != 'cancelado' THEN
        UPDATE produto p
        JOIN itens_pedido ip ON p.id_produto = ip.id_produto
        SET p.estoque = p.estoque + ip.quantidade
        WHERE ip.id_pedido = NEW.id_pedido;
    END IF;
END//

CREATE TRIGGER after_funcionario_login
AFTER UPDATE ON funcionarios
FOR EACH ROW
BEGIN
    IF NEW.ultimo_login IS NOT NULL AND (OLD.ultimo_login IS NULL OR NEW.ultimo_login != OLD.ultimo_login) THEN
        INSERT INTO logs_sistema (id_funcionario, acao, modulo, descricao)
        VALUES (NEW.id_funcionario, 'LOGIN', 'AUTENTICACAO', CONCAT('Login realizado por ', NEW.nome));
    END IF;
END//

DELIMITER ;

-- ==============================================================================
-- 5. PROCEDURES & FUNCTIONS
-- ==============================================================================

DELIMITER //

CREATE PROCEDURE sp_estatisticas_vendas(IN data_inicio DATE, IN data_fim DATE)
BEGIN
    SELECT 
        COUNT(*) as total_pedidos,
        SUM(total) as receita_total,
        AVG(total) as ticket_medio,
        COUNT(DISTINCT id_cliente) as clientes_unicos
    FROM pedidos
    WHERE DATE(data_pedido) BETWEEN data_inicio AND data_fim
    AND status != 'cancelado';
END//

CREATE PROCEDURE sp_aumento_preco_categoria(IN categoria_nome VARCHAR(100), IN percentual DECIMAL(5,2))
BEGIN
    UPDATE produto 
    SET preco = preco * (1 + percentual/100)
    WHERE categoria = categoria_nome AND ativo = TRUE;
END//

CREATE FUNCTION fn_calcular_idade(data_nascimento DATE)
RETURNS INT
READS SQL DATA
DETERMINISTIC
BEGIN
    RETURN TIMESTAMPDIFF(YEAR, data_nascimento, CURDATE());
END//

CREATE FUNCTION fn_verificar_estoque(id_prod INT, qtd INT)
RETURNS BOOLEAN
READS SQL DATA
DETERMINISTIC
BEGIN
    DECLARE estoque_atual INT;
    SELECT estoque INTO estoque_atual FROM produto WHERE id_produto = id_prod;
    RETURN estoque_atual >= qtd;
END//

DELIMITER ;

-- ==============================================================================
-- 6. INSERÇÃO DE DADOS INICIAIS
-- ==============================================================================

INSERT INTO vagas (titulo, slug, descricao, requisitos, tipo) VALUES
('Estagiário(a) de Marketing Digital', 'estagiario-marketing-digital', 'Descrição...', 'Requisitos...', 'Estágio'),
('Desenvolvedor(a) Web Front-End', 'desenvolvedor-front-end', 'Descrição...', 'Requisitos...', 'CLT'),
('Desenvolvedor(a) Back-End (Python/Flask)', 'desenvolvedor-back-end-python', 'Descrição...', 'Requisitos...', 'CLT'),
('Suporte ao Cliente', 'suporte-cliente', 'Descrição...', 'Requisitos...', 'CLT');

-- Finalização
SELECT '✅ Banco de dados loja_informatica recriado com sucesso!' as Status;