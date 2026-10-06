"""Attach one offline RSD skill to each EnvScaler RL task.

EnvScaler env_id values (env_148_rl) do not match AgentWorld skill env_id
values (0000000). Assignment is therefore by class / tool / domain overlap,
which is the paper's offline retrieval using environment identity and tool
schema. At most one skill is stored in extra_info.rsd_skill.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from recipe.envscaler_openai_fc.skill_context import camel_tokens, openai_tool_names

DOMAIN_HINTS = {
    "hospital": (
        "hospital",
        "patient",
        "medical",
        "clinic",
        "health",
        "healthcare",
        "ehr",
        "doctor",
        "nurse",
        "pharmacy",
        "telehealth",
        "telemedicine",
        "blood",
        "disease",
        "dermatology",
        "therapy",
        "lab",
        "clinical",
        "pubmed",
        "trial",
        "biomcp",
        "medrxiv",
        "heliomed",
    ),
    "insurance": (
        "insurance",
        "claim",
        "policy",
        "billing",
        "reimbursement",
        "benefits",
        "expense",
        "ledger",
        "ynab",
        "freshservice",
        "zendesk",
    ),
    "ecommerce": (
        "ecommerce",
        "order",
        "product",
        "review",
        "shop",
        "catalog",
        "subscription",
        "shipment",
        "commerce",
        "asin",
        "klaviyo",
    ),
    "hotel": (
        "hotel",
        "reservation",
        "booking",
        "room",
        "travel",
        "flight",
        "airbnb",
        "amadeus",
        "tripadvisor",
        "aeroledger",
        "aerovale",
        "stay",
    ),
    "fitness": (
        "fitness",
        "yoga",
        "nutrition",
        "sleep",
        "mood",
        "pregnancy",
        "reminder",
        "hevy",
        "oura",
        "lifelog",
    ),
    "messaging": (
        "message",
        "messaging",
        "contact",
        "slack",
        "telegram",
        "whatsapp",
        "mail",
        "inbox",
        "gmail",
    ),
    "schedule": (
        "schedule",
        "appointment",
        "calendar",
        "class",
        "dispatch",
        "emergency",
        "clockify",
        "clockwork",
        "ticktick",
        "todoist",
    ),
    "browser": ("browser", "bookmark", "raindrop", "playwright", "browsertools"),
    "food": ("food", "delivery", "pizza", "ifood", "nutrition"),
    "video": ("video", "conference", "youtube", "meet"),
}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def tool_token_set(tools: list | None) -> set[str]:
    tokens: set[str] = set()
    for name in openai_tool_names(tools):
        tokens.update(camel_tokens(name.replace("_", " ")))
        tokens.add(name.lower())
    return tokens


def domain_of(tokens: set[str]) -> set[str]:
    hit = set()
    for domain, hints in DOMAIN_HINTS.items():
        if tokens & set(hints):
            hit.add(domain)
    return hit


def precompute_skill(skill: dict) -> dict:
    name_tokens = set(camel_tokens(skill.get("env_name") or ""))
    desc_tokens = set(camel_tokens(skill.get("environment_description") or ""))
    text_tokens: set[str] = set()
    for item in skill.get("skills") or []:
        text_tokens.update(camel_tokens(str(item)))
    tool_tokens = tool_token_set(skill.get("tools"))
    return {
        "skill": skill,
        "env_id": str(skill.get("env_id") or ""),
        "name_tokens": name_tokens | desc_tokens,
        "tool_tokens": tool_tokens,
        "text_tokens": text_tokens,
        "domains": domain_of(name_tokens | desc_tokens | tool_tokens),
    }


GENERIC_TOKENS = {
    "server",
    "mcp",
    "api",
    "system",
    "management",
    "application",
    "platform",
    "portal",
    "backend",
    "integration",
    "tool",
    "tools",
    "list",
    "get",
    "create",
    "update",
    "delete",
    "add",
    "set",
    "make",
    "data",
    "info",
    "information",
    "service",
    "app",
    "user",
    "record",
    "records",
}


def distinctive(tokens: set[str]) -> set[str]:
    return {token for token in tokens if len(token) > 3 and token not in GENERIC_TOKENS}


def score_skill(task_tokens: set[str], task_tools: set[str], task_domains: set[str], item: dict) -> float:
    task_core = distinctive(task_tokens)
    name_overlap = len(task_core & distinctive(item["name_tokens"]))
    tool_overlap = len(distinctive(task_tools) & distinctive(item["tool_tokens"]))
    text_overlap = len(task_core & distinctive(item["text_tokens"]))
    domain_overlap = len(task_domains & item["domains"])
    env_name = str(item["skill"].get("env_name") or "").lower()
    substring_hits = sum(1 for token in task_core if token in env_name)
    return (
        6.0 * name_overlap
        + 4.0 * domain_overlap
        + 3.0 * substring_hits
        + 1.0 * tool_overlap
        + 0.15 * text_overlap
        + 0.01
    )


CLASS_TO_SKILL_NAME = {
    "HospitalPatientManagementSystem": "Healthcare Data and Medical Information Server",
    "ElectronicHealthRecordSystem": "Healthcare Data and Medical Information Server",
    "PersonalHealthRecordManagementSystem": "Healthcare Data and Medical Information Server",
    "PatientHealthcarePortal": "Healthcare Data and Medical Information Server",
    "HospitalAssetManagementSystem": "Healthcare Data and Medical Information Server",
    "HospitalBedReservationSystem": "Healthcare Data and Medical Information Server",
    "HospitalBillingManagementSystem": "Healthcare Data and Medical Information Server",
    "HospitalMealManagementSystem": "Healthcare Data and Medical Information Server",
    "HealthcareAppointmentLabManagementSystem": "Healthcare Data and Medical Information Server",
    "BloodDonationAppointmentSystem": "Healthcare Data and Medical Information Server",
    "PublicHealthOutbreakReportingSystem": "Healthcare Data and Medical Information Server",
    "DiseaseOutbreakAlertSubscriptionSystem": "Healthcare Data and Medical Information Server",
    "StateMedicalBoardProviderLicensingSystem": "Healthcare Data and Medical Information Server",
    "TelehealthAppointmentSchedulingSystem": "Healthcare Data and Medical Information Server",
    "TelemedicineDermatologyPlatform": "Healthcare Data and Medical Information Server",
    "EmergencyMedicalDispatchSystem": "Healthcare Data and Medical Information Server",
    "MedicalEquipmentLoanManagementSystem": "Healthcare Data and Medical Information Server",
    "OnlinePharmacyOrderManagementSystem": "Healthcare Data and Medical Information Server",
    "PhysicalTherapyTrackingApplication": "Healthcare Data and Medical Information Server",
    "CounselingServiceManagementSystem": "Healthcare Data and Medical Information Server",
    "ClinicalTrialParticipantManagementSystem": "Healthcare Data and Medical Information Server",
    "PregnancyTrackingHealthManagementApp": "Oura API Integration Server",
    "PersonalMoodTrackingApplication": "Oura API Integration Server",
    "SleepTrackingBackend": "Oura API Integration Server",
    "PersonalNutritionTrackingApp": "Hevy Fitness API MCP Server",
    "FitnessChallengePlatform": "Hevy Fitness API MCP Server",
    "FitnessEquipmentManagementSystem": "Hevy Fitness API MCP Server",
    "YogaClassBookingSystem": "Hevy Fitness API MCP Server",
    "HotelRoomReservationSystem": "Hotel Booking Server",
    "InsuranceClaimManagementSystem": "Freshservice Integration Server",
    "InsurancePolicyManagementSystem": "Freshservice Integration Server",
    "BillingDisputeManagementSystem": "Freshservice Integration Server",
    "OnlineAccountBillingPortal": "Pinnacle Expense Ledger",
    "CorporateExpenseReimbursementSystem": "Pinnacle Expense Ledger",
    "EmployeeBenefitsEnrollmentPortal": "Crescent HR Orchestration Hub",
    "EcommerceOrderManagementSystem": "Crescent Commerce Care Console",
    "EcommerceProductReviewSystem": "PulseShelf Catalog Browser",
    "ContactLensSubscriptionManagementSystem": "Beacon Subscription Ledger",
    "OnlineProfessionalReviewPlatform": "PulseShelf Catalog Browser",
    "FoodDeliveryUserProfileSystem": "Domino's Pizza API Integration Server",
    "MobileMessagingApplication": "WhatsApp Personal Account Connector",
    "PersonalContactsManagementSystem": "Orchard Contact Exchange",
    "MobileReminderSystem": "Todoist Task and Project Manager",
    "OnlineSupportGroupPlatform": "Slack User MCP Server",
    "SupportGroupManagementSystem": "Slack User MCP Server",
    "ClassSchedulingRegistrationSystem": "Keystone Calendar Directory",
    "VideoConferencingSchedulingSystem": "Keystone Calendar Directory",
    "WebBrowserBookmarkSystem": "Raindrop.io Bookmark Manager",
    "MobileEmergencyResponseApp": "GeoPal Travel and Logistics Server",
}


def choose_skill(task_extra: dict, catalog: list[dict]) -> tuple[dict, float, str]:
    environment = task_extra.get("environment") or {}
    env_id = str(task_extra.get("env_id") or environment.get("env_id") or "")
    class_name = str(environment.get("class_name") or "")
    for item in catalog:
        if env_id and item["env_id"] == env_id:
            return item["skill"], 100.0, "env_id"
    for item in catalog:
        if class_name and str(item["skill"].get("env_name") or "") == class_name:
            return item["skill"], 90.0, "class_name"
    return {"env_id": env_id, "env_name": class_name, "skills": [], "bad_patterns": []}, 0.0, "none"


def apply_assignment(row: dict, skill: dict, score: float, method: str) -> dict:
    extra = row.setdefault("extra_info", {})
    texts = [str(item).strip() for item in (skill.get("skills") or []) if str(item).strip()]
    extra["rsd_skill"] = texts[0] if texts else ""
    extra["rsd_skills"] = texts
    extra["rsd_skill_meta"] = {
        "skill_env_id": skill.get("env_id"),
        "skill_env_name": skill.get("env_name"),
        "match_score": round(float(score), 4),
        "match_method": method,
        "bad_pattern": (skill.get("bad_patterns") or [None])[0],
    }
    return row


def env_key(row: dict) -> str:
    extra = row.get("extra_info") or {}
    environment = extra.get("environment") or {}
    return str(
        environment.get("class_name")
        or extra.get("env_id")
        or environment.get("env_id")
        or extra.get("task_id")
        or "unknown"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True)
    parser.add_argument("--skills", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", default="")
    args = parser.parse_args()

    rows = load_jsonl(Path(args.train))
    raw_catalog = load_jsonl(Path(args.skills))
    catalog = [
        precompute_skill(skill)
        for skill in raw_catalog
        if any(str(item).strip() for item in (skill.get("skills") or []))
    ]
    if not catalog:
        raise RuntimeError("skill catalog is empty")

    assignments: dict[str, tuple[dict, float, str]] = {}
    attached = []
    for row in rows:
        key = env_key(row)
        if key not in assignments:
            assignments[key] = choose_skill(row.get("extra_info") or {}, catalog)
        skill, score, method = assignments[key]
        attached.append(apply_assignment(row, skill, score, method))
    write_jsonl(attached, Path(args.output))

    methods = Counter(row["extra_info"]["rsd_skill_meta"]["match_method"] for row in attached)
    skill_ids = Counter(row["extra_info"]["rsd_skill_meta"]["skill_env_id"] for row in attached)
    missing = sum(1 for row in attached if not row["extra_info"]["rsd_skill"])
    report = {
        "train_rows": len(attached),
        "skill_catalog": len(catalog),
        "missing_skill_text": missing,
        "match_methods": dict(methods),
        "unique_assigned_skill_envs": len(skill_ids),
        "top_assigned": skill_ids.most_common(15),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
