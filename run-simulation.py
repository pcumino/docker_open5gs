#!/usr/bin/env python3

#===========================================================#
#File Name:			run-simulation.py
#Author:			Pedro Cumino
#Email:				pedrolm@cpqd.com.br
#Creation Date:		Mon 11 May 2026 03:00:47 PM -03
#Last Modified:		Mon 12 May 2026
#Description:
#Args:
#Usage:
#===========================================================#

import subprocess
import sys
import yaml
import argparse
import shutil
from datetime import datetime
from pathlib import Path
from time import sleep

CONFIG_FILE = Path(__file__).parent / "simulation.yaml"


def _load_config(path: Path) -> dict:
	try:
		with path.open() as f:
			return yaml.safe_load(f)
	except FileNotFoundError:
		print(f"ERROR: configuration file not found: {path}", flush=True)
		sys.exit(1)
	except yaml.YAMLError as exc:
		print(f"ERROR: failed to parse {path}: {exc}", flush=True)
		sys.exit(1)


_cfg = _load_config(CONFIG_FILE)

BITRATE  = _cfg["iperf3"]["bitrate"]
SIMTIME  = int(_cfg["iperf3"]["simtime"])
INTERVAL = int(_cfg["iperf3"]["interval"])

# Maximum time (seconds) to poll for a single readiness check attempt
READINESS_TIMEOUT = 30
# Maximum number of retry attempts for readiness checks and commands
MAX_RETRIES = 3

STACK = _cfg["stack"]

CORE_CONTAINERS = _cfg["containers"]["core"]
RAN_CONTAINERS  = _cfg["containers"]["ran"]
UE_CONTAINERS   = _cfg["containers"]["ue"]

