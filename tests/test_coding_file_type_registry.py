from __future__ import annotations

from app.api.coding_file_type_registry import detect_file_type


def test_chunk1_file_type_detection_matrix():
    expected = {
        "main.py": "python_code",
        "client.ts": "typescript_code",
        "Component.tsx": "typescript_react_code",
        "view.js": "javascript_code",
        "Widget.jsx": "javascript_react_code",
        "config.json": "json_data",
        "config.yml": "yaml_data",
        "settings.toml": "toml_data",
        "setup.ini": "ini_config",
        "README": "project_readme",
        "LICENSE": "license_doc",
        "CHANGELOG.md": "changelog_doc",
        "notes.md": "markdown_doc",
        "data.csv": "csv_data",
        "data.tsv": "tsv_data",
        "example.xml": "xml_markup",
        "index.html": "html_markup",
        "style.css": "css_style",
        "query.sql": "sql_script",
        "script.sh": "shell_script",
        ".env": "blocked_secret_env",
        ".env.example": "env_example",
        ".gitignore": "gitignore",
        "Dockerfile": "dockerfile",
        "docker-compose.yml": "docker_compose_yaml",
        "package.json": "package_json",
        "package-lock.json": "package_lock_json",
        "Cargo.toml": "cargo_toml",
        "Cargo.lock": "cargo_lock",
        "requirements.txt": "requirements_txt",
    }

    for filename, type_id in expected.items():
        assert detect_file_type(filename).type_id == type_id


def test_env_is_blocked_but_env_example_is_allowed():
    env = detect_file_type(".env")
    example = detect_file_type(".env.example")

    assert env.readable is False
    assert env.patchable is False
    assert env.secret_sensitive is True
    assert example.readable is True
    assert example.patchable is True
    assert example.secret_sensitive is True
