import re

from app.pipeline.extraction.ats.base import AtsParser

PARSER = AtsParser(
    name="workday",
    domains=("myworkday.com", "myworkdayjobs.com", "workday.com"),
    PATTERNS=[
        (
            "workday.applying_to_position_at",
            re.compile(
                r"(?i:applying (?:to|for) (?:the )?)(?P<position>[A-Z][^\n.]{1,80}?)(?i: (?:position|role|job) (?:at|with) )(?P<company>[A-Z][\w&.' \-]{1,60}?)[.!,\n]"
            ),
        ),
    ],
)
