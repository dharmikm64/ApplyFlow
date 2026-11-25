"""Declarative phrase and pattern tables for deterministic extraction (research R8).

Order of kind detection (first match wins):
  rejection > withdrawal > offer > strong progress > confirmation > weak progress >
  acknowledgment
Noise (job alerts, invitations to apply, marketing) is checked before all of them, but only
when no application-specific phrase is present.
"""

from __future__ import annotations

import re

IGNORE_CASE = re.IGNORECASE


def _any(*phrases: str) -> re.Pattern[str]:
    return re.compile(r"(?:" + "|".join(phrases) + r")", IGNORE_CASE)


# --- event kinds ---------------------------------------------------------------------------
KIND_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "rejection",
        "rejection.phrases",
        _any(
            r"not (?:be )?moving forward with your (?:application|candidacy)",
            r"(?:will|won't|will not|are not|aren't|have decided not to) (?:be )?(?:moving|move) forward with your",
            r"decided to (?:move forward|proceed|pursue|continue) with other candidates",
            r"decided to pursue other candidates",
            r"pursue other candidates",
            r"regret to inform you",
            r"no longer (?:being )?(?:under consideration|considered)",
            r"(?:you were|you have) not (?:been )?selected",
            r"not (?:been )?selected (?:to move forward|for (?:this|the) (?:role|position))",
            r"unfortunately[^.]{0,160}\b(?:not|other candidates|unable)\b[^.]{0,80}\b(?:position|role|application|candidacy|candidates)",
            r"will not be proceeding with your application",
            r"position has been filled",
        ),
    ),
    (
        "withdrawal",
        "withdrawal.phrases",
        _any(
            r"(?:you have |you've )?withdrawn your application",
            r"application\b[^.]{0,120}?\b(?:has been|was) withdrawn",
            r"you withdrew your application",
            r"(?:requisition|job posting|position) (?:has been|was) (?:closed|cancell?ed)",
        ),
    ),
    (
        "offer",
        "offer.phrases",
        _any(
            r"pleased to (?:extend|offer) you",
            r"extend (?:you )?an offer",
            r"offer of employment",
            r"(?:your|an|the) offer letter",
            r"we(?:'d| would) like to offer you",
            r"job offer",
        ),
    ),
    (
        "progress",
        "progress.strong",
        _any(
            r"schedul\w* (?:an? |your |the )?(?:\w+ ){0,2}(?:interview|call|phone screen|chat|conversation|meeting)",
            r"invite you to (?:an? )?(?:\w+ ){0,2}interview",
            r"interview (?:invitation|invite|request)",
            r"(?:online|technical|coding|take-home|skills) (?:assessment|challenge|test|exercise)",
            r"complete (?:the|an|this|our) (?:\w+ )?assessment",
            r"phone screen",
            r"recruiter (?:call|screen)",
            r"(?:hackerrank|codesignal|codility|hirevue)",
            r"advanc\w* (?:you )?to the next (?:round|stage|step)",
            r"(?:move|moving) you forward",
            r"would (?:like|love) to (?:speak|chat|talk|connect) with you",
            r"share your availability",
            r"availability for (?:a|an) ",
            r"next round",
            r"onsite interview",
        ),
    ),
    (
        "confirmation",
        "confirmation.phrases",
        _any(
            r"thank(?:s| you) for (?:applying|your application)",
            r"we(?:'ve| have) received your application",
            r"your application (?:has been|was|is) (?:received|submitted|complete)",
            r"application (?:received|submitted|confirmation)",
            r"successfully (?:submitted|applied)",
            r"your application was sent to",
            r"thank you for (?:your )?(?:interest in|submitting)[^.]{0,120}\b(?:application|applied|applying)\b",
            r"we have your application",
        ),
    ),
    (
        "progress",
        "progress.weak",
        _any(
            r"next steps? (?:in|for) (?:the|our|your) (?:hiring|interview|recruiting) process",
            r"(?:move|moving) forward with your (?:application|candidacy)",
        ),
    ),
    (
        "acknowledgment",
        "acknowledgment.phrases",
        _any(
            r"we(?:'ve| have)? received your (?:message|email|inquiry|response|note)",
            r"thanks? (?:you )?for (?:your )?(?:reply|response|getting back|reaching out)",
            r"this is an automated (?:reply|response|message)",
        ),
    ),
]

# --- noise ------------------------------------------------------------------------------------
JOB_ALERT = _any(
    r"job alert",
    r"jobs? (?:you may|you might|that may) (?:be interested in|like)",
    r"new jobs? (?:for you|matching|that match)",
    r"recommended jobs",
    r"jobs matching your",
    r"\d+ new jobs",
    r"top job picks",
)
INVITE_TO_APPLY = _any(
    r"invite you to apply",
    r"invitation to apply",
    r"(?:we )?think you(?:'d| would) be a (?:great )?(?:fit|match)",
    r"consider applying",
    r"apply now",
    r"you(?:'re| are) a (?:great|good|strong) (?:fit|match) for",
)
MARKETING = _any(
    r"newsletter",
    r"webinar",
    r"limited[- ]time",
    r"% off",
    r"special offer",
    r"upgrade to premium",
)

