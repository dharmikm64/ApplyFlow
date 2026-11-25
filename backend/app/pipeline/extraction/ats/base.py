"""Base description of an applicant-tracking-system (ATS) / job-platform email format."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AtsParser:
    name: str
    domains: tuple[str, ...]
    # Template-specific patterns tried before the generic ones; groups: company, position.
    PATTERNS: list[tuple[str, re.Pattern[str]]] = field(default_factory=list)
    # Whether the sender display name is the hiring company (true for most ATSs, which send
    # "Acme Robotics <no-reply@...>"; false for job boards like LinkedIn).
    DISPLAY_NAME_IS_COMPANY: bool = True

    def matches(self, domain: str) -> bool:
        return any(domain == d or domain.endswith("." + d) for d in self.domains)
