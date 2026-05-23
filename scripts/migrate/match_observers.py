"""
Match obs_observer names to player IDs using tournament participants.
For each tournament with an obs_observer, searches identified results
for the closest name match (fuzzy, unicode-normalized).
Run with: python3 scripts/migrate/match_observers.py [--dry-run] [--threshold 0.75]
"""
import sys, os, unicodedata, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from difflib import SequenceMatcher
from app.database import SessionLocal
from app.models import Tournament, Result, AnonymousResult, Player


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.strip()


def _particle_forms(last: str, first: str) -> list[str]:
    """
    Reconstruct particle-inversion variants for Dutch names.
    DB stores: last="LINDEN, VAN DER", first="AD"
    Generates:  "ad van der linden", "van der linden ad", etc.
    """
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.75)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        tournois = (
            db.query(Tournament)
            .filter(Tournament.obs_observer.isnot(None))
            .all()
        )
        print(f"Tournaments with observer: {len(tournois)}")

        matched = 0
        ambiguous = 0
        no_match = 0

        for t in tournois:
            obs = t.obs_observer.strip()

            # Score each identified participant
            candidates = []
            results = db.query(Result).filter_by(tournament_id=t.id).all()
            for r in results:
                p = db.query(Player).filter_by(id=r.player_id).first()
                if not p:
                    continue
                score = name_score(obs, p.last_name, p.first_name)
                candidates.append((score, p))

            # Also score anonymous participants with a name (no player_id to store,
            # but a linked Player may exist — skip; just use for threshold check)
            anon_results = db.query(AnonymousResult).filter_by(tournament_id=t.id).all()
            anon_names = [
                (a.last_name or "", a.first_name or "")
                for a in anon_results
                if a.last_name or a.first_name
            ]

            if not candidates and not anon_names:
                no_match += 1
                continue

            candidates.sort(reverse=True, key=lambda x: x[0])

            if not candidates:
                # Only anonymous participants — can't store player_id
                no_match += 1
                continue

            best_score, best_player = candidates[0]

            if best_score < args.threshold:
                # Check if observer matches an anonymous participant
                best_anon_score = 0.0
                best_anon_name = ""
                for last, first in anon_names:
                    s = name_score(obs, last, first)
                    if s > best_anon_score:
                        best_anon_score = s
                        best_anon_name = f"{first} {last}".strip()

                no_match += 1
                hint = f"anon:{best_anon_name}({best_anon_score:.2f})" if best_anon_score >= args.threshold else f"best={best_score:.2f} {best_player.first_name} {best_player.last_name}" if candidates else "no candidates"
                print(f"  NO MATCH  TR{t.ema_id or t.id}: {obs!r}  ({hint})")
                continue

            # Check for ambiguity (two candidates within 0.05 of best)
            close = [p for s, p in candidates[1:4] if s >= best_score - 0.05]
            if close:
                ambiguous += 1
                print(f"  AMBIGUOUS TR{t.ema_id or t.id}: {obs!r}  → {best_player.first_name} {best_player.last_name} ({best_score:.2f}) vs {close[0].first_name} {close[0].last_name}")
                if not args.dry_run:
                    t.obs_player_id = best_player.id  # take best anyway
            else:
                matched += 1
                if not args.dry_run:
                    t.obs_player_id = best_player.id
                if args.dry_run or best_score < 0.92:
                    print(f"  MATCH     TR{t.ema_id or t.id}: {obs!r}  → {best_player.first_name} {best_player.last_name} ({best_score:.2f})")

        if not args.dry_run:
            db.commit()

        print(f"\nDone: {matched} matched, {ambiguous} ambiguous (taken), {no_match} unmatched")
    finally:
        db.close()


if __name__ == "__main__":
    main()
