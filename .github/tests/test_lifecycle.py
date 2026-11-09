import contextlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github/scripts"))
import release
import source_version as source


@contextlib.contextmanager
def cwd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def git(path, *args):
    location = ["--git-dir", str(path)] if path.name.endswith(".git") else ["-C", str(path)]
    return subprocess.run(
        ["git", *location, *args], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def copy_source(destination):
    for path in source.SOURCE_PATHS:
        (destination / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, destination / path)


def entry(tag="v9.8.7", draft=False):
    return {"id": 42, "tag_name": tag, "draft": draft, "prerelease": False}


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        copy_source(self.root)
        self.current = source.read(self.root)

    def plist(self, **values):
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        data.update(values)
        path.write_bytes(plistlib.dumps(data))

    def test_live_source_and_all_modes(self):
        parts = list(map(int, self.current.split(".")))
        for mode, expected in (
            ("patch", [parts[0], parts[1], parts[2] + 1]),
            ("minor", [parts[0], parts[1] + 1, 0]),
            ("major", [parts[0] + 1, 0, 0]),
        ):
            with self.subTest(mode=mode):
                copy_source(self.root)
                original = (self.root / source.LOCALIZED).read_bytes()
                new = ".".join(map(str, expected))
                self.assertEqual(source.bump(mode, self.root), new)
                self.assertEqual(source.read(self.root), new)
                self.assertEqual((self.root / source.LOCALIZED).read_bytes(),
                                 original.replace(self.current.encode(), new.encode()))
                self.assertNotIn("CFBundleVersion",
                                 plistlib.loads((self.root / source.PLIST).read_bytes()))

    def test_stable_fixture_and_coordinated_contract(self):
        (self.root / source.PROJECT).write_text(
            "MARKETING_VERSION = 2.3.4;\nCURRENT_PROJECT_VERSION = 2.3.4;\n" * 3)
        (self.root / source.PLIST).write_bytes(plistlib.dumps({
            "CFBundleShortVersionString": "2.3.4", "CFBundleVersion": "2.3.4",
            "CFBundleInfoDictionaryVersion": "6.0",
        }))
        (self.root / source.LOCALIZED).write_text(
            'CFBundleShortVersionString = "2.3.4";\n'
            'CFBundleGetInfoString = "Audio version 2.3.4, Copyright 2014 miyako.";\n')
        self.assertEqual(source.bump("minor", self.root), "2.4.0")
        data = plistlib.loads((self.root / source.PLIST).read_bytes())
        self.assertEqual(data["CFBundleVersion"], "2.4.0")
        self.assertEqual(data["CFBundleInfoDictionaryVersion"], "6.0")
        path = self.root / source.PROJECT
        path.write_text(path.read_text().replace("CURRENT_PROJECT_VERSION = 2.4.0;",
                                                "CURRENT_PROJECT_VERSION = 99;"))
        with self.assertRaises(ValueError):
            source.read(self.root)

    def test_all_metadata_bytes_modes_bom_and_mixed_endings(self):
        for path in source.SOURCE_PATHS:
            target = self.root / path
            original = target.read_text(encoding="utf-8-sig")
            endings = ("\r\n", "\r", "\n")
            lines = original.splitlines()
            target.write_bytes(b"\xef\xbb\xbf" + "".join(
                line + endings[index % len(endings)] for index, line in enumerate(lines)
            ).encode())
            target.chmod(0o755)
        before = {path: (self.root / path).read_bytes() for path in source.SOURCE_PATHS}
        new = source.bump("patch", self.root)
        for path, original in before.items():
            self.assertEqual((self.root / path).read_bytes(),
                             original.replace(self.current.encode(), new.encode()))
            self.assertEqual((self.root / path).stat().st_mode & 0o777, 0o755)

    def test_quoted_settings_preserve_quotes(self):
        path = self.root / source.PROJECT
        path.write_text(path.read_text().replace(
            f"= {self.current};", f'= "{self.current}";'))
        original = path.read_bytes()
        new = source.bump("patch", self.root)
        self.assertEqual(path.read_bytes(), original.replace(self.current.encode(), new.encode()))
        self.assertEqual(source.read(self.root), new)

    def test_invalid_missing_and_drifted_settings(self):
        path = self.root / source.PROJECT
        original = path.read_text()
        different = "0.0.0" if self.current != "0.0.0" else "0.0.1"
        for key in source.KEYS:
            for bad in ("1.2", "v1.2.3", "01.2.3", "1.2.3-beta", "$(UNKNOWN)", "", different):
                with self.subTest(key=key, bad=bad):
                    path.write_text(original.replace(f"{key} = {self.current};",
                                                     f"{key} = {bad};", 1))
                    with self.assertRaises(ValueError):
                        source.bump("patch", self.root)
            path.write_text(original.replace(f"{key} = {self.current};", "", 1))
            with self.assertRaises(ValueError):
                source.read(self.root)

    def test_plist_invalid_drift_missing_and_wrong_root(self):
        for key in ("CFBundleShortVersionString", "CFBundleVersion"):
            for value in ("0.0.0" if self.current != "0.0.0" else "0.0.1",
                          "$(UNKNOWN)", "$(PRODUCT_NAME)", "", "1.2", 123):
                with self.subTest(key=key, value=value):
                    copy_source(self.root)
                    self.plist(**{key: value})
                    with self.assertRaises(ValueError):
                        source.read(self.root)
        copy_source(self.root)
        path = self.root / source.PLIST
        data = plistlib.loads(path.read_bytes())
        del data["CFBundleShortVersionString"]
        path.write_bytes(plistlib.dumps(data))
        with self.assertRaises(ValueError):
            source.read(self.root)
        path.write_bytes(plistlib.dumps([]))
        with self.assertRaises(ValueError):
            source.read(self.root)

    def test_valid_refs_optional_keys_and_cycles(self):
        for reference in source.REFERENCES:
            with self.subTest(reference=reference):
                copy_source(self.root)
                self.plist(CFBundleShortVersionString=reference, CFBundleVersion=reference)
                path = self.root / source.PROJECT
                path.write_text(path.read_text().replace(
                    f"CURRENT_PROJECT_VERSION = {self.current};",
                    'CURRENT_PROJECT_VERSION = "$(MARKETING_VERSION)";'))
                new = source.bump("patch", self.root)
                data = plistlib.loads((self.root / source.PLIST).read_bytes())
                self.assertEqual(data["CFBundleShortVersionString"], reference)
                self.assertEqual(data["CFBundleVersion"], reference)
                self.assertEqual(path.read_text().count('"$(MARKETING_VERSION)"'), 3)
                self.assertEqual(source.read(self.root), new)
        copy_source(self.root)
        path.write_text(path.read_text().replace(
            f"CURRENT_PROJECT_VERSION = {self.current};",
            'CURRENT_PROJECT_VERSION = "$(CURRENT_PROJECT_VERSION)";'))
        with self.assertRaises(ValueError):
            source.read(self.root)

    def test_localization_drift_missing_duplicate_bom_and_endings(self):
        path = self.root / source.LOCALIZED
        original = path.read_text(encoding="utf-8-sig")
        for malformed in (
            original.replace(f'CFBundleShortVersionString = "{self.current}"',
                             'CFBundleShortVersionString = "1.0"'),
            original.replace(f"version {self.current},", "version invalid,"),
            original + f'\nCFBundleShortVersionString = "{self.current}";\n',
            original.replace("CFBundleShortVersionString", "UnknownKey"),
        ):
            with self.subTest(malformed=malformed):
                path.write_text(malformed, encoding="utf-8-sig")
                with self.assertRaises(ValueError):
                    source.read(self.root)
        for newline in ("\n", "\r", "\r\n"):
            for bom in (b"", b"\xef\xbb\xbf"):
                copy_source(self.root)
                before = bom + original.replace("\n", newline).encode()
                path.write_bytes(before)
                new = source.bump("minor", self.root)
                self.assertEqual(path.read_bytes(), before.replace(self.current.encode(), new.encode()))

    def test_prebuilt_schema_and_4d_untouched(self):
        excluded = (
            "Audio.4dbase/Plugins/Audio.bundle/Contents/Info.plist",
            "English.lproj/locversion.plist", "manifest.json",
            "Audio.4dbase/Project/Audio.4DProject",
            "Audio.4dbase/Plugins/Audio.bundle/Contents/Resources/English.lproj/InfoPlist.strings",
        )
        for name in excluded:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / name).read_bytes())
        before = {name: (self.root / name).read_bytes() for name in excluded}
        source.bump("major", self.root)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in excluded})


