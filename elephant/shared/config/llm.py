"""
ELEPHANT 2.0 — LLM Model Registry
Dual-Core Architecture:
  Cloud Core (Vertex AI) → Planner, Creator, Critic
  Local Core (Ollama)    → Gatekeeper, Shadow, Executor [DO NOT TOUCH]
"""
from __future__ import annotations
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

# ── CLOUD CORE MODELS (Vertex AI) ─────────────────────────────────────────────
PLANNER_MODEL    = "claude-3-5-sonnet@20240620"   # claude-sonnet-4.6 on Vertex
CREATOR_MODEL    = "claude-3-5-sonnet@20240620"   # claude-sonnet-4.6 on Vertex  
CRITIC_MODEL     = "gemini-1.5-pro-002"           # gemini-pro (1.5 Pro) on Vertex

# ── LOCAL CORE MODELS (Ollama) — KIRMIZI ÇİZGİ ───────────────────────────────
GATEKEEPER_MODEL = "dolphin-llama3"   # localhost:11434 — fast uncensored routing
SHADOW_MODEL     = "dolphin-llama3"   # localhost:11434 — uncensored (abliterated)
EXECUTOR_MODEL   = "deepseek-coder"   # localhost:11434 — code execution specialist


async def call_vertex_model(model_id: str, prompt: str, system_prompt: str = "") -> str:
    """
    Generic async wrapper for Vertex AI models.
    Supports both Claude (via Anthropic on Vertex) and Gemini models.
    """
    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel, Content, Part
        
        loop = asyncio.get_running_loop()
        
        def _call():
            vertexai.init()
            model = GenerativeModel(model_id, system_instruction=system_prompt if system_prompt else None)
            response = model.generate_content(prompt)
            return response.text if hasattr(response, 'text') else str(response)
        
        result = await loop.run_in_executor(None, _call)
        logger.info(f"vertex_call_success", extra={"model": model_id, "chars": len(result)})
        return result
        
    except ImportError:
        logger.error("google-cloud-aiplatform not installed. Run: pip install google-cloud-aiplatform")
        raise
    except Exception as exc:
        logger.error(f"vertex_call_failed", extra={"model": model_id, "error": str(exc)})
        raise


async def call_ollama_model(model_id: str, prompt: str, host: str = "http://localhost:11434") -> str:
    """
    Generic async wrapper for local Ollama models.
    Used by Gatekeeper, Shadow, and Executor agents.
    """
    import httpx
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            f"{host}/api/generate",
            json={"model": model_id, "prompt": prompt, "stream": False}
        )
        response.raise_for_status()
        return response.json().get("response", "")
