from app.rag import ingest_documents

# Simulamos que extrajimos esto de los PDFs internos de la empresa
documentos_internos = [
    "El manual técnico indica que LangGraph se utiliza para orquestar agentes autónomos y mantener el estado con Redis.",
    "La política de FinTech de la empresa requiere que cualquier análisis crítico sea aprobado por un operador humano antes de ejecutarse.",
    "Nuestro stack tecnológico principal incluye FastAPI para las APIs, Redis para caché y persistencia de grafos, y Arize Phoenix para trazabilidad.",
    "Las métricas internas demuestran que la automatización con IA ha mejorado la eficiencia operativa en un 35% durante el último año."
]

if __name__ == "__main__":
    print("Cargando documentos a la base vectorial (ChromaDB)...")
    ingest_documents(documentos_internos)
    print("¡Listo! Documentos indexados en la base de conocimiento.")