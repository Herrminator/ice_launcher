# icelaunch: HTTP server code
#
# Copyright Jeremy Sanders (2023)
# Released under the MIT Licence

from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import logging
import threading

from . import sources, metadata

class LauncherHTTPServer(HTTPServer):
    def __init__(self, conf, *args, **argsv):
        HTTPServer.__init__(self, *args, **argsv)
        self.conf = conf

        # locks for each mount
        self.mount_locks = {
            n: threading.Lock() for n in conf.mounts
        }

        # this keeps track of which clients are using each mount
        self.mount_clients = {m: set() for m in conf.mounts}
        # this maps mounts to Popen processes
        self.mount_processes = {}
        self.global_lock = threading.Lock()

    def add_dynamic_mount(self, mount, conf):
        with self.global_lock:
            self.mount_locks[mount] = threading.Lock()
            self.mount_clients[mount] = set()
            conf["dynamic"] = False

class HTTPHandler(BaseHTTPRequestHandler):
    KNOWN_UNKNOWNS = [ "server_version.xsl", "status.xsl", "style.css" ]

    server: LauncherHTTPServer # type: ignore # for now...

    def send_positive_response(self):
        """Tell icecast that it's ok to server the material."""
        self.send_response(200)
        self.send_header('icecast-auth-user', '1')
        self.end_headers()

    def send_negative_response(self):
        """Tell icecast that it should not continue."""
        self.send_response(200)
        self.send_header('icecast-auth-user', '0')
        self.end_headers()

    def start_source(self, mount):
        """Start source for mount given."""
        logging.info('starting source for mount "%s"' % mount)
        popen = sources.start_source(mount, self.server.conf)
        self.server.mount_processes[mount] = popen

    def stop_source(self, mount):
        """Stop the mount source by killing the process."""
        logging.info('stopping source for mount "%s"' % mount)
        popen = self.server.mount_processes[mount]
        del self.server.mount_processes[mount]
        sources.stop_source(popen, mount, self.server.conf)

    def listener_add(self, params):
        """Handle action listener_add from icecast."""

        mount = params['mount'].lstrip('/')
        client = params['client']

        logging.log(msg="listener_add " + str(params), level=logging.INFO if mount not in self.KNOWN_UNKNOWNS else logging.DEBUG)

        conf = self.server.conf.find_dynamic_mount_config(mount)
        if conf is None:
            logging.log(logging.INFO if mount not in self.KNOWN_UNKNOWNS else logging.DEBUG,
                        'unknown mount "%s" for listener_add, so ignoring' % mount)
            return

        if conf["dynamic"] is None:
            self.server.add_dynamic_mount(mount, conf)

        with self.server.mount_locks[mount]:
            if not self.server.mount_clients[mount]:
                self.start_source(mount)
            elif self.server.mount_processes[mount].poll() is not None:
                logging.warning(
                    'Process for mount "%s" died! Restarting.' % mount)
                self.start_source(mount)

            self.server.mount_clients[mount].add(client)
            
            logging.debug("active clients for mount %s: %s" % (mount, str(self.server.mount_clients[mount])))

    def listener_remove(self, params):
        """Handle action listener_remove from icecast."""

        mount = params['mount'].lstrip('/')
        client = params['client']

        logging.log(msg="listener_remove " + str(params), level=logging.INFO if mount not in self.KNOWN_UNKNOWNS else logging.DEBUG)
        
        conf = self.server.conf.find_dynamic_mount_config(mount)
        if conf is None:
            logging.log(logging.INFO if mount not in self.KNOWN_UNKNOWNS else logging.DEBUG,
                        'unknown mount "%s" for listener_remove, so ignoring' % mount)
            return

        delay = self.server.conf.main.get('source_remove_delay')
        if delay is not None and delay > 0:
            logging.debug(f"delaying source removal for mount {mount}, client {client} by {delay} seconds")
            threading.Timer(delay, self._remove_delayed, args=(mount, client, conf)).start()
        else:
            self._remove_delayed(mount, client, conf)

    def _remove_delayed(self, mount, client, conf):
        """ Kodi seems to connect repeatedly when starting to play.
            So we'll try to keep the source running for a few seconds after the client was removed."""
        if conf["dynamic"] is None:
            self.server.add_dynamic_mount(mount, conf)

        with self.server.mount_locks[mount]:
            if client in self.server.mount_clients[mount]:
                self.server.mount_clients[mount].remove(client)
                if not self.server.mount_clients[mount]:
                    logging.info('no more clients left for mount "%s"' % mount)
                    self.stop_source(mount)
            else:
                logging.debug(f"client {client} not found in mount {mount} clients")
            if self.server.mount_clients[mount]:
                logging.debug(f"remaining clients for mount {mount}: {self.server.mount_clients[mount]}")


    def check_user_password(self, params):
        """Check if provided user details match allowed users."""
        users = self.server.conf.allow_users
        if users:
            if 'user' not in params:
                logging.warning('User not provided, but needed')
                return False
            elif 'pass' not in params:
                logging.warning('Pass not provided, but needed')
                return False
            elif params['user'] not in users:
                logging.warning(
                    'User "%s" not found in allowed list' % params['user'])
                return False
            elif params['pass'] != users[params['user']]:
                logging.warning(
                    'User "%s" has incorrect password' % params['user'])
                return False
        return True

    def do_POST(self):
        # get data from POST
        length = int(self.headers['Content-Length'])
        data = self.rfile.read(length).decode('utf-8')

        # convert POST data to a dictionary
        params = urllib.parse.parse_qs(data)
        # keep only first parameters
        params = {k: v[0] for k, v in params.items()}

        if params['action'] == 'listener_add':
            # hide status page if requested
            if self.server.conf.main['icecast_forbid_status'] and (
                    params['mount'] in {
                        '/', '/status.xsl', '/server_version.xsl'}):
                self.send_negative_response()
                return

            # check usernames and password
            if not self.check_user_password(params):
                self.send_negative_response()
                return

            # handle listener_add
            try:
                self.listener_add(params)
            except sources.IceLaunchError:
                self.send_negative_response()
            else:
                self.send_positive_response()

        elif params['action'] == 'listener_remove':
            self.listener_remove(params)
            self.send_positive_response()

        else:
            logging.info("Unknown action: %s (%s)" % (
                params['action'], repr(params)))
            self.send_positive_response()

    def do_GET(self):
        """Handle GET request.

        This is not needed by icecast.
        """
        logging.info(
            'GET path: %s, headers: %s', repr(self.path), repr(self.headers))
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b'Error 404: Not found')

def run_server(conf):
    """Start HTTP server and process requests."""

    server_address = (
        conf.main['listen_address'],
        conf.main['listen_port'],
    )

    httpd = LauncherHTTPServer(conf, server_address, HTTPHandler)
    logging.info('Starting icecast launcher server')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    metadata.remove_all_updater(conf)
    httpd.server_close()
    logging.info('Stopping icecast launcher server')
