import re

from app.pipeline.extraction.ats.base import AtsParser

# LinkedIn "Easy Apply" notices: subject "Your application was sent to {company}" and a body
# block with the job title on one line and "{company} · {location}" on the next. LinkedIn is
# the platform, never the hiring company.
PARSER = AtsParser(
    name="linkedin",
    domains=("linkedin.com",),
    PATTERNS=[
        (
            "linkedin.title_company_block",
            re.compile(r"(?m)^(?P<position>[A-Z][^\n·]{1,80}?)\s*\n(?P<company>[A-Z][^\n·]{1,60}?)\s*·"),
        ),
    ],
    DISPLAY_NAME_IS_COMPANY=False,
)
