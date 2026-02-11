# 🎮 GameChip

**GameChip** é um sistema web completo desenvolvido em Python/Flask para gerenciamento de catálogos e transações de jogos. A plataforma funciona como uma loja ou biblioteca virtual, permitindo a administração de produtos, usuários, avaliações e vendas através de um painel de controle intuitivo.

## ✨ Funcionalidades Principais

*   **Catálogo de Jogos**: Cadastro, edição e exibição de jogos com detalhes como título, descrição, preço e categoria.
*   **Sistema de Usuários**: Registro, autenticação e perfis com níveis de permissão (comum e administrador).
*   **Avaliações e Comentários**: Usuários podem avaliar jogos e deixar feedback.
*   **Painel Administrativo**: Interface dedicada para gestão completa do conteúdo e usuários da plataforma.
*   **Gestão de Transações**: Módulo para acompanhar vendas ou trocas de jogos entre usuários.
*   **Interface Responsiva**: Frontend desenvolvido com HTML e CSS para uma boa experiência de usuário.

## 🛠️ Stack Tecnológica

*   **Backend**: Python 3 com Framework Flask
*   **Frontend**: HTML, CSS
*   **Banco de Dados**: MySQL
*   **Gerenciamento de Dependências**: PIP (arquivo `requirements.txt`)
*   **Controle de Versão**: Git

## 📁 Estrutura do Projeto
GameChip/
* ├── app.py              
* ├── config.py           
* ├── banco.sql           
* ├── requirements.txt    
* ├── models/             
* ├── routes/             
* ├── view/               
* ├── static/             
* ├── utils/
* └── __pycache__/

## 🚀 Instalação e Configuração

### Pré-requisitos
*   Python 3.8 ou superior
*   PIP (gerenciador de pacotes do Python)
*   Servidor MySQL (local ou remoto)

### Passos para Executar

1.  **Clone o repositório**:
    ```bash
    git clone https://github.com/TeamGHCP/GameChip.git
    cd GameChip
    ```

2.  **Configure o ambiente virtual** (recomendado):
    ```bash
    python -m venv venv
    # No Linux/macOS:
    source venv/bin/activate
    # No Windows:
    venv\Scripts\activate
    ```

3.  **Instale as dependências**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure o Banco de Dados**:
    *   Crie um banco de dados MySQL.
    *   Execute o script `banco.sql` para criar as tabelas.
    *   Atualize as credenciais de conexão no arquivo `config.py`.

5.  **Execute a aplicação**:
    ```bash
    python app.py
    ```
    A aplicação estará disponível em `http://localhost:5000`.

## 🤝 Como Contribuir

Contribuições são bem-vindas! Siga os passos:

1.  Faça um Fork do projeto.
2.  Crie uma Branch para sua feature (`git checkout -b feature/NovaFuncionalidade`).
3.  Commit suas mudanças (`git commit -m 'Adiciona NovaFuncionalidade'`).
4.  Faça Push para a Branch (`git push origin feature/NovaFuncionalidade`).
5.  Abra um Pull Request.

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 📞 Contato

**Equipe GHCP** - [Converse conosco](contatoghcp@gmail.com)
