import os
import sys
from openai import OpenAI
from tools import TOOLS, call_tool

MODEL = os.getenv("MODEL", "grok-4-1-fast-reasoning")
BASE_URL = os.getenv("BASE_URL", "https://api.x.ai/v1")
API_KEY = os.getenv("XAI_API_KEY", os.getenv("OPENAI_API_KEY", "sk-placeholder"))

SYSTEM_PROMPT = "You are a helpful assistant. Use the available tools when they would help answer the user's question."


def chat(client: OpenAI, messages: list[dict]) -> str:
    """Send messages, handle any tool calls, and return the final assistant text."""
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        choice = response.choices[0]
        message = choice.message
        messages.append(message)  # append raw message object; SDK accepts it

        if choice.finish_reason != "tool_calls":
            return message.content or ""

        # handle every tool call in this turn
        for tc in message.tool_calls:
            print(f"  [tool] {tc.function.name}({tc.function.arguments})")
            result = call_tool(tc.function.name, tc.function.arguments)
            print(f"  [result] {result}")
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })


def main():
    client_kwargs = {"api_key": API_KEY}
    if BASE_URL:
        client_kwargs["base_url"] = BASE_URL

    client = OpenAI(**client_kwargs)
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"Chatbot ready (model={MODEL}). Type 'exit' or Ctrl-C to quit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            print("Bye.")
            sys.exit(0)

        messages.append({"role": "user", "content": user_input})
        reply = chat(client, messages)
        print(f"Assistant: {reply}\n")


if __name__ == "__main__":
    main()
