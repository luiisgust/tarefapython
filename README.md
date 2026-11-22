# API de Fila de Atendimento

API REST desenvolvida com FastAPI para cadastrar e gerenciar clientes em uma fila de atendimento presencial. Os dados são armazenados em um banco SQLite criado automaticamente.

A fila atende primeiro os clientes prioritários (`P`). Entre clientes do mesmo tipo, é respeitada a ordem de chegada.

## Requisitos

- Python 3.10 ou superior
- pip

## Instalação e inicialização no Windows

Abra o PowerShell e acesse a pasta descompactada do projeto:

```powershell
cd caminho\para\flashentregas-api
```

Crie um ambiente virtual:

```powershell
py -m venv .venv
```

Instale as dependências:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Inicie o servidor:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Quando o terminal indicar que o servidor está rodando, a API estará disponível em:

- API: `http://127.0.0.1:8000`
- Documentação interativa: `http://127.0.0.1:8000/docs`
- Documentação alternativa: `http://127.0.0.1:8000/redoc`

Para desligar o servidor, volte ao terminal e pressione `Ctrl+C`.

## Endpoints

| Método | Caminho | Descrição |
| --- | --- | --- |
| `GET` | `/fila` | Lista as pessoas que aguardam atendimento. Se a fila estiver vazia, retorna `[]` com status `200`. |
| `GET` | `/fila/{id}` | Consulta a pessoa que ocupa a posição indicada. |
| `POST` | `/fila` | Cadastra uma pessoa na fila. |
| `PUT` | `/fila` | Chama a primeira pessoa e atualiza as posições restantes. |
| `DELETE` | `/fila/{id}` | Remove a pessoa que ocupa a posição indicada. |

Neste projeto, `{id}` representa a posição atual da pessoa na fila. Como as posições mudam quando alguém é atendido ou removido, esse número pode mudar ao longo do tempo.

## Cadastrar uma pessoa

Envie uma requisição `POST` para `/fila` com um nome e o tipo de atendimento:

```json
{
  "nome": "Ana Silva",
  "tipo_atendimento": "N"
}
```

Use `"N"` para atendimento normal ou `"P"` para prioritário. O nome é obrigatório e pode ter até 20 caracteres.

A API registra automaticamente a data e hora de chegada no fuso horário de São Paulo. O cliente cadastrado recebe uma posição e começa com `atendido` igual a `false`.

Exemplo de cadastro prioritário:

```json
{
  "nome": "Carlos Souza",
  "tipo_atendimento": "P"
}
```

Clientes prioritários ficam à frente dos clientes normais que ainda aguardam. Entre clientes prioritários, a ordem de chegada é mantida.

## Exemplo de resposta

```json
{
  "posicao": 1,
  "nome": "Ana Silva",
  "data_chegada": "2026-11-22T10:30:00-03:00",
  "tipo_atendimento": "N",
  "atendido": false
}
```

A data acima é apenas um exemplo. A API usa a data e hora do momento do cadastro.

## Consultar e atualizar a fila

- `GET /fila` mostra todas as pessoas que ainda aguardam.
- `GET /fila/1` consulta quem está na posição 1.
- `PUT /fila` marca como atendida a pessoa da posição 1, atribui a ela a posição 0 e recalcula as posições de quem permanece na fila.
- `DELETE /fila/2` remove quem ocupa a posição 2 e recalcula as posições seguintes.

Uma consulta ou remoção de uma posição inexistente retorna status `404` com uma mensagem explicativa. Dados inválidos no cadastro, como nome vazio, nome com mais de 20 caracteres ou tipo diferente de `N` e `P`, retornam status `422`.

## Banco de dados

Na primeira inicialização, a API cria o arquivo `fila.db` na pasta de onde o servidor foi iniciado. Esse arquivo contém os cadastros e permanece após o servidor ser desligado.

Para escolher outro caminho para o banco no PowerShell, defina a variável `DATABASE_PATH` antes de iniciar o servidor:

```powershell
$env:DATABASE_PATH = "C:\dados\flashentregas.db"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## Executar em outros sistemas

Depois de criar e ativar um ambiente virtual, instale as dependências e inicie o servidor:

```bash
python -m venv .venv
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

No Windows, o comando para ativar o ambiente virtual depende do terminal usado. A instalação e inicialização também podem ser feitas diretamente com `.\.venv\Scripts\python.exe`, como mostrado acima.

## Hospedagem

O projeto inclui um `Procfile` para plataformas de hospedagem que usam esse formato. A API usa a variável de ambiente `PORT` quando ela está definida.

O SQLite é adequado para execução local e demonstrações. Em serviços de hospedagem com armazenamento temporário, o banco pode ser apagado quando a aplicação reinicia. Para manter os dados em uma implantação permanente, use um banco de dados gerenciado.