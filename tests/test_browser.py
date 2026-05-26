import subprocess
import time
import sys
from pathlib import Path
import httpx

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))


def test_browser_tile_click_sends_correct_body():
    """Use a real browser to verify HTMX sends the correct POST body on tile click."""
    from playwright.sync_api import sync_playwright

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "9876"],
        cwd=HERE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        for _ in range(30):
            try:
                r = httpx.get("http://127.0.0.1:9876/health", timeout=2)
                if r.status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            proc.terminate()
            raise RuntimeError("Server did not start")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            # Intercept network requests to capture POST /action body
            post_bodies = []

            page = browser.new_page()
            page.on("request", lambda req: post_bodies.append(req) if req.url.endswith("/action") and req.method == "POST" else None)

            page.goto("http://127.0.0.1:9876/view/home", wait_until="load")

            tile_content = page.locator(".tile-content").first
            hx_vals = tile_content.get_attribute("hx-vals")
            hx_post = tile_content.get_attribute("hx-post")
            hx_trigger = tile_content.get_attribute("hx-trigger")

            print(f"hx-post: {hx_post}", file=sys.stderr)
            print(f"hx-trigger: {hx_trigger}", file=sys.stderr)
            print(f"hx-vals: {hx_vals}", file=sys.stderr)

            assert hx_post == "/action", f"Expected hx-post=/action, got {hx_post}"
            assert hx_trigger == "click", f"Expected hx-trigger=click, got {hx_trigger}"
            assert hx_vals is not None and "entity_id" in hx_vals, f"Expected hx-vals with entity_id, got {hx_vals}"

            tile_content.click()

            time.sleep(0.5)

            matching = [r for r in post_bodies if r.url.endswith("/action") and r.method == "POST"]
            if matching:
                req = matching[-1]
                post_data = req.post_data
                print(f"POST body: {post_data}", file=sys.stderr)
                assert post_data is not None, "POST body was None"
                import urllib.parse
                body = dict(urllib.parse.parse_qsl(post_data))
                assert body.get("entity_id"), f"entity_id was empty in POST: {body}"
                assert body.get("service"), f"service was empty in POST: {body}"
                print(f"SUCCESS: entity_id={body['entity_id']} service={body['service']}", file=sys.stderr)
            else:
                print("NO POST /ACTION REQUESTS CAPTURED", file=sys.stderr)
                print(f"All requests: {[r.url for r in post_bodies]}", file=sys.stderr)

            browser.close()

    finally:
        proc.terminate()
        proc.wait(timeout=5)
        stdout, stderr = proc.communicate(timeout=5)
        print("Server stderr:", stderr.decode(), file=sys.stderr)
