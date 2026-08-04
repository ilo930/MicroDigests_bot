#!/usr/bin/env python3
"""Checks the two landing pages are intact and correctly wired.

Run it after any change to the site:

    python3 site/verify_pages.py

It reads the files; it does not open a browser. So it catches a page that is
broken (missing stylesheet, mascot gone, half-applied edit) but not a page that
merely looks wrong. Anything visual still needs your eyes.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(HERE, "versions")

# What each page must have to be considered working, in plain terms.
# Each page loads the shared page design, then its own mascot on top.
MASCOT_SHEET = {"framed": "mascot-01-shy",
                "framed-mascot02": "mascot-02-grumpy"}

CHECKS = [
    ("it uses the shared page design", lambda h, n: 'href="page.css"' in h),
    ("its own mascot is linked",      lambda h, n: f'href="{MASCOT_SHEET[n]}.css"' in h),
    ("the page loads before the mascot",
     lambda h, n: h.index('href="page.css"') < h.index(f'href="{MASCOT_SHEET[n]}.css"')),
    ("its script is linked",          lambda h, n: f'src="{n}.js"' in h),
    ("the mascot is drawn",           lambda h, n: h.count("<rect") > 40),
    ("the mascot can blink",          lambda h, n: 'class="eye"' in h),
    ("the mascot can look around",    lambda h, n: 'class="gaze"' in h),
    ("the mascot has its tail",       lambda h, n: 'class="tail"' in h),
    ("the coffee cup is there",       lambda h, n: 'class="mug"' in h),
    ("the coffee link points out",    lambda h, n: "buymeacoffee.com" in h),
    ("the six scenes are present",    lambda h, n: h.count('class="scene') == 6),
    ("the digest is shown in a phone",lambda h, n: 'class="post"' in h),
    ("no half-applied edit left",     lambda h, n: "@@" not in h),
]

CSS_CHECKS = [
    ("the frame is fixed in place",   lambda c: ".frame{position:fixed" in c),
    ("the palette is a set of tokens",lambda c: c.count("--btn-") >= 6),
]

JS_CHECKS = [
    ("scroll drives the scenes",      lambda j: "function frame()" in j),
    ("the cup swings on its own",     lambda j: "Math.sin" in j),
]


def read(path):
    if not os.path.exists(path):
        return None
    return open(path, encoding="utf-8").read()


def check_page(name):
    """Returns (passed, failed, missing_files) for one page."""
    html = read(os.path.join(PAGES, name + ".html"))
    page_css = read(os.path.join(PAGES, "page.css"))
    mascot_css = read(os.path.join(PAGES, MASCOT_SHEET[name] + ".css"))
    js = read(os.path.join(PAGES, name + ".js"))

    missing = [f for f, src in ((name + ".html", html),
                                ("page.css", page_css),
                                (MASCOT_SHEET[name] + ".css", mascot_css),
                                (name + ".js", js)) if src is None]
    css = (page_css or "") + (mascot_css or "")
    if missing:
        return [], [], missing

    passed, failed = [], []
    for label, test in CHECKS:
        (passed if test(html, name) else failed).append(label)
    for label, test in CSS_CHECKS:
        (passed if test(css) else failed).append(label)
    for label, test in JS_CHECKS:
        (passed if test(js) else failed).append(label)

    # The dice runs inline in the page head so it can beat the first paint.
    dice = len(re.findall(r"mint|gum|lilac", html)) >= 3
    (passed if dice else failed).append("the palette dice has its three colours")
    return passed, failed, []


def main():
    names = ["framed", "framed-mascot02"]
    labels = {"framed": "Page 1 — cute mouse",
              "framed-mascot02": "Page 2 — grumpy mouse"}
    broken = 0

    for name in names:
        passed, failed, missing = check_page(name)
        print(f"\n{labels[name]}  ({name})")
        if missing:
            print("  MISSING FILES: " + ", ".join(missing))
            broken += 1
            continue
        for label in passed:
            print(f"  ok    {label}")
        for label in failed:
            print(f"  BROKEN  {label}")
        broken += len(failed)

    # site/index.html is the front door: it forwards to the chosen version.
    # If it ever points at a page that no longer exists, anything showing the
    # site (a browser, the dashboard preview) silently shows the wrong thing.
    front = read(os.path.join(HERE, "index.html"))
    target = re.search(r'url=([^"\s>]+)', front or "")
    if not front:
        print("\nFront door: MISSING — site/index.html is gone")
        broken += 1
    elif not target:
        print("\nFront door: BROKEN — site/index.html forwards nowhere")
        broken += 1
    elif not os.path.exists(os.path.join(HERE, target.group(1))):
        print(f"\nFront door: BROKEN — it points at {target.group(1)}, "
              "which does not exist")
        broken += 1
    else:
        print(f"\nFront door: opening site/ shows {target.group(1)}")

    # The mascots are kept separately so either page can be rebuilt from them.
    saved = os.path.join(PAGES, "_mascots")
    kept = sorted(os.listdir(saved)) if os.path.isdir(saved) else []
    print(f"\nSaved mascots: {', '.join(kept) if kept else 'NONE — these are the masters'}")
    if len(kept) < 2:
        broken += 1

    print()
    if broken:
        print(f"{broken} thing(s) need attention. Nothing was changed.")
        sys.exit(1)
    print("Both pages are intact. Everything the pages need is present and wired.")
    print("This does not check how they look — open them to judge that.")


if __name__ == "__main__":
    main()
