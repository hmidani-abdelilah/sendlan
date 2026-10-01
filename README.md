# SendLan

Sendlan is a peer-to-peer LAN application for discovering nearby devices,
chatting, and transferring files. It targets Python 3.10+ on Windows, macOS,
and Linux.

## Features

- Discovers peers using IPv4 broadcast heartbeats.
- Sends chat messages and files over TCP.
- Streams files in 64 KiB chunks and verifies SHA-256 before saving.
- Supports cancelling transfers, drag-and-drop, and a configurable downloads
	folder.
- Offers a settings menu for device name, ports, discovery timing, appearance,
	and download location.

## Installation

Create and activate a virtual environment, then install the dependencies.

Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS and Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Linux, install the operating system's Tk package if it is missing (for
example, `python3-tk` on Debian-based distributions).

## Run

From the project directory:

```bash
python main.py
```

On first launch Sendlan creates a local `config.json`. The file stores the
device name, persistent device ID, network settings, theme, and download
directory. It is excluded from Git because those values are specific to each
machine.

## Network Setup

Peer discovery uses UDP port `50000`; file and chat transfers use TCP port
`50001`. Allow incoming traffic on both ports on each device. Both devices
must be on a network that permits local broadcast traffic. Guest Wi-Fi,
client isolation, and some VPNs prevent peer discovery.

Windows PowerShell (run once as Administrator, on a Private network):

```powershell
New-NetFirewallRule -DisplayName "Sendlan Discovery" -Direction Inbound -Protocol UDP -LocalPort 50000 -RemoteAddress LocalSubnet -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "Sendlan Transfers" -Direction Inbound -Protocol TCP -LocalPort 50001 -RemoteAddress LocalSubnet -Action Allow -Profile Private
```

On macOS, allow Sendlan through the firewall and grant Local Network access if
macOS prompts for it. With UFW on Linux:

```bash
sudo ufw allow 50000/udp
sudo ufw allow 50001/tcp
```

## Data and Security

Received files are written to a temporary file and moved into `downloads/`
only after size and checksum verification. Existing files are not overwritten.
`config.json` and received files are ignored by Git; the repository keeps only
the empty `downloads/` directory marker.

SHA-256 detects accidental corruption but does not encrypt traffic or
authenticate peers. Use Sendlan on trusted local networks.