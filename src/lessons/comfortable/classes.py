import datetime
from dataclasses import dataclass
from typing import List


# General classes

@dataclass
class LessonSection:
    "Mixin to be used by specific LessonSections"
    pass


@dataclass
class Choice:
    index: str
    value: str


@dataclass
class Question:
    question: str
    type: str
    correct_answers: List[str]
    choices: List[Choice]


@dataclass
class Quiz:
    questions: List[Question]


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
    quiz: Quiz


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
class EnvironmentSection(LessonSection):
    title: str
    video_url: str
    description: str
    updated_at: datetime.datetime
