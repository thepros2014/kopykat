import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use test SQLite in-memory DB
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-32-chars-long-strictly-set"
os.environ["INTEGRATION_ENCRYPTION_KEY"] = "wB2tN4a-7iL3sZ_qU8rX0vY5mP1oJ9eK6cF_dG4hA8s="
os.environ["OPENAI_API_KEY"] = "test-openai-key"
os.environ["GEMINI_API_KEY"] = "test-gemini-key"
os.environ["ENVIRONMENT"] = "testing"

from server.database import Base, get_db, User
from server.main import app
from server.auth import create_access_token, hash_password

test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def db_session():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture
def test_user(db_session):
    user = User(
        id="test-user-id-12345",
        email="testowner@example.com",
        hashed_password=hash_password("Password123!"),
        full_name="Test Store Owner",
        plan="boutique",
        generations=10,
        monthly_limit=250,
        is_active=True,
        is_verified=False
    )
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture
def auth_headers(test_user):
    token = create_access_token(test_user.id, test_user.email)
    return {"Authorization": f"Bearer {token}"}
