import os
import re
import json
from pathlib import Path
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from tools import tools, save_draft
from config import (AGENT_MAX_ITERATIONS, SYSTEM_PROMPT_FILE, CONTENT_RULE_FILE_PATH)
from llm_factory import get_llm
from logger import setup_logger
logger = setup_logger("PublishAI")
# ----------------------------------------------------------------------
# 1. LLM Setup
# ----------------------------------------------------------------------
groq_api_key = os.getenv("GROQ_API_KEY")
llm = get_llm()

# ----------------------------------------------------------------------
# 2. Load system prompt from external file and inject tool descriptions
# ----------------------------------------------------------------------
# PROMPT_FILE = Path(__file__).parent / "system-prompt.md"
PROMPT_FILE = Path(__file__).parent / SYSTEM_PROMPT_FILE
with open(PROMPT_FILE, "r", encoding="utf-8") as f:
    raw_prompt = f.read()

# Only WebSearch and ReadArticle are available to the LLM (SaveDraft is automatic)
llm_tools = [t for t in tools if t.name in ("WebSearch", "ReadArticle")]
tool_descriptions = "\n".join([f"- **{t.name}**: {t.description}" for t in llm_tools])

CONTENT_TYPE_RULES = {}
CONTENT_TYPE_MAP = {
    "LinkedIn Post": "LinkedIn-Post-Rule",
    "Dev.to Article": "Dev-to-Article-Rule",
    "Research Topic": "Research-Summary-Rule",
    "README Draft": "README-Draft-Rule",
}

def load_content_type_rules():
    """Load content type rules from markdown files in the given directory."""
    rules = {}
    dir_path = Path(CONTENT_RULE_FILE_PATH)
    if not dir_path.exists():
        # Fallback to empty dict – no type-specific rules will be injected.
        return rules
    for rule_file in dir_path.glob("*.md"):
        # Key = filename without extension (e.g., "LinkedIn-Post-Rule")
        key = rule_file.stem
        with open(rule_file, "r", encoding="utf-8") as f:
            rules[key] = f.read()
    return rules

# Load rules once at startup
CONTENT_TYPE_RULES = load_content_type_rules()
DEFAULT_CONTENT_TYPE = "LinkedIn Post"



# Insert the dynamic tool list into the prompt
system_prompt = raw_prompt.replace("{{TOOL_DESCRIPTIONS}}", tool_descriptions)

# ----------------------------------------------------------------------
# 3. Global conversation memory (simple list, resets on app restart)
# ----------------------------------------------------------------------
chat_history = []


def extract_text(response) -> str:
    """Normalize LLM response content to a single string."""
    content = response.content
    if isinstance(content, list):
        # Concatenate all text parts (ignore non-text like tool calls)
        text_parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
            elif isinstance(part, str):
                text_parts.append(part)
        return "".join(text_parts)
    return str(content) if content else ""