# --- fields ---------------------------------------------------------------------------------
_NAME = r"[A-Z0-9](?:[\w&@'’\-]|\.(?=\w)|(?<=\b[A-Z])\.(?= [A-Z]))*(?:[ ][A-Za-z0-9&@'’\-](?:[\w&@'’\-]|\.(?=\w)|(?<=\b[A-Z])\.(?= [A-Z]))*){0,6}?"
_TITLE = r"[A-Za-z0-9][\w&/+#.,'’()\-]*(?:[ ][A-Za-z0-9&/+#.,'’()\-]+){0,9}?"
_END = r"(?=[ ]*(?:[.!,;:\n]|$| role| position| job| opening| team| has| was| is| and| -))"

# Each pattern must define named groups `company` and/or `position`. Keywords are matched
# case-insensitively via scoped (?i:...) groups; captured names must start with a capital or
# digit so ordinary prose ("our team") is not captured.
def _p(src: str) -> re.Pattern[str]:
    return re.compile(src.replace("{N}", _NAME).replace("{T}", _TITLE).replace("{E}", _END))


_ART = r"(?:(?i:the|our|a|an) )?"
FIELD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "f.applying_to_for",
        _p(r"\b(?i:applying|applied|application|apply) (?i:to|at|with) (?P<company>{N}) (?i:for) " + _ART + r"(?P<position>{T}){E}"),
    ),
    (
        "f.application_for_at",
        _p(r"\b(?i:application|candidacy|interest|applying|applied) (?i:for|in|to) " + _ART + r"(?P<position>{T}) (?:(?i:role|position|job|opening) )?(?i:at|with) (?P<company>{N}){E}"),
    ),
    (
        "f.position_at_company",
        _p(r"\b(?i:for|regarding|re:|about) " + _ART + r"(?P<position>{T}) (?:(?i:role|position|opening) )?(?i:at) (?P<company>{N}){E}"),
    ),
    ("f.sent_to", _p(r"(?i:your application was sent to) (?P<company>{N}){E}")),
    (
        "f.thanks_applying_company",
        _p(r"\b(?i:applying|your application|applied|application) (?i:to|at|with) (?P<company>{N}){E}"),
    ),
    ("f.interest_in_company", _p(r"\b(?i:interest in) (?:(?i:joining|working at) )?(?P<company>{N}){E}")),
    ("f.for_the_role", _p(r"\b(?i:for) (?i:the|our) (?P<position>{T}) (?i:role|position|opening){E}")),
    ("f.label_position", re.compile(r"(?im)^\s*(?:position|role|job title|job)\s*:\s*(?P<position>[^\n(]{2,80}?)\s*(?:\(|$)")),
    ("f.label_company", re.compile(r"(?im)^\s*company\s*:\s*(?P<company>[^\n]{2,60}?)\s*$")),
]

REQ_ID = re.compile(
    r"(?:req(?:uisition)?|job)(?:\s*(?:id|#|number|no\.?))\s*[:#]?\s*(?P<req>[A-Z0-9][A-Z0-9_\-]{2,})",
    IGNORE_CASE,
)
STATED_DATE = re.compile(
    r"(?:applied|submitted)(?: (?:your|an|the) application)?(?: for [^.]{1,80}?)? on "
    r"(?P<date>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,? )?"
    r"(?P<d>[A-Z][a-z]+ \d{1,2},? \d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})",
    IGNORE_CASE,
)

# Display names / words that identify a platform or a generic sender, never a hiring company.
PLATFORM_NAMES = {
    "linkedin",
    "indeed",
    "greenhouse",
    "lever",
    "workday",
    "ashby",
    "icims",
    "smartrecruiters",
    "jobvite",
    "workable",
    "glassdoor",
    "ziprecruiter",
    "handshake",
    "wellfound",
    "dice",
    "hackerrank",
    "codesignal",
    "hirevue",
    "taleo",
    "successfactors",
    "bamboohr",
    "jobs",
    "careers",
    "recruiting",
    "talent acquisition",
    "hiring team",
    "no-reply",
    "noreply",
    "do not reply",
    "notifications",
}
SENDER_SUFFIXES = re.compile(
    r"\s*(?:[-|@]\s*)?(?:hiring team|recruiting team|recruiting|recruitment|careers|talent acquisition|talent team|talent|people team|hr|jobs|via greenhouse|via lever|via workday|via ashby|via linkedin|team)\s*$",
    IGNORE_CASE,
)
