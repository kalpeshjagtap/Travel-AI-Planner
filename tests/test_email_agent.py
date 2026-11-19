from agents.email import EmailAgent, _send_failure_message


class FailingMCP:
    def call_tool(self, server, tool, arguments):
        raise RuntimeError("gmail-quota-units local daily safety cap reached (1000); no provider request was sent.")


def test_daily_safety_cap_message_says_no_send_request_was_sent():
    message = _send_failure_message(RuntimeError("gmail-quota-units local daily safety cap reached (1000); no provider request was sent."))
    assert "No send request was sent to Google" in message
    assert "retry it after the local quota resets" in message


def test_existing_draft_send_failure_preserves_draft_id_for_safe_retry():
    agent = EmailAgent(mcp=FailingMCP())
    state = {
        "trip_id": "trip-1",
        "request": {"gmail_action": "send_existing_draft", "gmail_draft_id": "draft-123", "email_confirmation": True},
    }
    result = agent.run(state)["agent_results"]["email"]
    assert result["draft_id"] == "draft-123"
    assert result["sent"] is False
    assert result["status"] == "send_blocked"
    assert "no send request was sent" in result["message"].lower()
