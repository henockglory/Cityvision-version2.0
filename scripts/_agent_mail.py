#!/usr/bin/env python3
"""Inspect the latest Mailhog messages: subject, key premium fields, evidence links."""
import json
import re
import urllib.request

MAILHOG = "http://localhost:8025"


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


def main():
    d = get(f"{MAILHOG}/api/v2/messages?limit=5")
    print("total mails:", d.get("total"))
    for m in d.get("items", [])[:3]:
        content = m.get("Content", {})
        headers = content.get("Headers", {})
        subj = headers.get("Subject", ["(none)"])[0]
        to = headers.get("To", ["?"])[0]
        body = content.get("Body", "") or ""
        # Mailhog may quote-encode; strip for scanning.
        flat = body.replace("=\r\n", "").replace("\r\n", " ").replace("=3D", "=")
        has_img = ("<img" in flat) or ("cid:" in flat)
        links = re.findall(r'https?://[^\s"\')]+', flat)
        fields = {
            k: (k.lower() in flat.lower())
            for k in ["vitesse", "km/h", "limite", "zone", "plaque", "infraction"]
        }
        print("=" * 60)
        print("SUBJECT:", subj)
        print("TO     :", to)
        print("len    :", len(body), "| has_img:", has_img, "| links:", len(links))
        print("fields :", {k: v for k, v in fields.items() if v})
        print("snippet:", flat[:280])


if __name__ == "__main__":
    main()
