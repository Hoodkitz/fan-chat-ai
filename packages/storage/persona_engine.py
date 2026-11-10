"""AI Persona Engine for fan chat responses."""
from typing import Dict, List
import json


class PersonaEngine:
    def __init__(self):
        self._personas: Dict[str, dict] = {}
        self._fan_profiles: Dict[str, dict] = {}
        self._chat_history: Dict[str, List[dict]] = {}

    def set_persona(self, tenant_id: str, persona: str, writing_style: str, boundaries: List[str], prices: dict):
        self._personas[tenant_id] = {
            "persona": persona,
            "writing_style": writing_style,
            "boundaries": boundaries,
            "prices": prices,
        }

    def get_persona(self, tenant_id: str) -> dict:
        return self._personas.get(tenant_id, {})

    def add_fan_profile(self, tenant_id: str, fan_id: str, profile: dict):
        key = f"{tenant_id}:{fan_id}"
        self._fan_profiles[key] = profile

    def get_fan_profile(self, tenant_id: str, fan_id: str) -> dict:
        return self._fan_profiles.get(f"{tenant_id}:{fan_id}", {})

    def record_message(self, tenant_id: str, fan_id: str, role: str, content: str):
        key = f"{tenant_id}:{fan_id}"
        self._chat_history.setdefault(key, []).append({"role": role, "content": content})

    def get_history(self, tenant_id: str, fan_id: str) -> List[dict]:
        return self._chat_history.get(f"{tenant_id}:{fan_id}", [])

    def generate_response(self, tenant_id: str, fan_id: str, fan_message: str) -> str:
        """Generate an AI response based on persona and fan profile."""
        persona = self.get_persona(tenant_id)
        fan_profile = self.get_fan_profile(tenant_id, fan_id)
        history = self.get_history(tenant_id, fan_id)

        # Build context
        style = persona.get("writing_style", "friendly")
        persona_desc = persona.get("persona", "helpful assistant")

        # Simple response generation (replace with LLM call in production)
        response = f"[{style}] Hey! Thanks for your message. "
        if fan_profile.get("preferences"):
            response += f"I remember you like {', '.join(fan_profile['preferences'])}. "
        response += "How can I help you today?"

        self.record_message(tenant_id, fan_id, "fan", fan_message)
        self.record_message(tenant_id, fan_id, "model", response)
        return response

    def should_auto_respond(self, tenant_id: str) -> bool:
        persona = self.get_persona(tenant_id)
        return persona.get("auto_responder_enabled", False)
