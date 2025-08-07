# users.py

TEAMS = {
    1:  {
        "members": {
            775766895: "Кирилл Востриков"
        },
        "managers": [775766895]
    },
    2: {
        "members": {
            8134384275: "Кирилл"
        },
        "managers": [8134384275]
    }
}

USERS = {}
for team in TEAMS.values():
    USERS.update(team["members"])