# ----------------------------------------------------------------------
# 4. Core agent loop
# ----------------------------------------------------------------------
def run_agent(user_input: str, content_type: str = DEFAULT_CONTENT_TYPE):
    """
    Executes the ReAct loop.
    Returns (final_answer_text, full_messages_list) for the UI.
    """
    logger.info("New request: %s with content type: %s", user_input[:100], content_type)
    rule_key = CONTENT_TYPE_MAP.get(content_type, "LinkedIn Post")
    type_rules = CONTENT_TYPE_RULES.get(rule_key, "")
    # Inject the rules into the system prompt
    final_system_prompt = system_prompt.replace("{{CONTENT_TYPE_RULES}}", type_rules)
    logger.info("Final system prompt: %s", final_system_prompt)
    global chat_history
    messages = [SystemMessage(content=final_system_prompt)] + chat_history + [HumanMessage(content=user_input)]
    tools_used = set()
    max_iterations =  AGENT_MAX_ITERATIONS
    final_answer = ""

    for i in range(max_iterations):
        response = llm.invoke(messages)
        messages.append(response)
        answer = extract_text(response)

        # Attempt to find a tool call JSON
        tool_call_match = re.search(r'\{.*"tool"\s*:\s*".*?".*\}', answer, re.DOTALL)
        if tool_call_match:
            try:
                tool_data = json.loads(tool_call_match.group(0))
                tool_name = tool_data["tool"]
                tool_args = tool_data["args"]
                logger.debug("Tool call: %s with args %s", tool_name, tool_args)
            except Exception as e:
                # JSON parse failed – treat as final answer, but only if research is done
                logger.error("Failed to parse tool call JSON: %s", str(e))
                if "WebSearch" not in tools_used:
                    messages.append(HumanMessage(content="You must use WebSearch before giving the final answer. Please search for the topic now."))
                    continue
                else:
                    final_answer = answer
                    logger.warning("Treating LLM output as final answer because WebSearch already used")
                    break

            # Record which tool was called
            tools_used.add(tool_name)
            logger.info("Tool call: %s", tool_name)

            # Execute the tool
            selected_tool = next((t for t in llm_tools if t.name == tool_name), None)
            if selected_tool:
                try:
                    if tool_name == "WebSearch":
                        observation = selected_tool.run(tool_args.get("query", ""))
                    elif tool_name == "ReadArticle":
                        observation = selected_tool.run(tool_args.get("url", ""))
                except Exception as e:
                    logger.error("Agent error ->  Tool: %s Error: %s",tool_name, str(e))
                    observation = f"Tool execution error: {str(e)}"
            else:
                observation = f"Tool '{tool_name}' not found."
                logger.info("Tool: %s not found",tool_name)

            # Feed the result back to the LLM
            messages.append(HumanMessage(content=f"<tool_result>\n{observation}\n</tool_result>"))

        else:
            # No tool call – check if mandatory research has been done
            if "WebSearch" not in tools_used:
                messages.append(HumanMessage(content="You haven't used WebSearch yet. Please search for the user's topic before answering."))
                continue
            # Optional: push to actually read an article if not done after a few turns
            if "ReadArticle" not in tools_used and i > 3:
                messages.append(HumanMessage(content="Please use ReadArticle on at least one URL from the search results to get the full content."))
                continue
            # All good – this is the final answer
            final_answer = answer
            break

    if not final_answer:
        final_answer = "Sorry, I couldn't generate content. Please try again with a more specific topic."

    # ------------------------------------------------------------------
    # 5. Auto‑save the draft and append the file path
    # ------------------------------------------------------------------
    # Save the generated final_answer to a persistent draft file and return
    # the filesystem path where the draft was written.
    #
    # Why we save here (intent & rationale):
    # - Durability: ensure the user's generated content isn't lost if the
    #   application or browser session ends unexpectedly. Saving immediately
    #   after generation minimizes the window of data loss.
    # - Traceability: the saved file provides an audit-friendly record of
    #   what was produced for the given user input and iteration of the
    #   agent loop.
    # - UX: returning the file path to the UI lets callers present a direct
    #   link to the draft so users can open, download or continue editing it.
    #
    # Implementation note: `save_draft` is imported from `tools` and is
    # responsible for handling filename generation, filesystem I/O, and any
    # normalization or error handling. We pass only the final_answer text so
    # the helper can enrich the file with metadata (timestamps, headings,
    # source prompts) if desired.
    heading_match = re.search(r'^#\s+(.+)$', final_answer, re.MULTILINE)
    if heading_match:
        filename_title = heading_match.group(1).strip()
    else:
        # Fallback: use the user input (truncated)
        filename_title = user_input.strip()[:80]

    saved_path = save_draft(content=final_answer, filename=f"{filename_title}")

    final_answer_with_path = f"{final_answer}\n\n---\n📁 {saved_path}"

    # Compose the string returned to callers: include the draft content and
    # append a short separator with the saved file path. This keeps the
    # content human-readable while also providing the exact location of the
    # persisted draft for programmatic use or display in the UI.
    final_answer_with_path = f"{final_answer}\n\n---\n📁 {saved_path}"
    logger.info("Draft saved: %s", saved_path)

    # Update conversation memory
    chat_history.append(HumanMessage(content=user_input))
    chat_history.append(AIMessage(content=final_answer_with_path))

    return final_answer_with_path, messages

# ----------------------------------------------------------------------
# 6. Simple wrapper class for Streamlit
# ----------------------------------------------------------------------
class ContentAgent:
    def __init__(self):
        self.last_messages = []

    def invoke(self, input_dict):
        content_type = input_dict.get("content_type", DEFAULT_CONTENT_TYPE)
        logger.info("Processing input with content type: %s", content_type)
        output, msgs = run_agent(input_dict["input"], content_type=content_type)
        self.last_messages = msgs
        return {"output": output}

agent_executor = ContentAgent()