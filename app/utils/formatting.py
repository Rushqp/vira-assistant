"""Converting model output (light Markdown) into Telegram-safe HTML, and splitting long texts."""

import html
import re

# Telegram's limit is 4096 characters; keep headroom for the HTML tags we add.
TELEGRAM_CHUNK = 3500

_CODE_BLOCK = re.compile(r"```(?:[\w+-]*\n)?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def markdown_to_html(text: str) -> str:
    """Escape everything, then turn complete Markdown pairs into tags.

    Only balanced pairs are converted, so a half-streamed answer still yields valid HTML.
    """
    placeholders: list[str] = []

    def stash(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    text = _CODE_BLOCK.sub(lambda m: stash(f"<pre>{html.escape(m[1].strip())}</pre>"), text)
    text = _INLINE_CODE.sub(lambda m: stash(f"<code>{html.escape(m[1])}</code>"), text)
    text = html.escape(text, quote=False)
    text = _HEADING.sub(r"<b>\1</b>", text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m[1])], text)


def split_point(text: str, limit: int = TELEGRAM_CHUNK) -> int:
    """Index where `text` should be cut so the first part fits in `limit` characters.

    Prefers a paragraph break, then a line break, then a space.
    """
    if len(text) <= limit:
        return len(text)
    for sep in ("\n\n", "\n", " "):
        cut = text.rfind(sep, limit // 2, limit)
        if cut != -1:
            return cut + len(sep)
    return limit
