# Local Release Publishing

This project intentionally does not use a GitHub Actions Python publishing workflow. Do not restore `.github/workflows/python-publish.yml` during release work.

Use the local publish script from the Git mirror instead:

```powershell
cd "D:\codex\GOH\Blender GOH Gem Exporter Git"
powershell -ExecutionPolicy Bypass -File .\tools\publish_release.ps1 -Version 1.5.0
```

The script performs the release path that has been used for recent addon releases:

- reads a GitHub token from `GH_TOKEN` or from `git credential fill`;
- uses `gh` for GitHub release creation and asset upload;
- refuses to publish if the removed `python-publish.yml` workflow exists locally;
- runs compile, smoke, Blender regression, humanskin import/export, and 5-iteration random import checks unless `-SkipValidation` is passed;
- backs up the unencrypted development tree into the `Unlock` folder unless `-SkipBackup` is passed;
- builds the protected release zips into the development `dist` folder;
- commits pending release files, creates an annotated tag, pushes `main` and the tag, creates the GitHub release, uploads both zip assets, and verifies that the tag is an ancestor of `origin/main`.

`gh auth status` may still report that no persistent login exists if the stored Git token lacks optional scopes such as `read:org`. That is acceptable for this workflow: the script injects the token into `GH_TOKEN` for the current process and verifies `gh repo view` before publishing.

Useful dry run:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\publish_release.ps1 -Version 1.5.0 -DryRun -SkipValidation -SkipBackup -SkipPackage
```

For an existing release, use `-ReplaceExistingRelease` only when intentionally replacing the uploaded assets for the same tag.
