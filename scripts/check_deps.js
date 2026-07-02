#!/usr/bin/env node
const { execSync, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const COLOR = {
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  red: '\x1b[31m',
  cyan: '\x1b[36m',
  reset: '\x1b[0m',
};

const log = (msg) => console.log(`${COLOR.cyan}[check-deps]${COLOR.reset} ${msg}`);
const ok = (msg) => console.log(`  ${COLOR.green}✓${COLOR.reset} ${msg}`);
const warn = (msg) => console.log(`  ${COLOR.yellow}⚠${COLOR.reset} ${msg}`);
const fail = (msg) => console.log(`  ${COLOR.red}✗${COLOR.reset} ${msg}`);

const REQUIRED_SYSTEM_CMDS = [
  'xdotool', 'wmctrl', 'xclip', 'ffmpeg',
  'notify-send', 'pandoc', 'ssh',
];

const KEY_PYTHON_PACKAGES = ['loguru', 'python-telegram-bot', 'fastapi', 'uvicorn', 'pyotp'];

function run(cmd, opts = {}) {
  return execSync(cmd, { stdio: 'pipe', timeout: 60000, ...opts }).toString().trim();
}

function runAsync(cmd, args) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: 'inherit', shell: true });
    p.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`Exit code ${code}`))));
    p.on('error', reject);
  });
}

function detectPython() {
  for (const py of ['python3', 'python']) {
    try {
      const v = run(`${py} --version`, { stdio: 'pipe' });
      if (v.toLowerCase().includes('python')) return py;
    } catch {}
  }
  return null;
}

function getProjectRoot() {
  const selfPath = __dirname;
  if (fs.existsSync(path.join(selfPath, '..', 'package.json'))) return path.resolve(selfPath, '..');
  if (fs.existsSync(path.join(selfPath, 'package.json'))) return path.resolve(selfPath);
  return process.cwd();
}

async function checkSystemDeps() {
  log('Memeriksa system dependencies...');
  const missing = [];
  for (const cmd of REQUIRED_SYSTEM_CMDS) {
    try {
      execSync(`which ${cmd}`, { stdio: 'pipe' });
      ok(`${cmd} tersedia`);
    } catch {
      fail(`${cmd} tidak ditemukan`);
      missing.push(cmd);
    }
  }
  if (missing.length > 0) {
    warn(`System dependencies kurang: ${missing.join(', ')}`);
    console.log(`     Jalankan: bash ${path.join(getProjectRoot(), 'INSTALL_DEPS.sh')}`);
    console.log(`     (membutuhkan sudo untuk install apt packages)`);
  } else {
    ok('Semua system dependencies terpenuhi');
  }
}

async function checkPythonDeps(root) {
  log('Memeriksa Python environment...');
  const python = detectPython();
  if (!python) {
    fail('Python3 tidak ditemukan. Install python3 dan python3-venv dulu.');
    return;
  }
  ok(`Python: ${python}`);

  const venvDir = path.join(root, 'venv');
  const pipBin = path.join(venvDir, 'bin', 'pip');
  const pythonBin = path.join(venvDir, 'bin', 'python');

  if (!fs.existsSync(venvDir)) {
    warn('Virtual environment belum ada, membuat...');
    try {
      run(`${python} -m venv "${venvDir}"`);
      ok('Virtual environment dibuat');
    } catch (e) {
      fail(`Gagal buat venv: ${e.message}`);
      return;
    }
  } else {
    ok('Virtual environment sudah ada');
  }

  if (!fs.existsSync(pythonBin)) {
    fail(`Python binary tidak ditemukan di venv: ${pythonBin}`);
    return;
  }

  const reqFile = path.join(root, 'requirements.txt');
  if (!fs.existsSync(reqFile)) {
    warn('requirements.txt tidak ditemukan, skip pip install');
    return;
  }

  const missingPkgs = [];
  for (const pkg of KEY_PYTHON_PACKAGES) {
    try {
      execSync(`"${pythonBin}" -c "import ${pkg.replace(/-/g, '_').replace(/[^a-zA-Z0-9_]/g, '')}"`, {
        stdio: 'pipe',
        timeout: 10000,
      });
    } catch {
      missingPkgs.push(pkg);
    }
  }

  if (missingPkgs.length > 0) {
    warn(`Package Python kurang: ${missingPkgs.join(', ')}. Menginstall...`);
    try {
      run(`"${pipBin}" install -r "${reqFile}"`, { stdio: 'pipe', timeout: 120000 });
      ok('Semua Python packages terinstall');
    } catch (e) {
      fail(`Gagal install Python packages: ${e.message}`);
    }
  } else {
    ok('Semua Python packages terpenuhi');
  }
}

async function main() {
  console.log(`${COLOR.cyan}══════════════════════════════════════${COLOR.reset}`);
  console.log(`${COLOR.cyan}  RAV-SPY — Dependency Checker${COLOR.reset}`);
  console.log(`${COLOR.cyan}══════════════════════════════════════${COLOR.reset}`);
  console.log();

  const root = getProjectRoot();
  log(`Project root: ${root}`);

  await checkSystemDeps();
  await checkPythonDeps(root);

  console.log();
  log('Selesai.');
}

if (require.main === module) {
  main().catch((e) => {
    fail(e.message);
    process.exit(1);
  });
}

module.exports = { checkSystemDeps, checkPythonDeps, detectPython, getProjectRoot };