REQUIRED_TOOLS = ["docker", "tmux", "tcpdump", "bash", "python3"]
REQUIRED_SCRIPTS = ["start.sh", "stop.sh", "run-iperf3-server.sh", "run-iperf3-client.sh"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_network_interface() -> str:
	result = subprocess.run(
		"docker network ls --format '{{.Name}} {{.ID}}'",
		shell=True,
		capture_output=True,
		text=True,
	)
	for line in result.stdout.splitlines():
		parts = line.split()
		if len(parts) != 2:
			continue
		name, net_id = parts
		if "open5gs" in name:
			return f"br-{net_id}"
	return ""


_tcpdump_procs: list = []


def start_tcpdump() -> None:
	global _tcpdump_procs

	# cmd = "tree -ifF | grep -E \".*.(pcap|log)$\" | xargs sudo rm -f"

	# subprocess.run(cmd, shell=True, check=False)

	net_interface = get_network_interface()
	if not net_interface:
		log("Warning: could not determine network interface; skipping tcpdump.")
		return

	captures = [
		("f1c.pcap",    "sctp and port 38472"),                                                           # F1-C  DU<->CU
		("n2.pcap",     "sctp and host 172.22.0.43 and host 172.22.0.10 and port 38412"),                 # N2    CU<->AMF
		("f1u.pcap",    "udp and host 172.22.0.43 and host 172.22.0.44 and (port 2152 or port 2153)"),   # F1-U  DU<->CU
		("n3.pcap",     "udp and host 172.22.0.43 and host 172.22.0.8 and port 2152"),                   # N3    CU<->UPF
		("uu-zmq.pcap", "tcp and (port 2000 or port 2001)"),                                             # Uu-ZMQ
	]

	for pcap, filt in captures:
		proc = subprocess.Popen(
			f"tcpdump -i {net_interface} -w {pcap} '{filt}'",
			shell=True,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
		)
		_tcpdump_procs.append(proc)
		log(f"tcpdump started: {pcap} (PID {proc.pid})")


def stop_tcpdump() -> None:
	global _tcpdump_procs
	if not _tcpdump_procs:
		return
	log("Stopping tcpdump processes...")
	for proc in _tcpdump_procs:
		if proc.poll() is None:
			proc.terminate()
	for proc in _tcpdump_procs:
		try:
			proc.wait(timeout=5)
		except subprocess.TimeoutExpired:
			proc.kill()
	_tcpdump_procs.clear()
	log("tcpdump processes stopped.")

def log(msg: str) -> None:
	"""Print a timestamped message."""
	print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _container_running(name: str) -> bool:
	"""Return True when container *name* exists and has running state."""
	result = subprocess.run(
		f"docker inspect -f '{{{{.State.Running}}}}' {name}",
		shell=True, capture_output=True, text=True,
	)
	return result.returncode == 0 and result.stdout.strip() == "true"


def _compose_file_for_stack(stack_name: str) -> str:
	"""Map stack selector to compose filename used by start.sh/stop.sh."""
	mapping = {
		"core": "sa-deploy.yaml",
		"gnb": "srsgnb_zmq.yaml",
		"split": "srsgnb_split_zmq.yaml",
		"ue": "srsue_5g_zmq.yaml",
		"ue-split": "srsue_5g_zmq.yaml",
	}
	if stack_name not in mapping:
		raise RuntimeError(f"Unknown stack value in config: {stack_name}")
	return mapping[stack_name]


def run_preflight_checks(validate_compose: bool = True) -> None:
	"""Validate host tools, required files, and compose syntax before runtime."""
	log("Running preflight checks...")

	missing_tools = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
	if missing_tools:
		raise RuntimeError(f"Missing required tools: {', '.join(missing_tools)}")

	for script in REQUIRED_SCRIPTS:
		path = Path(__file__).parent / script
		if not path.exists():
			raise RuntimeError(f"Required script not found: {path}")
		if not path.is_file():
			raise RuntimeError(f"Required script is not a file: {path}")
		if not path.stat().st_mode & 0o111:
			raise RuntimeError(f"Script is not executable: {path}")

	env_path = Path(__file__).parent / ".env"
	if not env_path.exists():
		raise RuntimeError(f"Required environment file not found: {env_path}")

	docker_ok = subprocess.run(
		"docker info",
		shell=True,
		capture_output=True,
		text=True,
	)
	if docker_ok.returncode != 0:
		raise RuntimeError("Docker daemon is not reachable. Check docker service and permissions.")

	if validate_compose:
		compose_files = [
			_compose_file_for_stack(STACK["core"]),
			_compose_file_for_stack(STACK["ran"]),
			_compose_file_for_stack(STACK["ue"]),
		]
		for compose_file in compose_files:
			path = Path(__file__).parent / compose_file
			if not path.exists():
				raise RuntimeError(f"Compose file not found: {path}")
			result = subprocess.run(
				f"docker compose -f {compose_file} config > /dev/null",
				shell=True,
			)
			if result.returncode != 0:
				raise RuntimeError(f"Compose validation failed: {compose_file}")

	log("Preflight checks passed.")


def wait_for_containers(
	containers: list,
	timeout: int = READINESS_TIMEOUT,
	max_retries: int = MAX_RETRIES,
) -> None:
	"""
	Poll until every container in *containers* is running.

	Each attempt polls once per second for up to *timeout* seconds.
	Raises RuntimeError after *max_retries* failed attempts.
	"""
	for attempt in range(1, max_retries + 1):
		elapsed = 0
		while elapsed < timeout:
			if all(_container_running(c) for c in containers):
				return
			log(f"Waiting for containers {containers} ... ({elapsed + 1}s / attempt {attempt}/{max_retries})")
			sleep(1)
			elapsed += 1
		log(f"Attempt {attempt}/{max_retries}: containers not ready after {timeout}s.")
	raise RuntimeError(f"Containers {containers} did not become ready after {max_retries} attempts.")


def wait_for_iperf3_server(
	timeout: int = READINESS_TIMEOUT,
	max_retries: int = MAX_RETRIES,
) -> None:
	"""Wait until the iperf3 server process is visible inside the upf container."""
	for attempt in range(1, max_retries + 1):
		elapsed = 0
		while elapsed < timeout:
			result = subprocess.run(
				"docker exec upf pgrep iperf3",
				shell=True, capture_output=True,
			)
			if result.returncode == 0:
				return
			log(f"Waiting for iperf3 server ... ({elapsed + 1}s / attempt {attempt}/{max_retries})")
			sleep(1)
			elapsed += 1
		log(f"Attempt {attempt}/{max_retries}: iperf3 server not ready after {timeout}s.")
	raise RuntimeError(f"iperf3 server did not become ready after {max_retries} attempts.")


def run_with_retry(cmd: str, max_retries: int = MAX_RETRIES) -> None:
	"""Run a shell command, retrying up to *max_retries* times on failure."""
	log(f"Running: {cmd}")
	for attempt in range(1, max_retries + 1):
		try:
			subprocess.run(cmd, shell=True, check=True)
			return
		except subprocess.CalledProcessError as exc:
			log(f"Command failed (attempt {attempt}/{max_retries}): {exc}")
			if attempt < max_retries:
				sleep(2)
	raise RuntimeError(f"Command failed after {max_retries} attempts: {cmd}")


def attach_container_tmux(container: str, session: str) -> None:
	"""
	Create a detached tmux session running 'docker attach <container>'.
	If the session already exists it is reused.
	"""
	exists = subprocess.run(
		f"tmux has-session -t {session}",
		shell=True, capture_output=True,
	).returncode == 0

	if not exists:
		subprocess.run(
			f"tmux new-session -d -s {session} 'docker attach {container}'",
			shell=True, check=True,
		)
		log(f"tmux session '{session}' created and attached to container '{container}'.")
	else:
		log(f"tmux session '{session}' already exists; reusing.")


def _wait_container_stopped(name: str, timeout: int = READINESS_TIMEOUT) -> None:
	"""Block until container *name* is no longer running, or *timeout* expires."""
	for elapsed in range(1, timeout + 1):
		if not _container_running(name):
			return
		log(f"Waiting for '{name}' to stop ... ({elapsed}/{timeout}s)")
		sleep(1)
	log(f"Warning: container '{name}' did not stop within {timeout}s.")


def shutdown_containers() -> None:
	"""
	Gracefully stop UE then RAN containers by sending 'q' to each app.

	The UE (in its tmux session) is stopped first; only after it exits are
	the gNB containers stopped — DU before CU for the split stack.
	"""
	ue = UE_CONTAINERS[0]  # srsue_5g_zmq

	# --- Stop UE via its tmux session (session name == container name) ---
	log(f"Sending 'q' to UE container '{ue}'...")
	subprocess.run(
		f"tmux send-keys -t {ue} 'q' Enter",
		shell=True, check=False,
	)
	_wait_container_stopped(ue)
	log(f"UE container '{ue}' stopped.")
	subprocess.run(f"bash stop.sh {STACK['ue']}", shell=True, check=False)

	# --- Stop gNB containers: DU first (radio front-end), then CU ---
	# RAN_CONTAINERS = ['srscu_zmq', 'srsdu_zmq'] → reversed: du → cu
	for gnb in reversed(RAN_CONTAINERS):
		if not _container_running(gnb):
			log(f"gNB container '{gnb}' is already stopped; skipping.")
			continue
		log(f"Sending 'q' to gNB container '{gnb}' via tmux session '{gnb}'...")
		subprocess.run(
			f"tmux send-keys -t {gnb} 'q' Enter",
			shell=True, check=False,
		)
		_wait_container_stopped(gnb)
		log(f"gNB container '{gnb}' stopped.")

	subprocess.run(f"bash stop.sh {STACK['ran']}", shell=True, check=False)
	log("RAN compose stack torn down.")


def cleanup(stop_core: bool = False) -> None:
	"""Best-effort teardown of all stacks.

	Core is only stopped when *stop_core* is True (i.e. --stop-core was passed).
	"""
	log("Running cleanup...")
	stop_tcpdump()
	for key, stack in STACK.items():
		if key == 'core' and not stop_core:
			log("Leaving core stack running (pass --stop-core to override).")
			continue
		try:
			subprocess.run(f"bash stop.sh {stack}", shell=True, check=False)
		except Exception:
			pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list) -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Run Open5GS simulation workflow.")
	parser.add_argument(
		"--stop-core",
		action="store_true",
		help="Stop and restart core stack at the start of the run; also stop it during cleanup.",
	)
	parser.add_argument(
		"--preflight-only",
		action="store_true",
		help="Run host/config/compose checks and exit without starting stacks.",
	)
	return parser.parse_args(argv)


