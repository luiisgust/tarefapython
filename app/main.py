
from contextlib import contextmanager
from datetime import datetime
import os
import sqlite3
from typing import Iterator
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field, field_validator


DATABASE_PATH = os.getenv("DATABASE_PATH", "fila.db")
TIMEZONE = ZoneInfo("America/Sao_Paulo")

app = FastAPI(
    title="FlashEntregas - API de Fila",
    description=(
        "API demonstrativa para cadastro, consulta, chamada e remoção de clientes "
        "na fila presencial. Clientes prioritários ficam à frente dos normais; "
        "entre clientes do mesmo tipo, vale a ordem de chegada."
    ),
    version="1.0.0",
)


class NovoCliente(BaseModel):

    model_config = ConfigDict(str_strip_whitespace=True)

    nome: str = Field(min_length=1, max_length=20, description="Nome com até 20 caracteres")
    tipo_atendimento: str = Field(
        min_length=1,
        max_length=1,
        description="N para normal ou P para prioritário",
        examples=["N"],
    )

    @field_validator("nome")
    @classmethod
    def nome_nao_pode_ser_vazio(cls, valor: str) -> str:
        if not valor:
            raise ValueError("O nome é obrigatório e não pode conter apenas espaços.")
        return valor

    @field_validator("tipo_atendimento")
    @classmethod
    def validar_tipo(cls, valor: str) -> str:
        valor = valor.upper()
        if valor not in {"N", "P"}:
            raise ValueError("tipo_atendimento deve ser N (normal) ou P (prioritário).")
        return valor


@contextmanager
def conectar_banco() -> Iterator[sqlite3.Connection]:
    conexao = sqlite3.connect(DATABASE_PATH, timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    try:
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def inicializar_banco() -> None:
    with conectar_banco() as banco:
        banco.execute(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL CHECK(length(nome) BETWEEN 1 AND 20),
                tipo_atendimento TEXT NOT NULL CHECK(tipo_atendimento IN ('N', 'P')),
                data_chegada TEXT NOT NULL,
                atendido INTEGER NOT NULL DEFAULT 0 CHECK(atendido IN (0, 1)),
                posicao INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        banco.execute(
            "CREATE INDEX IF NOT EXISTS idx_clientes_fila "
            "ON clientes(atendido, tipo_atendimento, id)"
        )


def ordenar_espera(banco: sqlite3.Connection) -> list[sqlite3.Row]:
    return banco.execute(
        """
        SELECT id, nome, tipo_atendimento, data_chegada, atendido, posicao
        FROM clientes
        WHERE atendido = 0
        ORDER BY CASE tipo_atendimento WHEN 'P' THEN 0 ELSE 1 END, id
        """
    ).fetchall()


def reindexar_fila(banco: sqlite3.Connection) -> list[sqlite3.Row]:
    clientes = ordenar_espera(banco)
    for posicao, cliente in enumerate(clientes, start=1):
        banco.execute(
            "UPDATE clientes SET posicao = ? WHERE id = ?",
            (posicao, cliente["id"]),
        )
    return ordenar_espera(banco)


def para_resposta(cliente: sqlite3.Row) -> dict[str, object]:
    return {
        "posicao": cliente["posicao"],
        "nome": cliente["nome"],
        "data_chegada": cliente["data_chegada"],
        "tipo_atendimento": cliente["tipo_atendimento"],
        "atendido": bool(cliente["atendido"]),
    }


@app.on_event("startup")
def ao_iniciar() -> None:
    inicializar_banco()


@app.get("/fila", response_model=list[dict[str, object]], summary="Consultar toda a fila")
def consultar_fila() -> list[dict[str, object]]:
    with conectar_banco() as banco:
        clientes = ordenar_espera(banco)
        return [para_resposta(cliente) for cliente in clientes]


@app.get("/fila/{id}", summary="Consultar cliente pela posição")
def consultar_posicao(
    id: int = Path(ge=1, description="Posição atual do cliente na fila"),
) -> dict[str, object]:
    with conectar_banco() as banco:
        cliente = banco.execute(
            """
            SELECT posicao, nome, data_chegada, tipo_atendimento, atendido
            FROM clientes WHERE atendido = 0 AND posicao = ?
            """,
            (id,),
        ).fetchone()
        if cliente is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Não há cliente aguardando na posição {id}.",
            )
        return para_resposta(cliente)


@app.post("/fila", status_code=status.HTTP_201_CREATED, summary="Adicionar cliente à fila")
def adicionar_cliente(novo: NovoCliente) -> dict[str, object]:
    data_chegada = datetime.now(TIMEZONE).isoformat(timespec="seconds")
    with conectar_banco() as banco:
        banco.execute("BEGIN IMMEDIATE")
        cursor = banco.execute(
            """
            INSERT INTO clientes (nome, tipo_atendimento, data_chegada, atendido, posicao)
            VALUES (?, ?, ?, 0, 0)
            """,
            (novo.nome, novo.tipo_atendimento, data_chegada),
        )
        reindexar_fila(banco)
        cliente = banco.execute(
            """
            SELECT posicao, nome, data_chegada, tipo_atendimento, atendido
            FROM clientes WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        return para_resposta(cliente)


@app.put("/fila", summary="Chamar o próximo cliente")
def chamar_proximo() -> dict[str, object]:
    with conectar_banco() as banco:
        banco.execute("BEGIN IMMEDIATE")
        fila = ordenar_espera(banco)
        if not fila:
            return {"mensagem": "A fila está vazia; não há cliente para chamar."}

        primeiro = fila[0]
        banco.execute(
            "UPDATE clientes SET posicao = 0, atendido = 1 WHERE id = ?",
            (primeiro["id"],),
        )
        restante = reindexar_fila(banco)
        atualizado = banco.execute(
            """
            SELECT posicao, nome, data_chegada, tipo_atendimento, atendido
            FROM clientes WHERE id = ?
            """,
            (primeiro["id"],),
        ).fetchone()
        return {
            "mensagem": f"{primeiro['nome']} foi chamado para atendimento.",
            "cliente_atendido": para_resposta(atualizado),
            "proxima_fila": [para_resposta(cliente) for cliente in restante],
        }


@app.delete("/fila/{id}", summary="Remover cliente pela posição")
def remover_cliente(
    id: int = Path(ge=1, description="Posição atual do cliente na fila"),
) -> dict[str, object]:
    with conectar_banco() as banco:
        banco.execute("BEGIN IMMEDIATE")
        cliente = banco.execute(
            "SELECT id, nome FROM clientes WHERE atendido = 0 AND posicao = ?",
            (id,),
        ).fetchone()
        if cliente is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Não há cliente aguardando na posição {id}; nada foi removido.",
            )
        banco.execute("DELETE FROM clientes WHERE id = ?", (cliente["id"],))
        fila = reindexar_fila(banco)
        return {
            "mensagem": f"{cliente['nome']} foi removido da fila.",
            "fila_atualizada": [para_resposta(pessoa) for pessoa in fila],
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
