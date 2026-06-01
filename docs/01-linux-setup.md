# Local Linux Setup

The dev machine runs Ubuntu 26.04 LTS, dual-boot on a separate physical disk from Windows. This doc covers how to rebuild that environment from a fresh install: editor, Python, Docker, Azure CLI, hardening, network, and the repo bootstrap.

The terraform stack has its own pre-commit story. Once the repo is cloned, see `docs/03-pre-commit.md` for the hook install.

## Machine baseline

| Component | Value |
|---|---|
| OS | Ubuntu 26.04 LTS |
| Shell | bash |
| Editor | VS Code |
| Python | 3.11.9 via pyenv |
| GPU | RTX 3070 Laptop, 8 GB VRAM |
| Host NVIDIA driver | 595.71.05 |
| CUDA in Docker | 12.1 |
| RAM | 16 GB |
| Camera | Logitech C922 Pro (USB) |
| Docker Engine | 29.5.2 (native, no Desktop) |
| Docker Compose | v5.1.4 |
| Azure CLI | 2.86.0 |
| Project path | `~/theft-detection-platform` |

Windows lives on Disk 0 and is never touched. Ubuntu lives on Disk 1, a separate physical disk. GRUB picks the OS at boot.

## Editor: VS Code

VS Code handles every multi-line file. nano is allowed for a one-line config tweak and nothing larger. Encoding and indentation mistakes from nano cost a full session of debugging in the past.

Install from the Microsoft apt repo, not snap. Snap confinement hides VS Code from some system paths that the project uses.

```bash
sudo apt install -y wget gpg
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -o root -g root -m 644 packages.microsoft.gpg /usr/share/keyrings/
sudo sh -c 'echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'
rm -f packages.microsoft.gpg
sudo apt update
sudo apt install -y code
```

## Python via pyenv

The host venv runs the AI model only. Backend code runs inside Docker, so the host never installs `backend/requirements.txt`. That split keeps host and container dependencies from drifting.

Install pyenv, then 3.11.9:

```bash
curl -fsSL https://pyenv.run | bash

cat >> ~/.bashrc <<'EOF'
export PYENV_ROOT="$HOME/.pyenv"
[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init - bash)"
eval "$(pyenv virtualenv-init -)"
EOF

exec bash
pyenv install 3.11.9
```

If 3.11.9 fails to compile, install the build deps and retry:

```bash
sudo apt install -y build-essential libssl-dev zlib1g-dev libbz2-dev \
  libreadline-dev libsqlite3-dev curl libncursesw5-dev xz-utils tk-dev \
  libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
```

## Docker Engine native (no Desktop)

Docker Desktop on Linux runs the engine inside a VM. That extra hop blocks the host GPU from passing through to the AI container. The native engine binds directly to the NVIDIA driver, which is the configuration the AI workload needs.

Install the engine:

```bash
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  sudo apt remove -y $pkg
done

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Run as your user, not root:

```bash
sudo usermod -aG docker $USER
newgrp docker
docker run --rm hello-world
```

### NVIDIA runtime as the default

The AI container needs GPU passthrough. The NVIDIA container toolkit adds a `nvidia` runtime to Docker, and we set it as the default so the AI service runs without a per-call `--runtime nvidia` flag.

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker --set-as-default
sudo systemctl restart docker
```

The nvidia default is process-wide. CPU-only containers (backend, frontend) override back to `runc` per-service in `docker-compose.linux.yml`. The override lives in the compose layer, not in the daemon config.

Verify GPU passthrough:

```bash
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

The host driver reports CUDA up to 13.2; the container ships its own CUDA 12.1 userspace. Driver-to-runtime is forward-compatible, so the mismatch is fine.

## The three-file compose invocation

Compose merges files left to right, last wins. The project uses three layers:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.override.yml \
  -f docker-compose.linux.yml <cmd>
```

- `docker-compose.yml` — base, prod-like defaults
- `docker-compose.override.yml` — local dev tweaks (bind mounts, debug flags)
- `docker-compose.linux.yml` — Linux-only overrides, including the per-service `runtime: runc` for CPU containers

