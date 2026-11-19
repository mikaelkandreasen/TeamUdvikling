"""Opstillinger, pladser, positionsmatch og holdforslag (rene funktioner)."""
import itertools
import random

import pytest

from app import formations as f
from app import model


def test_every_formation_has_the_right_number_of_players():
    for gt, formations in f.FORMATIONS.items():
        assert gt in f.GAME_TYPES and f.DEFAULT_FORMATION[gt] in formations and f.is_valid(gt, f.DEFAULT_FORMATION[gt])
        for name, lines in formations.items():
            n = sum(len(line) for line in lines)
            assert n == f.GAME_TYPES[gt], (gt, name)
            outfield = n - (0 if gt == "3v3" else 1)
            assert sum(int(x) for x in name.split("-")) == outfield, (gt, name)         # navnet passer til linjerne
            tags = [t for line in lines for t in line]
            assert all(t in model.POSITIONS for t in tags), (gt, name)                    # pladserne bruger dropdown-positionerne
            assert (tags.count(f.GK) == 1) == (gt != "3v3"), (gt, name)                    # 3v3 har ingen målmand


def test_slots_layout_is_sane():
    for gt, formations in f.FORMATIONS.items():
        for name in formations:
            sl = f.slots(gt, name)
            assert [s["i"] for s in sl] == list(range(f.GAME_TYPES[gt]))
            assert all(0 <= s["x"] <= 100 and 0 <= s["y"] <= 100 for s in sl)
            assert len({(s["x"], s["y"]) for s in sl}) == len(sl)                          # ingen to pladser oven i hinanden
            for line in set(s["line"] for s in sl):
                xs = [s["x"] for s in sl if s["line"] == line]
                assert xs == sorted(xs)                                                    # venstre mod højre
            ys = [next(s["y"] for s in sl if s["line"] == li) for li in range(len(set(s["line"] for s in sl)))]
            assert ys == sorted(ys, reverse=True)                                          # bagfra og frem (y falder)
    sl = f.slots("8v8", "3-3-1")
    assert [s["tag"] for s in sl][:4] == ["Målmand", "Venstre back", "Midtstopper", "Højre back"]
    assert sl[1]["x"] < sl[2]["x"] < sl[3]["x"]                                            # venstre back til venstre i billedet


def test_wing_sides_exist_in_formations():
    tags = {t for gt in f.FORMATIONS.values() for lines in gt.values() for line in lines for t in line}
    assert {"Højre kant", "Venstre kant", "Højre back", "Venstre back"} <= tags
    assert {"Kant", "Højre kant", "Venstre kant"} <= set(model.POSITIONS)


@pytest.mark.parametrize("pos,tag,expected", [
    ("Angreb", "Angreb", 100), ("Højre kant", "Højre kant", 100),
    ("Kant", "Højre kant", 90), ("Højre kant", "Kant", 90), ("Højre kant", "Venstre kant", 60),
    ("Forsvar", "Højre back", 80), ("Højre back", "Forsvar", 85), ("Højre back", "Venstre back", 60),
    ("Midtbane", "Defensiv midtbane", 80), ("Offensiv midtbane", "Midtbane", 85),
    ("Allround", "Angreb", 55), ("Allround", "Målmand", 5), ("Målmand", "Angreb", 0), ("Angreb", "Målmand", 0),
    ("Højre kant", "Angreb", 40), ("Midtbane", "Højre kant", 40), ("Forsvar", "Angreb", 0), ("", "Angreb", 0),
])
def test_affinity(pos, tag, expected):
    assert f.affinity(pos, tag) == expected


def test_fit_uses_best_of_four_choices_with_small_penalty():
    assert f.fit(["Angreb", "Højre kant"], "Angreb") == 100
    assert f.fit(["Angreb", "Højre kant"], "Højre kant") == 94
    assert f.fit(["", "Midtbane", "", "Højre kant"], "Højre kant") == 100 - 6 * 1        # tomme valg springes over
    assert f.fit(["Midtbane", "Forsvar", "Kant", "Højre kant"], "Højre kant") == max(90 - 12, 100 - 18)
    assert f.fit([], "Angreb") == 0
    assert f.choice_no(["Angreb", "Højre kant"], "Højre kant") == 2 and f.choice_no(["Angreb"], "Forsvar") is None


def test_hungarian_matches_brute_force():
    rnd = random.Random(7)
    for rows, cols in ((4, 4), (3, 6), (6, 3), (5, 5), (1, 4), (4, 1)):
        for _ in range(15):
            v = [[rnd.randint(0, 100) for _c in range(cols)] for _r in range(rows)]
            got = f.best_assignment(v)
            assert len(got) == min(rows, cols) and len(set(got.values())) == len(got)
            total = sum(v[r][c] for r, c in got.items())
            k = min(rows, cols)
            best = max(sum(v[r][c] for r, c in zip(rs, cs))
                       for rs in itertools.combinations(range(rows), k) for cs in itertools.permutations(range(cols), k))
            assert total == best


def _players():
    pos = {1: ["Målmand"], 2: ["Venstre back"], 3: ["Midtstopper"], 4: ["Højre back"], 5: ["Venstre kant"], 6: ["Midtbane"],
           7: ["Højre kant"], 8: ["Angreb"], 9: ["Allround"], 10: ["Forsvar"]}
    return [dict(id=i, positions=p) for i, p in pos.items()]


def test_suggest_puts_players_on_their_positions():
    sl = f.slots("8v8", "3-3-1")
    got = f.suggest(sl, _players())
    assert [got[i] for i in range(8)] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(set(got.values())) == len(got)


def test_suggest_with_few_players_leaves_slots_empty_and_never_duplicates():
    sl = f.slots("11v11", "4-3-3")
    got = f.suggest(sl, _players()[:6])
    assert len(got) == 6 and len(set(got.values())) == 6 and set(got) <= set(range(11))
    assert f.suggest(sl, []) == {} and f.suggest([], _players()) == {}


def test_suggest_scores_break_ties_but_position_still_matters():
    sl = f.slots("5v5", "2-2")
    players = [dict(id=1, positions=["Angreb"]), dict(id=2, positions=["Angreb"]), dict(id=3, positions=["Angreb"]),
               dict(id=4, positions=["Venstre back"]), dict(id=5, positions=["Højre back"]), dict(id=6, positions=["Målmand"])]
    plain = f.suggest(sl, players)
    assert plain[0] == 6 and plain[1] == 4 and plain[2] == 5                                  # målmand, backs
    scored = f.suggest(sl, players, {1: 2.0, 2: 4.5, 3: 4.0})
    assert {scored[3], scored[4]} == {2, 3}                                                    # de to bedste angribere spiller
    assert f.suggest(sl, players, {1: 2.0, 2: 4.5, 3: 4.0}) == scored                         # deterministisk
