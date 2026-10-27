import asyncio
import time
import httpx
import numpy as np

BASE_URL = "http://127.0.0.1:8000"
MAX_WAIT = 240

QUERIES = [
    "Investigar la adopción de LangGraph en empresas FinTech y calcular métricas de ROI.",
    "Analizar el impacto de la automatización multi-agente en la reducción de costos operativos.",
    "Evaluar herramientas de orquestación de LLMs en el mercado actual y comparar eficiencias.",
    "Calcular métricas proyectadas de rendimiento al migrar arquitecturas a FastAPI y Redis.",
    "Investigar casos de uso de Human-in-the-loop en agentes autónomos de salud.",
]


async def run_one(client, idx, query):
    t0 = time.time()
    try:
        r = await client.post(f"{BASE_URL}/tasks",
                              json={"query": query, "critical": False}, timeout=60.0)
        r.raise_for_status()
        jid = r.json()["job_id"]
        print(f"[{idx}] POST -> 202 ({time.time()-t0:.2f}s) | {jid}")

        while time.time() - t0 < MAX_WAIT:
            await asyncio.sleep(2.0)
            s = await client.get(f"{BASE_URL}/tasks/{jid}", timeout=30.0)
            status = s.json().get("status")
            if status == "DONE":
                dt = time.time() - t0
                print(f"[{idx}] DONE en {dt:.2f}s")
                return dt
            if status in ("FAILED", "REJECTED"):
                print(f"[{idx}] {status}: {s.json().get('error', '')[:120]}")
                return None
        print(f"[{idx}] timeout")
        return None
    except Exception as e:
        print(f"[{idx}] error: {type(e).__name__}: {e}")
        return None


async def main():
    print("=" * 60)
    print("PRUEBA DE CARGA: 5 peticiones concurrentes REALES")
    print("=" * 60)

    t_start = time.time()
    async with httpx.AsyncClient(timeout=400.0, trust_env=False) as client:
        tasks = [asyncio.create_task(run_one(client, i + 1, q))
                 for i, q in enumerate(QUERIES)]
        latencies = await asyncio.gather(*tasks)

    total = time.time() - t_start
    valid = [l for l in latencies if l is not None]

    print("=" * 60)
    print(f"Exitosas: {len(valid)}/{len(QUERIES)}")
    print(f"Tiempo total desde primer POST: {total:.2f}s")
    if valid:
        print(f"p50: {np.percentile(valid, 50):.2f}s")
        print(f"p95: {np.percentile(valid, 95):.2f}s")
        print(f"min: {min(valid):.2f}s | max: {max(valid):.2f}s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())