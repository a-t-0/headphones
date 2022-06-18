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

import datetime
import re
import string

from pygazelle import api as gazelleapi
from pygazelle import encoding as gazelleencoding
from pygazelle import format as gazelleformat
from pygazelle import release_type as gazellerelease_type
from unidecode import unidecode

import headphones
from headphones import (
    db,
    helpers,
    logger,
    request,
    rutracker,
)
from headphones.common import USER_AGENT
from headphones.downloader import send_to_downloader
from headphones.piratebay_searcher import fix_url, search_piratebay
from headphones.preprocessor import preprocess
from headphones.types import Result

# Magnet to torrent services, for Black hole. Stolen from CouchPotato.
TORRENT_TO_MAGNET_SERVICES = [
    "https://itorrents.org/torrent/%s.torrent",
    "https://cache.torrentgalaxy.org/get/%s",
    "https://www.seedpeer.me/torrent/%s",
]

# Persistent Orpheus.network API object
orpheusobj = None
ruobj = None
# Persistent RED API object
redobj = None


def searchforalbum(
    albumid=None, new=False, losslessOnly=False, choose_specific_download=False
):
    logger.info("Searching for wanted albums")
    myDB = db.DBConnection()

    if not albumid:
        results = myDB.select(
            'SELECT * from albums WHERE Status="Wanted" OR Status="Wanted Lossless"'
        )

        for album in results:

            if not album["AlbumTitle"] or not album["ArtistName"]:
                logger.warn(
                    "Skipping release %s. No title available", album["AlbumID"]
                )
                continue

            if (
                headphones.CONFIG.WAIT_UNTIL_RELEASE_DATE
                and album["ReleaseDate"]
            ):
                release_date = strptime_musicbrainz(album["ReleaseDate"])
                if not release_date:
                    logger.warn(
                        "No valid date for: %s. Skipping automatic search"
                        % album["AlbumTitle"]
                    )
                    continue

                elif release_date > datetime.datetime.today():
                    logger.info(
                        "Skipping: %s. Waiting for release date of: %s"
                        % (album["AlbumTitle"], album["ReleaseDate"])
                    )
                    continue

            new = True

            if album["Status"] == "Wanted Lossless":
                losslessOnly = True

            logger.info(
                'Searching for "%s - %s" since it is marked as wanted'
                % (album["ArtistName"], album["AlbumTitle"])
            )
            do_sorted_search(album, new, losslessOnly)

    elif albumid and choose_specific_download:
        album = myDB.action(
            "SELECT * from albums WHERE AlbumID=?", [albumid]
        ).fetchone()
        logger.info(
            'Searching for "%s - %s"'
            % (album["ArtistName"], album["AlbumTitle"])
        )
        results = do_sorted_search(
            album, new, losslessOnly, choose_specific_download=True
        )
        return results

    else:
        album = myDB.action(
            "SELECT * from albums WHERE AlbumID=?", [albumid]
        ).fetchone()
        logger.info(
            'Searching for "%s - %s" since it was marked as wanted'
            % (album["ArtistName"], album["AlbumTitle"])
        )
        do_sorted_search(album, new, losslessOnly)

    logger.info("Search for wanted albums complete")


def strptime_musicbrainz(date_str):
    """Release date as returned by Musicbrainz may contain the full date (Year-
    Month-Day) but it may as well be just Year-Month or even just the year.

    Args:
        date_str: the date as a string (ex: "2003-05-01", "2003-03", "2003")

    Returns:
        The more accurate datetime object we can create or None if parse failed
    """
    acceptable_formats = ("%Y-%m-%d", "%Y-%m", "%Y")
    for date_format in acceptable_formats:
        try:
            return datetime.datetime.strptime(date_str, date_format)
        except:
            pass
    return None


def do_sorted_search(album, new, losslessOnly, choose_specific_download=False):
    NZB_PROVIDERS = (
        headphones.CONFIG.HEADPHONES_INDEXER
        or headphones.CONFIG.NEWZNAB
        or headphones.CONFIG.NZBSORG
        or headphones.CONFIG.OMGWTFNZBS
    )

    NZB_DOWNLOADERS = (
        headphones.CONFIG.SAB_HOST
        or headphones.CONFIG.BLACKHOLE_DIR
        or headphones.CONFIG.NZBGET_HOST
    )

    TORRENT_PROVIDERS = (
        headphones.CONFIG.TORZNAB
        or headphones.CONFIG.PIRATEBAY
        or headphones.CONFIG.OLDPIRATEBAY
        or headphones.CONFIG.WAFFLES
        or headphones.CONFIG.RUTRACKER
        or headphones.CONFIG.ORPHEUS
        or headphones.CONFIG.REDACTED
    )

    results = []
    myDB = db.DBConnection()
    albumlength = myDB.select(
        "SELECT sum(TrackDuration) from tracks WHERE AlbumID=?",
        [album["AlbumID"]],
    )[0][0]

    if headphones.CONFIG.PREFER_TORRENTS == 0 and not choose_specific_download:

        if NZB_PROVIDERS and NZB_DOWNLOADERS:
            results = searchNZB(album, new, losslessOnly, albumlength)

        if not results and TORRENT_PROVIDERS:
            results = searchTorrent(album, new, losslessOnly, albumlength)

    elif (
        headphones.CONFIG.PREFER_TORRENTS == 1 and not choose_specific_download
    ):

        if TORRENT_PROVIDERS:
            results = searchTorrent(album, new, losslessOnly, albumlength)

        if not results and NZB_PROVIDERS and NZB_DOWNLOADERS:
            results = searchNZB(album, new, losslessOnly, albumlength)

    else:

        nzb_results = None
        torrent_results = None

        if NZB_PROVIDERS and NZB_DOWNLOADERS:
            nzb_results = searchNZB(
                album, new, losslessOnly, albumlength, choose_specific_download
            )

        if TORRENT_PROVIDERS:
            torrent_results = searchTorrent(
                album, new, losslessOnly, albumlength, choose_specific_download
            )

        if not nzb_results:
            nzb_results = []

        if not torrent_results:
            torrent_results = []

        results = nzb_results + torrent_results

    if choose_specific_download:
        return results

    # Filter all results that do not comply
    results = [result for result in results if result.matches]

    # Sort the remaining results
    sorted_search_results = sort_search_results(
        results, album, new, albumlength
    )

    if not sorted_search_results:
        return

    logger.info(
        "Making sure we can download the best result: "
        f"{sorted_search_results[0].title} from {sorted_search_results[0].provider}"
    )
    (data, result) = preprocess(sorted_search_results, ruobj)

    if data and result:
        send_to_downloader(
            data, result, album, ruobj, TORRENT_TO_MAGNET_SERVICES
        )


