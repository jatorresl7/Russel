import os
from datetime import datetime, date
from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean,
    DateTime, Date, JSON, ForeignKey, text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from pgvector.sqlalchemy import Vector

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://jarvis:jarvis123@localhost/jarvis')

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class BaseModel:
    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def __repr__(self):
        fields = ", ".join(f"{c.name}={getattr(self, c.name)!r}" for c in self.__table__.columns)
        return f"<{self.__class__.__name__} {fields}>"


Base = declarative_base(cls=BaseModel)


class Conversation(Base):
    __tablename__ = 'conversations'

    id = Column(Integer, primary_key=True)
    role = Column(String(20), nullable=False)  # user | assistant
    content = Column(Text, nullable=False)
    meta = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)


class Tool(Base):
    __tablename__ = 'tools'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    command = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class GmailSummary(Base):
    __tablename__ = 'gmail_summaries'

    id = Column(Integer, primary_key=True)
    date = Column(Date, unique=True, nullable=False)
    summary = Column(Text, nullable=False)
    email_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class ScriptRun(Base):
    __tablename__ = 'script_runs'

    id = Column(Integer, primary_key=True)
    tool_id = Column(Integer, ForeignKey('tools.id'))
    output = Column(Text)
    status = Column(String(20), default='pending')  # pending | success | error
    created_at = Column(DateTime, default=datetime.utcnow)


class WorkScript(Base):
    __tablename__ = 'work_scripts'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    title = Column(String(100), nullable=False)
    filename = Column(String(200), nullable=False)
    enabled = Column(Boolean, default=True)
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Face(Base):
    """Una cara conocida. `embedding` es el vector de 128 numeros que devuelve
    SFace; se guardan varias filas por persona (una por foto de enrolamiento)
    porque una sola vista no cubre los cambios de luz y de angulo."""
    __tablename__ = 'faces'

    id = Column(Integer, primary_key=True)
    nombre = Column(String(80), nullable=False, index=True)
    embedding = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Dimensiones del embebido de texto. Atadas al modelo: cambiar de modelo
# obliga a recalcular TODOS los vectores, por eso el nombre del modelo se
# guarda en cada fila.
DIMS_MEMORIA = 384


class Pensamiento(Base):
    """Un arranque de razonamiento, escrito a mano y reciclable.

    No es un pensamiento COMPLETO ni la respuesta a nada: es el comienzo del
    bloque `<think>` que se le precarga al modelo cuando la pregunta se parece
    a `disparador`. El modelo lo lee como propio y sigue desde ahi, en vez de
    volver a derivar la misma apertura por enesima vez.

    Por que genericos y no una respuesta cacheada: la respuesta depende de lo
    que la camara ve AHORA y de lo que recuerda AHORA. El razonamiento de como
    encarar "me estan preguntando por mi estado" no depende de nada de eso, y
    por eso si se puede reciclar. Cachear la conclusion daria respuestas
    congeladas; cachear el enfoque no.

    `disparador` es la frase canonica de la que sale el vector. `texto` es lo
    que se precarga. `usos` deja ver cuales trabajan y cuales nunca aciertan.

    `modelo` guarda QUE modelo de embeddings produjo `vector`, y solo eso — sin
    hashes del catalogo pegados. Es lo que permite sembrar de forma incremental:
    una fila cuyo texto no cambio y cuyo modelo sigue siendo el mismo ya tiene
    el vector correcto y no hay que recalcularlo. Antes aca iba
    `modelo#huella_del_catalogo_entero`, asi que tocar UN pensamiento invalidaba
    las 292 filas y las re-vectorizaba todas.
    """
    __tablename__ = 'pensamientos'

    id = Column(Integer, primary_key=True)
    disparador = Column(Text, nullable=False, unique=True, index=True)
    texto = Column(Text, nullable=False)
    vector = Column(Vector(DIMS_MEMORIA))
    modelo = Column(String(80), nullable=False, index=True)
    usos = Column(Integer, default=0)
    ultimo_uso = Column(DateTime)
    vigente = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Memoria(Base):
    """Una cosa que Russ decidio recordar.

    `tipo` separa dos cosas que se escriben distinto y se buscan igual:
      - `hecho`     algo que vale siempre. "Jaime trabaja en Aixa."
      - `episodio`  algo que paso. "El martes le pedi dos veces lo mismo."

    `fuente` dice de donde salio: `explicito` (Russ llamo a la tool `recordar`)
    o `consolidado` (lo saco el trabajo de fondo releyendo `conversations`).
    Importa para poder borrar en masa lo que produjo la consolidacion sin
    tocar lo que Russ eligio guardar a mano.
    """
    __tablename__ = 'memorias'

    id = Column(Integer, primary_key=True)
    tipo = Column(String(20), nullable=False, default='hecho', index=True)
    texto = Column(Text, nullable=False)
    # El vector vive en la misma fila y no en una tabla aparte: acá no hay
    # catálogo que sobreviva al cambio de modelo, la memoria ES el texto.
    vector = Column(Vector(DIMS_MEMORIA))
    modelo = Column(String(80), nullable=False)
    fuente = Column(String(20), nullable=False, default='explicito', index=True)
    # De qué turno salió, cuando salió de uno. Sirve para poder volver a leer
    # el contexto original si una memoria resulta estar mal.
    conversation_id = Column(Integer, ForeignKey('conversations.id'))
    usos = Column(Integer, default=0)
    ultimo_uso = Column(DateTime)
    vigente = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Marcador(Base):
    """Clave/valor para lo poco que hay que recordar entre arranques y no es
    una entidad. Hoy solo lo usa la consolidacion, para saber hasta que turno
    ya leyo: sin esto, un lote que no produce ninguna memoria haria que volviera
    a leer los mismos turnos para siempre.
    """
    __tablename__ = 'marcadores'

    clave = Column(String(60), primary_key=True)
    valor = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    # pgvector tiene que existir ANTES de crear la tabla que usa Vector().
    # Si no está, no se rompe todo: memorias es la única que la necesita.
    try:
        with engine.begin() as con:
            con.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except Exception as e:
        print(f"[jarvis] pgvector no disponible ({type(e).__name__}); "
              f"la memoria no va a poder guardar vectores.")
    Base.metadata.create_all(engine)
    print("Tablas creadas correctamente.")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == '__main__':
    init_db()
