from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional
from functools import lru_cache
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _resolve_default_gguf_path() -> Optional[str]:
    here = Path(__file__).resolve()
    # backend/App/interview_engine.py -> backend/model/*.gguf
    candidate = here.parent.parent / "model"
    if not candidate.exists():
        return None
    matches = sorted(candidate.glob("*.gguf"))
    return str(matches[0]) if matches else None


@lru_cache(maxsize=1)
def _get_llama_cpp():
    try:
        from llama_cpp import Llama
    except Exception as exc:
        raise RuntimeError(
            "Local GGUF model requires `llama-cpp-python`. Install it, then restart the backend."
        ) from exc
    return Llama


@lru_cache(maxsize=1)
def _get_llama_instance():
    Llama = _get_llama_cpp()
    model_path = (
        os.environ.get("LOCAL_LLM_PATH")
        or os.environ.get("LLAMA_CPP_MODEL_PATH")
        or _resolve_default_gguf_path()
        or ""
    ).strip()
    if model_path and not Path(model_path).is_absolute():
        # Allow paths relative to repo root (backend/..)
        repo_root = Path(__file__).resolve().parent.parent.parent
        model_path = str((repo_root / model_path).resolve())
    if not model_path or not Path(model_path).exists():
        raise RuntimeError("Local GGUF model not found. Set LOCAL_LLM_PATH to a .gguf file.")

    n_ctx = int(_env("LLAMA_CPP_N_CTX", "4096"))
    n_threads = int(_env("LLAMA_CPP_THREADS", "8"))
    # GPU layers is optional; 0 means CPU only.
    n_gpu_layers = int(_env("LLAMA_CPP_GPU_LAYERS", "0"))

    # Llama 3 family chat format
    return Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=n_threads,
        n_gpu_layers=n_gpu_layers,
        chat_format=_env("LLAMA_CPP_CHAT_FORMAT", "llama-3"),
        verbose=False,
    )


def _llama_cpp_chat(messages: list[dict[str, str]]) -> str:
    llm = _get_llama_instance()
    result = llm.create_chat_completion(
        messages=messages,
        temperature=float(_env("LLAMA_CPP_TEMPERATURE", "0.4")),
    )
    content = (
        ((result.get("choices") or [{}])[0].get("message") or {}).get("content")
        if isinstance(result, dict)
        else None
    )
    return (content or "").strip()


