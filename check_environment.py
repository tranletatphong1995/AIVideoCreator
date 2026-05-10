"""Quick environment checker for AIVideoCreator."""

import importlib
import sys


REQUIRED_MODULES = [
    ("PyQt5", "PyQt5"),
    ("ollama", "ollama"),
    ("playwright", "playwright"),
    ("moviepy", "moviepy"),
    ("Pillow", "PIL"),
    ("pydantic", "pydantic"),
    ("requests", "requests"),
    ("vieneu", "vieneu"),
]


def check_imports() -> bool:
    ok = True
    print(f"Python: {sys.version.split()[0]}")
    for package, module_name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "")
            print(f"[OK] {package} {version}".rstrip())
        except Exception as exc:
            ok = False
            print(f"[ERR] {package}: {exc}")
    return ok


def check_playwright_browser() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("[OK] Playwright Chromium")
        return True
    except Exception as exc:
        print(f"[ERR] Playwright Chromium: {exc}")
        print("      Fix: python -m playwright install chromium")
        return False


def check_ollama() -> bool:
    try:
        import ollama

        models = ollama.list().get("models", [])
        if models:
            print(f"[OK] Ollama: {len(models)} model(s) found")
        else:
            print("[WARN] Ollama is reachable, but no models were found")
            print("       Fix: ollama pull qwen2.5-coder")
        return True
    except Exception as exc:
        print(f"[WARN] Ollama is not reachable: {exc}")
        print("       Fix: start Ollama, then run: ollama serve")
        return False


def main() -> int:
    imports_ok = check_imports()
    browser_ok = check_playwright_browser() if imports_ok else False
    check_ollama()

    if imports_ok and browser_ok:
        print("\nEnvironment looks ready.")
        return 0

    print("\nEnvironment is incomplete.")
    print("Install/fix with:")
    print("  python -m pip install -r requirements.txt")
    print("  python -m playwright install chromium")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
