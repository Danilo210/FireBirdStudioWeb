# Firebird Studio Web 1.0

**Workbench de bancos Firebird para navegador**, inspirado em ferramentas como IBExpert. Interface em português, com modo demonstração e integração opcional com bancos **Firebird 3.0 ou superiores**.

> **ATENÇÃO:** este projeto não é o IBExpert nem um port oficial. A interface web está funcional; a integração real usa um servidor Python. É uma primeira versão e deve ser testada com banco de homologação antes de usar em produção.

## Recursos

- Interface profissional responsiva, tema claro/escuro e múltiplas abas.
- Árvore de **tabelas, views, procedures, triggers, generators/sequences, domains e índices** lida diretamente de `RDB$...`.
- Editor SQL com cores, linhas, formatação básica, mensagens, resultados tabulares, atalhos `Ctrl+Enter`, `Ctrl+N`, `Ctrl+S`, `Ctrl+B`.
- Consulta paginada de dados; ordenação por coluna; filtro de página; exportação CSV (somente linhas carregadas).
- **Inserção, edição e exclusão de registros** em tabelas com chave primária. Confirmação antes da exclusão.
- Designer visual de tabelas: nome, colunas, tipos, NULL, chave primária; gera e executa `CREATE TABLE`.
- Geração de comandos `ALTER TABLE ADD` e `CREATE INDEX` para revisão no editor SQL.
- Importação de arquivos `.sql` (abre no editor, **não executa automaticamente**).
- Exportação SQL básica de tabelas (sem constraints externas, stored procedures, triggers, domínios, dados ou índices adicionais).
- Criação **opcional** de novos bancos `.fdb` diretamente no servidor Firebird, restrita a diretório aprovado pelo administrador.
- Alternância entre bancos preconfigurados no backend; senha de administração e proteção CSRF; credenciais Firebird nunca enviadas ao navegador.
- Sem CDN nem bibliotecas JS externas. Backend Python/Flask e driver oficial `firebird-driver`.

## 1. Testar sem banco / sem instalar dependências

**Windows**: descompacte o projeto, abra o terminal dentro da pasta e execute:

```sh
py -m http.server 8000
```

Acesse `http://localhost:8000`. O site funciona em **modo demonstração**, com tabelas CLIENTES, PRODUTOS, VENDAS e FUNCIONARIOS e SELECTs básicos. O modo demo guarda os registros **somente em memória**: ao atualizar a página, as alterações desaparecem. Não é um engine Firebird nem um `.fdb` real.

Se abrir `index.html` com duplo clique, URLs absolutos de recursos (`/static/...`) podem não carregar: use o servidor HTTP acima.

## 2. Hospedar no Render (IMPORTANTE)

Este projeto **NÃO é um Static Site**. Para fazer a conexão com Firebird, precisa de um **Web Service (Docker)** no Render.

1. Extraia `FirebirdStudioWeb.zip`.
2. No GitHub, crie um repositório e, por **Add file → Upload files**, arraste os arquivos e subpastas extraídos. Mantenha `Dockerfile`, `app.py`, `index.html`, `requirements.txt` e `static/` na raiz. Você não precisa instalar Git.
3. No Render clique **New → Web Service** e conecte o repositório.
4. Escolha **Language/Runtime: Docker** (o `Dockerfile` está na raiz).
5. Não preencha Build Command nem Start Command do Python: o Dockerfile já instala o cliente Firebird, instala as dependências e inicia o Gunicorn no `PORT` provido pelo Render.
6. Configure as variáveis em **Environment** conforme abaixo.
7. Publique o serviço e abra o URL `https://seu-servico.onrender.com`.

Este Dockerfile utiliza Debian Bookworm e instala `libfbclient2` (cliente nativo Firebird). A aplicação **não instala um servidor de banco de dados Firebird no Render**: conecta-se a um Firebird preexistente através da rede.

### Variáveis obrigatórias para banco real

| Variável | Exemplo / descrição |
|---|---|
| `APP_ADMIN_PASSWORD` | Senha forte para entrar no painel web; **não reutilize a senha SYSDBA**. |
| `APP_SECRET_KEY` | Uma chave longa, secreta e aleatória para assinar sessões Flask. |
| `COOKIE_SECURE` | `1` no Render (HTTPS). |
| `FIREBIRD_HOST` | Endereço do **servidor Firebird acessível pelo Render**, não `localhost` do PC. |
| `FIREBIRD_PORT` | `3050` (se mantiver a porta padrão). |
| `FIREBIRD_DATABASE` | Caminho/alias **no computador servidor Firebird**, ex.: `/var/lib/firebird/data/empresa.fdb`, `C:\Dados\EMPRESA.FDB` ou alias `EMPRESA`. |
| `FIREBIRD_USER` | Usuário Firebird com as permissões adequadas. |
| `FIREBIRD_PASSWORD` | Senha desse usuário. |

**Nunca inclua senhas reais no código ou em arquivos versionados no GitHub!** O `.env.example` é somente documentação, com credenciais fictícias; não é lido automaticamente pelo servidor.

Opcionalmente, `FIREBIRD_NAME=Principal` define o título da conexão.

### Múltiplos bancos

