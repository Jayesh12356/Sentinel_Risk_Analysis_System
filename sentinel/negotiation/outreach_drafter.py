"""OutreachDrafter — drafts professional outreach emails (Level 9, thinking=ON).

For each AlternativeSupplier, drafts a professional email requesting
information about their services as a potential replacement.
"""

from __future__ import annotations

from typing import Any

import structlog

from sentinel.models.negotiation import AlternativeSupplier, OutreachEmail

logger = structlog.get_logger(__name__)


class OutreachDrafter:
    """Drafts professional outreach emails to alternative suppliers."""

    def __init__(self, demo_mode: bool = False) -> None:
        self.demo_mode = demo_mode

    async def draft(
        self,
        supplier: AlternativeSupplier,
        company_name: str = "Our Company",
        company_profile: Any = None,
        risk_reason: str = "",
        original_supplier: str = "",
    ) -> OutreachEmail:
        """Draft a professional outreach email to a supplier.

        Uses Gemini (thinking=ON) to generate a compelling, specific email.
        """
        # Build context from company profile
        industry = ""
        tech_stack = ""
        if company_profile:
            industry = getattr(company_profile, "industry", "")
            tech_stack = ", ".join(getattr(company_profile, "tech_stack", [])[:5])
            company_name = getattr(company_profile, "name", company_name)

        try:
            from sentinel.llm.client import get_chat_completion

            prompt = (
                f"Draft a professional business email to {supplier.name} from {company_name}.\n"
                f"Context: We are evaluating alternatives to our current provider ({original_supplier}) "
                f"due to: {risk_reason}.\n"
                f"Our industry: {industry or 'Technology'}\n"
                f"Our tech stack: {tech_stack or 'Cloud-based enterprise systems'}\n"
                f"Supplier description: {supplier.description}\n\n"
                f"Requirements:\n"
                f"- Professional and concise (under 200 words)\n"
                f"- Express interest in their services\n"
                f"- Ask about pricing, capabilities, and onboarding timeline\n"
                f"- Do NOT mention the specific risk (bankruptcy etc.) — keep it professional\n"
                f"- Include a clear call to action\n\n"
                f"Return ONLY the email in this exact format:\n"
                f"SUBJECT: [subject line]\n"
                f"BODY:\n[email body]"
            )

            response = await get_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                thinking=True,
            )
            content = response.choices[0].message.content.strip()

            # Parse subject and body
            subject, body = self._parse_email_response(content, supplier, company_name)

        except Exception as exc:
            logger.warning("outreach_drafter.llm_failed", error=str(exc))
            subject, body = self._fallback_email(supplier, company_name, risk_reason)

        email = OutreachEmail(
            supplier=supplier,
            subject=subject,
            body=body,
        )

        logger.info(
            "outreach_drafter.drafted",
            supplier=supplier.name,
            subject=subject[:60],
        )
        return email

    async def draft_batch(
        self,
        suppliers: list[AlternativeSupplier],
        company_name: str = "Our Company",
        company_profile: Any = None,
        risk_reason: str = "",
        original_supplier: str = "",
    ) -> list[OutreachEmail]:
        """Draft emails for multiple suppliers."""
        emails = []
        for supplier in suppliers:
            email = await self.draft(
                supplier=supplier,
                company_name=company_name,
                company_profile=company_profile,
                risk_reason=risk_reason,
                original_supplier=original_supplier,
            )
            emails.append(email)
        return emails

    def _parse_email_response(
        self, content: str, supplier: AlternativeSupplier, company_name: str
    ) -> tuple[str, str]:
        """Parse LLM response into subject and body."""
        subject = f"Partnership Inquiry — {supplier.name}"
        body = content

        if "SUBJECT:" in content:
            parts = content.split("BODY:", 1)
            subject_part = parts[0].replace("SUBJECT:", "").strip()
            if subject_part:
                subject = subject_part
            if len(parts) > 1:
                body = parts[1].strip()

        return subject, body

    def _fallback_email(
        self,
        supplier: AlternativeSupplier,
        company_name: str,
        risk_reason: str,
    ) -> tuple[str, str]:
        """Generate a template email when LLM is unavailable."""
        subject = f"Partnership Inquiry — {supplier.name}"
        body = (
            f"Dear {supplier.name} Team,\n\n"
            f"I'm writing on behalf of {company_name}. We are currently evaluating "
            f"infrastructure and service providers, and {supplier.name} stood out "
            f"as a strong potential partner.\n\n"
            f"We would appreciate learning more about:\n"
            f"- Your service offerings and pricing structure\n"
            f"- Typical onboarding timeline for enterprise clients\n"
            f"- SLA guarantees and support availability\n"
            f"- Any relevant case studies or references\n\n"
            f"Could we schedule a brief call to discuss further? "
            f"We are looking to make a decision within the next 2-3 weeks.\n\n"
            f"Best regards,\n"
            f"{company_name} Team"
        )
        return subject, body
