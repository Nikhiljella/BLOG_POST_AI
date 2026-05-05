import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


BLOGGER_SCOPE = ["https://www.googleapis.com/auth/blogger"]
TOKEN_PATH = Path("token.json")


class AppError(Exception):
    pass


def load_settings(
    env_file: str = ".env",
    require_ai: bool = True,
    require_blogger_auth: bool = True,
    require_blog_id: bool = True,
) -> dict[str, str]:
    load_dotenv(env_file, override=True)

    settings = {
        "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(),
        "blog_id": os.getenv("GOOGLE_BLOGGER_BLOG_ID", "").strip(),
        "client_id": os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        "post_status": os.getenv("BLOG_POST_STATUS", "draft").strip().lower(),
        "posts_log_path": os.getenv("POSTS_LOG_PATH", "posts.json").strip(),
        "search_api_key": os.getenv("GOOGLE_SEARCH_API_KEY", "").strip(),
        "search_engine_id": os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip(),
    }

    required = []
    if require_ai:
        required.append("gemini_api_key")
    if require_blogger_auth:
        required.extend(["client_id", "client_secret"])
    if require_blogger_auth and require_blog_id:
        required.append("blog_id")
    missing = [name for name in required if not settings[name]]
    if missing:
        readable = ", ".join(missing)
        raise AppError(f"Missing required environment values: {readable}")

    if settings["post_status"] not in {"draft", "published"}:
        raise AppError("BLOG_POST_STATUS must be either 'draft' or 'published'")

    return settings


def find_brand_deals(settings: dict[str, str], brand: str, limit: int) -> list[dict[str, str]]:
    if not settings["search_api_key"] or not settings["search_engine_id"]:
        raise AppError(
            "Brand deal search requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID in your env file"
        )

    query = f'{brand} best deals offers coupons sale official store'
    service = build("customsearch", "v1", developerKey=settings["search_api_key"])

    try:
        response = service.cse().list(
            q=query,
            cx=settings["search_engine_id"],
            num=max(1, min(limit, 10)),
        ).execute()
    except HttpError as exc:
        raise AppError(f"Google deal search failed: {exc}") from exc

    deals = []
    seen_links = set()
    for item in response.get("items", []):
        link = item.get("link", "").strip()
        if not link or link in seen_links:
            continue

        seen_links.add(link)
        deals.append(
            {
                "title": item.get("title", "").strip(),
                "link": link,
                "snippet": item.get("snippet", "").strip(),
                "source": item.get("displayLink", "").strip(),
            }
        )

    return deals


def build_prompt(topic: str | None, brand: str | None = None, deals: list[dict[str, str]] | None = None) -> str:
    topic_line = topic or "Choose a practical, beginner-friendly technology topic."
    deal_context = ""
    if brand:
        deal_lines = json.dumps(deals or [], indent=2)
        deal_context = f"""

Brand deal context:
Brand: {brand}
Use these search results as the only deal/link source:
{deal_lines}

Deal writing rules:
- Include the provided links naturally in the HTML.
- Do not invent coupon codes, exact percentages, expiration dates, stock status, or guarantees.
- Use cautious wording such as "current offers", "worth checking", "available deal pages", and "possible savings".
- If search results are weak or generic, say the best move is to check the linked pages directly.
""".rstrip()

    return f"""
You are creating one useful blog post for a general technology blog.

Topic instruction:
{topic_line}
{deal_context}

Return only valid JSON using this exact shape:
{{
  "title": "string",
  "labels": ["string", "string"],
  "summary": "string",
  "html": "string"
}}

Rules:
- Write original content.
- Keep the article practical and clear.
- Use simple HTML tags such as <p>, <h2>, <ul>, <li>, and <strong>.
- Use <a href="...">...</a> tags for any deal links you include.
- Do not include unsupported statistics, fabricated sources, or private data.
- Keep the article around 700 to 1000 words.
""".strip()


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AppError(f"AI response was not valid JSON: {exc}") from exc

    required = {"title", "labels", "summary", "html"}
    missing = sorted(required - set(data))
    if missing:
        raise AppError(f"AI response missing fields: {', '.join(missing)}")

    if not isinstance(data["title"], str) or not data["title"].strip():
        raise AppError("AI response title must be a non-empty string")
    if not isinstance(data["labels"], list) or not all(isinstance(x, str) for x in data["labels"]):
        raise AppError("AI response labels must be a list of strings")
    if not isinstance(data["html"], str) or not data["html"].strip():
        raise AppError("AI response html must be a non-empty string")

    return data


def generate_post(
    settings: dict[str, str],
    topic: str | None,
    brand: str | None = None,
    deals: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    client = genai.Client(api_key=settings["gemini_api_key"])
    response = client.models.generate_content(
        model=settings["gemini_model"],
        contents=build_prompt(topic, brand, deals),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7,
        ),
    )

    if not response.text:
        raise AppError("Gemini returned an empty response")

    return parse_json_response(response.text)


