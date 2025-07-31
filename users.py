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
 	    949507228: "Марьяна Попова"
                  },
        "manager": 949507228
    }
}

USERS = {}
for team in TEAMS.values():
    USERS.update(team["members"])