def more_filtering(results, album, albumlength, new):
    low_size_limit = None
    high_size_limit = None
    allow_lossless = False
    myDB = db.DBConnection()

    # Lossless - ignore results if target size outside bitrate range
    if (
        headphones.CONFIG.PREFERRED_QUALITY == 3
        and albumlength
        and (
            headphones.CONFIG.LOSSLESS_BITRATE_FROM
            or headphones.CONFIG.LOSSLESS_BITRATE_TO
        )
    ):
        if headphones.CONFIG.LOSSLESS_BITRATE_FROM:
            low_size_limit = (
                albumlength
                / 1000
                * int(headphones.CONFIG.LOSSLESS_BITRATE_FROM)
                * 128
            )
        if headphones.CONFIG.LOSSLESS_BITRATE_TO:
            high_size_limit = (
                albumlength
                / 1000
                * int(headphones.CONFIG.LOSSLESS_BITRATE_TO)
                * 128
            )

    # Preferred Bitrate - ignore results if target size outside % buffer
    elif (
        headphones.CONFIG.PREFERRED_QUALITY == 2
        and headphones.CONFIG.PREFERRED_BITRATE
    ):
        logger.debug(
            "Target bitrate: %s kbps" % headphones.CONFIG.PREFERRED_BITRATE
        )
        if albumlength:
            targetsize = (
                albumlength
                / 1000
                * int(headphones.CONFIG.PREFERRED_BITRATE)
                * 128
            )
            logger.info("Target size: %s" % helpers.bytes_to_mb(targetsize))
            if headphones.CONFIG.PREFERRED_BITRATE_LOW_BUFFER:
                low_size_limit = (
                    targetsize
                    * int(headphones.CONFIG.PREFERRED_BITRATE_LOW_BUFFER)
                    / 100
                )
            if headphones.CONFIG.PREFERRED_BITRATE_HIGH_BUFFER:
                high_size_limit = (
                    targetsize
                    * int(headphones.CONFIG.PREFERRED_BITRATE_HIGH_BUFFER)
                    / 100
                )
                if headphones.CONFIG.PREFERRED_BITRATE_ALLOW_LOSSLESS:
                    allow_lossless = True

    newlist = []

    for result in results:

        if low_size_limit and result.size < low_size_limit:
            logger.info(
                f"{result.title} from {result.provider} is too small for this album. "
                f"(Size: {result.size}, MinSize: {helpers.bytes_to_mb(low_size_limit)})"
            )
            continue

        if high_size_limit and result.size > high_size_limit:
            logger.info(
                f"{result.title} from {result.provider} is too large for this album. "
                f"(Size: {result.size}, MaxSize: {helpers.bytes_to_mb(high_size_limit)})"
            )
            # Keep lossless results if there are no good lossy matches
            if not (allow_lossless and "flac" in result.title.lower()):
                continue

        if new:
            alreadydownloaded = myDB.select(
                "SELECT * from snatched WHERE URL=?", [result.url]
            )
            if len(alreadydownloaded):
                logger.info(
                    f"{result.title} has already been downloaded from "
                    f"{result.provider}. Skipping."
                )
                continue

        newlist.append(result)

    return newlist


def sort_by_priority_then_size(rs):
    return list(
        map(
            lambda x: x[0],
            sorted(
                rs, key=lambda x: (x[0].matches, x[1], x[0].size), reverse=True
            ),
        )
    )


def sort_search_results(resultlist, album, new, albumlength):
    if new and not len(resultlist):
        logger.info(
            "No more results found for:  %s - %s"
            % (album["ArtistName"], album["AlbumTitle"])
        )
        return None

    # Add a priority if it has any of the preferred words
    results_with_priority = []
    preferred_words = helpers.split_string(headphones.CONFIG.PREFERRED_WORDS)
    for result in resultlist:
        priority = 0
        for word in preferred_words:
            if word.lower() in [result.title.lower(), result.provider.lower()]:
                priority += len(preferred_words) - preferred_words.index(word)
        results_with_priority.append((result, priority))

    if (
        headphones.CONFIG.PREFERRED_QUALITY == 2
        and headphones.CONFIG.PREFERRED_BITRATE
    ):

        try:
            targetsize = (
                albumlength
                / 1000
                * int(headphones.CONFIG.PREFERRED_BITRATE)
                * 128
            )
            if not targetsize:
                logger.info(
                    f"No track information for {album['ArtistName']} - "
                    f"{album['AlbumTitle']}. Defaulting to highest quality"
                )
                return sort_by_priority_then_size(results_with_priority)

            else:
                lossy_results_with_delta = []
                lossless_results = []

                for result, priority in results_with_priority:

                    # Add lossless results to the "flac list" which we can use if there are no good lossy matches
                    if "flac" in result.title.lower():
                        lossless_results.append((result, priority))
                    else:
                        delta = abs(targetsize - result.size)
                        lossy_results_with_delta.append(
                            (result, priority, delta)
                        )

                return list(
                    map(
                        lambda x: x[0],
                        sorted(
                            lossy_results_with_delta,
                            key=lambda x: (-x[0].matches, -x[1], x[2]),
                        ),
                    )
                )

                if (
                    not len(lossy_results_with_delta)
                    and len(lossless_results)
                    and headphones.CONFIG.PREFERRED_BITRATE_ALLOW_LOSSLESS
                ):
                    logger.info(
                        "Since there were no appropriate lossy matches "
                        "(and at least one lossless match), going to use "
                        "lossless instead"
                    )
                    return sort_by_priority_then_size(results_with_priority)

        except Exception:
            logger.exception("Unhandled exception")
            logger.info(
                f"No track information for {album['ArtistName']} - "
                f"{album['AlbumTitle']}. Defaulting to highest quality"
            )
            return sort_by_priority_then_size(results_with_priority)

    else:
        return sort_by_priority_then_size(results_with_priority)

    logger.info(
        f"No appropriate matches found for {album['ArtistName']} - "
        f"{album['AlbumTitle']}"
    )
    return None


