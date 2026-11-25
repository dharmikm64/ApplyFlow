import re

from app.pipeline.extraction.ats.base import AtsParser

PARSER = AtsParser(
    name="smartrecruiters",
    domains=("smartrecruiters.com",),
    PATTERNS=[
        (
            "smartrecruiters.applied_position_at",
            re.compile(
                r"(?i:you applied for (?:the )?)(?P<position>[A-Z][^\n.]{1,80}?)(?i: (?:position |role )?at )(?P<company>[A-Z][\w&.' \-]{1,60}?)[.!,\n]"
            ),
        ),
    ],
)
