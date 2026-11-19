"""Gmail MCP tools using desktop OAuth and the official Gmail API."""

import base64
import logging
import os
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from config.settings import get_settings
from services.providers.cache import DailyRequestBudget

logger = logging.getLogger(__name__)
mcp = FastMCP("travel-gmail")
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]
KEYRING_SERVICE = "ai-travel-planner-gmail-oauth"
KEYRING_ACCOUNT = "default"


class GmailAuthorizationError(RuntimeError):
    """Gmail OAuth credentials are missing, expired, or not authorized."""


def _client_file() -> Path:
    settings = get_settings()
    client_file = Path(settings.gmail_oauth_client_file).expanduser()
    if not client_file.is_file():
        raise GmailAuthorizationError(
            "Gmail OAuth client JSON is not configured. Set GMAIL_OAUTH_CLIENT_FILE to your downloaded desktop OAuth file."
        )
    return client_file


def _keyring():
    try:
        import keyring
    except ImportError as exc:
        raise GmailAuthorizationError("Install the keyring package to protect Gmail OAuth tokens in the OS credential store.") from exc
    return keyring


def _load_credentials() -> Any:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise GmailAuthorizationError("Install google-api-python-client, google-auth-oauthlib, and google-auth-httplib2.") from exc
    _client_file()
    token_json = _keyring().get_password(KEYRING_SERVICE, KEYRING_ACCOUNT)
    credentials = Credentials.from_authorized_user_info(__import__("json").loads(token_json), SCOPES) if token_json else None
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _store_credentials(credentials)
    if not credentials or not credentials.valid:
        raise GmailAuthorizationError("Gmail is not authorized. Call the authorize_gmail MCP tool first.")
    return credentials


def _store_credentials(credentials: Any) -> None:
    import json

    _client_file()
    serialized = credentials.to_json()
    _keyring().set_password(KEYRING_SERVICE, KEYRING_ACCOUNT, serialized)


def _service():
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailAuthorizationError("Install google-api-python-client to use Gmail integration.") from exc
    return build("gmail", "v1", credentials=_load_credentials(), cache_discovery=False)


def _consume_quota_units(units: int) -> None:
    """Stop well below Gmail's 2026 daily billing threshold; never enable billing here."""
    settings = get_settings()
    DailyRequestBudget(settings.api_cache_directory).consume(
        "gmail-quota-units", limit=settings.gmail_daily_quota_unit_cap, amount=units
    )


@mcp.tool()
def authorize_gmail() -> dict:
    """Start interactive Gmail desktop OAuth and store tokens in the OS keyring."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise GmailAuthorizationError("Install google-auth-oauthlib to authorize Gmail.") from exc
    client_file = _client_file()
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    credentials = flow.run_local_server(port=0, open_browser=True, access_type="offline", prompt="consent")
    _store_credentials(credentials)
    return {"authorized": True, "scopes": SCOPES, "token_storage": "OS credential store"}


@mcp.tool()
def list_relevant_emails(query: str, max_results: int = 10) -> dict:
    """Read matching Gmail messages after OAuth authorization and an explicit search query."""
    query = query.strip()
    if not query:
        raise ValueError("Supply a narrow Gmail search query, such as a hotel or airline name.")
    max_results = max(1, min(max_results, 25))
    service = _service()
    _consume_quota_units(5)  # Gmail messages.list
    listed = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = []
    for item in listed.get("messages", []):
        _consume_quota_units(20)  # Gmail messages.get in metadata-only mode
        message = service.users().messages().get(
            userId="me", id=item["id"], format="metadata", metadataHeaders=["Subject", "From", "Date"]
        ).execute()
        headers = {h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])}
        messages.append({
            "id": message["id"], "thread_id": message.get("threadId"), "snippet": message.get("snippet", ""),
            "subject": headers.get("subject", ""), "from": headers.get("from", ""), "date": headers.get("date", ""),
        })
    return {"messages": messages, "result_size_estimate": listed.get("resultSizeEstimate", len(messages))}


@mcp.tool()
def create_gmail_draft(recipient: str, subject: str, body: str) -> dict:
    """Create a Gmail draft without sending it."""
    if not recipient.strip() or "@" not in recipient:
        raise ValueError("A valid recipient email address is required.")
    message = EmailMessage()
    message["To"] = recipient.strip()
    message["Subject"] = subject.strip() or "Travel itinerary"
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    _consume_quota_units(10)  # Gmail drafts.create
    draft = _service().users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return {"draft_id": draft["id"], "message_id": draft.get("message", {}).get("id"), "status": "draft_created"}


@mcp.tool()
def send_gmail_draft(draft_id: str, user_confirmation: bool) -> dict:
    """Send a previously created draft; requires explicit user confirmation."""
    if not user_confirmation:
        raise PermissionError("Sending denied: explicit user confirmation is required.")
    if not draft_id.strip():
        raise ValueError("A Gmail draft ID is required.")
    _consume_quota_units(100)  # Gmail drafts.send
    sent = _service().users().drafts().send(userId="me", body={"id": draft_id}).execute()
    return {"message_id": sent.get("id"), "thread_id": sent.get("threadId"), "status": "sent"}


if __name__ == "__main__":
    # Never print to stdout: stdio is the MCP protocol transport.
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), stream=__import__("sys").stderr)
    mcp.run(transport="stdio")
