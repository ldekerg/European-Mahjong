"""
Extract referee names from obs report PDFs and match them to players/referees in DB.
For each tournament with an obs_report_path:
  1. Extract the Referee/Refereeing section from the PDF
  2. Extract candidate names (Title Case / ALL CAPS tokens)
  3. Match against tournament participants (Result + AnonymousResult) AND the referees table
  4. Insert TournamentReferee rows

Run with: python3 scripts/migrate/match_referees_from_pdf.py [--dry-run] [--threshold 0.75]
"""
import sys, os, re, unicodedata, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pypdf
from difflib import SequenceMatcher
from app.database import SessionLocal
from app.models import Tournament, Result, AnonymousResult, Player, Referee, TournamentReferee

OBS_DIR = "app/static/obs_reports"

# Words that appear in referee sentences but are NOT names
STOPWORDS = {
    "was", "were", "is", "are", "the", "a", "an", "as", "and", "or", "of",
    "not", "non", "playing", "player", "referee", "referees", "refereeing",
    "head", "chief", "assisted", "by", "with", "also", "all", "both",
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "in", "at", "for", "from", "total", "served", "did", "great", "job",
    "substitute", "additional", "on", "top", "that", "where", "which",
    "good", "well", "planned", "feature", "seen", "could", "notice",
    "questions", "raised", "none", "no", "there", "had",
    # mahjong terms and geography that appear in referee sections
    "fully", "concealed", "self", "drawn", "digital", "time", "bad",
    "united", "kingdom", "great", "britain",
}


# ── text extraction ─────────────────────────────────────────────────────────

def extract_referee_text(pdf_path: str) -> str | None:
    try:
        reader = pypdf.PdfReader(pdf_path)
        text = " ".join(p.extract_text() or "" for p in reader.pages[:3])
    except Exception:
        return None
    text = re.sub(r"\s+", " ", text)
    text = text.replace("­", "-").replace("​", "")  # soft-hyphen, ZWS
    # Insert space when lowercase is immediately followed by uppercase (PDF merge artifact)
    text = re.sub(r"([a-z\xe0-\xf6\xf8-\xff])([A-Z\xc0-\xd6\xd8-\xde])", r"\1 \2", text)
    m = re.search(
        r"(?:Refereeing|Referee)\s*:\s*(.{5,500}?)"
        r"(?:\s*(?:Complaints|Information|Sessions|Playing|Equipment|Results"
        r"|Participants|Location|Catering|Prizes|Schedule|represented|Website)"
        r"(?:\s*/\s*\w+)?\s*:)",
        text,
        re.I | re.S,
    )
    return m.group(1).strip() if m else None


# ── name extraction ──────────────────────────────────────────────────────────

# Match sequences of capitalised tokens: "John VAN DER Linden", "Sylvain Malbec", "JEAN MICHEL MORISSE"
_NAME_RE = re.compile(
    r"\b([A-ZÁÀÂÄÉÈÊËÍÌÎÏÓÒÔÖÚÙÛÜÝŸÆŒÇÑ][a-záàâäéèêëíìîïóòôöúùûüýÿæœçñ\-']+"
    r"(?:\s+(?:[A-ZÁÀÂÄÉÈÊËÍÌÎÏÓÒÔÖÚÙÛÜÝŸÆŒÇÑ][a-záàâäéèêëíìîïóòôöúùûüýÿæœçñ\-']+|"
    r"[A-ZÁÀÂÄÉÈÊËÍÌÎÏÓÒÔÖÚÙÛÜÝŸÆŒÇÑ]{2,}))+)\b"
)

# Also match ALL-CAPS sequences: "JEAN MICHEL MORISSE"
_ALLCAPS_RE = re.compile(r"\b([A-ZÁÀÂÄÉÈÊËÍÌÎÏÓÒÔÖÚÙÛÜÝŸÆŒÇÑ]{2,}(?:\s+[A-ZÁÀÂÄÉÈÊËÍÌÎÏÓÒÔÖÚÙÛÜÝŸÆŒÇÑ]{2,})+)\b")


def _clean_name(name: str) -> str:
    """Strip trailing junk that got sucked into the match (e.g. 'Axel Eschenburg Complains')."""
    # cut at colon or opening parenthesis
    name = re.split(r"[\:(]", name)[0].strip()
    return name


