"""The prompts have to stay inside Groq's per-minute token allowance.

A prompt larger than the whole window comes back 413 and no retry can save it, so
`analysis_prompt` and `entity_prompt` trim their evidence block to fit before sending.
"""

from app import prompts


def _evidence(count=240):
    return [
        {
            "id": f"e{i:03d}",
            "engine": "google",
            "source_domain": "example.com",
            "title": "A long result title that runs on for a while " * 4,
            "snippet": "A long snippet full of detail about pricing and market share. " * 12,
            "search_no": (i % 18) + 1,
            "published_date": "2026-01-01",
        }
        for i in range(count)
    ]


def test_analysis_prompt_fits_its_budget_on_a_full_evidence_set():
    prompt = prompts.analysis_prompt("Acme", "acme.com", "CRM", _evidence(), "note", token_budget=5200)
    assert prompts.estimate_tokens(prompt) <= 5200


def test_entity_prompt_fits_its_budget():
    prompt = prompts.entity_prompt("Acme", "acme.com", "CRM", _evidence(), token_budget=2200)
    assert prompts.estimate_tokens(prompt) <= 2200


def test_a_smaller_budget_produces_a_smaller_prompt():
    items = _evidence()
    big = prompts.analysis_prompt("Acme", "acme.com", "CRM", items, None, token_budget=5200)
    small = prompts.analysis_prompt("Acme", "acme.com", "CRM", items, None, token_budget=4800)
    assert len(small) < len(big)
    assert prompts.estimate_tokens(small) <= 4800


def test_trimming_stops_before_the_evidence_becomes_unreadable():
    # The instructions alone cost about 2.7K tokens, and each search keeps at least one
    # readable snippet, so an impossible budget floors out rather than emptying the
    # prompt. The analyzer's 413 handler is what copes if a floored prompt is still too
    # large for the plan's limit.
    prompt = prompts.analysis_prompt("Acme", "acme.com", "CRM", _evidence(), None, token_budget=500)
    assert prompts.estimate_tokens(prompt) < 5000
    assert "[e000]" in prompt


def test_a_thin_evidence_set_is_left_untrimmed():
    items = _evidence(6)
    fitted = prompts.analysis_prompt("Acme", "acme.com", "CRM", items, None, token_budget=5200)
    unfitted = prompts._analysis_prompt_text(
        "Acme", "acme.com", "CRM", prompts._format_evidence(items), None
    )
    assert fitted == unfitted


def test_every_search_keeps_at_least_one_item_at_the_tightest_budget():
    items = _evidence()
    prompt = prompts.analysis_prompt("Acme", "acme.com", "CRM", items, None, token_budget=1)
    for search_no in prompts._SHAPES:
        first = next(i for i in items if i["search_no"] == search_no)
        assert f"[{first['id']}]" in prompt
