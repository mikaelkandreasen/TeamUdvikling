"""B-041b: rå SQL på team-afgrænsede tabeller skal enten nævne team_id eller stå på den gennemgåede liste (tests/sql_scope_allow.txt).

Ratchet: nye forespørgsler uden team_id fejler, indtil udvikleren har tjekket, at spilleren/kampen kommer fra helpers.get_player()/_get()/active_players()
eller tilsvarende, og tilføjer linjen `fil::funktion::tabel` med en kort begrundelse. Kør `python3 tests/test_sql_scope.py` for at se den aktuelle liste.
"""
import ast
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parent.parent / "app"
ALLOW = pathlib.Path(__file__).with_name("sql_scope_allow.txt")
SCOPED = ("players", "evaluations", "motivation_answers", "motivation_categories", "motivation_questions", "devdata", "player_photos", "conversations",
          "motivation_log", "matches", "match_slots", "lineups", "lineup_slots", "level_ratings", "eval_history", "dbu_checks", "player_links", "wellbeing",
          "att_events", "att_marks", "team_notes", "mascot_log", "team_mascot_img", "team_criteria")
TABLE = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+(" + "|".join(SCOPED) + r")\b", re.I)
SQLISH = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE)\b", re.I)


def found():
    out = set()
    for path in sorted(APP.glob("*.py")):
        if path.name == "db.py":                                         # skema og migrationer
            continue
        tree = ast.parse(path.read_text())
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for node in ast.walk(fn):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and SQLISH.match(node.value):
                    sql = node.value
                    for t in {m.group(1).lower() for m in TABLE.finditer(sql)}:
                        if "team_id" not in sql.lower():
                            out.add(f"{path.name}::{fn.name}::{t}")
    return out


def allowed():
    return {ln.split("#")[0].strip() for ln in ALLOW.read_text().splitlines() if ln.split("#")[0].strip()}


def test_no_new_unscoped_sql_on_team_tables():
    new = sorted(found() - allowed())
    assert not new, ("Ny SQL på team-afgrænsede tabeller uden team_id. Tjek afgrænsningen (get_player/_get/active_players) og tilføj linjerne til "
                     "tests/sql_scope_allow.txt:\n" + "\n".join(new))


def test_allow_list_has_no_stale_entries():
    stale = sorted(allowed() - found())
    assert not stale, "Fjern forældede linjer fra tests/sql_scope_allow.txt:\n" + "\n".join(stale)


if __name__ == "__main__":
    print("\n".join(sorted(found())))
