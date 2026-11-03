import os
from gen_ai_hub.proxy.langchain.openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

LLM_DEPLOYMENT_ID = os.getenv("LLM_DEPLOYMENT_ID")

def get_llm(temperature=0):
    return ChatOpenAI(
        deployment_id=LLM_DEPLOYMENT_ID,
        temperature=temperature
    )
