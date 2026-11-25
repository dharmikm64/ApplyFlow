import re

from app.pipeline.extraction.ats.base import AtsParser

PARSER = AtsParser(
    name="lever",
    domains=("lever.co", "hire.lever.co"),
    PATTERNS=[
        (
            "lever.application_to_company_position",
            re.compile(
                r"(?i:application to )(?P<company>[A-Z][\w&.' \-]{1,60}?)(?i: for (?:the )?)(?P<position>[A-Z][^\n.]{1,80}?)(?i: (?:role|position))?[.!\n]"
            ),
        ),
    ],
)