Bare `docker compose up` misses the override and the runc fix. CPU containers then start under the nvidia runtime and fail in non-obvious ways.

Save the typing in `~/.bashrc`:

```bash
alias dctd='docker compose -f docker-compose.yml -f docker-compose.override.yml -f docker-compose.linux.yml'
```

Then `dctd up -d`, `dctd down`, `dctd logs backend --tail 50`.

## Azure CLI and Azure for Students

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
az --version
az login
az account show
```

The subscription is Azure for Students. The $100 credit is the hard ceiling for everything cloud-side. Set the $50 budget alert before any deployment, not after.

A fresh Students subscription ships with no resource providers registered. The project needs at least Storage, Key Vault, and Network:

```bash
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.KeyVault
az provider register --namespace Microsoft.Network
```

Each registration takes 1–3 minutes. Poll until `registrationState` reads `Registered`:

```bash
az provider show --namespace Microsoft.Storage --query "registrationState"
```

Azure for Students also enforces a per-resource-type region allowlist. `spaincentral` works for every resource the project provisions; `francecentral` blocks `Microsoft.Storage`. The whole stack stays in `spaincentral`.

## Hardening stack

Seven tools cover seven independent slices of the host. None of them depend on each other.

| Tool | What it does | Config location |
|---|---|---|
| auditd | Kernel audit log, 27 immutable rules | `/etc/audit/rules.d/` |
| fail2ban | Bans IPs that fail SSH auth repeatedly | `/etc/fail2ban/jail.d/` |
| AppArmor | Mandatory access control, per-app profiles | `/etc/apparmor.d/` |
| ufw | Host firewall, default-deny inbound | `sudo ufw status` |
| unattended-upgrades | Automatic security patches | `/etc/apt/apt.conf.d/50unattended-upgrades` |
| journald caps | Bounded binary journal at `/var/log/journal/` | `/etc/systemd/journald.conf.d/` |
| logrotate | Rotates plain-text log files | `/etc/logrotate.d/` |

Two log subsystems, two configs: systemd-journald owns the binary journal, logrotate owns plain-text files in `/var/log/` and elsewhere. They do not overlap. Any logrotate snippet for a path under `/home/` needs a `su <user> <group>` directive, otherwise rotation refuses to run.

Docker container logs are capped at the daemon level via `/etc/docker/daemon.json` (`log-driver` and `log-opts`), not via logrotate. Source-of-write is the correct enforcement point.

## Network: DNS on hostile wi-fi

Café and hotel wi-fi often returns broken DNS. Two workarounds:

```bash
# Per-session override (systemd-resolved overwrites on reboot)
sudo bash -c 'echo "nameserver 8.8.8.8" > /etc/resolv.conf'

# Or run a VPN that ships its own DNS
```

Treat the resolv.conf change as a session patch, not a permanent fix.

## Repo clone and venv setup

With Docker, pyenv, and VS Code in place:

```bash
cd ~
git clone git@github.com:Nizar7kabbaj/theft-detection-platform.git
cd theft-detection-platform

pyenv local 3.11.9
python -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel

# CUDA 12.1 torch wheel FIRST. Otherwise ultralytics pulls the CPU-only torch.
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

pip install -r ai-model/requirements.txt
```

Confirm CUDA bound to the RTX 3070:

```bash
python -c "import torch; print(torch.cuda.is_available())"
# expect: True
```

Recreate `backend/.env` from `backend/.env.example`. The original `.env` is gitignored, and the values are recoverable from MongoDB Atlas, BotFather, and the Azure portal in about 15 minutes.

## Pre-commit

The terraform stack runs five hooks (`terraform fmt`, `tflint`, `tfsec`, `checkov` auto, `conftest` manual) on every commit. Install steps, tool pins, and the suppression rationale live in `docs/03-pre-commit.md`.

## Other docs in this folder

- `docs/02-iac-foundation.md` — terraform module structure, remote state, policy-as-code
- `docs/03-pre-commit.md` — terraform hook install and suppression rationale
- `docs/04-disaster-recovery.md` — backup script, restore runbook, drill log