from .factory_llm import get_llm

dummy_llm    = get_llm(temperature=0.2)
agentic_transformer_func_llm = get_llm(temperature=0)