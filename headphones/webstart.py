#  This file is part of Headphones.
#
#  Headphones is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Headphones is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Headphones.  If not, see <http://www.gnu.org/licenses/>.

import sys

import os
import cherrypy
import headphones
from headphones import logger
from headphones.webserve import WebInterface
from headphones.helpers import create_https_certificates


def initialize(options):
    # HTTPS stuff stolen from sickbeard
    enable_https = options["enable_https"]
    https_cert = options["https_cert"]
    https_key = options["https_key"]

    if enable_https:
        # If either the HTTPS certificate or key do not exist, try to make
        # self-signed ones.
        if not (https_cert and os.path.exists(https_cert)) or not (
            https_key and os.path.exists(https_key)
        ):
            if not create_https_certificates(https_cert, https_key):
                logger.warn(
                    "Unable to create certificate and key. Disabling " "HTTPS"
                )
                enable_https = False

        if not (os.path.exists(https_cert) and os.path.exists(https_key)):
            logger.warn(
                "Disabled HTTPS because of missing certificate and " "key."
            )
            enable_https = False

    options_dict = {
        "server.socket_port": options["http_port"],
        "server.socket_host": options["http_host"],
        "server.thread_pool": 10,
        "tools.encode.on": True,
        "tools.encode.encoding": "utf-8",
        "tools.decode.on": True,
        "log.screen": False,
        "engine.autoreload.on": False,
    }

    if enable_https:
        options_dict["server.ssl_certificate"] = https_cert
        options_dict["server.ssl_private_key"] = https_key
        protocol = "https"
    else:
        protocol = "http"

    logger.info(
        "Starting Headphones web server on %s://%s:%d/",
        protocol,
        options["http_host"],
        options["http_port"],
    )
    cherrypy.config.update(options_dict)

    conf = {
        "/": {
            "tools.staticdir.root": os.path.join(headphones.PROG_DIR, "data"),
            "tools.proxy.on": options[
                "http_proxy"
            ],  # pay attention to X-Forwarded-Proto header
        },
        "/interfaces": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": "interfaces",
        },
        "/images": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": "images",
        },
        "/css": {"tools.staticdir.on": True, "tools.staticdir.dir": "css"},
        "/js": {"tools.staticdir.on": True, "tools.staticdir.dir": "js"},
        "/favicon.ico": {
            "tools.staticfile.on": True,
            "tools.staticfile.filename": os.path.join(
                os.path.abspath(os.curdir), "images" + os.sep + "favicon.ico"
            ),
        },
        "/cache": {
            "tools.staticdir.on": True,
            "tools.staticdir.dir": headphones.CONFIG.CACHE_DIR,
        },
    }

    if options["http_password"]:
        logger.info(
            "Web server authentication is enabled, username is '%s'",
            options["http_username"],
        )

        conf["/"].update(
            {
                "tools.auth_basic.on": True,
                "tools.auth_basic.realm": "Headphones web server",
                "tools.auth_basic.checkpassword": cherrypy.lib.auth_basic.checkpassword_dict(
                    {options["http_username"]: options["http_password"]}
                ),
            }
        )
        conf["/api"] = {"tools.auth_basic.on": False}

    cherrypy.tree.mount(WebInterface(), str(options["http_root"]), config=conf)

    try:
        cherrypy.server.start()
    except IOError:
        sys.stderr.write(
            "Failed to start on port: %i. Is something else running?\n"
            % (options["http_port"])
        )
        sys.exit(1)

    cherrypy.server.wait()
