"""Memory mode selection without importing embedding/vector-store dependencies."""


def create_memory(env, mode="off"):
    """Return no memory in off mode; reserve on for verified local embeddings.

    Deliberately do not import the original memory module, whose import changes
    OPENAI_API_KEY and whose constructor opens an OpenAI embedding/Chroma store.
    """
    if mode == "off":
        return None
    if mode == "on":
        raise NotImplementedError(
            "memory on requires configured local embeddings and a compatible store")
    raise ValueError("Unsupported memory mode: " + str(mode))
