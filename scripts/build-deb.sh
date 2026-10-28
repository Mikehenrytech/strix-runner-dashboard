#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"

VERSION="${1:-}"
if [ -z "${VERSION}" ]; then
    VERSION="$(python3 -c "import pathlib, re; text = pathlib.Path('${BACKEND_DIR}/src/strix_dashboard/__init__.py').read_text(); print(re.search(r'__version__\\s*=\\s*\"([^\"]+)\"', text).group(1))")"
fi

PKG_NAME="strix-runner-dashboard"
PKG_VERSION="${VERSION}-1"
PKG_DIR="${PROJECT_ROOT}/build/${PKG_NAME}_${PKG_VERSION}_amd64"
DEB_PATH="${PROJECT_ROOT}/build/${PKG_NAME}_${PKG_VERSION}_amd64.deb"

echo "Building ${PKG_NAME} ${PKG_VERSION}"

# Clean previous build
rm -rf "${PKG_DIR}" "${DEB_PATH}"
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/opt/${PKG_NAME}/backend/src"
mkdir -p "${PKG_DIR}/opt/${PKG_NAME}/frontend"

# Build frontend
echo "Building frontend..."
(
    cd "${FRONTEND_DIR}"
    if command -v pnpm >/dev/null 2>&1; then
        pnpm install --frozen-lockfile
        pnpm run build
    else
        npm ci
        npm run build
    fi
)

# Copy backend source into the package first so the venv is self-contained
cp -r "${BACKEND_DIR}/src/strix_dashboard" "${BACKEND_DIR}/pyproject.toml" "${PKG_DIR}/opt/${PKG_NAME}/backend/"

# Create Python virtual environment with backend dependencies
echo "Creating Python virtual environment..."
python3 -m venv "${PKG_DIR}/opt/${PKG_NAME}/backend/.venv"
"${PKG_DIR}/opt/${PKG_NAME}/backend/.venv/bin/pip" install --upgrade pip
"${PKG_DIR}/opt/${PKG_NAME}/backend/.venv/bin/pip" install \
    "${PKG_DIR}/opt/${PKG_NAME}/backend" \
    fastapi "uvicorn[standard]"

# Copy frontend build
cp -r "${FRONTEND_DIR}/dist" "${PKG_DIR}/opt/${PKG_NAME}/frontend/dist"

# Copy control file and substitute version
sed "s/{{VERSION}}/${VERSION}/" "${PROJECT_ROOT}/packaging/deb/control" > "${PKG_DIR}/DEBIAN/control"

# Copy entry point
cp "${PROJECT_ROOT}/packaging/deb/strix-dashboard" "${PKG_DIR}/usr/bin/strix-dashboard"
chmod +x "${PKG_DIR}/usr/bin/strix-dashboard"

# Build .deb
dpkg-deb --build "${PKG_DIR}" "${DEB_PATH}"

# Generate checksum
cd "${PROJECT_ROOT}/build"
sha256sum "${PKG_NAME}_${PKG_VERSION}_amd64.deb" > "${PKG_NAME}_${PKG_VERSION}_amd64.deb.sha256"

echo "Built: ${DEB_PATH}"
