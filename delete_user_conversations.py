import requests
from dotenv import dotenv_values

# 📦 Загружаем переменные из .env
config = dotenv_values(".env")
API_KEY = config.get("DIFY_API_KEY")
BASE_URL = config.get("DIFY_API_URL").rstrip("/")  # на всякий случай убираем /
TARGET_USER = config.get("TARGET_USER")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

def get_conversations():
    url = f"{BASE_URL}/conversations"
    params = {"user": TARGET_USER}
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json().get("data", [])

def delete_conversation(conv_id):
    url = f"{BASE_URL}/conversations/{conv_id}"
    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        print(f"✅ Удалён диалог {conv_id}")
    else:
        print(f"⚠️ Ошибка при удалении {conv_id} | Статус: {response.status_code}")

def main():
    conversations = get_conversations()
    print(f"🔍 Найдено {len(conversations)} диалог(ов) с пользователем {TARGET_USER}")
    for conv in conversations:
        delete_conversation(conv["id"])

if __name__ == "__main__":
    main()