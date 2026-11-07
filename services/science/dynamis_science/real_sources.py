"""Verified source assessments for the RES-587 real-data candidates.

Every field below was checked against the publisher's public metadata API on
2026-11-04.  The assessment deliberately separates *rights* (what the licence
permits) from *scientific admissibility* (what the deposited files can support).
"""

from __future__ import annotations

from typing import Any

VERIFIED_AT = "2026-11-04T13:50:00Z"

MENDELEY_SOURCE: dict[str, Any] = {
    "id": "SRC-MENDELEY-6P99569X66",
    "name": "Sprint Priming - Longitudinal Study",
    "short_name": "Holmberg sprint priming",
    "doi": "10.17632/6p99569x66.1",
    "canonical_url": "https://data.mendeley.com/datasets/6p99569x66/1",
    "metadata_api": "https://data.mendeley.com/public-api/datasets/6p99569x66",
    "publisher": "Mendeley Data (Elsevier)",
    "creators": ["Patrick Holmberg"],
    "institution": "Queensland University of Technology",
    "version": "1",
    "publication_date": "2026-06-11",
    "license": {
        "id": "CC-BY-4.0",
        "name": "Creative Commons Attribution 4.0 International",
        "url": "https://creativecommons.org/licenses/by/4.0/",
        "evidence": (
            "Mendeley public API field data_licence.url = "
            "http://creativecommons.org/licenses/by/4.0 and full_name = "
            "Creative Commons Attribution 4.0 International; the Creative Commons "
            "deed was fetched independently and returned 'Attribution 4.0 International'."
        ),
        "verified_at": VERIFIED_AT,
    },
    "attribution": (
        "Holmberg P. (2026). Sprint Priming - Longitudinal Study (Version 1) "
        "[Data set]. Mendeley Data. https://doi.org/10.17632/6p99569x66.1. "
        "Licensed under CC BY 4.0; indicate if changes were made."
    ),
    "commercial_use": "PERMITTED",
    "redistribution": (
        "Permitted with attribution and a link to the licence. DynamisScience does "
        "not redistribute participant-level rows in its public repository; derived "
        "aggregates may be published with attribution."
    ),
    "privacy": {
        "classification": "PSEUDONYMOUS",
        "rationale": (
            "Rows are keyed by integer athlete IDs 1-21. Age, height, body mass and "
            "testing occasion are present. No name, contact detail or free-text "
            "identifier is deposited. The combination is still quasi-identifying, so "
            "the data is treated as participant-level and kept outside the public repo."
        ),
        "additional_obligations": [
            "Do not attempt re-identification.",
            "Do not publish participant-level rows from this repository.",
            "Retain only for the documented research purpose.",
        ],
    },
    "files": [
        {
            "name": "DATA.xlsx",
            "size_bytes": 40973,
            "sha256": "81e5665cb9c547f8a1870a62bca87126db58108cf65e002b1fdf681deb21a9da",
            "source_url": (
                "https://data.mendeley.com/public-files/datasets/6p99569x66/files/"
                "9e384262-ee7b-41e5-93e3-a33c6141b94c/file_downloaded"
            ),
            "role": "DERIVED_TABULAR",
        }
    ],
    "data_classification": "DERIVED_TABULAR",
    "methods_documentation": {
        "available": True,
        "location": "Mendeley 'method' field; associated manuscript referenced but not deposited.",
        "summary": (
            "21 highly trained male collegiate athletes; repeated-measures sprint "
            "priming across a 9-week periodised intervention; 20 m sprint with 10 m "
            "split using Brower timing gates; CMJ, 10 rebound jump, isometric squat and "
            "1RM back squat on dual Hawkin Dynamics force plates at 1000 Hz; training "
            "loads across three weekly sessions; linear mixed-effects models in R 4.3.0 "
            "with REML."
        ),
        "gaps": [
            "No column-level codebook is deposited.",
            "The manuscript itself is not part of the deposit.",
            "Occasion labels COND 1-4 are not mapped to study weeks in the deposit.",
            "No raw force-time traces are deposited; only derived scalar outcomes.",
        ],
    },
    "scientific_admissibility": {
        "status": "ADMISSIBLE_WITH_LIMITATIONS",
        "supports": [
            "Longitudinal mixed-effects modelling of repeated CMJ height and isometric strength.",
            "Sprint split consistency checks.",
            "Data-quality and missingness assessment.",
        ],
        "does_not_support": [
            "Independent force-signal integration or phase detection (no raw traces).",
            "Within-session trial-to-trial reliability (one CMJ per occasion).",
            "Causal claims beyond the single-arm repeated-measures design.",
        ],
        "design": "Single-arm repeated-measures longitudinal intervention; no concurrent control group is identifiable in the deposited table.",
    },
    "acquisition": {
        "method": "HTTPS download from the publisher's public file endpoint",
        "destination": "sources/mendeley-6p99569x66/DATA.xlsx",
        "downloaded_at": VERIFIED_AT,
        "checksum_verified": True,
    },
    "rights_status": "VERIFIED",
    "admissibility_status": "ADMISSIBLE_WITH_LIMITATIONS",
}


