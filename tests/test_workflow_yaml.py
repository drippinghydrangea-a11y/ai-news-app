from pathlib import Path

import yaml


def test_workflow_yaml_is_valid_and_has_schedule_and_dispatch():
    workflow_path = (
        Path(__file__).parent.parent / ".github" / "workflows" / "update-news.yml"
    )

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = yaml.safe_load(f)

    # PyYAML(YAML 1.1)は `on:` を真偽値キー True としてパースするため両方を許容する
    on_section = workflow.get("on", workflow.get(True))
    assert on_section is not None
    assert on_section["schedule"][0]["cron"] == "0 22 * * *"
    assert "workflow_dispatch" in on_section
