import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY not found. Please check your .env file.")

client = OpenAI(api_key=api_key)


def ask_llm(prompt: str, model: str = "gpt-5.4-mini") -> str:
    response = client.responses.create(
        model=model,
        input=prompt
    )
    return response.output_text.strip()