Em vez de `FIREBIRD_DATABASE` e campos relacionados, você pode definir `FIREBIRD_CONNECTIONS_JSON` no Environment do Render, por exemplo (em **uma linha**):

```json
[{"name":"Empresa","host":"firebird-interno","port":3050,"database":"/dados/empresa.fdb","user":"OPERADOR","password":"SENHA"},{"name":"Teste","host":"firebird-interno","port":3050,"database":"/dados/teste.fdb","user":"OPERADOR","password":"SENHA"}]
```

Essa variável é **segredo de servidor** e nunca deve ser exposta em páginas web ou commits. As conexões só são selecionáveis após login.

### Criar novos bancos `.fdb`

Opcional: `FIREBIRD_CREATE_DIRECTORY=/dados/novos_bancos`. A pasta **precisa existir no host do Firebird**, e o usuário Firebird precisa ter autorização para criar banco nela. Depois, o botão **Criar banco de dados** permite usar um nome simples como `cliente_a.fdb`. A operação não altera automaticamente a lista de conexões: registre o novo caminho no Environment.

Não habilite esta função indiscriminadamente em servidores de produção. Não há upload de `.fdb` pelo navegador: o Firebird é responsável por criar e abrir arquivos reais.

## 3. Firebird instalado no seu Windows

Se o banco Firebird roda em seu computador Windows e o site está no Render, `localhost` no Render **não aponta para o seu Windows**. O serviço em nuvem precisa conseguir alcançar o Firebird na rede de forma segura. Para ambiente profissional, prefira VPN privada/serviço interno ou hospede o backend na mesma rede do banco. **Não exponha simplesmente a porta TCP 3050 na internet pública.**

Se preferir rodar o backend na **mesma máquina Windows do Firebird**, instale Python 3.11+ e as dependências (o `fbclient.dll` do Firebird também deve estar acessível no sistema):

```powershell
py -m pip install -r requirements.txt
$env:COOKIE_SECURE="0"
$env:APP_ADMIN_PASSWORD="SENHA_FORTE_AQUI"
$env:APP_SECRET_KEY="UMA_CHAVE_LONGA_E_ALEATORIA"
$env:FIREBIRD_HOST="127.0.0.1"
$env:FIREBIRD_PORT="3050"
$env:FIREBIRD_DATABASE="C:\Dados\EMPRESA.FDB"
$env:FIREBIRD_USER="SYSDBA"
$env:FIREBIRD_PASSWORD="SENHA_DO_FIREBIRD"
py app.py
```

Abra `http://localhost:10000` e clique em **Conexões** para entrar com a senha do painel.

## 4. Regras de operação / limites

- A consulta SQL real executa **uma instrução por clique**. Scripts multi-instrução e `SET TERM` do isql não são interpretados. Para procedures, um único `CREATE PROCEDURE ... BEGIN ... END` pode ser executado como uma instrução.
- Até **250 linhas** retornadas por consulta SQL; a grade de tabelas exibe **100 linhas por página** (paginação por `FIRST/SKIP`).
- A API faz `COMMIT` automaticamente em SQL bem-sucedido e `ROLLBACK` em caso de erro. Não há transações manuais persistentes entre chamadas.
- Para atualização ou exclusão pelo formulário, a tabela precisa ter **chave primária**. Operações de SQL livre estão sujeitas às permissões do usuário Firebird.
- Datas, BLOBs, colunas computadas, campos identity e tipos específicos podem exigir comandos SQL manuais; valores `BLOB` aparecem como resumo, não editor de conteúdo.
- O botão **Exportar estrutura** entrega apenas DDL simplificado das tabelas (não um backup completo). Para backup/restore real use `gbak`/`nbackup` do Firebird, fora da ferramenta.
- O aplicativo não faz administração de usuários Firebird, monitoramento avançado, diagrams ER, autocomplete SQL baseado no esquema, execução de scripts inteiros ou migrações automáticas.
- Para uso real, mantenha backup, HTTPS, isolamento de rede e conta SQL com privilégios mínimos. A proteção de login é básica: ambientes públicos/multiusuário devem ser reforçados com controles externos de acesso, MFA/reverse proxy e auditoria.

## 5. Estrutura do repositório

```text
FirebirdStudioWeb/
├── index.html         Interface web
├── static/
│   ├── app.js         Editor SQL, visualizador, designer e modo demo
│   └── styles.css     Temas e layout responsivo
├── app.py             Backend Flask / API Firebird
├── requirements.txt   Dependências Python
├── Dockerfile         Render Web Service (Docker)
├── .dockerignore
├── .env.example       Modelo de variáveis (NÃO contém senhas reais)
└── README.md
```

## 6. Compatibilidade e validação

- Código Python e JavaScript passou por verificações de sintaxe.
- Modo demo testado em Chromium headless: abertura, navegação, SELECT, atualização de registro, criação de tabela visual e tema.
- **Não houve teste de conexão com um Firebird real nem build Docker no ambiente de geração deste pacote**. Recomendado testar primeiro com Firebird 3 de homologação.

Referências: documentação do projeto [Firebird](https://www.firebirdsql.org/), [driver Python oficial](https://firebird-driver.readthedocs.io/) e [Render Web Services](https://render.com/docs/web-services).
