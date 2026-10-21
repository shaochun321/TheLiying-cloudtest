"""Render the v1 dev re-audit JSON as a Markdown table (INFRA). Numbers come only from
audit/v1_dev_raw_audit.json; nothing is typed by hand."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def fmt_events(ev):
    if not ev:
        return "no q vector saved"
    parts = []
    # cells with events first, then silent ones
    for name, lst in sorted(ev.items(), key=lambda kv: (len(kv[1]) == 0, kv[0])):
        if not lst:
            parts.append(f"{name}: 0")
            continue
        first = lst[0]
        down = "null" if first["down_s"] is None else f"{first['down_s']:.4f}"
        parts.append(f"{name}: n={len(lst)}, first up {first['up_s']:.4f} / down {down}")
    return "; ".join(parts[:3]) + ("; ..." if len(parts) > 3 else "")


def main():
    d = json.load(open(os.path.join(HERE, "v1_dev_raw_audit.json"), encoding="utf-8"))
    rows = ["| id | tag | raw | points | x_end | h feedback (deck) | ledger error | q events (VDD/2) |",
            "|---|---|---|---:|---:|---|---|---|"]
    for aid, r in d["runs"].items():
        raw = r.get("raw") or {}
        hrf = r.get("deck", {}).get("hrf_nodes") or []
        # node after the first '_' of the last segment: e.g. 'n0_qb' -> 'qb', 'gw1_e1_ko2' -> 'ko2'
        tgt = sorted({h.split()[1].rsplit("_", 1)[-1] for h in hrf})
        src = sorted({h.split()[0].rsplit("_", 1)[-1] for h in hrf})
        if src == ["thr"]:
            tgt = [t + " (N-P1 thr feedback)" for t in tgt]
        rows.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            aid, r["tag"], ("sha " + r["files"]["raw"]["sha256"][:8]) if r["files"]["raw"] else "absent",
            raw.get("points", "-"), "-" if raw.get("x_end") is None else f"{raw['x_end']:.4g}",
            ("h→" + "/".join(tgt)) if tgt else "-", r["ledger_error"] or "-",
            fmt_events(r.get("q_events")) if "q_events" in r else
            (f"sweep over {raw['x_var']} (no time events)" if raw.get("x_var") not in (None, "time")
             else "no raw")))
    L = d["ledger"]
    rows.append("")
    rows.append(f"Ledger: {L['starts']} starts / {L['ends']} ends, solver wall sum "
                f"{L['solver_wall_s_sum']:.3f} s, sha {L['sha256'][:12]}.")
    print("\n".join(rows))


if __name__ == "__main__":
    main()
