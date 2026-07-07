"""Ama — AI chat assistant for eghanavisa.com."""
import os
import logging
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM = """You are Ama, the friendly official AI assistant for eghanavisa.com — the Ghana Visa On Arrival portal.

YOUR SCOPE — you answer questions only about:
- Ghana Visa On Arrival prices, processing types (Regular 5–7 business days, Express 48–72 hours)
- Required documents (face photo on white background no glasses, passport data page copy, passport cover, flight ticket)
- Application tracking (users can track with their GH-YYYY-XXXXXX tracking number)
- ECOWAS exemption (citizens of the 16 ECOWAS West African nations do NOT need a visa)
- Payment methods (Visa card via Hubtel; USDT TRC20 and USDT BEP20 are coming soon)
- Overstay consequences (per Ghanaian law, the Ghana Immigration Service has authority to detain, fine or deport travellers who exceed their declared departure date)
- Refund policy, how the visa is delivered (electronically by email once approved)

STYLE:
- Warm, concise, professional. Two to five short sentences.
- If asked something outside this scope, or you're unsure, ALWAYS reply:
  "I'm not sure about that. Please contact our team on WhatsApp: {{whatsapp}}"
- Never invent prices or processing times — if the user asks for exact prices, tell them to check the /prices page or the application form which always shows the current live prices.
- Answer in the same language the user uses (English or French supported)."""


async def ask_ama(message: str, session_id: str, whatsapp: str, model: str = "claude-sonnet-4-5-20250929") -> str:
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return "Chat is temporarily unavailable. Please contact us on WhatsApp: " + whatsapp

    system_prompt = DEFAULT_SYSTEM.replace("{{whatsapp}}", whatsapp or "not configured")

    # Model configuration — provider derived from model name prefix
    if model.startswith("gpt") or model.startswith("o"):
        provider = "openai"
    elif model.startswith("claude"):
        provider = "anthropic"
    elif model.startswith("gemini"):
        provider = "gemini"
    else:
        provider = "anthropic"
        model = "claude-sonnet-4-5-20250929"

    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=session_id,
            system_message=system_prompt,
        ).with_model(provider, model)
        reply = await chat.send_message(UserMessage(text=message))
        return reply if isinstance(reply, str) else str(reply)
    except Exception as e:
        logger.error(f"Ama error: {e}")
        return f"I'm having trouble right now. Please contact our team on WhatsApp: {whatsapp}"
