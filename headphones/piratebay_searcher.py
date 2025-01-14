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

# NZBGet support added by CurlyMo <curlymoo1@gmail.com> as a part of XBian - XBMC on the Raspberry Pi
# Pirate Bay
import re
import headphones
import urllib3
import urllib.parse
from headphones import helpers, logger, request

# from headphones.searcher import fix_url, set_proxy
from headphones.types import Result


def set_proxy(proxy_url):
    if not proxy_url.startswith("http"):
        proxy_url = "https://" + proxy_url
    if proxy_url.endswith("/"):
        proxy_url = proxy_url[:-1]

    return proxy_url


def fix_url(s, charset="utf-8"):
    """
    Fix the URL so it is proper formatted and encoded.
    """

    scheme, netloc, path, qs, anchor = urllib.parse.urlsplit(s)
    path = urllib.parse.quote(path, "/%")
    qs = urllib.parse.quote_plus(qs, ":&=")

    return urllib.parse.urlunsplit((scheme, netloc, path, qs, anchor))


def search_piratebay(
    term, losslessOnly, allow_lossless, minimumseeders, resultlist
):

    # In GUI: Settings>Search providers>Torrents>The Pirate Bay.
    if headphones.CONFIG.PIRATEBAY:

        # Specify the search provider name.
        provider = "The Pirate Bay"

        # Improve search term formatting.
        tpb_term = term.replace("!", "").replace("'", " ")

        # Use proxy if specified
        if headphones.CONFIG.PIRATEBAY_PROXY_URL:
            # In GUI: Settings>Search providers>Torrents>The Pirate Bay>Proxy URL
            providerurl = fix_url(
                set_proxy(headphones.CONFIG.PIRATEBAY_PROXY_URL)
            )
        else:
            # TODO: move to hardcoded value on top of function.
            providerurl = fix_url("https://thepiratebay.org")

        # Build search URL # TODO: remove
        providerurl = (
            providerurl + "/search/" + tpb_term + "/0/7/"
        )  # 7 is sort by seeders

        # Pick category for torrents
        if headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly:
            category = "104"  # FLAC
            maxsize = 10000000000
        elif headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless:
            category = "100"  # General audio category
            maxsize = 10000000000
        else:
            category = "101"  # MP3 only
            maxsize = 300000000

        # Request content
        logger.info("Searching The Pirate Bay using term: %s", tpb_term)

        # Check if a downloader is configured that automatically downloads torrent files that are opened.
        if headphones.CONFIG.TORRENT_DOWNLOADER == 0:
            logger.info(
                "The pirate bay does not give direct torrent links"
                + " anymore. Instead goto: Apply Settings>Download settings>Magnet"
                + " link options and select:Convert to convert magnet links to "
                + "Torrent files and export them to a black hole dir. %s",
                tpb_term,
            )
        else:
            # TODO: Apply Settings>Download settings>Magnet link options:
            # Ignore: Don't do anything. (Because you won't get torrent directly anymore.)
            # Open: Do what it used to do.
            # TODO: Determine how to open magnet link from this code.

            # Convert: Convert magnet to .torrent file
            # Get magnet links
            # Select magnet links based on quality, size, seeds,
            # Get titles, size, quality
            # Append to results
            # TODO: remove the url aspect from this Result.
            resultlist.append(
                Result(title, size, url, provider, "torrent", match)
            )

            # Embed: Do what it used to do.
            # TODO: Determine which code ensures the embed action is completed.
            if size < maxsize and minimumseeders < seeds and url is not None:
                pass

        ### May be relevant on how to download torrent directly
        ###for torrent in match_torrents:
        ###        if not torrent.file_path:
        ###            torrent.group.update_group_data()  # will load the file_path for the individual torrents
        ###        resultlist.append(
        ###            Result(
        ###                torrent.file_path,
        ###                torrent.size,
        ###                orpheusobj.generate_torrent_link(torrent.id),
        ###                provider,
        ###                'torrent',
        ###                True
        ###            )
        ###        )

        # TODO: Remove
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2243.2 Safari/537.36"
        }

        # TODO: Remove
        data = request.request_soup(
            url=providerurl + category, headers=headers
        )

        # Process content
        if data:
            rows = data.select("table tbody tr")

            if not rows:
                # TODO: adjust to amount of magnet links retrieved.
                logger.info(
                    "No results found from The Pirate Bay using term: %s"
                    % tpb_term
                )
            else:
                # TODO: Remove.
                for item in rows:
                    try:
                        url = None
                        title = "".join(item.find("a", {"class": "detLink"}))
                        seeds = int(
                            "".join(item.find("td", {"align": "right"}))
                        )

                        if headphones.CONFIG.TORRENT_DOWNLOADER == 0:
                            try:
                                url = item.find(
                                    "a", {"title": "Download this torrent"}
                                )["href"]
                            except TypeError:
                                if headphones.CONFIG.MAGNET_LINKS != 0:
                                    url = item.findAll("a")[3]["href"]
                                else:
                                    logger.info(
                                        '"%s" only has a magnet link, skipping'
                                        % title
                                    )
                                    continue
                        else:
                            url = item.findAll("a")[3]["href"]

                        if url.lower().startswith("//"):
                            url = "http:" + url

                        formatted_size = (
                            re.search("Size (.*),", str(item))
                            .group(1)
                            .replace("\xa0", " ")
                        )
                        size = helpers.piratesize(formatted_size)

                        if (
                            size < maxsize
                            and minimumseeders < seeds
                            and url is not None
                        ):
                            match = True
                            logger.info(
                                "Found %s. Size: %s" % (title, formatted_size)
                            )
                        else:
                            match = False
                            logger.info(
                                "%s is larger than the maxsize or has too little seeders for this category, "
                                "skipping. (Size: %i bytes, Seeders: %i)"
                                % (title, size, int(seeds))
                            )

                        resultlist.append(
                            Result(
                                title, size, url, provider, "torrent", match
                            )
                        )
                    except Exception as e:
                        logger.error(
                            "An unknown error occurred in the Pirate Bay parser: %s"
                            % e
                        )

    # Old Pirate Bay Compatible
    if headphones.CONFIG.OLDPIRATEBAY:
        provider = "Old Pirate Bay"
        tpb_term = term.replace("!", "")

        # Pick category for torrents
        if headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly:
            maxsize = 10000000000
        elif headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless:
            maxsize = 10000000000
        else:
            maxsize = 300000000

        # Requesting content
        logger.info("Parsing results from Old Pirate Bay")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2243.2 Safari/537.36"
        }
        provider_url = (
            fix_url(headphones.CONFIG.OLDPIRATEBAY_URL)
            + "/search.php?"
            + urllib3.parse.urlencode({"q": tpb_term, "iht": 6})
        )

        data = request.request_soup(url=provider_url, headers=headers)

        # Process content
        if data:
            rows = data.select("table tbody tr")

            if not rows:
                logger.info("No results found")
            else:
                for item in rows:
                    try:
                        links = item.select("td.title-row a")

                        title = links[1].text
                        seeds = int(item.select("td.seeders-row")[0].text)
                        url = links[0][
                            "href"
                        ]  # Magnet link. The actual download link is not based on the URL

                        formatted_size = item.select("td.size-row")[0].text
                        size = helpers.piratesize(formatted_size)

                        if (
                            size < maxsize
                            and minimumseeders < seeds
                            and url is not None
                        ):
                            match = True
                            logger.info(
                                "Found %s. Size: %s" % (title, formatted_size)
                            )
                        else:
                            match = False
                            logger.info(
                                "%s is larger than the maxsize or has too little seeders for this category, "
                                "skipping. (Size: %i bytes, Seeders: %i)"
                                % (title, size, int(seeds))
                            )

                        resultlist.append(
                            Result(
                                title, size, url, provider, "torrent", match
                            )
                        )
                    except Exception as e:
                        logger.error(
                            "An unknown error occurred in the Old Pirate Bay parser: %s"
                            % e
                        )
    return resultlist
