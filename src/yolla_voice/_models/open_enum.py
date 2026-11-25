from enum import Enum
from typing import Self


class OpenEnum(str, Enum):
    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        if not isinstance(value, str):
            return None
        member = str.__new__(cls, value)
        member._name_ = value
        member._value_ = value
        return member

    def __str__(self) -> str:
        return self.value
