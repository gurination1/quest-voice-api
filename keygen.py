import argparse
import os
import secrets
from datetime import datetime


KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys.txt")


def generate_key() -> str:
    return "neo-" + secrets.token_urlsafe(32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Quest Voice API keys")
    parser.add_argument("--count", type=int, default=1, help="Number of keys to generate")
    parser.add_argument("--label", default="", help="Optional label/comment")
    args = parser.parse_args()

    new_keys = []
    with open(KEYS_FILE, "a", encoding="utf-8") as handle:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        label = f"  # {args.label}" if args.label else ""
        handle.write(f"\n# Generated {timestamp}{label}\n")
        for _ in range(args.count):
            key = generate_key()
            handle.write(key + "\n")
            new_keys.append(key)

    print(f"\n{len(new_keys)} key(s) written to keys.txt\n")
    for key in new_keys:
        print(f"  {key}")
    print("\nRestart proxy.py after updating keys.\n")


if __name__ == "__main__":
    main()