def searchNZB(
    album,
    new=False,
    losslessOnly=False,
    albumlength=None,
    choose_specific_download=False,
):
    reldate = album["ReleaseDate"]
    year = get_year_from_release_date(reldate)

    replacements = {
        "...": "",
        " & ": " ",
        " = ": " ",
        "?": "",
        "$": "s",
        " + ": " ",
        '"': "",
        ",": "",
        "*": "",
        ".": "",
        ":": "",
    }

    cleanalbum = unidecode(
        helpers.replace_all(album["AlbumTitle"], replacements)
    ).strip()
    cleanartist = unidecode(
        helpers.replace_all(album["ArtistName"], replacements)
    ).strip()

    # Use the provided search term if available, otherwise build a search term
    if album["SearchTerm"]:
        term = album["SearchTerm"]
    elif album["Type"] == "part of":
        term = cleanalbum + " " + year
    else:
        # FLAC usually doesn't have a year for some reason so leave it out.
        # Various Artist albums might be listed as VA, so I'll leave that out too
        # Only use the year if the term could return a bunch of different albums, i.e. self-titled albums
        if (
            album["ArtistName"] in album["AlbumTitle"]
            or len(album["ArtistName"]) < 4
            or len(album["AlbumTitle"]) < 4
        ):
            term = cleanartist + " " + cleanalbum + " " + year
        elif album["ArtistName"] == "Various Artists":
            term = cleanalbum + " " + year
        else:
            term = cleanartist + " " + cleanalbum

    # Replace bad characters in the term
    term = re.sub(r"[\.\-\/]", " ", term)
    artistterm = re.sub(r"[\.\-\/]", " ", cleanartist)

    # If Preferred Bitrate and High Limit and Allow Lossless then get both lossy and lossless
    if (
        headphones.CONFIG.PREFERRED_QUALITY == 2
        and headphones.CONFIG.PREFERRED_BITRATE
        and headphones.CONFIG.PREFERRED_BITRATE_HIGH_BUFFER
        and headphones.CONFIG.PREFERRED_BITRATE_ALLOW_LOSSLESS
    ):
        allow_lossless = True
    else:
        allow_lossless = False

    logger.debug("Using search term: %s" % term)

    resultlist = []

    if headphones.CONFIG.HEADPHONES_INDEXER:
        provider = "headphones"

        if headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly:
            categories = "3040"
        elif headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless:
            categories = "3040,3010"
        else:
            categories = "3010"

        if album["Type"] == "Other":
            logger.info(
                "Album type is audiobook/spokenword. Using audiobook category"
            )
            categories = "3030"

        # Request results
        logger.info("Searching Headphones Indexer with search term: %s" % term)

        headers = {"User-Agent": USER_AGENT}
        params = {
            "t": "search",
            "cat": categories,
            "apikey": "964d601959918a578a670984bdee9357",
            "maxage": headphones.CONFIG.USENET_RETENTION,
            "q": term,
        }

        data = request.request_feed(
            url="https://indexer.codeshy.com/api",
            params=params,
            headers=headers,
            auth=(headphones.CONFIG.HPUSER, headphones.CONFIG.HPPASS),
        )

        # Process feed
        if data:
            if not len(data.entries):
                logger.info(
                    "No results found from %s for %s"
                    % ("Headphones Index", term)
                )
            else:
                for item in data.entries:
                    try:
                        url = item.link
                        title = item.title
                        size = int(item.links[1]["length"])

                        resultlist.append(
                            Result(title, size, url, provider, "nzb", True)
                        )
                        logger.info(
                            "Found %s. Size: %s"
                            % (title, helpers.bytes_to_mb(size))
                        )
                    except Exception as e:
                        logger.error(
                            "An unknown error occurred trying to parse the feed: %s"
                            % e
                        )

    if headphones.CONFIG.NEWZNAB:
        provider = "newznab"
        newznab_hosts = []

        if (
            headphones.CONFIG.NEWZNAB_HOST
            and headphones.CONFIG.NEWZNAB_ENABLED
        ):
            newznab_hosts.append(
                (
                    headphones.CONFIG.NEWZNAB_HOST,
                    headphones.CONFIG.NEWZNAB_APIKEY,
                    headphones.CONFIG.NEWZNAB_ENABLED,
                )
            )

        for newznab_host in headphones.CONFIG.get_extra_newznabs():
            if newznab_host[2] == "1" or newznab_host[2] == 1:
                newznab_hosts.append(newznab_host)

        if headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly:
            categories = "3040"
        elif headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless:
            categories = "3040,3010"
        else:
            categories = "3010"

        if album["Type"] == "Other":
            categories = "3030"
            logger.info(
                "Album type is audiobook/spokenword. Using audiobook category"
            )

        for newznab_host in newznab_hosts:

            provider = newznab_host[0]

            # Add a little mod for kere.ws
            if newznab_host[0] == "https://kere.ws":
                if categories == "3040":
                    categories = categories + ",4070"
                elif categories == "3040,3010":
                    categories = categories + ",4070,4010"
                elif categories == "3010":
                    categories = categories + ",4010"
                else:
                    categories = categories + ",4050"

            # Request results
            logger.info(
                "Parsing results from %s using search term: %s"
                % (newznab_host[0], term)
            )

            headers = {"User-Agent": USER_AGENT}
            params = {
                "t": "search",
                "apikey": newznab_host[1],
                "cat": categories,
                "maxage": headphones.CONFIG.USENET_RETENTION,
                "q": term,
            }

            data = request.request_feed(
                url=newznab_host[0] + "/api?", params=params, headers=headers
            )

            # Process feed
            if data:
                if not len(data.entries):
                    logger.info(
                        "No results found from %s for %s",
                        newznab_host[0],
                        term,
                    )
                else:
                    for item in data.entries:
                        try:
                            url = item.link
                            title = item.title
                            size = int(item.links[1]["length"])
                            if all(
                                word.lower() in title.lower()
                                for word in term.split()
                            ):
                                logger.info(
                                    "Found %s. Size: %s"
                                    % (title, helpers.bytes_to_mb(size))
                                )
                                resultlist.append(
                                    Result(
                                        title, size, url, provider, "nzb", True
                                    )
                                )
                            else:
                                logger.info(
                                    "Skipping %s, not all search term words found"
                                    % title
                                )

                        except Exception as e:
                            logger.exception(
                                "An unknown error occurred trying to parse the feed: %s"
                                % e
                            )

    if headphones.CONFIG.NZBSORG:
        provider = "nzbsorg"
        if headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly:
            categories = "3040"
        elif headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless:
            categories = "3040,3010"
        else:
            categories = "3010"

        if album["Type"] == "Other":
            categories = "3030"
            logger.info(
                "Album type is audiobook/spokenword. Using audiobook category"
            )

        headers = {"User-Agent": USER_AGENT}
        params = {
            "t": "search",
            "apikey": headphones.CONFIG.NZBSORG_HASH,
            "cat": categories,
            "maxage": headphones.CONFIG.USENET_RETENTION,
            "q": term,
        }

        data = request.request_feed(
            url="https://beta.nzbs.org/api",
            params=params,
            headers=headers,
            timeout=5,
        )

        logger.info(
            "Parsing results from nzbs.org using search term: %s" % term
        )
        # Process feed
        if data:
            if not len(data.entries):
                logger.info("No results found from nzbs.org for %s" % term)
            else:
                for item in data.entries:
                    try:
                        url = item.link
                        title = item.title
                        size = int(item.links[1]["length"])

                        resultlist.append(
                            Result(title, size, url, provider, "nzb", True)
                        )
                        logger.info(
                            "Found %s. Size: %s"
                            % (title, helpers.bytes_to_mb(size))
                        )
                    except Exception:
                        logger.exception(
                            "Unhandled exception while parsing feed"
                        )

    if headphones.CONFIG.OMGWTFNZBS:
        provider = "omgwtfnzbs"

        if headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly:
            categories = "22"
        elif headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless:
            categories = "22,7"
        else:
            categories = "7"

        if album["Type"] == "Other":
            categories = "29"
            logger.info(
                "Album type is audiobook/spokenword. Searching all music categories"
            )

        # Request results
        logger.info(
            "Parsing results from omgwtfnzbs using search term: %s" % term
        )

        headers = {"User-Agent": USER_AGENT}
        params = {
            "user": headphones.CONFIG.OMGWTFNZBS_UID,
            "api": headphones.CONFIG.OMGWTFNZBS_APIKEY,
            "catid": categories,
            "retention": headphones.CONFIG.USENET_RETENTION,
            "search": term,
        }

        data = request.request_json(
            url="https://api.omgwtfnzbs.me/json/",
            params=params,
            headers=headers,
        )

        # Parse response
        if data:
            if "notice" in data:
                logger.info(
                    "No results returned from omgwtfnzbs: %s" % data["notice"]
                )
            else:
                for item in data:
                    try:
                        url = item["getnzb"]
                        title = item["release"]
                        size = int(item["sizebytes"])

                        resultlist.append(
                            Result(title, size, url, provider, "nzb", True)
                        )
                        logger.info(
                            "Found %s. Size: %s",
                            title,
                            helpers.bytes_to_mb(size),
                        )
                    except Exception:
                        logger.exception("Unhandled exception")

    # attempt to verify that this isn't a substring result
    # when looking for "Foo - Foo" we don't want "Foobar"
    # this should be less of an issue when it isn't a self-titled album so we'll only check vs artist
    #
    # Also will filter flac & remix albums if not specifically looking for it
    # This code also checks the ignored words and required words
    results = [
        result
        for result in resultlist
        if verifyresult(result.title, artistterm, term, losslessOnly)
    ]

    # Additional filtering for size etc
    if results and not choose_specific_download:
        results = more_filtering(results, album, albumlength, new)

    return results


