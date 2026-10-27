import os
import json
import asyncio
import traceback
import redis.asyncio as aioredis
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.types import Command
from app.graph import build_graph

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Cola persistente en memoria de la app
job_queue = asyncio.Queue()

# Semaforo para no saturar el LLM (Rate Limit)
_agent_semaphore = asyncio.Semaphore(1)

_setup_lock = asyncio.Lock()
_setup_done = False

async def _ensure_checkpointer_setup(checkpointer):
    global _setup_done
    if _setup_done: return
    async with _setup_lock:
        if _setup_done: return
        try:
            await checkpointer.asetup()
        except Exception as e:
            if "Index already exists" not in str(e): raise
        _setup_done = True

_redis_client = None

async def get_redis_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client

async def set_job_status(job_id, status, result=None, error=None):
    r = await get_redis_client()
    payload = {"status": status}
    if result is not None: payload["result"] = result
    if error is not None: payload["error"] = error
    await r.set(f"job:{job_id}", json.dumps(payload), ex=3600)

async def get_job_status(job_id):
    r = await get_redis_client()
    data = await r.get(f"job:{job_id}")
    if not data: return {"status": "NOT_FOUND"}
    return json.loads(data)

# El proceso que consume la cola
async def process_queue_worker():
    print("[WORKER] Iniciando bucle de la cola...")
    while True:
        job_id, query, is_critical, resume, approved = await job_queue.get()
        await set_job_status(job_id, "RUNNING")
        
        async with _agent_semaphore:
            try:
                async with AsyncRedisSaver.from_conn_string(REDIS_URL) as checkpointer:
                    await _ensure_checkpointer_setup(checkpointer)
                    app_graph = build_graph(checkpointer=checkpointer)
                    config = {"configurable": {"thread_id": job_id}}

                    if resume:
                        input_data = Command(resume={"approved": approved})
                    else:
                        input_data = {
                            "messages": [{"role": "user", "content": query}],
                            "next_agent": "Supervisor",
                            "research_data": None,
                            "analysis_data": None,
                            "rag_data": None,
                            "step_count": 0,
                            "is_critical": is_critical,
                            "approved_by_human": False,
                        }

                    async for _ in app_graph.astream(input_data, config=config, stream_mode="values"):
                        pass

                    snapshot = await app_graph.aget_state(config)
                    if snapshot.tasks and any(t.interrupts for t in snapshot.tasks):
                        await set_job_status(job_id, "WAITING_APPROVAL", result={"message": "Esperando aprobacion."})
                    else:
                        values = snapshot.values or {}
                        await set_job_status(job_id, "DONE", result={
                            "rag": values.get("rag_data"),
                            "research": values.get("research_data"),
                            "analysis": values.get("analysis_data"),
                        })
            except Exception as e:
                tb = traceback.format_exc()
                print(f"[WORKER] FAILED {job_id}: {tb}")
                await set_job_status(job_id, "FAILED", error=f"{type(e).__name__}: {e}")
            finally:
                # se mantiene el sleep(20) para proteger rpm de Gemini
                await asyncio.sleep(20)
                job_queue.task_done()

# Encolar tareas desde la API
async def enqueue_job(job_id, query, is_critical=False, resume=False, approved=False):
    await job_queue.put((job_id, query, is_critical, resume, approved))