def main(argv: list) -> None:
	args = _parse_args(argv)
	stop_core = args.stop_core

	try:
		run_preflight_checks(validate_compose=True)
	except RuntimeError as exc:
		log(f"ERROR: {exc}")
		sys.exit(1)

	if args.preflight_only:
		log("Preflight-only mode requested; exiting.")
		return

	if stop_core:
		log("--stop-core set: stopping core containers before (re)start...")
		subprocess.run(f"bash stop.sh {STACK['core']}", shell=True, check=False)
		for c in CORE_CONTAINERS:
			_wait_container_stopped(c)
		log("Core containers stopped.")

	log("Checking core containers...")
	try:
		if not stop_core and all(_container_running(c) for c in CORE_CONTAINERS):
			log("Core containers are already running; skipping start.")
		else:
			log("Starting core containers...")
			run_with_retry(f"bash start.sh {STACK['core']} --no-attach")
			wait_for_containers(CORE_CONTAINERS)
	except RuntimeError as exc:
		log(f"ERROR: {exc}")
		sys.exit(1)
	log("Core containers are ready.")

	try:
		log("Starting RAN containers...")
		run_with_retry(f"bash start.sh {STACK['ran']} --no-attach")
		wait_for_containers(RAN_CONTAINERS)
		log("RAN containers are ready.")

		for gnb in RAN_CONTAINERS:
			attach_container_tmux(container=gnb, session=gnb)

		log("Starting UE containers...")
		run_with_retry(f"bash start.sh {STACK['ue']} --no-attach")
		wait_for_containers(UE_CONTAINERS)
		log("UE containers are ready.")

		attach_container_tmux(container=UE_CONTAINERS[0], session=UE_CONTAINERS[0])

		log("Starting iperf3 server...")
		start_tcpdump()
		run_with_retry("bash run-iperf3-server.sh")
		wait_for_iperf3_server()
		log("iperf3 server is ready.")

		log("Starting iperf3 client...")
		run_with_retry(f"bash run-iperf3-client.sh {BITRATE} {SIMTIME} {INTERVAL}")

		log("Shutting down UE and gNB containers gracefully...")
		shutdown_containers()
		stop_tcpdump()

	except RuntimeError as exc:
		log(f"ERROR: {exc}")
		cleanup(stop_core=stop_core)
		sys.exit(1)
	except KeyboardInterrupt:
		log("Interrupted.")
		cleanup(stop_core=stop_core)
		sys.exit(130)

	log("Simulation complete.")


if __name__ == '__main__':
	main(sys.argv[1:])


