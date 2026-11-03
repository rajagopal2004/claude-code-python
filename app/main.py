import argparse
import os
import sys
import json

from openai import OpenAI

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")

def Read(file_path: str) -> str:
    content = ""
    with open(file_path, "r") as f:
        content = f.read()
    return content

funcs = {
    "Read": Read
}

funcArgs = {
    "Read": ["file_path"]
}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    chat = client.chat.completions.create(
        model="anthropic/claude-haiku-4.5",
        messages=[{"role": "user", "content": args.p}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "Read",
                    "description": "Read and return the contents of a file",
                    "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                        "type": "string",
                        "description": "The path to the file to read"
                        }
                    },
                    "required": ["file_path"]
                    }
                }
            }
        ]
    )

    if not chat.choices or len(chat.choices) == 0:
        raise RuntimeError("no choices in response")

    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!", file=sys.stderr)

    message = chat.choices[0].message
    toolCalls = message.tool_calls if message.tool_calls else []

    for toolCall in toolCalls:
        if toolCall.type == "function":
            functionName = toolCall.function.name
            toolArgs  = json.loads(toolCall.function.arguments)
            reqArgs = funcArgs[functionName]
            args = [toolArgs[arg] for arg in reqArgs]
            result = funcs[functionName](*args)
            print(result)


if __name__ == "__main__":
    main()
