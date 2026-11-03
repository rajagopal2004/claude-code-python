import argparse
import os
import sys
import json
import subprocess

from openai import OpenAI

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
SKILLS_PARENT_FOLDER = "ccSkill/skills"

def execRead(file_path: str) -> str:
    content = ""
    with open(file_path, "r") as f:
        content = f.read()
    return content

def execWrite(file_path: str, content: str) -> None:
    with open(file_path, "w") as f:
        f.write(content)

def execBash(command: str) -> str:
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return f"returncode: {result.returncode}, stderr: {result.stderr}, stdout: {result.stdout}"
    
funcs = {
    "Read": execRead,
    "Write": execWrite,
    "Bash": execBash
}

funcArgs = {
    "Read": ["file_path"],
    "Write": ["file_path", "content"],
    "Bash": ["command"]
}

def renderSkills() -> str:
    skills = "You have access to the following skills: \n"
    for skillFolder in os.listdir(SKILLS_PARENT_FOLDER):
        with open(f"{SKILLS_PARENT_FOLDER}/{skillFolder}/SKILL.md", "r") as f:
            lines = [l.split(":")[1].strip() for l in list(f.read().split("---"))[1].split("\n") if l]
            skillDescription = ":".join(lines)
            skills += "\n" + skillDescription
    return skills

def callLLM(client, messages): 
    return client.chat.completions.create(
        model="anthropic/claude-haiku-4.5",
        messages=messages,
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
            },
            {
                "type": "function",
                "function": {
                    "name": "Write",
                    "description": "Write content to a file",
                    "parameters": {
                    "type": "object",
                    "required": ["file_path", "content"],
                    "properties": {
                        "file_path": {
                        "type": "string",
                        "description": "The path of the file to write to"
                        },
                        "content": {
                        "type": "string",
                        "description": "The content to write to the file"
                        }
                    }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "Bash",
                    "description": "Execute a shell command",
                    "parameters": {
                    "type": "object",
                    "required": ["command"],
                    "properties": {
                        "command": {
                        "type": "string",
                        "description": "The command to execute"
                        }
                    }
                    }
                }
            }
        ]
    )

def execToolCall(toolCall):
    result = None
    if toolCall.type == "function": 
        functionName = toolCall.function.name
        toolArgs  = json.loads(toolCall.function.arguments)
        reqArgs = funcArgs[functionName]
        args = [toolArgs[arg] for arg in reqArgs]
        result = funcs[functionName](*args)
    return result

def execLoop(client, messages):
    chat = callLLM(client, messages)

    if not chat.choices or len(chat.choices) == 0:
        raise RuntimeError("no choices in response")
    
    messages.append(chat.choices[0].message)
    
    toolCalls = chat.choices[0].message.tool_calls
    if toolCalls is None:
        if chat.choices[0].message.content is not None:
            print(chat.choices[0].message.content)
        return 
        
    for toolCall in toolCalls:
        result = execToolCall(toolCall)
        toolCallEntry = {
            "role": "tool",
            "tool_call_id": toolCall.id,
            "content": str(result)
        }
        messages.append(toolCallEntry)

    return execLoop(client, messages)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    messages = [
        {"role": "system", "content": renderSkills()},
        {"role": "user", "content": args.p}
    ]
    execLoop(client, messages)

    

if __name__ == "__main__":
    main()
