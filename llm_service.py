import os
from dotenv import load_dotenv
from openai import OpenAI
from anthropic import Anthropic

load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")

if not openai_api_key:
    raise ValueError("OPENAI_API_KEY not found. Please check your .env file.")

openai_client = OpenAI(api_key=openai_api_key)
anthropic_client = Anthropic(api_key=anthropic_api_key) if anthropic_api_key else None


def ask_openai(prompt: str, model: str = "gpt-5.4-mini") -> str:
    response = openai_client.responses.create(
        model=model,
        input=prompt
    )
    return response.output_text.strip()


def ask_claude(
    prompt: str,
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 2200
) -> str:
    if not anthropic_client:
        raise ValueError("ANTHROPIC_API_KEY not found. Please check your .env file.")

    response = anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "user", "content": prompt}
        ],
    )

    parts = []
    for block in response.content:
        if getattr(block, "type", "") == "text":
            parts.append(block.text)

    return "".join(parts).strip()


def ask_llm(
    prompt: str,
    provider: str = "openai",
    model: str | None = None,
    max_tokens: int | None = None,
) -> str:
    provider = (provider or "openai").strip().lower()

    if provider == "claude":
        return ask_claude(
            prompt=prompt,
            model=model or "claude-sonnet-4-6",
            max_tokens=max_tokens or 2200,
        )

    return ask_openai(
        prompt=prompt,
        model=model or "gpt-5.4-mini",
    )