class AvailabilityTests(unittest.TestCase):
    def test_page_two_draft_published_and_successful_absence(self):
        for draft in (True, False):
            with self.subTest(draft=draft), patch.object(release, "remote_ref", return_value=None), \
                    patch.object(release, "api", side_effect=[
                        [entry()] * 100, [entry("v1.2.3", draft)]
                    ]) as api:
                with self.assertRaisesRegex(ValueError, "draft or published"):
                    release.available("owner/repo", "v1.2.3")
                self.assertEqual(api.call_args_list[1].args[0],
                                 "repos/owner/repo/releases?per_page=100&page=2")
        with patch.object(release, "remote_ref", return_value=None), \
                patch.object(release, "api", side_effect=[[entry()] * 100, []]) as api:
            release.available("owner/repo", "v1.2.3")
            self.assertEqual(api.call_count, 2)

    def test_errors_and_malformed_every_page_fail_closed(self):
        errors = [
            *(subprocess.CalledProcessError(1, ["gh", "api", str(status)])
              for status in (401, 403, 404, 500)),
            OSError("network"), json.JSONDecodeError("bad", "?", 0),
        ]
        bad_pages = [{}, None, "[]", [None], [{}], [dict(entry(), id=True)],
                     [dict(entry(), id=0)], [dict(entry(), tag_name=None)],
                     [dict(entry(), tag_name="")], [dict(entry(), draft="false")],
                     [dict(entry(), prerelease=None)], [entry()] * 101]
        for page in (1, 2):
            for response in errors + bad_pages:
                with self.subTest(page=page, response=response), \
                        patch.object(release, "remote_ref", return_value=None), \
                        patch.object(release, "api", side_effect=(
                            [[entry()] * 100] * (page - 1) + [response])):
                    with self.assertRaises((ValueError, OSError, subprocess.CalledProcessError)):
                        release.available("owner/repo", "v1.2.3")

    def test_remote_errors_and_malformed_fail_closed(self):
        with patch.object(release, "remote_ref", return_value="a" * 40), \
                patch.object(release, "api") as api:
            with self.assertRaises(ValueError):
                release.available("o/r", "v1.2.3")
            api.assert_not_called()
        for output in ("invalid\trefs/tags/v1.2.3", "a" * 40,
                       "a" * 40 + "\trefs/tags/wrong",
                       ("a" * 40 + "\trefs/tags/v1.2.3\n") * 2):
            with self.subTest(output=output), patch.object(release, "run", return_value=output):
                with self.assertRaises(ValueError):
                    release.remote_ref("refs/tags/v1.2.3")
        with patch.object(release, "run", side_effect=OSError("network")):
            with self.assertRaises(OSError):
                release.available("o/r", "v1.2.3")

    def test_transport_explicit_methods_and_no_retry(self):
        with patch.object(release, "run", return_value="[]") as run:
            release.api("repos/o/r/releases?per_page=100&page=2")
            self.assertEqual(run.call_args.args, ("gh", "api", "--method", "GET",
                             "repos/o/r/releases?per_page=100&page=2"))
        with patch.object(release, "run", return_value='{"id": 7}') as run:
            payload = {"tag_name": "v1.2.3", "draft": False}
            release.api("repos/o/r/releases", payload)
            self.assertIn("POST", run.call_args.args)
            self.assertEqual(json.loads(run.call_args.kwargs["input"]), payload)
        with patch.object(release, "run", side_effect=subprocess.CalledProcessError(1, "gh")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                release.api("repos/o/r/releases")
            self.assertEqual(run.call_count, 1)
        with patch.object(release, "run", return_value='{"id": 8}') as run:
            asset = Path("Audio-1.2.3.zip")
            release.api("https://uploads.github.com/repos/o/r/releases/123/assets", asset=asset)
            self.assertEqual(run.call_args.args, (
                "gh", "api", "--method", "POST",
                "https://uploads.github.com/repos/o/r/releases/123/assets",
                "--header", "Content-Type: application/octet-stream", "--input", str(asset)))


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.local = self.root / "local"
        self.peer = self.root / "peer"
        git(self.root, "init", "--bare", str(self.remote))
        git(self.root, "init", "-b", "selected", str(self.local))
        for key, value in (("user.name", "Lifecycle Test"), ("user.email", "test@example.invalid"),
                           ("push.followTags", "true")):
            git(self.local, "config", key, value)
        git(self.local, "commit", "--allow-empty", "-m", "ancestor")
        self.ancestor = git(self.local, "rev-parse", "HEAD")
        copy_source(self.local)
        shutil.copytree(ROOT / ".github/scripts", self.local / ".github/scripts",
                        ignore=shutil.ignore_patterns("__pycache__"))
        git(self.local, "add", ".")
        git(self.local, "commit", "-m", "fixture")
        git(self.local, "remote", "add", "origin", str(self.remote))
        git(self.local, "push", "origin", "HEAD:refs/heads/selected")
        self.sha = git(self.local, "rev-parse", "HEAD")
        self.version = source.read(self.local)
        self.tag = f"v{self.version}"
        self.published = None
        self.uploaded = []
        git(self.root, "clone", "--branch", "selected", str(self.remote), str(self.peer))
        git(self.peer, "config", "user.name", "Peer")
        git(self.peer, "config", "user.email", "peer@example.invalid")
        self.enter = cwd(self.local)
        self.enter.__enter__()
        self.addCleanup(self.enter.__exit__, None, None, None)

    def advance_peer(self):
        (self.peer / "peer.txt").write_text("concurrent branch update")
        git(self.peer, "add", ".")
        git(self.peer, "commit", "-m", "peer")
        git(self.peer, "push", "origin", "HEAD:refs/heads/selected")

    def test_bump_only_explicit_branch_source_no_follow_tags(self):
        git(self.local, "tag", "-a", "unrelated-annotated", "-m", "must not follow")
        git(self.remote, "update-ref", "refs/heads/other", self.sha)
        release.bump_branch(self.sha, "selected", "patch")
        self.assertNotEqual(git(self.remote, "rev-parse", "refs/heads/selected"), self.sha)
        self.assertEqual(git(self.remote, "rev-parse", "refs/heads/other"), self.sha)
        self.assertEqual(git(self.remote, "tag", "--list"), "")
        self.assertEqual(git(self.local, "rev-parse", "HEAD^"), self.sha)
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assertEqual(set(git(self.local, "diff-tree", "--no-commit-id", "--name-only",
                                 "-r", "HEAD").splitlines()), set(map(str, source.SOURCE_PATHS)))

    def test_cli_bytecode_keeps_clean_checkout(self):
        env = os.environ.copy()
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        subprocess.run(
            [sys.executable, ".github/scripts/release.py", "bump", "--sha", self.sha,
             "--branch", "selected", "--mode", "patch"],
            env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(git(self.local, "status", "--porcelain"), "")
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_preparation_races(self):
        self.advance_peer()
        with self.assertRaisesRegex(ValueError, "moved"):
            release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)

    def test_race_during_preparation(self):
        real_bump = release.bump

        def concurrent_bump(mode):
            result = real_bump(mode)
            self.advance_peer()
            return result

        with patch.object(release, "bump", side_effect=concurrent_bump):
            with self.assertRaisesRegex(ValueError, "moved during"):
                release.bump_branch(self.sha, "selected", "minor")
        self.assertEqual(release.remote_ref("refs/heads/selected"),
                         git(self.peer, "rev-parse", "HEAD"))

    def advertised_race(self, kind):
        real_run = release.run
        expected = None
        pushes = 0

        def concurrent_push(*args, **kwargs):
            nonlocal expected, pushes
            # After the final ls-remote, before receive-pack advertisement.
            if "push" in args:
                pushes += 1
                if kind == "rewind":
                    expected = self.ancestor
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                elif kind == "delete":
                    git(self.remote, "update-ref", "-d", "refs/heads/selected")
                elif kind == "advance":
                    self.advance_peer()
                    expected = git(self.peer, "rev-parse", "HEAD")
                elif kind == "same-result":
                    expected = git(self.local, "rev-parse", "HEAD")
                    git(self.remote, "fetch", "--no-tags", str(self.local), "HEAD")
                    git(self.remote, "update-ref", "refs/heads/selected", expected)
                else:
                    self.fail(kind)
            return real_run(*args, **kwargs)

        with patch.object(release, "run", side_effect=concurrent_push):
            with self.assertRaises(subprocess.CalledProcessError):
                release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(pushes, 1)
        self.assertEqual(release.remote_ref("refs/heads/selected"), expected)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_advertised_rewind(self):
        self.advertised_race("rewind")

    def test_advertised_deletion(self):
        self.advertised_race("delete")

    def test_advertised_advance(self):
        self.advertised_race("advance")

    def test_advertised_same_result(self):
        self.advertised_race("same-result")

    def test_missing_nonexecutable_guard_and_dirty_source(self):
        guard = self.local / ".github/scripts/bump-hooks/pre-push"
        guard.chmod(0o644)
        for absent in (False, True):
            if absent:
                guard.unlink()
            with self.subTest(absent=absent), \
                    patch.object(release, "__file__", str(self.local / ".github/scripts/release.py")):
                with self.assertRaisesRegex(ValueError, "guard is missing or not executable"):
                    release.bump_branch(self.sha, "selected", "patch")
            self.assertEqual(git(self.local, "rev-parse", "HEAD"), self.sha)
        with self.assertRaisesRegex(ValueError, "clean checkout"):
            release.bump_branch(self.sha, "selected", "patch")

    def test_immutable_invalid_sha_and_branch(self):
        for sha in ("selected", "a" * 40, "a" * 39, "a" * 41):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                release.selected_sha(sha)
        release.selected_sha(self.sha)
        with self.assertRaises(subprocess.CalledProcessError):
            release.bump_branch(self.sha, "invalid..branch", "patch")

    def test_preflight_clean_and_final_source_drift(self):
        (self.local / source.PLIST).write_text("dirty source")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaisesRegex(ValueError, "clean source"):
                release.preflight(self.sha)
            api.assert_not_called()
        copy_source(self.local)
        paths = self.assets()
        source.bump("patch")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaisesRegex(ValueError, "differs from the selected commit"):
                release.publish(self.sha, paths)
            api.assert_not_called()
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_guard_local_sha_target_parent_and_missing_env(self):
        guard = ROOT / ".github/scripts/bump-hooks/pre-push"
        git(self.local, "commit", "--allow-empty", "-m", "direct child")
        new = git(self.local, "rev-parse", "HEAD")
        env = {**os.environ, "BUMP_EXPECTED_SHA": self.sha,
               "BUMP_EXPECTED_REF": "refs/heads/selected", "BUMP_NEW_SHA": new}
        valid = f"{new} {new} refs/heads/selected {self.sha}\n"
        result = subprocess.run([str(guard)], input=valid, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in (
            f"{new} {new} refs/heads/wrong {self.sha}\n",
            f"HEAD {new} refs/heads/selected {self.sha}\n",
            f"{new} {self.ancestor} refs/heads/selected {self.sha}\n",
            f"{new} {new} refs/heads/selected {self.ancestor}\n",
            valid * 2, "",
        ):
            result = subprocess.run([str(guard)], input=row, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode, 0)
        result = subprocess.run([str(guard)], input=valid, env={}, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(result.returncode, 0)

    def test_guard_disappearing_during_preparation(self):
        guard = ROOT / ".github/scripts/bump-hooks/pre-push"
        real_access = os.access
        calls = 0

        def vanished(path, mode):
            nonlocal calls
            if path == guard:
                calls += 1
                return calls == 1
            return real_access(path, mode)

        with patch.object(release.os, "access", side_effect=vanished):
            with self.assertRaisesRegex(ValueError, "guard is missing or not executable"):
                release.bump_branch(self.sha, "selected", "patch")
        self.assertEqual(calls, 2)
        self.assertEqual(release.remote_ref("refs/heads/selected"), self.sha)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def assets(self):
        paths = [Path(f"Audio-{self.version}.{ext}") for ext in ("zip", "dmg")]
        for asset in paths:
            asset.write_bytes(b"fixture asset")
        return paths

    def publication_api(self, calls, fail=None, race=None):
        def api(endpoint, payload=None, asset=None):
            calls.append((endpoint, payload, asset))
            if "/releases?" in endpoint:
                return []
            if endpoint.endswith("/git/refs"):
                if race:
                    git(self.remote, "update-ref", f"refs/tags/{self.tag}", race)
                # Atomic create-only bare Git models POST refs, including same-SHA rejection.
                git(self.remote, "update-ref", payload["ref"], payload["sha"], "0" * 40)
                return {"ref": payload["ref"], "object": {"sha": payload["sha"]}}
            if endpoint.endswith("/releases"):
                if fail == "release":
                    raise subprocess.CalledProcessError(1, ["gh", "api"])
                self.published = {"id": 123, "tag_name": self.tag, "draft": False, "prerelease": False}
                return self.published
            if asset is not None:
                if fail == asset.suffix:
                    raise subprocess.CalledProcessError(1, ["gh", "api"])
                self.uploaded.append(asset.name)
                return {"id": 456, "name": asset.name,
                        "size": asset.stat().st_size, "state": "uploaded"}
            raise AssertionError(endpoint)
        return api

    def test_create_only_sha_new_release_id_original_notes(self):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls)):
            release.publish(self.sha, self.assets())
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertIn("/releases?", calls[0][0])
        self.assertTrue(calls[1][0].endswith("/git/refs"))
        self.assertEqual(calls[2][1], {
            "tag_name": self.tag, "target_commitish": self.sha, "name": self.tag,
            "draft": False, "prerelease": False, "body": ""})
        self.assertEqual(len(calls), 5)
        for endpoint, payload, asset in calls[3:]:
            self.assertIn("/releases/123/assets?name=", endpoint)
            self.assertIsNone(payload)
            self.assertIsNotNone(asset)

    def tag_race(self, sha):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls, race=sha)):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 2)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), sha)
        self.assertIsNone(self.published)

    def test_same_sha_tag_race(self):
        self.tag_race(self.sha)

    def test_different_sha_tag_race(self):
        self.advance_peer()
        self.tag_race(git(self.peer, "rev-parse", "HEAD"))

    def test_release_post_failure_retains_tag(self):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls, fail="release")):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 3)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertIsNone(self.published)
        self.assertEqual(self.uploaded, [])

    def test_upload_failure_retains_tag_release_earlier_asset(self):
        calls = []
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls, fail=".dmg")):
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 5)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)
        self.assertEqual(self.published["id"], 123)
        self.assertEqual(self.uploaded, [f"Audio-{self.version}.zip"])

    def test_final_recheck_new_draft(self):
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", return_value=[]):
            release.preflight(self.sha)
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", return_value=[entry(self.tag, True)]) as api:
            with self.assertRaisesRegex(ValueError, "draft or published"):
                release.publish(self.sha, self.assets())
            self.assertEqual(api.call_count, 1)
        self.assertEqual(git(self.remote, "tag", "--list"), "")

    def test_final_later_page_failure_stops_before_creation(self):
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", return_value=[]):
            release.preflight(self.sha)
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=[
                    [entry()] * 100, subprocess.CalledProcessError(1, ["gh", "api", "404"])
                ]) as api:
            with self.assertRaises(subprocess.CalledProcessError):
                release.publish(self.sha, self.assets())
            self.assertEqual(api.call_count, 2)
        self.assertEqual(git(self.remote, "tag", "--list"), "")
        self.assertIsNone(self.published)

    def test_remote_verification_blocks_release(self):
        calls = []
        real_remote_ref = release.remote_ref

        def incorrect_verification(ref):
            return "a" * 40 if real_remote_ref(ref) else None

        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api", side_effect=self.publication_api(calls)), \
                patch.object(release, "remote_ref", side_effect=incorrect_verification):
            with self.assertRaisesRegex(ValueError, "exact-SHA verification"):
                release.publish(self.sha, self.assets())
        self.assertEqual(len(calls), 2)
        self.assertIsNone(self.published)
        self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)

    def test_malformed_post_and_upload_retain_state(self):
        for kind in ("release", "upload"):
            with self.subTest(kind=kind):
                if kind == "upload":
                    git(self.remote, "update-ref", "-d", f"refs/tags/{self.tag}")
                calls = []
                real_api = self.publication_api(calls)

                def malformed(endpoint, payload=None, asset=None):
                    result = real_api(endpoint, payload, asset)
                    if (kind == "release" and endpoint.endswith("/releases")) or (
                            kind == "upload" and asset is not None):
                        return {"id": None}
                    return result

                with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                        patch.object(release, "api", side_effect=malformed):
                    with self.assertRaisesRegex(ValueError, "Malformed"):
                        release.publish(self.sha, self.assets())
                self.assertEqual(len(calls), 3 if kind == "release" else 4)
                self.assertEqual(self.published["id"], 123)
                self.assertEqual(git(self.remote, "rev-parse", f"refs/tags/{self.tag}"), self.sha)

    def test_missing_empty_wrong_assets_before_mutation(self):
        for paths in (
            [Path(f"Audio-{self.version}.{ext}") for ext in ("zip", "dmg")],
            [Path("wrong.zip"), Path("wrong.dmg")],
        ):
            with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                    patch.object(release, "api") as api:
                with self.assertRaises(ValueError):
                    release.publish(self.sha, paths)
                api.assert_not_called()
        paths = self.assets()
        paths[0].write_bytes(b"")
        with patch.dict(os.environ, GITHUB_REPOSITORY="owner/repo"), \
                patch.object(release, "api") as api:
            with self.assertRaises(ValueError):
                release.publish(self.sha, paths)
            api.assert_not_called()


