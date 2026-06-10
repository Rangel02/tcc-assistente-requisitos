# Assistente Virtual para Apoio à Engenharia de Requisitos

Este repositório contém o protótipo desenvolvido para o Trabalho de Conclusão de Curso em Ciência da Computação na PUC Minas.

O projeto consiste em um assistente virtual para apoiar a fase inicial da Engenharia de Requisitos. A ideia principal é ajudar Product Owners, analistas e equipes de desenvolvimento a conduzirem entrevistas iniciais com stakeholders de forma mais organizada, registrando as informações coletadas e gerando automaticamente uma ATA em Markdown e PDF.

## Sobre o projeto

Em muitos projetos de software, as primeiras conversas com stakeholders acontecem de forma informal. Muitas vezes, as informações ficam espalhadas em anotações pessoais, mensagens, e-mails ou documentos pouco padronizados.

Isso pode dificultar a recuperação do que foi discutido, gerar perda de contexto e prejudicar etapas posteriores, como a escrita de histórias de usuário, o refinamento de requisitos e a priorização de demandas.

Este protótipo busca apoiar esse momento inicial por meio de uma entrevista estruturada. O sistema conduz o usuário por uma árvore de perguntas, registra as respostas fornecidas e, ao final, gera uma ATA com o conteúdo da conversa.

A proposta não é substituir o trabalho do Product Owner, mas oferecer um apoio para organizar melhor a entrevista, reduzir esquecimentos e centralizar as informações levantadas em um documento reutilizável.

## Funcionalidades

* Entrevista estruturada baseada em uma árvore de perguntas.
* Registro de perguntas e respostas por sessão.
* Persistência das informações em banco SQLite.
* Interface em formato de chat com Streamlit.
* API REST desenvolvida com FastAPI.
* Geração automática de ATA em Markdown.
* Geração automática de ATA em PDF.
* Scripts PowerShell para facilitar a execução do backend e do frontend.

## Tecnologias utilizadas

* Python
* FastAPI
* Streamlit
* SQLite
* SQLModel
* ReportLab
* Uvicorn
* PowerShell

## Arquitetura geral

O sistema foi dividido em duas partes principais: frontend e backend.

Frontend Streamlit  →  API FastAPI  →  SQLite

O frontend é responsável por exibir a entrevista em formato de chat, receber as respostas do usuário e apresentar a ATA gerada.

O backend controla o fluxo da entrevista, consulta a árvore de perguntas, salva as respostas, persiste os dados e gera os arquivos em Markdown e PDF.

## Estrutura do repositório

```text
tcc-assistente-requisitos/
│
├── backend/
│   └── app/
│       ├── db.py
│       ├── main.py
│       ├── models.py
│       ├── questions.json
│       └── repository.py
│
├── frontend/
│   └── streamlit_app.py
│
├── scripts/
│   ├── run_backend.ps1
│   └── run_frontend.ps1
│
├── requirements.txt
├── .gitignore
└── README.md
```

## Principais arquivos

### `backend/app/main.py`

Arquivo principal da API. Nele estão os endpoints do sistema, o controle do fluxo da entrevista, a geração da ATA em Markdown e a geração do PDF.

### `backend/app/questions.json`

Arquivo responsável por armazenar a árvore de perguntas usada na entrevista. Cada pergunta possui um identificador, o texto exibido ao usuário e a indicação do próximo passo do fluxo.

### `backend/app/models.py`

Define o modelo de dados usado para representar uma sessão de entrevista no banco.

### `backend/app/repository.py`

Contém as funções responsáveis por salvar, atualizar e recuperar sessões no banco de dados.

### `backend/app/db.py`

Configura a conexão com o banco SQLite e cria as tabelas necessárias.

### `frontend/streamlit_app.py`

Arquivo da interface web do protótipo. Exibe a entrevista em formato de chat, permite gerar a ATA e disponibiliza os arquivos Markdown e PDF para download.

### `scripts/run_backend.ps1`

Script PowerShell criado para facilitar a execução do backend. Ele prepara o ambiente virtual, instala as dependências e inicia a API FastAPI.

### `scripts/run_frontend.ps1`

