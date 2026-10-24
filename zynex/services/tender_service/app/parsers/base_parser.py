from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ParseResult:
    text: str
    page_count: int
    mime_type: str
    metadata: dict


class BaseParser(ABC):
    @abstractmethod
    async def parse(self, file_bytes: bytes, filename: str) -> ParseResult:
        pass