def _ollama_chat(messages: list[dict[str, str]]) -> str:
    """
    Thin wrapper around Ollama /api/chat.
    Expected env:
      OLLAMA_URL (default http://127.0.0.1:11434/api/chat)
      OLLAMA_MODEL (default qwen2.5:7b-instruct)
    """
    import requests

    payload = {
        "model": _env("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.4},
    }
    url = _env("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
    try:
        res = requests.post(url, json=payload, timeout=120)
        res.raise_for_status()
        data = res.json()
        return (data.get("message") or {}).get("content", "").strip()
    except Exception as exc:
        raise RuntimeError("LLM service unavailable (Ollama).") from exc


def llm_chat(messages: list[dict[str, str]]) -> str:
    """
    Provider order:
      - `LLM_PROVIDER=llama_cpp` -> local GGUF via llama-cpp-python
      - `LLM_PROVIDER=ollama` -> Ollama
      - `LLM_PROVIDER=auto` (default): try Ollama then llama_cpp
    """
    provider = _env("LLM_PROVIDER", "auto").lower()
    if provider == "llama_cpp":
        return _llama_cpp_chat(messages)
    if provider == "ollama":
        return _ollama_chat(messages)

    # auto
    try:
        return _ollama_chat(messages)
    except Exception:
        return _llama_cpp_chat(messages)


def parse_bot_json(text: str):
    """
    Expected schema:
    {
      "ack": "1-2 sentence response",
      "feedback": ["2-4 bullets"],
      "follow_up": "ONE clarifying question OR empty string",
      "next_question": "ONE next question OR empty string",
      "evaluation": {
        "overall_score": 1-10,
        "clarity": 1-10,
        "structure": 1-10,
        "technical_depth": 1-10,
        "communication": 1-10,
        "strengths": ["..."],
        "improvements": ["..."],
        "one_sentence_summary": "..."
      }
    }
    """
    try:
        data = json.loads(text)
        ack = data.get("ack", "")
        feedback = data.get("feedback", [])
        follow_up = data.get("follow_up", "")
        next_q = data.get("next_question", "")
        evaluation = data.get("evaluation", {})

        if isinstance(feedback, str):
            feedback = [feedback]
        if not isinstance(feedback, list):
            feedback = []

        if not isinstance(ack, str):
            ack = ""
        if not isinstance(follow_up, str):
            follow_up = ""
        if not isinstance(next_q, str):
            next_q = ""
        if not isinstance(evaluation, dict):
            evaluation = {}

        # Enforce: only one question total.
        if follow_up.strip() and next_q.strip():
            next_q = ""

        return ack.strip(), feedback, follow_up.strip(), next_q.strip(), evaluation, None
    except Exception:
        return "", [], "", "", {}, text


def build_system_prompt() -> str:
    return (
        "You are an interviewer.\n"
        "You MUST respond in valid JSON only.\n"
        "Schema:\n"
        "{\n"
        '  "ack": "1-2 sentences responding to the user and referencing the current question",\n'
        '  "feedback": ["2-4 short actionable bullets"],\n'
        '  "follow_up": "ONE clarifying question if needed, else empty string",\n'
        '  "next_question": "ONE new interview question only when ready, else empty string",\n'
        '  "evaluation": {\n'
        '    "overall_score": 1,\n'
        '    "clarity": 1,\n'
        '    "structure": 1,\n'
        '    "technical_depth": 1,\n'
        '    "communication": 1,\n'
        '    "strengths": ["..."],\n'
        '    "improvements": ["..."],\n'
        '    "one_sentence_summary": "..." \n'
        "  }\n"
        "}\n"
        "First turn behavior:\n"
        "- On the very first turn ONLY, begin with a short friendly greeting before asking the first question.\n"
        "Hard rules:\n"
        "- You will ALWAYS be given a line 'CURRENT_QUESTION: ...'. Treat it as the ONLY current question.\n"
        "- Your ack/feedback MUST relate to CURRENT_QUESTION.\n"
        "- If the user did not answer CURRENT_QUESTION, ask a follow_up and keep next_question empty.\n"
        "- A direct yes/no (including 'no experience') counts as an answer. Do NOT repeat the same question after a clear yes/no.\n"
        "- Never repeat the same question verbatim. If the candidate answers 'no', move on to a different question (e.g. adjacent skills, learning approach).\n"
        "- Ask only ONE question per turn: follow_up OR next_question.\n"
        "- Scores must be integers from 1 to 10.\n"
        "- If user says 'skip/next/change question/repeat', comply.\n"
        "- Never endorse violence or harm.\n"
    )


@dataclass
class BotTurn:
    ack: str
    feedback: list[str]
    follow_up: str
    next_question: str
    evaluation: dict[str, Any]
    raw: str
    fallback: Optional[str] = None

    @property
    def question(self) -> str:
        return self.follow_up or self.next_question


def start_interview(llm_messages: list[dict[str, str]]) -> BotTurn:
    """
    Initialize the interview and return the first question.
    """
    messages = list(llm_messages)
    if not messages:
        messages = [{"role": "system", "content": build_system_prompt()}]
    raw = llm_chat(messages + [{"role": "user", "content": "Start the interview. Ask the first question."}])
    ack, feedback, follow_up, next_q, evaluation, fallback = parse_bot_json(raw)
    return BotTurn(
        ack=ack,
        feedback=feedback,
        follow_up=follow_up,
        next_question=next_q,
        evaluation=evaluation,
        raw=raw,
        fallback=fallback,
    )


def continue_interview(llm_messages: list[dict[str, str]], current_question: str, user_answer: str) -> BotTurn:
    messages = list(llm_messages)
    if not messages:
        messages = [{"role": "system", "content": build_system_prompt()}]

    user_payload = (
        f"CURRENT_QUESTION: {current_question}\n"
        f"USER_ANSWER: {user_answer}\n\n"
        "Respond using the JSON schema."
    )
    raw = llm_chat(messages + [{"role": "user", "content": user_payload}])
    ack, feedback, follow_up, next_q, evaluation, fallback = parse_bot_json(raw)
    return BotTurn(
        ack=ack,
        feedback=feedback,
        follow_up=follow_up,
        next_question=next_q,
        evaluation=evaluation,
        raw=raw,
        fallback=fallback,
    )
