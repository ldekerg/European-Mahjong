"""
Backfill observer reports for tournaments already in the database.
Fetches each TR_ page, extracts observer name + PDF link, downloads PDF.
Run with: python3 scripts/importers/import_obs_reports.py [--force]
  --force : re-download even if obs_report_path already set
"""
import sys, os, re, time, argparse, ssl, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.database import SessionLocal
from app.models import Tournament

import re as _re
from bs4 import BeautifulSoup

BASE_URL = "http://mahjong-europe.org/ranking/Tournament/{}_{}.html"
OBS_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "../../app/static/obs_reports")
OBS_BASE_URL = "http://mahjong-europe.org/ranking/reports/"

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE


def fetch_page(tournament_id, prefix: str = "TR") -> str | None:
    url = BASE_URL.format(prefix, tournament_id)
    try:
        with urllib.request.urlopen(url, context=ssl_ctx, timeout=10) as r:
            raw = r.read()
        for encoding in ("utf-8", "windows-1252", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("latin-1", errors="replace")
    except Exception as e:
        print(f"  [WARN] Could not fetch {url}: {e}")
        return None


def _download_obs_report(pdf_filename: str, ema_id: int | None) -> str | None:
    os.makedirs(OBS_REPORTS_DIR, exist_ok=True)
    local_name = f"TR{ema_id}_{pdf_filename}" if ema_id else pdf_filename
    local_path = os.path.join(OBS_REPORTS_DIR, local_name)
    if not os.path.exists(local_path):
        url = OBS_BASE_URL + pdf_filename
        try:
            with urllib.request.urlopen(url, context=ssl_ctx, timeout=15) as r:
                with open(local_path, "wb") as f:
                    f.write(r.read())
        except Exception as e:
            print(f"  [WARN] Could not download {url}: {e}")
            return None
    return f"/static/obs_reports/{local_name}"


def extract_obs(html: str) -> tuple[str | None, str | None]:
    """Return (pdf_filename, observer_name) or (None, None)."""
    soup = BeautifulSoup(html, "html.parser")
    obs_h3 = soup.find("h3", string=_re.compile(r"EMA Observer", _re.I))
    if not obs_h3:
        return None, None
    next_text = obs_h3.next_sibling
    observer = None
    if next_text:
        raw = str(next_text).strip().removeprefix("EMA Observer :").strip()
        observer = raw if raw and raw != "-" else None
    pdf_a = obs_h3.find_next("a", href=_re.compile(r"reports/.*\.pdf", _re.I))
    if not pdf_a:
        return None, observer
    href = pdf_a["href"]
    pdf_filename = href.split("reports/")[-1]
    return pdf_filename, observer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Re-download even if already set")
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # Get all tournaments with an ema_id, ordered by ema_id desc (most recent first)
        tournois = (
            db.query(Tournament)
            .filter(Tournament.ema_id.isnot(None))
            .order_by(Tournament.ema_id.desc())
            .all()
        )
        print(f"Found {len(tournois)} tournaments with ema_id")

        updated = 0
        skipped = 0
        no_report = 0

        for t in tournois:
            if not args.force and t.obs_report_path:
                skipped += 1
                continue

            prefix = "TR_RCR" if t.rules == "RCR" else "TR"
            html = fetch_page(t.ema_id, prefix)
            if not html:
                continue

            pdf_filename, observer = extract_obs(html)

            if not pdf_filename:
                no_report += 1
                time.sleep(args.delay)
                continue

            local_path = _download_obs_report(pdf_filename, t.ema_id)
            if local_path:
                t.obs_report_path = local_path
                print(f"  TR{t.ema_id} ({t.rules}): {local_path}")
            if observer:
                t.obs_observer = observer

            db.commit()
            updated += 1
            time.sleep(args.delay)

        print(f"\nDone: {updated} updated, {skipped} already set, {no_report} without report")
    finally:
        db.close()


if __name__ == "__main__":
    main()
