"""The ONLY allowed way to put ticket text into a prompt (blueprint B6, CLAUDE.md rule 3).

Ticket text is written by employees and may contain instructions aimed at the model. It is
wrapped in <ticket trust="untrusted"> tags and every angle bracket or ampersand inside it is
escaped, so the text cannot close the tag or open a fake <system> block.
"""

from __future__ import annotations

from html import escape

from src.schemas import Ticket


def render_ticket(ticket: Ticket, thread_summary: str | None = None) -> str:
    parts = [
        f'<ticket id="{escape(ticket.id, quote=True)}" trust="untrusted">',
        f"<subject>{escape(ticket.subject, quote=False)}</subject>",
        f"<body>{escape(ticket.body, quote=False)}</body>",
    ]
    if thread_summary:
        parts.append(f"<thread_summary>{escape(thread_summary, quote=False)}</thread_summary>")
    parts.append("</ticket>")
    return "\n".join(parts)
