# Firebird Designer Online

Editor de banco de dados **Firebird 3.0** para navegador. Crie o modelo, as tabelas, os campos e os registros **sem conectar a um Firebird existente**. O projeto fica salvo no armazenamento local do navegador. Quando estiver hospedado como **Web Service Docker**, o botão de exportação gera um arquivo **`.fdb` verdadeiro**, com o Firebird Embedded 3.0, e entrega o arquivo como download.

## Recursos

- Criar um banco vazio ou começar com um exemplo `COMERCIAL` (CLIENTES, PRODUTOS, VENDAS)
- Criar, renomear, duplicar e excluir tabelas
- Criar e editar campos, tipo, tamanho, `NOT NULL`, `PRIMARY KEY`, `IDENTITY`, valores `DEFAULT`
- Adicionar/editar/excluir registros; importar/exportar CSV da tabela aberta
- Definir índices e relações `FOREIGN KEY` com ON DELETE
- Diagrama ER simplificado
- Editor/visualizador do script SQL de todo o projeto
- Console de consultas locais simples: `SELECT`, `COUNT`, `WHERE CAMPO = VALOR`, `ORDER BY`
- Desfazer/refazer; tema claro e escuro
- Exportar banco real `.FDB` (requer backend), script `.SQL` e projeto `.JSON`
- Importar projeto `.JSON`, CSV de uma tabela e comandos simples `CREATE TABLE` em `.SQL`

## Publicar gratuitamente no Render

1. Extraia o arquivo ZIP. No GitHub, envie os **arquivos e pastas extraídos**, com `Dockerfile`, `server.py`, `index.html` e a pasta `static` na raiz do repositório.
2. No Render, clique em **New → Web Service** (NÃO `Static Site`). Conecte seu repositório do GitHub.
3. Selecione **Docker** como linguagem/runtime. O Render detectará o `Dockerfile` na raiz.
4. Se solicitado, deixe `Root Directory` vazio. O Render constrói a imagem automaticamente; **não precisa preencher Build Command nem Start Command**.
5. Conclua `Create Web Service` / `Deploy`.
6. Acesse `https://seu-projeto.onrender.com` e comece a editar.

**Não são necessárias** `APP_ADMIN_PASSWORD`, `APP_SECRET_KEY`, `FIREBIRD_HOST`, `FIREBIRD_DATABASE`, `FIREBIRD_USER` ou `FIREBIRD_PASSWORD`. Essas variáveis eram do projeto antigo de conexão; o novo é independente.

### Como funciona o arquivo .FDB?

O servidor usa `isql-fb` do **Firebird 3.0 Embedded** (pacotes instalados no Docker) para criar uma base nova em pasta temporária. O servidor recebe **somente a estrutura e registros do projeto**, monta SQL a partir de uma lista restrita de tipos e identificadores, executa o mecanismo real e devolve os bytes do `.fdb`. A pasta temporária é destruída automaticamente. Não executa SQL arbitrário enviado pelo cliente. A porta TCP do Firebird **não é exposta**.

O arquivo .FDB não guarda uma senha própria; a autenticação depende do servidor Firebird que vier a abri-lo. Abra o arquivo no IBExpert, FlameRobin ou Lazarus com usuário/senha do **seu servidor Firebird 3.0**. O backend não fica conectado ao Firebird do Windows.

**Compatibilidade**: O Docker foi configurado com Firebird Embedded 3.0 para produzir formato ODS 12 compatível com Firebird 3. O gerador foi testado localmente com Firebird Embedded 4.0 (mesmo SQL principal); teste a geração no ambiente Docker antes de uso em produção.

## Executar no computador

O editor visual pode ser aberto com duplo clique em `index.html`. Neste modo local, as operações de projeto JSON, SQL, CSV e edição funcionam, mas **não será possível gerar FDB**, pois exige o mecanismo Firebird no servidor.

Para rodar o backend com Docker:

```bash
docker build -t firebird-designer-online .
docker run --rm -p 10000:10000 firebird-designer-online
```

Depois, abra `http://localhost:10000`.

Para desenvolvimento, se o Firebird Embedded e `isql-fb` já estiverem instalados no Linux:

```bash
python server.py
```

## Limitações

- Não é uma conexão SQL remota com o Firebird já instalado, e não substitui ferramentas de administração (usuários, permissões, backup/restore, procedures, triggers).
- Importação SQL é **parcial** (CREATE TABLE simples; não restaura triggers/procedures ou todo tipo de SQL).
- Não importa diretamente um `.fdb` binário existente.
- Diagrama ER é simplificado; a edição visual é feita por tabelas, índices e relacionamentos.
- O console local aceita consultas SELECT simples, não executa o motor SQL Firebird.
- O projeto salvo no navegador não fica sincronizado entre dispositivos. **Exporte JSON como backup.**
- Arquivos `.fdb` são gerados no servidor para download e **não ficam hospedados como bancos persistentes** no Render.
- Limites do gerador: até 70 tabelas, 120 campos/tabela, 5.000 registros por projeto, 2 MB de entrada JSON, 30 MB de arquivo FDB, 8 gerações por minuto por IP.

## Segurança

- Não use dados pessoais sensíveis num site público sem autenticação e privacidade adequadas. Embora o gerador descarte os arquivos após cada solicitação, os registros enviados para gerar FDB passam pelo servidor.
- Identificadores são validados e SQL executável não é aceito como entrada arbitrária pelo backend.
- Para projetos privados ou hospedagem pública de larga escala, adicionar login/autorização, limitação de uso distribuída e controles de acesso é recomendado.

## Estrutura

```
index.html             Interface
static/style.css       Temas e layout
static/app.js          Editor visual + armazenamento local
server.py              API de geração do .FDB
Dockerfile             Firebird Embedded 3.0 para Render
render.yaml            Configuração opcional de serviço
```
