from pathlib import Path

from jk.jenkins.client import JenkinsConfig, _with_env_file

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = REPO_ROOT / ".env.example"
REQUIRED = ("JENKINS_URL", "JENKINS_USER_ID", "JENKINS_API_TOKEN")


def test_example_defines_exactly_the_required_keys():
    values = _with_env_file(EXAMPLE, {})
    assert set(values) == set(REQUIRED)
    for key in REQUIRED:
        assert values.get(key), f"{key} has no placeholder value"


def test_example_is_loadable_the_way_jk_loads_it(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(EXAMPLE.read_text())
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)

    config = JenkinsConfig.from_environment(tmp_path)

    assert config.base_url == "https://jenkins.ci.folio.org"
    assert config.user_id == "your-jenkins-user-id"
    assert config.api_token == "your-api-token"


def test_the_process_environment_wins_over_the_example_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(EXAMPLE.read_text())
    monkeypatch.setenv("JENKINS_URL", "https://shell-wins.invalid")
    monkeypatch.delenv("JENKINS_USER_ID", raising=False)
    monkeypatch.delenv("JENKINS_API_TOKEN", raising=False)

    config = JenkinsConfig.from_environment(tmp_path)

    assert config.base_url == "https://shell-wins.invalid"


def test_local_env_files_stay_git_ignored():
    assert ".env" in (REPO_ROOT / ".gitignore").read_text().split()
