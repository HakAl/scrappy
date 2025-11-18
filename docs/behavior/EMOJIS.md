# Unicode Emoji Blocks and Detection

Unicode defines specific blocks for emoji characters. This distinction makes it straightforward to detect or filter emojis programmatically by checking code point ranges.

### Main Emoji Blocks
- **U+1F600–U+1F64F** - Emoticons
- **U+1F300–U+1F5FF** - Miscellaneous Symbols and Pictographs
- **U+1F680–U+1F6FF** - Transport and Map Symbols
- **U+1F1E0–U+1F1FF** - Regional Indicator Symbols (flags)
- **U+1F900–U+1F9FF** - Supplemental Symbols and Pictographs
- **U+1FA00–U+1FA6F** - Chess Symbols
- **U+1FA70–U+1FAFF** - Symbols and Pictographs Extended-A

### Legacy Symbol Blocks
*Some of these are rendered as emoji depending on the platform.*
- **U+2600–U+26FF** - Miscellaneous Symbols
- **U+2700–U+27BF** - Dingbats
- **U+231A–U+23FF** - Miscellaneous Technical

### Modifiers
- **U+1F3FB–U+1F3FF** - Skin tone modifiers
- **U+FE0F** - Variation Selector-16 (forces emoji rendering)
- **U+200D** - Zero Width Joiner (combines emojis)

The Unicode Consortium maintains an official list at [unicode.org/Public/emoji/](https://unicode.org/Public/emoji/), and each Unicode version adds new emoji to these blocks.

---

## Practical Implementation

`tests/test_no_emojis.py` uses a practical approach using Unicode range checking with static analysis.

```python
import re

def contains_emoji(text: str) -> bool:
    """Check if text contains emoji characters."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Misc Symbols & Pictographs
        "\U0001F680-\U0001F6FF"  # Transport & Map
        "\U0001F1E0-\U0001F1FF"  # Flags (regional indicators)
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols
        "\U0001FA00-\U0001FAFF"  # Extended-A
        "\U00002600-\U000026FF"  # Misc Symbols
        "\U00002700-\U000027BF"  # Dingbats
        "\U0000FE00-\U0000FE0F"  # Variation Selectors
        "\U0000200D"             # Zero Width Joiner
        "]"
    )
    return bool(emoji_pattern.search(text))
```

### Testing CLI Output

This test ensures your application's output remains emoji-free.

```python
def test_cli_output_contains_no_emojis(capsys):
    """Ensure CLI output is emoji-free."""
    # Run your CLI function
    your_cli_function()

    captured = capsys.readouterr()
    output = captured.out + captured.err

    assert not contains_emoji(output), (
        f"CLI output contains emoji characters. "
        f"Found in: {repr(output)}"
    )
```

### Testing Strings Directly

You can also test specific string lists to catch attempts to add emojis like "Success! 🎉" or "Error ❌".

```python
def test_no_emojis_in_messages():
    messages = [
        "Operation complete",
        "Error: file not found",
        "Processing 5 items...",
    ]

    for msg in messages:
        assert not contains_emoji(msg), f"Emoji found in: {msg}"
```