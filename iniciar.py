"""Install dependencies and serve the local HorarioGen workspace."""
import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def wait_for(url, process, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"El servicio terminó con código {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.3)
    raise RuntimeError(f"El servicio no respondió en {url}.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--sin-navegador", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise RuntimeError("Instala Python 3.11 o posterior.")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm or not shutil.which("node"):
        raise RuntimeError("Instala Node.js 22 o posterior y npm.")
    backend, frontend = ROOT / "backend", ROOT / "frontend"
    venv = backend / ".venv"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    backend_url = f"http://127.0.0.1:{args.api_port}"
    site = f"http://127.0.0.1:{args.port}"
    env = {**os.environ, "HORARIOGEN_BACKEND": backend_url, "NEXT_TELEMETRY_DISABLED": "1"}
    if not python.exists():
        print("Preparando Python…", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    if subprocess.run([str(python), "-c", "import fastapi, uvicorn, python_multipart, openpyxl"], capture_output=True).returncode:
        subprocess.run([str(python), "-m", "pip", "install", "-r", "requirements.txt"], cwd=backend, check=True)
    if not (frontend / "node_modules/next/dist/bin/next").is_file():
        print("Instalando la interfaz…", flush=True)
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=frontend, env=env, check=True)
    print("Compilando la interfaz…", flush=True)
    next_cli = frontend / "node_modules/next/dist/bin/next"
    subprocess.run(["node", str(next_cli), "build"], cwd=frontend, env=env, check=True)

    services = []
    try:
        api = subprocess.Popen(
            [str(python), "-m", "uvicorn", "horariogen.api:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
            cwd=backend, env=env,
        )
        services.append(api)
        wait_for(backend_url + "/api/health", api)
        web = subprocess.Popen(
            ["node", str(next_cli), "start", "--hostname", "127.0.0.1", "--port", str(args.port)],
            cwd=frontend, env=env,
        )
        services.append(web)
        wait_for(site + "/api/health", web)
        print(f"\nHorarioGen está listo en {site}. Pulsa Ctrl+C para detenerlo.\n", flush=True)
        if not args.sin_navegador:
            webbrowser.open(site)
        while all(process.poll() is None for process in services):
            time.sleep(0.5)
        raise RuntimeError("Se detuvo uno de los servicios. Consulta el registro anterior.")
    finally:
        for process in reversed(services):
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nHorarioGen detenido.")
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"\nNo se pudo iniciar HorarioGen: {exc}", file=sys.stderr)
        sys.exit(1)

