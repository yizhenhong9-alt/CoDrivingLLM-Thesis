"""Memory mode selection without importing embedding/vector-store dependencies."""


def create_memory(env, mode="off", config=None):
    """Return nothing in off; configured on uses local original read/write flow.

    Deliberately do not import the original memory module, whose import changes
    OPENAI_API_KEY and whose constructor opens an OpenAI embedding/Chroma store.
    """
    if mode == "off":
        return None
    if mode == "on":
        if config is None:
            raise NotImplementedError('memory on requires explicit original local memory config')
        from .original_memory import OriginalMemorySession
        return OriginalMemorySession.from_file(config)
    raise ValueError("Unsupported memory mode: " + str(mode))
