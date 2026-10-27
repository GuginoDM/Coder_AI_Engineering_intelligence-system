import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI 
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration

load_dotenv()

class MockLLM(BaseChatModel):
    """LLM de prueba (Mock) que simula respuestas cuando no hay créditos o claves válidas."""
    

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs) -> ChatResult:
        last_message = messages[-1].content if messages else ""
        
        if "investiga" in last_message.lower() or "mercado" in last_message.lower():
            text = "Análisis de mercado simulado: Crecimiento constante en adopción de orquestadores jerárquicos (2026)."
        elif "analiza" in last_message.lower() or "métricas" in last_message.lower():
            text = "Métricas calculadas: Eficiencia incrementada en +42.5% con margen de error del <2%."
        else:
            text = "Respuesta simulada correctamente por el modo Mock."
            
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    @property
    def _llm_type(self) -> str:
        return "mock"


def get_llm(temperature: float = 0.0):
    """
    Retorna el ChatModel según LLM_PROVIDER.
    Orden de prioridad en modo auto (provider vacío o desconocido):
    Gemini > Groq > OpenAI > MockLLM
    """
    provider = os.getenv("LLM_PROVIDER", "").lower()

    google_key = os.getenv("GOOGLE_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    def _has_key(k, placeholder):
        return bool(k) and k != placeholder

    if provider == "mock":
        print("[config] Mock forzado.")
        return MockLLM()

    # --- Gemini ---
    if provider == "gemini" or (provider == "" and _has_key(google_key, "tu_gemini_api_key")):
        try:
            return ChatGoogleGenerativeAI(
                model="gemini-3.5-flash-lite",
                temperature=temperature,
                google_api_key=google_key,
                max_retries=1,
            )
        except Exception as e:
            print(f"[config] Gemini falló: {e}. Probando siguiente...")

    # --- Groq ---
    if provider == "groq" or (provider == "" and _has_key(groq_key, "tu_groq_api_key")):
        try:
            return ChatGroq(
                model_name="openai/gpt-oss-20b",
                temperature=temperature,
                groq_api_key=groq_key,
                max_retries=1,
            )
        except Exception as e:
            print(f"[config] Groq falló: {e}. Probando siguiente...")

    # --- OpenAI ---
    if provider == "openai" or (provider == "" and _has_key(openai_key, "tu_openai_api_key")):
        try:
            return ChatOpenAI(
                model="gpt-4o-mini",
                temperature=temperature,
                api_key=openai_key,
                max_retries=1,
            )
        except Exception as e:
            print(f"[config] OpenAI falló: {e}. Cayendo a Mock...")

    # --- Fallback ---
    print("[config] Sin proveedores válidos → MockLLM")
    return MockLLM()