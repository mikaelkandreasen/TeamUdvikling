import re

from conftest import Client, PW


def make_team(admin, name):
    return admin.post("/admin/teams", {"name": name}, page="/admin/teams")


def team_id(app, name):
    from app import db
    con = db.connect(app.config["DATABASE"])
    r = con.execute("SELECT id FROM teams WHERE name=?", (name,)).fetchone()
    con.close()
    return r["id"]


def switch(c, tid):
    return c.post("/switch-team", {"team_id": tid}, page="/")


def add_player(c, name, birth="2016-03-10", pos="Angreb", pos2="", active=True):
    data = {"name": name, "birth_date": birth, "position": pos, "position2": pos2}
    if active:
        data["active"] = "1"
    return c.post("/players/new", data, page="/players/new")


def player_id(app, name):
    from app import db
    con = db.connect(app.config["DATABASE"])
    r = con.execute("SELECT id FROM players WHERE name=?", (name,)).fetchone()
    con.close()
    return r["id"]


def make_trainer(app, admin, username, team_names, email=None):
    ids = [str(team_id(app, n)) for n in team_names]
    r = admin.c.post("/admin/users", data={"username": username, "display_name": username.title(), "role": "trainer",
                                           "teams": ids, "csrf_token": admin.token("/admin/users"), **({"email": email} if email else {})})
    temp = re.search(r'class="secret">([^<]+)<', r.get_data(as_text=True)).group(1)
    c = Client(app)
    c.login(username, temp)                        # temp pw → 2FA-opsætning (gemmer c.secret)
    c.post("/account/password", {"new": PW, "new2": PW}, page="/account/password")
    return c


def score_all(c, rnd, pid, value, page=None):
    data = {f"c{i}": str(value) for i in range(24)}
    return c.post(f"/eval/{rnd}/{pid}", data, page=page or f"/eval/{rnd}/{pid}")
