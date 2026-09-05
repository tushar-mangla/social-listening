from listening_loop import notion_sync


def test_sync_marks_only_successfully_created_pages(monkeypatch):
    monkeypatch.setattr(notion_sync, "get_notion_client", lambda: object())
    responses = iter(["page-1", None])
    monkeypatch.setattr(notion_sync, "save_lead_to_notion", lambda lead: next(responses))

    synced = notion_sync.sync_leads_to_notion([{"id": 1, "post_id": "one"}, {"id": 2, "post_id": "two"}])

    assert synced == [1]


def test_build_properties_maps_canonical_fields_and_scores():
    props = notion_sync.build_notion_properties(
        {
            "author": "Founder",
            "source": "reddit",
            "content": "fallback content",
            "one_line": "Bounded model summary.",
            "summary": "Bounded model summary.",
            "author_role": "founder",
            "intent_type": "buying",
            "urgency": "soon",
            "keyword_score": 0.75,
            "confidence": 0.9,
            "outreach_draft": "Hi Founder, ...",
        }
    )
    assert props["Summary"]["rich_text"][0]["text"]["content"] == "Bounded model summary."
    assert props["Author Role"]["rich_text"][0]["text"]["content"] == "founder"
    assert props["Intent Type"]["select"]["name"] == "buying"
    assert props["Urgency"]["select"]["name"] == "soon"
    # Score preserves deterministic keyword score; confidence never derives Score.
    assert props["Score"]["number"] == 0.75
    assert props["Cold Outreach Draft"]["rich_text"][0]["text"]["content"].startswith("Hi Founder")


def test_sync_without_credentials_syncs_nothing(monkeypatch):
    monkeypatch.setattr(notion_sync, "get_notion_client", lambda: None)
    assert notion_sync.sync_leads_to_notion([{"id": 1}]) == []
