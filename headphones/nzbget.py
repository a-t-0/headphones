# This file is modified to work with headphones by CurlyMo <curlymoo1@gmail.com> as a part of XBian - XBMC on the Raspberry Pi

# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.


from base64 import standard_b64encode
import http.client
import xmlrpc.client

import headphones
from headphones import logger


def sendNZB(nzb):
    addToTop = False
    nzbgetXMLrpc = "%(protocol)s://%(username)s:%(password)s@%(host)s/xmlrpc"

    if not headphones.CONFIG.NZBGET_HOST:
        logger.error(
            "No NZBget host found in configuration. Please configure it."
        )
        return False

    if headphones.CONFIG.NZBGET_HOST.startswith("https://"):
        protocol = "https"
        host = headphones.CONFIG.NZBGET_HOST.replace("https://", "", 1)
    else:
        protocol = "http"
        host = headphones.CONFIG.NZBGET_HOST.replace("http://", "", 1)

    url = nzbgetXMLrpc % {
        "protocol": protocol,
        "host": host,
        "username": headphones.CONFIG.NZBGET_USERNAME,
        "password": headphones.CONFIG.NZBGET_PASSWORD,
    }

    nzbGetRPC = xmlrpc.client.ServerProxy(url)
    try:
        if nzbGetRPC.writelog(
            "INFO",
            "headphones connected to drop of %s any moment now."
            % (nzb.name + ".nzb"),
        ):
            logger.debug("Successfully connected to NZBget")
        else:
            logger.info(
                "Successfully connected to NZBget, but unable to send a message"
                % (nzb.name + ".nzb")
            )

    except http.client.socket.error:
        logger.error(
            "Please check your NZBget host and port (if it is running). NZBget is not responding to this combination"
        )
        return False

    except xmlrpc.client.ProtocolError as e:
        if e.errmsg == "Unauthorized":
            logger.error("NZBget password is incorrect.")
        else:
            logger.error("Protocol Error: " + e.errmsg)
        return False

    nzbcontent64 = None
    if nzb.resultType == "nzbdata":
        data = nzb.extraInfo[0]
        # NZBGet needs a string, not bytes
        nzbcontent64 = standard_b64encode(data).decode("utf-8")

    logger.info("Sending NZB to NZBget")
    logger.debug("URL: " + url)

    dupekey = ""
    dupescore = 0

    try:
        # Find out if nzbget supports priority (Version 9.0+), old versions beginning with a 0.x will use the old command
        nzbget_version_str = nzbGetRPC.version()
        nzbget_version = int(
            nzbget_version_str[: nzbget_version_str.find(".")]
        )
        if nzbget_version == 0:
            if nzbcontent64 is not None:
                nzbget_result = nzbGetRPC.append(
                    nzb.name + ".nzb",
                    headphones.CONFIG.NZBGET_CATEGORY,
                    addToTop,
                    nzbcontent64,
                )
            else:
                # from headphones.common.providers.generic import GenericProvider
                # if nzb.resultType == "nzb":
                #     genProvider = GenericProvider("")
                #     data = genProvider.getURL(nzb.url)
                #     if (data is None):
                #         return False
                #     nzbcontent64 = standard_b64encode(data)
                # nzbget_result = nzbGetRPC.append(nzb.name + ".nzb", headphones.CONFIG.NZBGET_CATEGORY, addToTop, nzbcontent64)
                return False
        elif nzbget_version == 12:
            if nzbcontent64 is not None:
                nzbget_result = nzbGetRPC.append(
                    nzb.name + ".nzb",
                    headphones.CONFIG.NZBGET_CATEGORY,
                    headphones.CONFIG.NZBGET_PRIORITY,
                    False,
                    nzbcontent64,
                    False,
                    dupekey,
                    dupescore,
                    "score",
                )
            else:
                nzbget_result = nzbGetRPC.appendurl(
                    nzb.name + ".nzb",
                    headphones.CONFIG.NZBGET_CATEGORY,
                    headphones.CONFIG.NZBGET_PRIORITY,
                    False,
                    nzb.url,
                    False,
                    dupekey,
                    dupescore,
                    "score",
                )
        # v13+ has a new combined append method that accepts both (url and content)
        # also the return value has changed from boolean to integer
        # (Positive number representing NZBID of the queue item. 0 and negative numbers represent error codes.)
        elif nzbget_version >= 13:
            nzbget_result = (
                True
                if nzbGetRPC.append(
                    nzb.name + ".nzb",
                    nzbcontent64 if nzbcontent64 is not None else nzb.url,
                    headphones.CONFIG.NZBGET_CATEGORY,
                    headphones.CONFIG.NZBGET_PRIORITY,
                    False,
                    False,
                    dupekey,
                    dupescore,
                    "score",
                )
                > 0
                else False
            )
        else:
            if nzbcontent64 is not None:
                nzbget_result = nzbGetRPC.append(
                    nzb.name + ".nzb",
                    headphones.CONFIG.NZBGET_CATEGORY,
                    headphones.CONFIG.NZBGET_PRIORITY,
                    False,
                    nzbcontent64,
                )
            else:
                nzbget_result = nzbGetRPC.appendurl(
                    nzb.name + ".nzb",
                    headphones.CONFIG.NZBGET_CATEGORY,
                    headphones.CONFIG.NZBGET_PRIORITY,
                    False,
                    nzb.url,
                )

        if nzbget_result:
            logger.debug("NZB sent to NZBget successfully")
            return True
        else:
            logger.error(
                "NZBget could not add %s to the queue" % (nzb.name + ".nzb")
            )
            return False
    except:
        logger.error(
            "Connect Error to NZBget: could not add %s to the queue"
            % (nzb.name + ".nzb")
        )
        return False