class WiringTests(unittest.TestCase):
    def test_manual_zero_inputs_immutable_native_gate_wiring(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertRegex(workflow, r"(?m)^name: Build$")
        self.assertEqual(workflow.split("on:\n", 1)[1].split("\npermissions:", 1)[0].strip(),
                         "workflow_dispatch:")
        self.assertEqual(workflow.count("uses: actions/checkout@v4"), 2)
        self.assertEqual(workflow.count("ref: ${{ github.sha }}"), 2)
        self.assertIn("group: release-publication\n  cancel-in-progress: false", workflow)
        self.assertIn("needs: [version]", workflow)
        self.assertEqual(workflow.count("GH_TOKEN: ${{ github.token }}"), 2)
        self.assertIn('test "$REF_TYPE" = branch', workflow)
        gates = [
            "validate source version and publication availability",
            "import Developer ID certificate", "store notarytool credentials",
            "build macOS plugin (universal)", "verify universal binary",
            "- name: codesign",
            "package, notarize & staple", "recheck availability and create tag, release and assets",
        ]
        self.assertEqual([workflow.index(gate) for gate in gates],
                         sorted(workflow.index(gate) for gate in gates))
        for required in ('ARCHS="arm64 x86_64"', "ONLY_ACTIVE_ARCH=NO",
                         "codesign --verify --deep --strict", 'stapler staple "$DMG_PATH"',
                         'notarytool submit "$ZIP_PATH"', 'notarytool submit "$DMG_PATH"',
                         "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
                         "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID",
                         "NOTARYTOOL_PASSWORD", "runs-on: macos-latest",
                         "MACOS_DEPLOYMENT_TARGET: '11.0'",
                         "VCX_SOLUTION: Audio.sln", "XCODE_PROJECT: Audio.xcodeproj"):
            self.assertIn(required, workflow)
        for prohibited in ("continue-on-error", "always()", "inputs.", "softprops/",
                           "github.ref_name", "branches:", "refs/heads/master",
                           "build-windows", "windows-latest", "CODE_SIGNING_ALLOWED=NO"):
            self.assertNotIn(prohibited, workflow)
        final = workflow.split("- name: recheck availability", 1)[1]
        self.assertEqual(final.count("python3 "), 1)
        self.assertIn('publish --sha "$SELECTED_SHA" "$ZIP_PATH" "$DMG_PATH"', final)

    def test_native_steps_preserved_from_verified_baseline(self):
        baseline = git(ROOT, "show", "5d695b4f255c3c6c97ab47241480cdf92facb280:"
                       ".github/workflows/release.yml")
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        start = "      - name: import Developer ID certificate"
        original = baseline.split(start, 1)[1].split("      - name: create GitHub Release", 1)[0]
        current = workflow.split(start, 1)[1].split("      - name: recheck availability", 1)[0]
        self.assertEqual(current, original)

    def test_bump_no_tag_or_destructive_publication(self):
        workflow = (ROOT / ".github/workflows/bump-version.yml").read_text()
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("SELECTED_BRANCH: ${{ github.ref_name }}", workflow)
        self.assertIn('test "$REF_TYPE" = branch', workflow)
        for mode in ("patch", "minor", "major"):
            self.assertIn(f"- {mode}", workflow)
        helper = (ROOT / ".github/scripts/release.py").read_text()
        for prohibited in ('"DELETE"', '"PATCH"', "--clobber", "--force",
                           '"gh", "release", "create"', '"git", "tag"'):
            self.assertNotIn(prohibited, helper)
        self.assertIn('"push.followTags=false"', helper)
        self.assertIn('"--no-follow-tags"', helper)
        self.assertNotIn("workflow_dispatch", helper)

    def test_cli_asset_options(self):
        assets = [Path(f"Audio-1.2.3.{ext}") for ext in ("zip", "dmg")]
        with patch.object(sys, "argv", ["release.py", "publish", "--sha", "a" * 40,
                                       *map(str, assets)]), \
                patch.object(release, "publish") as publish:
            release.main()
        publish.assert_called_once_with("a" * 40, assets)


if __name__ == "__main__":
    unittest.main()
