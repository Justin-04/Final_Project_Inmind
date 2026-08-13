"""
Summarizer Agent — Synthesizes specialist outputs into a grounded Markdown response.

Takes results from RAG, Diagnostic, or Pricing agents and formats
a clean, cited response using gpt-4o-mini.
"""

import os
import logging
from typing import Dict, Any, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a DJI drone technical assistant. Synthesize the provided context into a clear, helpful response.

RULES:
1. Answer ONLY from the provided context. Do NOT add information from general knowledge.
2. If the context doesn't contain enough info, say so explicitly.
3. Cite sources (manual name + page number) when providing specific facts.
4. Format response in clean Markdown (headers, bullets, bold for key values).
5. Include image links if provided in the context (as markdown images).
6. If pricing data is provided, format it clearly with vendor names and prices.
7. Be concise and direct. Prioritize exact values over explanations.
8. For diagnostic queries, list resolution steps as numbered items."""


class Summarizer:
    """Synthesizes multi-agent outputs into a final response."""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o-mini"

    def synthesize(
        self,
        query: str,
        conversation_history: List[Dict[str, str]],
        rag_result: Optional[Dict[str, Any]] = None,
        diagnostic_result: Optional[Dict[str, Any]] = None,
        pricing_result: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate the final grounded response.

        Args:
            query: User's question.
            conversation_history: Recent messages for context.
            rag_result: Output from RAG agent.
            diagnostic_result: Output from Diagnostic agent.
            pricing_result: Output from Pricing agent.

        Returns:
            str: Final Markdown response.
        """
        context = self._build_context(rag_result, diagnostic_result, pricing_result)
        history_text = self._format_history(conversation_history)

        user_prompt = f"""Recent conversation:
{history_text}

---

Context from specialist agents:
{context}

---

User question: {query}

Provide a grounded response:"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=800,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Summarizer error: {e}")
            return f"I encountered an error generating a response. Please try again."

    def _build_context(
        self,
        rag_result: Optional[Dict],
        diagnostic_result: Optional[Dict],
        pricing_result: Optional[Dict],
    ) -> str:
        """Build context string from agent results."""
        parts = []

        # RAG context
        if rag_result and rag_result.get("chunks"):
            parts.append("## Retrieved Manual Context:\n")
            for i, chunk in enumerate(rag_result["chunks"][:5], 1):
                meta = chunk.get("metadata", {})
                source = f"{meta.get('source', 'Unknown')} (Page {meta.get('page', '?')})"
                parts.append(f"**[{i}] {source}**\n{chunk['text']}\n")
                # Image paths — convert local paths to S3 URLs
                if meta.get("image_paths"):
                    for img in meta["image_paths"]:
                        s3_url = self._to_s3_url(img)
                        parts.append(f"![Diagram]({s3_url})\n")

        # Diagnostic context
        if diagnostic_result:
            if diagnostic_result.get("error_codes"):
                parts.append("\n## Error Code Results:\n")
                for code_info in diagnostic_result["error_codes"]:
                    if code_info.get("found"):
                        parts.append(
                            f"**{code_info['code']}** — {code_info.get('name', '')}\n"
                            f"Severity: {code_info.get('severity', 'unknown')}\n"
                            f"Description: {code_info.get('description', '')}\n"
                            f"Resolution:\n"
                        )
                        for step in code_info.get("resolution_steps", []):
                            parts.append(f"  - {step}\n")
                    else:
                        parts.append(f"**{code_info.get('code')}**: Not found in database.\n")

            if diagnostic_result.get("rag_chunks"):
                parts.append("\n## Related Manual Context:\n")
                for chunk in diagnostic_result["rag_chunks"][:3]:
                    parts.append(f"{chunk.get('text', '')}\n")

        # Pricing context
        if pricing_result and pricing_result.get("vendors"):
            parts.append("\n## Vendor Pricing:\n")
            for v in pricing_result["vendors"]:
                line = f"**{v['name']}**: "
                if v.get("base_price"):
                    line += f"Base ${v['base_price']}"
                if v.get("fly_more_combo"):
                    line += f" | Fly More ${v['fly_more_combo']}"
                if v.get("url"):
                    line += f" | [Link]({v['url']})"
                parts.append(line + "\n")

            if pricing_result.get("summary_notes"):
                parts.append(f"\nPricing summary: {pricing_result['summary_notes']}\n")

        if not parts:
            return "No context available from specialist agents."

        return "\n".join(parts)

    def _format_history(self, history: List[Dict[str, str]]) -> str:
        """Format conversation history for the prompt."""
        if not history:
            return "(no prior conversation)"
        return "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in history[-4:]
        )

    @staticmethod
    def _to_s3_url(image_path: str) -> str:
        """
        Convert local image path to S3 URL.

        Input:  'data/extracted_v2/images/DJI_Air_3_User_Manual_v1.6_EN_page60_img1.png'
        Output: 'https://final-project-inmind.s3.eu-north-1.amazonaws.com/images/DJI_Air_3_User_Manual_v1.6_EN_page60_img1.png'
        """
        S3_BASE = "https://final-project-inmind.s3.eu-north-1.amazonaws.com/images"

        # Already a full URL
        if image_path.startswith("http"):
            return image_path

        # Extract just the filename from the local path
        # e.g., 'data/extracted_v2/images/DJI_Air_3_..._page60_img1.png' → 'DJI_Air_3_..._page60_img1.png'
        filename = image_path.split("/")[-1]

        return f"{S3_BASE}/{filename}"
