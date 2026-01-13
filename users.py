

# users.py — Telegram users & teams
# chat_id -> ФИО
# Новые chat_id ты добавляешь вручную

TEAMS = {
    1: {
        "team_name": "Отдел развития цифровых каналов и сервисов",
        "tag": "Daily",
        "members": {
            775766895: "Кирилл Востриков",
        },
        "managers": [775766895],
    },
    2: {
        "team_name": "Отдел бизнес-анализа операций на финансовых рынках",
        "tag": "Daily",
        "members": {
        },
        "managers": [775766895],
    },
    3: {
        "team_name": "Отдел бизнес-анализа брокерских операций",
        "tag": "Weekly",
        "members": {
        },
        "managers": [775766895],
    },
    4: {
        "team_name": "Отдел аналитики данных и неторговых операций",
        "tag": "Weekly",
        "members": {

        },
        "managers": [775766895],
    },
}

# Плоский справочник
USERS = {}
for team in TEAMS.values():
    USERS.update(team["members"])