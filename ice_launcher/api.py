import re, shlex, subprocess, requests
from typing import Any

from . import metadata, config

AUTH_PATT = re.compile(r'[-\w\s]+?:[^@:]+?@')

# Calling this from the HTTPHandler causes a deadlock, if the server is single-threaded!
def icecast_status_j(conf: config.Config) -> dict[str, Any]:

    url = f"http://{conf.main['icecast_host']}:{conf.main['icecast_port']}/status-json.xsl"
    auth = ("source", conf.main['icecast_password'])
    rsp = requests.get(url, auth=auth)
    rsp.raise_for_status()
    
    return rsp.json()


# This has more data available, but it needs the admin user und is a tad slower...
def icecast_status(conf: config.Config) -> dict[str, Any]:
    from xml.etree import ElementTree

    url = f"http://{conf.main['icecast_host']}:{conf.main['icecast_port']}/admin/stats"
    auth = (conf.main['icecast_admin'], conf.main['icecast_admin_password'])
    rsp = requests.get(url, auth=auth)
    rsp.raise_for_status()

    root = ElementTree.fromstring(rsp.content)

    status_dict: dict[str, Any] = {}
    for info in root:
        if info.tag == "source": continue
        status_dict[info.tag] = info.text
    status_dict["source"] = {}
    for source in root.findall("source"):
        mount = source.get("mount")
        if mount is None: continue
        mount_info: dict[str, Any] = {}
        for child in source:
            mount_info[child.tag] = child.text
        status_dict["source"][mount] = mount_info

    return status_dict

def mask(data: str) -> str:
    return AUTH_PATT.sub('*****:****@', data)
    
def status(launcher) -> dict[str, dict[str, str | int]]:
    from .server import LauncherHTTPServer
    server: LauncherHTTPServer = launcher
    p: subprocess.Popen
    status_dict: dict[str, Any] = {
        "clients": server.mount_clients,
        "processes": { m: {"pid": p.pid, "command": mask(shlex.join(p.args)) } for m, p in server.mount_processes.items() },
        "metadata": metadata.api.status(),
        "icecast": icecast_status(server.conf),
    }
    return status_dict

def generate_status_json(launcher) -> str:
    import json
    from .server import LauncherHTTPServer
    server: LauncherHTTPServer = launcher
    status_dict = status(server)
    def default(o):
        if isinstance(o, set):
            return list(o)
        raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
    return json.dumps(status_dict, indent=4, default=default)
