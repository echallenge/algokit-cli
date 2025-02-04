import os
from importlib import metadata
from time import time

import pytest
from algokit.core.conf import PACKAGE_NAME
from algokit.core.version_prompt import LATEST_URL, VERSION_CHECK_INTERVAL
from approvaltests.scrubbers.scrubbers import Scrubber, combine_scrubbers
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture
from utils.app_dir_mock import AppDirs
from utils.approvals import normalize_path, verify
from utils.click_invoker import invoke

CURRENT_VERSION = metadata.version(PACKAGE_NAME)
NEW_VERSION = "999.99.99"


def make_scrubber(app_dir_mock: AppDirs) -> Scrubber:
    return combine_scrubbers(
        lambda x: normalize_path(x, str(app_dir_mock.app_config_dir), "{app_config}"),
        lambda x: normalize_path(x, str(app_dir_mock.app_state_dir), "{app_state}"),
        lambda x: x.replace(CURRENT_VERSION, "{current_version}"),
        lambda x: x.replace(NEW_VERSION, "{new_version}"),
    )


@pytest.fixture(autouse=True)
def setup(mocker: MockerFixture, app_dir_mock: AppDirs) -> None:
    mocker.patch("algokit.core.version_prompt.get_app_config_dir").return_value = app_dir_mock.app_config_dir
    mocker.patch("algokit.core.version_prompt.get_app_state_dir").return_value = app_dir_mock.app_state_dir
    # make bootstrap env a no-op
    mocker.patch("algokit.cli.bootstrap.bootstrap_env")


def test_version_check_queries_github_when_no_cache(app_dir_mock: AppDirs, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=LATEST_URL, json={"tag_name": f"v{NEW_VERSION}"})

    # bootstrap env is a nice simple command we can use to test the version check side effects
    result = invoke("bootstrap env", skip_version_check=False)

    assert result.exit_code == 0
    verify(result.output, scrubber=make_scrubber(app_dir_mock))


def test_version_check_uses_cache(app_dir_mock: AppDirs):
    version_cache = app_dir_mock.app_state_dir / "last-version-check"
    version_cache.write_text("1234.56.78", encoding="utf-8")
    result = invoke("bootstrap env", skip_version_check=False)

    assert result.exit_code == 0
    verify(result.output, scrubber=make_scrubber(app_dir_mock))


def test_version_check_queries_github_when_cache_out_of_date(app_dir_mock: AppDirs, httpx_mock: HTTPXMock):
    httpx_mock.add_response(url=LATEST_URL, json={"tag_name": f"v{NEW_VERSION}"})
    version_cache = app_dir_mock.app_state_dir / "last-version-check"
    version_cache.write_text("1234.56.78", encoding="utf-8")
    modified_time = time() - VERSION_CHECK_INTERVAL - 1
    os.utime(version_cache, (modified_time, modified_time))

    result = invoke("bootstrap env", skip_version_check=False)

    assert result.exit_code == 0
    verify(result.output, scrubber=make_scrubber(app_dir_mock))


def test_version_check_respects_disable_config(app_dir_mock: AppDirs):
    (app_dir_mock.app_config_dir / "disable-version-prompt").touch()
    result = invoke("bootstrap env", skip_version_check=False)

    assert result.exit_code == 0
    verify(result.output, scrubber=make_scrubber(app_dir_mock))


def test_version_check_respects_skip_option(app_dir_mock: AppDirs):
    result = invoke("--skip-version-check bootstrap env", skip_version_check=False)

    assert result.exit_code == 0
    assert len(result.output.strip()) == 0


def test_version_check_disable_version_check(app_dir_mock: AppDirs):
    disable_version_check_path = app_dir_mock.app_config_dir / "disable-version-prompt"
    result = invoke("config version-prompt disable")

    assert result.exit_code == 0
    assert disable_version_check_path.exists()
    verify(result.output, scrubber=make_scrubber(app_dir_mock))


def test_version_check_enable_version_check(app_dir_mock: AppDirs):
    disable_version_check_path = app_dir_mock.app_config_dir / "disable-version-prompt"
    disable_version_check_path.touch()
    result = invoke("config version-prompt enable")

    assert result.exit_code == 0
    assert not disable_version_check_path.exists()
    verify(result.output, scrubber=make_scrubber(app_dir_mock))
