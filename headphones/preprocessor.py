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

import headphones
from headphones import request
from headphones.common import USER_AGENT
from headphones.types import Result


def preprocess(resultlist, ruobj):
    for result in resultlist:

        if result.provider in ["The Pirate Bay", "Old Pirate Bay"]:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 6.3; Win64; x64) \
                    AppleWebKit/537.36 (KHTML, like Gecko) \
                    Chrome/41.0.2243.2 Safari/537.36"
            }
        else:
            headers = {"User-Agent": USER_AGENT}

        if result.kind == "torrent":
            # Get out of here if we're using Transmission or Deluge
            # if not a magnet link still need the .torrent to generate hash... uTorrent support labeling
            if headphones.CONFIG.TORRENT_DOWNLOADER in [1, 3]:
                return True, result

            # Get out of here if it's a magnet link
            if result.url.lower().startswith("magnet:"):
                return True, result

            # rutracker always needs the torrent data
            if result.provider == "rutracker.org":
                return ruobj.get_torrent_data(result.url), result

            # Jackett sometimes redirects
            if (
                result.provider.startswith("Jackett_")
                or "torznab" in result.provider.lower()
            ):
                r = request.request_response(
                    url=result.url, headers=headers, allow_redirects=False
                )
                if r:
                    link = r.headers.get("Location")
                    if link and link != result.url:
                        if link.startswith("magnet:"):
                            result = Result(
                                result.url,
                                result.size,
                                link,
                                result.provider,
                                "magnet",
                                result.matches,
                            )
                            return (
                                "d10:magnet-uri%d:%se" % (len(link), link),
                                result,
                            )
                        else:
                            result = Result(
                                result.url,
                                result.size,
                                link,
                                result.provider,
                                result.kind,
                                result.matches,
                            )
                            return True, result
                    else:
                        return r.content, result

            # Download the torrent file
            return (
                request.request_content(url=result.url, headers=headers),
                result,
            )

        if result.kind == "magnet":
            magnet_link = result.url
            return (
                "d10:magnet-uri%d:%se" % (len(magnet_link), magnet_link),
                result,
            )

        # TODO: Allow result.kind that implies "torrent already downloaded"

        else:
            if result.provider == "headphones":
                return (
                    request.request_content(
                        url=result.url,
                        headers=headers,
                        auth=(
                            headphones.CONFIG.HPUSER,
                            headphones.CONFIG.HPPASS,
                        ),
                    ),
                    result,
                )
            else:
                return (
                    request.request_content(url=result.url, headers=headers),
                    result,
                )
