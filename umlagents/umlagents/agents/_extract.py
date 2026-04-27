"""Shared LLM-response file extractor used by DeveloperAgent and TesterAgent."""
import re
from typing import Dict


def _strip_fences(text: str) -> str:
    """
    Remove opening/closing code-fence markers from a raw LLM response.
    Handles truncated responses that have an opening fence but no closing one.
    """
    text = text.strip()
    # Remove opening fence line (```python, ```text, etc.)
    text = re.sub(r"^```[a-zA-Z]*\s*\n", "", text)
    # Remove optional leading  # filename.ext  comment line
    text = re.sub(r"^#\s*[\w.-]+\.(?:py|txt|md)[^\n]*\n", "", text)
    # Remove closing fence if present
    text = re.sub(r"\n```\s*$", "", text)
    return text.strip() + "\n"


def _extract_files_from_response(text: str) -> Dict[str, str]:
    """
    Extract named source files from an LLM response.

    Handles the common patterns LLMs produce:
      1. Fenced block whose first line is  # filename.ext [optional description]
         e.g.  ```python\\n# main.py - entry point\\n...```
      2. Markdown heading  ### filename.ext  immediately before a code fence
      3. Fallback: unnamed blocks inferred from content keywords
    """
    files: Dict[str, str] = {}

    # ── Pattern 1: first line of fenced block is a comment with the filename ──
    fenced = re.findall(
        r"```(?:python|text|markdown|)?\s*\n"        # opening fence
        r"#\s*([\w.-]+\.(?:py|txt|md))[^\n]*\n"      # # filename.ext [anything]
        r"(.*?)```",                                  # body up to closing fence
        text,
        re.DOTALL | re.IGNORECASE,
    )
    for filename, body in fenced:
        files[filename] = f"# {filename}\n{body.strip()}\n"

    # ── Pattern 2: ### filename.ext heading before a code block ──────────────
    if not files:
        headed = re.findall(
            r"#{1,4}\s+([\w.-]+\.(?:py|txt|md))\s*\n"
            r"```(?:python|text|markdown|)?\s*\n"
            r"(.*?)```",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        for filename, body in headed:
            files[filename] = body.strip() + "\n"

    # ── Pattern 3: truncated response — opening fence but no closing fence ────
    # Happens when the AI hits the token limit mid-file.
    if not files:
        truncated = re.match(
            r"```(?:python|text|markdown|)?\s*\n"
            r"#\s*([\w.-]+\.(?:py|txt|md))[^\n]*\n"
            r"(.*)",          # greedy — take everything to end of string
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if truncated:
            files[truncated.group(1)] = truncated.group(2).strip() + "\n"

    # ── Fallback: any fenced block, guess filename from content ───────────────
    if not files:
        for i, body in enumerate(
            re.findall(r"```(?:python|text|markdown|)?\s*\n(.*?)```", text, re.DOTALL)
        ):
            first = body.strip().split("\n")[0]
            m = re.match(r"#\s*([\w.-]+\.(?:py|txt|md))", first)
            if m:
                files[m.group(1)] = body.strip() + "\n"
            elif "test" in body.lower():
                files[f"test_module_{i}.py"] = body.strip() + "\n"
            elif "uat" in body.lower() or "checklist" in body.lower():
                files[f"uat_checklist_{i}.md"] = body.strip() + "\n"
            else:
                files[f"module_{i}.py"] = body.strip() + "\n"

    return files