def verifyresult(title, artistterm, term, lossless):
    title = re.sub(r"[\.\-\/\_]", " ", title)

    # if artistterm != 'Various Artists':
    #
    #    if not re.search('^' + re.escape(artistterm), title, re.IGNORECASE):
    #        #logger.info("Removed from results: " + title + " (artist not at string start).")
    #        #return False
    #    elif re.search(re.escape(artistterm) + '\w', title, re.IGNORECASE | re.UNICODE):
    #        logger.info("Removed from results: " + title + " (post substring result).")
    #        return False
    #    elif re.search('\w' + re.escape(artistterm), title, re.IGNORECASE | re.UNICODE):
    #        logger.info("Removed from results: " + title + " (pre substring result).")
    #        return False

    # another attempt to weed out substrings. We don't want "Vol III" when we were looking for "Vol II"

    # Filter out remix search results (if we're not looking for it)
    if "remix" not in term.lower() and "remix" in title.lower():
        logger.info(
            "Removed %s from results because it's a remix album and we're not looking for a remix album right now.",
            title,
        )
        return False

    # Filter out FLAC if we're not specifically looking for it
    if (
        headphones.CONFIG.PREFERRED_QUALITY == (0 or "0")
        and "flac" in title.lower()
        and not lossless
    ):
        logger.info(
            "Removed %s from results because it's a lossless album and we're not looking for a lossless album right now.",
            title,
        )
        return False

    if headphones.CONFIG.IGNORED_WORDS:
        for each_word in helpers.split_string(headphones.CONFIG.IGNORED_WORDS):
            if each_word.lower() in title.lower():
                logger.info(
                    "Removed '%s' from results because it contains ignored word: '%s'",
                    title,
                    each_word,
                )
                return False

    if headphones.CONFIG.REQUIRED_WORDS:
        for each_word in helpers.split_string(
            headphones.CONFIG.REQUIRED_WORDS
        ):
            if " OR " in each_word:
                or_words = helpers.split_string(each_word, "OR")
                if any(word.lower() in title.lower() for word in or_words):
                    continue
                else:
                    logger.info(
                        "Removed '%s' from results because it doesn't contain any of the required words in: '%s'",
                        title,
                        str(or_words),
                    )
                    return False
            if each_word.lower() not in title.lower():
                logger.info(
                    "Removed '%s' from results because it doesn't contain required word: '%s'",
                    title,
                    each_word,
                )
                return False

    if headphones.CONFIG.IGNORE_CLEAN_RELEASES:
        for each_word in ["clean", "edited", "censored"]:
            logger.debug(
                "Checking if '%s' is in search result: '%s'", each_word, title
            )
            if (
                each_word.lower() in title.lower()
                and each_word.lower() not in term.lower()
            ):
                logger.info(
                    "Removed '%s' from results because it contains clean album word: '%s'",
                    title,
                    each_word,
                )
                return False

    tokens = re.split(r"\W", term, re.IGNORECASE | re.UNICODE)
    for token in tokens:

        if not token:
            continue
        if token == "Various" or token == "Artists" or token == "VA":
            continue
        if not re.search(
            r"(?:\W|^)+" + token + r"(?:\W|$)+",
            title,
            re.IGNORECASE | re.UNICODE,
        ):
            cleantoken = "".join(
                c for c in token if c not in string.punctuation
            )
            if not not re.search(
                r"(?:\W|^)+" + cleantoken + r"(?:\W|$)+",
                title,
                re.IGNORECASE | re.UNICODE,
            ):
                dic = {"!": "i", "$": "s"}
                dumbtoken = helpers.replace_all(token, dic)
                if not not re.search(
                    r"(?:\W|^)+" + dumbtoken + r"(?:\W|$)+",
                    title,
                    re.IGNORECASE | re.UNICODE,
                ):
                    logger.info(
                        "Removed from results: %s (missing tokens: %s and %s)",
                        title,
                        token,
                        cleantoken,
                    )
                    return False

    return True


