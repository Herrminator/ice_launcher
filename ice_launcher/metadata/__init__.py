import re, threading, requests
from typing import Any, Callable, Iterable, Mapping
from . import streammeta
from .. import config
import logging

# http://admin:hackme@tjpi10:8000/admin/metadata.xsl?song=Pong%21&mount=%2Fstreams%2Ftryme.mp3&mode=updinfo&charset=UTF-8
UPDATE_URL   = "http://{host}:{port}/admin/metadata.xsl"
UPDATE_PARAM = { "mode": "updinfo", "charset": "UTF-8" }
SKIP_ADV     = ('adw_ad', 'true')
SKIP_ADV     = ("StreamTitle", re.compile(r"^(RADIO BOB|Bayern).*", re.I))

class Updater(threading.Thread):
    def __init__(self, mount: str, conf: config.Config) -> None:
        super().__init__()
        self.mount  = mount
        self.stream = conf.mounts[mount]["input"]
        self.update_url = UPDATE_URL.format(host=conf.main["icecast_host"], port=conf.main["icecast_port"])
        self.auth = (conf.main["icecast_admin"], conf.main["icecast_admin_password"])
        self.last = None
        self.stopping = threading.Event()
    
    def update(self, meta: dict[Any, Any]) -> None:
        if meta.get("StreamTitle") is None:
            logging.warning(f"No usable metadata for {self.mount} in {meta}")
            return
        val = meta["StreamTitle"]
        if val == self.last:
            logging.debug(f"Metadata for {self.mount} already set to {self.last}")
            return
        logging.debug(f"Updating metadata for {self.mount} with {meta}")
        par = { "song": val, "mount": f"/{self.mount}" }
        par.update(UPDATE_PARAM)
        try:
            rsp = requests.get(self.update_url, params=par, auth=self.auth)
            rsp.raise_for_status()
            self.last = val
        except Exception as exc:
            logging.error(f"Error updating metadata for {self.mount}: {exc}", exc_info=True)

    def run(self) -> None:
        while not self.stopping.wait(10.0):
            try:
                meta = streammeta.get_meta(url=self.stream, skip_meta=SKIP_ADV)
                if meta is not None:
                    self.update(meta)
                else:
                    logging.debug(f"No metadata returned for {self.mount}")
            except Exception as exc:
                logging.error(f"Error reading stream metadata: {exc}", exc_info=True)

        logging.debug(f"Metadata updater for {self.mount} stopping.")

    def stop(self) -> None:
        self.stopping.set()

updaters: dict[str, Updater] = {}

def add_updater(mount: str, conf: config.Config):
    if not conf.mounts[mount]["meta"]:
        logging.debug(f"Metadata updating not requested for '{mount}'")
        return
    if mount in updaters:
        logging.debug(f"Metadata updater for '{mount}' already running")
        return
    thread = Updater(mount, conf)
    thread.start()
    updaters[mount] = thread
    logging.info(f"Metadata updater for {mount} started.")
    streammeta.DEBUG = logging.root.level == logging.DEBUG

def remove_updater(mount, conf):
    if mount not in updaters:
        logging.debug(f"No metadata updater for {mount} running")
        return
    thread = updaters.pop(mount)
    thread.stop()
    thread.join()
    logging.info(f"Metadata updater for {mount} stopped.")

def remove_all_updater(conf):
    logging.debug(f"Removing all remaing metada updaters")
    for mount in list(updaters.keys()):
        remove_updater(mount, conf)

