import datetime
from dataclasses import dataclass
from typing import List


# General classes

@dataclass
class LessonSection:
    pass


@dataclass
class LessonContent:
    introduction: str
    sections: List[LessonSection]


@dataclass
class Lesson:
    id: str
    title: str
    category: str
    description: str
    updated_at: datetime.datetime
    content: LessonContent


@dataclass
class LessonMeta:
    id: str
    title: str
    description: str
    updated_at: datetime.datetime

@dataclass
class Collection:
    category: str
    lessons: List[LessonMeta]


# Specific classes for each lesson type

@dataclass
class ReclamationSection(LessonSection):
    title: str
    video_url: str
