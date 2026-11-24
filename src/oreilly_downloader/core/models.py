from typing import List, Optional, Dict, Any


class Video:
    def __init__(self, title: str, url: str):
        self.title: str = title
        self.url: str = url
        self.m3u8_url: Optional[str] = None
        self.transcript: Optional[str] = None


class Lesson:
    def __init__(self, title: str, videos: Optional[List["Video"]] = None):
        self.title: str = title
        self.videos: List["Video"] = videos or []


class Module:
    def __init__(self, title: str, lessons: Optional[List["Lesson"]] = None):
        self.title: str = title
        self.lessons: List["Lesson"] = lessons or []


class Course:
    def __init__(
        self,
        title: str,
        modules: Optional[List["Module"]] = None,
        structure: Optional[Dict[str, Any]] = None,
    ):
        self.title: str = title
        self.modules: List["Module"] = modules or []
        self.structure: Dict[str, Any] = structure or {}


def build_course(structure: dict, title: str = "OReilly Extracted Course") -> Course:
    """Builds a Course object from the scraped structure dict."""
    course = Course(title=title, modules=[], structure=structure)
    for mod_name, lessons_dict in structure.items():
        module = Module(title=mod_name, lessons=[])
        for lesson_name, videos_list in lessons_dict.items():
            lesson = Lesson(title=lesson_name, videos=[])
            for v_data in videos_list:
                video = Video(title=v_data["title"], url=v_data["url"])
                lesson.videos.append(video)
            module.lessons.append(lesson)
        course.modules.append(module)
    return course