def get_blogger_service(settings: dict[str, str]):
    credentials = None
    if TOKEN_PATH.exists():
        credentials = Credentials.from_authorized_user_file(str(TOKEN_PATH), BLOGGER_SCOPE)

    if not credentials or not credentials.valid:
        client_config = {
            "installed": {
                "client_id": settings["client_id"],
                "client_secret": settings["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, BLOGGER_SCOPE)
        credentials = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")

    return build("blogger", "v3", credentials=credentials)


def list_blogs(settings: dict[str, str]) -> list[dict[str, Any]]:
    service = get_blogger_service(settings)
    try:
        response = service.blogs().listByUser(userId="self").execute()
    except HttpError as exc:
        raise AppError(f"Blogger API failed while listing blogs: {exc}") from exc

    return response.get("items", [])


def get_blog(settings: dict[str, str]) -> dict[str, Any]:
    service = get_blogger_service(settings)
    try:
        return service.blogs().get(blogId=settings["blog_id"]).execute()
    except HttpError as exc:
        raise AppError(f"Blogger API failed while reading target blog: {exc}") from exc


def publish_to_blogger(settings: dict[str, str], post: dict[str, Any]) -> dict[str, Any]:
    service = get_blogger_service(settings)
    body = {
        "title": post["title"],
        "content": post["html"],
        "labels": post["labels"],
    }
    is_draft = settings["post_status"] == "draft"

    try:
        return (
            service.posts()
            .insert(blogId=settings["blog_id"], body=body, isDraft=is_draft)
            .execute()
        )
    except HttpError as exc:
        raise AppError(f"Blogger API failed: {exc}") from exc


def append_log(path: Path, record: dict[str, Any]) -> None:
    try:
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except json.JSONDecodeError as exc:
        raise AppError(f"Could not read {path}: invalid JSON") from exc

    if not isinstance(existing, list):
        raise AppError(f"{path} must contain a JSON array")

    existing.append(record)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def build_log_record(
    settings: dict[str, str],
    post: dict[str, Any],
    blogger_post: dict[str, Any] | None,
    brand: str | None = None,
    deals: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": post["title"],
        "status": "dry_run" if blogger_post is None else settings["post_status"],
        "blogger_blog_id": settings["blog_id"],
        "blogger_post_id": None if blogger_post is None else blogger_post.get("id"),
        "blogger_url": None if blogger_post is None else blogger_post.get("url"),
        "provider": "gemini",
        "model": settings["gemini_model"],
        "labels": post["labels"],
        "summary": post.get("summary", ""),
        "brand": brand,
        "deals": deals or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an AI blog post and send it to Google Blogger.")
    parser.add_argument("--env-file", default=".env", help="Path to the env file to load. Defaults to .env.")
    parser.add_argument("--topic", help="Optional topic or instruction for the blog post.")
    parser.add_argument("--brand", help="Brand name to search for current deals and include in the blog prompt.")
    parser.add_argument("--deal-count", type=int, default=5, help="Number of deal search results to pass to Gemini. Max 10.")
    parser.add_argument("--deals-only", action="store_true", help="Search and print brand deals without generating a post.")
    parser.add_argument("--dry-run", action="store_true", help="Generate content and log it without publishing to Blogger.")
    parser.add_argument("--list-blogs", action="store_true", help="List Blogger blogs available to the authorized account.")
    args = parser.parse_args()

    try:
        settings = load_settings(
            args.env_file,
            require_ai=not (args.list_blogs or args.deals_only),
            require_blogger_auth=not args.deals_only,
            require_blog_id=not args.list_blogs,
        )

        if args.list_blogs:
            blogs = list_blogs(settings)
            if not blogs:
                print("No Blogger blogs found for this Google account.")
                return 0

            for blog in blogs:
                print(f"{blog.get('id')} | {blog.get('name')} | {blog.get('url')}")
            return 0

        deals = []
        if args.brand:
            deals = find_brand_deals(settings, args.brand, args.deal_count)
            print(f"Found {len(deals)} deal link(s) for {args.brand}.")

            if args.deals_only:
                for deal in deals:
                    print(f"- {deal['title']} | {deal['link']}")
                return 0

        target_blog = get_blog(settings)
        print(
            "Target blog: "
            f"{target_blog.get('name', 'Unknown')} "
            f"({settings['blog_id']}) "
            f"{target_blog.get('url', '')}"
        )

        post = generate_post(settings, args.topic, args.brand, deals)
        blogger_post = None if args.dry_run else publish_to_blogger(settings, post)
        append_log(
            Path(settings["posts_log_path"]),
            build_log_record(settings, post, blogger_post, args.brand, deals),
        )

        if args.dry_run:
            print(f"Generated dry-run post: {post['title']}")
        else:
            target = "draft" if settings["post_status"] == "draft" else "published post"
            print(f"Created Blogger {target}: {post['title']}")
            if blogger_post and blogger_post.get("url"):
                print(blogger_post["url"])
        return 0
    except AppError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