Script PowerShell criado para facilitar a execução do frontend. Ele prepara o ambiente virtual, instala as dependências e inicia a interface Streamlit apontando para o backend local.

## Como executar o projeto

### Pré-requisitos

Antes de executar o projeto, é necessário ter instalado:

* Python 3.10 ou superior
* PowerShell
* Git

## Execução usando scripts

O projeto possui scripts PowerShell para simplificar a execução local.

### 1. Clonar o repositório

git clone https://github.com/Rangel02/tcc-assistente-requisitos.git
cd tcc-assistente-requisitos


### 2. Iniciar o backend

Em um terminal PowerShell, execute:

.\scripts\run_backend.ps1

O backend será iniciado em:

http://127.0.0.1:8010

A documentação automática da API pode ser acessada em:

http://127.0.0.1:8010/docs

### 3. Iniciar o frontend

Em outro terminal PowerShell, execute:

.\scripts\run_frontend.ps1

A interface Streamlit será aberta no navegador.

## Execução manual

Também é possível executar o projeto manualmente.

### 1. Criar ambiente virtual

python -m venv .venv

### 2. Ativar ambiente virtual no Windows

.\.venv\Scripts\Activate.ps1

### 3. Instalar dependências

pip install -r requirements.txt

### 4. Iniciar backend

python -m uvicorn backend.app.main:app --reload --port 8010

### 5. Iniciar frontend

Em outro terminal:

set BACKEND_URL=http://127.0.0.1:8010
python -m streamlit run frontend/streamlit_app.py

## Endpoints principais da API

| Método | Endpoint                     | Descrição                          |
| ------ | ---------------------------- | ---------------------------------- |
| GET    | `/health`                    | Verifica se a API está respondendo |
| POST   | `/interview/next`            | Avança o fluxo da entrevista       |
| POST   | `/briefing`                  | Gera a ATA em Markdown             |
| GET    | `/briefing/pdf/{session_id}` | Gera e retorna a ATA em PDF        |
| POST   | `/reset`                     | Reinicia a sessão em memória       |

## Fluxo de funcionamento

1. O usuário acessa a interface em Streamlit.
2. O sistema inicia uma nova sessão de entrevista.
3. O backend carrega a árvore de perguntas definida em `questions.json`.
4. A cada resposta enviada, o backend registra a pergunta e a resposta correspondente.
5. O sistema avança para a próxima pergunta do fluxo.
6. Ao final da entrevista, o usuário pode gerar uma ATA.
7. A ATA fica disponível em Markdown e PDF.

## Geração da ATA

A ATA gerada pelo sistema contém:

* Identificação da sessão.
* Informações gerais da entrevista.
* Perguntas e respostas registradas.
* Observações finais.

O arquivo Markdown pode ser editado e reaproveitado em ferramentas de documentação, wikis ou repositórios. O PDF pode ser usado para consulta, compartilhamento e arquivamento.

## Limitações do protótipo

Este projeto foi desenvolvido como uma prova de conceito acadêmica. Algumas limitações atuais são:

* O fluxo de perguntas é definido previamente no arquivo `questions.json`.
* O sistema não realiza análise semântica automática das respostas.
* O sistema não identifica automaticamente ambiguidades, conflitos ou prioridades.
* A interpretação das respostas ainda depende do Product Owner ou da equipe responsável pelo refinamento.
* O SQLite foi escolhido pela simplicidade e por ser suficiente para o contexto do protótipo.

## Possíveis trabalhos futuros

* Tornar o fluxo de perguntas mais dinâmico e adaptável.
* Ampliar a avaliação com equipes reais de desenvolvimento.
* Exportar entrevistas em formatos estruturados, como CSV.
* Integrar modelos de linguagem para apoiar a identificação de requisitos, riscos e ambiguidades.
* Adicionar autenticação e controle de usuários.
* Evoluir o armazenamento para um banco relacional mais robusto em ambiente de produção.

## Autor

Eduardo Rangel Becattini
Curso de Ciência da Computação
PUC Minas

## Contexto acadêmico

Protótipo desenvolvido para o Trabalho de Conclusão de Curso intitulado:

**Assistente Virtual para Apoio à Engenharia de Requisitos**
