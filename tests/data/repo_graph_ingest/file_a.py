def resolve_backend(config):
    return config.get("backend", "qdrant")
