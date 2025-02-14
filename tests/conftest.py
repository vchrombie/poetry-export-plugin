import shutil
import sys
import tempfile

from pathlib import Path
from typing import Any
from typing import Dict

import pytest

from poetry.config.config import Config as BaseConfig
from poetry.config.dict_config_source import DictConfigSource
from poetry.core.packages.package import Package
from poetry.factory import Factory
from poetry.layouts import layout
from poetry.repositories.pool import Pool
from poetry.repositories.repository import Repository
from poetry.utils.env import SystemEnv

from tests.helpers import TestLocker


class Config(BaseConfig):
    def get(self, setting_name: str, default: Any = None) -> Any:
        self.merge(self._config_source.config)
        self.merge(self._auth_config_source.config)

        return super(Config, self).get(setting_name, default=default)

    def raw(self) -> Dict[str, Any]:
        self.merge(self._config_source.config)
        self.merge(self._auth_config_source.config)

        return super(Config, self).raw()

    def all(self) -> Dict[str, Any]:
        self.merge(self._config_source.config)
        self.merge(self._auth_config_source.config)

        return super(Config, self).all()


@pytest.fixture
def config_cache_dir(tmp_dir):
    path = Path(tmp_dir) / ".cache" / "pypoetry"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def config_virtualenvs_path(config_cache_dir):
    return config_cache_dir / "virtualenvs"


@pytest.fixture
def config_source(config_cache_dir):
    source = DictConfigSource()
    source.add_property("cache-dir", str(config_cache_dir))

    return source


@pytest.fixture
def auth_config_source():
    source = DictConfigSource()

    return source


@pytest.fixture
def config(config_source, auth_config_source, mocker):
    import keyring

    from keyring.backends.fail import Keyring

    keyring.set_keyring(Keyring())

    c = Config()
    c.merge(config_source.config)
    c.set_config_source(config_source)
    c.set_auth_config_source(auth_config_source)

    mocker.patch("poetry.factory.Factory.create_config", return_value=c)
    mocker.patch("poetry.config.config.Config.set_config_source")

    return c


@pytest.fixture
def tmp_dir():
    dir_ = tempfile.mkdtemp(prefix="poetry_")

    yield dir_

    shutil.rmtree(dir_)


@pytest.fixture
def fixture_dir():
    def _fixture_dir(fixture):
        return Path(__file__).parent.joinpath("fixtures").joinpath(fixture)

    return _fixture_dir


@pytest.fixture()
def repo():
    return Repository()


@pytest.fixture
def installed():
    return Repository()


@pytest.fixture(scope="session")
def current_env():
    return SystemEnv(Path(sys.executable))


@pytest.fixture(scope="session")
def current_python(current_env):
    return current_env.version_info[:3]


@pytest.fixture(scope="session")
def default_python(current_python):
    return "^{}".format(".".join(str(v) for v in current_python[:2]))


@pytest.fixture
def project_factory(tmp_dir, config, repo, installed, default_python):
    workspace = Path(tmp_dir)

    def _factory(
        name=None,
        dependencies=None,
        dev_dependencies=None,
        pyproject_content=None,
        poetry_lock_content=None,
        install_deps=True,
    ):
        project_dir = workspace / "poetry-fixture-{}".format(name)
        dependencies = dependencies or {}
        dev_dependencies = dev_dependencies or {}

        if pyproject_content:
            project_dir.mkdir(parents=True, exist_ok=True)
            with project_dir.joinpath("pyproject.toml").open(
                "w", encoding="utf-8"
            ) as f:
                f.write(pyproject_content)
        else:
            layout("src")(
                name,
                "0.1.0",
                author="PyTest Tester <mc.testy@testface.com>",
                readme_format="md",
                python=default_python,
                dependencies=dependencies,
                dev_dependencies=dev_dependencies,
            ).create(project_dir, with_tests=False)

        if poetry_lock_content:
            lock_file = project_dir / "poetry.lock"
            lock_file.write_text(data=poetry_lock_content, encoding="utf-8")

        poetry = Factory().create_poetry(project_dir)

        locker = TestLocker(
            poetry.locker.lock.path, poetry.locker._local_config
        )  # noqa
        locker.write()

        poetry.set_locker(locker)
        poetry.set_config(config)

        pool = Pool()
        pool.add_repository(repo)

        poetry.set_pool(pool)

        if install_deps:
            for deps in [dependencies, dev_dependencies]:
                for name, version in deps.items():
                    pkg = Package(name, version)
                    repo.add_package(pkg)
                    installed.add_package(pkg)

        return poetry

    return _factory
