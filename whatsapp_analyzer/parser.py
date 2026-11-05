import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator


# Soporta formatos frecuentes: 15/10/2026, 14:32 - Nombre: mensaje
# y 15/10/26, 14:32 - Nombre: mensaje. También acepta -, / y .
HEADER = re.compile(
    r"^\[?(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)(?:\s?(?P<ampm>[APap][Mm]))?\s*"
    r"\]?\s*(?:[-–]\s*)?(?P<body>.*)$"
)


@dataclass
class Message:
    date: str
    time: str
    contact: str
    text: str


def parse_datetime(date_text: str, time_text: str, ampm: str | None) -> datetime:
    parts = re.split(r"[./-]", date_text)
    # Las exportaciones más habituales son día/mes/año. Si el primer valor
    # supera 12, también se puede interpretar sin ambigüedad.
    first, second, year = (int(value) for value in parts)
    if len(parts[0]) == 4:
        year, month, day = first, second, int(parts[2])
    else:
        # WhatsApp puede exportar MM/DD/YY según la configuración regional.
        # En fechas ambiguas (ambos valores <= 12) se conserva el formato
        # habitual en español: DD/MM/YY.
        if ampm:
            # En las exportaciones con AM/PM suele usarse MM/DD/YY.
            month, day = first, second
        elif first > 12:
            day, month = first, second
        elif second > 12:
            month, day = first, second
        else:
            day, month = first, second
        year = year + 2000 if year < 100 else year

    hour, minute, *seconds = (int(value) for value in time_text.split(":"))
    second = seconds[0] if seconds else 0
    if ampm:
        if ampm.lower() == "pm" and hour != 12:
            hour += 12
        elif ampm.lower() == "am" and hour == 12:
            hour = 0
    return datetime(year, month, day, hour, minute, second)


def iter_messages(path: str | Path, encoding: str = "utf-8") -> Iterator[Message]:
    """Lee un exportado sin cargarlo completo en memoria.

    Las líneas que no empiezan con una fecha se consideran continuación del
    mensaje anterior, algo habitual cuando el texto contiene saltos de línea.
    """
    current: Message | None = None
    with open(path, "r", encoding=encoding, errors="replace") as file:
        for raw_line in file:
            line = raw_line.rstrip("\r\n")
            match = HEADER.match(line)
            if match:
                if current:
                    yield current
                try:
                    timestamp = parse_datetime(
                        match["date"], match["time"], match["ampm"]
                    )
                except ValueError:
                    current = None
                    continue
                body = match["body"]
                if ": " in body:
                    contact, text = body.split(": ", 1)
                else:
                    contact, text = "Sistema", body
                current = Message(
                    timestamp.strftime("%Y-%m-%d"),
                    timestamp.strftime("%H:%M:%S"),
                    contact.strip(),
                    text,
                )
            elif current and line:
                current.text += "\n" + line
        if current:
            yield current
