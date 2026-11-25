"""ATS-specific parsers. Each one recognizes its sender domains and adds template patterns."""

from __future__ import annotations

from app.pipeline.extraction.ats import (
    ashby,
    greenhouse,
    icims,
    lever,
    linkedin,
    smartrecruiters,
    workday,
)
from app.pipeline.extraction.ats.base import AtsParser

PARSERS: list[AtsParser] = [
    greenhouse.PARSER,
    lever.PARSER,
    workday.PARSER,
    ashby.PARSER,
    icims.PARSER,
    smartrecruiters.PARSER,
    linkedin.PARSER,
]
# Job boards whose display name is never the hiring company.
_BOARDS = AtsParser(
    name="job_board",
    domains=("indeed.com", "indeedemail.com", "glassdoor.com", "ziprecruiter.com", "dice.com",
             "joinhandshake.com", "wellfound.com"),
    DISPLAY_NAME_IS_COMPANY=False,
)


def parser_for(domain: str) -> AtsParser | None:
    for p in [*PARSERS, _BOARDS]:
        if p.matches(domain):
            return p
    return None
