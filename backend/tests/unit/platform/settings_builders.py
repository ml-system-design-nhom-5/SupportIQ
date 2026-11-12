"""Settings for tests that read only the given values, never the environment (TEST-17)."""

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from supportiq_backend.platform.settings import Settings

TEST_APP_URL = "postgresql+asyncpg://supportiq_app:app-test-password@127.0.0.1:5433/supportiq"
TEST_ORIGIN = "http://shop.test"
TEST_AI_SERVICE_URL = "http://ai-service.test"
TEST_AI_SERVICE_TOKEN = "ai-service-test-token"


class SettingsWithoutEnvironment(Settings):
    """The settings of backend, validated from the given values only."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Keep only the values given to the class, so a developer's environment never leaks in.

        Args:
            settings_cls: The settings class.
            init_settings: The values given to the class.
            env_settings: The environment variables, ignored.
            dotenv_settings: The dotenv file, ignored.
            file_secret_settings: The secret files, ignored.

        Returns:
            The single source of given values.
        """
        del settings_cls, env_settings, dotenv_settings, file_secret_settings
        return (init_settings,)


def build_test_settings(**values: object) -> Settings:
    """Build valid settings from the required values and the given overrides.

    Args:
        **values: Settings that replace the required test values or the initial values.

    Returns:
        The validated settings.
    """
    required: dict[str, object] = {
        "database_url_app": TEST_APP_URL,
        "allowed_origins": (TEST_ORIGIN,),
        "ai_service_base_url": TEST_AI_SERVICE_URL,
        "ai_service_token": TEST_AI_SERVICE_TOKEN,
    }
    return SettingsWithoutEnvironment.model_validate(required | values)
