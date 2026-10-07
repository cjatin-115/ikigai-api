import time
import jwt
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.modules.workspaces.repository import workspace_repository
from app.modules.workspaces.dto import WorkspaceRole

client = TestClient(app)

def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ikigai-api"

# --- Contact Form Validation & Security Tests ---

def test_contact_valid_submission():
    payload = {
        "name": "Alex Chen",
        "email": "alex.chen@example.com",
        "subject": "Systems Collaboration",
        "message": "Interested in discussing autonomous pipeline architecture."
    }
    response = client.post("/api/v1/public/messages", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "RECEIVED"
    assert "Transmission acknowledged" in data["message"]

def test_contact_missing_required_fields():
    # Missing email and message
    payload = {"name": "Alex Chen"}
    response = client.post("/api/v1/public/messages", json=payload)
    assert response.status_code == 422

def test_contact_invalid_email():
    payload = {
        "name": "Alex Chen",
        "email": "not-a-valid-email",
        "message": "Valid transmission length here."
    }
    response = client.post("/api/v1/public/messages", json=payload)
    assert response.status_code == 422

def test_contact_excessive_message_length():
    payload = {
        "name": "Alex Chen",
        "email": "alex@example.com",
        "message": "A" * 5001  # Exceeds max 5000
    }
    response = client.post("/api/v1/public/messages", json=payload)
    assert response.status_code == 422

def test_contact_honeypot_spam_flagged():
    payload = {
        "name": "Bot Submitter",
        "email": "bot@automated.net",
        "message": "Spam payload offering services.",
        "honeypot": "https://spamlink.ru"
    }
    response = client.post("/api/v1/public/messages", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "SPAM_FLAGGED"

# --- Anonymous Review Tests ---

def test_anonymous_review_valid_submission():
    payload = {
        "content": "Superb architecture and aesthetic discipline. Very impressive engineer.",
        "rating": 5
    }
    response = client.post("/api/v1/public/reviews", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "PENDING"
    assert "Orbital Observer" in data["synthetic_display_name"]
    assert "seed-orbit" in data["synthetic_avatar_seed"]

def test_anonymous_review_missing_content():
    payload = {"rating": 5}
    response = client.post("/api/v1/public/reviews", json=payload)
    assert response.status_code == 422

def test_anonymous_review_honeypot():
    payload = {
        "content": "Another spam review submission attempt.",
        "honeypot": "spam-bot-value"
    }
    response = client.post("/api/v1/public/reviews", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "REJECTED"

def test_public_reviews_only_exposes_approved():
    # 1. Submit review (defaults to PENDING)
    submit_res = client.post("/api/v1/public/reviews", json={
        "content": "This review should not be visible until approved by owner.",
        "rating": 5
    })
    review_id = submit_res.json()["id"]

    # 2. Query public endpoint -> must NOT contain the pending review
    public_res = client.get("/api/v1/public/reviews")
    assert public_res.status_code == 200
    public_reviews = public_res.json()
    assert not any(r["id"] == review_id for r in public_reviews)

    # 3. Moderate review (Approve) via protected route
    admin_id = "00000000-0000-0000-0000-000000000002"
    workspace_repository.seed_membership("ws_default_jatin", admin_id, WorkspaceRole.ADMIN)
    token_admin = jwt.encode({
        "sub": admin_id,
        "email": "admin@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    approve_res = client.post(
        f"/api/v1/workspaces/current/reviews/{review_id}/approve",
        headers={
            "Authorization": f"Bearer {token_admin}",
            "X-Workspace-Id": "ws_default_jatin",
        }
    )
    assert approve_res.status_code == 200

    # 4. Query public endpoint again -> now MUST be visible
    public_res_after = client.get("/api/v1/public/reviews")
    assert any(r["id"] == review_id for r in public_res_after.json())

# --- Security & Unauthorized Data Exposure Tests ---

def test_unauthorized_cannot_read_private_contact_messages():
    # Public user tries to read private inbox messages without auth
    response = client.get("/api/v1/workspaces/current/messages")
    assert response.status_code == 401

def test_unauthenticated_cannot_approve_review():
    # Public user tries to approve a review without credentials
    response = client.post("/api/v1/workspaces/current/reviews/rev_101/approve")
    assert response.status_code == 401

def test_cross_workspace_cannot_approve_review():
    # Clear rate limiter history for clean test isolation
    from app.core.rate_limit import review_rate_limiter
    review_rate_limiter._history.clear()

    # Submitting review in default workspace
    submit_res = client.post("/api/v1/public/reviews", json={
        "content": "Cross workspace review test content.",
        "rating": 4
    })
    assert submit_res.status_code == 201
    review_id = submit_res.json()["id"]

    alien_admin_id = "00000000-0000-0000-0000-000000000003"
    token_alien = jwt.encode({
        "sub": alien_admin_id,
        "email": "alien@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    # Attempting to approve the review with an alien workspace ID
    response = client.post(
        f"/api/v1/workspaces/current/reviews/{review_id}/approve",
        headers={
            "Authorization": f"Bearer {token_alien}",
            "X-Workspace-Id": "00000000-0000-0000-0000-000000000099",
        }
    )
    assert response.status_code == 404

# --- Phase 3B: Supabase JWT, RBAC & Persistence Isolation Tests ---

import jwt
import time
from app.core.config import settings
from app.modules.workspaces.repository import workspace_repository
from app.modules.workspaces.dto import WorkspaceRole

def test_jwt_verification_valid_token():
    user_id = "6d333cf3-190d-4729-9274-d6f5ea705244"
    workspace_repository.seed_membership("ws_default_jatin", user_id, WorkspaceRole.MEMBER)

    # Generate real signed HS256 token
    payload = {
        "sub": user_id,
        "email": "jatin@real.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
        "role": "authenticated"
    }
    valid_token = jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={
            "Authorization": f"Bearer {valid_token}",
            "X-Workspace-Id": "ws_default_jatin",
        }
    )
    assert response.status_code == 200

def test_missing_workspace_header_returns_400():
    user_id = "6d333cf3-190d-4729-9274-d6f5ea705244"
    payload = {
        "sub": user_id,
        "email": "jatin@real.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
        "role": "authenticated"
    }
    valid_token = jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    # Missing X-Workspace-Id must be rejected with HTTP 400 Bad Request
    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_WORKSPACE_HEADER"

def test_jwt_verification_expired_token():
    payload = {
        "sub": "6d333cf3-190d-4729-9274-d6f5ea705244",
        "email": "jatin@real.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) - 100,  # Expired
        "role": "authenticated"
    }
    expired_token = jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={"Authorization": f"Bearer {expired_token}", "X-Workspace-Id": "ws_default_jatin"}
    )
    assert response.status_code == 401
    assert "expired" in response.json()["error"]["message"].lower()

def test_jwt_verification_wrong_issuer():
    # If SUPABASE_URL configured, wrong issuer must be rejected
    from unittest.mock import patch
    payload = {
        "sub": "6d333cf3-190d-4729-9274-d6f5ea705244",
        "email": "jatin@real.internal",
        "aud": "authenticated",
        "iss": "https://attacker-fake-supabase.co/auth/v1",
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
    with patch.object(settings, "SUPABASE_URL", "https://valid-project.supabase.co"):
        response = client.get(
            "/api/v1/workspaces/current/messages",
            headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": "ws_default_jatin"}
        )
        assert response.status_code == 401
        assert "issuer" in response.json()["error"]["message"].lower()

def test_jwt_verification_wrong_audience():
    payload = {
        "sub": "6d333cf3-190d-4729-9274-d6f5ea705244",
        "email": "jatin@real.internal",
        "aud": "wrong-audience",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }
    bad_aud_token = jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={"Authorization": f"Bearer {bad_aud_token}", "X-Workspace-Id": "ws_default_jatin"}
    )
    assert response.status_code == 401
    assert "audience" in response.json()["error"]["message"].lower()

def test_jwt_verification_non_uuid_sub():
    payload = {
        "sub": "invalid-not-a-uuid-and-not-usr-test",
        "email": "badsub@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }
    bad_sub_token = jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={"Authorization": f"Bearer {bad_sub_token}", "X-Workspace-Id": "ws_default_jatin"}
    )
    assert response.status_code == 401
    assert "uuid" in response.json()["error"]["message"].lower()

def test_jwt_verification_tampered_signature():
    payload = {
        "sub": "6d333cf3-190d-4729-9274-d6f5ea705244",
        "email": "jatin@real.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }
    # Tampered signature using wrong secret
    tampered_token = jwt.encode(payload, "wrong-secret-key-12345678901234567890", algorithm="HS256")

    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={"Authorization": f"Bearer {tampered_token}", "X-Workspace-Id": "ws_default_jatin"}
    )
    assert response.status_code == 401
    assert "signature" in response.json()["error"]["message"].lower()

def test_jwt_verification_alg_none_rejected():
    # PyJWT rejects alg=none or unsigned tokens when algorithms=['HS256']
    # Craft raw alg=none token header.payload.
    import base64
    import json
    header_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps({
        "sub": "6d333cf3-190d-4729-9274-d6f5ea705244",
        "email": "jatin@real.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }).encode()).decode().rstrip("=")
    none_token = f"{header_b64}.{payload_b64}."

    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={"Authorization": f"Bearer {none_token}", "X-Workspace-Id": "ws_default_jatin"}
    )
    assert response.status_code == 401

def test_jwt_verification_missing_authorization_header():
    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={"X-Workspace-Id": "ws_default_jatin"}
    )
    assert response.status_code == 401
    assert "valid bearer token is required" in response.json()["error"]["message"].lower()

def test_jwt_verification_malformed_authorization_header():
    # Not starting with Bearer
    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={"Authorization": "Basic dXNlcjpwYXNz", "X-Workspace-Id": "ws_default_jatin"}
    )
    assert response.status_code == 401
    assert "valid bearer token is required" in response.json()["error"]["message"].lower()

# --- Task 2: Fail-Closed & Missing Required Claims Tests ---

def test_jwt_verification_missing_supabase_url():
    from unittest.mock import patch
    token = jwt.encode({
        "sub": "6d333cf3-190d-4729-9274-d6f5ea705244",
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    with patch.object(settings, "SUPABASE_URL", ""):
        res = client.get("/api/v1/workspaces/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 500
        assert res.json()["error"]["code"] == "AUTH_CONFIG_ERROR"

def test_jwt_verification_missing_jwt_secret():
    from unittest.mock import patch
    token = jwt.encode({
        "sub": "6d333cf3-190d-4729-9274-d6f5ea705244",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, "temp-secret", algorithm="HS256")

    with patch.object(settings, "SUPABASE_JWT_SECRET", ""):
        res = client.get("/api/v1/workspaces/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 500
        assert res.json()["error"]["code"] == "AUTH_CONFIG_ERROR"

def test_jwt_verification_missing_exp_claim():
    token = jwt.encode({
        "sub": "6d333cf3-190d-4729-9274-d6f5ea705244",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    res = client.get("/api/v1/workspaces/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401

def test_jwt_verification_missing_sub_claim():
    token = jwt.encode({
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    res = client.get("/api/v1/workspaces/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401

def test_jwt_verification_missing_aud_claim():
    token = jwt.encode({
        "sub": "6d333cf3-190d-4729-9274-d6f5ea705244",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    res = client.get("/api/v1/workspaces/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401

def test_rbac_member_cannot_approve_review():
    # 1. Submit review
    from app.core.rate_limit import review_rate_limiter
    review_rate_limiter._history.clear()
    
    sub = client.post("/api/v1/public/reviews", json={
        "content": "Critique submitted for role test verification.",
        "rating": 5
    })
    rev_id = sub.json()["id"]

    # 2. Create user with MEMBER role (not Admin/Owner)
    member_user_id = "e63606f1-a53d-49ea-b528-7fbfb6e72dde"
    workspace_repository.seed_membership("ws_default_jatin", member_user_id, WorkspaceRole.MEMBER)

    member_token = jwt.encode({
        "sub": member_user_id,
        "email": "member@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    # Member can view inbox
    inbox_res = client.get(
        "/api/v1/workspaces/current/messages",
        headers={
            "Authorization": f"Bearer {member_token}",
            "X-Workspace-Id": "ws_default_jatin",
        }
    )
    assert inbox_res.status_code == 200

    # Member CANNOT approve review -> Must be 403 Forbidden
    approve_res = client.post(
        f"/api/v1/workspaces/current/reviews/{rev_id}/approve",
        headers={
            "Authorization": f"Bearer {member_token}",
            "X-Workspace-Id": "ws_default_jatin",
        }
    )
    assert approve_res.status_code == 403
    assert "admin" in approve_res.json()["error"]["message"].lower()

def test_rbac_admin_can_approve_review():
    from app.core.rate_limit import review_rate_limiter
    review_rate_limiter._history.clear()
    
    sub = client.post("/api/v1/public/reviews", json={
        "content": "Critique submitted for admin approval test.",
        "rating": 5
    })
    rev_id = sub.json()["id"]

    admin_user_id = "a74a622e-e9f7-4c05-a485-97ee390e6c1b"
    workspace_repository.seed_membership("ws_default_jatin", admin_user_id, WorkspaceRole.ADMIN)

    admin_token = jwt.encode({
        "sub": admin_user_id,
        "email": "admin@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    approve_res = client.post(
        f"/api/v1/workspaces/current/reviews/{rev_id}/approve",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "X-Workspace-Id": "ws_default_jatin",
        }
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "success"

def test_get_my_workspaces_cases_and_isolation():
    # Case A: User A with multiple workspaces
    user_a = "16e2328b-0de6-49b0-960d-4171d4e25e98"
    workspace_repository.seed_workspace("ws_tenant_a1", "Tenant A Workspace 1", "tenant-a1")
    workspace_repository.seed_workspace("ws_tenant_a2", "Tenant A Workspace 2", "tenant-a2")
    workspace_repository.seed_membership("ws_tenant_a1", user_a, WorkspaceRole.OWNER)
    workspace_repository.seed_membership("ws_tenant_a2", user_a, WorkspaceRole.MEMBER)

    token_a = jwt.encode({
        "sub": user_a,
        "email": "user_a@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    res_a = client.get("/api/v1/workspaces/me", headers={"Authorization": f"Bearer {token_a}"})
    assert res_a.status_code == 200
    workspaces_a = res_a.json()
    ids_a = {ws["id"] for ws in workspaces_a}
    assert ids_a == {"ws_tenant_a1", "ws_tenant_a2"}

    # Case B: User B with independent workspace
    user_b = "da503d23-e1c2-4021-8227-3b5ad8cb9e9d"
    workspace_repository.seed_workspace("ws_tenant_b1", "Tenant B Workspace 1", "tenant-b1")
    workspace_repository.seed_membership("ws_tenant_b1", user_b, WorkspaceRole.OWNER)

    token_b = jwt.encode({
        "sub": user_b,
        "email": "user_b@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    res_b = client.get("/api/v1/workspaces/me", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    workspaces_b = res_b.json()
    ids_b = {ws["id"] for ws in workspaces_b}
    assert ids_b == {"ws_tenant_b1"}
    assert "ws_tenant_a1" not in ids_b
    assert "ws_tenant_a2" not in ids_b

    # Case C: User C with zero workspaces receives empty list (NO default workspace fallback)
    user_c = "43c3e808-c679-4b9e-8b90-1406cf9855b2"
    token_c = jwt.encode({
        "sub": user_c,
        "email": "user_c@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    res_c = client.get("/api/v1/workspaces/me", headers={"Authorization": f"Bearer {token_c}"})
    assert res_c.status_code == 200
    workspaces_c = res_c.json()
    assert workspaces_c == []

    # Case D: Unauthenticated request returns 401
    res_d = client.get("/api/v1/workspaces/me")
    assert res_d.status_code == 401

    # Case E: Supplied X-Workspace-Id header does not alter discovery result
    res_e = client.get(
        "/api/v1/workspaces/me",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Workspace-Id": "ws_tenant_a1",
        }
    )
    assert res_e.status_code == 200
    workspaces_e = res_e.json()
    ids_e = {ws["id"] for ws in workspaces_e}
    assert ids_e == {"ws_tenant_b1"}

    # Field assertions: verify response items have exact keys and no extra/sensitive fields
    first_ws = workspaces_a[0]
    assert set(first_ws.keys()) == {"id", "name", "slug", "role"}
    assert first_ws["role"] in {"owner", "admin", "member"}

def test_workspaces_me_exact_contract_and_roles():
    user = "88c0aca9-ace1-4ff8-ac28-ac5f1ef7d8c4"
    workspace_repository.seed_workspace("ws_owner_test", "Owner Test Workspace", "owner-test")
    workspace_repository.seed_workspace("ws_member_test", "Member Test Workspace", "member-test")
    workspace_repository.seed_membership("ws_owner_test", user, WorkspaceRole.OWNER)
    workspace_repository.seed_membership("ws_member_test", user, WorkspaceRole.MEMBER)

    token = jwt.encode({
        "sub": user,
        "email": "user_contract@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    res = client.get("/api/v1/workspaces/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    for item in items:
        assert set(item.keys()) == {"id", "name", "slug", "role"}
    roles_by_slug = {item["slug"]: item["role"] for item in items}
    assert roles_by_slug["owner-test"] == "owner"
    assert roles_by_slug["member-test"] == "member"

def test_supabase_workspace_repository_mode_b_mock_transport():
    import pytest
    import httpx
    from app.core.supabase import SupabasePostgrestClient
    from app.modules.workspaces.repository import SupabaseWorkspaceRepository

    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        return httpx.Response(
            status_code=200,
            json=[
                {
                    "role": "owner",
                    "workspaces": {
                        "id": "mock-ws-uuid-1",
                        "slug": "mock-workspace",
                        "name": "Mock Workspace",
                    }
                }
            ],
        )

    transport = httpx.MockTransport(mock_handler)
    mock_postgrest_client = SupabasePostgrestClient(
        base_url="https://mockproject.supabase.co",
        anon_key="mock-anon-key-12345",
        service_role_key="mock-service-role-secret-67890",
    )

    repo = SupabaseWorkspaceRepository(client=mock_postgrest_client)

    # Monkeypatch httpx.AsyncClient inside postgrest_request to use transport
    original_postgrest_request = mock_postgrest_client.postgrest_request
    async def wrapped_postgrest_request(method, path, headers, params=None, json_data=None):
        url = f"{mock_postgrest_client.rest_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient(transport=transport, timeout=10.0) as cl:
            resp = await cl.request(method=method, url=url, headers=headers, params=params, json=json_data)
            return resp.json()

    mock_postgrest_client.postgrest_request = wrapped_postgrest_request

    user_id = "f4109c84-bf23-4b5b-a94e-e3942a9518bf"
    user_jwt = "mock-user-jwt-bearer-token"

    import asyncio
    workspaces = asyncio.run(repo.list_user_workspaces(user_id=user_id, user_jwt=user_jwt))

    assert len(workspaces) == 1
    assert workspaces[0].id == "mock-ws-uuid-1"
    assert workspaces[0].slug == "mock-workspace"
    assert workspaces[0].name == "Mock Workspace"
    assert workspaces[0].role == WorkspaceRole.OWNER

    # Assert captured HTTP headers and URL params
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.headers["apikey"] == "mock-anon-key-12345"
    assert req.headers["authorization"] == f"Bearer {user_jwt}"
    assert "mock-service-role-secret-67890" not in str(req.headers)
    assert "user_id=eq.f4109c84-bf23-4b5b-a94e-e3942a9518bf" in str(req.url)
    assert "workspace_members" in str(req.url)

def test_cross_workspace_access_rejection():
    # User B is NOT a member of Tenant A workspace
    user_b = "e7d9742e-4a17-40e9-8589-60af3c3028dc"
    workspace_repository.seed_workspace("ws_tenant_a_target", "Tenant A Target", "tenant-a-target")
    token_b = jwt.encode({
        "sub": user_b,
        "email": "attacker@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    # Attempting to access Tenant A messages while providing valid token of User B
    response = client.get(
        "/api/v1/workspaces/current/messages",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Workspace-Id": "ws_tenant_a_target",
        }
    )
    # Must be 403 Forbidden because user_b is not in ws_tenant_a_target
    assert response.status_code == 403
    assert "not a member" in response.json()["error"]["message"].lower()

# --- Phase 3C.3: Project Registry Tests ---

def test_project_registry_crud_and_tenancy_isolation():
    # 1. Setup Tenant Alpha with User Alpha
    user_alpha = "c3ed5f5a-8d13-4811-90e8-f569c1ea8bcc"
    ws_alpha = "ws_proj_alpha"
    workspace_repository.seed_workspace(ws_alpha, "Alpha Workspace", "alpha-ws")
    workspace_repository.seed_membership(ws_alpha, user_alpha, WorkspaceRole.OWNER)

    token_alpha = jwt.encode({
        "sub": user_alpha,
        "email": "alpha@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    # 2. Setup Tenant Beta with User Beta
    user_beta = "a7b42028-0040-45aa-aa85-9b43dca96cf5"
    ws_beta = "ws_proj_beta"
    workspace_repository.seed_workspace(ws_beta, "Beta Workspace", "beta-ws")
    workspace_repository.seed_membership(ws_beta, user_beta, WorkspaceRole.OWNER)

    token_beta = jwt.encode({
        "sub": user_beta,
        "email": "beta@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    # 3. Create Project in Workspace Alpha
    create_payload = {
        "title": "Quantum Ledger",
        "description": "Distributed ledger engine with quantum resistance.",
        "project_type": "software",
        "technologies": ["Rust", "Cryptography"],
    }
    create_res = client.post(
        "/api/v1/workspaces/current/projects",
        headers={
            "Authorization": f"Bearer {token_alpha}",
            "X-Workspace-Id": ws_alpha,
        },
        json=create_payload,
    )
    assert create_res.status_code == 201
    created_proj = create_res.json()
    assert created_proj["title"] == "Quantum Ledger"
    assert created_proj["slug"] == "quantum-ledger"
    assert created_proj["workspace_id"] == ws_alpha
    assert created_proj["status"] == "active"
    proj_id = created_proj["id"]

    # 4. Listing in Alpha returns created project
    list_alpha = client.get(
        "/api/v1/workspaces/current/projects",
        headers={
            "Authorization": f"Bearer {token_alpha}",
            "X-Workspace-Id": ws_alpha,
        },
    )
    assert list_alpha.status_code == 200
    alpha_projects = list_alpha.json()
    assert any(p["id"] == proj_id for p in alpha_projects)

    # 5. Listing in Beta DOES NOT leak Alpha's project (Empty or disjoint)
    list_beta = client.get(
        "/api/v1/workspaces/current/projects",
        headers={
            "Authorization": f"Bearer {token_beta}",
            "X-Workspace-Id": ws_beta,
        },
    )
    assert list_beta.status_code == 200
    beta_projects = list_beta.json()
    assert not any(p["id"] == proj_id for p in beta_projects)

    # 6. Detail in Alpha succeeds
    detail_res = client.get(
        f"/api/v1/workspaces/current/projects/{proj_id}",
        headers={
            "Authorization": f"Bearer {token_alpha}",
            "X-Workspace-Id": ws_alpha,
        },
    )
    assert detail_res.status_code == 200
    assert detail_res.json()["title"] == "Quantum Ledger"

    # 7. Cross-Workspace IDOR Rejection: User Beta requesting Alpha's project via Beta's workspace returns 404
    cross_res = client.get(
        f"/api/v1/workspaces/current/projects/{proj_id}",
        headers={
            "Authorization": f"Bearer {token_beta}",
            "X-Workspace-Id": ws_beta,
        },
    )
    assert cross_res.status_code == 404

    # 8. Cross-Workspace Rejection: User Beta sending Alpha's workspace returns 403 Forbidden
    alien_ws_res = client.get(
        f"/api/v1/workspaces/current/projects/{proj_id}",
        headers={
            "Authorization": f"Bearer {token_beta}",
            "X-Workspace-Id": ws_alpha,
        },
    )
    assert alien_ws_res.status_code == 403

    # 9. Update Project
    update_res = client.patch(
        f"/api/v1/workspaces/current/projects/{proj_id}",
        headers={
            "Authorization": f"Bearer {token_alpha}",
            "X-Workspace-Id": ws_alpha,
        },
        json={"tagline": "High performance cryptographic store"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["tagline"] == "High performance cryptographic store"

    # 10. Archive Project (Soft delete)
    archive_res = client.delete(
        f"/api/v1/workspaces/current/projects/{proj_id}",
        headers={
            "Authorization": f"Bearer {token_alpha}",
            "X-Workspace-Id": ws_alpha,
        },
    )
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "archived"

    # 11. Unauthenticated creation is rejected (401)
    unauth_create = client.post(
        "/api/v1/workspaces/current/projects",
        headers={"X-Workspace-Id": ws_alpha},
        json={"title": "Hacker Proj"},
    )
    assert unauth_create.status_code == 401

    # 12. Missing workspace header is rejected (400)
    no_ws_create = client.post(
        "/api/v1/workspaces/current/projects",
        headers={"Authorization": f"Bearer {token_alpha}"},
        json={"title": "No Workspace Proj"},
    )
    assert no_ws_create.status_code == 400

    # 13. Client-supplied workspace_id cannot override authorized workspace
    tamper_create = client.post(
        "/api/v1/workspaces/current/projects",
        headers={
            "Authorization": f"Bearer {token_alpha}",
            "X-Workspace-Id": ws_alpha,
        },
        json={
            "title": "Tampered Ownership",
            "workspace_id": ws_beta,  # Client attempts to assign project to Workspace Beta
        },
    )
    assert tamper_create.status_code == 201
    assert tamper_create.json()["workspace_id"] == ws_alpha  # Must remain Workspace Alpha

    # 14. Slug collision handling: identical title in same workspace generates unique hyphenated slug
    dup_slug_create = client.post(
        "/api/v1/workspaces/current/projects",
        headers={
            "Authorization": f"Bearer {token_alpha}",
            "X-Workspace-Id": ws_alpha,
        },
        json={"title": "Quantum Ledger"},
    )
    assert dup_slug_create.status_code == 201
    assert dup_slug_create.json()["slug"] == "quantum-ledger-1"

    # 15. Same slug can exist independently across different workspaces
    beta_slug_create = client.post(
        "/api/v1/workspaces/current/projects",
        headers={
            "Authorization": f"Bearer {token_beta}",
            "X-Workspace-Id": ws_beta,
        },
        json={"title": "Quantum Ledger"},
    )
    assert beta_slug_create.status_code == 201
    assert beta_slug_create.json()["slug"] == "quantum-ledger"
    assert beta_slug_create.json()["workspace_id"] == ws_beta

    # 16. Empty workspace returns clean empty list with zero fabricated projects
    user_empty = "acb8e99d-29a5-42ae-9fd8-a315f191ed3c"
    ws_empty = "ws_proj_empty"
    workspace_repository.seed_workspace(ws_empty, "Empty Workspace", "empty-ws")
    workspace_repository.seed_membership(ws_empty, user_empty, WorkspaceRole.MEMBER)
    token_empty = jwt.encode({
        "sub": user_empty,
        "email": "empty@ikigai.internal",
        "aud": "authenticated",
        "iss": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
        "exp": int(time.time()) + 3600,
    }, settings.SUPABASE_JWT_SECRET, algorithm="HS256")

    empty_list_res = client.get(
        "/api/v1/workspaces/current/projects",
        headers={
            "Authorization": f"Bearer {token_empty}",
            "X-Workspace-Id": ws_empty,
        },
    )
    assert empty_list_res.status_code == 200
    assert empty_list_res.json() == []






