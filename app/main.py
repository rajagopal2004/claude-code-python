import argparse
import os
import json
import subprocess
import contextlib
import io

from openai import OpenAI

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
SKILLS_PARENT_FOLDER = ".claude/skills"
SUB_AGENT_SKILLS = []

def getClient():
    if not API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return client

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

def execSkill(name, args = None):
    skillBody = resolveSkillBody(f"/{name}", args)
    if name in SUB_AGENT_SKILLS:
        mess = [{"role": "user", "content": skillBody}]
        client = getClient()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            execLoop(client, mess)
        return buffer.getvalue()
    else:
        return skillBody

funcs = {
    "Read": execRead,
    "Write": execWrite,
    "Bash": execBash,
    "Skill": execSkill
}

def renderSkills() -> str:
    try:
        skills = "You have access to the following skills: \n"
        for skillFolder in os.listdir(SKILLS_PARENT_FOLDER):
            with open(f"{SKILLS_PARENT_FOLDER}/{skillFolder}/SKILL.md", "r") as f:
                lines = [l.split(":")[1].strip() for l in list(f.read().split("---"))[1].split("\n") if l]
                skillDescription = ":".join(lines[:-1])
                if lines[-1] == "fork":
                    SUB_AGENT_SKILLS.append(lines[0])
                skills += "\n" + skillDescription
        skills += "\n If a skill matches the user's request, call the Skill tool with its name and follow the instructions it returns."
    except:
        skills = ""
    return skills

def resolveSkillBody(skill, sargs) -> str:
    with open(f"{SKILLS_PARENT_FOLDER}{skill}/SKILL.md", "r") as f:
        skillBody = f.read().split("---")[2]
    if sargs:
        skillBody = skillBody.replace("$ARGUMENTS", " ".join(sargs))
        for i, skillArg in list(zip(range(len(sargs)), sargs)):
            skillBody = skillBody.replace(f"${i}", skillArg)
            skillBody = skillBody.replace(f"ARGUMENTS[{i}]", skillArg)
    return skillBody

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
            },
            {
                "type": "function",
                "function": {
                "name": "Skill",
                "description": "Load a skill's instructions into the conversation",
                "parameters": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                    "name": { "type": "string", "description": "The name of the skill to use" },
                    "args": { "type": "string", "description": "Optional arguments for the skill" }
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
        args = list(toolArgs.values())
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
    userInput = str(args.p)

    client = getClient()

    messages = [{"role": "system", "content": renderSkills()}]

    uiw = [w for w in userInput.split(" ") if w]
    esk = []
    sargs = []
    for i, w in list(zip(range(len(uiw)), uiw)):
        if w.startswith("/") and os.path.isdir(f"{SKILLS_PARENT_FOLDER}{w}"):
           esk.append(w)
        else:
           sargs = uiw[i:]
           break
    
    for skillName in esk:
        skillBody = resolveSkillBody(skillName, sargs)
        messages.append({"role": "user", "content": skillBody})

    if len(esk) == 0:
        messages.append({"role": "user", "content": " ".join(uiw)})
        
    execLoop(client, messages)
 

if __name__ == "__main__":
    main()
