import hashlib
import json
import subprocess
import sys

import check_assets as gate
import yaml

from conftest import ROOT, make_image


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tree(tmp_path, *, license="CC0", name="K04.jpg", listed=True, extra=None):
    """A tiny repository with one image, its manifest and one bundled case."""
    (tmp_path / "bench" / "golden" / "images").mkdir(parents=True)
    img = make_image(tmp_path / "bench" / "golden" / "images" / name)
    rel = f"bench/golden/images/{name}"
    assets = [{"path": rel, "sha256": sha(img), "kind": "product-photo", "license": license, "origin": "https://commons.wikimedia.org/wiki/File:X.jpg"}] if listed else []
    (tmp_path / "bench" / "ASSETS.json").write_text(json.dumps({"version": 1, "assets": assets}), encoding="utf-8")
    case = {"id": "K04", "name": "a lip balm", "subcategory": "Lipstick", "verb": "holding", "tags": [], "pose": "p",
            "source": {"kind": "bundled", "file": f"golden/images/{name}", "page": "https://e.org", "license": "CC0", "sha256": sha(img)}}
    (tmp_path / "bench" / "cases.yaml").write_text(yaml.safe_dump({"version": 1, "cases": [case]}), encoding="utf-8")
    for rel_path, text in (extra or {}).items():
        p = tmp_path / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def problems(root):
    return "\n".join(gate.run(root))


def test_the_repository_itself_is_clean():
    assert gate.run(ROOT) == []


def test_a_clean_tree_passes(tmp_path):
    assert gate.run(tree(tmp_path)) == []


def test_an_image_missing_from_the_manifest_is_refused(tmp_path):
    assert "not listed in bench/ASSETS.json" in problems(tree(tmp_path, listed=False))


def test_a_license_outside_the_allow_list_is_refused(tmp_path):
    assert "license 'CC BY-SA 3.0' is not one of" in problems(tree(tmp_path, license="CC BY-SA 3.0"))


def test_a_changed_image_is_refused(tmp_path):
    root = tree(tmp_path)
    make_image(root / "bench" / "golden" / "images" / "K04.jpg", (10, 10), (1, 1, 1))
    assert "sha256 differs from bench/ASSETS.json" in problems(root)


def test_a_manifest_entry_without_a_file_is_refused(tmp_path):
    root = tree(tmp_path)
    (root / "bench" / "golden" / "images" / "K04.jpg").unlink()
    assert "listed in bench/ASSETS.json but not in the repository" in problems(root)


def test_a_file_name_about_adult_content_or_lingerie_is_refused(tmp_path):
    out = problems(tree(tmp_path, name="lace_bralette_front.jpg"))
    assert "mentions bralette" in out
    assert "mentions" not in problems(tree(tmp_path / "ok", name="brand_front.jpg"))          # whole words only: "brand" is fine


def test_a_linked_image_must_not_be_committed(tmp_path):
    root = tree(tmp_path)
    case = yaml.safe_load((root / "bench" / "cases.yaml").read_text(encoding="utf-8"))
    img_sha = sha(root / "bench" / "golden" / "images" / "K04.jpg")
    case["cases"].append({"id": "L1", "name": "linked", "subcategory": "Rings", "verb": "wearing", "tags": [], "pose": "p",
                          "source": {"kind": "linked", "url": "https://upload.wikimedia.org/x.jpg", "page": "p", "license": "CC BY-SA 4.0", "sha256_source": img_sha}})
    (root / "bench" / "cases.yaml").write_text(yaml.safe_dump(case), encoding="utf-8")
    assert "the linked image is committed in the repository" in problems(root)


def test_a_bundled_case_must_be_cc0_or_public_domain(tmp_path):
    root = tree(tmp_path)
    case = yaml.safe_load((root / "bench" / "cases.yaml").read_text(encoding="utf-8"))
    case["cases"][0]["source"]["license"] = "CC BY 4.0"
    (root / "bench" / "cases.yaml").write_text(yaml.safe_dump(case), encoding="utf-8")
    assert "must be CC0 or public domain" in problems(root)


def test_secrets_local_paths_internal_names_and_emails_are_refused(tmp_path):
    fake_google_key = "AIza" + "x" * 35
    fake_gh_token = "ghp_" + "a" * 36
    out = problems(tree(tmp_path, extra={
        "docs/notes.md": f"key {fake_google_key}\ntoken {fake_gh_token}\nsee C:\\Users\\someone\\file and /Users/someone/x\n",
        "docs/more.md": "from wearai/wearai, mail me at someone@gmail.com",
        ".env": "GEMINI_API_KEY=abc",
        "bundle.zip": "x",
    }))
    for expected in ("a Google API key", "a GitHub token", "a local Windows path", "a local user path", "internal name (wearai/wearai)",
                     "e-mail address (someone@gmail.com)", ".env: a secrets or key file", "bundle.zip: .zip files"):
        assert expected in out, expected


def test_noreply_and_example_addresses_are_allowed(tmp_path):
    assert gate.run(tree(tmp_path, extra={"docs/a.md": "12345+name@users.noreply.github.com and a@example.com and noreply@anthropic.com"})) == []


def test_the_command_line_exit_code(tmp_path):
    clean = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_assets.py"), "--root", str(tree(tmp_path))], capture_output=True, text=True)
    assert clean.returncode == 0 and "clean" in clean.stdout
    dirty = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_assets.py"), "--root", str(tree(tmp_path / "d", license="CC BY-SA 3.0"))], capture_output=True, text=True)
    assert dirty.returncode == 1 and "PROBLEM" in dirty.stdout
