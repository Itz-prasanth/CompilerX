from .c import CAdapter
from .cpp import CppAdapter
from .java import JavaAdapter
from .python import PythonAdapter

_ADAPTERS = {"c": CAdapter(), "cpp": CppAdapter(), "java": JavaAdapter(), "python": PythonAdapter()}


def get_adapter(language: str):
    try:
        return _ADAPTERS[language]
    except KeyError:
        raise ValueError(f"unsupported language: {language!r}; choose one of {sorted(_ADAPTERS)}")


def all_adapters():
    return dict(_ADAPTERS)