def extract_name_candidates(text: str) -> list[str]:
    candidates = []
    seen = set()
    for m in _NAME_RE.finditer(text):
        name = _clean_name(m.group(1).strip())
        tokens = name.lower().split()
        if any(t in STOPWORDS for t in tokens):
            continue
        if len(tokens) < 2:
            continue
        # Skip fragments: at least one token must be ≥ 3 chars (avoids "Ad Van")
        if all(len(t) <= 3 for t in tokens):
            continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            candidates.append(name)
    for m in _ALLCAPS_RE.finditer(text):
        name = m.group(1).strip()
        tokens = name.lower().split()
        if any(t in STOPWORDS for t in tokens):
            continue
        if len(tokens) < 2:
            continue
        key = name.lower()
        if key not in seen:
            seen.add(key)
            candidates.append(name)
    # Remove candidates that are a substring of another candidate (e.g. "MATOS LIMA" ⊂ "Sérgio MATOS LIMA")
    def is_substring_of_other(name: str, others: list[str]) -> bool:
        n = normalize(name)
        return any(n != normalize(o) and n in normalize(o) for o in others)

    candidates = [c for c in candidates if not is_substring_of_other(c, candidates)]
    return candidates


# ── name matching (same as match_observers.py) ───────────────────────────────

def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.strip()


def _particle_forms(last: str, first: str) -> list[str]:
    parts = normalize(last).split(",", 1)
    if len(parts) == 2:
        base, particle = parts[0].strip(), parts[1].strip()
        fn = normalize(first)
        return [
            f"{fn} {particle} {base}",
            f"{fn} {base} {particle}",
            f"{particle} {base} {fn}",
            f"{base} {particle} {fn}",
        ]
    return []


def name_score(obs: str, last: str, first: str) -> float:
    obs_n = normalize(obs)
    full_n = normalize(f"{first} {last}")
    full_r = normalize(f"{last} {first}")
    s1 = SequenceMatcher(None, obs_n, full_n).ratio()
    s2 = SequenceMatcher(None, obs_n, full_r).ratio()
    obs_tokens = set(obs_n.split())
    full_tokens = set((full_n + " " + full_r).split())
    token_score = len(obs_tokens & full_tokens) / max(len(obs_tokens), 1)
    best = max(s1, s2, token_score * 0.9)
    for form in _particle_forms(last, first):
        best = max(best, SequenceMatcher(None, obs_n, form).ratio())
    return best


def best_match_player(name: str, players: list[Player], threshold: float):
    best_score, best_player = 0.0, None
    for p in players:
        s = name_score(name, p.last_name, p.first_name)
        if s > best_score:
            best_score, best_player = s, p
    if best_score >= threshold:
        return best_player, best_score
    return None, best_score


def best_match_referee(name: str, referees: list[Referee], threshold: float):
    best_score, best_ref = 0.0, None
    for r in referees:
        # Referee.name is a raw string e.g. "Anton Kösters"
        s = SequenceMatcher(None, normalize(name), normalize(r.name)).ratio()
        # also token overlap
        obs_t = set(normalize(name).split())
        ref_t = set(normalize(r.name).split())
        tok = len(obs_t & ref_t) / max(len(obs_t), 1)
        s = max(s, tok * 0.9)
        if s > best_score:
            best_score, best_ref = s, r
    if best_score >= threshold:
        return best_ref, best_score
    return None, best_score


