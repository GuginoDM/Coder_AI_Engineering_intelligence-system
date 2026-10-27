import os
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from app.state import TeamState
from app.config import get_llm
from app.rag import get_vectorstore

def _content_to_text(content) -> str:
    """Normaliza .content a string. Gemini 3.5 puede devolver lista de bloques."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    return str(content)

# Esquema Pydantic unificado para la salida estructurada del Supervisor
class RouterSchema(BaseModel):
    next_agent: Literal["Retriever", "Investigador", "Analista", "FINISH"] = Field(
        description="El proximo agente que debe actuar o FINISH si la tarea esta completada."
    )

async def supervisor_node(state: TeamState) -> dict:
    """Nodo Supervisor: Determina la ruta del flujo basandose en el estado actual y un limite de pasos."""
    llm = get_llm()
    messages = state.get("messages", [])
    step_count = state.get("step_count", 0) + 1
    
    # Prevenir bucles infinitos
    if step_count >= 6:
        return {"next_agent": "FINISH", "step_count": step_count}

    # FIX: Si ya tenemos datos del RAG, no volver a llamar al Retriever
    if state.get("rag_data"):
        print(f"[SUPERVISOR] step={step_count} RAG ya consultado -> Determinando siguiente paso")
        if not state.get("research_data"):
            next_agent = "Investigador"
        elif not state.get("analysis_data"):
            next_agent = "Analista"
        else:
            next_agent = "FINISH"
        return {"next_agent": next_agent, "step_count": step_count}

    # FIX: cortar determinísticamente cuando ya hay research + analysis
    if state.get("research_data") and state.get("analysis_data"):
        return {"next_agent": "FINISH", "step_count": step_count}
        
    system_prompt = (
        "Eres el Supervisor de un equipo multi-agente.\n"
        "- Delegar al 'Retriever' si se necesita buscar en la base de conocimiento interna (RAG).\n"
        "- Delegar al 'Investigador' si falta buscar informacion en la web.\n"
        "- Delegar al 'Analista' si ya hay datos de investigacion y se requiere computo/metricas cuantitativas.\n"
        "- Responder 'FINISH' cuando el analisis este completo."
    )
    
    try:
        structured_llm = llm.with_structured_output(RouterSchema)
        response = await structured_llm.ainvoke([SystemMessage(content=system_prompt)] + messages)
        next_agent = response.next_agent
    except Exception:
        # Fallback: primero RAG, luego investigador, luego analista
        if not state.get("rag_data"):
            next_agent = "Retriever"
        elif not state.get("research_data"):
            next_agent = "Investigador"
        elif not state.get("analysis_data"):
            next_agent = "Analista"
        else:
            next_agent = "FINISH"

    # Si el LLM quiso ir al Analista pero no hay investigacion, obligarlo a investigar primero      
    if next_agent == "Analista" and not state.get("research_data"):
        print("[SUPERVISOR] Alerta: Se intento ir a Analista sin datos. Redirigiendo a Investigador.")
        next_agent = "Investigador"

    print(f"[SUPERVISOR] step={step_count} research={bool(state.get('research_data'))} analysis={bool(state.get('analysis_data'))} -> next={next_agent}")
        
    return {"next_agent": next_agent, "step_count": step_count}

async def retriever_node(state: TeamState) -> dict:
    query = state["messages"][0].content if state.get("messages") else ""
    print(f"[RETRIEVER] Buscando en base vectorial: {query}")
    
    try:
        vectorstore = get_vectorstore()
        # Buscamos los 3 documentos mas relevantes
        docs = vectorstore.similarity_search(query, k=3)
        context = "\n\n".join([d.page_content for d in docs])
        if not context:
            context = "No se encontro informacion relevante en la base de conocimiento interna."
    except Exception as e:
        print(f"[RETRIEVER] Error: {e}")
        context = "Error al acceder a la base de conocimiento."
        
    return {
        "rag_data": context,
        "messages": [SystemMessage(content=f"[RAG]: {context}")]
    }

async def research_node(state: TeamState) -> dict:
    llm = get_llm()
    last_user_msg = state["messages"][0].content if state.get("messages") else "Investigar"
    prompt = f"Como Investigador de Mercado, investiga y provee datos clave, cifras y contexto sobre: {last_user_msg}"
    res = await llm.ainvoke([HumanMessage(content=prompt)])
    result_text = _content_to_text(res.content)
    print(f"[INVESTIGADOR] result_len={len(result_text)}")
    return {
        "research_data": result_text,
        "messages": [SystemMessage(content=f"[Investigacion]: {result_text}")]
    }

async def human_approval_node(state: TeamState) -> dict:
    """Nodo HITL: Interrumpe la ejecucion si la tarea es crítica y aún no cuenta con aprobacion."""
    is_critical = state.get("is_critical", False)
    approved = state.get("approved_by_human", False)
    
    if is_critical and not approved:
        # La funcion interrupt() guarda el estado en el checkpointer de Redis y suspende la ejecucion
        approval_decision = interrupt({
            "status": "WAITING_APPROVAL",
            "message": "Esta tarea requiere aprobacion de un operador humano antes de ejecutar el analisis cuantitativo."
        })
        
        # Al reanudar con Command(resume=True) o update_state
        if approval_decision and approval_decision.get("approved"):
            return {"approved_by_human": True}
        else:
            raise Exception("Ejecucion rechazada por el operador humano.")
            
    return {"approved_by_human": True}

async def analyst_node(state: TeamState) -> dict:
    llm = get_llm()
    research_context = state.get("research_data") or "Sin contexto de investigacion previo."
    prompt = (
        f"Basandote en estos datos de investigacion:\n\n"
        f"{research_context[:2000]}\n\n"
        f"Calcula metricas cuantitativas, promedios y conclusiones clave."
    )
    res = await llm.ainvoke([HumanMessage(content=prompt)])
    result_text = _content_to_text(res.content)
    print(f"[ANALISTA] result_len={len(result_text)}")
    return {
        "analysis_data": result_text,
        "messages": [SystemMessage(content=f"[Analisis]: {result_text}")]
    }

def route_decision(state: TeamState) -> str:
    next_agent = state.get("next_agent")
    if next_agent == "Retriever":
        return "Retriever"
    elif next_agent == "Investigador":
        return "Investigador"
    elif next_agent == "Analista":
        return "AprobacionHumana"
    return END

def build_graph(checkpointer=None):
    workflow = StateGraph(TeamState)
    
    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("Retriever", retriever_node)
    workflow.add_node("Investigador", research_node)
    workflow.add_node("AprobacionHumana", human_approval_node)
    workflow.add_node("Analista", analyst_node)
    
    workflow.set_entry_point("Supervisor")
    
    workflow.add_conditional_edges("Supervisor", route_decision, {
        "Retriever": "Retriever",
        "Investigador": "Investigador",
        "AprobacionHumana": "AprobacionHumana",
        END: END
    })
    
    # Retriever vuelve al Supervisor
    workflow.add_edge("Retriever", "Supervisor")
    workflow.add_edge("Investigador", "Supervisor")
    workflow.add_edge("AprobacionHumana", "Analista")
    workflow.add_edge("Analista", "Supervisor")
    
    return workflow.compile(checkpointer=checkpointer)