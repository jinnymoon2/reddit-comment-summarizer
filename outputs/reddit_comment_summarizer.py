#!/usr/bin/env python3
"""
Summarize Reddit thread comments into bullet points.

Usage:
  python reddit_comment_summarizer.py "https://www.reddit.com/r/example/comments/abc123/title/"
  python reddit_comment_summarizer.py thread.json --input-file
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import math
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from html import unescape
from typing import Any, Iterable


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)

STOPWORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "did",
    "do",
    "does",
    "doing",
    "don",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "will",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


@dataclass(frozen=True)
class Comment:
    body: str
    score: int
    depth: int


def normalize_reddit_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Please provide a full Reddit thread URL, including https://")

    path = parsed.path.rstrip("/")
    if not path.endswith(".json"):
        path = f"{path}.json"

    query = urllib.parse.parse_qs(parsed.query)
    query.setdefault("limit", ["500"])
    query.setdefault("sort", ["confidence"])
    flat_query = urllib.parse.urlencode({key: values[-1] for key, values in query.items()})

    return urllib.parse.urlunparse(
        ("https", parsed.netloc, path, "", flat_query, "")
    )


def request_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
    }
    if extra:
        headers.update(extra)
    return headers


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers=request_headers())
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            raise RuntimeError(
                "Reddit refused this request. Try again later, use a saved JSON file, "
                "or use old.reddit.com in the URL."
            ) from exc
        raise RuntimeError(f"Reddit returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Reddit: {exc.reason}") from exc


def load_input(source: str, input_file: bool) -> Any:
    if input_file:
        with open(source, "r", encoding="utf-8") as file:
            return json.load(file)
    return fetch_json(normalize_reddit_url(source))


def plain_text(markdown: str) -> str:
    text = unescape(markdown)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"(^|\n)\s*>.*", " ", text)
    text = re.sub(r"[*_~#>\[\]()]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def solve_reddit_challenge(
    opener: urllib.request.OpenerDirector, url: str, html_text: str
) -> str:
    solution_match = re.search(r'\("([0-9a-f]+)"\)', html_text)
    token_match = re.search(r'name="token" value="([^"]+)"', html_text)
    if not solution_match or not token_match:
        return html_text

    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    query.update(
        {
            "solution": [solution_match.group(1) * 2],
            "js_challenge": ["1"],
            "token": [token_match.group(1)],
            "jsc_orig_r": [""],
        }
    )
    solved_url = urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            urllib.parse.urlencode({key: values[-1] for key, values in query.items()}),
            "",
        )
    )
    request = urllib.request.Request(solved_url, headers=request_headers())
    with opener.open(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, "replace")


def fetch_text_with_reddit_challenge(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    referer: str | None = None,
    accept: str = "text/html",
) -> str:
    extra_headers = {"Accept": accept}
    if referer:
        extra_headers["Referer"] = referer
    request = urllib.request.Request(url, headers=request_headers(extra_headers))
    with opener.open(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        html_text = response.read().decode(charset, "replace")

    if "Please wait for verification" in html_text:
        html_text = solve_reddit_challenge(opener, url, html_text)
    return html_text


def reddit_origin(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def extract_attr(tag: str, name: str) -> str:
    match = re.search(rf'\s{name}="([^"]*)"', tag)
    return unescape(match.group(1)) if match else ""


def strip_html(html_text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_div_by_id(html_text: str, element_id: str) -> str:
    start_match = re.search(
        rf'<div\b[^>]*id="{re.escape(element_id)}"[^>]*>', html_text
    )
    if not start_match:
        return ""

    start = start_match.end()
    depth = 1
    position = start
    tag_pattern = re.compile(r"</?div\b[^>]*>", re.I)
    while depth and (tag_match := tag_pattern.search(html_text, position)):
        tag = tag_match.group(0)
        if tag.startswith("</"):
            depth -= 1
        else:
            depth += 1
        position = tag_match.end()

    if depth != 0:
        return ""
    return html_text[start : tag_match.start()]


def parse_comments_from_html(html_text: str) -> list[Comment]:
    comments = []
    comment_tags = re.finditer(r"<shreddit-comment\b[^>]*>", html_text)

    for match in comment_tags:
        tag = match.group(0)
        thing_id = extract_attr(tag, "thingId")
        if not thing_id:
            continue

        body_html = extract_div_by_id(html_text[match.end() :], f"{thing_id}-comment-rtjson-content")
        body = strip_html(body_html)
        if not body or body in {"[deleted]", "[removed]"}:
            continue

        score_text = extract_attr(tag, "score")
        depth_text = extract_attr(tag, "depth")
        try:
            score = int(score_text or "0")
        except ValueError:
            score = 0
        try:
            depth = int(depth_text or "0")
        except ValueError:
            depth = 0

        comments.append(Comment(body, score, depth))

    return comments


def fetch_thread_from_html(url: str) -> tuple[str, str, list[Comment]]:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    page_html = fetch_text_with_reddit_challenge(opener, url)

    post_tag_match = re.search(r"<shreddit-post\b[^>]*>", page_html)
    title = "Reddit thread"
    if post_tag_match:
        title = extract_attr(post_tag_match.group(0), "post-title") or title

    post_body_match = re.search(r'property="schema:articleBody"[^>]*>(.*?)</div>', page_html, re.S)
    selftext = strip_html(post_body_match.group(1)) if post_body_match else ""

    partial_match = re.search(
        r'<faceplate-partial[^>]+name="TopComments[^"]*"[^>]+src="([^"]+)"',
        page_html,
    )
    if not partial_match:
        raise RuntimeError("Could not find Reddit comments on the page.")

    partial_src = unescape(partial_match.group(1))
    partial_url = urllib.parse.urljoin(reddit_origin(url), partial_src)
    comments_html = fetch_text_with_reddit_challenge(
        opener,
        partial_url,
        referer=url,
        accept="text/vnd.reddit.partial+html, text/html;q=0.9",
    )
    comments = parse_comments_from_html(comments_html)
    if not comments:
        raise RuntimeError("Could not extract any readable comments from Reddit's page.")

    return title, selftext, comments


def iter_comment_nodes(node: dict[str, Any], depth: int = 0) -> Iterable[Comment]:
    data = node.get("data", {})
    kind = node.get("kind")

    if kind == "t1":
        body = data.get("body") or ""
        if body not in {"[deleted]", "[removed]"}:
            cleaned = plain_text(body)
            if cleaned:
                yield Comment(cleaned, int(data.get("score") or 0), depth)

    replies = data.get("replies")
    if isinstance(replies, dict):
        children = replies.get("data", {}).get("children", [])
        for child in children:
            yield from iter_comment_nodes(child, depth + 1)


def extract_thread(payload: Any) -> tuple[str, str, list[Comment]]:
    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError("Expected Reddit thread JSON: a list containing post and comments data.")

    post_data = payload[0]["data"]["children"][0]["data"]
    title = plain_text(post_data.get("title", "Reddit thread"))
    selftext = plain_text(post_data.get("selftext", ""))

    comments = []
    for child in payload[1].get("data", {}).get("children", []):
        comments.extend(iter_comment_nodes(child))

    return title, selftext, comments


def split_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+", text)
    return [piece.strip(" -") for piece in pieces if len(piece.strip()) >= 35]


def words(text: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-zA-Z][a-zA-Z'-]{2,}", text.lower())
        if word not in STOPWORDS
    ]


def score_sentences(comments: list[Comment]) -> list[tuple[float, str]]:
    corpus_words = Counter()
    for comment in comments:
        corpus_words.update(words(comment.body))

    if not corpus_words:
        return []

    max_frequency = max(corpus_words.values())
    scored = []
    seen = set()
    for comment in comments:
        score_weight = 1 + math.log(max(comment.score, 0) + 1, 10)
        depth_weight = 1 / (1 + comment.depth * 0.2)

        for sentence in split_sentences(comment.body):
            key = re.sub(r"\W+", "", sentence.lower())
            if key in seen:
                continue
            seen.add(key)

            sentence_words = words(sentence)
            if not sentence_words:
                continue

            frequency_score = sum(corpus_words[word] / max_frequency for word in sentence_words)
            length_penalty = max(1, len(sentence_words) / 22)
            total = (frequency_score / length_penalty) * score_weight * depth_weight
            scored.append((total, sentence))

    return sorted(scored, reverse=True)


def trim_sentence(sentence: str, max_chars: int) -> str:
    sentence = sentence.strip()
    if len(sentence) <= max_chars:
        return sentence
    trimmed = sentence[: max_chars - 1].rsplit(" ", 1)[0]
    return f"{trimmed}..."


def summarize(comments: list[Comment], bullet_count: int, max_chars: int) -> list[str]:
    scored = score_sentences(comments)
    chosen = []
    chosen_terms: list[set[str]] = []

    for _, sentence in scored:
        terms = set(words(sentence))
        if not terms:
            continue

        too_similar = any(
            len(terms & existing) / max(len(terms | existing), 1) > 0.45
            for existing in chosen_terms
        )
        if too_similar:
            continue

        chosen.append(trim_sentence(sentence, max_chars))
        chosen_terms.append(terms)
        if len(chosen) == bullet_count:
            break

    return chosen


def print_summary(title: str, selftext: str, comments: list[Comment], bullets: list[str]) -> None:
    print(f"\n{title}")
    print("=" * min(len(title), 80))

    if selftext:
        preview = textwrap.shorten(selftext, width=220, placeholder="...")
        print(f"\nPost: {preview}")

    print(f"\nRead {len(comments)} comments.")
    if not bullets:
        print("\nNo summary could be generated from the available comments.")
        return

    print("\nSummary")
    for bullet in bullets:
        print(f"- {bullet}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize Reddit thread comments into bullet points."
    )
    parser.add_argument("source", help="Reddit thread URL, or a JSON file with --input-file.")
    parser.add_argument(
        "-n",
        "--bullets",
        type=int,
        default=8,
        help="Number of bullet points to print. Default: 8.",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=500,
        help="Maximum comments to summarize after fetching/loading. Default: 500.",
    )
    parser.add_argument(
        "--max-bullet-chars",
        type=int,
        default=180,
        help="Maximum characters per bullet. Default: 180.",
    )
    parser.add_argument(
        "--input-file",
        action="store_true",
        help="Read Reddit JSON from a local file instead of fetching a URL.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.bullets < 1:
        print("Please request at least one bullet.", file=sys.stderr)
        return 2

    try:
        if args.input_file:
            payload = load_input(args.source, args.input_file)
            title, selftext, comments = extract_thread(payload)
        else:
            try:
                payload = load_input(args.source, args.input_file)
                title, selftext, comments = extract_thread(payload)
            except RuntimeError as exc:
                if "Reddit refused this request" not in str(exc):
                    raise
                print(
                    "Reddit blocked the JSON endpoint; trying the web page instead...",
                    file=sys.stderr,
                )
                title, selftext, comments = fetch_thread_from_html(args.source)

        comments = comments[: max(args.max_comments, 1)]
        bullets = summarize(comments, args.bullets, args.max_bullet_chars)
        print_summary(title, selftext, comments, bullets)
    except (OSError, RuntimeError, ValueError, KeyError, IndexError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