# ── manual overrides (obs_report filename → list of name strings) ────────────
# Use when PDF extraction produces wrong/incomplete names for a specific tournament.
# Key = basename of the PDF file (unique per tournament).
MANUAL_OVERRIDES: dict[str, list[str]] = {
    "TR47_20121208_poland.pdf":    ["Dominik Kolenda", "Jakub Tomaszewski", "Szymon Lasota"],
    "TR58_20130706_Windsor.pdf":   ["Janco Onnink", "Ans Hoogland", "Axel Eschenburg"],
    "TR175_20140706_5OEMC.pdf":    ["Lionel Legaie", "Martial Regnault", "Alexandre Martin", "Anne Schäfer", "Norbert Szamboki"],
    "TR226_20190406_ned.pdf":      ["Jose Manuel Merino"],  # anonymous player → FREE-TEXT
    "TR330_20240510_ned.pdf":      ["Pieter Potmeers", "Jacqueline Oudshoorn", "Ivar Bouwman", "Martijn Gulmans"],
    "TR344_20240810_ire.pdf":      ["Maksym Ivanov", "Jacqueline Oudshoorn", "Martin Lester", "Ben Thomas"],
    "TR349_20240928_aut.pdf":      ["Peter Hamilton", "Lena Weinguny", "Manuel Kameda-Schlich"],
    "TR392_20251025_uk.pdf":       ["Tom Pearson", "James Johns", "Martin Lester"],
    "TR442_20251130_reu.pdf":      ["Jean-Michel Morisse"],
}


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--force", action="store_true", help="Re-process tournaments that already have referee_assignments")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        tournois = (
            db.query(Tournament)
            .filter(Tournament.obs_report_path.isnot(None))
            .all()
        )
        print(f"Tournaments with obs report: {len(tournois)}")

        total_inserted = 0
        total_skipped = 0
        total_no_text = 0
        total_no_names = 0

        for t in tournois:
            if t.referee_assignments and not args.force:
                total_skipped += 1
                continue

            pdf_path = os.path.join("app/static", t.obs_report_path.lstrip("/static/"))
            if not os.path.exists(pdf_path):
                pdf_path = t.obs_report_path.lstrip("/")
                if not os.path.exists(pdf_path):
                    continue

            pdf_basename = os.path.basename(pdf_path)
            from_override = False
            if pdf_basename in MANUAL_OVERRIDES:
                candidates = MANUAL_OVERRIDES[pdf_basename]
                from_override = True
                print(f"  OVERRIDE  TR{t.ema_id or t.id}: {candidates}")
            else:
                ref_text = extract_referee_text(pdf_path)
                if not ref_text:
                    total_no_text += 1
                    continue

                candidates = extract_name_candidates(ref_text)
                if not candidates:
                    total_no_names += 1
                    print(f"  NO NAMES  TR{t.ema_id or t.id}: {ref_text!r}")
                    continue

            # Build pool: identified players in this tournament
            results = db.query(Result).filter_by(tournament_id=t.id).all()
            players = [db.query(Player).filter_by(id=r.player_id).first() for r in results]
            players = [p for p in players if p]

            # All referees in DB
            all_refs = db.query(Referee).all()
            # All players in DB (for non-participant referees) — loaded once per tournament
            all_players = db.query(Player).all()

            for name in candidates:
                # 1. Try certified referee table first
                ref, rscore = best_match_referee(name, all_refs, args.threshold)
                if ref:
                    print(f"  REF-CERT  TR{t.ema_id or t.id}: {name!r} → referee#{ref.id} {ref.name!r} ({rscore:.2f})")
                    if not args.dry_run:
                        existing = db.query(TournamentReferee).filter_by(
                            tournament_id=t.id, referee_id=ref.id
                        ).first()
                        if not existing:
                            db.add(TournamentReferee(
                                tournament_id=t.id,
                                referee_id=ref.id,
                                player_id=ref.player_id,
                                name=name,
                            ))
                            total_inserted += 1
                    continue

                # 2. Try tournament participants (skip for overrides — names are already correct)
                if from_override:
                    player, pscore = None, 0.0
                else:
                    player, pscore = best_match_player(name, players, args.threshold)
                if player:
                    print(f"  PLAYER    TR{t.ema_id or t.id}: {name!r} → {player.first_name} {player.last_name} ({pscore:.2f})")
                    if not args.dry_run:
                        existing = db.query(TournamentReferee).filter_by(
                            tournament_id=t.id, player_id=player.id
                        ).first()
                        if not existing:
                            db.add(TournamentReferee(
                                tournament_id=t.id,
                                referee_id=None,
                                player_id=player.id,
                                name=name,
                            ))
                            total_inserted += 1
                    continue

                # 3. Try all players (non-participant referees) — stricter threshold to avoid false positives
                all_player, ascore = best_match_player(name, all_players, max(args.threshold, 0.80))
                if all_player:
                    print(f"  ALL-PLAYER TR{t.ema_id or t.id}: {name!r} → {all_player.first_name} {all_player.last_name} ({ascore:.2f})")
                    if not args.dry_run:
                        existing = db.query(TournamentReferee).filter_by(
                            tournament_id=t.id, player_id=all_player.id
                        ).first()
                        if not existing:
                            db.add(TournamentReferee(
                                tournament_id=t.id,
                                referee_id=None,
                                player_id=all_player.id,
                                name=name,
                            ))
                            total_inserted += 1
                    continue

                # 4. Free text — no match anywhere
                print(f"  FREE-TEXT TR{t.ema_id or t.id}: {name!r}  (ref_best={rscore:.2f}, pl_best={pscore:.2f})")
                if not args.dry_run:
                    existing = db.query(TournamentReferee).filter_by(
                        tournament_id=t.id, name=name
                    ).first()
                    if not existing:
                        db.add(TournamentReferee(
                            tournament_id=t.id,
                            referee_id=None,
                            player_id=None,
                            name=name,
                        ))
                        total_inserted += 1

        if not args.dry_run:
            db.commit()

        print(f"\nDone: {total_inserted} inserted, {total_skipped} skipped (already have referees), "
              f"{total_no_text} no PDF text, {total_no_names} no names extracted")
    finally:
        db.close()


if __name__ == "__main__":
    main()
