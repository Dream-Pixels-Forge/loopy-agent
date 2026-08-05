#!/bin/bash
# Release helper — bump version, commit, tag, push
# Usage: ./scripts/release.sh 0.5.1

set -e

VERSION=${1:?Usage: ./scripts/release.sh <version>}

echo "🔄 Releasing loopy-agent v${VERSION}..."

# 1. Bump version in pyproject.toml
sed -i "s/^version = .*/version = \"${VERSION}\"/" pyproject.toml
echo "✅ pyproject.toml → v${VERSION}"

# 2. Bump version in _version.py (canonical source; __init__.py re-exports it)
sed -i "s/^__version__ = .*/__version__ = \"${VERSION}\"/" loopy/_version.py
echo "✅ _version.py → v${VERSION}"

# 3. Run tests
echo "🧪 Running tests..."
python -m pytest --tb=short -q
echo "✅ Tests pass"

# 4. Run lint
echo "🔍 Running lint..."
ruff check loopy/
echo "✅ Lint clean"

# 5. Commit
git add -A
git commit -m "release: v${VERSION}"
echo "✅ Committed"

# 6. Tag
git tag "v${VERSION}"
echo "✅ Tagged v${VERSION}"

# 7. Push
git push && git push --tags
echo "✅ Pushed to GitHub"

echo ""
echo "🎉 Done! GitHub Actions will now:"
echo "   1. Run tests"
echo "   2. Build wheel + sdist"
echo "   3. Create GitHub Release"
echo "   4. Publish to PyPI"
echo ""
echo "   Monitor: https://github.com/Dream-Pixels-Forge/loopy-agent/actions"
echo "   PyPI:    https://pypi.org/project/loopy-agent/${VERSION}/"
