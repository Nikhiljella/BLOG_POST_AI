# BLOG_POST_AI

Generate a blog post with Google Gemini and send it to Google Blogger.

This MVP is intentionally small:

1. Run a local Python command.
2. Generate title, labels, summary, and HTML content with Gemini.
3. Create a Blogger draft post.
4. Log the result in `posts.json`.

## Setup

Create a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Create your local environment file:

```bash
cp .env.example .env
```

Fill in:

```bash
GEMINI_API_KEY=
GOOGLE_BLOGGER_BLOG_ID=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
BLOG_POST_STATUS=draft
GOOGLE_SEARCH_API_KEY=
GOOGLE_SEARCH_ENGINE_ID=
```

## Google Blogger Auth

Create an OAuth client in Google Cloud with access to the Blogger API.

Required scope:

```text
https://www.googleapis.com/auth/blogger
```

On the first run, the script opens a local OAuth flow and writes `token.json`. That file is ignored by git.

## Deal Search Setup

Brand deal search uses Google Programmable Search.

1. Enable the Custom Search API in Google Cloud.
2. Create an API key and set `GOOGLE_SEARCH_API_KEY`.
3. Create a Programmable Search Engine at `programmablesearchengine.google.com`.
4. Configure it to search the web.
5. Copy the search engine ID into `GOOGLE_SEARCH_ENGINE_ID`.

## Usage

Start the app with the helper script.

On macOS or Linux:

```bash
./run.sh --list-blogs
./run.sh --topic "How beginners can use AI to write better study notes"
```

On Windows:

```bat
run.bat --list-blogs
run.bat --topic "How beginners can use AI to write better study notes"
```

Find deal links for a brand without generating a post:

```bash
./run.sh --brand "Nike" --deals-only
```

Generate a blog draft using brand deal links:

```bash
./run.sh --brand "Nike" --topic "Best Nike deals worth checking this week"
```

List the blogs available to your authorized Google account:

```bash
python main.py --list-blogs
```

Generate and create a Blogger draft:

```bash
python main.py --topic "How beginners can use AI to write better study notes"
```

Generate content without posting to Blogger:

```bash
python main.py --topic "Simple automation ideas for small business owners" --dry-run
```

Use a different env file for a different blog:

```bash
python main.py --env-file .env.film --topic "A simple guide to reviewing classic movies"
python main.py --env-file .env.tech --topic "How small teams can use AI automation"
```

Each env file can use a different `GOOGLE_BLOGGER_BLOG_ID`. The app prints the target blog name, ID, and URL before it creates content.

## MVP Acceptance Criteria

- `python main.py` runs locally.
- Gemini returns structured blog content.
- Blogger receives a draft post by default.
- `posts.json` records the result.
- `.env` and `token.json` are not committed.

## Later

- Add a scheduler.
- Add a topic queue.
- Add brand voice configuration.
- Add optional image generation.
- Add auto-publish mode after draft quality is trusted.
