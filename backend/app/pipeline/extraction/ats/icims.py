import re

from app.pipeline.extraction.ats.base import AtsParser

PARSER = AtsParser(
    name="icims",
    domains=("icims.com",),
    PATTERNS=[
        (
            "icims.job_title_label",
            re.compile(r"(?im)^\s*job title\s*:\s*(?P<position>[^\n]{2,80}?)\s*$"),
        ),
    ],
)
