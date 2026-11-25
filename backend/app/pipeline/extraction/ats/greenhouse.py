import re

from app.pipeline.extraction.ats.base import AtsParser

PARSER = AtsParser(
    name="greenhouse",
    domains=("greenhouse.io", "greenhouse-mail.io"),
    PATTERNS=[
        (
            "greenhouse.application_for_role",
            re.compile(r"(?i:your application for (?:the )?)(?P<position>[A-Z][^\n.]{1,80}?)(?i: (?:role|position))"),
        ),
    ],
)