def searchTorrent(
    album,
    new=False,
    losslessOnly=False,
    albumlength=None,
    choose_specific_download=False,
):
    global orpheusobj  # persistent orpheus.network api object to reduce number of login attempts
    global redobj  # persistent redacted api object to reduce number of login attempts
    global ruobj  # and rutracker

    reldate = album["ReleaseDate"]

    year = get_year_from_release_date(reldate)

    # MERGE THIS WITH THE TERM CLEANUP FROM searchNZB
    replacements = {
        "...": "",
        " & ": " ",
        " = ": " ",
        "?": "",
        "$": "s",
        " + ": " ",
        '"': "",
        ",": " ",
        "*": "",
    }

    semi_cleanalbum = helpers.replace_all(album["AlbumTitle"], replacements)
    cleanalbum = unidecode(semi_cleanalbum)
    semi_cleanartist = helpers.replace_all(album["ArtistName"], replacements)
    cleanartist = unidecode(semi_cleanartist)

    # Use provided term if available, otherwise build our own (this code needs to be cleaned up since a lot
    # of these torrent providers are just using cleanartist/cleanalbum terms
    if album["SearchTerm"]:
        term = album["SearchTerm"]
    elif album["Type"] == "part of":
        term = cleanalbum + " " + year
    else:
        # FLAC usually doesn't have a year for some reason so I'll leave it out
        # Various Artist albums might be listed as VA, so I'll leave that out too
        # Only use the year if the term could return a bunch of different albums, i.e. self-titled albums
        if (
            album["ArtistName"] in album["AlbumTitle"]
            or len(album["ArtistName"]) < 4
            or len(album["AlbumTitle"]) < 4
        ):
            term = cleanartist + " " + cleanalbum + " " + year
        elif album["ArtistName"] == "Various Artists":
            term = cleanalbum + " " + year
        else:
            term = cleanartist + " " + cleanalbum

    # Save user search term
    if album["SearchTerm"]:
        usersearchterm = term
    else:
        usersearchterm = ""

    semi_clean_artist_term = re.sub(r"[\.\-\/]", " ", semi_cleanartist)
    semi_clean_album_term = re.sub(r"[\.\-\/]", " ", semi_cleanalbum)
    # Replace bad characters in the term
    term = re.sub(r"[\.\-\/]", " ", term)
    artistterm = re.sub(r"[\.\-\/]", " ", cleanartist)
    albumterm = re.sub(r"[\.\-\/]", " ", cleanalbum)

    # If Preferred Bitrate and High Limit and Allow Lossless then get both lossy and lossless
    if (
        headphones.CONFIG.PREFERRED_QUALITY == 2
        and headphones.CONFIG.PREFERRED_BITRATE
        and headphones.CONFIG.PREFERRED_BITRATE_HIGH_BUFFER
        and headphones.CONFIG.PREFERRED_BITRATE_ALLOW_LOSSLESS
    ):
        allow_lossless = True
    else:
        allow_lossless = False

    logger.debug("Using search term: %s" % term)

    resultlist = []
    minimumseeders = int(headphones.CONFIG.NUMBEROFSEEDERS) - 1

    if headphones.CONFIG.TORZNAB:
        provider = "torznab"
        torznab_hosts = []

        if (
            headphones.CONFIG.TORZNAB_HOST
            and headphones.CONFIG.TORZNAB_ENABLED
        ):
            torznab_hosts.append(
                (
                    headphones.CONFIG.TORZNAB_HOST,
                    headphones.CONFIG.TORZNAB_APIKEY,
                    headphones.CONFIG.TORZNAB_RATIO,
                    headphones.CONFIG.TORZNAB_ENABLED,
                )
            )

        for torznab_host in headphones.CONFIG.get_extra_torznabs():
            if torznab_host[3] == "1" or torznab_host[3] == 1:
                torznab_hosts.append(torznab_host)

        if headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly:
            categories = "3040"
            maxsize = 10000000000
        elif headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless:
            categories = "3040,3010,3050"
            maxsize = 10000000000
        else:
            categories = "3010,3050"
            maxsize = 300000000

        if album["Type"] == "Other":
            categories = "3030"
            logger.info(
                "Album type is audiobook/spokenword. Using audiobook category"
            )

        for torznab_host in torznab_hosts:

            provider = torznab_host[0]

            # Format Jackett provider
            if "api/v2.0/indexers" in torznab_host[0]:
                provider = (
                    "Jackett_"
                    + provider.split("/indexers/", 1)[1].split("/", 1)[0]
                )

            # Request results
            logger.info(
                "Parsing results from %s using search term: %s"
                % (provider, term)
            )

            headers = {"User-Agent": USER_AGENT}
            params = {
                "t": "search",
                "apikey": torznab_host[1],
                "cat": categories,
                "maxage": headphones.CONFIG.USENET_RETENTION,
                "q": term,
            }

            data = request.request_soup(
                url=torznab_host[0], params=params, headers=headers
            )

            # Process feed
            if data:
                items = data.find_all("item")
                if not items:
                    logger.info(
                        "No results found from %s for %s", provider, term
                    )
                else:
                    for item in items:
                        try:
                            title = item.title.get_text()
                            url = item.find("link").next_sibling.strip()
                            seeders = int(
                                item.find(
                                    "torznab:attr", attrs={"name": "seeders"}
                                ).get("value")
                            )

                            # Torrentech hack - size currently not returned, make it up
                            if "torrentech" in torznab_host[0]:
                                if albumlength:
                                    if "Lossless" in title:
                                        size = albumlength / 1000 * 800 * 128
                                    elif "MP3" in title:
                                        size = albumlength / 1000 * 320 * 128
                                    else:
                                        size = albumlength / 1000 * 256 * 128
                                else:
                                    logger.info(
                                        "Skipping %s, could not determine size"
                                        % title
                                    )
                                    continue
                            elif item.size:
                                size = int(item.size.string)
                            else:
                                size = int(
                                    item.find(
                                        "torznab:attr", attrs={"name": "size"}
                                    ).get("value")
                                )

                            if all(
                                word.lower() in title.lower()
                                for word in term.split()
                            ):
                                if size < maxsize and minimumseeders < seeders:
                                    logger.info(
                                        "Found %s. Size: %s"
                                        % (title, helpers.bytes_to_mb(size))
                                    )
                                    resultlist.append(
                                        Result(
                                            title,
                                            size,
                                            url,
                                            provider,
                                            "torrent",
                                            True,
                                        )
                                    )
                                else:
                                    logger.info(
                                        "%s is larger than the maxsize or has too little seeders for this category, "
                                        "skipping. (Size: %i bytes, Seeders: %d)",
                                        title,
                                        size,
                                        seeders,
                                    )
                            else:
                                logger.info(
                                    "Skipping %s, not all search term words found"
                                    % title
                                )

                        except Exception as e:
                            logger.exception(
                                "An unknown error occurred trying to parse the feed: %s"
                                % e
                            )

    if headphones.CONFIG.WAFFLES:
        provider = "Waffles.ch"
        providerurl = fix_url("https://waffles.ch/browse.php")

        bitrate = None
        if headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly:
            format = "FLAC"
            bitrate = "(Lossless)"
            maxsize = 10000000000
        elif headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless:
            format = "FLAC OR MP3"
            maxsize = 10000000000
        else:
            format = "MP3"
            maxsize = 300000000

        if not usersearchterm:
            query_items = [
                'artist:"%s"' % artistterm,
                'album:"%s"' % albumterm,
                "year:(%s)" % year,
            ]
        else:
            query_items = [usersearchterm]

        query_items.extend(
            ["format:(%s)" % format, "size:[0 TO %d]" % maxsize]
        )
        # (25/03/2017 Waffles back up after 5 months, all torrents currently have no seeders, remove for now)
        # '-seeders:0'])  cut out dead torrents

        if bitrate:
            query_items.append('bitrate:"%s"' % bitrate)

        # Requesting content
        logger.info("Parsing results from Waffles.ch")

        params = {
            "uid": headphones.CONFIG.WAFFLES_UID,
            "passkey": headphones.CONFIG.WAFFLES_PASSKEY,
            "rss": "1",
            "c0": "1",
            "s": "seeders",  # sort by
            "d": "desc",  # direction
            "q": " ".join(query_items),
        }

        data = request.request_feed(url=providerurl, params=params, timeout=20)

        # Process feed
        if data:
            if not len(data.entries):
                logger.info("No results found from %s for %s", provider, term)
            else:
                for item in data.entries:
                    try:
                        title = item.title
                        desc_match = re.search(
                            r"Size: (\d+)<", item.description
                        )
                        size = int(desc_match.group(1))
                        url = item.link
                        resultlist.append(
                            Result(title, size, url, provider, "torrent", True)
                        )
                        logger.info(
                            "Found %s. Size: %s",
                            title,
                            helpers.bytes_to_mb(size),
                        )
                    except Exception as e:
                        logger.error(
                            "An error occurred while trying to parse the response from Waffles.ch: %s",
                            e,
                        )

    # rutracker.org
    if headphones.CONFIG.RUTRACKER:
        provider = "rutracker.org"

        # Ignore if release date not specified, results too unpredictable
        if not year and not usersearchterm:
            logger.info(
                "Release date not specified, ignoring for rutracker.org"
            )
        else:
            if headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly:
                format = "lossless"
            elif headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless:
                format = "lossless+mp3"
            else:
                format = "mp3"

            # Login
            if not ruobj or not ruobj.logged_in():
                ruobj = rutracker.Rutracker()
                if not ruobj.login():
                    ruobj = None

            if ruobj and ruobj.logged_in():

                # build search url
                if not usersearchterm:
                    searchURL = ruobj.searchurl(
                        artistterm, albumterm, year, format
                    )
                else:
                    searchURL = ruobj.searchurl(
                        usersearchterm, " ", " ", format
                    )

                # parse results
                rulist = ruobj.search(searchURL)
                if rulist:
                    resultlist.extend(rulist)

    if headphones.CONFIG.ORPHEUS:
        provider = "Orpheus.network"
        providerurl = "https://orpheus.network/"

        bitrate = None
        bitrate_string = bitrate

        if (
            headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly
        ):  # Lossless Only mode
            search_formats = [gazelleformat.FLAC]
            maxsize = 10000000000
        elif (
            headphones.CONFIG.PREFERRED_QUALITY == 2
        ):  # Preferred quality mode
            search_formats = [None]  # should return all
            bitrate = headphones.CONFIG.PREFERRED_BITRATE
            if bitrate:
                if 225 <= int(bitrate) < 256:
                    bitrate = "V0"
                elif 200 <= int(bitrate) < 225:
                    bitrate = "V1"
                elif 175 <= int(bitrate) < 200:
                    bitrate = "V2"
                for encoding_string in gazelleencoding.ALL_ENCODINGS:
                    if re.search(bitrate, encoding_string, flags=re.I):
                        bitrate_string = encoding_string
                if bitrate_string not in gazelleencoding.ALL_ENCODINGS:
                    logger.info(
                        "Your preferred bitrate is not one of the available Orpheus.network filters, so not using it as a search parameter."
                    )
            maxsize = 10000000000
        elif (
            headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless
        ):  # Highest quality including lossless
            search_formats = [gazelleformat.FLAC, gazelleformat.MP3]
            maxsize = 10000000000
        else:  # Highest quality excluding lossless
            search_formats = [gazelleformat.MP3]
            maxsize = 300000000

        if not orpheusobj or not orpheusobj.logged_in():
            try:
                logger.info("Attempting to log in to Orpheus.network...")
                orpheusobj = gazelleapi.GazelleAPI(
                    headphones.CONFIG.ORPHEUS_USERNAME,
                    headphones.CONFIG.ORPHEUS_PASSWORD,
                    headphones.CONFIG.ORPHEUS_URL,
                )
                orpheusobj._login()
            except Exception as e:
                orpheusobj = None
                logger.error(
                    "Orpheus.network credentials incorrect or site is down. Error: %s %s"
                    % (e.__class__.__name__, str(e))
                )

        if orpheusobj and orpheusobj.logged_in():
            logger.info("Searching %s..." % provider)
            all_torrents = []

            album_type = ""

            # Specify release types to filter by
            if album["Type"] == "Album":
                album_type = [gazellerelease_type.ALBUM]
            if album["Type"] == "Soundtrack":
                album_type = [gazellerelease_type.SOUNDTRACK]
            if album["Type"] == "EP":
                album_type = [gazellerelease_type.EP]
            # No musicbrainz match for this type
            # if album['Type'] == 'Anthology':
            #   album_type = [gazellerelease_type.ANTHOLOGY]
            if album["Type"] == "Compilation":
                album_type = [gazellerelease_type.COMPILATION]
            if album["Type"] == "DJ-mix":
                album_type = [gazellerelease_type.DJ_MIX]
            if album["Type"] == "Single":
                album_type = [gazellerelease_type.SINGLE]
            if album["Type"] == "Live":
                album_type = [gazellerelease_type.LIVE_ALBUM]
            if album["Type"] == "Remix":
                album_type = [gazellerelease_type.REMIX]
            if album["Type"] == "Bootleg":
                album_type = [gazellerelease_type.BOOTLEG]
            if album["Type"] == "Interview":
                album_type = [gazellerelease_type.INTERVIEW]
            if album["Type"] == "Mixtape/Street":
                album_type = [gazellerelease_type.MIXTAPE]
            if album["Type"] == "Other":
                album_type = [gazellerelease_type.UNKNOWN]

            for search_format in search_formats:
                if usersearchterm:
                    all_torrents.extend(
                        orpheusobj.search_torrents(
                            searchstr=usersearchterm,
                            format=search_format,
                            encoding=bitrate_string,
                            releasetype=album_type,
                        )["results"]
                    )
                else:
                    all_torrents.extend(
                        orpheusobj.search_torrents(
                            artistname=semi_clean_artist_term,
                            groupname=semi_clean_album_term,
                            format=search_format,
                            encoding=bitrate_string,
                            releasetype=album_type,
                        )["results"]
                    )

            # filter on format, size, and num seeders
            logger.info(
                "Filtering torrents by format, maximum size, and minimum seeders..."
            )
            match_torrents = [
                t
                for t in all_torrents
                if t.size <= maxsize and t.seeders >= minimumseeders
            ]

            logger.info(
                "Remaining torrents: %s"
                % ", ".join(repr(torrent) for torrent in match_torrents)
            )

            # sort by times d/l'd
            if not len(match_torrents):
                logger.info(
                    "No results found from %s for %s after filtering"
                    % (provider, term)
                )
            elif len(match_torrents) > 1:
                logger.info(
                    "Found %d matching releases from %s for %s - %s after filtering"
                    % (len(match_torrents), provider, artistterm, albumterm)
                )
                logger.info("Sorting torrents by number of seeders...")
                match_torrents.sort(key=lambda x: int(x.seeders), reverse=True)
                if gazelleformat.MP3 in search_formats:
                    logger.info("Sorting torrents by seeders...")
                    match_torrents.sort(
                        key=lambda x: int(x.seeders), reverse=True
                    )
                if search_formats and None not in search_formats:
                    match_torrents.sort(
                        key=lambda x: int(search_formats.index(x.format))
                    )  # prefer lossless
                #                if bitrate:
                #                    match_torrents.sort(key=lambda x: re.match("mp3", x.getTorrentDetails(), flags=re.I), reverse=True)
                #                    match_torrents.sort(key=lambda x: str(bitrate) in x.getTorrentFolderName(), reverse=True)
                logger.info(
                    "New order: %s"
                    % ", ".join(repr(torrent) for torrent in match_torrents)
                )

            for torrent in match_torrents:
                if not torrent.file_path:
                    torrent.group.update_group_data()  # will load the file_path for the individual torrents
                resultlist.append(
                    Result(
                        torrent.file_path,
                        torrent.size,
                        orpheusobj.generate_torrent_link(torrent.id),
                        provider,
                        "torrent",
                        True,
                    )
                )

    # Redacted - Using same logic as What.CD as it's also Gazelle, so should really make this into something reusable
    if headphones.CONFIG.REDACTED:
        provider = "Redacted"
        providerurl = "https://redacted.ch"

        bitrate = None
        bitrate_string = bitrate

        if (
            headphones.CONFIG.PREFERRED_QUALITY == 3 or losslessOnly
        ):  # Lossless Only mode
            search_formats = [gazelleformat.FLAC]
            maxsize = 10000000000
        elif (
            headphones.CONFIG.PREFERRED_QUALITY == 2
        ):  # Preferred quality mode
            search_formats = [None]  # should return all
            bitrate = headphones.CONFIG.PREFERRED_BITRATE
            if bitrate:
                if 225 <= int(bitrate) < 256:
                    bitrate = "V0"
                elif 200 <= int(bitrate) < 225:
                    bitrate = "V1"
                elif 175 <= int(bitrate) < 200:
                    bitrate = "V2"
                for encoding_string in gazelleencoding.ALL_ENCODINGS:
                    if re.search(bitrate, encoding_string, flags=re.I):
                        bitrate_string = encoding_string
                if bitrate_string not in gazelleencoding.ALL_ENCODINGS:
                    logger.info(
                        "Your preferred bitrate is not one of the available RED filters, so not using it as a search parameter."
                    )
            maxsize = 10000000000
        elif (
            headphones.CONFIG.PREFERRED_QUALITY == 1 or allow_lossless
        ):  # Highest quality including lossless
            search_formats = [gazelleformat.FLAC, gazelleformat.MP3]
            maxsize = 10000000000
        else:  # Highest quality excluding lossless
            search_formats = [gazelleformat.MP3]
            maxsize = 300000000

        if not redobj or not redobj.logged_in():
            try:
                logger.info("Attempting to log in to Redacted...")
                redobj = gazelleapi.GazelleAPI(
                    headphones.CONFIG.REDACTED_USERNAME,
                    headphones.CONFIG.REDACTED_PASSWORD,
                    providerurl,
                )
                redobj._login()
            except Exception as e:
                redobj = None
                logger.error(
                    "Redacted credentials incorrect or site is down. Error: %s %s"
                    % (e.__class__.__name__, str(e))
                )

        if redobj and redobj.logged_in():
            logger.info("Searching %s..." % provider)
            all_torrents = []
            for search_format in search_formats:
                if usersearchterm:
                    all_torrents.extend(
                        redobj.search_torrents(
                            searchstr=usersearchterm,
                            format=search_format,
                            encoding=bitrate_string,
                        )["results"]
                    )
                else:
                    all_torrents.extend(
                        redobj.search_torrents(
                            artistname=semi_clean_artist_term,
                            groupname=semi_clean_album_term,
                            format=search_format,
                            encoding=bitrate_string,
                        )["results"]
                    )

            # filter on format, size, and num seeders
            logger.info(
                "Filtering torrents by format, maximum size, and minimum seeders..."
            )
            match_torrents = [
                t
                for t in all_torrents
                if t.size <= maxsize and t.seeders >= minimumseeders
            ]

            logger.info(
                "Remaining torrents: %s"
                % ", ".join(repr(torrent) for torrent in match_torrents)
            )

            # sort by times d/l'd
            if not len(match_torrents):
                logger.info(
                    "No results found from %s for %s after filtering"
                    % (provider, term)
                )
            elif len(match_torrents) > 1:
                logger.info(
                    "Found %d matching releases from %s for %s - %s after filtering"
                    % (len(match_torrents), provider, artistterm, albumterm)
                )
                logger.info(
                    "Sorting torrents by times snatched and preferred bitrate %s..."
                    % bitrate_string
                )
                match_torrents.sort(
                    key=lambda x: int(x.snatched), reverse=True
                )
                if gazelleformat.MP3 in search_formats:
                    # sort by size after rounding to nearest 10MB...hacky, but will favor highest quality
                    match_torrents.sort(
                        key=lambda x: int(
                            10 * round(x.size / 1024.0 / 1024.0 / 10.0)
                        ),
                        reverse=True,
                    )
                if search_formats and None not in search_formats:
                    match_torrents.sort(
                        key=lambda x: int(search_formats.index(x.format))
                    )  # prefer lossless
                #                if bitrate:
                #                    match_torrents.sort(key=lambda x: re.match("mp3", x.getTorrentDetails(), flags=re.I), reverse=True)
                #                    match_torrents.sort(key=lambda x: str(bitrate) in x.getTorrentFolderName(), reverse=True)
                logger.info(
                    "New order: %s"
                    % ", ".join(repr(torrent) for torrent in match_torrents)
                )

            for torrent in match_torrents:
                if not torrent.file_path:
                    torrent.group.update_group_data()  # will load the file_path for the individual torrents
                use_token = (
                    headphones.CONFIG.REDACTED_USE_FLTOKEN
                    and torrent.can_use_token
                )
                resultlist.append(
                    Result(
                        torrent.file_path,
                        torrent.size,
                        redobj.generate_torrent_link(torrent.id, use_token),
                        provider,
                        "torrent",
                        True,
                    )
                )

    # TODO: pass arguments.
    resultlist = search_piratebay(
        term, losslessOnly, allow_lossless, minimumseeders, resultlist
    )

    # attempt to verify that this isn't a substring result
    # when looking for "Foo - Foo" we don't want "Foobar"
    # this should be less of an issue when it isn't a self-titled album so we'll only check vs artist
    results = [
        result
        for result in resultlist
        if verifyresult(result.title, artistterm, term, losslessOnly)
    ]

    # Additional filtering for size etc
    if results and not choose_specific_download:
        results = more_filtering(results, album, albumlength, new)

    return results


# THIS IS KIND OF A MESS AND PROBABLY NEEDS TO BE CLEANED UP
