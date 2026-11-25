import re

from app.pipeline.extraction.ats.base import AtsParser

PARSER = AtsParser(
    name="ashby",
    domains=("ashbyhq.com",),
    PATTERNS=[
        (
            "ashby.interest_in_position_at",
            re.compile(
                r"(?i:interest in (?:the )?)(?P<position>[A-Z][^\n.]{1,80}?)(?i: (?:role |position )?at )(?P<company>[A-Z][\w&.' \-]{1,60}?)[.!,\n]"
            ),
        ),
    ],
)
