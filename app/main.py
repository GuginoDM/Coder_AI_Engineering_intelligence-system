import uuid
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.queue_worker import enqueue_job, get_job_status, set_job_status, process_queue_worker
from app.observability import setup_observability

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        setup_observability()
    except Exception as e:
        print(f"Observabilidad no disponible: {e}")
    # Arrancamos el worker en segundo plano
    worker_task = asyncio.create_task(process_queue_worker())
    yield
    worker_task.cancel()

app = FastAPI(
    title="API REST Intelligence System (RAG + Agentes)",
    description="API Asincrona con RAG, Redis, Observabilidad y HITL.",
    version="2.0.0",
    lifespan=lifespan,
)

class TaskRequest(BaseModel):
    query: str = Field(..., json_schema_extra={"example": "¿Que dice la documentacion interna sobre LangGraph?"})
    critical: Optional[bool] = Field(default=False)

class TaskResponse(BaseModel):
    job_id: str
    status: str
    message: str

class ApprovalRequest(BaseModel):
    approved: bool
    reason: Optional[str] = None

@app.post("/tasks", response_model=TaskResponse, status_code=202)
async def create_task(request: TaskRequest):
    job_id = str(uuid.uuid4())
    
    # Detectar heurística de tarea crítica si contiene palabras sensibles
    is_critical = request.critical or any(w in request.query.lower() for w in ["publicar", "borrar", "eliminar"])
    
    await set_job_status(job_id, "PENDING")
    
    # Encolar ejecución asíncrona no bloqueante
    await enqueue_job(job_id, request.query, is_critical, False)
    
    return TaskResponse(
        job_id=job_id,
        status="PENDING",
        message="Tarea encolada correctamente."
    )

@app.get("/tasks/{job_id}")
async def get_task_status(job_id: str):
    job_data = await get_job_status(job_id)
    if job_data.get("status") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="El trabajo especificado no existe.")
    return job_data

@app.post("/tasks/{job_id}/approve", response_model=TaskResponse)
async def approve_task(job_id: str, request: ApprovalRequest):
    job_data = await get_job_status(job_id)
    if job_data.get("status") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Trabajo no encontrado.")
        
    if job_data.get("status") != "WAITING_APPROVAL":
        raise HTTPException(status_code=400, detail=f"El trabajo no esta esperando aprobacion.")
        
    if not request.approved:
        await set_job_status(job_id, "REJECTED", error="Rechazado por el operador humano.")
        return TaskResponse(job_id=job_id, status="REJECTED", message="Tarea rechazada.")

    # Reencolamos para reanudar
    await enqueue_job(job_id, "", False, True, True)
    
    return TaskResponse(
        job_id=job_id,
        status="RUNNING",
        message="Reanudando ejecucion."
    )