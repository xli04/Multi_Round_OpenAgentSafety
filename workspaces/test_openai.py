#!/usr/bin/env python3
"""
Quick sanity check for the OpenAI Chat Completions endpoint.

Example usage:
    python workspaces/test_openai.py --model gpt-4o-mini

Requires OPENAI_API_KEY to be set.
"""

import argparse
import json
import os
import sys
import time

from openai import OpenAI, APIError, RateLimitError


def run_test(model: str, delay: float, max_retries: int = 5) -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    retries = 0
    last_attempt = 0.0

    while retries < max_retries:
        if delay > 0:
            elapsed = time.time() - last_attempt
            if elapsed < delay:
                time.sleep(delay - elapsed)

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that answers succinctly."
                    },
                    {
                        "role": "user",
                        "content": "Respond with a short JSON greeting containing keys 'message' and 'timestamp'."
                    },
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )

            print(json.dumps(json.loads(resp.choices[0].message.content), indent=2))
            return

        except RateLimitError as err:
            retries += 1
            wait = max(delay, 10 * retries)
            print(f"Rate limited (attempt {retries}/{max_retries}). Waiting {wait}s …", file=sys.stderr)
            time.sleep(wait)

        except APIError as err:
            retries += 1
            wait = max(delay, 5)
            print(f"API error {err} (attempt {retries}/{max_retries}). Waiting {wait}s …", file=sys.stderr)
            time.sleep(wait)

        except Exception as err:
            print(f"Unexpected error: {err}", file=sys.stderr)
            sys.exit(1)

        finally:
            last_attempt = time.time()

    print("Failed to get a successful response after retries.", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple OpenAI API connectivity test.")
    parser.add_argument("--model", default="gpt-4o", help="Model name to test (default: gpt-4o)")
    parser.add_argument("--delay", type=float, default=0.0, help="Optional delay between retries (seconds)")
    args = parser.parse_args()

    run_test(model=args.model, delay=max(0.0, args.delay))


if __name__ == "__main__":
    main()
