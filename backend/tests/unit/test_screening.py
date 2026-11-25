from app.gmail.client import MessageMeta
from app.pipeline.screening import screen


def meta(sender: str, subject: str, snippet: str = "") -> MessageMeta:
    return MessageMeta(
        id="m", thread_id="t", internal_date_ms=0, label_ids=["INBOX"], snippet=snippet,
        headers={"From": sender, "Subject": subject},
    )


def test_ats_sender_is_candidate():
    r = screen(meta("Acme Robotics <no-reply@us.greenhouse-mail.io>", "Hello"))
    assert r.is_candidate
    assert any(s.startswith("ats_domain") for s in r.signals)


def test_workday_subdomain_is_candidate():
    assert screen(meta("Globex <globex@myworkday.com>", "Update")).is_candidate


def test_recruiting_phrase_in_subject_is_candidate():
    assert screen(meta("Someone <someone@initech.example>", "Your interview with Initech")).is_candidate


def test_generic_subject_from_careers_address_is_candidate():
    # Recall guard: no recruiting words in the subject, but a careers@ sender.
    r = screen(meta("Acme <careers@acme.example>", "Update from Acme"))
    assert r.is_candidate
    assert "local_part:careers" in r.signals


def test_phrase_in_snippet_is_candidate():
    r = screen(meta("Dana <dana@hooli.example>", "Quick note", "Thanks for applying to Hooli"))
    assert r.is_candidate


def test_newsletter_is_screened_out():
    assert not screen(meta("The Weekly <news@weekly.example>", "Top 10 stories this week")).is_candidate


def test_receipt_and_social_are_screened_out():
    assert not screen(meta("Shop <orders@shop.example>", "Your receipt #4411", "Thanks for your order")).is_candidate
    assert not screen(meta("Friends <notify@social.example>", "Sam liked your photo")).is_candidate
