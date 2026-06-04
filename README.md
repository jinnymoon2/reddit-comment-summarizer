# Reddit Comment Summarizer

A small terminal program that reads a Reddit thread and summarizes the comments as bullet points.

## Run it

```bash
python3 reddit_comment_summarizer.py "https://www.reddit.com/r/Python/comments/example/thread_title/"
```

## Options

```bash
python3 reddit_comment_summarizer.py SOURCE --bullets 5 --max-comments 300 --max-bullet-chars 160
```

- `SOURCE`: a Reddit thread URL, or a local Reddit JSON file when using `--input-file`
- `--bullets`: number of bullet points to print
- `--max-comments`: maximum number of comments to summarize
- `--max-bullet-chars`: maximum length for each bullet
- `--input-file`: read from a local JSON file instead of fetching Reddit

## Notes

The summarizer is local and extractive: it chooses representative sentences from comments instead of sending text to an AI service. Live Reddit fetching first tries Reddit's public JSON endpoint. If Reddit blocks that endpoint, the tool automatically retries through Reddit's web-page comment loader.
