"""Load the optional cloud SDK only when the legacy cloud path is called."""


def OpenAI(*args, **kwargs):
    from openai import OpenAI as Client
    return Client(*args, **kwargs)
