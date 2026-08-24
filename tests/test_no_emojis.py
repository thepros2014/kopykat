import os
import re
import pytest

emoji_pattern = re.compile(
    r"[\U0001F600-\U0001F64F"  # emoticons
    r"\U0001F300-\U0001F5FF"  # symbols & pictographs
    r"\U0001F680-\U0001F6FF"  # transport & map symbols
    r"\U0001F1E0-\U0001F1FF"  # flags (iOS)
    r"\U0001F900-\U0001F9FF"  # supplemental symbols
    r"\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
    r"\U00002702-\U000027B0"  # dingbats
    r"\U000024C2-\U0001F251"
    r"\U00002600-\U000026FF"  # miscellaneous symbols
    r"\U00002B50"              # star
    r"\U0000FE0F"              # variation selector-16
    r"\ufffd"                  # replacement character
    r"]+",
    flags=re.UNICODE
)

def test_zero_emojis_in_codebase():
    """Permanent regression test: Ensures zero emojis exist in server and frontend files."""
    extensions_to_check = {'.html', '.py', '.js', '.css', '.json'}
    found_emojis = []
    
    for check_dir in ['server', 'frontend']:
        if not os.path.exists(check_dir):
            continue
        for root, dirnames, files in os.walk(check_dir):
            # Dependency/build trees are not project source and may carry
            # localized diagnostics or box-drawing characters.
            dirnames[:] = [d for d in dirnames if d not in {"node_modules", "dist", "__pycache__"}]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in extensions_to_check:
                    filepath = os.path.join(root, file)
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        matches = emoji_pattern.findall(content)
                        if matches:
                            found_emojis.append((filepath, matches))
                            
    assert len(found_emojis) == 0, f"Found emojis in codebase: {found_emojis}"
