from pocketcode.cli.user_interaction import parse_interaction_response


def test_parse_radio_response_accepts_numeric_choice():
    response = parse_interaction_response(
        {
            "kind": "radio",
            "prompt": "Choose one",
            "options": [
                {"id": "alpha", "label": "Alpha", "value": "a"},
                {"id": "beta", "label": "Beta", "value": "b"},
            ],
        },
        "2",
    )

    assert response["value"] == "b"
    assert response["selected_options"][0]["id"] == "beta"


def test_parse_checklist_response_accepts_multiple_ids():
    response = parse_interaction_response(
        {
            "kind": "checklist",
            "prompt": "Select tools",
            "options": [
                {"id": "git", "label": "Git", "value": "git"},
                {"id": "context", "label": "Context", "value": "context"},
                {"id": "search", "label": "Search", "value": "search"},
            ],
            "min_selected": 1,
        },
        "git,search",
    )

    assert response["values"] == ["git", "search"]
    assert [item["id"] for item in response["selected_options"]] == ["git", "search"]


def test_parse_buttons_response_accepts_explicit_value_token():
    response = parse_interaction_response(
        {
            "kind": "buttons",
            "prompt": "Approve this tool?",
            "options": [
                {"id": "one-time", "label": "Approve Once", "value": "once"},
                {"id": "session", "label": "Approve for Session", "value": "session"},
            ],
            "default": "session",
        },
        "once",
    )

    assert response["value"] == "once"
    assert response["selected_options"][0]["id"] == "one-time"