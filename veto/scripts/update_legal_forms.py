from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

GLEIF_PAGE = "https://www.gleif.org/en/about-lei/iso-20275-entity-legal-forms-code-list"
CSV_LINK_PATTERN = re.compile(r'href="([^"]+elf-code-list-v[^"]+\.csv)"')
COUNTRY_CODES = {
    "AT": "AT",
    "BE": "BE",
    "BG": "BG",
    "CY": "CY",
    "CZ": "CZ",
    "DE": "DE",
    "DK": "DK",
    "EE": "EE",
    "ES": "ES",
    "FI": "FI",
    "FR": "FR",
    "GB": "XI",
    "GR": "EL",
    "HR": "HR",
    "HU": "HU",
    "IE": "IE",
    "IT": "IT",
    "LT": "LT",
    "LU": "LU",
    "LV": "LV",
    "MT": "MT",
    "NL": "NL",
    "PL": "PL",
    "PT": "PT",
    "RO": "RO",
    "SE": "SE",
    "SI": "SI",
    "SK": "SK",
}
FORM_FIELDS = (
    "Entity Legal Form name Local name",
    "Entity Legal Form name Transliterated name (per ISO 01-140-10)",
    "Abbreviations Local language",
    "Abbreviations transliterated",
)


class LegalFormsUpdateError(RuntimeError):
    pass


def normalize_form(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(
        "".join(
            character if character.isalnum() else " " for character in without_marks
        )
        .casefold()
        .split()
    )


def fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": "veto-skill/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except (OSError, TimeoutError, UnicodeDecodeError) as error:
        raise LegalFormsUpdateError(str(error)) from error


def current_csv_url(page: str) -> str:
    links = CSV_LINK_PATTERN.findall(page)
    if not links:
        raise LegalFormsUpdateError("GLEIF CSV link not found")
    return urljoin(GLEIF_PAGE, links[-1])


def extract_forms(csv_text: str) -> dict[str, set[str]]:
    forms = {country: set[str]() for country in COUNTRY_CODES.values()}
    for row in csv.DictReader(io.StringIO(csv_text)):
        source_country = row["Country Code (ISO 3166-1)"]
        if row["ELF Status ACTV/INAC"] != "ACTV" or source_country not in COUNTRY_CODES:
            continue
        country = COUNTRY_CODES[source_country]
        for field in FORM_FIELDS:
            for candidate in row[field].split(";"):
                normalized = normalize_form(candidate)
                if normalized:
                    forms[country].add(normalized)
    return forms


def main() -> int:
    csv_url = current_csv_url(fetch(GLEIF_PAGE))
    forms = extract_forms(fetch(csv_url))
    output = Path(__file__).resolve().parents[1] / "references" / "legal-forms-eu.txt"
    lines = [
        f"{country}|{form}"
        for country in sorted(forms)
        for form in sorted(forms[country])
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} legal forms from {csv_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
