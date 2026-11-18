import pytest


@pytest.fixture(autouse=True)
def default_email_verification(settings):
    # La configuration temporaire du poste ne doit pas désactiver les tests du parcours normal.
    settings.REQUIRE_EMAIL_VERIFICATION = True
