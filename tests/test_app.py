import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as wai


@pytest.fixture
def client(monkeypatch):
    # Keep tests isolated from any configured Supabase database and optional LLM service.
    monkeypatch.setattr(wai, "SUPABASE_URL", "")
    monkeypatch.setattr(wai, "SUPABASE_SERVICE_ROLE_KEY", "")
    wai.store._db_configured = False
    wai.store._last_error = None
    wai.store._memory = wai._seed_state()
    monkeypatch.setattr(wai, "GEMINI_API_KEY", "")
    with TestClient(wai.app, follow_redirects=False) as test_client:
        yield test_client


def csrf(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    assert match, "Expected a CSRF token in rendered form"
    return match.group(1)


def read_password_file_credentials() -> dict[str, tuple[str, str]]:
    content = (Path(wai.ROOT) / "password.md").read_text(encoding="utf-8")
    rows = re.findall(r"\| (Administrator|Staff user) \| `([^`]+)` \| `([^`]+)` \|", content)
    return {role: (username, password) for role, username, password in rows}


def sign_in(client: TestClient, username: str, password: str) -> None:
    page = client.get("/login")
    assert page.status_code == 200
    response = client.post(
        "/login",
        data={"csrf_token": csrf(page.text), "username": username, "password": password, "lang": "en"},
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/app"



def grant_staff_access(client: TestClient, username: str = "operator@example.org", password: str = "LongPassword!2026") -> None:
    """Create an individually credentialed staff account through admin access control."""
    sign_in(client, *read_password_file_credentials()["Administrator"])
    admin_page = client.get("/admin")
    created = client.post(
        "/admin/grant",
        data={"csrf_token": csrf(admin_page.text), "display_name": "Test Operator", "username": username, "password": password},
    )
    assert created.status_code == 303
    admin_page = client.get("/admin")
    signed_out = client.post("/logout", data={"csrf_token": csrf(admin_page.text)})
    assert signed_out.status_code == 303



def test_two_initial_logins_are_seeded_and_setup_is_not_required(client):
    state = wai._seed_state()
    admin_email, admin_password = read_password_file_credentials()["Administrator"]
    staff_email, staff_password = read_password_file_credentials()["Staff user"]
    assert state["users"][admin_email]["role"] == "admin"
    assert state["users"][staff_email]["role"] == "main_user"
    assert wai._verify_password(admin_password, state["users"][admin_email])
    assert wai._verify_password(staff_password, state["users"][staff_email])
    assert "DEMO" + "_ADMIN_PASSWORD" not in (Path(wai.ROOT) / ".env.example").read_text()
    assert client.get("/setup").headers["location"] == "/login"
    page = client.get("/login")
    assert page.status_code == 200
    assert "Create administrator" not in page.text
    assert admin_email not in page.text and admin_password not in page.text
    assert staff_email not in page.text and staff_password not in page.text


def test_admin_and_staff_initial_logins_have_expected_permissions(client):
    admin_email, admin_password = read_password_file_credentials()["Administrator"]
    staff_email, staff_password = read_password_file_credentials()["Staff user"]
    sign_in(client, admin_email, admin_password)
    assert client.get("/admin").status_code == 200
    page = client.get("/admin")
    client.post("/logout", data={"csrf_token": csrf(page.text)})
    sign_in(client, staff_email, staff_password)
    assert client.get("/app").status_code == 200
    assert client.get("/admin").status_code == 303

def test_public_routes_and_french_language(client):
    assert client.get("/").status_code == 200
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/setup").headers["location"] == "/login"
    login_page = client.get("/login")
    assert login_page.status_code == 200
    token = csrf(login_page.text)
    result = client.post("/language", data={"csrf_token": token, "lang": "fr", "next": "/"})
    assert result.status_code == 303
    landing = client.get("/")
    assert 'lang="fr-CA"' in landing.text
    assert "Capacités intégrées" not in landing.text
    assert "Trouver des perspectives sur l’eau" in landing.text


def test_landing_page_removes_capabilities_and_orbit_numbers(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    for removed in (
        "Shared decision workflow",
        "Explore the workflow",
        "Better decisions start with better context.",
        "Five connected work areas",
        "Connected capabilities",
        "Built around WaterAid Canada’s operating realities",
        "Open workspace",
        "Access Wai Intelligence",
    ):
        assert removed not in html
    assert "Find water insights" in html
    assert "Intelligence for lasting water access" in html
    assert "Bring funding, evidence, donor relationships and programme delivery together for clearer, accountable decisions." in html
    assert "one reviewable workspace" not in html
    assert "Support lasting access to safe water, sanitation and hygiene." in html
    assert 'class="capability-card"' not in html
    assert 'class="capability-grid"' not in html
    assert 'class="node-number"' not in html
    assert "<footer" not in html
    css = client.get("/static/styles.css").text
    assert ".capability-grid { display: grid; grid-template-columns: repeat(5,minmax(0,1fr));" not in css

def test_private_routes_require_login(client):
    response = client.get("/app")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert client.get("/modules/grant-prospecting").status_code == 303
    assert client.get("/admin").status_code == 303


def test_staff_can_open_all_modules_and_admin_is_restricted(client):
    grant_staff_access(client)
    sign_in(client, "operator@example.org", "LongPassword!2026")
    routes = [
        "/app",
        "/modules/grant-prospecting",
        "/modules/intelligent-reporting",
        "/modules/donor-stewardship",
        "/modules/ethical-due-diligence",
        "/modules/grant-compliance",
    ]
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200, route
    assert client.get("/decisions").status_code == 303
    response = client.get("/admin")
    assert response.status_code == 303
    assert response.headers["location"].startswith("/app?")


def test_analysis_review_is_integrated_in_work_area(client, monkeypatch):
    async def no_gemini(prompt, lang, use_search=False):
        return None

    monkeypatch.setattr(wai, "_call_gemini", no_gemini)
    grant_staff_access(client)
    sign_in(client, "operator@example.org", "LongPassword!2026")
    module_page = client.get("/modules/intelligent-reporting")
    token = csrf(module_page.text)
    submit = client.post(
        "/modules/intelligent-reporting/analyze",
        data={"csrf_token": token, "objective": "Explain the quarterly fundraising trend", "audience": "Board"},
    )
    assert submit.status_code == 303
    analysis_url = submit.headers["location"].split("?", 1)[0]
    analysis_page = client.get(analysis_url)
    assert analysis_page.status_code == 200
    assert "Synthetic" not in analysis_page.text and "synthetic" not in analysis_page.text

    review_token = csrf(analysis_page.text)
    reviewed = client.post(
        f"{analysis_url}/review",
        data={"csrf_token": review_token, "action": "approve", "feedback": "Numbers reviewed for the demo."},
    )
    assert reviewed.status_code == 303
    updated = client.get(analysis_url)
    assert "Approved by reviewer" in updated.text

    decision_token = csrf(updated.text)
    pushed = client.post(f"{analysis_url}/decision", data={"csrf_token": decision_token})
    assert pushed.status_code == 303
    workbench = client.get("/decisions")
    assert workbench.status_code == 303
    assert workbench.headers["location"] == "/app"


def test_admin_can_grant_and_revoke_staff_access(client):
    sign_in(client, *read_password_file_credentials()["Administrator"])
    page = client.get("/admin")
    assert page.status_code == 200
    token = csrf(page.text)
    granted = client.post(
        "/admin/grant",
        data={"csrf_token": token, "display_name": "New Staff", "username": "new.user@example.org", "password": "LongPassword!2026"},
    )
    assert granted.status_code == 303
    assert wai.store._memory["users"]["new.user@example.org"]["status"] == "active"

    page = client.get("/admin")
    revoked = client.post(
        "/admin/revoke",
        data={"csrf_token": csrf(page.text), "username": "new.user@example.org"},
    )
    assert revoked.status_code == 303
    assert wai.store._memory["users"]["new.user@example.org"]["status"] == "revoked"


def test_post_requires_valid_csrf_token(client):
    grant_staff_access(client)
    sign_in(client, "operator@example.org", "LongPassword!2026")
    response = client.post("/decisions", data={"problem": "missing token"})
    assert response.status_code == 403


def test_reporting_analysis_cache_is_reused(client, monkeypatch):
    async def no_gemini(prompt, lang, use_search=False):
        return None

    monkeypatch.setattr(wai, "_call_gemini", no_gemini)
    grant_staff_access(client)
    sign_in(client, "operator@example.org", "LongPassword!2026")
    page = client.get("/modules/intelligent-reporting")
    payload = {"csrf_token": csrf(page.text), "objective": "Compare quarterly revenue changes"}
    first = client.post("/modules/intelligent-reporting/analyze", data=payload)
    assert first.status_code == 303
    second = client.post("/modules/intelligent-reporting/analyze", data=payload)
    assert second.status_code == 303
    assert len(wai.store._memory["analysis_cache"]) == 1
    assert wai.store._memory["analyses"][-1]["mode"] == "local-cached"


def test_document_upload_is_processed_in_memory(client, monkeypatch):
    async def no_gemini(prompt, lang, use_search=False):
        return None

    monkeypatch.setattr(wai, "_call_gemini", no_gemini)
    grant_staff_access(client)
    sign_in(client, "operator@example.org", "LongPassword!2026")
    page = client.get("/modules/grant-compliance")
    response = client.post(
        "/modules/grant-compliance/analyze",
        data={"csrf_token": csrf(page.text), "objective": "Review reporting obligations in the sample document", "grant": "Test grant", "focus": "Obligations and reporting schedule"},
        files={"document": ("sample.txt", b"Synthetic reporting clause: monthly reporting by the 10th.", "text/plain")},
    )
    assert response.status_code == 303
    analysis = wai.store._memory["analyses"][-1]
    assert analysis["uploaded_text_present"] is True
    assert analysis["uploaded_filename"] == "sample.txt"
    assert "monthly reporting" in analysis["result"].lower()


def test_workspace_localizes_navigation_and_recent_work(client):
    grant_staff_access(client)
    page = client.get("/login")
    response = client.post(
        "/language",
        data={"csrf_token": csrf(page.text), "lang": "fr", "next": "/login"},
    )
    assert response.status_code == 303
    login_page = client.get("/login")
    result = client.post(
        "/login",
        data={"csrf_token": csrf(login_page.text), "username": "operator@example.org", "password": "LongPassword!2026", "lang": "fr"},
    )
    assert result.status_code == 303
    overview = client.get("/app")
    assert 'lang="fr-CA"' in overview.text
    assert "Source de financement" in overview.text
    assert "Aucun brouillon pour le moment" in overview.text
    assert "synthetic" not in overview.text.lower()
    for slug in wai.MODULES:
        module = client.get(f"/modules/{slug}")
        assert module.status_code == 200
        assert 'lang="fr-CA"' in module.text


def test_data_folder_csvs_are_loaded_from_source_files():
    profiles = wai.read_dataset("constituent_profiles_table1")
    interactions = wai.read_dataset("CRM_interacions_table1")
    engagement = wai.read_dataset("video_email_data_table1")
    assert profiles and profiles[0]["CONSTITUENT_ID"] == "437216659"
    assert "LIFETIME_GIVING" in profiles[0]
    assert interactions and interactions[0]["CRM_INTERACTION_TYPE"] == "Phone"
    assert engagement and "FINISHED_VIDEO" in engagement[0]
    with pytest.raises(KeyError):
        wai.read_dataset("../../.env")


def test_authenticated_exports_and_data_integration_page(client):
    assert client.get("/exports").status_code == 303
    grant_staff_access(client)
    sign_in(client, "operator@example.org", "LongPassword!2026")
    page = client.get("/exports")
    assert page.status_code == 200
    assert "Data exports" in page.text
    assert "CRM_interacions_table1.csv" in page.text
    csv_export = client.get("/exports/constituent_profiles_table1.csv")
    assert csv_export.status_code == 200
    assert "text/csv" in csv_export.headers["content-type"]
    assert "CONSTITUENT_ID" in csv_export.text
    summary = client.get("/exports/summary.json")
    assert summary.status_code == 200
    assert "video_email_data_table1.csv" in summary.text
    assert client.get("/exports/not-a-dataset.csv").status_code == 404


def test_donor_stewardship_displays_joined_profile_crm_and_engagement_data(client):
    grant_staff_access(client)
    sign_in(client, "operator@example.org", "LongPassword!2026")
    page = client.get("/modules/donor-stewardship")
    assert page.status_code == 200
    assert "Morgan Ellis" in page.text
    assert "Scenario profile" in page.text
    assert "Previous correspondence" in page.text
    assert "Permission and next action" in page.text
    assert "Lifetime giving · source value" in page.text
    assert "Recent CRM interactions" in page.text
    assert "Email and video engagement" in page.text
    assert "Prepare a stewardship brief" in page.text
    assert "Browse constituent records" in page.text
    assert "CRM_INTERACTION_TYPE" not in page.text
    assert "synthetic" not in page.text.lower()


def test_donor_restrictions_hide_outbound_email_actions_and_context_is_exportable(client):
    grant_staff_access(client)
    sign_in(client, "operator@example.org", "LongPassword!2026")
    context_rows = wai.read_dataset("donor_relationship_context")
    restricted = next(row for row in context_rows if row["DISPLAY_NAME"] == "Avery Chen")
    page = client.get(f"/modules/donor-stewardship?constituent_id={restricted['CONSTITUENT_ID']}")
    assert page.status_code == 200
    assert "Contact restriction needs review" in page.text
    assert "Withdrawn" in page.text
    form = re.search(r'<select id="purpose".*?</select>', page.text, re.S)
    assert form and "Internal relationship review" in form.group(0)
    assert "Thank-you / impact update draft" not in form.group(0)
    exports = client.get("/exports")
    assert "donor_relationship_context.csv" in exports.text
    assert client.get("/exports/donor_relationship_context.csv").status_code == 200


def test_login_page_never_displays_initial_credentials(client, monkeypatch):
    monkeypatch.setenv("DEMO_SHOW_CREDENTIALS", "true")
    page = client.get("/login")
    assert page.status_code == 200
    for username, password in read_password_file_credentials().values():
        assert username not in page.text
        assert password not in page.text
    assert "Create administrator" not in page.text
    assert "two accounts" not in page.text.lower()

def test_legacy_seeded_staff_account_is_removed_from_persisted_state(client):
    state = wai._seed_state()
    state["users"]["legacy.staff@wai.local"] = {
        "email": "legacy.staff@wai.local",
        "role": "main_user",
        "status": "active",
        **wai._hash_password("OldDemoPassword!2026"),
        "created_at": wai._utc_now(),
        "is_seed": True,
    }
    wai.store._memory = state
    repaired = wai._repair_state(wai.store.load())
    assert "legacy.staff@wai.local" not in repaired["users"]
    assert read_password_file_credentials()["Administrator"][0] in repaired["users"]
    assert read_password_file_credentials()["Staff user"][0] in repaired["users"]


def test_legacy_demo_admin_is_removed_instead_of_requiring_its_password(client):
    state = wai._seed_state()
    state["users"]["admin@wai.local"] = {
        "email": "admin@wai.local", "role": "admin", "status": "active",
        **wai._hash_password("OldDemoAdmin!2026"), "created_at": wai._utc_now(), "is_seed": True,
    }
    wai.store._memory = state
    repaired = wai._repair_state(wai.store.load())
    assert "admin@wai.local" not in repaired["users"]
    assert client.get("/setup").headers["location"] == "/login"


def test_overview_uses_display_name_and_no_decision_workbench(client):
    sign_in(client, *read_password_file_credentials()["Staff user"])
    page = client.get("/app")
    assert page.status_code == 200
    assert "Welcome, Wai Staff" in page.text
    assert "wai.staff" not in page.text
    assert "Decision workbench" not in page.text
    assert "Illustrative fit only" not in page.text
    assert "Figures are illustrative CAD totals" not in page.text


def test_data_exports_show_only_source_datasets_and_no_connection_status(client):
    sign_in(client, *read_password_file_credentials()["Staff user"])
    page = client.get("/exports")
    assert page.status_code == 200
    assert "constituent_profiles_table1.csv" in page.text
    assert "video_email_data_table1.csv" in page.text
    assert "demo_kpis.csv" not in page.text
    assert "Connection status" not in page.text
    assert "Connection options" not in page.text


def test_work_areas_have_distinct_brief_aligned_layouts_and_no_title_subtitles(client):
    sign_in(client, *read_password_file_credentials()["Staff user"])
    pages = {}
    for slug in wai.MODULES:
        page = client.get(f"/modules/{slug}")
        assert page.status_code == 200
        pages[slug] = page.text
        assert "Decision support, not autonomous approval" not in page.text
        assert "rules-based demo mode" not in page.text.lower()
        title = re.search(r'<header class="work-area-title"><h1>.*?</h1>(.*?)</header>', page.text, re.S)
        assert title and "<p" not in title.group(1), f"Unneeded subtitle below title: {slug}"
    funding = pages["grant-prospecting"]
    assert "WASH" not in funding
    assert "Current funding pathways" in funding
    assert "Peter Gilgan Foundation" in funding
    assert "Canadian Global Community Impact Foundation" in funding
    assert "Strong history · intake closed" in funding
    assert "Local applicant required" in funding
    assert "Eligibility and application process" in funding
    assert "Published international grant history" in funding
    assert "Monitoring effort and cost" in funding
    assert "Record or update staff assessment" in funding
    reporting = pages["intelligent-reporting"]
    assert "Email engagement by send year" in reporting
    assert "CRM interaction mix" in reporting
    assert "Draft a report narrative" in reporting
    stewardship = pages["donor-stewardship"]
    assert "Constituent record" in stewardship and "Recent CRM interactions" in stewardship
    assert "Email and video engagement" in stewardship
    diligence = pages["ethical-due-diligence"]
    assert "Partner review" in diligence and "Assessment criteria" in diligence
    assert "Ownership and leadership" in diligence and "Source and date" in diligence
    compliance = pages["grant-compliance"]
    assert "Grant document review" in compliance
    assert "Select the files to compare" in compliance
    assert "Requirement map" in compliance and "Consistency checks" in compliance


def test_funding_opportunity_staff_disposition_is_saved(client):
    sign_in(client, *read_password_file_credentials()["Staff user"])
    page = client.get("/modules/grant-prospecting")
    assert page.status_code == 200
    token = csrf(page.text)
    response = client.post(
        "/modules/grant-prospecting/review",
        data={"csrf_token": token, "opportunity_id": "opp-gac-unsolicited", "decision": "monitor", "rationale": "Recheck eligibility after the programme concept is defined."},
    )
    assert response.status_code == 303
    review = wai.store._memory["opportunity_reviews"]["opp-gac-unsolicited"]
    assert review["decision"] == "monitor"
    assert "programme concept" in review["rationale"]
    updated = client.get("/modules/grant-prospecting")
    assert "Staff decision" in updated.text
    assert "Recheck eligibility after the programme concept is defined." in updated.text


def test_reporting_upload_calculates_numeric_changes(client, monkeypatch):
    async def no_gemini(prompt, lang, use_search=False):
        return None
    monkeypatch.setattr(wai, "_call_gemini", no_gemini)
    sign_in(client, *read_password_file_credentials()["Staff user"])
    page = client.get("/modules/intelligent-reporting")
    response = client.post(
        "/modules/intelligent-reporting/analyze",
        data={"csrf_token": csrf(page.text), "objective": "Compare annual engagement", "audience": "Leadership team", "period": "2025 to 2026"},
        files={"document": ("engagement.csv", b"period,engagement\n2025,10\n2026,15\n", "text/csv")},
    )
    assert response.status_code == 303
    result = wai.store._memory["analyses"][-1]["result"]
    assert "engagement" in result
    assert "10.00" in result and "15.00" in result and "+50.0%" in result


def test_expanded_source_tables_remain_under_25mb():
    for filename in ("constituent_profiles_table1.csv", "CRM_interacions_table1.csv", "video_email_data_table1.csv", "donor_relationship_context.csv"):
        assert (wai.DATA_DIR / filename).stat().st_size < 25 * 1024 * 1024
