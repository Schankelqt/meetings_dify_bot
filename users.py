# users.py

TEAMS = {
    1: {
        "members": {
            775766895: "Кирилл Востриков"
        },
        "manager": 775766895
    },
    2: {
        "members": {
            949507228: "Марьяна Дмитриевская"
        },
        "manager": 775766895
    }
}

USERS = {}
for team in TEAMS.values():
    USERS.update(team["members"])