import os

import requests

from lessons.comfortable.classes import Collection, LessonMeta

COMFORTABLE_API_KEY = os.getenv('COMFORTABLE_API_KEY')
COMFORTABLE_API_URL = "https://api.cmft.io/v1/kpma"

HEADERS = {
    "Authorization": COMFORTABLE_API_KEY
}

PARAMS = {
    "embedAssets": True
}


def get_lessons(category: str):
    url = f"{COMFORTABLE_API_URL}/collections/{category}"
    response = requests.get(url=url, params=PARAMS, headers=HEADERS)
    if response.status_code == 200:
        data = response.json()
        collection = parse_collection(raw_collection=data, category=category)
        return collection
    else:
        print(f"ERROR - {response.status_code} - {response.json()}")


def parse_collection(raw_collection: dict, category: str) -> Collection:
    raw_lessons = raw_collection.get('data')
    lessons = []
    for lesson in raw_lessons:
        fields = lesson.get('fields')
        info = fields.get('info')
        meta = lesson.get('meta')
        lesson = LessonMeta(
                id=meta.get('id'),
                title=info.get('title'),
                description=info.get('description'),
                updated_at=meta.get('updatedAt'),
            )
        lessons.append(lesson)

    collection = Collection(
        category=category,
        lessons=lessons
    )

    return collection
