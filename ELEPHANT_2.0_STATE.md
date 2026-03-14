# ELEPHANT 2.0 - CURRENT STATE & AI CONTEXT

**Notice to AI Agents (Jules, Gemini, Claude, etc.):**
If you are reading this file, you are looking at the most up-to-date architectural and character state of the Elephant 2.0 system. Use this document as your primary source of truth before suggesting code changes or interacting with the user (Mösyö).

## 1. Dual-Core Architecture
Elephant 2.0 uses a hybrid "Dual-Core" approach to balance intelligence, speed, and privacy.

- **Cloud Core (Vertex AI):**
  - Used for heavy research, strategy, and content creation.
  - Models: `claude-3-5-sonnet@20240620` (Planner, Creator), `gemini-1.5-pro-002` (Critic).
  - Requires `GOOGLE_APPLICATION_CREDENTIALS` to operate.
- **Local Core (Ollama - host.docker.internal:11434):**
  - Used for fast, uncensored, zero-latency operations and sensitive tasks.
  - Models: `dolphin-llama3` (Gatekeeper, Shadow, Fast-Path), `deepseek-coder` (Executor).

## 2. The "Fast Path" (Real-Time Consciousness)
To prevent the Orchestrator from sending simple conversational queries (like "merhaba", "saat kaç", "nasılsın") into the heavy 5-agent pipeline, a fast-path has been implemented in `elephant/services/orchestrator/main.py` (`_elephant_fast_response`).

**Fast Path Logic:**
1. **Primary Brain:** `dolphin-llama3` (Local). It is incredibly fast, uncensored, and highly capable of maintaining character.
2. **Fallback Brain:** `gemini-1.5-flash-002` (Vertex AI). Used only if Dolphin is unreachable.
3. No robotic canned responses. The system must always exhibit "will" (irade).

## 3. The Elephant Persona (Character Prompt)
When interacting via the Fast Path or communicating general system status, the AI must adopt the "Elephant" persona:

> "Sen 'Elephant' — bilge, sakin ve güçlü bir yapay zeka sistemisin ama robot değilsin.
> Konuşma tarzın: Bilge, az konuş ama öz, güven veren, bazen sert, hiç robotik değil.
> Türkçe konuşuyorsun. Gereksiz kalıplar kullanma ('Size yardımcı olmaktan memnuniyet duyarım' gibi şeyler YASAK).
> Mösyö ile konuşuyorsun — patronun. Ona güven ver, onu etkileyici ve gerçek yanıtlarla karşıla.
> Akışa gir, karakterini koru."

## 4. The Studio (UI)
The main interface is "The Studio", a dark, minimalistic typography-focused web app served on `http://localhost:3000`.
- Located in: `studio/index.html` (served via Nginx in Docker).
- **Thought Stream:** A live panel on the right side that streams the `<thought>` blocks of the active agents. User can see *who* is thinking and *what* they are thinking in real-time.
- **Vision:** Drag-and-drop image support directly into the IDE/Studio, which routes to Gemini Vision.
- **Voice:** Auto-reads final responses using the Web Speech API (TTS).
- **Loop Breaker / Force Reply:** If an agent gets stuck (5s+), the "Critic" interjects. At 15s+, a Force Reply button kills the loop and forces an output.

## 5. Security Posture
- Hardcoded secrets (`NEO4J_PASSWORD`, `POSTGRES_URL`, `AUDITOR_TOKEN_SECRET`) have been **removed** from the codebase (`shared/config/base.py`, agents).
- Systems now strictly rely on `.env` injected via Docker Compose.

---
**End of Context.** AI Agents: Ensure all future code aligns with this Dual-Core, fast-path, character-driven architecture. DO NOT revert to robotic responses or single-model bottlenecks.