ZENODO_SOURCE: dict[str, Any] = {
    "id": "SRC-ZENODO-17376717",
    "name": "MoveSmart: multi-modal ground reaction force and Apple Watch dataset",
    "short_name": "MoveSmart wearable + force plate",
    "doi": "10.5281/zenodo.17376717",
    "canonical_url": "https://zenodo.org/records/17376717",
    "metadata_api": "https://zenodo.org/api/records/17376717",
    "publisher": "Zenodo (CERN)",
    "creators": [
        "Parvin Ghaffarzadeh",
        "Debarati Chakraborty",
        "Koorosh Aslansefat",
        "Ali Dostan",
        "Yiannis Papadopoulos",
    ],
    "institution": "University of Hull; Nottingham Trent University",
    "version": "v1.0",
    "publication_date": "2025-11-04",
    "license": {
        "id": "CC0-1.0",
        "name": "Creative Commons Zero v1.0 Universal",
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "evidence": (
            "Zenodo record metadata license.id = 'cc-zero'. The Creative Commons "
            "deed was fetched independently and returned 'CC0 1.0 Universal'. This "
            "differs from the CC BY 4.0 reported in the RES-587 research notes."
        ),
        "verified_at": VERIFIED_AT,
    },
    "attribution": (
        "Ghaffarzadeh P., Chakraborty D., Aslansefat K., Dostan A., Papadopoulos Y. "
        "(2025). MoveSmart: A multi-modal dataset for ground reaction force estimation "
        "using Apple Watch and force plate data (v1.0) [Data set]. Zenodo. "
        "https://doi.org/10.5281/zenodo.17376717. CC0 1.0; attribution is offered "
        "as good scientific practice even though the licence does not require it."
    ),
    "commercial_use": "PERMITTED",
    "redistribution": (
        "CC0 waives copyright and related rights. DynamisScience still does not "
        "redistribute the participant-level archive in its public repository, because "
        "the deposit contains quasi-identifying anthropometric folder names and an "
        "unrelated personal document."
    ),
    "privacy": {
        "classification": "PSEUDONYMOUS",
        "rationale": (
            "Participant directory names encode a participant number, birth year, height and "
            "body mass; these are quasi-identifying fields even though names are absent."
        ),
        "incidents": [
            "The archive contains one unrelated personal document. It is excluded "
            "from extraction and recorded as a privacy incident; it is not research data.",
        ],
        "additional_obligations": [
            "Do not republish participant folder names or the personal document.",
            "Do not attempt re-identification.",
            "Report derived results only at aggregate or pseudonymous level.",
        ],
    },
    "files": [
        {
            "name": "Dataset.zip",
            "size_bytes": 166259083,
            "md5": "cc354ea010f622572a24ccd3e6dfd5a9",
            "source_url": "https://zenodo.org/api/records/17376717/files/Dataset.zip/content",
            "role": "RAW_SIGNAL_ARCHIVE",
        }
    ],
    "archive_inventory": {
        "entries": 3564,
        "csv_files": 1769,
        "uncompressed_bytes": 676083934,
        "path_traversal_findings": 0,
        "excluded_entries": [
            "__MACOSX metadata (1783 entries)",
            ".DS_Store files (7 entries)",
            "one unrelated personal DOCX (not extracted)",
        ],
    },
    "data_classification": "RAW_MULTIMODAL_SIGNAL",
    "methods_documentation": {
        "available": True,
        "location": "Zenodo description and linked GitHub repository; no methods file inside the archive.",
        "summary": (
            "10 healthy adults; five activities (walking, jogging, running, heel drops, "
            "step drops); Apple Watch wrist and waist IMU at approximately 100 Hz; "
            "three AMTI Gen 5 force plates at 1000 Hz; 757 validated trials (584 with "
            "complete trial-ID matching)."
        ),
        "gaps": [
            "The abstract advertises a trial matching manifest, quality flags, "
            "biomechanical validation results and full analysis code; none of these "
            "files is present in the deposited ZIP.",
            "No column-level codebook; force and IMU units are inferred from headers and magnitudes.",
            "No documented clock synchronisation procedure. Recovered device clocks differ "
            "by about 4 hours with ~15 s variability, so sample-level synchronisation "
            "cannot be verified from the archive alone.",
            "Force plate files exist for 400 trials but only 120 have all three plates; "
            "398 have a matching IMU trial by participant, activity and trial number.",
        ],
    },
    "scientific_admissibility": {
        "status": "ADMISSIBLE_WITH_LIMITATIONS",
        "supports": [
            "Measurement qualification of force-plate sampling, baseline and saturation.",
            "Trial-to-trial reliability of peak vertical GRF within participant and activity.",
            "Body-weight plausibility checks from support-phase impulse.",
            "IMU sampling and gravity-vector sanity checks.",
        ],
        "does_not_support": [
            "CMJ or jump-landing inference; no CMJ task is present.",
            "Longitudinal intervention inference; the design is cross-sectional.",
            "Sample-level IMU-to-force synchronisation without the missing manifest.",
            "Claims that the deposited archive contains the advertised quality artefacts.",
        ],
        "design": "Cross-sectional multi-task measurement study; 10 participants; repeated trials within task.",
    },
    "acquisition": {
        "method": "HTTPS download from the Zenodo record file endpoint",
        "destination": "sources/zenodo-17376717/Dataset.zip",
        "downloaded_at": VERIFIED_AT,
        "checksum_verified": True,
    },
    "rights_status": "VERIFIED",
    "admissibility_status": "ADMISSIBLE_WITH_LIMITATIONS",
}


SOURCES = [MENDELEY_SOURCE, ZENODO_SOURCE]


def source_assessment(source_id: str) -> dict[str, Any] | None:
    return next((source for source in SOURCES if source["id"] == source_id), None)


def source_summaries() -> list[dict[str, Any]]:
    summaries = []
    for source in SOURCES:
        summaries.append(
            {
                "id": source["id"],
                "name": source["name"],
                "short_name": source["short_name"],
                "doi": source["doi"],
                "canonical_url": source["canonical_url"],
                "publisher": source["publisher"],
                "creators": source["creators"],
                "version": source["version"],
                "license_id": source["license"]["id"],
                "license_name": source["license"]["name"],
                "license_url": source["license"]["url"],
                "commercial_use": source["commercial_use"],
                "privacy_status": source["privacy"]["classification"],
                "rights_status": source["rights_status"],
                "admissibility_status": source["admissibility_status"],
                "data_classification": source["data_classification"],
                "file_count": len(source["files"]),
                "total_bytes": sum(item["size_bytes"] for item in source["files"]),
                "scientific_admissibility": source["scientific_admissibility"],
                "methods_documentation": source["methods_documentation"],
            }
        )
    return summaries
